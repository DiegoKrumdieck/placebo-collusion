"""Cross-game diagnostic (CLAUDE.md, Analysis): are games independent enough for the placebo to be informative?

For every pair of different games, correlate the same role (firm 0 with firm 0, and separately firm 1
with firm 1) over periods 101-300, in levels and in first differences. Sellers in different games never
interacted, so a high cross-game correlation of first differences means games are near-copies in their
moves. Also reports how often each firm's price changes at all (the frozen-game rule's distribution).
"""

import math
from itertools import combinations

import numpy as np
import pandas as pd

from detectors import FISH_WINDOW, MOVING_MIN_CHANGES, correlation, n_changes
from pairs import Game, Market


def change_counts(games: list[Game], window=FISH_WINDOW) -> pd.DataFrame:
    s, e = window
    n_periods = e - s + 1
    rows = []
    for g in games:
        for firm in (0, 1):
            n = n_changes(g.prices[:, firm], window)
            rows.append({"run_id": g.run_id, "condition": g.condition, "firm": firm, "n_changes": n,
                         "share_periods_changed": n / n_periods, "moving": n >= MOVING_MIN_CHANGES})
    return pd.DataFrame(rows)


def cross_game_correlations(games: list[Game], window=FISH_WINDOW) -> pd.DataFrame:
    """One row per unordered pair of different games and role."""
    rows = []
    for gi, gj in combinations(games, 2):
        for firm in (0, 1):
            m = Market(gi.prices[:, firm], gj.prices[:, firm], "cross", gi.run_id, gj.run_id)
            rows.append({"run_i": gi.run_id, "run_j": gj.run_id, "firm": firm,
                         "corr_levels": correlation(m, diff=False, window=window),
                         "corr_diffs": correlation(m, diff=True, window=window)})
    return pd.DataFrame(rows)


def within_game_correlations(games: list[Game], window=FISH_WINDOW) -> pd.DataFrame:
    """Reference: firm 0 vs firm 1 of the same game (sellers who did interact)."""
    rows = []
    for g in games:
        m = Market(g.prices[:, 0], g.prices[:, 1], "real", g.run_id, g.run_id)
        rows.append({"run_id": g.run_id, "corr_levels": correlation(m, diff=False, window=window),
                     "corr_diffs": correlation(m, diff=True, window=window)})
    return pd.DataFrame(rows)


def _describe(x: pd.Series, band: float) -> dict:
    v = x.dropna().to_numpy()
    return {"n_defined": len(v), "n_undefined": int(x.isna().sum()),
            "mean": float(v.mean()) if len(v) else math.nan,
            "median": float(np.median(v)) if len(v) else math.nan,
            "p05": float(np.quantile(v, 0.05)) if len(v) else math.nan,
            "p95": float(np.quantile(v, 0.95)) if len(v) else math.nan,
            "share_abs_gt_band": float((np.abs(v) > band).mean()) if len(v) else math.nan}


def _band(window_len: int) -> float:
    """Approximate 95% band for a correlation between two independent white-noise series of this length."""
    return 1.96 / math.sqrt(window_len - 1)


def summarize(games: list[Game], window=FISH_WINDOW) -> dict:
    cross = cross_game_correlations(games, window)
    within = within_game_correlations(games, window)
    changes = change_counts(games, window)
    s, e = window
    band = _band(e - s + 1)
    rows = []
    for firm in (0, 1):
        for col in ("corr_levels", "corr_diffs"):
            rows.append({"window": f"{s}-{e}", "what": f"cross-game firm {firm}", "measure": col,
                         **_describe(cross.loc[cross.firm == firm, col], band)})
    for col in ("corr_levels", "corr_diffs"):
        rows.append({"window": f"{s}-{e}", "what": "within-game (reference)", "measure": col, **_describe(within[col], band)})
    return {
        "correlations": pd.DataFrame(rows),
        "cross": cross,
        "within": within,
        "changes": changes,
        "independence_band": _band(e - s + 1),
        "share_firms_moving": float(changes.moving.mean()),
        "share_games_both_moving": float(changes.groupby("run_id").moving.all().mean()),
        "median_share_periods_changed": float(changes.share_periods_changed.median()),
    }
