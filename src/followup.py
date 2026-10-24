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


def run_instructed() -> None:
    """Instructed-only placebo: re-pair firms across the 6 instructed games (30 placebo pairs)."""
    from analyze import load_all
    OUT.mkdir(parents=True, exist_ok=True)
    _, instr, nash, mono = load_all()
    res = evaluate(instr, [], nash, mono, B=B, B_boot=B_BOOT, seed=SEED)
    s = res["summary"]
    s.insert(0, "row", "Haiku instructed (instructed-only placebo)")
    s.to_csv(OUT / "instructed_placebo_tests.csv", index=False)
    res["pairs"].to_csv(OUT / "instructed_placebo_pairs.csv", index=False)
    print(s[s.version == "all"][["test", "real_pooled", "placebo_null_mean", "placebo_null_p95", "p_value_real",
                                 "auroc_real_vs_placebo", "auroc_real_ci_low", "auroc_real_ci_high",
                                 "n_real", "n_placebo", "n_unidentified_real", "n_unidentified_placebo"]]
          .round(3).to_string(index=False))
    p = res["pairs"]
    print(p[["kind", "run_a", "run_b", "collusion_index"]].groupby("kind").collusion_index.describe().round(3).to_string())


def run_haiku_holdback() -> None:
    """Apply the committed rules (holdback_rules.py) to the Haiku hold-back fork."""
    root = ROOT / "data" / "holdback"
    rows, paths = [], []
    for cond in ("baseline", "instructed"):
        for gdir in sorted(d for d in (root / cond).iterdir() if d.is_dir()):
            br = {}
            for branch in ("forced", "control"):
                df = pd.read_csv(gdir / branch / "periods.csv")
                if df.period.max() < 220:
                    raise SystemExit(f"{gdir.name} {branch} unfinished")
                br[branch] = df.pivot(index="period", columns="firm", values="price")
            D = {t: br["forced"].loc[t, 1] - br["control"].loc[t, 1] for t in range(202, 221)}
            cfg = json.loads((gdir / "forced" / "config.json").read_text(encoding="utf-8"))
            row = {"row": f"Haiku {cond}", "run_id": gdir.name, "p0_200": cfg["firm0_period200_price"], **classify(D)}
            for branch in ("forced", "control"):
                row[f"share_firm1_below_147_{branch}"] = float((br[branch].loc[202:220, 1] < 1.47 - 1e-9).mean())
            rows.append(row)
            paths += [{"row": f"Haiku {cond}", "run_id": gdir.name, "period": t, "D": d} for t, d in D.items()]
    per_game = pd.DataFrame(rows)
    per_game.to_csv(OUT / "haiku_holdback_per_game.csv", index=False)
    pd.DataFrame(paths).to_csv(OUT / "haiku_holdback_D.csv", index=False)
    print(summarize_categories(per_game).to_string(index=False))
    print(per_game.round(3).to_string(index=False))


def main_table() -> pd.DataFrame:
    syn = pd.read_csv(OUT / "synthetic_tests.csv")
    base = pd.read_csv(ROOT / "results" / "real" / "tests_summary.csv")
    base.insert(0, "row", "Haiku baseline")
    ins = pd.read_csv(OUT / "instructed_placebo_tests.csv")
    ins["row"] = "Haiku instructed"
    tests = pd.concat([syn, base, ins])
    tests = tests[tests.version == "all"]
    cats = pd.concat([pd.read_csv(OUT / "synthetic_holdback_per_game.csv"), pd.read_csv(OUT / "haiku_holdback_per_game.csv")])
    counts = summarize_categories(cats).set_index("row")
    order = ["synthetic competitor", "synthetic colluder", "synthetic shocked competitor", "Haiku baseline", "Haiku instructed"]
    out = []
    for r in order:
        row = {"row": r}
        for test, name in (("fish_delta", "fish"), ("naive_delta", "naive")):
            t = tests[(tests.row == r) & (tests.test == test)]
            if len(t):
                t = t.iloc[0]
                row.update({f"{name}_real": t.real_pooled, f"{name}_placebo_mean": t.placebo_null_mean,
                            f"{name}_p": t.p_value_real, f"{name}_auroc": t.auroc_real_vs_placebo,
                            f"{name}_unidentified_real": f"{int(t.n_unidentified_real)}/{int(t.n_real)}"})
        if r in counts.index:
            row.update(counts.loc[r].to_dict())
        out.append(row)
    return pd.DataFrame(out)


def run_summary() -> None:
    import figures
    table = main_table()
    table.to_csv(OUT / "main_table.csv", index=False)
    D = pd.concat([pd.read_csv(OUT / "synthetic_holdback_D.csv"), pd.read_csv(OUT / "haiku_holdback_D.csv")])
    figures.holdback_mean_D(D, ["synthetic competitor", "synthetic colluder", "Haiku baseline", "Haiku instructed"],
                            OUT / "fig6_holdback_mean_D.png")
    print(table.round(3).to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["synthetic", "instructed", "holdback", "summary"])
    args = ap.parse_args()
    {"synthetic": run_synthetic, "instructed": run_instructed, "holdback": run_haiku_holdback,
     "summary": run_summary}[args.cmd]()


if __name__ == "__main__":
    main()
