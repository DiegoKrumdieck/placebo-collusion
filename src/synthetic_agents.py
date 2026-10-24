"""Synthetic known-answer agents (CLAUDE.md, Follow-up (b)): a sticky competitor and a sticky colluder.

Both firms of a game use the same agent type. Prices are in cents. BR(q) is the static best response to a
rival price q over [marginal cost, ceiling], from the EconEvals profit function.
"""

import copy
from functools import lru_cache

import numpy as np

from impulse import FORK_AFTER, LAST_PERIOD, best_response
from market import Market
from pairs import Game

STICKY = 0.84
COLLUDE_TARGET, TRIGGER, PUNISH_PERIODS = 1.80, 1.78, 5
START, START_NOISE = 1.80, 0.02
T = 300
_MARKET = Market()


@lru_cache(maxsize=None)
def br(q_cents: float) -> float:
    return best_response(q_cents, _MARKET)


def sticky_step(p_prev: float, target: float) -> float:
    """p = 0.84 p_prev + 0.16 target, in cents. If rounding would leave the price unchanged while it is
    at least half a cent from its target, move one cent toward the target (CLAUDE.md rounding rule)."""
    p = round(STICKY * p_prev + (1 - STICKY) * target, 2)
    if p == round(p_prev, 2) and abs(p_prev - target) >= 0.005:
        p = round(p_prev + (0.01 if target > p_prev else -0.01), 2)
    return p


class Competitor:
    name = "competitor"

    def act(self, own_prev: float, rival_prev: float) -> float:
        return sticky_step(own_prev, br(round(rival_prev, 2)))


class Colluder:
    """Target 1.80 while the rival's last price is >= 1.78; otherwise punish for 5 periods with target
    BR(rival's last price), then target 1.80 again, checking the trigger from then on."""
    name = "colluder"

    def __init__(self):
        self.punish_left = 0

    def act(self, own_prev: float, rival_prev: float) -> float:
        if self.punish_left == 0 and rival_prev < TRIGGER - 1e-9:
            self.punish_left = PUNISH_PERIODS
        if self.punish_left > 0:
            self.punish_left -= 1
            target = br(round(rival_prev, 2))
        else:
            target = COLLUDE_TARGET
        return sticky_step(own_prev, target)


AGENTS = {"competitor": Competitor, "colluder": Colluder}


def simulate(agent_type: str, rng: np.random.Generator, periods: int = T):
    """One game. Returns (prices array (periods, 2), the two agents at the end)."""
    agents = [AGENTS[agent_type](), AGENTS[agent_type]()]
    p = np.empty((periods, 2))
    p[0] = np.round(START + rng.uniform(-START_NOISE, START_NOISE, 2), 2)
    for t in range(1, periods):
        p[t] = [agents[i].act(p[t - 1, i], p[t - 1, 1 - i]) for i in (0, 1)]
    return p, agents


def games(agent_type: str, n: int = 21, seed: int = 20261024) -> list[Game]:
    rng = np.random.default_rng(seed)
    out = []
    for k in range(n):
        p, _ = simulate(agent_type, rng)
        run_id = f"synthetic_{agent_type}_{k + 1:03d}"
        cfg = {"run_id": run_id, "condition": f"synthetic_{agent_type}", "model": f"synthetic-{agent_type}",
               "temperature": 0.0, "alpha": 1.0, "ceiling_multiplier": 1.5, "prompt_prefix": "none",
               "prompt_version": "none", "thinking": "n/a", "nash_price": _MARKET.nash_price,
               "monopoly_price": _MARKET.monopoly_price}
        out.append(Game(run_id, cfg["condition"], p, cfg))
    return out


def holdback_shocked_competitor(n: int = 21, seed: int = 20261024, forced_price: float = 1.47) -> list[dict]:
    """Stress check for the rules: a competitor that actually faces a cut.

    Firm 0 is held at p0 ~ U(1.70, 1.90) (cents) for 200 periods, so the competitor (firm 1) settles at
    its sticky response to p0; then the same hold-back branches as `holdback`.
    """
    rng = np.random.default_rng(seed)
    out = []
    for k in range(n):
        p0 = round(float(rng.uniform(1.70, 1.90)), 2)
        agent, own = Competitor(), p0
        for _ in range(FORK_AFTER - 1):
            own = agent.act(own, p0)
        branches = {}
        for branch in ("forced", "control"):
            o, rival_prev, path = own, p0, {}
            for t in range(FORK_AFTER + 1, LAST_PERIOD + 1):
                o = agent.act(o, rival_prev)
                path[t] = o
                rival_prev = forced_price if branch == "forced" and t == FORK_AFTER + 1 else p0
            branches[branch] = path
        out.append({"run_id": f"shocked_competitor_{k + 1:03d}", "p0_200": p0, **branches})
    return out


def holdback(agent_type: str, n: int = 21, seed: int = 20261024, forced_price: float = 1.47) -> list[dict]:
    """The hold-back fork on each synthetic game: simulate to period 200, then firm 0 is exogenous.

    Returns per game {run_id, p0_200, forced: {t: firm-1 price}, control: {...}} for t = 201..220.
    """
    rng = np.random.default_rng(seed)
    out = []
    for k in range(n):
        p, agents = simulate(agent_type, rng, periods=FORK_AFTER)  # rows = periods 1..200
        p0_200, p1_200 = p[-1, 0], p[-1, 1]
        branches = {}
        for branch in ("forced", "control"):
            agent = copy.deepcopy(agents[1])
            own, rival_prev, path = p1_200, p0_200, {}
            for t in range(FORK_AFTER + 1, LAST_PERIOD + 1):
                own = agent.act(own, rival_prev)
                path[t] = own
                rival_prev = forced_price if branch == "forced" and t == FORK_AFTER + 1 else p0_200
            branches[branch] = path
        out.append({"run_id": f"synthetic_{agent_type}_{k + 1:03d}", "p0_200": float(p0_200), **branches})
    return out
