"""Analysis of the real runs. Refuses to run until every game in the batch has finished.

Usage:
    python src/analyze.py diagnostic   # cross-game diagnostic and price-change counts (run first)
    python src/analyze.py tests        # all detectors against the placebo null, plus figures
Writes to results/real/.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnostics  # noqa: E402
import figures  # noqa: E402
from detectors import fish_regression, naive_regression  # noqa: E402
from impulse import finished_games  # noqa: E402
from pairs import load_games, real_markets  # noqa: E402
from stats import evaluate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data" / "runs"
OUT = ROOT / "results" / "real"
EXPECTED = {"baseline": 21, "instructed": 6}


def load_all():
    finished_games(RUNS)  # raises if any game is unfinished
    base, instr = load_games(RUNS, "baseline"), load_games(RUNS, "instructed")
    for cond, games in (("baseline", base), ("instructed", instr)):
        if len(games) != EXPECTED[cond]:
            raise SystemExit(f"expected {EXPECTED[cond]} {cond} games, found {len(games)}")
    cfg = base[0].config
    return base, instr, cfg["nash_price"], cfg["monopoly_price"]


def price_levels(games, nash: float, mono: float, last: int = 50) -> "pd.DataFrame":
    """Per game: each firm's mean price over the last 50 periods, whether it held one price, and the game's Delta."""
    import pandas as pd
    rows = []
    for g in games:
        tail = g.prices[-last:]
        rows.append({"condition": g.condition, "run_id": g.run_id,
                     "firm0_mean_price": float(tail[:, 0].mean()), "firm1_mean_price": float(tail[:, 1].mean()),
                     "firm0_distinct_prices": int(len(set(tail[:, 0]))), "firm1_distinct_prices": int(len(set(tail[:, 1]))),
                     "collusion_index": float((tail.mean() - nash) / (mono - nash))})
    return pd.DataFrame(rows)


def gap_test(games, B: int = 1000, last: int = 50, seed: int = 20261024) -> tuple[dict, "pd.DataFrame"]:
    """Partner price-gap test: per game, mean |firm 0 - firm 1| over the last 50 periods.

    Statistic = mean gap across games. Null = the same statistic on B random re-pairings (derangements):
    firm 0 of game i with firm 1 of game perm[i]. One-sided: small real gaps are the signal, so
    p = (1 + #{null <= real}) / (1 + B). "Within one cent" = mean gap over the last 50 periods <= 0.01.
    """
    import numpy as np
    import pandas as pd
    from pairs import derangement
    tails = [g.prices[-last:] for g in games]
    gap = lambda a, b: float(np.abs(a - b).mean())  # noqa: E731
    per_game = pd.DataFrame({"run_id": [g.run_id for g in games],
                             "mean_abs_gap_last50": [gap(t[:, 0], t[:, 1]) for t in tails],
                             "final_abs_gap": [abs(t[-1, 0] - t[-1, 1]) for t in tails]})
    within = lambda gaps: int(sum(x <= 0.01 + 1e-9 for x in gaps))  # noqa: E731
    real = float(per_game.mean_abs_gap_last50.mean())
    rng = np.random.default_rng(seed)
    null, null_within = [], []
    for _ in range(B):
        perm = derangement(len(games), rng)
        gaps = [gap(tails[i][:, 0], tails[p][:, 1]) for i, p in enumerate(perm)]
        null.append(float(np.mean(gaps)))
        null_within.append(within(gaps))
    null = np.array(null)
    summary = {"n_games": len(games), "real_mean_gap": real,
               "placebo_mean_gap": float(null.mean()), "placebo_p05_gap": float(np.quantile(null, 0.05)),
               "p_value": float((1 + (null <= real + 1e-12).sum()) / (1 + B)),
               "real_within_1c": within(per_game.mean_abs_gap_last50),
               "real_final_within_1c": within(per_game.final_abs_gap),
               "placebo_mean_within_1c": float(np.mean(null_within)), "B": B}
    return summary, per_game


def run_gap() -> None:
    import pandas as pd
    from pairs import load_games
    base, instr, _, _ = load_all()
    strat = load_games(RUNS, "strategy_instructed")
    rows, per_game = [], []
    for cond, games in (("baseline", base), ("instructed", instr), ("strategy_instructed", strat)):
        s, pg = gap_test(games)
        rows.append({"condition": cond, **s})
        pg.insert(0, "condition", cond)
        per_game.append(pg)
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "gap_test.csv", index=False)
    pd.concat(per_game).to_csv(OUT / "gap_test_per_game.csv", index=False)
    print(out.round(4).to_string(index=False))


def run_diagnostic() -> None:
    import pandas as pd
    base, instr, nash, mono = load_all()
    OUT.mkdir(parents=True, exist_ok=True)
    d = diagnostics.summarize(base)
    early = diagnostics.summarize(base, window=(1, 100))
    both = pd.concat([early["correlations"], d["correlations"]])
    both.to_csv(OUT / "diagnostic_correlations_both_windows.csv", index=False)
    early["cross"].to_csv(OUT / "diagnostic_cross_pairs_1_100.csv", index=False)
    levels = price_levels(base + instr, nash, mono)
    levels.to_csv(OUT / "price_levels_per_game.csv", index=False)
    print(both.round(3).to_string(index=False))
    print(levels.round(3).to_string(index=False))
    d["correlations"].to_csv(OUT / "diagnostic_correlations.csv", index=False)
    d["cross"].to_csv(OUT / "diagnostic_cross_pairs.csv", index=False)
    d["within"].to_csv(OUT / "diagnostic_within.csv", index=False)
    changes = diagnostics.change_counts(base + instr)
    changes.to_csv(OUT / "price_changes.csv", index=False)
    summary = {k: d[k] for k in ("independence_band", "share_firms_moving", "share_games_both_moving",
                                 "median_share_periods_changed")}
    summary["instructed"] = {
        "share_firms_moving": float(changes[changes.condition == "instructed"].moving.mean()),
        "share_games_both_moving": float(changes[changes.condition == "instructed"].groupby("run_id").moving.all().mean()),
    }
    (OUT / "diagnostic_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    figures.cross_game(d, OUT / "fig4_cross_game.png")
    print(d["correlations"].round(3).to_string(index=False))
    print(json.dumps(summary, indent=2))
    print(changes.groupby(["condition", "firm"]).n_changes.describe().round(1).to_string())


def run_tests(B: int, B_boot: int) -> None:
    base, instr, nash, mono = load_all()
    OUT.mkdir(parents=True, exist_ok=True)
    res = evaluate(base, instr, nash, mono, B=B, B_boot=B_boot, seed=20261023)
    res["summary"].to_csv(OUT / "tests_summary.csv", index=False)
    res["pairs"].to_csv(OUT / "tests_pairs.csv", index=False)
    res["null"].to_csv(OUT / "tests_null.csv", index=False)
    # Table 1 replication on real baseline and instructed pairs.
    rows = []
    for cond, games in (("baseline", base), ("instructed", instr)):
        for spec, fn in (("fish", fish_regression), ("naive", naive_regression)):
            r = fn(real_markets(games))
            rows.append({"condition": cond, "spec": spec, **r.__dict__})
    import pandas as pd
    pd.DataFrame(rows).to_csv(OUT / "table1_replication.csv", index=False)
    figures.all_figures(res, base, diagnostics.summarize(base), nash, mono, OUT)
    print(res["summary"].round(3).to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["diagnostic", "tests", "gap"])
    ap.add_argument("--B", type=int, default=1000)
    ap.add_argument("--B-boot", type=int, default=1000)
    args = ap.parse_args()
    if args.cmd == "diagnostic":
        run_diagnostic()
    elif args.cmd == "tests":
        run_tests(args.B, args.B_boot)
    else:
        run_gap()


if __name__ == "__main__":
    main()
