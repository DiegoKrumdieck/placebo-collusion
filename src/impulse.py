"""Impulse-response forks (CLAUDE.md, Tests 5), with the spec fixed before any results.

Every finished baseline and instructed game is forked at period 200 into two branches that both run
periods 201-220 with the same model and settings, restoring price history and notes from the logs:
- forced:  firm 0's period-201 price is set to the Nash price instead of its own choice. Firm 0 is still
           queried in period 201 and its notes from that call are kept as written.
- control: a fresh rerun of periods 201-220 with no intervention.
Outcome: firm 1's price in periods 202-220, forced minus control, per game.

Usage:
    python src/impulse.py fork --condition baseline --run-id baseline_001 --branch forced
    python src/impulse.py launch --concurrency 9   # refuses until all 27 games are done; model etc. come from each game's config
    python src/impulse.py analyze
Output: data/forks/<condition>/<run_id>/<branch>/{config.json, periods.csv, llm.jsonl, state.json}
"""

import argparse
import csv
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import build_prompt, load_prompt_blocks, prefix_for, query_agent  # noqa: E402
from market import Market  # noqa: E402
from run import PERIOD_COLUMNS, ROOT, write_json_atomic  # noqa: E402

FORK_AFTER = 200  # history and notes restored through period 200
FORCED_PERIOD = 201
LAST_PERIOD = 220
FORCED_FIRM = 0
RESPONDER = 1
BRANCHES = ("forced", "control")
CUT_WINDOW = (202, 204)  # "cut its price within 3 periods of the forced cut"
RESPONSE_TOL = 0.01  # CLAUDE.md: a response is a forced-minus-control gap beyond 0.01; "back" is within 0.01
BR_CUT_PRICE = 1.47  # best-response benchmark evaluated at 1.47, as specified
FORK_COLUMNS = PERIOD_COLUMNS + ["branch", "chosen_price", "forced"]


def restore_state(run_dir: Path, after: int = FORK_AFTER) -> tuple[dict, dict, list[dict]]:
    """Rebuild the runner's per-firm state at the end of period `after` from the game's logs.

    Returns (config, state, original period-(after+1) llm records). Notes are the last parsed plans and
    insights at or before `after` (the runner keeps the old notes after a parse failure).
    """
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    with (run_dir / "periods.csv").open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if int(r["period"]) <= after]
    if max(int(r["period"]) for r in rows) < after:
        raise ValueError(f"{run_dir} has not reached period {after}")
    firms = [{"plans": "", "insights": "", "history": [], "last_price": None} for _ in range(2)]
    for r in sorted(rows, key=lambda r: (int(r["period"]), int(r["firm"]))):
        f = firms[int(r["firm"])]
        f["history"].append({"period": int(r["period"]), "my_price": float(r["price"]),
                             "competitor_price": float(r["competitor_price"]),
                             "my_quantity": float(r["quantity"]), "my_profit": float(r["profit"])})
        f["last_price"] = float(r["price"])
    next_records = {}
    with (run_dir / "llm.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if rec["period"] <= after and rec["parsed"] is not None:
                firms[rec["firm"]]["plans"] = rec["parsed"]["plans"]
                firms[rec["firm"]]["insights"] = rec["parsed"]["insights"]
            elif rec["period"] == after + 1:
                next_records[rec["firm"]] = rec
    for f in firms:
        f["history"] = f["history"][-100:]
    return config, {"last_period": after, "firms": firms}, next_records


def run_fork(condition: str, run_id: str, branch: str, client, runs_root: Path, forks_root: Path,
             max_parse_retries: int = 3, max_tokens: int = 4000) -> Path:
    """Run one branch of one game's fork. Resumable: re-running continues after the last saved period."""
    assert branch in BRANCHES
    src = runs_root / condition / run_id
    out = forks_root / condition / run_id / branch
    out.mkdir(parents=True, exist_ok=True)
    cfg_path, periods_path, llm_path, state_path = (out / n for n in ("config.json", "periods.csv", "llm.jsonl", "state.json"))

    game_cfg, state0, original_next = restore_state(src)
    blocks = load_prompt_blocks()
    prefix_name, prefix = prefix_for(condition, blocks)
    if prefix_name != game_cfg["prompt_prefix"]:
        raise ValueError(f"prompt prefix changed: {game_cfg['prompt_prefix']} -> {prefix_name}")
    market = Market(alpha=game_cfg["alpha"], ceiling_multiplier=game_cfg["ceiling_multiplier"])
    model = game_cfg["model"]

    # The restored state must reproduce the game's own period-201 prompts exactly.
    for firm in (0, 1):
        f = state0["firms"][firm]
        rebuilt = build_prompt(blocks, prefix, market.marginal_cost, market.ceiling, f["plans"], f["insights"], f["history"])
        if firm in original_next and rebuilt != original_next[firm]["prompt"]:
            raise ValueError(f"{run_id} firm {firm}: restored period-{FORCED_PERIOD} prompt differs from the logged one")

    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = state0
        write_json_atomic(cfg_path, {
            **{k: game_cfg[k] for k in ("condition", "model", "thinking", "temperature", "temperature_sent_to_api",
                                        "alpha", "ceiling_multiplier", "prompt_prefix", "prompt_version")},
            "run_id": run_id, "branch": branch, "fork_after_period": FORK_AFTER, "forced_period": FORCED_PERIOD,
            "forced_firm": FORCED_FIRM, "forced_price": market.nash_price if branch == "forced" else None,
            "last_period": LAST_PERIOD, "source_git_commit": game_cfg.get("git_commit"),
            "max_parse_retries": max_parse_retries, "max_tokens": max_tokens,
            "start_time": datetime.now(timezone.utc).isoformat(),
        })
        with periods_path.open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=FORK_COLUMNS).writeheader()

    def call(prompt):
        return query_agent(client, model, prompt, max_parse_retries, max_tokens)

    with ThreadPoolExecutor(max_workers=2) as pool:
        for period in range(state["last_period"] + 1, LAST_PERIOD + 1):
            firms = state["firms"]
            prompts = [build_prompt(blocks, prefix, market.marginal_cost, market.ceiling,
                                    f["plans"], f["insights"], f["history"]) for f in firms]
            results = list(pool.map(call, prompts))
            chosen, parse_ok = [], []
            for firm, res in enumerate(results):
                ok = res.parsed is not None
                chosen.append(res.parsed["price"] if ok else firms[firm]["last_price"])
                parse_ok.append(ok)
            prices = list(chosen)
            forced = [False, False]
            if branch == "forced" and period == FORCED_PERIOD:
                prices[FORCED_FIRM] = market.nash_price
                forced[FORCED_FIRM] = True
            quantities, profits = market.outcome(prices[0], prices[1])

            with llm_path.open("a", encoding="utf-8") as fh:
                for firm, res in enumerate(results):
                    fh.write(json.dumps({"run_id": run_id, "branch": branch, "period": period, "firm": firm,
                                         "prompt": prompts[firm], "attempts": res.attempts, "parsed": res.parsed,
                                         "parse_ok": parse_ok[firm], "n_retries": res.n_retries,
                                         "chosen_price": chosen[firm], "price_used": prices[firm],
                                         "forced": forced[firm]}) + "\n")
            with periods_path.open("a", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=FORK_COLUMNS)
                for firm in range(2):
                    w.writerow({"run_id": run_id, "condition": condition, "model": model,
                                "temperature": game_cfg["temperature"], "alpha": game_cfg["alpha"], "period": period,
                                "firm": firm, "price": prices[firm], "competitor_price": prices[1 - firm],
                                "quantity": quantities[firm], "profit": profits[firm],
                                "nash_price": market.nash_price, "monopoly_price": market.monopoly_price,
                                "parse_ok": parse_ok[firm], "n_retries": results[firm].n_retries,
                                "branch": branch, "chosen_price": chosen[firm], "forced": forced[firm]})
            for firm, res in enumerate(results):
                f = firms[firm]
                if res.parsed is not None:  # notes kept as written, also for the forced firm
                    f["plans"], f["insights"] = res.parsed["plans"], res.parsed["insights"]
                f["last_price"] = prices[firm]
                f["history"].append({"period": period, "my_price": prices[firm], "competitor_price": prices[1 - firm],
                                     "my_quantity": quantities[firm], "my_profit": profits[firm]})
                f["history"] = f["history"][-100:]
            state["last_period"] = period
            write_json_atomic(state_path, state)
            print(f"{run_id} {branch} period {period}  p0={prices[0]:.2f}  p1={prices[1]:.2f}  ok={parse_ok}", flush=True)
    return out


# ---------- launching (only after the batch has finished) ----------

def finished_games(runs_root: Path, periods: int = 300) -> list[tuple[str, str]]:
    """Every baseline and instructed game. Raises if any game is unfinished, so forks never compete with the batch."""
    games, unfinished = [], []
    for condition in ("baseline", "instructed"):
        for d in sorted((runs_root / condition).iterdir()):
            if not (d / "state.json").exists():
                continue
            last = json.loads((d / "state.json").read_text(encoding="utf-8"))["last_period"]
            (games if last >= periods else unfinished).append((condition, d.name))
    if unfinished:
        raise SystemExit(f"Batch not finished; refusing to run. Unfinished: {[r for _, r in unfinished]}")
    return games


def launch(concurrency: int, runs_root: Path, expected: int) -> None:
    games = finished_games(runs_root)
    if len(games) != expected:
        raise SystemExit(f"Expected {expected} finished games, found {len(games)}")
    jobs = [(c, r, b) for c, r in games for b in BRANCHES]
    running, queue = {}, list(jobs)
    log_path = ROOT / "data" / "forks" / "launcher.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg):
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log(f"fork launch: {len(jobs)} branches, concurrency {concurrency}")
    restarts = {}
    while queue or running:
        for job, proc in list(running.items()):
            code = proc.poll()
            if code is None:
                continue
            del running[job]
            if code == 0:
                log(f"finished {job[1]} {job[2]}")
            elif restarts.get(job, 0) < 3:
                restarts[job] = restarts.get(job, 0) + 1
                log(f"{job[1]} {job[2]} exited {code}; resuming (restart {restarts[job]})")
                queue.insert(0, job)
            else:
                log(f"GAVE UP on {job[1]} {job[2]}")
        while queue and len(running) < concurrency:
            c, r, b = job = queue.pop(0)
            out = ROOT / "data" / "forks" / c / r / b
            out.mkdir(parents=True, exist_ok=True)
            fh = (out / "stdout.log").open("a", encoding="utf-8")
            running[job] = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "fork", "--condition", c,
                                             "--run-id", r, "--branch", b], cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
            log(f"started {r} {b}")
            time.sleep(5)
        time.sleep(10)
    log("fork launch done")


# ---------- analysis ----------

def load_branch(forks_root: Path, condition: str, run_id: str, branch: str) -> pd.DataFrame | None:
    p = forks_root / condition / run_id / branch / "periods.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    return df.pivot(index="period", columns="firm", values="price")


def best_response(p0: float, market: Market) -> float:
    """Firm 1's price maximizing its one-period profit against firm 0's price p0, over [marginal cost, ceiling]."""
    res = minimize_scalar(lambda p1: -market.outcome(p0, p1)[1][1],
                          bounds=(market.marginal_cost, market.ceiling), method="bounded", options={"xatol": 1e-7})
    return float(res.x)


def classify(fo: pd.DataFrame, co: pd.DataFrame, p0_200: float, dbr: float) -> dict:
    """Outcome categories for one game (CLAUDE.md, Tests 5). fo/co: forced/control prices, index period, columns firm."""
    D = (fo[RESPONDER] - co[RESPONDER]).loc[FORCED_PERIOD + 1 : LAST_PERIOD]
    w0, w1 = CUT_WINDOW
    early_min = float(D.loc[w0:w1].min())
    responded = early_min < -RESPONSE_TOL
    back = fo[FORCED_FIRM].loc[FORCED_PERIOD + 1 : LAST_PERIOD].sub(p0_200).abs() <= RESPONSE_TOL
    t0 = int(back.idxmax()) if back.any() else None
    deeper = early_min < -abs(dbr)
    stays_cut = (t0 is not None and t0 + 3 <= LAST_PERIOD
                 and bool((D.loc[t0 + 1 : t0 + 3] < -RESPONSE_TOL).all()))
    return {
        "responded": responded,
        "punishment_like": bool(deeper or stays_cut),
        "deeper_than_myopic": bool(deeper),
        "stays_cut_after_firm0_back": bool(stays_cut),
        "returned": bool(abs(D.loc[LAST_PERIOD]) <= RESPONSE_TOL),
        "firm0_back": t0 is not None,
        "firm0_back_period": t0,
        "firm0_back_at_220": bool(abs(fo.loc[LAST_PERIOD, FORCED_FIRM] - p0_200) <= RESPONSE_TOL),
        "min_D_202_204": early_min,
        "D_220": float(D.loc[LAST_PERIOD]),
    }


def summarize(forks_root: Path, runs_root: Path) -> dict:
    """Per-game outcome categories, counts by condition, and mean responses by period."""
    per_game, by_period = [], []
    for condition in ("baseline", "instructed"):
        cdir = forks_root / condition
        if not cdir.exists():
            continue
        for gdir in sorted(d for d in cdir.iterdir() if d.is_dir()):
            fo, co = (load_branch(forks_root, condition, gdir.name, b) for b in BRANCHES)
            if fo is None or co is None or fo.index.max() < LAST_PERIOD or co.index.max() < LAST_PERIOD:
                continue
            cfg = json.loads((runs_root / condition / gdir.name / "config.json").read_text(encoding="utf-8"))
            market = Market(alpha=cfg["alpha"], ceiling_multiplier=cfg["ceiling_multiplier"])
            orig = pd.read_csv(runs_root / condition / gdir.name / "periods.csv")
            p0_200 = float(orig[(orig.period == FORK_AFTER) & (orig.firm == FORCED_FIRM)].price.iloc[0])
            br_actual, br_cut = best_response(p0_200, market), best_response(BR_CUT_PRICE, market)
            dbr = br_cut - br_actual
            per_game.append({"condition": condition, "run_id": gdir.name, "p0_period200": p0_200,
                             "BR_p0_200": br_actual, "BR_147": br_cut, "dBR": dbr,
                             **classify(fo, co, p0_200, dbr)})
            for t in range(FORCED_PERIOD + 1, LAST_PERIOD + 1):
                by_period.append({"condition": condition, "run_id": gdir.name, "period": t, "dBR": dbr,
                                  "D_firm1": fo.loc[t, RESPONDER] - co.loc[t, RESPONDER],
                                  "D_firm0": fo.loc[t, FORCED_FIRM] - co.loc[t, FORCED_FIRM],
                                  "firm0_forced_minus_p200": fo.loc[t, FORCED_FIRM] - p0_200})
    per_game, by_period = pd.DataFrame(per_game), pd.DataFrame(by_period)
    if per_game.empty:
        return {"per_game": per_game, "by_period": by_period, "counts": per_game}
    se = lambda x: x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan  # noqa: E731
    avg = (by_period.groupby(["condition", "period"])
           .agg(D_firm1_mean=("D_firm1", "mean"), D_firm1_se=("D_firm1", se), D_firm0_mean=("D_firm0", "mean"),
                firm0_forced_minus_p200_mean=("firm0_forced_minus_p200", "mean"), dBR_mean=("dBR", "mean"),
                n_games=("run_id", "nunique")).reset_index())
    cats = ["responded", "punishment_like", "deeper_than_myopic", "stays_cut_after_firm0_back", "returned", "firm0_back", "firm0_back_at_220"]
    counts = per_game.groupby("condition").agg(n_games=("run_id", "size"), **{c: (c, "sum") for c in cats}).reset_index()
    counts["returned_among_responded"] = [
        int(per_game[(per_game.condition == c) & per_game.responded].returned.sum()) for c in counts.condition]
    counts["mean_dBR"] = [float(per_game[per_game.condition == c].dBR.mean()) for c in counts.condition]
    return {"per_game": per_game, "by_period": avg, "counts": counts}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fork")
    f.add_argument("--condition", required=True, choices=["baseline", "instructed"])
    f.add_argument("--run-id", required=True)
    f.add_argument("--branch", required=True, choices=BRANCHES)
    lp = sub.add_parser("launch")
    lp.add_argument("--concurrency", type=int, default=9)
    lp.add_argument("--expected", type=int, default=27)
    sub.add_parser("analyze")
    args = ap.parse_args()

    runs_root, forks_root = ROOT / "data" / "runs", ROOT / "data" / "forks"
    if args.cmd == "fork":
        import anthropic
        from dotenv import load_dotenv
        finished_games(runs_root)  # never run a fork while the batch is still going
        load_dotenv(ROOT / ".env")
        run_fork(args.condition, args.run_id, args.branch, anthropic.Anthropic(max_retries=2), runs_root, forks_root)
    elif args.cmd == "launch":
        launch(args.concurrency, runs_root, args.expected)
    else:
        import figures
        res = summarize(forks_root, runs_root)
        out = ROOT / "results" / "impulse"
        out.mkdir(parents=True, exist_ok=True)
        for name, df in res.items():
            df.to_csv(out / f"{name}.csv", index=False)
        figures.impulse_response(res["by_period"], out / "fig5_impulse_response.png")
        print(res["counts"].to_string(index=False))


if __name__ == "__main__":
    main()
