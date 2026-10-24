"""Follow-up analyses (CLAUDE.md, Follow-up): synthetic agents, hold-back classification, instructed-only placebo.

Usage:
    python src/followup.py synthetic     # placebo tests + hold-back fork on the synthetic agents (no API)
    python src/followup.py instructed    # instructed-only placebo (no API)
    python src/followup.py holdback      # apply the committed rules to the Haiku hold-back fork
    python src/followup.py summary       # main table and figure
Writes to results/followup/.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import synthetic_agents as sa  # noqa: E402
from holdback_rules import classify, summarize_categories  # noqa: E402
from stats import evaluate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "followup"
NASH, MONO = sa._MARKET.nash_price, sa._MARKET.monopoly_price
B, B_BOOT, SEED = 1000, 1000, 20261024


def run_synthetic() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tests, cats, paths = [], [], []
    for agent in ("competitor", "colluder", "shocked competitor"):
        if agent != "shocked competitor":
            res = evaluate(sa.games(agent), [], NASH, MONO, B=B, B_boot=B_BOOT, seed=SEED)
            s = res["summary"]
            s.insert(0, "row", f"synthetic {agent}")
            tests.append(s)
        forks = sa.holdback_shocked_competitor() if agent == "shocked competitor" else sa.holdback(agent)
        for g in forks:
            D = {t: g["forced"][t] - g["control"][t] for t in range(202, 221)}
            cats.append({"row": f"synthetic {agent}", "run_id": g["run_id"], "p0_200": g["p0_200"], **classify(D)})
            paths += [{"row": f"synthetic {agent}", "run_id": g["run_id"], "period": t, "D": d} for t, d in D.items()]
    pd.concat(tests).to_csv(OUT / "synthetic_tests.csv", index=False)
    cats = pd.DataFrame(cats)
    cats.to_csv(OUT / "synthetic_holdback_per_game.csv", index=False)
    pd.DataFrame(paths).to_csv(OUT / "synthetic_holdback_D.csv", index=False)
    print(summarize_categories(cats).to_string(index=False))
    show = pd.concat(tests)
    print(show[show.test.isin(["fish_delta", "naive_delta"])][
        ["row", "test", "version", "real_pooled", "placebo_null_mean", "p_value_real", "auroc_real_vs_placebo",
         "n_unidentified_real", "n_unidentified_placebo"]].round(3).to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["synthetic", "instructed", "holdback", "summary"])
    args = ap.parse_args()
    {"synthetic": run_synthetic}[args.cmd]()


if __name__ == "__main__":
    main()
