"""Run the full batch of games, at most --concurrency at a time, with conditions mixed in every group.

Usage:
    python src/launch_batch.py --model claude-haiku-5-5 --baseline 21 --instructed 6 --concurrency 9

Each game is its own process running src/run.py; its output goes to data/runs/<condition>/<run_id>/stdout.log.
Finished games (state.json at the last period) are skipped, so re-running this command resumes the batch.
A game that exits with an error is resumed up to --max-restarts times.
Create data/runs/STOP to stop starting new games; running games finish normally.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data" / "runs"
PYTHON = sys.executable


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    with (RUNS / "launcher.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def interleave(n_base: int, n_instr: int) -> list[tuple[str, str]]:
    """Spread instructed games evenly through the queue so every group of games mixes both conditions."""
    base = [("baseline", f"baseline_{i:03d}") for i in range(1, n_base + 1)]
    instr = [("instructed", f"instructed_{i:03d}") for i in range(1, n_instr + 1)]
    total = n_base + n_instr
    # Instructed game j goes at the position closest to (j + 0.5) * total / n_instr.
    slots = {round((j + 0.5) * total / n_instr - 0.5) for j in range(n_instr)} if n_instr else set()
    queue, bi, ii = [], iter(base), iter(instr)
    for pos in range(total):
        queue.append(next(ii) if pos in slots else next(bi))
    return queue


def last_period(condition: str, run_id: str) -> int:
    state = RUNS / condition / run_id / "state.json"
    return json.loads(state.read_text(encoding="utf-8"))["last_period"] if state.exists() else 0


PRICES_PER_MTOK = {"claude-haiku-5-5": (0.10, 0.50)}  # input, output USD per million tokens


class SpendTracker:
    """Running API spend of the games in this launch, read incrementally from their llm.jsonl files."""

    def __init__(self, games, model: str):
        self.files = [RUNS / c / r / "llm.jsonl" for c, r in games]
        self.offsets = {f: 0 for f in self.files}
        self.p_in, self.p_out = PRICES_PER_MTOK[model]
        self.total = 0.0

    def update(self) -> float:
        for f in self.files:
            if not f.exists():
                continue
            with f.open("rb") as fh:
                fh.seek(self.offsets[f])
                data = fh.read()
            end = data.rfind(b"\n") + 1  # only complete lines
            for line in data[:end].splitlines():
                for a in json.loads(line)["attempts"]:
                    self.total += a["input_tokens"] / 1e6 * self.p_in + a["output_tokens"] / 1e6 * self.p_out
            self.offsets[f] += end
        return self.total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--baseline", type=int, default=21)
    ap.add_argument("--instructed", type=int, default=6)
    ap.add_argument("--strategy-instructed", type=int, default=0)
    ap.add_argument("--cost-cap", type=float, default=None,
                    help="stop every game in this launch once their logged spend reaches this many USD")
    ap.add_argument("--periods", type=int, default=300)
    ap.add_argument("--concurrency", type=int, default=9)
    ap.add_argument("--max-restarts", type=int, default=3)
    ap.add_argument("--stagger-s", type=float, default=10.0, help="pause between starting games")
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    games = interleave(args.baseline, args.instructed) + [
        ("strategy_instructed", f"strategy_instructed_{i:03d}") for i in range(1, args.strategy_instructed + 1)]
    queue = [g for g in games if last_period(*g) < args.periods]
    tracker = SpendTracker(games, args.model) if args.cost_cap is not None else None
    log(f"batch start: {len(queue)} games to run, concurrency {args.concurrency}, order "
        + " ".join({"instructed": "I", "baseline": "B"}.get(c, "S") for c, _ in queue)
        + (f", cost cap ${args.cost_cap:.2f}" if tracker else ""))
    running: dict[tuple[str, str], subprocess.Popen] = {}
    restarts: dict[tuple[str, str], int] = {}
    failed: list[tuple[str, str]] = []

    while queue or running:
        if tracker and tracker.update() >= args.cost_cap:
            for proc in running.values():
                proc.terminate()
            log(f"COST CAP reached (${tracker.total:.2f}); stopped {len(running)} running games, "
                f"{len(queue)} not started. Games are resumable.")
            return
        for game, proc in list(running.items()):
            code = proc.poll()
            if code is None:
                continue
            del running[game]
            done = last_period(*game)
            if code == 0 and done >= args.periods:
                log(f"finished {game[1]}")
            elif restarts.get(game, 0) < args.max_restarts:
                restarts[game] = restarts.get(game, 0) + 1
                log(f"{game[1]} exited with code {code} at period {done}; resuming (restart {restarts[game]})")
                queue.insert(0, game)
            else:
                log(f"GAVE UP on {game[1]} at period {done} after {args.max_restarts} restarts")
                failed.append(game)

        stop = (RUNS / "STOP").exists()
        while queue and len(running) < args.concurrency and not stop:
            condition, run_id = game = queue.pop(0)
            run_dir = RUNS / condition / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            out = (run_dir / "stdout.log").open("a", encoding="utf-8")
            running[game] = subprocess.Popen(
                [PYTHON, str(ROOT / "src" / "run.py"), "--condition", condition, "--model", args.model,
                 "--periods", str(args.periods), "--run-id", run_id],
                cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
            )
            log(f"started {run_id} (from period {last_period(*game) + 1}); running {len(running)}, queued {len(queue)}")
            time.sleep(args.stagger_s)
        if stop and queue and not running:
            log(f"STOP file present: leaving {len(queue)} games unstarted")
            break
        time.sleep(15)

    log(f"batch end: {len(failed)} failed" + (f" ({', '.join(r for _, r in failed)})" if failed else "")
        + (f"; spent ${tracker.update():.2f}" if tracker else ""))


if __name__ == "__main__":
    main()
