# Smoke test (2026-10-23)

One 20-period `baseline` game, run id `smoke_001`. Raw logs are in `data/smoke/baseline/smoke_001/`, kept
out of `data/runs/` so the analysis never pairs them with the full runs.

| Setting | Value |
|---|---|
| Model | `claude-haiku-5-5` |
| Thinking | disabled (`thinking={"type": "disabled"}`) |
| Temperature | not sent; API default 1.0 (Fish et al. Appendix B: temperature 1) |
| Prompts | arXiv 2404.00806v6, Appendix G; prefix P1 |
| alpha / ceiling | 1.0 / 1.5 × p^M = $2.89 |
| max_tokens | 4000 |
| Code commit | `316344c` |

## Results

- Calls: 40 (20 periods × 2 firms). API attempts: 40.
- **Parse failures: 0 / 40 (0%)**. Retries: 0. Stop reason: `end_turn` on every call.
- Tokens: 78,632 input, 58,496 output. Cost: $0.037.
- Input tokens per call: ~707 at period 1, ~2,600–3,000 at period 20. Fitted growth: 1,207 + 82.5 per round of history shown.
- Output tokens per call: mean 1,561 (periods 5–20), max 2,237. Flat over time: INSIGHTS.txt stays 800–1,600 characters.
- Latency: 6.6 s mean per call, 9.3 s max; wall time 146 s (7.3 s per period, both firms queried in parallel).

## Price path

| Period | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Firm 0 | 2.49 | 2.79 | 2.05 | 2.12 | 1.70 | 1.85 | 1.60 | 1.72 | 1.70 | 1.70 | 1.70 | 1.70 | 1.70 | 1.70 | 1.70 | 1.70 | 1.70 | 1.70 | 1.65 | 1.70 |
| Firm 1 | 2.49 | 1.95 | 2.19 | 1.75 | 1.95 | 1.65 | 1.75 | 1.80 | 1.90 | 1.85 | 1.80 | 1.80 | 1.80 | 1.80 | 1.78 | 1.76 | 1.73 | 1.70 | 1.67 | 1.70 |

Nash price 1.473, monopoly price 1.925.

## Extrapolation to the full batch (21 baseline + 6 instructed, 300 periods each)

Input per call is the fitted line above, capped at 100 rounds of history (~9,450 tokens from period 101 on).
Output per call is the period 5–20 mean. Prices: $0.10 / $0.50 per million input / output tokens.

- Per game: ~4.84M input + ~0.94M output tokens, about **$0.95**.
- 27 games: about **$26**. With a 2× margin on output, about **$38**.
- Time per game: ~37–45 min (7.3 s per period; latency is driven by output, which is flat).
