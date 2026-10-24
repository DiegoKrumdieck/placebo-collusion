"""Load finished games and build real, placebo and re-paired (derangement) markets.

A market is two price paths, seller A in the firm-0 role and seller B in the firm-1 role.
Placebo markets use price paths only: logged quantities and profits were computed against the
real competitor and are never used here.
"""

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# Settings that must match for two games to be paired (CLAUDE.md, Pairs).
PAIRING_KEYS = ["condition", "model", "temperature", "alpha", "ceiling_multiplier", "prompt_prefix", "prompt_version", "thinking"]


@dataclass
class Game:
    run_id: str
    condition: str
    prices: np.ndarray  # shape (T, 2); row t-1 holds period t, column = firm
    config: dict = field(default_factory=dict)

    @property
    def periods(self) -> int:
        return self.prices.shape[0]


@dataclass
class Market:
    a: np.ndarray  # firm-0 role price path, period 1 at index 0
    b: np.ndarray  # firm-1 role price path
    kind: str  # "real", "placebo" or "instructed"
    run_a: str
    run_b: str

    @property
    def sellers(self) -> tuple[tuple[str, int], tuple[str, int]]:
        return (self.run_a, 0), (self.run_b, 1)


def load_game(run_dir: Path) -> Game:
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    with (run_dir / "periods.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    T = max(int(r["period"]) for r in rows)
    prices = np.full((T, 2), np.nan)
    for r in rows:
        prices[int(r["period"]) - 1, int(r["firm"])] = float(r["price"])
    if np.isnan(prices).any():
        raise ValueError(f"{run_dir}: missing periods")
    return Game(config["run_id"], config["condition"], prices, config)


def load_games(runs_root: Path, condition: str, periods: int = 300) -> list[Game]:
    """All finished games of one condition, sorted by run id. Unfinished games are an error."""
    games = [load_game(d) for d in sorted((runs_root / condition).iterdir()) if (d / "config.json").exists()]
    short = [g.run_id for g in games if g.periods < periods]
    if short:
        raise ValueError(f"unfinished games in {condition}: {short}")
    check_compatible(games)
    return games


def check_compatible(games: list[Game]) -> None:
    """Refuse to pair games that differ in any pairing setting."""
    if not games:
        return
    ref = {k: games[0].config.get(k) for k in PAIRING_KEYS}
    for g in games[1:]:
        diff = {k: (ref[k], g.config.get(k)) for k in PAIRING_KEYS if g.config.get(k) != ref[k]}
        if diff:
            raise ValueError(f"{g.run_id} differs from {games[0].run_id}: {diff}")


def real_markets(games: list[Game], kind: str = "real") -> list[Market]:
    return [Market(g.prices[:, 0], g.prices[:, 1], kind, g.run_id, g.run_id) for g in games]


def placebo_markets(games: list[Game]) -> list[Market]:
    """Firm 0 of game i with firm 1 of game j, every ordered i != j: N(N-1) markets."""
    return [
        Market(gi.prices[:, 0], gj.prices[:, 1], "placebo", gi.run_id, gj.run_id)
        for i, gi in enumerate(games) for j, gj in enumerate(games) if i != j
    ]


def derangement(n: int, rng: np.random.Generator) -> np.ndarray:
    """Uniform random permutation with no fixed points (rejection sampling; ~e tries on average)."""
    if n < 2:
        raise ValueError("need at least 2 games for a derangement")
    while True:
        perm = rng.permutation(n)
        if not (perm == np.arange(n)).any():
            return perm


def deranged_markets(games: list[Game], perm: np.ndarray) -> list[Market]:
    """N placebo markets: firm 0 of game i with firm 1 of game perm[i]."""
    return [
        Market(games[i].prices[:, 0], games[p].prices[:, 1], "placebo", games[i].run_id, games[p].run_id)
        for i, p in enumerate(perm)
    ]
