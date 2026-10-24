# Cross-game diagnostic, real runs (2026-10-23)

Run after all 27 games finished (21 baseline + 6 instructed, 300 periods each; batch ended 21:49 EDT,
0 failed games, 0 parse failures in 16,200 price decisions, 0 API errors). Nothing else has been
computed on the real runs. Source files: `diagnostic_correlations.csv`, `diagnostic_cross_pairs.csv`,
`diagnostic_within.csv`, `price_changes.csv`, `diagnostic_summary.json`, `fig4_cross_game.png`.

## Cross-game correlation of first differences, periods 101–300 (baseline)

| Comparison | Pairs defined | Mean | 5th–95th pct | Share outside ±0.14 |
|---|---|---|---|---|
| Firm 0 across games | 190 of 210 (20 undefined: baseline_006 firm 0 never changes) | 0.001 | −0.071 to 0.055 | 3.2% |
| Firm 1 across games | 210 of 210 | −0.001 | −0.072 to 0.078 | 4.8% |
| Within game, firm 0 vs firm 1 (reference) | 20 of 21 | −0.055 | −0.350 to 0.172 | 40% |

±0.14 is the 95% range for two independent series of this length; about 5% of pairs fall outside it by chance.

## Price changes in periods 101–300

| | Median changes per firm (of 200 periods) | Firms with ≥ 10 changes | Games with both firms ≥ 10 |
|---|---|---|---|
| Baseline | firm 0: 8, firm 1: 10 | 17 of 42 (40%) | 4 of 21 (baseline_002, 005, 008, 014) |
| Instructed | firm 0: 1, firm 1: 0 | 0 of 12 | 0 of 6 |

Median share of periods in which a baseline firm changes price: 4%. Instructed games change price
at most 4 times in 200 periods; three of them never change at all after period 100.

## Reading (per CLAUDE.md's pre-registered rules)

- **Games are independent in their moves.** Cross-game correlation of first differences is centered
  on 0 and falls outside the noise band no more often than chance. The placebo is informative:
  if placebo δ comes out as large as real δ, near-copy games are not the explanation.
- **But there is little movement to work with.** Baseline firms change price in about 4% of periods
  101–300, and only 4 of 21 games pass the 10-change cutoff for both firms. On-path tests will rest
  on few price changes.
- **Instructed games are frozen.** No instructed firm passes the cutoff. Per the frozen-game rule,
  δ has essentially no power against them, and that is a result: the standard on-path test cannot
  detect even explicit coordination once agents lock in. The impulse response is the test that can.
