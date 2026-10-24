"""Collusion detectors, each scoring one market or a pooled set of markets.

(Named detectors.py rather than tests.py, as in CLAUDE.md's layout, so it can't be confused with
the pytest tests/ directory.)

Periods are 1-indexed: path[t - 1] is the price in period t.
"""

import math
from dataclasses import dataclass

import numpy as np

from pairs import Market

FISH_WINDOW = (101, 300)  # Fish et al.: periods 101-300
NAIVE_WINDOW = (1, 300)  # naive spec: all periods
MOVING_MIN_CHANGES = 10  # frozen-game rule: "moving" = at least 10 price changes in 101-300
CHANGE_TOL = 1e-9


# ---------- price movement (frozen-game rule) ----------

def n_changes(path: np.ndarray, window: tuple[int, int] = FISH_WINDOW) -> int:
    """Periods t in the window whose price differs from period t-1."""
    s, e = window
    seg = path[max(s - 2, 0) : e]  # periods s-1 .. e (from period 1 when the window starts there)
    return int((np.abs(np.diff(seg)) > CHANGE_TOL).sum())


def is_moving(m: Market, min_changes: int = MOVING_MIN_CHANGES) -> bool:
    """Both sellers change price at least min_changes times in periods 101-300.

    Applied per market, so the same rule covers real, placebo and instructed pairs.
    """
    return n_changes(m.a) >= min_changes and n_changes(m.b) >= min_changes


# ---------- simple per-market scores ----------

def collusion_index(m: Market, nash: float, monopoly: float, last: int = 50) -> float:
    """Delta = (mean price of both firms over the last 50 periods - Nash) / (monopoly - Nash)."""
    pbar = (m.a[-last:].mean() + m.b[-last:].mean()) / 2
    return float((pbar - nash) / (monopoly - nash))


def correlation(m: Market, diff: bool = False, window: tuple[int, int] = FISH_WINDOW) -> float:
    """Correlation of the two price paths over the window, in levels or first differences.

    NaN when either series has no variation (a frozen seller).
    """
    s, e = window
    a, b = m.a[s - 1 : e], m.b[s - 1 : e]
    if diff:
        lo = max(s - 2, 0)  # include the change into period s, when there is a period s-1
        a, b = np.diff(m.a[lo:e]), np.diff(m.b[lo:e])
    if a.std() < CHANGE_TOL or b.std() < CHANGE_TOL:
        return math.nan
    return float(np.corrcoef(a, b)[0, 1])


# ---------- Fish et al. regression ----------

def fish_design(markets: list[Market], window: tuple[int, int]):
    """Rows of Eq. 1 built Fish et al.'s way.

    Disjoint pairs of consecutive periods (s, s+1), (s+2, s+3), ... within the window; in pair k the
    dependent firm is firm k % 2. One row per pair: y = p_i[t], own = p_i[t-1], comp = p_-i[t-1],
    with t the second period of the pair. Returns y, own, comp, group (market-firm id), cluster (market id).
    """
    s, e = window
    y, own, comp, group, cluster = [], [], [], [], []
    for mi, m in enumerate(markets):
        paths = (m.a, m.b)
        for k, t_prev in enumerate(range(s, e, 2)):
            t = t_prev + 1
            if t > e:
                break
            i = k % 2
            y.append(paths[i][t - 1])
            own.append(paths[i][t_prev - 1])
            comp.append(paths[1 - i][t_prev - 1])
            group.append(2 * mi + i)
            cluster.append(mi)
    return (np.array(y), np.array(own), np.array(comp), np.array(group), np.array(cluster))


@dataclass
class RegResult:
    gamma: float
    delta: float
    se_gamma_hc1: float
    se_delta_hc1: float
    se_delta_cluster: float
    r2_within: float
    n: int
    n_groups: int


NAN_RESULT = RegResult(*([math.nan] * 6), 0, 0)


def _demean(v: np.ndarray, group: np.ndarray) -> np.ndarray:
    sums = np.bincount(group, weights=v)
    counts = np.bincount(group)
    return v - (sums / np.maximum(counts, 1))[group]


def ols_fe(y, own, comp, group, cluster, fixed_effects: bool = True) -> RegResult:
    """OLS of y on (own, comp) with group fixed effects (or an intercept), HC1 and cluster-robust SEs.

    Returns NaN coefficients when the regressors have no (within-group) variation, e.g. frozen markets.
    """
    n = len(y)
    if n == 0:
        return NAN_RESULT
    if fixed_effects:
        _, group = np.unique(group, return_inverse=True)
        G = group.max() + 1
        yd, X = _demean(y, group), np.column_stack([_demean(own, group), _demean(comp, group)])
        k_absorbed = G
    else:
        G = 1
        yd, X = y - y.mean(), np.column_stack([own - own.mean(), comp - comp.mean()])
        k_absorbed = 1
    k = X.shape[1]
    XtX = X.T @ X
    if n - k - k_absorbed <= 0 or np.linalg.matrix_rank(XtX, tol=1e-10 * max(1.0, np.abs(XtX).max())) < k:
        return RegResult(math.nan, math.nan, math.nan, math.nan, math.nan, math.nan, n, G)
    XtX_inv = np.linalg.inv(XtX)
    beta = XtX_inv @ X.T @ yd
    resid = yd - X @ beta
    dof = n - k - k_absorbed
    # HC1: White's sandwich with an n / (n - k) small-sample factor (Stata's ", robust").
    meat = (X * resid[:, None] ** 2).T @ X
    V_hc1 = XtX_inv @ meat @ XtX_inv * n / dof
    # CR1 clustered by market (= run for real pairs).
    _, cl = np.unique(cluster, return_inverse=True)
    C = cl.max() + 1
    scores = np.zeros((C, k))
    np.add.at(scores, cl, X * resid[:, None])
    V_cl = XtX_inv @ (scores.T @ scores) @ XtX_inv
    if C > 1:
        V_cl *= (C / (C - 1)) * ((n - 1) / dof)
    tss = float(yd @ yd)
    r2 = 1 - float(resid @ resid) / tss if tss > 0 else math.nan
    return RegResult(
        gamma=float(beta[0]), delta=float(beta[1]),
        se_gamma_hc1=float(math.sqrt(V_hc1[0, 0])), se_delta_hc1=float(math.sqrt(V_hc1[1, 1])),
        se_delta_cluster=float(math.sqrt(V_cl[1, 1])) if C > 1 else math.nan,
        r2_within=r2, n=n, n_groups=G,
    )


def fish_regression(markets: list[Market]) -> RegResult:
    """Fish et al.'s exact specification: periods 101-300, disjoint alternating pairs, firm-run FE."""
    return ols_fe(*fish_design(markets, FISH_WINDOW), fixed_effects=True)


def naive_regression(markets: list[Market]) -> RegResult:
    """Naive specification: all periods, same disjoint alternating pairs, no fixed effects."""
    return ols_fe(*fish_design(markets, NAIVE_WINDOW), fixed_effects=False)


# ---------- registry used by stats.py ----------

def per_market_scorers(nash: float, monopoly: float) -> dict:
    """name -> function(market) -> score (higher = more collusive-looking). NaN = not identified."""
    return {
        "collusion_index": lambda m: collusion_index(m, nash, monopoly),
        "corr_levels": lambda m: correlation(m, diff=False),
        "corr_diffs": lambda m: correlation(m, diff=True),
        "fish_delta": lambda m: fish_regression([m]).delta,
        "naive_delta": lambda m: naive_regression([m]).delta,
    }


def pooled_scorers(nash: float, monopoly: float) -> dict:
    """name -> function(list of markets) -> pooled statistic.

    Regressions are estimated on the pooled markets; the other tests average per-market scores
    (unidentified correlations count as 0, as in stats.py).
    """
    per = per_market_scorers(nash, monopoly)

    def mean_of(name):
        return lambda ms: float(np.mean([_nan0(per[name](m)) for m in ms])) if ms else math.nan

    return {
        "collusion_index": mean_of("collusion_index"),
        "corr_levels": mean_of("corr_levels"),
        "corr_diffs": mean_of("corr_diffs"),
        "fish_delta": lambda ms: fish_regression(ms).delta,
        "naive_delta": lambda ms: naive_regression(ms).delta,
    }


def _nan0(x: float) -> float:
    return 0.0 if math.isnan(x) else x
