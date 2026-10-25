# Placebo calibration of LLM pricing-collusion tests

Two LLM pricing agents built on the same model can move their prices together without reacting to each
other: they share priors and follow similar paths (start high, come down, settle). Standard collusion
tests may read that shared path as reaction to the competitor.

This project builds a **placebo null**: take sellers from *different* games, who never saw each other,
pair them artificially, and run every test on these fake markets. Anything a test flags there cannot be
reaction. A test's result counts as evidence only if it beats the placebo.

The setup is Fish, Gonczarowski & Shorrer's duopoly (*Algorithmic Collusion by Large Language Models*,
arXiv 2404.00806) with a different model (`claude-haiku-5-5`, thinking disabled, temperature 1) and two
deliberate changes so placebo pairs share one market: α = 1 and a fixed price ceiling of 1.5 × the
monopoly price in every game. Built for the Apart Research AI Collusion Research Sprint (Oct 23–25 2026),
research questions 1.3 and 2.3.

## Main findings

Games: 21 baseline (Fish et al.'s prompt P1), 6 instructed (P1 + "coordinate to keep prices high"),
10 strategy-instructed (P1 + an explicit punish-then-return rule), 300 periods each.

- **Fish δ beats the placebo on Haiku baseline games**: pooled δ = 0.086 vs a placebo mean of 0.005
  (p = 0.001, 1,000 re-pairings). Naive δ (all periods, no fixed effects) does too (0.033 vs 0.003).
  But the signal comes from games that barely move: restricted to the 4 games where both firms change
  price at least 10 times, Fish δ does not beat the placebo (p = 0.79).
- **δ measures reaction, not collusion.** On synthetic agents with a known answer, it flags a myopic
  competitor that just follows its rival (p = 0.001) and misses a reward–punishment colluder at every
  punishment length (p ≥ 0.85).
- **Games freeze.** After period 100 a baseline firm changes price in ~4% of periods. All 6 instructed
  games freeze above the monopoly price, where δ can't be estimated at all: the on-path test has no
  power against explicit coordination once agents lock in. The price level flags all 6, but it doesn't
  separate real from placebo baseline pairs (AUROC 0.49).
- **The partner price gap works where δ can't**: real partners end within one cent of each other in
  11/21 baseline and 8/10 strategy-instructed games, vs fewer than 1 expected under re-pairing
  (p = 0.001 in both).
- **Hold-back forks** (firm 0 undercuts for one period, firm 1 is the only LLM): Haiku baseline firms
  rarely punish and return (1/21). Instead 8 of 27 baseline and instructed games drop to a lower price
  and stay there. Of the 12 such games (with 4 strategy-instructed ones), 10 are still down 59 periods
  later. Even LLMs told to punish for 5 periods and then return often don't (compliant 6/10).

Full numbers: [`results/real/SUMMARY.md`](results/real/SUMMARY.md) (placebo tests, impulse response,
gap test) and [`results/followup/SUMMARY.md`](results/followup/SUMMARY.md) (hold-back forks, synthetic
agents, strategy-instructed games). The analysis plan, pre-registered step by step before each
experiment, is in [`CLAUDE.md`](CLAUDE.md); the git history records when each step was fixed.

## Report

The submitted report is [`report/placebo-collusion-report.pdf`](report/placebo-collusion-report.pdf).

## Layout

```
CLAUDE.md                  pre-registered design and analysis plan (with amendments, dated)
prompts/fish_appendix_g.md Fish et al. prompts, transcribed from arXiv 2404.00806v6 Appendix G
src/
  market.py                thin wrapper over the EconEvals logit duopoly
  agent.py, run.py         Fish-format agent (one call per period) and one-game runner
  launch_batch.py          runs the batch of games in parallel, resumable, optional cost cap
  impulse.py               first impulse-response fork (both firms LLM)
  holdback.py              hold-back fork (firm 0 exogenous, firm 1 only LLM), cost cap
  pairs.py, detectors.py   real/placebo pairs; Δ, correlations, Fish δ, naive δ
  stats.py, diagnostics.py re-pairing null, AUROC, thresholds; cross-game diagnostic
  synthetic*.py            known-answer synthetic agents
  holdback_rules.py        committed hold-back classification rules
  analyze.py, followup.py  analysis entry points (no API calls)
  figures.py, fig_holdback_grid.py, report_tables.py
  export_prices.py         writes results/prices.csv
  reproduce.py             runs every analysis step in order (no API calls)
tests/                     pytest suite (synthetic data, no API calls)
results/                   every table and figure in the report, plus prices.csv
report/                    the submitted report (PDF)
data/                      raw logs, not in git: download from the release (below)
vendor/                    EconEvals, not in git: clone it (below)
```

## Data

`data/` (~560 MB unpacked, 28 MB compressed) is not in git. It is attached to the
[v1.0-sprint release](https://github.com/DiegoKrumdieck/placebo-collusion/releases/tag/v1.0-sprint) as
`placebo-collusion-data-v1.0.tar.gz` (SHA-256 `299b55d1cbbaf735fd4f56ab19c5ca82813fe930e60f916b6c6c0e710f34e42b`).

```
data/runs/<condition>/<run_id>/       the 37 games: config.json, periods.csv, llm.jsonl (every prompt and reply)
data/forks/<condition>/<run_id>/      first impulse-response fork: forced/ and control/ branches
data/holdback/<condition>/<run_id>/   hold-back fork: forced/, control/, control2/ (extended to 260 for 12 games)
data/smoke/                           20-period smoke test, never used in the analysis
```

Unpack it in the repository root, so that `data/runs/baseline/...` exists (works on Linux, macOS and
Windows 10+):

```bash
tar -xzf placebo-collusion-data-v1.0.tar.gz
```

To look at price paths without the archive, use [`results/prices.csv`](results/prices.csv): one row
per game, branch, period and firm (`run_id, condition, branch, period, firm, price`). `branch` is
`game` for the 300-period games, `impulse_forced`/`impulse_control` for the first fork and
`holdback_forced`/`holdback_control`/`holdback_control2` for the hold-back fork.

## Reproduce

Python 3.12 (tested with 3.12.1).

```bash
git clone https://github.com/DiegoKrumdieck/placebo-collusion.git
cd placebo-collusion
python -m venv .venv
```

Activate the venv (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` elsewhere), then:

```bash
pip install -r requirements.txt
```

**EconEvals** (market code only) goes in `vendor/` at the exact commit used,
`e1f2a40fec96f0d27f5414873c4310f2b5c51935`:

```bash
git clone https://github.com/sara-fish/econ-evals-paper vendor/econ-evals-paper
```

```bash
git -C vendor/econ-evals-paper checkout e1f2a40fec96f0d27f5414873c4310f2b5c51935
```

```bash
pip install -e vendor/econ-evals-paper
```

(`setuptools` is in `requirements.txt` because EconEvals' `setup.py` imports `distutils`, which
Python 3.12 removed.)

### Regenerate all results and figures from the logs (no API calls)

Unpack the data archive first (see Data), then:

```bash
python src/reproduce.py
```

It runs the 16 analysis steps in order (`python src/reproduce.py --list` prints them) and rewrites
`results/`. Every step is seeded, so afterwards `git status results/` should show no changes. Then
`python src/export_prices.py` rebuilds `results/prices.csv`. Tests: `python -m pytest`.

### Rerun the experiments (API calls, costs real money)

Set your Anthropic key in the environment as `ANTHROPIC_API_KEY`, or in a `.env` file in the repo root
(`ANTHROPIC_API_KEY=...`; `.env` is git-ignored). Each command resumes from where it stopped. Commands in
order, with what they cost us:

| Experiment | Command | Calls | Cost |
|---|---|---|---|
| Smoke test (20 periods) | `python src/run.py --condition baseline --model claude-haiku-5-5 --periods 20 --run-id smoke_001` | 40 | $0.04 |
| Main batch: 21 baseline + 6 instructed games | `python src/launch_batch.py --model claude-haiku-5-5 --baseline 21 --instructed 6 --concurrency 9` | 16,209 | $20.93 |
| First impulse-response fork | `python src/impulse.py launch --concurrency 9` | 2,162 | $2.98 |
| Hold-back fork | `python src/holdback.py launch --concurrency 9` | 1,080 | $1.47 |
| Control-vs-control fork | `python src/holdback.py launch --branches control2 --cap 3` | 540 | $0.73 |
| 10 strategy-instructed games | `python src/launch_batch.py --model claude-haiku-5-5 --baseline 0 --instructed 0 --strategy-instructed 10 --concurrency 10 --cost-cap 8.40` | 6,005 | $6.93 |
| Their hold-back fork | `python src/holdback.py launch --conditions strategy_instructed --expected 10 --concurrency 10 --cap 2.06` | 400 | $0.51 |
| Hold-back extended to period 260 (12 games) | see below | 960 | $1.25 |
| **Total** | | | **~$34.8** |

The smoke test writes to `data/runs/`; move it to `data/smoke/` afterwards so the analysis never pairs it
with the batch. The extension command:

```bash
python src/holdback.py launch --conditions baseline instructed strategy_instructed --expected 12 --last-period 260 --concurrency 12 --cap 3 --only baseline/baseline_002 baseline/baseline_005 baseline/baseline_008 baseline/baseline_013 baseline/baseline_014 baseline/baseline_020 instructed/instructed_002 instructed/instructed_003 strategy_instructed/strategy_instructed_001 strategy_instructed/strategy_instructed_002 strategy_instructed/strategy_instructed_009 strategy_instructed/strategy_instructed_010
```

The launchers log every start and finish to `launcher.log` in each data folder. The flags in the last
three hold-back rows are reconstructed from those logs and the launcher code.

LLM sampling isn't deterministic, so reruns give new games. The analysis of new games uses the same
commands as above.

## License

MIT, see [`LICENSE`](LICENSE). The market code comes from
[EconEvals](https://github.com/sara-fish/econ-evals-paper) by Fish et al., which is MIT-licensed and
**not included** in this repository; clone it into `vendor/` as above. The prompts in
`prompts/fish_appendix_g.md` are transcribed from Fish, Gonczarowski & Shorrer (arXiv 2404.00806v6),
Appendix G.
