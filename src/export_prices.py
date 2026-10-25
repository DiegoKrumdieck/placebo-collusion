"""Write a prices-only CSV of every game and fork branch, for readers without the data archive.

Usage: python src/export_prices.py
Output: results/prices.csv with columns run_id, condition, branch, period, firm, price.
branch is "game" for the 300-period games (data/runs), "impulse_<branch>" for the first fork
(data/forks) and "holdback_<branch>" for the hold-back fork (data/holdback, incl. the 221-260 extension).
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COLS = ["run_id", "condition", "branch", "period", "firm", "price"]


def main() -> None:
    frames = []
    for f in sorted((DATA / "runs").glob("*/*/periods.csv")):
        frames.append(pd.read_csv(f).assign(branch="game"))
    for root, prefix in [("forks", "impulse_"), ("holdback", "holdback_")]:
        for f in sorted((DATA / root).glob("*/*/*/periods.csv")):
            frames.append(pd.read_csv(f).assign(branch=prefix + f.parent.name))
    d = pd.concat(frames)[COLS].sort_values(["condition", "run_id", "branch", "period", "firm"])
    d.to_csv(ROOT / "results" / "prices.csv", index=False)
    print(f"{len(d):,} rows, {d.groupby(['run_id', 'branch']).ngroups} game-branches -> results/prices.csv")


if __name__ == "__main__":
    main()
