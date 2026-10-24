# Results on the real runs (2026-10-23)

Model `claude-haiku-5-5`, thinking disabled, API-default temperature 1.0, prompts from arXiv 2404.00806v6,
α = 1, ceiling 1.5 × p^M. 21 baseline (P1) and 6 instructed games, 300 periods each.
Batch ran 20:10:53–21:49:41 EDT (1 h 39 min), 9 games at a time. 16,200 price decisions, 16,209 API calls:
9 parse retries (0.06%), 0 final parse failures, 0 API errors. Actual cost $20.93.
Spec: CLAUDE.md as of commit `7fe4213` (amended before any placebo test or fork).

## 1. Cross-game diagnostic (`DIAGNOSTIC.md`, `diagnostic_correlations_both_windows.csv`)

| Window | Cross-game corr. of first differences (firm 0 / firm 1) | Levels (firm 0 / firm 1) |
|---|---|---|
| Periods 1–100 | **0.40 / 0.35** (85% / 71% of pairs outside ±0.20) | 0.72 / 0.72 |
| Periods 101–300 | 0.00 / −0.00 (3% / 5% outside ±0.14) | 0.08 / 0.03 |

- Periods 1–100: sellers in different games move together (the shared start-high, come-down, settle path).
- Periods 101–300: sellers in different games don't change price in the same periods.
- Movement after period 100 is sparse: a typical baseline firm changes price in 4% of periods;
  4/21 baseline and 0/6 instructed games have both firms with ≥ 10 changes.

## 2. Placebo tests (`tests_summary.csv`, `tests_pairs.csv`, `tests_null.csv`, `table1_replication.csv`)

Pooled statistic on the 21 real baseline markets vs 1,000 random re-pairings (derangements).
Per-pair: 21 real, 420 placebo, 6 instructed pairs; threshold = 95th percentile of placebo pairs.
p-values are one-sided; 0.001 is the smallest possible (1/1001).
The pooled price level is the same for real pairs and every re-pairing (re-pairing reuses the same price
paths), so it has no placebo p-value; only its per-pair AUROC is informative.

All games:

| Test | Real (pooled) | Placebo mean / 95th pct | p | AUROC real vs placebo [95% CI] | Instructed (pooled) | Power on instructed at threshold |
|---|---|---|---|---|---|---|
| Price level Δ | 0.398 | — (identical by construction) | — | 0.49 [0.45, 0.53] | 1.623 | **6/6** |
| Correlation, levels | 0.365 | 0.050 / 0.123 | 0.001 | 0.71 [0.61, 0.81] | −0.001 | 0/6 |
| Correlation, differences | −0.052 | −0.005 / 0.016 | 0.99 | 0.45 [0.28, 0.62] | −0.083 | 0/6 |
| **Fish δ** | **0.086** | 0.005 / 0.030 | **0.001** | 0.71 [0.58, 0.83] | not identified (6/6 frozen) | **0/6** |
| Naive δ | 0.033 | 0.003 / 0.009 | 0.001 | 0.74 [0.64, 0.83] | 0.006 | 0/6 |

Moving games only (both firms ≥ 10 changes; 4 real, 62 placebo, 0 instructed pairs):
Fish δ real −0.005 vs placebo mean 0.040 (p = 0.79); naive δ 0.070 vs 0.001 (p = 0.023).

Fish et al. Table 1 replication, real baseline pairs (N = 2,100): γ = 0.842 (HC1 SE 0.094),
δ = 0.086 (HC1 SE 0.051; clustered by game 0.103), within R² = 0.859. Fish et al. (GPT-4, P1):
γ = 0.484 (0.102), δ = 0.103 (0.046), R² = 0.209.

Per-pair Fish δ above the placebo threshold (0.130): 8 of 21 real pairs vs 21 of 420 placebo pairs.
The largest real δs come from games with few price changes (baseline_020: 1.04, baseline_003: 0.90,
baseline_011: 0.86), i.e. a firm that moved once, onto its rival's price.

## 3. Price levels per game (`price_levels_per_game.csv`)

Δ over the last 50 periods (0 = Nash 1.473, 1 = monopoly 1.925):

| | Median Δ | Range | Games above monopoly (Δ > 1) | Games where both firms held one price in the last 50 periods |
|---|---|---|---|---|
| Baseline (21) | 0.37 | −0.09 to 1.11 | 1 | 8 |
| Instructed (6) | 1.60 | 1.09 to 2.27 | 6 | 6 |

Instructed games froze at prices (firm 0 / firm 1): 2.09/1.84, 2.20/2.00, 2.24/2.45, 2.34/2.24, 1.89/2.19, 2.50/2.50.
All six are **above the monopoly price**, so they earn less than a monopolist would: "keep prices high"
overshoots. The price ceiling shown to agents is 2.89.

## 4. Impulse response (`../impulse/per_game.csv`, `counts.csv`, `by_period.csv`, `fig5_impulse_response.png`)

Every game forked at period 200; firm 0 forced to the Nash price in period 201; forced and fresh control
branches run to period 220. 54 branches, 2,162 calls (2 parse retries, 0 failures), cost $2.98.
The restored state reproduced each game's logged period-201 prompt exactly.
D(t) = firm 1's forced-branch price minus control-branch price.

| | Games | Responded (D < −0.01 in 202–204) | Punishment-like | · deeper than myopic | · stays cut after firm 0 is back | Returned (|D(220)| ≤ 0.01) | Returned among responders | Firm 0 back within 0.01 of its p200 price |
|---|---|---|---|---|---|---|---|---|
| Baseline | 21 | 12 | 12 | 11 | 5 | 7 | **0 of 12** | 15 (8 still there at 220) |
| Instructed | 6 | 3 | 1 | 1 | 1 | 3 | **0 of 3** | 4 (3 still there at 220) |

Mean dBR (myopic best-response cut): baseline −0.091, instructed −0.260.
Mean D(t), baseline: −0.07 at 202, −0.10 at 204, −0.10 at 220 (SE ≈ 0.03). Instructed: −0.16 throughout (SE ≈ 0.08).
Firm 0's own forced-minus-control price stays near −0.19 (baseline) and −0.26 (instructed) to period 220.

Reading:
- No game shows the reward–punishment signature of a cut followed by a return: no responder returned within 19 periods.
- After the forced cut, firm 0 itself often stays low (its own history now shows 1.47 earning more),
  and firm 1 follows it down and stays there. A new, lower price level persists.
- "Deeper than myopic" mostly reflects firm 1 starting above its best response. dBR measures the change
  in the best response, but in 10 of the 12 "deeper" games firm 1 priced above BR(p0) in period 200
  (19 of 27 games overall), and its cut was no deeper than one jump straight to BR(1.47). Only
  baseline_004 (−0.26 vs a full myopic jump of −0.19) and baseline_007 (−0.14 vs −0.08) cut deeper than that.
  (Check: `../impulse/per_game.csv` plus each game's period-200 prices.)
- The cut is no shock at all where firm 0 already priced near 1.47 in period 200 (baseline_001, 009, 011
  at 1.46–1.48). Those games count as "not responded" by construction.
- Instructed games respond less often (3/6) than baseline (12/21), despite the larger myopic incentive to cut.
