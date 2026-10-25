"""Regenerate every result table and figure from the logs in data/. No API calls.

Usage:
    python src/reproduce.py            # all steps, in order
    python src/reproduce.py --list     # print the steps without running them

Needs the unpacked data archive in data/ (see README). Each step is the same command that produced
the committed results, so after a full run `git status results/` should show no changes.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS = [
    ["src/analyze.py", "diagnostic"],     # results/real: cross-game diagnostic, price changes
    ["src/analyze.py", "tests"],          # results/real: placebo tests, Table 1, figures 1-4
    ["src/analyze.py", "gap"],            # results/real: partner price-gap test
    ["src/impulse.py", "analyze"],        # results/impulse: first fork, figure 5
    ["src/validate_synthetic.py"],        # results/synthetic: pipeline check on known-answer paths
    ["src/followup.py", "synthetic"],     # results/followup: sticky competitor / colluder
    ["src/followup.py", "instructed"],    # instructed-only placebo
    ["src/followup.py", "holdback"],      # Haiku hold-back fork, committed rules
    ["src/followup.py", "noise"],         # control-vs-control noise threshold
    ["src/followup.py", "noisy"],         # noisy synthetic agents, punishment-length sweep
    ["src/followup.py", "br"],            # exploratory best-response position
    ["src/followup.py", "strategy"],      # strategy-instructed games
    ["src/followup.py", "extension"],     # hold-back extended to period 260
    ["src/followup.py", "summary"],       # main table, figures 6-7
    ["src/report_tables.py"],             # report tables A2 and 3
    ["src/fig_holdback_grid.py"],         # figure 8
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if not args.list and not (ROOT / "data" / "runs" / "baseline").is_dir():
        sys.exit("data/runs/baseline not found: unpack the data archive into data/ first (see README).")
    for i, step in enumerate(STEPS, 1):
        print(f"[{i}/{len(STEPS)}] python {' '.join(step)}", flush=True)
        if args.list:
            continue
        t0 = time.time()
        subprocess.run([sys.executable, *step], cwd=ROOT, check=True)
        print(f"    done in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
