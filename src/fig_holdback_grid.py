"""Hold-back fork figure for the report: 2x3 grid, mean firm-1 forced-minus-control price (±1 SE).

Reads existing result CSVs only (no API calls). Output: results/followup/fig8_holdback_grid.png
"""
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import figures as F  # noqa: E402  (reuse the report's colours and axis style)

FU = Path(__file__).parent.parent / "results" / "followup"
D = pd.concat([pd.read_csv(FU / f) for f in
               ["synthetic_holdback_D.csv", "noisy_holdback_D.csv", "haiku_holdback_D.csv", "strategy_holdback_D.csv"]])
PANELS = [("synthetic shocked competitor", "Rule-based competitor\n(facing a real cut)"),
          ("noisy colluder L=5", "Rule-based colluder\n(punishes 5 periods)"),
          ("noisy colluder L=10", "Rule-based colluder\n(punishes 10 periods)"),
          ("Haiku baseline", "Haiku baseline"),
          ("Haiku instructed", "Haiku instructed\n(keep prices high)"),
          ("Haiku strategy-instructed", "Haiku strategy-instructed\n(told to punish, then return)")]

fig, axes = plt.subplots(2, 3, figsize=(10, 6.2), sharey=True, sharex=True, facecolor=F.SURFACE)
for ax, (row, title) in zip(axes.flat, PANELS):
    F._style(ax)
    ax.grid(axis="y", color=F.GRID, linewidth=0.8)
    ax.axhline(0, color=F.INK2, linewidth=1)
    d = D[D.row == row].groupby("period").D
    mean, n = d.mean(), d.count()
    se = (d.std(ddof=1) / np.sqrt(n)).fillna(0)
    t = mean.index.to_numpy()
    ax.fill_between(t, mean - se, mean + se, color=F.COLORS["real"], alpha=0.18, linewidth=0)
    ax.plot(t, mean.values, color=F.COLORS["real"], linewidth=2, marker="o", markersize=3)
    ax.set_title(f"{title}  (n={int(n.iloc[0])})", color=F.INK, fontsize=10, loc="left")
    ax.xaxis.set_major_locator(matplotlib.ticker.FixedLocator([202, 207, 212, 217]))
    ax.tick_params(labelsize=9)
for ax in axes[:, 0]:
    ax.set_ylabel("Firm 1 price,\nforced minus control", color=F.INK2, fontsize=10)
fig.supxlabel("Period (firm 0 at 1.47 in period 201, back at its period-200 price from 202)", color=F.INK2, fontsize=10)
fig.tight_layout()
fig.savefig(FU / "fig8_holdback_grid.png", dpi=200, facecolor=F.SURFACE)
print("wrote", FU / "fig8_holdback_grid.png")
