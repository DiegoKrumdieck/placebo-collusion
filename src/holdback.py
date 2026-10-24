"""Hold-back fork (CLAUDE.md, Follow-up (a)): firm 0 is exogenous, firm 1 is the only LLM call.

Every game is forked at period 200, restoring firm 1's history and notes from the logs.
- forced:  firm 0 = 1.47 in period 201, then firm 0's own period-200 price in 202-220.
- control: firm 0 = its own period-200 price in 201-220.
Fork processes print progress only, never prices, so results stay unseen until the rules are committed.

Usage:
    python src/holdback.py fork --condition baseline --run-id baseline_001 --branch forced
    python src/holdback.py launch --concurrency 9     # refuses unless all 27 games are finished; $5 hard cap
Output: data/holdback/<condition>/<run_id>/<branch>/{config.json, periods.csv, llm.jsonl, state.json}
"""

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import build_prompt, load_prompt_blocks, prefix_for, query_agent  # noqa: E402
from impulse import FORK_AFTER, LAST_PERIOD, finished_games, restore_state  # noqa: E402
from market import Market  # noqa: E402
from run import PERIOD_COLUMNS, ROOT, write_json_atomic  # noqa: E402

FORCED_PRICE = 1.47
BRANCHES = ("forced", "control", "control2")  # control2: a second, identical control (CLAUDE.md, Follow-up (e))
COLUMNS = PERIOD_COLUMNS + ["branch", "exogenous"]
PRICES_PER_MTOK = {"claude-haiku-5-5": (0.10, 0.50)}  # input, output USD per million tokens
COST_CAP, COST_STOP_STARTING = 5.00, 4.50
HOLDBACK_ROOT = ROOT / "data" / "holdback"


def firm0_price(branch: str, period: int, p0_200: float) -> float:
    return FORCED_PRICE if branch == "forced" and period == FORK_AFTER + 1 else p0_200


def run_holdback(condition: str, run_id: str, branch: str, client, runs_root: Path, out_root: Path,
                 max_parse_retries: int = 3, max_tokens: int = 4000, verbose: bool = True,
                 last_period: int = LAST_PERIOD) -> Path:
    """One branch of one game. Resumable; a finished branch can be extended by passing a later last_period."""
    assert branch in BRANCHES
    out = out_root / condition / run_id / branch
    out.mkdir(parents=True, exist_ok=True)
    cfg_path, periods_path, llm_path, state_path = (out / n for n in ("config.json", "periods.csv", "llm.jsonl", "state.json"))

    game_cfg, state0, original_next = restore_state(runs_root / condition / run_id)
    blocks = load_prompt_blocks()
    prefix_name, prefix = prefix_for(condition, blocks)
    if prefix_name != game_cfg["prompt_prefix"]:
        raise ValueError(f"prompt prefix changed: {game_cfg['prompt_prefix']} -> {prefix_name}")
    market = Market(alpha=game_cfg["alpha"], ceiling_multiplier=game_cfg["ceiling_multiplier"])
    model = game_cfg["model"]
    f1 = state0["firms"][1]
    rebuilt = build_prompt(blocks, prefix, market.marginal_cost, market.ceiling, f1["plans"], f1["insights"], f1["history"])
    if 1 in original_next and rebuilt != original_next[1]["prompt"]:
        raise ValueError(f"{run_id}: restored firm-1 period-{FORK_AFTER + 1} prompt differs from the logged one")
    p0_200 = state0["firms"][0]["last_price"]

    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        if last_period > cfg.get("extended_to", cfg["last_period"]):
            write_json_atomic(cfg_path, {**cfg, "extended_to": last_period,  # CLAUDE.md, Follow-up (i)
                                         "extension_start_time": datetime.now(timezone.utc).isoformat()})
    else:
        state = state0
        write_json_atomic(cfg_path, {
            **{k: game_cfg[k] for k in ("condition", "model", "thinking", "temperature", "temperature_sent_to_api",
                                        "alpha", "ceiling_multiplier", "prompt_prefix", "prompt_version")},
            "run_id": run_id, "branch": branch, "design": "hold-back", "fork_after_period": FORK_AFTER,
            "firm0_period200_price": p0_200, "forced_price": FORCED_PRICE if branch == "forced" else None,
            "last_period": LAST_PERIOD, "source_git_commit": game_cfg.get("git_commit"),
            "max_parse_retries": max_parse_retries, "max_tokens": max_tokens,
            "start_time": datetime.now(timezone.utc).isoformat(),
        })
        with periods_path.open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=COLUMNS).writeheader()

    for period in range(state["last_period"] + 1, last_period + 1):
        f1 = state["firms"][1]
        prompt = build_prompt(blocks, prefix, market.marginal_cost, market.ceiling, f1["plans"], f1["insights"], f1["history"])
        res = query_agent(client, model, prompt, max_parse_retries, max_tokens)
        ok = res.parsed is not None
        prices = [firm0_price(branch, period, p0_200), res.parsed["price"] if ok else f1["last_price"]]
        quantities, profits = market.outcome(prices[0], prices[1])
        with llm_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"run_id": run_id, "branch": branch, "period": period, "firm": 1, "prompt": prompt,
                                 "attempts": res.attempts, "parsed": res.parsed, "parse_ok": ok,
                                 "n_retries": res.n_retries, "price_used": prices[1],
                                 "competitor_price": prices[0]}) + "\n")
        with periods_path.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            for firm in (0, 1):
                w.writerow({"run_id": run_id, "condition": condition, "model": model,
                            "temperature": game_cfg["temperature"], "alpha": game_cfg["alpha"], "period": period,
                            "firm": firm, "price": prices[firm], "competitor_price": prices[1 - firm],
                            "quantity": quantities[firm], "profit": profits[firm],
                            "nash_price": market.nash_price, "monopoly_price": market.monopoly_price,
                            "parse_ok": ok if firm == 1 else "", "n_retries": res.n_retries if firm == 1 else "",
                            "branch": branch, "exogenous": firm == 0})
        for firm in (0, 1):
            f = state["firms"][firm]
            if firm == 1 and ok:
                f["plans"], f["insights"] = res.parsed["plans"], res.parsed["insights"]
            f["last_price"] = prices[firm]
            f["history"].append({"period": period, "my_price": prices[firm], "competitor_price": prices[1 - firm],
                                 "my_quantity": quantities[firm], "my_profit": profits[firm]})
            f["history"] = f["history"][-100:]
        state["last_period"] = period
        write_json_atomic(state_path, state)
        if verbose:
            print(f"{run_id} {branch} period {period} done", flush=True)  # progress only: no prices
    return out


def spent_usd(root: Path = HOLDBACK_ROOT) -> float:
    total = 0.0
    for f in root.glob("*/*/*/llm.jsonl"):
        model = json.loads((f.parent / "config.json").read_text(encoding="utf-8"))["model"]
        p_in, p_out = PRICES_PER_MTOK[model]
        for line in f.open(encoding="utf-8"):
            for a in json.loads(line)["attempts"]:
                total += a["input_tokens"] / 1e6 * p_in + a["output_tokens"] / 1e6 * p_out
    return total


def finished_in(runs_root: Path, conditions, periods: int = 300) -> list[tuple[str, str]]:
    """Every game of the given conditions; raises if any is unfinished."""
    if tuple(conditions) == ("baseline", "instructed"):
        return finished_games(runs_root)
    games, unfinished = [], []
    for condition in conditions:
        for d in sorted((runs_root / condition).iterdir()):
            if (d / "state.json").exists():
                last = json.loads((d / "state.json").read_text(encoding="utf-8"))["last_period"]
                (games if last >= periods else unfinished).append((condition, d.name))
    if unfinished:
        raise SystemExit(f"Games not finished; refusing to run. Unfinished: {[r for _, r in unfinished]}")
    return games


def launch(concurrency: int, runs_root: Path, expected: int, branches=("forced", "control"), cap: float = COST_CAP,
           conditions=("baseline", "instructed"), only=None, last_period: int = LAST_PERIOD) -> None:
    """Run the given branches for every game (or only the `only` list of "condition/run_id") up to last_period.
    `cap` limits spend by this launch (USD), on top of earlier spend."""
    games = finished_in(runs_root, conditions)
    if only:
        wanted = {tuple(g.split("/")) for g in only}
        missing = wanted - set(games)
        if missing:
            raise SystemExit(f"unknown games: {sorted(missing)}")
        games = [g for g in games if g in wanted]
    if len(games) != expected:
        raise SystemExit(f"Expected {expected} finished games, found {len(games)}")
    for c, r in games:
        model = json.loads((runs_root / c / r / "config.json").read_text(encoding="utf-8"))["model"]
        if model not in PRICES_PER_MTOK:
            raise SystemExit(f"no price for model {model}; refusing to launch without a cost cap")
    queue = [(c, r, b) for c, r in games for b in branches
             if not _done(HOLDBACK_ROOT / c / r / b, last_period)]
    HOLDBACK_ROOT.mkdir(parents=True, exist_ok=True)
    spent_before = spent_usd()
    stop_starting = cap - (COST_CAP - COST_STOP_STARTING)  # same $0.50 headroom as the original cap
    log_path = HOLDBACK_ROOT / "launcher.log"

    def log(msg):
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log(f"hold-back launch: {len(queue)} branches {list(branches)}, concurrency {concurrency}, "
        f"cap ${cap:.2f} of new spend (already spent ${spent_before:.2f})")
    running, restarts = {}, {}
    while queue or running:
        spent = spent_usd() - spent_before
        if spent >= cap:
            for proc in running.values():
                proc.terminate()
            log(f"COST CAP reached (${spent:.2f}); stopped {len(running)} running branches, {len(queue)} not started")
            return
        for job, proc in list(running.items()):
            code = proc.poll()
            if code is None:
                continue
            del running[job]
            if code == 0:
                log(f"finished {job[1]} {job[2]} (spent so far ${spent:.2f})")
            elif restarts.get(job, 0) < 3:
                restarts[job] = restarts.get(job, 0) + 1
                log(f"{job[1]} {job[2]} exited {code}; resuming (restart {restarts[job]})")
                queue.insert(0, job)
            else:
                log(f"GAVE UP on {job[1]} {job[2]}")
        while queue and len(running) < concurrency and spent < stop_starting:
            c, r, b = job = queue.pop(0)
            out = HOLDBACK_ROOT / c / r / b
            out.mkdir(parents=True, exist_ok=True)
            fh = (out / "stdout.log").open("a", encoding="utf-8")
            running[job] = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "fork", "--condition", c,
                                             "--run-id", r, "--branch", b, "--conditions", *conditions,
                                             "--last-period", str(last_period)],
                                            cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
            log(f"started {r} {b}")
            time.sleep(3)
        if queue and spent >= stop_starting and not running:
            log(f"spend ${spent:.2f} reached the stop-starting level; {len(queue)} branches not started")
            return
        time.sleep(10)
    log(f"hold-back launch done; this launch spent ${spent_usd() - spent_before:.2f} (total ${spent_usd():.2f})")


def _done(branch_dir: Path, last_period: int = LAST_PERIOD) -> bool:
    s = branch_dir / "state.json"
    return s.exists() and json.loads(s.read_text(encoding="utf-8"))["last_period"] >= last_period


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    conds = ["baseline", "instructed", "strategy_instructed"]
    f = sub.add_parser("fork")
    f.add_argument("--condition", required=True, choices=conds)
    f.add_argument("--run-id", required=True)
    f.add_argument("--branch", required=True, choices=BRANCHES)
    f.add_argument("--conditions", nargs="+", default=["baseline", "instructed"], choices=conds)
    f.add_argument("--last-period", type=int, default=LAST_PERIOD)
    lp = sub.add_parser("launch")
    lp.add_argument("--only", nargs="+", default=None, help="restrict to these condition/run_id games")
    lp.add_argument("--last-period", type=int, default=LAST_PERIOD)
    lp.add_argument("--concurrency", type=int, default=9)
    lp.add_argument("--expected", type=int, default=27)
    lp.add_argument("--branches", nargs="+", default=["forced", "control"], choices=BRANCHES)
    lp.add_argument("--cap", type=float, default=COST_CAP, help="USD cap on spend by this launch")
    lp.add_argument("--conditions", nargs="+", default=["baseline", "instructed"], choices=conds)
    args = ap.parse_args()
    runs_root = ROOT / "data" / "runs"
    if args.cmd == "fork":
        import anthropic
        from dotenv import load_dotenv
        finished_in(runs_root, args.conditions)  # never fork while games of these conditions still run
        load_dotenv(ROOT / ".env")
        run_holdback(args.condition, args.run_id, args.branch, anthropic.Anthropic(max_retries=2), runs_root, HOLDBACK_ROOT,
                     last_period=args.last_period)
    else:
        launch(args.concurrency, runs_root, args.expected, branches=args.branches, cap=args.cap,
               conditions=tuple(args.conditions), only=args.only, last_period=args.last_period)


if __name__ == "__main__":
    main()
