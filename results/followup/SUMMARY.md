# Follow-up: hold-back fork, synthetic known-answer agents, instructed-only placebo (2026-10-24)

Pre-registered in CLAUDE.md (commit `2384f37`), designed after seeing the first fork results.
Hold-back classification rules were fixed on synthetic agents only and committed (`f3ce733`) before any
Haiku hold-back result was read. Haiku hold-back fork: 54 branches, 1,080 firm-1 calls, 0 parse failures,
cost $1.47 (cap $5). Files: `main_table.csv`, `*_per_game.csv`, `*_D.csv`, `fig6_holdback_mean_D.png`.

## Main table

Fish δ and naive δ: pooled real vs 1,000 re-pairings within the same row (p one-sided), and per-pair AUROC
real vs placebo. "Not identified" = the pair's prices don't move in the regression window.
Hold-back: firm 0 at 1.47 for one period (201), then back at its own period-200 price; categories from
D(t) = firm 1 forced minus control, t = 202–220 (rules in CLAUDE.md, Follow-up (d)).

| Row | Fish δ real / placebo mean | Fish p, AUROC | Naive δ real / placebo mean | Naive p, AUROC | No reaction | Matching | Punish-and-return | Persistent | Other |
|---|---|---|---|---|---|---|---|---|---|
| Synthetic competitor (21) | not identified (21/21 frozen) | —, 0.50 | 0.028 / 0.014 | 0.042, 0.65 | 21 | 0 | 0 | 0 | 0 |
| Synthetic colluder (21) | not identified (21/21 frozen) | —, 0.50 | 0.070 / 0.002 | 0.15, 0.50 | 0 | 0 | **21** | 0 | 0 |
| Synthetic competitor, shocked (21; hold-back only) | — | — | — | — | 0 | **21** | 0 | 0 | 0 |
| Haiku baseline (21) | 0.086 / 0.005 | 0.001, 0.71 | 0.033 / 0.003 | 0.001, 0.74 | 5 | 7 | **1** | 6 | 2 |
| Haiku instructed (6; instructed-only placebo) | not identified (6/6 frozen) | 0.79, 0.48 | 0.006 / 0.000 | 0.033, 0.42 | 3 | 1 | **0** | 2 | 0 |

![Mean D(t)](fig6_holdback_mean_D.png)

## What it shows

- **On-path δ tests are blind to a known colluder that holds its price.** The synthetic colluder runs a
  true reward–punishment strategy, but it never deviates on path, so Fish δ has nothing to estimate (21/21),
  and naive δ doesn't beat its placebo (p = 0.15, AUROC 0.50). The Haiku instructed games look the same:
  Fish δ is not identified in 6/6.
- **The hold-back fork separates the known agents.** Colluder: 21/21 punish-and-return, cutting to −0.12
  for 5 periods and returning by period 215–216. Competitor: no reaction (it already sits at 1.48, so the
  cut is one cent). A competitor facing a real cut: 21/21 matching, a 2–3 cent dip gone by period 204.
- **Haiku firms mostly ignore or briefly match a one-period cut.** Among 21 baseline games: 5 no reaction,
  7 matching (often a one-period drop of 0.10–0.27, back the next period), and only 1 punish-and-return
  (baseline_016: −0.24 for 4 periods, back by 206). Instructed: 0 of 6 punish-and-return.
- **But 8 of 27 Haiku games drop and stay down.** 6 baseline and 2 instructed games are persistent: firm 1
  is still lower at period 220 although firm 0 returned to its old price in period 202. Sizes range
  from −0.05 to −0.16 at period 220 (instructed_003: −0.45). That is not the reward–punishment signature,
  which needs a return.
- **Firm 1 almost never goes below the Nash price (1.47).** Share of periods 202–220 below 1.47, mean over
  baseline games: 0.20 forced vs 0.18 control. Nearly all of it is in 4 games that already priced at
  1.43–1.47 before the fork (baseline_001, 009, 010, 012). Elsewhere: one period in baseline_004 and
  baseline_007, three in baseline_008 (forced branch only). Instructed: 0 in both branches.
- **Instructed-only placebo:** re-pairing instructed firms across the 6 instructed games gives the same
  high prices. Per-pair price-level AUROC, real vs placebo: 0.48 [0.35, 0.64] (6 real, 30 placebo pairs).
  The high level reflects each firm following its own instruction, not anything the pair does together.

## Caveats

- The hold-back rules have a thin margin against a sluggish myopic responder (CLAUDE.md, Follow-up (d)).
  The one Haiku punish-and-return game has a deep cut (−0.24), which counts against that explanation.
- Forced and control branches are sampled separately, so small persistent gaps (−0.05 in baseline_013,
  baseline_020, instructed_002) could be sampling noise between branches. We did not run a
  control-vs-control fork to measure that noise.
- Synthetic agents are deterministic. With noise only in their starting prices, they freeze by period 100,
  which is why Fish δ can't be estimated for them.
