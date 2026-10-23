"""Thin wrapper over the EconEvals logit duopoly (Fish et al.'s parameters)."""

from functools import lru_cache

from econ_evals.experiments.pricing.pricing_market_logic_multiproduct import (
    get_monopoly_prices,
    get_nash_prices,
    get_profits,
    get_quantities,
)

# Fish et al.'s duopoly, Section 2.1. alpha is set per market.
BASE_PARAMS = dict(a0=0, a=(2, 2), c=(1, 1), mu=0.25, multiplier=100, sigma=0, group_idxs=(1, 1))


@lru_cache(maxsize=None)
def _equilibria(alpha: float) -> tuple[float, float]:
    kw = dict(BASE_PARAMS, alpha=(alpha, alpha))
    nash = get_nash_prices(**kw)
    monopoly = get_monopoly_prices(**kw)
    # The market is symmetric, so both firms share one Nash and one monopoly price.
    return sum(nash) / 2, sum(monopoly) / 2


class Market:
    def __init__(self, alpha: float = 1.0, ceiling_multiplier: float = 1.5):
        self.alpha = alpha
        self.ceiling_multiplier = ceiling_multiplier
        self.nash_price, self.monopoly_price = _equilibria(alpha)
        # Fish et al. footnote 18: the ceiling shown to agents is multiplier * p^M.
        self.ceiling = ceiling_multiplier * self.monopoly_price
        self.marginal_cost = alpha * BASE_PARAMS["c"][0]

    def outcome(self, p0: float, p1: float) -> tuple[list[float], list[float]]:
        """Quantities and profits for both firms at prices (p0, p1)."""
        kw = dict(BASE_PARAMS, alpha=(self.alpha, self.alpha))
        c = kw.pop("c")
        q = get_quantities(p=(p0, p1), **kw)
        pi = get_profits(p=(p0, p1), c=c, **kw)
        return q, pi
