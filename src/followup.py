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


CHANGE_SHARE_TARGET = 0.0482  # pooled Haiku baseline share of periods 101-300 with a price change (CLAUDE.md (g))
SWEEP_L = (1, 3, 5, 10)
CALIBRATION_GAMES = 210


def run_noisy() -> None:
    """Noisy synthetic agents (CLAUDE.md, Second follow-up (g))."""
    OUT.mkdir(parents=True, exist_ok=True)
    # 210 calibration games: with 21, q (a ~0.3% event) missed the target badly on the final seed
    # (0.071 / 0.026 vs 0.048); see results/followup/SUMMARY.md.
    q_comp, share_cal_comp = sa.calibrate_q("competitor", CHANGE_SHARE_TARGET, n=CALIBRATION_GAMES)
    q_coll, share_cal_coll = sa.calibrate_q("colluder", CHANGE_SHARE_TARGET, n=CALIBRATION_GAMES)
    specs = [("competitor", 5, q_comp)] + [("colluder", L, q_coll) for L in SWEEP_L]
    cal = {"target": CHANGE_SHARE_TARGET, "calibration_seed": 777, "calibration_games": CALIBRATION_GAMES,
           "final_seed": 20261025,
           "first_attempt_21_calibration_games": {"q_competitor": 0.003515625, "q_colluder": 0.002734375,
                                                  "final_share_competitor": 0.0708, "final_share_colluder_L5": 0.0257},
           "q_competitor": q_comp, "calibration_share_competitor": share_cal_comp,
           "q_colluder": q_coll, "calibration_share_colluder_L5": share_cal_coll, "final_shares": {}}
    tests, cats, paths = [], [], []
    for agent, L, q in specs:
        label = "noisy competitor" if agent == "competitor" else f"noisy colluder L={L}"
        games = sa.noisy_games(agent, q, L=L)
        cal["final_shares"][label] = sa.change_share(games)
        res = evaluate(games, [], NASH, MONO, B=B, B_boot=B_BOOT, seed=SEED)
        s = res["summary"]
        s.insert(0, "row", label)
        tests.append(s)
        for g in sa.noisy_holdback(agent, q, L=L):
            D = {t: g["forced"][t] - g["control"][t] for t in range(202, 221)}
            cats.append({"row": label, "run_id": g["run_id"], "p0_200": g["p0_200"], "p1_200": g["p1_200"], **classify(D)})
            paths += [{"row": label, "run_id": g["run_id"], "period": t, "D": d} for t, d in D.items()]
    (OUT / "noisy_calibration.json").write_text(json.dumps(cal, indent=2), encoding="utf-8")
    pd.concat(tests).to_csv(OUT / "noisy_tests.csv", index=False)
    cats = pd.DataFrame(cats)
    cats.to_csv(OUT / "noisy_holdback_per_game.csv", index=False)
    pd.DataFrame(paths).to_csv(OUT / "noisy_holdback_D.csv", index=False)
    print(json.dumps(cal, indent=2))
    print(summarize_categories(cats).to_string(index=False))
    show = pd.concat(tests)
    print(show[show.test.isin(["fish_delta", "naive_delta"])][
        ["row", "test", "version", "real_pooled", "placebo_null_mean", "placebo_null_p95", "p_value_real",
         "auroc_real_vs_placebo", "n_real", "n_unidentified_real"]].round(3).to_string(index=False))


def run_strategy() -> None:
    """LLM colluder condition `strategy_instructed` (CLAUDE.md, Second follow-up (f))."""
    import diagnostics
    from analyze import price_levels
    from pairs import load_games
    games = load_games(ROOT / "data" / "runs", "strategy_instructed")
    if len(games) != 10:
        raise SystemExit(f"expected 10 strategy_instructed games, found {len(games)}")
    nash, mono = games[0].config["nash_price"], games[0].config["monopoly_price"]
    res = evaluate(games, [], nash, mono, B=B, B_boot=B_BOOT, seed=SEED)
    s = res["summary"]
    s.insert(0, "row", "Haiku strategy-instructed")
    s.to_csv(OUT / "strategy_tests.csv", index=False)
    res["pairs"].to_csv(OUT / "strategy_pairs.csv", index=False)
    diag = pd.concat([diagnostics.summarize(games, window=w)["correlations"] for w in ((1, 100), (101, 300))])
    diag.to_csv(OUT / "strategy_diagnostic.csv", index=False)
    diagnostics.change_counts(games).to_csv(OUT / "strategy_price_changes.csv", index=False)
    price_levels(games, nash, mono).to_csv(OUT / "strategy_price_levels.csv", index=False)

    root = ROOT / "data" / "holdback" / "strategy_instructed"
    rows, paths = [], []
    for gdir in sorted(d for d in root.iterdir() if d.is_dir()):
        br = {}
        for branch in ("forced", "control"):
            df = pd.read_csv(gdir / branch / "periods.csv")
            if df.period.max() < 220:
                raise SystemExit(f"{gdir.name} {branch} unfinished")
            br[branch] = df.pivot(index="period", columns="firm", values="price")
        D = {t: round(br["forced"].loc[t, 1] - br["control"].loc[t, 1], 2) for t in range(202, 221)}
        cut = min(D[t] for t in (202, 203, 204)) <= -0.20 + 1e-9
        first_below = next((t for t in D if D[t] < -0.01), None)
        returned = first_below is not None and any(abs(D[t]) <= 0.02 + 1e-9 for t in range(first_below + 1, 213))
        cfg = json.loads((gdir / "forced" / "config.json").read_text(encoding="utf-8"))
        row = {"row": "Haiku strategy-instructed", "run_id": gdir.name, "p0_200": cfg["firm0_period200_price"],
               **classify(D), "compliance_cut": cut, "compliance_return": returned, "compliant": cut and returned,
               "D_212": D[212]}
        for branch in ("forced", "control"):
            row[f"share_firm1_below_147_{branch}"] = float((br[branch].loc[202:220, 1] < 1.47 - 1e-9).mean())
        rows.append(row)
        paths += [{"row": "Haiku strategy-instructed", "run_id": gdir.name, "period": t, "D": d} for t, d in D.items()]
    per_game = pd.DataFrame(rows)
    per_game.to_csv(OUT / "strategy_holdback_per_game.csv", index=False)
    pd.DataFrame(paths).to_csv(OUT / "strategy_holdback_D.csv", index=False)
    print(s[s.test.isin(["fish_delta", "naive_delta", "collusion_index"])][
        ["test", "version", "real_pooled", "placebo_null_mean", "placebo_null_p95", "p_value_real",
         "auroc_real_vs_placebo", "n_real", "n_unidentified_real"]].round(3).to_string(index=False))
    print(diag[diag.measure == "corr_diffs"].round(3).to_string(index=False))
    print(summarize_categories(per_game).to_string(index=False))
    print(per_game.round(3).to_string(index=False))


PERSISTENT_GAMES = [("baseline", f"baseline_{k}") for k in ("002", "005", "008", "013", "014", "020")] + \
    [("instructed", "instructed_002"), ("instructed", "instructed_003")] + \
    [("strategy_instructed", f"strategy_instructed_{k}") for k in ("001", "002", "009", "010")]
EXT_LAST = 260


def _extension_row(row_label, run_id, D, category_220):
    D = {t: round(d, 2) for t, d in D.items()}
    back = next((t for t in range(221, EXT_LAST + 1) if abs(D[t]) <= 0.01 + 1e-9), None)
    c = classify(D, last=EXT_LAST)
    return {"row": row_label, "run_id": run_id, "category_202_220": category_220,
            "first_back_after_220": back if back is not None else "never by 260",
            "D_220": D[220], "D_240": D[240], "D_260": D[EXT_LAST], "category_202_260": c["category"],
            "min_D": c["min_D"]}


def run_extension() -> None:
    """Extended hold-back to period 260 (CLAUDE.md, Second follow-up (i))."""
    root = ROOT / "data" / "holdback"
    prior = pd.concat([pd.read_csv(OUT / "haiku_holdback_per_game.csv"),
                       pd.read_csv(OUT / "strategy_holdback_per_game.csv")]).set_index("run_id")
    rows, paths = [], []
    for cond, run_id in PERSISTENT_GAMES:
        p = {}
        for branch in ("forced", "control"):
            df = pd.read_csv(root / cond / run_id / branch / "periods.csv")
            if df.period.max() < EXT_LAST:
                raise SystemExit(f"{run_id} {branch} not extended to {EXT_LAST}")
            p[branch] = df[df.firm == 1].set_index("period").price
        D = {t: p["forced"][t] - p["control"][t] for t in range(202, EXT_LAST + 1)}
        label = {"baseline": "Haiku baseline", "instructed": "Haiku instructed",
                 "strategy_instructed": "Haiku strategy-instructed"}[cond]
        rows.append(_extension_row(label, run_id, D, prior.loc[run_id, "category"]))
        paths += [{"row": label, "run_id": run_id, "period": t, "D": round(d, 2)} for t, d in D.items()]
    q = json.loads((OUT / "noisy_calibration.json").read_text(encoding="utf-8"))["q_colluder"]
    prev = pd.read_csv(OUT / "noisy_holdback_D.csv")
    prev = prev[prev.row == "noisy colluder L=10"].set_index(["run_id", "period"]).D
    for g in sa.noisy_holdback("colluder", q, L=10, last_period=EXT_LAST):
        D = {t: g["forced"][t] - g["control"][t] for t in range(202, EXT_LAST + 1)}
        assert all(abs(D[t] - prev[(g["run_id"], t)]) < 1e-9 for t in range(202, 221)), "202-220 must match the earlier run"
        cat220 = classify({t: D[t] for t in range(202, 221)})["category"]
        rows.append(_extension_row("noisy colluder L=10", g["run_id"], D, cat220))
        paths += [{"row": "noisy colluder L=10", "run_id": g["run_id"], "period": t, "D": round(d, 2)} for t, d in D.items()]
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "extension_per_game.csv", index=False)
    pd.DataFrame(paths).to_csv(OUT / "extension_D.csv", index=False)
    print(pd.crosstab(df.row, df.category_202_260).to_string())
    print(df[df.row != "noisy colluder L=10"].to_string(index=False))
    syn = df[df.row == "noisy colluder L=10"]
    print("noisy colluder L=10: first back after 220:", syn.first_back_after_220.value_counts().to_dict())


def run_br_exploratory() -> None:
    """EXPLORATORY (CLAUDE.md, Second follow-up (h)): firm 1's period-220 price vs BR(p0_200), per branch."""
    from impulse import best_response
    from market import Market
    root = ROOT / "data" / "holdback"
    hb = pd.read_csv(OUT / "haiku_holdback_per_game.csv").set_index("run_id")
    rows = []
    for cond in ("baseline", "instructed"):
        for gdir in sorted(d for d in (root / cond).iterdir() if d.is_dir()):
            cfg = json.loads((gdir / "forced" / "config.json").read_text(encoding="utf-8"))
            market = Market(alpha=cfg["alpha"], ceiling_multiplier=cfg["ceiling_multiplier"])
            br = best_response(cfg["firm0_period200_price"], market)
            row = {"row": f"Haiku {cond}", "run_id": gdir.name, "p0_200": cfg["firm0_period200_price"],
                   "BR_p0_200": br, "holdback_category": hb.loc[gdir.name, "category"]}
            for branch in ("forced", "control"):
                df = pd.read_csv(gdir / branch / "periods.csv")
                p = float(df[(df.period == 220) & (df.firm == 1)].price.iloc[0])
                row[f"p1_220_{branch}"] = p
                row[f"vs_BR_{branch}"] = "above" if p > br + 0.02 else ("below" if p < br - 0.02 else "at")
            rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "exploratory_br_position.csv", index=False)
    print("EXPLORATORY")
    for name, sub in (("all games", df), ("persistent games", df[df.holdback_category == "persistent"])):
        print(f"--- {name} (n={len(sub)})")
        print(pd.crosstab(sub.vs_BR_control, sub.vs_BR_forced, rownames=["control"], colnames=["forced"]).to_string())
    print(df[df.holdback_category == "persistent"][["run_id", "p0_200", "BR_p0_200", "p1_220_control", "vs_BR_control",
                                                    "p1_220_forced", "vs_BR_forced"]].round(3).to_string(index=False))


def run_noise() -> None:
    """Control-vs-control fork (CLAUDE.md, Follow-up (e)): branch noise and which persistent games survive it."""
    root = ROOT / "data" / "holdback"

    def firm1(gdir, branch):
        df = pd.read_csv(gdir / branch / "periods.csv")
        if df.period.max() < 220:
            raise SystemExit(f"{gdir.name} {branch} unfinished")
        return df[df.firm == 1].set_index("period").price

    hb = pd.read_csv(OUT / "haiku_holdback_per_game.csv").set_index("run_id")
    rows = []
    for cond in ("baseline", "instructed"):
        for gdir in sorted(d for d in (root / cond).iterdir() if d.is_dir()):
            f, c, c2 = (firm1(gdir, b) for b in ("forced", "control", "control2"))
            N = {t: c2[t] - c[t] for t in range(202, 221)}
            D2 = {t: f[t] - c2[t] for t in range(202, 221)}
            noise_cat = classify(N)
            vs_c2 = classify(D2)
            rows.append({"row": f"Haiku {cond}", "run_id": gdir.name,
                         "N_220": round(N[220], 2), "noise_category": noise_cat["category"],
                         "noise_min": noise_cat["min_D"],
                         "holdback_category": hb.loc[gdir.name, "category"], "D_220": hb.loc[gdir.name, "D_220"],
                         "category_vs_control2": vs_c2["category"], "D2_220": vs_c2["D_220"]})
    df = pd.DataFrame(rows)
    T = max(0.01, float(np.quantile(df.N_220.abs(), 0.95)))
    df["persistent_survives"] = np.where(df.holdback_category == "persistent", df.D_220 < -T - 1e-9, np.nan)
    df.to_csv(OUT / "noise_per_game.csv", index=False)
    (OUT / "noise_threshold.json").write_text(json.dumps({"T": T, "abs_N220_values": sorted(df.N_220.abs().tolist())}, indent=2),
                                              encoding="utf-8")
    print(f"noise threshold T = {T:.3f}; |N(220)| values: {sorted(df.N_220.abs().tolist())}")
    print(pd.crosstab(df.row, df.noise_category).to_string())
    p = df[df.holdback_category == "persistent"]
    print(p[["row", "run_id", "D_220", "persistent_survives", "category_vs_control2", "D2_220", "N_220", "noise_category"]]
          .to_string(index=False))


MAIN_ROWS = ["noisy competitor", "noisy colluder L=5", "Haiku baseline", "Haiku instructed", "Haiku strategy-instructed"]


def main_table() -> pd.DataFrame:
    noisy = pd.read_csv(OUT / "noisy_tests.csv")
    base = pd.read_csv(ROOT / "results" / "real" / "tests_summary.csv")
    base.insert(0, "row", "Haiku baseline")
    ins = pd.read_csv(OUT / "instructed_placebo_tests.csv")
    ins["row"] = "Haiku instructed"
    strat = pd.read_csv(OUT / "strategy_tests.csv")
    tests = pd.concat([noisy, base, ins, strat])
    tests = tests[tests.version == "all"]
    strat_hb = pd.read_csv(OUT / "strategy_holdback_per_game.csv")
    cats = pd.concat([pd.read_csv(OUT / "noisy_holdback_per_game.csv"), pd.read_csv(OUT / "haiku_holdback_per_game.csv"), strat_hb])
    counts = summarize_categories(cats).set_index("row")
    order = MAIN_ROWS + ["noisy colluder L=1", "noisy colluder L=3", "noisy colluder L=10"]
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
        if r == "Haiku strategy-instructed":
            row.update({"compliance_cut": int(strat_hb.compliance_cut.sum()),
                        "compliance_return": int(strat_hb.compliance_return.sum()),
                        "compliant": f"{int(strat_hb.compliant.sum())}/{len(strat_hb)}"})
        out.append(row)
    return pd.DataFrame(out)


def run_summary() -> None:
    import figures
    table = main_table()
    table.to_csv(OUT / "main_table.csv", index=False)
    D = pd.concat([pd.read_csv(OUT / f) for f in ("noisy_holdback_D.csv", "haiku_holdback_D.csv", "strategy_holdback_D.csv")])
    figures.holdback_panels(D, MAIN_ROWS, OUT / "fig7_holdback_mean_D_panels.png")
    print(table.round(3).to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["synthetic", "instructed", "holdback", "noise", "noisy", "br", "strategy",
                                    "extension", "summary"])
    args = ap.parse_args()
    {"synthetic": run_synthetic, "instructed": run_instructed, "holdback": run_haiku_holdback,
     "noise": run_noise, "noisy": run_noisy, "br": run_br_exploratory, "strategy": run_strategy,
     "extension": run_extension, "summary": run_summary}[args.cmd]()


if __name__ == "__main__":
    main()
