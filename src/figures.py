"""Figures for the writeup (CLAUDE.md, Figures), as PNGs.

1. Per-pair Fish delta: placebo, real and instructed pairs, Fish et al.'s reported delta marked.
2. The same for naive delta.
3. Price paths of a few real games with the Nash and monopoly lines.
4. Cross-game diagnostic: correlation of first differences between games vs within games.

Colors: the dataviz skill's validated categorical slots 1-3, in fixed order. Groups sit on labeled
rows, so identity never depends on color alone.
"""

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLORS = {"placebo": "#2a78d6", "real": "#eb6834", "instructed": "#1baf7a"}
LABELS = {"placebo": "Placebo pairs", "real": "Real pairs", "instructed": "Instructed pairs"}
FISH_P1_DELTA = 0.103  # Fish et al. Table 1, P1
LABEL_BOX = dict(facecolor=SURFACE, edgecolor="none", pad=1.5)  # keeps reference lines from crossing label text


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def coefficient_strips(pairs: pd.DataFrame, test: str, title: str, path: Path, reference: float | None = None,
                       threshold: float | None = None, seed: int = 0) -> None:
    """One row per group; each dot is one pair's coefficient. Unidentified pairs are counted in the row label."""
    rng = np.random.default_rng(seed)
    kinds = [k for k in ("placebo", "real", "instructed") if (pairs.kind == k).any()]
    fig, ax = plt.subplots(figsize=(8, 1.2 + 0.9 * len(kinds)), facecolor=SURFACE)
    _style(ax)
    yticks, ylabels = [], []
    for row, kind in enumerate(reversed(kinds)):
        v = pairs.loc[pairs.kind == kind, test].to_numpy(float)
        ok = v[~np.isnan(v)]
        n_nan = int(np.isnan(v).sum())
        jitter = rng.uniform(-0.28, 0.28, len(ok)) if len(ok) > 30 else rng.uniform(-0.12, 0.12, len(ok))
        size, alpha = (14, 0.45) if len(ok) > 30 else (46, 0.9)
        ax.scatter(ok, row + jitter, s=size, color=COLORS[kind], alpha=alpha, edgecolors=SURFACE, linewidths=0.8, zorder=3)
        if len(ok):
            ax.plot([np.median(ok)] * 2, [row - 0.38, row + 0.38], color=INK, linewidth=2, zorder=4, solid_capstyle="round")
        yticks.append(row)
        extra = f"\n{n_nan} not identified" if n_nan else ""
        ylabels.append(f"{LABELS[kind]}\n(n={len(v)}){extra}")
    ax.set_yticks(yticks, ylabels, color=INK, fontsize=9)
    ax.tick_params(axis="y", length=0)
    ax.set_ylim(-0.6, len(kinds) - 0.4)
    top = len(kinds) - 0.45
    ax.axvline(0, color=INK2, linewidth=1, zorder=2)
    if reference is not None:
        ax.axvline(reference, color=INK, linewidth=1.2, linestyle=(0, (4, 3)), zorder=2)
        ax.text(reference, top, f" Fish et al. P1 δ = {reference}", color=INK, fontsize=8.5, va="top", zorder=5,
                bbox=LABEL_BOX)
    if threshold is not None and math.isfinite(threshold):
        ax.axvline(threshold, color=COLORS["placebo"], linewidth=1.2, linestyle=(0, (1, 2)), zorder=2)
        ax.text(threshold, -0.55, f" placebo 95th pct = {threshold:.3f}", color=INK2, fontsize=8.5, va="bottom",
                zorder=5, bbox=LABEL_BOX)
    ax.set_xlabel(f"{title} per pair  (black bar = median)", color=INK2, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def price_paths(games, nash: float, monopoly: float, path: Path, n: int = 6) -> None:
    """Small multiples, shared axes: firm 0 and firm 1 prices by period, Nash and monopoly lines."""
    games = games[:n]
    cols = 3
    rows = math.ceil(len(games) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(10, 2.6 * rows), sharex=True, sharey=True, facecolor=SURFACE, squeeze=False)
    t = np.arange(1, games[0].periods + 1)
    for ax, g in zip(axes.flat, games):
        _style(ax)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        for level, name in ((monopoly, "Monopoly"), (nash, "Nash")):
            ax.axhline(level, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
            ax.text(t[-1], level, f" {name}", color=INK2, fontsize=7.5, va="center", ha="left")
        ax.plot(t, g.prices[:, 0], color=COLORS["placebo"], linewidth=1.6, label="Firm 0")
        ax.plot(t, g.prices[:, 1], color=COLORS["real"], linewidth=1.6, label="Firm 1")
        ax.set_title(g.run_id, color=INK, fontsize=9, loc="left")
    for ax in axes.flat[len(games):]:
        ax.set_visible(False)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, loc="upper center", ncol=2, labelcolor=INK)
    fig.supxlabel("Period", color=INK2, fontsize=9)
    fig.supylabel("Price", color=INK2, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def cross_game(diag: dict, path: Path) -> None:
    """First-difference correlations: cross-game (never met) vs within-game (real pairs)."""
    cross = diag["cross"]
    within = diag["within"]
    groups = [("Cross-game, firm 0", cross.loc[cross.firm == 0, "corr_diffs"], COLORS["placebo"]),
              ("Cross-game, firm 1", cross.loc[cross.firm == 1, "corr_diffs"], COLORS["placebo"]),
              ("Within-game (real pairs)", within["corr_diffs"], COLORS["real"])]
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(figsize=(8, 3.4), facecolor=SURFACE)
    _style(ax)
    band = diag["independence_band"]
    ax.axvspan(-band, band, color=GRID, alpha=0.6, zorder=1)
    ax.text(band, 2.45, f" ±{band:.2f}: range for independent noise", color=INK2, fontsize=8, va="top", zorder=5,
            bbox=LABEL_BOX)
    ax.axvline(0, color=INK2, linewidth=1)
    labels = []
    for row, (name, s, color) in enumerate(reversed(groups)):
        v = s.to_numpy(float)
        ok = v[~np.isnan(v)]
        jit = rng.uniform(-0.28, 0.28, len(ok)) if len(ok) > 30 else rng.uniform(-0.12, 0.12, len(ok))
        ax.scatter(ok, row + jit, s=14 if len(ok) > 30 else 40, color=color, alpha=0.5 if len(ok) > 30 else 0.9,
                   edgecolors=SURFACE, linewidths=0.8, zorder=3)
        if len(ok):
            ax.plot([np.median(ok)] * 2, [row - 0.38, row + 0.38], color=INK, linewidth=2, zorder=4)
        n_nan = int(np.isnan(v).sum())
        labels.append(f"{name}\n(n={len(v)}" + (f", {n_nan} undefined)" if n_nan else ")"))
    ax.set_yticks(range(len(groups)), labels, color=INK, fontsize=9)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(-1.06, 1.06)
    ax.set_xlabel("Correlation of first differences, periods 101–300  (black bar = median; undefined = a frozen seller)",
                  color=INK2, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def impulse_response(by_period: pd.DataFrame, path: Path) -> None:
    """Mean forced-minus-control price by period, per condition, with the mean myopic best-response cut as reference."""
    conds = [c for c in ("baseline", "instructed") if (by_period.condition == c).any()]
    fig, axes = plt.subplots(1, len(conds), figsize=(5 * len(conds), 3.6), sharey=True, facecolor=SURFACE, squeeze=False)
    for ax, cond in zip(axes.flat, conds):
        _style(ax)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        d = by_period[by_period.condition == cond].sort_values("period")
        t = d.period.to_numpy()
        ax.axhline(0, color=INK2, linewidth=1)
        dbr = float(d.dBR_mean.iloc[0])
        ax.axhline(dbr, color=INK, linewidth=1.2, linestyle=(0, (4, 3)), label="Myopic best-response cut (mean dBR)")
        ax.plot(t, d.D_firm0_mean, color=COLORS["placebo"], linewidth=1.6, marker="o", markersize=4, label="Firm 0 (forced)")
        ax.errorbar(t, d.D_firm1_mean, yerr=d.D_firm1_se, color=COLORS["real"], linewidth=2, marker="o", markersize=5,
                    capsize=0, elinewidth=1.2, label="Firm 1 (responder), ±1 SE across games")
        ax.set_title(f"{cond.capitalize()} games (n={int(d.n_games.iloc[0])}), mean dBR = {dbr:.3f}",
                     color=INK, fontsize=10, loc="left")
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        ax.set_xlabel("Period (firm 0 forced to 1.47 in period 201)", color=INK2, fontsize=9)
    axes.flat[0].set_ylabel("Price, forced minus control branch", color=INK2, fontsize=9)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, loc="upper center", ncol=3, labelcolor=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def all_figures(evaluation: dict, games, diag: dict, nash: float, monopoly: float, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    s = evaluation["summary"].set_index(["test", "version"])
    paths = [out_dir / "fig1_fish_delta.png", out_dir / "fig2_naive_delta.png",
             out_dir / "fig3_price_paths.png", out_dir / "fig4_cross_game.png"]
    coefficient_strips(evaluation["pairs"], "fish_delta", "Fish δ (periods 101–300, firm-run fixed effects)", paths[0],
                       reference=FISH_P1_DELTA, threshold=s.loc[("fish_delta", "all"), "threshold_placebo_p95"])
    coefficient_strips(evaluation["pairs"], "naive_delta", "Naive δ (all periods, no fixed effects)", paths[1],
                       reference=FISH_P1_DELTA, threshold=s.loc[("naive_delta", "all"), "threshold_placebo_p95"])
    price_paths(games, nash, monopoly, paths[2])
    cross_game(diag, paths[3])
    return paths
