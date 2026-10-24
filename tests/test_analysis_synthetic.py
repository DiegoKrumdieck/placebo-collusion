"""Analysis pipeline on synthetic data with known answers. Never touches data/runs."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import diagnostics  # noqa: E402
from detectors import fish_design, fish_regression, n_changes, naive_regression, ols_fe  # noqa: E402
from pairs import check_compatible, derangement, placebo_markets, real_markets  # noqa: E402
from stats import evaluate  # noqa: E402
from synthetic import MONOPOLY, NASH, scenario  # noqa: E402

B = 200  # re-pairings per test here (1,000 in the real analysis); smallest p-value = 1/201


@pytest.fixture(scope="module")
def results():
    out = {}
    for name in ["independent", "follower", "leader_follower", "shared_trajectory", "mostly_frozen", "all_frozen"]:
        base, instr = scenario(name, seed=0)
        s = evaluate(base, instr, NASH, MONOPOLY, B=B, B_boot=100, seed=1)["summary"]
        out[name] = s.set_index(["test", "version"])
    return out


# ---------- construction ----------

def test_fish_design_matches_paper_sample_size():
    base, _ = scenario("independent")
    y, own, comp, group, cluster = fish_design(real_markets(base), (101, 300))
    assert len(y) == 2100  # Table 1: N = 2,100 for 21 runs
    assert (np.bincount(group) == 50).all()  # 100 pairs per run, dependent firm alternates
    m = real_markets(base[:1])[0]
    # First pair (101, 102): firm 0 is "self"; second pair (103, 104): firm 1.
    assert (y[0], own[0], comp[0]) == (m.a[101], m.a[100], m.b[100])
    assert (y[1], own[1], comp[1]) == (m.b[103], m.b[102], m.a[102])
    assert len(fish_design(real_markets(base), (1, 300))[0]) == 21 * 150


def test_fe_ols_matches_statsmodels():
    base, _ = scenario("follower")
    y, own, comp, group, cluster = fish_design(real_markets(base), (101, 300))
    r = ols_fe(y, own, comp, group, cluster)
    dummies = (group[:, None] == np.unique(group)[None, :]).astype(float)
    fit = sm.OLS(y, np.column_stack([own, comp, dummies])).fit(cov_type="HC1")
    assert r.gamma == pytest.approx(fit.params[0], abs=1e-8)
    assert r.delta == pytest.approx(fit.params[1], abs=1e-8)
    assert r.se_delta_hc1 == pytest.approx(fit.bse[1], rel=1e-6)
    fit_cl = sm.OLS(y, np.column_stack([own, comp, dummies])).fit(cov_type="cluster", cov_kwds={"groups": cluster})
    assert r.se_delta_cluster == pytest.approx(fit_cl.bse[1], rel=1e-6)
    # Naive spec = OLS with a single intercept.
    yn, on, cn, gn, cln = fish_design(real_markets(base), (1, 300))
    rn = naive_regression(real_markets(base))
    fitn = sm.OLS(yn, sm.add_constant(np.column_stack([on, cn]))).fit(cov_type="HC1")
    assert rn.delta == pytest.approx(fitn.params[2], abs=1e-8)
    assert rn.se_delta_hc1 == pytest.approx(fitn.bse[2], rel=1e-6)


def test_pairs_and_derangements():
    base, _ = scenario("independent")
    plc = placebo_markets(base)
    assert len(plc) == 21 * 20 and all(m.run_a != m.run_b for m in plc)
    rng = np.random.default_rng(0)
    for _ in range(200):
        assert not (derangement(21, rng) == np.arange(21)).any()


def test_pairing_refuses_mismatched_settings():
    base, _ = scenario("independent")
    base[3].config = dict(base[3].config, temperature=0.7)
    with pytest.raises(ValueError, match="temperature"):
        check_compatible(base)


def test_n_changes():
    p = np.full(300, 1.7)
    assert n_changes(p) == 0
    p[150:] = 1.8
    assert n_changes(p) == 1
    p[99] = 1.0  # period 100 differs from period 101: the change into period 101 counts
    assert n_changes(p) == 2


# ---------- known answers ----------

def test_independent_paths_give_no_signal(results):
    r = results["independent"]
    assert abs(r.loc[("fish_delta", "all"), "real_pooled"]) < 0.05
    assert abs(r.loc[("fish_delta", "all"), "placebo_null_mean"]) < 0.03
    assert 0.35 < r.loc[("fish_delta", "all"), "auroc_real_vs_placebo"] < 0.65
    assert r.loc[("fish_delta", "all"), "p_value_real"] > 0.05


def test_follower_is_detected_and_beats_placebo(results):
    r = results["follower"].loc[("fish_delta", "all")]
    assert r.real_pooled > 0.6  # true delta 0.8
    assert r.placebo_null_mean < 0.05
    assert r.real_pooled > r.placebo_null_p95
    assert r.p_value_real <= 1 / (B + 1) + 1e-12
    assert r.auroc_real_vs_placebo > 0.95


def test_one_sided_follower(results):
    r = results["leader_follower"].loc[("fish_delta", "all")]
    assert 0.3 < r.instructed_pooled < 0.5  # rho / 2
    assert r.power_instructed >= 5 / 6


def test_shared_trajectory_fools_naive_delta_but_not_placebo(results):
    naive = results["shared_trajectory"].loc[("naive_delta", "all")]
    fish = results["shared_trajectory"].loc[("fish_delta", "all")]
    assert naive.real_pooled > 0.1  # naive delta looks like reaction...
    assert abs(naive.real_pooled - naive.placebo_null_mean) < 0.03  # ...but placebo pairs show the same
    assert naive.p_value_real > 0.1 and 0.35 < naive.auroc_real_vs_placebo < 0.65
    assert abs(fish.real_pooled) < 0.05  # Fish's spec (late periods, FE) is not fooled


def test_frozen_games_are_handled(results):
    mf = results["mostly_frozen"]
    assert math.isfinite(mf.loc[("fish_delta", "all"), "real_pooled"])
    assert mf.loc[("fish_delta", "moving"), "n_real"] <= mf.loc[("fish_delta", "all"), "n_real"]
    af = results["all_frozen"]
    r = af.loc[("fish_delta", "all")]
    assert math.isnan(r.real_pooled) and r.n_unidentified_real == 21 and r.n_unidentified_placebo == 420
    assert r.power_instructed == 0 and r.auroc_real_vs_placebo == 0.5
    assert af.loc[("fish_delta", "moving"), "n_real"] == 0
    base, _ = scenario("all_frozen")
    assert math.isnan(fish_regression(real_markets(base)).delta)


def test_cross_game_diagnostic():
    base, _ = scenario("independent")
    d = diagnostics.summarize(base)
    cross = d["correlations"].set_index(["what", "measure"])
    assert len(d["cross"]) == 2 * 21 * 20 // 2
    assert abs(cross.loc[("cross-game firm 0", "corr_diffs"), "mean"]) < 0.03
    # Shared trajectory: levels correlate across games before period 101 settles; first differences don't.
    sh, _ = scenario("shared_trajectory")
    dsh = diagnostics.summarize(sh, window=(1, 300))["correlations"].set_index(["what", "measure"])
    assert dsh.loc[("cross-game firm 0", "corr_levels"), "mean"] > 0.5
    assert abs(dsh.loc[("cross-game firm 0", "corr_diffs"), "mean"]) < 0.05
    frozen, _ = scenario("all_frozen")
    df = diagnostics.summarize(frozen)
    assert df["share_firms_moving"] == 0 and df["correlations"].n_defined.sum() == 0
