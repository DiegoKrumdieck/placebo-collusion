"""Impulse-response forks against a scripted fake client. No API calls, never touches data/runs."""

import csv
import itertools
import json
import re
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import impulse  # noqa: E402
from run import parse_args, run_game  # noqa: E402


class FollowerClient:
    """Copies the competitor's most recent price (1.80 with no history). Notes carry a unique call id."""

    def __init__(self):
        self.lock = threading.Lock()
        self.ids = itertools.count(1)
        self.messages = self

    def create(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        with self.lock:
            k = next(self.ids)
        m = re.search(r"Competitor's price: (\S+)", prompt)  # newest round comes first
        price = m.group(1) if m else "1.80"
        text = (f"My observations and thoughts:\nx\n\nNew content for PLANS.txt:\nPLAN-{k}\n\n"
                f"New content for INSIGHTS.txt:\nINSIGHT-{k}\n\nMy chosen price:\n{price}")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))


def read_llm(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


@pytest.fixture(scope="module")
def forked(tmp_path_factory):
    root = tmp_path_factory.mktemp("impulse")
    runs, forks = root / "runs", root / "forks"
    args = parse_args(["--condition", "baseline", "--model", "fake", "--periods", "205", "--run-id", "g1"])
    run_game(args, FollowerClient(), runs)
    for branch in impulse.BRANCHES:
        impulse.run_fork("baseline", "g1", branch, FollowerClient(), runs, forks)
    return runs, forks


def test_restored_state_reproduces_logged_prompt(forked):
    runs, forks = forked
    original = {r["firm"]: r for r in read_llm(runs / "baseline" / "g1" / "llm.jsonl") if r["period"] == 201}
    for branch in impulse.BRANCHES:
        fork = {r["firm"]: r for r in read_llm(forks / "baseline" / "g1" / branch / "llm.jsonl") if r["period"] == 201}
        for firm in (0, 1):
            assert fork[firm]["prompt"] == original[firm]["prompt"]


def test_forced_branch_sets_nash_and_keeps_notes(forked):
    _, forks = forked
    recs = read_llm(forks / "baseline" / "g1" / "forced" / "llm.jsonl")
    r201 = {r["firm"]: r for r in recs if r["period"] == 201}
    assert r201[0]["forced"] and r201[0]["price_used"] == pytest.approx(1.4729, abs=1e-3)
    assert r201[0]["chosen_price"] == 1.8 and not r201[1]["forced"]
    r202 = {r["firm"]: r for r in recs if r["period"] == 202}
    # Firm 0's own notes from its period-201 call are kept.
    assert r201[0]["parsed"]["plans"] in r202[0]["prompt"]
    # Firm 0 sees its forced price as its own; firm 1 sees it as the competitor's.
    assert "Round 201:\n- My price: 1.47\n" in r202[0]["prompt"]
    assert "Round 201:\n- My price: 1.8\n- Competitor's price: 1.47\n" in r202[1]["prompt"]
    with open(forks / "baseline" / "g1" / "control" / "periods.csv", newline="", encoding="utf-8") as fh:
        assert not any(r["forced"] == "True" for r in csv.DictReader(fh))


def test_follower_categories(forked):
    """The copier: firm 1 copies firm 0's 1.47 in 202; firm 0 copies firm 1's 1.80 back in 202; they then alternate."""
    runs, forks = forked
    res = impulse.summarize(forks, runs)
    g = res["per_game"].iloc[0]
    assert g.p0_period200 == 1.8
    assert g.responded and g.min_D_202_204 == pytest.approx(1.47 - 1.8, abs=1e-6)
    assert g.firm0_back and g.firm0_back_period == 202
    assert not g.stays_cut_after_firm0_back  # firm 1 copies 1.80 again in 203
    assert g.dBR < 0 and g.deeper_than_myopic == (0.33 > abs(g.dBR)) and g.punishment_like == g.deeper_than_myopic
    assert not g.returned  # alternation: firm 1 is at 1.47 in even periods, including 220
    by = res["by_period"].set_index("period")
    assert by.loc[202, "D_firm1_mean"] == pytest.approx(1.47 - 1.8, abs=1e-6)
    c = res["counts"].iloc[0]
    assert (c.n_games, c.responded, c.returned_among_responded) == (1, 1, 0)


def test_best_response_benchmark():
    from market import Market
    m = Market()
    br_nash = impulse.best_response(m.nash_price, m)
    assert br_nash == pytest.approx(m.nash_price, abs=1e-4)  # Nash is a mutual best response
    assert impulse.best_response(1.47, m) < impulse.best_response(1.80, m)  # strategic complements


def test_stays_cut_clause():
    import pandas as pd
    t = range(201, 221)
    fo = pd.DataFrame({0: [1.47] + [1.80] * 19, 1: [1.80, 1.60, 1.60, 1.60, 1.60] + [1.80] * 15}, index=t)
    co = pd.DataFrame({0: [1.80] * 20, 1: [1.80] * 20}, index=t)
    g = impulse.classify(fo, co, p0_200=1.80, dbr=-0.5)  # cut of 0.2 is shallower than |dBR|
    assert g["responded"] and not g["deeper_than_myopic"]
    assert g["firm0_back_period"] == 202 and g["stays_cut_after_firm0_back"] and g["punishment_like"]
    assert g["returned"]


def test_forks_refuse_while_batch_runs(tmp_path):
    args = parse_args(["--condition", "baseline", "--model", "fake", "--periods", "3", "--run-id", "short"])
    run_game(args, FollowerClient(), tmp_path)
    (tmp_path / "instructed").mkdir()
    with pytest.raises(SystemExit, match="Batch not finished"):
        impulse.finished_games(tmp_path)
