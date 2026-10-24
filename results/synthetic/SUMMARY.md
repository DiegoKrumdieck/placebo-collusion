# Synthetic validation of the analysis pipeline (2026-10-23)

Synthetic price paths only; no real runs were read. 21 "baseline" and 6 "instructed" games per
scenario, 300 periods, prices rounded to cents. 1,000 random re-pairings (derangements) per test;
AUROC CIs from 500 run-level bootstrap draws. Full numbers: `validation.csv`, `diagnostic.csv`.
Figures for three scenarios: `figures/<scenario>/`. Tests: `tests/test_analysis_synthetic.py` (16 pass with the impulse and leak tests).

## Known-answer checks (Fish delta unless noted; "all games" version)

| Scenario | What's built in | Real pooled | Placebo mean / 95th pct | p | AUROC real vs placebo | Instructed power |
|---|---|---|---|---|---|---|
| independent | no reaction | 0.009 | 0.006 / 0.035 | 0.43 | 0.52 | 6/6 (instructed = follower) |
| follower | both firms copy rival's last price, delta = 0.8 | 0.794 | 0.014 / 0.055 | 0.001 | 1.00 | 6/6 |
| leader_follower | only firm 1 copies, pooled delta ≈ 0.4 | (baseline independent) 0.009 | 0.006 / 0.035 | 0.43 | 0.52 | instructed delta 0.378, 6/6 |
| shared_trajectory, **naive delta** | same climb-then-settle path, no reaction | 0.173 | 0.175 / 0.187 | 0.63 | 0.48 | — |
| shared_trajectory, Fish delta | same | 0.024 | 0.014 / 0.040 | 0.26 | 0.55 | — |
| near_copies | reaction (0.8) but every game makes nearly the same moves | 0.797 | 0.770 / 0.772 | 0.001 | 0.73 | — |
| mostly_frozen | 70% of games lock in after period 100–150 | 0.717 | 0.004 / 0.051 | 0.001 | 0.91 | 5/6 |
| all_frozen | every game frozen before period 100 | not identified (21/21) | not identified | — | 0.50 | 0/6 |

Cross-game diagnostic (mean correlation of first differences, periods 101–300, firm 0 across games):
independent −0.00, follower 0.00, shared_trajectory −0.01, **near_copies 0.97**, mostly_frozen −0.00,
all_frozen undefined (210/210 frozen pairs). Independence band ±0.14.

## What this shows

- The placebo catches shared trajectory: naive delta is 0.17 in real pairs, but placebo pairs give the same 0.17.
- Fish's spec (periods 101–300, fixed effects) is not fooled by that trajectory.
- The diagnostic flags near-copies (0.97). There placebo delta ≈ real delta despite real reaction, so
  outcome 2 must not be read as "no reaction".
- Frozen games: no crashes. Unidentified per-pair scores count as 0 and are reported. With everything
  frozen, delta is not identified and has zero power against frozen instructed games.
- The pooled price level (collusion index) is identical for real and every re-pairing by construction
  (re-pairing reuses the same price paths), so the placebo can never reject on level.
- Contemporaneous correlation of first differences is negative under mutual copying (prices oscillate),
  so it doesn't detect lagged reaction.
