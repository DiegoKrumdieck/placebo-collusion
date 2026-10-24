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


# ---------- noisy agents (CLAUDE.md, Second follow-up (g)) ----------

TREMBLE = 0.15
COOLDOWN = 20


class CoolingColluder(Colluder):
    """Colluder with punishment length L and a cooldown: no new punishment in the 20 periods after any
    period in which its own price was below 1.78 (its tremble, punishment or recovery)."""

    def __init__(self, punish_periods: int = PUNISH_PERIODS):
        super().__init__()
        self.L, self.cool = punish_periods, 0

    def act(self, own_prev: float, rival_prev: float) -> float:
        if own_prev < TRIGGER - 1e-9:
            self.cool = COOLDOWN
        if self.punish_left == 0 and self.cool == 0 and rival_prev < TRIGGER - 1e-9:
            self.punish_left = self.L
        if self.cool > 0:
            self.cool -= 1
        if self.punish_left > 0:
            self.punish_left -= 1
            target = br(round(rival_prev, 2))
        else:
            target = COLLUDE_TARGET
        return sticky_step(own_prev, target)


def make_agent(agent_type: str, L: int = PUNISH_PERIODS):
    return Competitor() if agent_type == "competitor" else CoolingColluder(L)


def tremble(rule_price: float, flag: float, amount: float, q: float) -> float:
    if flag >= q:
        return rule_price
    return float(min(max(round(rule_price + amount, 2), _MARKET.marginal_cost), round(_MARKET.ceiling, 2)))


def simulate_noisy(agent_type: str, q: float, seed: int, L: int = PUNISH_PERIODS, periods: int = T):
    """One noisy game. Draws are taken every period for both firms whatever q is, so a game's first
    200 periods are identical however long it is simulated. Returns (prices, agents)."""
    rng = np.random.default_rng(seed)
    agents = [make_agent(agent_type, L), make_agent(agent_type, L)]
    p = np.empty((periods, 2))
    p[0] = np.round(START + rng.uniform(-START_NOISE, START_NOISE, 2), 2)
    for t in range(1, periods):
        flags, amounts = rng.random(2), rng.uniform(-TREMBLE, TREMBLE, 2)
        p[t] = [tremble(agents[i].act(p[t - 1, i], p[t - 1, 1 - i]), flags[i], amounts[i], q) for i in (0, 1)]
    return p, agents


def noisy_games(agent_type: str, q: float, n: int = 21, seed: int = 20261025, L: int = PUNISH_PERIODS) -> list[Game]:
    label = agent_type if agent_type == "competitor" else f"colluder_L{L}"
    out = []
    for k in range(n):
        p, _ = simulate_noisy(agent_type, q, seed * 1000 + k, L)
        run_id = f"noisy_{label}_{k + 1:03d}"
        cfg = {"run_id": run_id, "condition": f"noisy_{label}", "model": f"synthetic-noisy-{label}",
               "temperature": 0.0, "alpha": 1.0, "ceiling_multiplier": 1.5, "prompt_prefix": "none",
               "prompt_version": "none", "thinking": "n/a", "tremble_q": q,
               "nash_price": _MARKET.nash_price, "monopoly_price": _MARKET.monopoly_price}
        out.append(Game(run_id, cfg["condition"], p, cfg))
    return out


def change_share(games_: list[Game], window=(101, 300)) -> float:
    from detectors import n_changes
    s, e = window
    return float(np.mean([n_changes(g.prices[:, f], window) / (e - s + 1) for g in games_ for f in (0, 1)]))


def calibrate_q(agent_type: str, target: float, seed: int = 777, n: int = 21, tol: float = 0.003,
                L: int = PUNISH_PERIODS) -> tuple[float, float]:
    """Bisection on q so the pooled change share over periods 101-300 is within tol of target."""
    lo, hi = 0.0, 0.2
    for _ in range(30):
        q = (lo + hi) / 2
        share = change_share(noisy_games(agent_type, q, n, seed, L))
        if abs(share - target) <= tol:
            return q, share
        lo, hi = (q, hi) if share < target else (lo, q)
    return q, share


def noisy_holdback(agent_type: str, q: float, n: int = 21, seed: int = 20261025, L: int = PUNISH_PERIODS,
                   forced_price: float = 1.47, last_period: int = LAST_PERIOD) -> list[dict]:
    """Hold-back fork on each noisy game: same game as noisy_games up to period 200; firm 0 exogenous;
    firm 1's tremble draws for 201-220 are drawn once and replayed in both branches."""
    label = agent_type if agent_type == "competitor" else f"colluder_L{L}"
    out = []
    for k in range(n):
        p, agents = simulate_noisy(agent_type, q, seed * 1000 + k, L, periods=FORK_AFTER)
        p0_200, p1_200 = p[-1, 0], p[-1, 1]
        frng = np.random.default_rng([seed, k, 201])
        # Sequential draws: a longer fork reuses the same draws for 201-220 and continues the stream.
        draws = [(frng.random(), frng.uniform(-TREMBLE, TREMBLE)) for _ in range(last_period - FORK_AFTER)]
        branches = {}
        for branch in ("forced", "control"):
            agent = copy.deepcopy(agents[1])
            own, rival_prev, path = p1_200, p0_200, {}
            for i, t in enumerate(range(FORK_AFTER + 1, last_period + 1)):
                own = tremble(agent.act(own, rival_prev), draws[i][0], draws[i][1], q)
                path[t] = own
                rival_prev = forced_price if branch == "forced" and t == FORK_AFTER + 1 else p0_200
            branches[branch] = path
        out.append({"run_id": f"noisy_{label}_{k + 1:03d}", "p0_200": float(p0_200), "p1_200": float(p1_200), **branches})
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
