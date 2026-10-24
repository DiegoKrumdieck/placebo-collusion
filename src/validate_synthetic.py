"""Run the full placebo evaluation and the cross-game diagnostic on each synthetic scenario.

Usage: python src/validate_synthetic.py [--B 1000]
Writes results/synthetic/{validation.csv, diagnostic.csv}. Synthetic data only; never reads data/runs.
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnostics  # noqa: E402
import figures  # noqa: E402
from stats import evaluate  # noqa: E402
from synthetic import MONOPOLY, NASH, SCENARIOS, scenario  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "results" / "synthetic"
FIGURE_SCENARIOS = ["follower", "shared_trajectory", "mostly_frozen"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--B", type=int, default=1000)
    ap.add_argument("--B-boot", type=int, default=500)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    summaries, diags = [], []
    for name in SCENARIOS:
        t0 = time.time()
        base, instr = scenario(name, seed=0)
        res = evaluate(base, instr, NASH, MONOPOLY, B=args.B, B_boot=args.B_boot, seed=1)
        if name in FIGURE_SCENARIOS:
            figures.all_figures(res, base, diagnostics.summarize(base), NASH, MONOPOLY, OUT / "figures" / name)
        s = res["summary"]
        s.insert(0, "scenario", name)
        summaries.append(s)
        d = diagnostics.summarize(base)
        c = d["correlations"]
        c.insert(0, "scenario", name)
        c["share_games_both_moving"] = d["share_games_both_moving"]
        diags.append(c)
        print(f"{name}: {time.time() - t0:.1f}s", flush=True)
    pd.concat(summaries).to_csv(OUT / "validation.csv", index=False)
    pd.concat(diags).to_csv(OUT / "diagnostic.csv", index=False)


if __name__ == "__main__":
    main()
