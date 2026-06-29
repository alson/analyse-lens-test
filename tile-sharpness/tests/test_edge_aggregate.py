"""Tests for the direction-aware flat-edge aggregation (edge_aggregate)."""
import numpy as np

from tile_sharpness.methods import edge_aggregate as EA


def _rec(mtf50, kind, over=None, flag=False, t_along=None, settled=None):
    r = dict(mtf50=mtf50, kind=kind, over=over, flag=flag)
    if t_along is not None:
        r["t_along"] = t_along
    if settled is not None:
        r["settled"] = settled
    return r


def _split_set():
    # rising ~0.11 (clean), falling ~0.18 (over-reads); 6 each
    ris = [_rec(0.10 + 0.01 * i, "rising", over=0.55 + 0.02 * i) for i in range(6)]
    fal = [_rec(0.17 + 0.01 * i, "falling", over=0.90 + 0.05 * i) for i in range(6)]
    return ris + fal


def test_conservative_picks_lower_direction():
    out = EA.aggregate_conservative(_split_set(), over_ceiling=1.0, combine="min_direction")
    assert out is not None
    # rising median (~0.125) should be chosen over falling (~0.195)
    assert out["mtf50"] == out["rising_med"]
    assert out["rising_med"] < out["falling_med"]


def test_conservative_drops_over_ceiling():
    recs = [_rec(0.30, "rising", over=1.6),       # over ceiling -> dropped
            _rec(0.12, "rising", over=0.6),
            _rec(0.13, "falling", over=0.65)]
    out = EA.aggregate_conservative(recs, over_ceiling=1.05)
    assert out["n"] == 2                       # the 1.6 over-read dropped
    assert out["mtf50"] <= 0.13 + 1e-9


def test_conservative_drops_flagged():
    recs = [_rec(0.30, "rising", flag=True), _rec(0.12, "falling")]
    out = EA.aggregate_conservative(recs)
    assert out["n"] == 1 and out["mtf50"] == 0.12


def test_per_edge_focus_reports_split():
    out = EA.aggregate_per_edge_focus(_split_set(), over_ceiling=1.3)
    assert out["split_ratio"] > 1.3
    assert out["n"] == 12
    # mean lies between the two direction medians
    assert out["rising_med"] < out["mtf50"] < out["falling_med"]


def test_polarity_prefers_closest_to_anchor():
    # anchor (FFT) ~0.12 -> should pick rising, not falling
    out = EA.aggregate_polarity_selected(_split_set(), reference_cypx=0.12,
                                         ceiling_cypx=0.20)
    assert out["chosen"] == "rising"
    assert abs(out["mtf50"] - out["rising_med"]) < 1e-9


def test_polarity_ceiling_cut_removes_impossible_direction():
    recs = [_rec(0.25, "rising", over=1.4), _rec(0.10, "falling", over=0.55),
            _rec(0.24, "rising", over=1.3), _rec(0.11, "falling", over=0.6)]
    out = EA.aggregate_polarity_selected(recs, ceiling_cypx=0.18)
    assert out["chosen"] == "falling"


def test_polarity_prefers_settled_direction():
    recs = ([_rec(0.20, "rising", settled=False) for _ in range(4)] +
            [_rec(0.12, "falling", settled=True) for _ in range(4)])
    out = EA.aggregate_polarity_selected(recs, prefer_settled=True)
    assert out["chosen"] == "falling"
    assert "settled" in out["reason"]


def test_diagnose_consistent_sign_is_feature_profile():
    # rising > falling on EVERY line -> (a)/(c)
    recs = []
    for i in range(8):
        recs.append(_rec(0.18, "rising", t_along=10.0 * i))
        recs.append(_rec(0.11, "falling", t_along=10.0 * i + 2))
    d = EA.diagnose_asymmetry(recs)
    assert d["split_ratio"] > 1.3
    assert d["per_line_sign"] is not None and d["per_line_sign"] > 0.8
    assert d["verdict"].startswith("(a)")


def test_diagnose_field_gradient():
    # MTF50 trends strongly with position, split sign flips line to line -> (b)
    recs = []
    rng = np.random.default_rng(0)
    for i in range(12):
        base = 0.08 + 0.01 * i           # rising MTF climbs with field
        jit = rng.normal(0, 0.005)
        recs.append(_rec(base + jit, "rising", t_along=20.0 * i))
        recs.append(_rec(base - jit, "falling", t_along=20.0 * i + 3))
    d = EA.diagnose_asymmetry(recs)
    assert d["field_trend"] is not None and abs(d["field_trend"]) > 0.4


def test_diagnose_no_split():
    recs = [_rec(0.12, "rising", t_along=i) for i in range(6)] + \
           [_rec(0.121, "falling", t_along=i) for i in range(6)]
    d = EA.diagnose_asymmetry(recs)
    assert d["verdict"] == "no-meaningful-split"


def test_empty_returns_none():
    assert EA.aggregate_conservative([]) is None
    assert EA.aggregate_per_edge_focus([{"mtf50": None, "kind": "rising"}]) is None
    assert EA.aggregate_polarity_selected([]) is None
