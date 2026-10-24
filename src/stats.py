"""Placebo-null statistics for every detector: re-pairing permutation null, AUROC, calibrated threshold, power.

Two levels (CLAUDE.md, Statistics):
- Pooled (main result): the statistic on all N real baseline markets, compared against the same statistic
  on N placebo markets from a random derangement, repeated B times. Placebo markets reuse each run, so the
  null is built from whole re-pairings rather than from treating the N(N-1) placebo pairs as independent.
- Per pair: distributions of per-market scores, AUROC (real vs placebo, instructed vs placebo), the 95th
  percentile of placebo scores as the calibrated threshold, and power on instructed pairs at that threshold.
  AUROC confidence intervals come from a bootstrap that resamples runs (clustering by run).

Unidentified per-market scores (NaN: no price variation, e.g. a frozen seller) are scored 0, i.e. "no
evidence", and counted. Higher scores always mean "more collusive-looking"; p-values are one-sided.

Frozen-game rule: every statistic is computed on all markets ("all") and again on moving markets only
("moving": both sellers change price >= 10 times in periods 101-300), using the same rule for real,
placebo and instructed markets.
"""

import math

import numpy as np
import pandas as pd

from detectors import is_moving, per_market_scorers, pooled_scorers
from pairs import Game, deranged_markets, derangement, placebo_markets, real_markets

TESTS = ["collusion_index", "corr_levels", "corr_diffs", "fish_delta", "naive_delta"]
VERSIONS = ["all", "moving"]


def auroc(pos: np.ndarray, neg: np.ndarray) -> float:
    """P(score of a random positive > score of a random negative), ties count half."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return math.nan
    gt = (pos[:, None] > neg[None, :]).sum()
    eq = (pos[:, None] == neg[None, :]).sum()
    return float((gt + 0.5 * eq) / (len(pos) * len(neg)))


def nan0(x) -> np.ndarray:
    x = np.asarray(x, float)
    return np.where(np.isnan(x), 0.0, x)


def p_value_upper(real: float, null: np.ndarray) -> float:
    """One-sided permutation p-value, counting the observed re-pairing as one draw."""
    null = null[~np.isnan(null)]
    if math.isnan(real) or len(null) == 0:
        return math.nan
    return float((1 + (null >= real).sum()) / (1 + len(null)))


def keep(markets, version):
    return markets if version == "all" else [m for m in markets if is_moving(m)]


def per_pair_scores(games: list[Game], instructed: list[Game], nash: float, monopoly: float) -> pd.DataFrame:
    """One row per market (real, placebo, instructed) with every detector's raw score."""
    scorers = per_market_scorers(nash, monopoly)
    markets = real_markets(games) + placebo_markets(games) + real_markets(instructed, kind="instructed")
    rows = []
    for m in markets:
        row = {"kind": m.kind, "run_a": m.run_a, "run_b": m.run_b, "moving": is_moving(m)}
        row.update({name: f(m) for name, f in scorers.items()})
        rows.append(row)
    return pd.DataFrame(rows)


def pooled_null(games: list[Game], nash: float, monopoly: float, B: int, rng: np.random.Generator) -> pd.DataFrame:
    """Pooled statistics on B random derangements, for every test and version."""
    pooled = pooled_scorers(nash, monopoly)
    rows = []
    for b in range(B):
        ms = deranged_markets(games, derangement(len(games), rng))
        for version in VERSIONS:
            sub = keep(ms, version)
            row = {"draw": b, "version": version, "n_markets": len(sub)}
            row.update({name: pooled[name](sub) if sub else math.nan for name in TESTS})
            rows.append(row)
    return pd.DataFrame(rows)


def bootstrap_auroc(scores: pd.DataFrame, test: str, positive_kind: str, B: int, rng) -> tuple[float, float]:
    """95% CI for AUROC(positive kind vs placebo), resampling baseline runs (and instructed runs) with replacement."""
    real_runs = sorted(scores.loc[scores.kind == "real", "run_a"])
    inst_runs = sorted(scores.loc[scores.kind == "instructed", "run_a"])
    plc = scores[scores.kind == "placebo"]
    by_pair = {(a, b): v for a, b, v in zip(plc.run_a, plc.run_b, nan0(plc[test]))}
    pos_src = scores[scores.kind == positive_kind].set_index("run_a")[test]
    out = []
    for _ in range(B):
        draw = rng.choice(real_runs, size=len(real_runs), replace=True)
        # Pairs missing from by_pair were filtered out (the "moving" version); skip them.
        neg = [by_pair[(a, b)] for a in draw for b in draw if a != b and (a, b) in by_pair]
        pos_runs = draw if positive_kind == "real" else rng.choice(inst_runs, size=len(inst_runs), replace=True)
        pos = nan0(pos_src.loc[list(pos_runs)].values)
        out.append(auroc(pos, np.array(neg)))
    out = np.array(out)
    out = out[~np.isnan(out)]
    return (float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))) if len(out) else (math.nan, math.nan)


def evaluate(games: list[Game], instructed: list[Game], nash: float, monopoly: float,
             B: int = 1000, B_boot: int = 500, seed: int = 0) -> dict:
    """Full placebo evaluation. Returns {"summary": DataFrame, "pairs": DataFrame, "null": DataFrame}."""
    rng = np.random.default_rng(seed)
    pooled = pooled_scorers(nash, monopoly)
    scores = per_pair_scores(games, instructed, nash, monopoly)
    null = pooled_null(games, nash, monopoly, B, rng)
    real_ms, inst_ms = real_markets(games), real_markets(instructed, kind="instructed")

    rows = []
    for version in VERSIONS:
        sc = scores if version == "all" else scores[scores.moving]
        nl = null[null.version == version]
        r_ms, i_ms = keep(real_ms, version), keep(inst_ms, version)
        for test in TESTS:
            real_val = pooled[test](r_ms) if r_ms else math.nan
            inst_val = pooled[test](i_ms) if i_ms else math.nan
            null_vals = nl[test].to_numpy(float)
            plc = sc.loc[sc.kind == "placebo", test].to_numpy(float)
            rl = sc.loc[sc.kind == "real", test].to_numpy(float)
            ins = sc.loc[sc.kind == "instructed", test].to_numpy(float)
            thr = float(np.quantile(nan0(plc), 0.95)) if len(plc) else math.nan
            ci_real = bootstrap_auroc(sc, test, "real", B_boot, rng) if len(rl) >= 2 and len(plc) else (math.nan, math.nan)
            ci_inst = bootstrap_auroc(sc, test, "instructed", B_boot, rng) if len(ins) >= 1 and len(rl) >= 2 and len(plc) else (math.nan, math.nan)
            valid_null = null_vals[~np.isnan(null_vals)]
            rows.append({
                "test": test, "version": version,
                "real_pooled": real_val,
                "placebo_null_mean": float(valid_null.mean()) if len(valid_null) else math.nan,
                "placebo_null_p95": float(np.quantile(valid_null, 0.95)) if len(valid_null) else math.nan,
                "p_value_real": p_value_upper(real_val, null_vals),
                "instructed_pooled": inst_val,
                "p_value_instructed": p_value_upper(inst_val, null_vals),
                "auroc_real_vs_placebo": auroc(nan0(rl), nan0(plc)),
                "auroc_real_ci_low": ci_real[0], "auroc_real_ci_high": ci_real[1],
                "auroc_instructed_vs_placebo": auroc(nan0(ins), nan0(plc)),
                "auroc_instructed_ci_low": ci_inst[0], "auroc_instructed_ci_high": ci_inst[1],
                "threshold_placebo_p95": thr,
                "power_instructed": float((nan0(ins) > thr).mean()) if len(ins) else math.nan,
                "n_real": len(rl), "n_placebo": len(plc), "n_instructed": len(ins),
                "n_unidentified_real": int(np.isnan(rl).sum()),
                "n_unidentified_placebo": int(np.isnan(plc).sum()),
                "n_unidentified_instructed": int(np.isnan(ins).sum()),
                "null_draws_valid": int(len(valid_null)),
            })
    return {"summary": pd.DataFrame(rows), "pairs": scores, "null": null}
