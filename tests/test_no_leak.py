"""The two firms are queried in parallel. Check that no prompt leaks current-period information.

A fake client stands in for the API. Each call gets a unique price and unique plan/insight markers,
and sleeps a random time so the two firms' calls overlap and finish in random order. We then check
every logged prompt against what each firm had actually done by then.
"""

import itertools
import json
import random
import re
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agent import HISTORY_WINDOW, fmt_num  # noqa: E402
from run import parse_args, run_game  # noqa: E402

PERIODS = 110  # past the 100-period history window


class FakeClient:
    def __init__(self):
        self.lock = threading.Lock()
        self.counter = itertools.count(1)
        self.received = []  # (prompt, call id, start, end)
        self.messages = self

    def create(self, **kwargs):
        start = time.perf_counter()
        prompt = kwargs["messages"][0]["content"]
        with self.lock:
            k = next(self.counter)
        time.sleep(random.uniform(0.0, 0.02))
        price = round(1 + 0.01 * k, 2)  # unique to this call
        text = (
            "My observations and thoughts:\nfake\n\n"
            f"New content for PLANS.txt:\nPLANTOKEN-{k}-END\n\n"
            f"New content for INSIGHTS.txt:\nINSIGHTTOKEN-{k}-END\n\n"
            f"My chosen price:\n{price}"
        )
        with self.lock:
            self.received.append((prompt, k, start, time.perf_counter()))
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )


def parse_rounds(prompt: str) -> dict[int, tuple[str, str]]:
    market = prompt.split("Filename: MARKET_DATA (read-only)")[1].split("Now you have all")[0]
    rounds = re.findall(r"Round (\d+):\n- My price: (\S+)\n- Competitor's price: (\S+)\n", market)
    return {int(r): (mine, comp) for r, mine, comp in rounds}


def test_parallel_prompts_do_not_leak(tmp_path):
    random.seed(0)
    client = FakeClient()
    args = parse_args(["--condition", "baseline", "--model", "fake", "--periods", str(PERIODS), "--run-id", "leaktest"])
    run_game(args, client, tmp_path)

    logged = [json.loads(l) for l in open(tmp_path / "baseline" / "leaktest" / "llm.jsonl", encoding="utf-8")]
    assert len(logged) == 2 * PERIODS

    # The prompts the client received are exactly the logged prompts.
    assert sorted(p for p, *_ in client.received) == sorted(r["prompt"] for r in logged)

    price = {(r["period"], r["firm"]): r["price_used"] for r in logged}
    price_to_call = {round(1 + 0.01 * k, 2): k for _, k, *_ in client.received}
    call = {key: price_to_call[p] for key, p in price.items()}

    for r in logged:
        t, f, prompt = r["period"], r["firm"], r["prompt"]
        rounds = parse_rounds(prompt)

        # 1. History covers exactly periods max(1, t-100) .. t-1. Nothing from period t.
        assert set(rounds) == set(range(max(1, t - HISTORY_WINDOW), t)), (t, f)

        # 2. Each round shows this firm's own price as "My price" and the rival's as "Competitor's price".
        for s, (mine, comp) in rounds.items():
            assert mine == fmt_num(price[(s, f)]) and comp == fmt_num(price[(s, 1 - f)]), (t, f, s)

        # 3. Neither firm's period-t price appears on any price line.
        price_values = set(re.findall(r"price: (\S+)", prompt))
        for g in (0, 1):
            assert fmt_num(price[(t, g)]) not in price_values, (t, f, g)

        # 4. Plans and insights are this firm's own, from period t-1. Never the rival's, never period t's.
        if t > 1:
            own = call[(t - 1, f)]
            assert f"PLANTOKEN-{own}-END" in prompt and f"INSIGHTTOKEN-{own}-END" in prompt, (t, f)
        foreign = [call[(t - 1, 1 - f)]] if t > 1 else []
        foreign += [call[(t, 0)], call[(t, 1)]]
        for k in foreign:
            assert f"PLANTOKEN-{k}-END" not in prompt and f"INSIGHTTOKEN-{k}-END" not in prompt, (t, f, k)

    # The test actually exercised the parallel path: the two firms' calls overlapped in time.
    spans = {k: (s, e) for _, k, s, e in client.received}
    overlaps = sum(
        1 for t in range(1, PERIODS + 1)
        if max(spans[call[(t, 0)]][0], spans[call[(t, 1)]][0]) < min(spans[call[(t, 0)]][1], spans[call[(t, 1)]][1])
    )
    assert overlaps >= 0.9 * PERIODS, overlaps
