"""Run one Fish et al.-style duopoly game between two LLM pricing agents.

Usage:
    python src/run.py --condition baseline --model claude-haiku-5-5 --periods 300 --run-id baseline_001

Writes data/runs/<condition>/<run_id>/{config.json, periods.csv, llm.jsonl, state.json}.
Re-running the same command resumes from the last completed period.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import PROMPT_VERSION, build_prompt, load_prompt_blocks, prefix_for, query_agent  # noqa: E402
from market import Market  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPERATURE = 1.0  # not sent to the API; 1.0 is the API default and Fish et al.'s value
PERIOD_COLUMNS = [
    "run_id", "condition", "model", "temperature", "alpha", "period", "firm", "price",
    "competitor_price", "quantity", "profit", "nash_price", "monopoly_price", "parse_ok", "n_retries",
]


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def write_json_atomic(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    # OneDrive can hold a file open briefly while syncing; retry instead of crashing the game.
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.5)


def truncate_periods_csv(path: Path, last_period: int) -> None:
    """Drop rows past the last period recorded in state.json (left by a crash mid-write)."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if int(r["period"]) <= last_period]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PERIOD_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", required=True, choices=["baseline", "instructed", "p2"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--periods", type=int, default=300)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--ceiling-multiplier", type=float, default=1.5)
    ap.add_argument("--max-parse-retries", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=4000)
    return ap.parse_args(argv)


def main() -> None:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    # SDK-level retries are kept short; agent.create_with_backoff handles long rate-limit waits.
    client = anthropic.Anthropic(max_retries=2)
    run_game(args, client, ROOT / "data" / "runs")


def run_game(args: argparse.Namespace, client, runs_root: Path) -> None:
    blocks = load_prompt_blocks()
    prefix_name, prefix = prefix_for(args.condition, blocks)
    market = Market(alpha=args.alpha, ceiling_multiplier=args.ceiling_multiplier)

    run_dir = runs_root / args.condition / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    config_path, periods_path = run_dir / "config.json", run_dir / "periods.csv"
    llm_path, state_path = run_dir / "llm.jsonl", run_dir / "state.json"

    config = {
        "run_id": args.run_id,
        "condition": args.condition,
        "model": args.model,
        "thinking": "disabled",
        "temperature": TEMPERATURE,
        "temperature_sent_to_api": False,
        "temperature_note": "No temperature parameter is sent; the API default of 1.0 applies (Fish et al. Appendix B also use 1).",
        "max_tokens": args.max_tokens,
        "max_parse_retries": args.max_parse_retries,
        "alpha": args.alpha,
        "ceiling_multiplier": args.ceiling_multiplier,
        "ceiling": market.ceiling,
        "marginal_cost": market.marginal_cost,
        "nash_price": market.nash_price,
        "monopoly_price": market.monopoly_price,
        "prompt_prefix": prefix_name,
        "prompt_version": PROMPT_VERSION,
        "history_window": 100,
        "periods": args.periods,
        "git_commit": git_commit(),
        "start_time": datetime.now(timezone.utc).isoformat(),
    }

    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        old = json.loads(config_path.read_text(encoding="utf-8"))
        for key in ["condition", "model", "alpha", "ceiling_multiplier", "prompt_prefix", "thinking", "temperature"]:
            if old[key] != config[key]:
                raise SystemExit(f"Refusing to resume: {key} was {old[key]!r}, now {config[key]!r}")
        if args.periods != old["periods"]:
            old["periods"] = args.periods
            write_json_atomic(config_path, old)
        truncate_periods_csv(periods_path, state["last_period"])
        print(f"Resuming {args.run_id} after period {state['last_period']}", flush=True)
    else:
        write_json_atomic(config_path, config)
        state = {
            "last_period": 0,
            "firms": [{"plans": "", "insights": "", "history": [], "last_price": None} for _ in range(2)],
        }
        with periods_path.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=PERIOD_COLUMNS).writeheader()

    def call(firm: int, prompt: str):
        return query_agent(client, args.model, prompt, args.max_parse_retries, args.max_tokens)

    with ThreadPoolExecutor(max_workers=2) as pool:
        for period in range(state["last_period"] + 1, args.periods + 1):
            firms = state["firms"]
            prompts = [
                build_prompt(blocks, prefix, market.marginal_cost, market.ceiling,
                             f["plans"], f["insights"], f["history"])
                for f in firms
            ]
            # Simultaneous moves: both agents see history only through period - 1.
            results = list(pool.map(call, [0, 1], prompts))

            prices, parse_ok = [], []
            for firm, res in enumerate(results):
                if res.parsed is not None:
                    prices.append(res.parsed["price"])
                    parse_ok.append(True)
                else:
                    if firms[firm]["last_price"] is None:
                        raise SystemExit(f"Period {period}, firm {firm}: no parsable price and no previous price to repeat.")
                    prices.append(firms[firm]["last_price"])
                    parse_ok.append(False)

            quantities, profits = market.outcome(prices[0], prices[1])

            with llm_path.open("a", encoding="utf-8") as f:
                for firm, res in enumerate(results):
                    f.write(json.dumps({
                        "run_id": args.run_id, "period": period, "firm": firm,
                        "prompt": prompts[firm],
                        "attempts": res.attempts,
                        "parsed": res.parsed,
                        "parse_ok": parse_ok[firm],
                        "n_retries": res.n_retries,
                        "price_used": prices[firm],
                    }) + "\n")
            with periods_path.open("a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=PERIOD_COLUMNS)
                for firm in range(2):
                    w.writerow({
                        "run_id": args.run_id, "condition": args.condition, "model": args.model,
                        "temperature": TEMPERATURE, "alpha": args.alpha, "period": period, "firm": firm,
                        "price": prices[firm], "competitor_price": prices[1 - firm],
                        "quantity": quantities[firm], "profit": profits[firm],
                        "nash_price": market.nash_price, "monopoly_price": market.monopoly_price,
                        "parse_ok": parse_ok[firm], "n_retries": results[firm].n_retries,
                    })

            for firm, res in enumerate(results):
                f_state = firms[firm]
                if res.parsed is not None:
                    f_state["plans"], f_state["insights"] = res.parsed["plans"], res.parsed["insights"]
                f_state["last_price"] = prices[firm]
                f_state["history"].append({
                    "period": period, "my_price": prices[firm], "competitor_price": prices[1 - firm],
                    "my_quantity": quantities[firm], "my_profit": profits[firm],
                })
                f_state["history"] = f_state["history"][-100:]
            state["last_period"] = period
            write_json_atomic(state_path, state)

            print(f"period {period:3d}  p0={prices[0]:.2f}  p1={prices[1]:.2f}  "
                  f"ok={parse_ok}  retries={[r.n_retries for r in results]}", flush=True)

    print("done", flush=True)


if __name__ == "__main__":
    main()
