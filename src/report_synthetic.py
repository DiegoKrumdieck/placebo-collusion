"""Print the synthetic validation results as compact tables (reads results/synthetic/validation.csv)."""

from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "results" / "synthetic"

d = pd.read_csv(OUT / "validation.csv")
cols = ["scenario", "test", "real_pooled", "placebo_null_mean", "placebo_null_p95", "p_value_real",
        "auroc_real_vs_placebo", "instructed_pooled", "power_instructed", "n_unidentified_real"]
pd.set_option("display.width", 250)
for version in ("all", "moving"):
    print(f"\n=== version: {version} ===")
    sub = d[(d.version == version) & d.test.isin(["fish_delta", "naive_delta", "collusion_index", "corr_diffs"])]
    print(sub[cols + ["n_real"]].round(3).to_string(index=False))
dg = pd.read_csv(OUT / "diagnostic.csv")
print("\n=== cross-game diagnostic (corr of first differences, periods 101-300) ===")
print(dg[dg.measure == "corr_diffs"][["scenario", "what", "n_defined", "n_undefined", "mean", "p95", "share_games_both_moving"]]
      .round(3).to_string(index=False))
