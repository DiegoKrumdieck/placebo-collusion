"""Hold-back classification (CLAUDE.md, Follow-up (d)). Rules are fixed on synthetic agents only.

D(t) = firm 1's forced-branch price minus its control-branch price, t = 202..220, rounded to cents
(prices are set in cents, so this removes float noise like 1.79 - 1.80 = -0.0100000001).
"""

import pandas as pd

TOL = 0.01
FIRST, LAST = 202, 220
MATCH_BY = 204
MIN_PUNISH_PERIODS = 3
CATEGORIES = ["no reaction", "matching", "punish-and-return", "persistent", "other"]


def classify(D: dict) -> dict:
    """Categories in precedence order: no reaction, persistent, matching, punish-and-return, other."""
    D = {t: round(D[t], 2) for t in range(FIRST, LAST + 1)}
    below = {t: D[t] < -TOL for t in D}
    if not any(below.values()):
        return {"category": "no reaction", "first_cut": None, "back_period": None, "periods_below": 0,
                "min_D": min(D.values()), "D_220": D[LAST]}
    t_cut = min(t for t in D if below[t])
    back = next((t for t in range(t_cut + 1, LAST + 1) if abs(D[t]) <= TOL), None)
    periods_below = (back if back is not None else LAST + 1) - t_cut
    if below[LAST]:
        cat = "persistent"
    elif back is not None and back <= MATCH_BY:
        cat = "matching"
    elif back is not None and periods_below >= MIN_PUNISH_PERIODS:
        cat = "punish-and-return"
    else:
        cat = "other"
    return {"category": cat, "first_cut": t_cut, "back_period": back, "periods_below": periods_below,
            "min_D": min(D.values()), "D_220": D[LAST]}


def summarize_categories(per_game: pd.DataFrame) -> pd.DataFrame:
    counts = pd.crosstab(per_game["row"], per_game["category"]).reindex(columns=CATEGORIES, fill_value=0)
    counts.insert(0, "n_games", counts.sum(axis=1))
    return counts.reset_index()
