# Passing the Placebo Is Not Enough: Testing LLM Pricing-Collusion Detectors Against Known Strategies

Can the standard reaction test for LLM pricing collusion (Fish et al.'s δ, which asks whether a seller
follows its competitor's last price) tell collusion from competition? We test the detectors in two ways.
First against a **placebo null**: sellers from *different* games, who never saw each other, paired
artificially, so anything a test flags there cannot be reaction. Then against **rule-based agents with
known strategies**, a competitor that follows its rival and a colluder that punishes undercuts and then
returns. A **hold-back intervention** completes the set: one seller undercuts for a single period while
the other is the only LLM, to see whether it punishes and returns.

The setup is Fish, Gonczarowski & Shorrer's duopoly (*Algorithmic Collusion by Large Language Models*,
arXiv 2404.00806) with a different model (`claude-haiku-5-5`, thinking disabled, temperature 1) and two
deliberate changes so placebo pairs share one market: α = 1 and a fixed price ceiling of 1.5 × the
monopoly price in every game. Built for the Apart Research AI Collusion Research Sprint (Oct 23–25 2026),
research questions 1.3 and 2.3.

## Main findings

Games: 21 baseline (Fish et al.'s prompt P1), 6 instructed (P1 + "coordinate to keep prices high"),
10 strategy-instructed (P1 + an explicit punish-then-return rule), 300 periods each.

1. **Fish δ beats the placebo, but the signal is fragile.** Pooled δ = 0.086 vs a placebo mean of 0.005
   (p = 0.001, 1,000 re-pairings). But it rests on a few games: the largest per-game δs come from firms
   that moved once, onto their rival's price. It is not significant with standard errors clustered by
   game (SE 0.103), and in the 4 games where both firms change price at least 10 times it fails the
   placebo (p = 0.79).
2. **δ measures following, not collusion.** It flags a rule-based competitor that just follows its rival
   (δ = 0.149, p = 0.001) and misses our rule-based colluder at every punishment length (p = 0.85–1.00;
   only the punishment length was varied). It does detect the LLM colluder (δ = 0.465), but that rests
   almost entirely on one game, strategy_instructed_008, the only strategy-instructed game where both
   firms keep moving.
3. **Haiku sellers freeze.** After period 100 a typical firm changes price in about 4% of periods, and
   δ can't be estimated in any of the 6 instructed games. Re-paired among themselves, instructed sellers
   keep their high prices (price-level AUROC 0.48, real vs re-paired). Those prices come from each
   seller's own instruction, so the instructed games are not a positive control for reaction tests.
4. **The hold-back fork separates the rule-based follower from punishers, given a long enough window.**
   Punish-and-return: 2 of 21 baseline games (one of them baseline_008, which has large branch noise) vs
   4 of 10 strategy-instructed games (Fisher exact p = 0.07). Of the 12 games still lower at period 220,
   10 never return by period 260, including 3 that were told to return. Only 6 of 10 strategy-instructed
   sellers comply with their instructed punish-then-return rule.
5. **Exploratory, added last: the partner price gap.** Real baseline partners end 0.094 apart on average
   vs 0.204 when re-paired (p = 0.001, mean-gap test). It works on frozen games where δ can't, but it
   can't show how a common price is sustained.

Full numbers: [`results/real/SUMMARY.md`](results/real/SUMMARY.md) (placebo tests, impulse response,
gap test) and [`results/followup/SUMMARY.md`](results/followup/SUMMARY.md) (hold-back forks, synthetic
agents, strategy-instructed games). The analysis plan is in [`CLAUDE.md`](CLAUDE.md). It was committed
before the first run and amended twice before any test; each follow-up was committed before it ran; the
tremble calibration of the noisy synthetic agents was redone on a larger sample; the partner gap was
added last and is exploratory. The git history records when each step was fixed.

## Report

The submitted report is [`report/placebo-collusion-report.pdf`](report/placebo-collusion-report.pdf).

## Layout

```
CLAUDE.md                  analysis plan: committed before the first run, amended before any test, with each follow-up added before it ran (dated)
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
