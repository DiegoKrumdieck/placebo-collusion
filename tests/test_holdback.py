"""Hold-back fork against a scripted fake client. No API calls, never touches data/runs."""

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import holdback  # noqa: E402
from run import parse_args, run_game  # noqa: E402
from test_impulse import FollowerClient  # noqa: E402


class CountingFollower(FollowerClient):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return super().create(**kwargs)


@pytest.fixture(scope="module")
def held(tmp_path_factory):
    root = tmp_path_factory.mktemp("holdback")
    runs, out = root / "runs", root / "holdback"
    run_game(parse_args(["--condition", "baseline", "--model", "fake", "--periods", "205", "--run-id", "g1"]),
             FollowerClient(), runs)
    clients = {}
    for branch in holdback.BRANCHES:
        clients[branch] = CountingFollower()
        holdback.run_holdback("baseline", "g1", branch, clients[branch], runs, out, verbose=False)
    return runs, out, clients


def prices(out, branch):
    with open(out / "baseline" / "g1" / branch / "periods.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {(int(r["period"]), int(r["firm"])): float(r["price"]) for r in rows}


def test_firm0_is_exogenous_and_firm1_is_the_only_call(held):
    _, out, clients = held
    for branch in holdback.BRANCHES:
        assert clients[branch].calls == 20  # one call per period, firm 1 only
        p = prices(out, branch)
        expected = [holdback.FORCED_PRICE if branch == "forced" and t == 201 else 1.8 for t in range(201, 221)]
        assert [p[(t, 0)] for t in range(201, 221)] == expected


def test_follower_copies_the_one_period_cut(held):
    _, out, _ = held
    f, c = prices(out, "forced"), prices(out, "control")
    D = {t: f[(t, 1)] - c[(t, 1)] for t in range(202, 221)}
    assert D[202] == pytest.approx(1.47 - 1.8)  # copies the cut once...
    assert all(abs(D[t]) < 1e-9 for t in range(203, 221))  # ...then copies 1.80 again


def test_restored_firm1_prompt_matches_log(held):
    runs, out, _ = held
    original = [json.loads(l) for l in open(runs / "baseline" / "g1" / "llm.jsonl", encoding="utf-8")]
    orig201 = next(r for r in original if r["period"] == 201 and r["firm"] == 1)
    for branch in holdback.BRANCHES:
        recs = [json.loads(l) for l in open(out / "baseline" / "g1" / branch / "llm.jsonl", encoding="utf-8")]
        assert recs[0]["period"] == 201 and recs[0]["prompt"] == orig201["prompt"]
        assert all(r["firm"] == 1 for r in recs)


def test_classification_rules():
    from holdback_rules import classify
    flat = {t: 0.0 for t in range(202, 221)}
    assert classify(flat)["category"] == "no reaction"
    assert classify({**flat, 202: -0.33})["category"] == "matching"
    punish = {**flat, **{t: -0.1 for t in range(202, 210)}}
    assert classify(punish)["category"] == "punish-and-return" and classify(punish)["periods_below"] == 8
    assert classify({**flat, **{t: -0.1 for t in range(205, 221)}})["category"] == "persistent"
    assert classify({**flat, 206: -0.05, 207: -0.05})["category"] == "other"
    assert classify({**flat, 202: 1.79 - 1.80})["category"] == "no reaction"  # float noise rounds to -0.01


def test_spend_counter(held, monkeypatch):
    _, out, _ = held
    for branch in holdback.BRANCHES:
        cfg = out / "baseline" / "g1" / branch / "config.json"
        cfg.write_text(json.dumps(dict(json.loads(cfg.read_text()), model="claude-haiku-5-5")))
    # FollowerClient reports 1 input + 1 output token per call: 20 calls per branch.
    assert holdback.spent_usd(out) == pytest.approx(20 * len(holdback.BRANCHES) * (0.10 + 0.50) / 1e6)


def test_control2_matches_control_for_a_deterministic_agent(held):
    _, out, _ = held
    assert prices(out, "control2") == prices(out, "control")
