"""Synthetic price paths where the right answer is known, for validating the analysis pipeline.

Prices are rounded to 2 decimals like the LLM agents' prices. Every generator returns Game objects
with a config that passes the pairing check.
"""

import numpy as np

from pairs import Game

NASH, MONOPOLY = 1.4729287011528647, 1.9249809175424142
T = 300


def _config(condition: str, run_id: str) -> dict:
    return {"run_id": run_id, "condition": condition, "model": "synthetic", "temperature": 1.0, "alpha": 1.0,
            "ceiling_multiplier": 1.5, "prompt_prefix": "synthetic", "prompt_version": "synthetic", "thinking": "n/a"}


def _games(paths: list[np.ndarray], condition: str) -> list[Game]:
    return [Game(f"{condition}_{k + 1:03d}", condition, np.round(p, 2), _config(condition, f"{condition}_{k + 1:03d}"))
            for k, p in enumerate(paths)]


def independent(n: int, rng, phi: float = 0.6, sigma: float = 0.03) -> list[np.ndarray]:
    """Each firm an AR(1) around its own level; no reaction to the competitor at all."""
    out = []
    for _ in range(n):
        mu = rng.uniform(1.55, 1.85, size=2)
        p = np.empty((T, 2))
        p[0] = mu + rng.normal(0, sigma, 2)
        for t in range(1, T):
            p[t] = mu + phi * (p[t - 1] - mu) + rng.normal(0, sigma, 2)
        out.append(p)
    return out


def follower(n: int, rng, rho: float = 0.8, sigma: float = 0.03) -> list[np.ndarray]:
    """Each firm copies its competitor's last price (shrunk toward a level) plus noise. True delta = rho."""
    out = []
    for _ in range(n):
        mu = rng.uniform(1.55, 1.85)
        p = np.empty((T, 2))
        p[0] = mu + rng.normal(0, sigma, 2)
        for t in range(1, T):
            p[t] = mu + rho * (p[t - 1, ::-1] - mu) + rng.normal(0, sigma, 2)
        out.append(p)
    return out


def leader_follower(n: int, rng, rho: float = 0.8, phi: float = 0.6, sigma: float = 0.03) -> list[np.ndarray]:
    """Firm 0 is an independent AR(1); firm 1 copies firm 0's last price plus noise.

    With the dependent firm alternating, the pooled delta averages rho (firm 1) and 0 (firm 0): about rho / 2.
    """
    out = []
    for _ in range(n):
        mu = rng.uniform(1.55, 1.85)
        p = np.empty((T, 2))
        p[0] = mu + rng.normal(0, sigma, 2)
        for t in range(1, T):
            p[t, 0] = mu + phi * (p[t - 1, 0] - mu) + rng.normal(0, sigma)
            p[t, 1] = mu + rho * (p[t - 1, 0] - mu) + rng.normal(0, sigma)
        out.append(p)
    return out


def shared_trajectory(n: int, rng, phi: float = 0.6, sigma: float = 0.03) -> list[np.ndarray]:
    """Every seller follows the same start-low, climb, settle path plus independent AR(1) noise.

    No seller reacts to anyone, but all paths share one trajectory: the case the placebo is built for.
    """
    t = np.arange(1, T + 1)
    path = 1.40 + 0.40 * (1 - np.exp(-t / 40))
    out = []
    for _ in range(n):
        e = np.zeros((T, 2))
        for s in range(1, T):
            e[s] = phi * e[s - 1] + rng.normal(0, sigma, 2)
        out.append(path[:, None] + e)
    return out


def freeze(paths: list[np.ndarray], rng, share: float, start=(100, 150)) -> list[np.ndarray]:
    """Freeze a share of games: from a random period in `start` on, both firms repeat their last price."""
    out = []
    for p in paths:
        p = np.round(p.copy(), 2)
        if rng.random() < share:
            tau = int(rng.integers(start[0], start[1] + 1))
            p[tau:] = p[tau - 1]
        out.append(p)
    return out


def scenario(name: str, seed: int = 0, n_base: int = 21, n_instr: int = 6) -> tuple[list[Game], list[Game]]:
    """(baseline games, instructed games) for a named validation case."""
    rng = np.random.default_rng(seed)
    if name == "independent":
        base, instr = independent(n_base, rng), follower(n_instr, rng)
    elif name == "follower":
        base, instr = follower(n_base, rng), follower(n_instr, rng)
    elif name == "shared_trajectory":
        base, instr = shared_trajectory(n_base, rng), follower(n_instr, rng)
    elif name == "leader_follower":
        base, instr = independent(n_base, rng), leader_follower(n_instr, rng)
    elif name == "mostly_frozen":
        # As in wave 1: 70% of baseline games lock in after period 100-150; every instructed game does.
        base, instr = freeze(follower(n_base, rng), rng, 0.7), freeze(follower(n_instr, rng), rng, 1.0)
    elif name == "all_frozen":
        # Every game freezes before period 100: no price variation at all in periods 101-300.
        base = freeze(follower(n_base, rng), rng, 1.0, start=(50, 99))
        instr = freeze(follower(n_instr, rng), rng, 1.0, start=(50, 99))
    else:
        raise ValueError(name)
    return _games(base, "baseline"), _games(instr, "instructed")


SCENARIOS = ["independent", "follower", "leader_follower", "shared_trajectory", "mostly_frozen", "all_frozen"]
