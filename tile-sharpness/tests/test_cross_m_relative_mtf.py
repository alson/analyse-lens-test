"""Tests for the cross-magnification RELATIVE glass-MTF estimator core.

These exercise the validated, target-agnostic logic in ``cross_m_relative_mtf``:
the transitive chain, the f_px-window enforcement (the fence), the de-confound
self-check gate, the empty-magnification float check, the graph-connectivity check,
and a synthetic SAME-PATCH case with a KNOWN relative Gaussian blur (the estimator
must recover the correct sharpness ORDER from the amplitude ratio).
"""
import warnings

import numpy as np
import pandas as pd
import pytest

from tile_sharpness import cross_m_relative_mtf as X


# --------------------------------------------------------------------------- #
# chain solver
# --------------------------------------------------------------------------- #

def test_chain_recovers_differences_zero_mean_gauge():
    # true scores -2, 0, +2 (zero mean). edges are exact pairwise differences.
    nodes = ["a", "b", "c"]
    edges = [("c", "a", 4.0, 1.0), ("c", "b", 2.0, 1.0), ("b", "a", 2.0, 1.0)]
    sc = X.chain_solve(edges, nodes)
    assert sc["a"] == pytest.approx(-2.0, abs=1e-9)
    assert sc["b"] == pytest.approx(0.0, abs=1e-9)
    assert sc["c"] == pytest.approx(+2.0, abs=1e-9)
    assert sum(sc.values()) == pytest.approx(0.0, abs=1e-9)


def test_chain_is_transitive_across_a_bridge():
    # a-b and b-c share, a-c does NOT: the chain must still order a<b<c via b.
    nodes = ["a", "b", "c"]
    edges = [("b", "a", 1.0, 1.0), ("c", "b", 1.0, 1.0)]
    sc = X.chain_solve(edges, nodes)
    assert sc["a"] < sc["b"] < sc["c"]


def test_connected_components():
    edges = [("a", "b", 0.0, 1.0), ("c", "d", 0.0, 1.0)]
    ncomp, roots = X.connected_components(edges)
    assert ncomp == 2
    edges.append(("b", "c", 0.0, 1.0))
    ncomp, _ = X.connected_components(edges)
    assert ncomp == 1


# --------------------------------------------------------------------------- #
# synthetic same-patch known-blur recovery
# --------------------------------------------------------------------------- #

def _blurred_psd_curve(sigma_px, freqs):
    """Amplitude (sqrt-PSD) of a shared white-ish patch seen through a Gaussian PSF
    of width ``sigma_px``: |MTF| = exp(-2 pi^2 sigma^2 f^2). The shared intrinsic
    spectrum is flat (== 1) so it cancels in any ratio — exactly the same-patch
    construction the estimator relies on."""
    mtf = np.exp(-2 * np.pi ** 2 * sigma_px ** 2 * freqs ** 2)
    return (mtf ** 2)  # PSD = amplitude^2


def _synthetic_psd_meta(sigmas, n_patches=6, freqs=None):
    """Build (psd, meta) for configs with known blur sigmas (px/common-grid).
    All configs share the same px_per_unit so sensor-freq == grid-freq here, and
    every config covers every patch (fully connected)."""
    if freqs is None:
        freqs = np.linspace(0.0, 0.4, 40)
    rows = []
    for sid, sigma in sigmas.items():
        psd = _blurred_psd_curve(sigma, freqs)
        for pk in range(n_patches):
            for f, ps in zip(freqs, psd):
                rows.append(dict(sid=sid, patch=f"P{pk}", f_grid=f, psd=ps))
    psd = pd.DataFrame(rows)
    # M increases with blur deliberately, so an M-CONFOUNDED estimator would credit
    # the blurrier (higher-M) config; the sensor-freq ratio must NOT.
    meta = pd.DataFrame([
        dict(sid=sid, M=1.0 + i * 0.2, px_per_unit=X.SAMPLES_PER_UNIT)
        for i, sid in enumerate(sigmas)
    ])
    return psd, meta


def test_same_patch_recovers_known_relative_blur_order():
    # sharper (smaller sigma) must score higher.
    sigmas = {"sharp": 0.6, "mid": 1.0, "soft": 1.6}
    psd, meta = _synthetic_psd_meta(sigmas)
    px_per_unit = dict(zip(meta.sid, meta.px_per_unit))
    edges, _ = X.build_edges(psd, px_per_unit, 0.10, mode="sensor")
    scores, ncomp, resid = X.solve_chain(edges)
    assert ncomp == 1
    assert scores["sharp"] > scores["mid"] > scores["soft"]


def test_same_patch_recovers_blur_magnitude():
    # the log-amplitude difference at f equals 2*pi^2*(s_b^2 - s_a^2)*f^2, so the
    # recovered score gap should match the analytic Gaussian prediction.
    sigmas = {"a": 0.5, "b": 1.2}
    f = 0.10
    psd, meta = _synthetic_psd_meta(sigmas)
    px_per_unit = dict(zip(meta.sid, meta.px_per_unit))
    edges, _ = X.build_edges(psd, px_per_unit, f, mode="sensor")
    scores, _, _ = X.solve_chain(edges)
    expected_gap = 2 * np.pi ** 2 * (sigmas["b"] ** 2 - sigmas["a"] ** 2) * f ** 2
    assert (scores["a"] - scores["b"]) == pytest.approx(expected_gap, rel=1e-3)


# --------------------------------------------------------------------------- #
# f_px-window enforcement (the fence)
# --------------------------------------------------------------------------- #

def test_fpx_window_inside_is_silent():
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning would fail the test
        assert X.enforce_fpx_window(0.10) is True
        assert X.enforce_fpx_window(X.FPX_WINDOW[0]) is True
        assert X.enforce_fpx_window(X.FPX_WINDOW[1]) is True


def test_fpx_window_outside_warns():
    with pytest.warns(UserWarning, match="trustworthy window"):
        assert X.enforce_fpx_window(0.25) is False
    with pytest.warns(UserWarning):
        assert X.enforce_fpx_window(0.02) is False


def test_fpx_window_strict_raises():
    with pytest.raises(ValueError, match="trustworthy window"):
        X.enforce_fpx_window(0.30, strict=True)


# --------------------------------------------------------------------------- #
# de-confound self-check gate + empty-magnification float
# --------------------------------------------------------------------------- #

def test_deconfound_corr_is_negative_for_a_clean_set():
    # blur grows with M (set up in the helper) -> the SHARPNESS score must DECREASE
    # with M, i.e. corr(M, score) <= 0 (de-confounded).
    sigmas = {"a": 0.6, "b": 0.9, "c": 1.2, "d": 1.5}
    psd, meta = _synthetic_psd_meta(sigmas)
    px_per_unit = dict(zip(meta.sid, meta.px_per_unit))
    edges, _ = X.build_edges(psd, px_per_unit, 0.10, mode="sensor")
    scores, _, _ = X.solve_chain(edges)
    m_by_sid = dict(zip(meta.sid, meta.M))
    assert X.deconfound_corr(scores, m_by_sid) < 0


def test_gate_self_check_passes_clean_set():
    sigmas = {"a": 0.6, "b": 0.9, "c": 1.2, "d": 1.5}
    psd, meta = _synthetic_psd_meta(sigmas)
    gate, scores, pair_cells = X.gate_self_check(psd, meta, 0.10)
    assert gate.in_window
    assert gate.deconfound_ok
    assert gate.connectivity_ok
    assert gate.empty_mag_ok
    assert gate.passed
    assert gate.messages() == []


def test_gate_flags_empty_magnification_float():
    # a "+" accessory config is the SHARPEST -> empty-magnification float -> flagged.
    sigmas = {"bare": 1.2, "bare2": 1.4, "bare+TC": 0.5}
    psd, meta = _synthetic_psd_meta(sigmas)
    gate, scores, _ = X.gate_self_check(psd, meta, 0.10)
    assert "bare+TC" in gate.empty_mag_floats
    assert not gate.empty_mag_ok
    assert not gate.passed
    assert any("EMPTY-MAGNIFICATION FLOAT" in m for m in gate.messages())


def test_gate_strict_raises_on_deconfound_fail():
    # make sharpness INCREASE with M (M-confounded) -> corr(M,score) > 0 -> strict raise.
    sigmas = {"a": 1.5, "b": 1.2, "c": 0.9, "d": 0.6}  # blur falls as M rises
    psd, meta = _synthetic_psd_meta(sigmas)
    with pytest.raises(ValueError):
        X.gate_self_check(psd, meta, 0.10, strict=True)


def test_gate_flags_disconnected_graph():
    # two config groups that never share a patch -> two components.
    rows = []
    freqs = np.linspace(0.0, 0.4, 40)
    for sid, sigma, patches in (("a", 0.6, ["P0", "P1"]), ("b", 1.0, ["P0", "P1"]),
                                ("c", 0.7, ["Q0", "Q1"]), ("d", 1.1, ["Q0", "Q1"])):
        psd_c = _blurred_psd_curve(sigma, freqs)
        for pk in patches:
            for f, ps in zip(freqs, psd_c):
                rows.append(dict(sid=sid, patch=pk, f_grid=f, psd=ps))
    psd = pd.DataFrame(rows)
    meta = pd.DataFrame([dict(sid=s, M=1.0, px_per_unit=X.SAMPLES_PER_UNIT)
                         for s in ("a", "b", "c", "d")])
    gate, _, _ = X.gate_self_check(psd, meta, 0.10)
    assert gate.n_components == 2
    assert not gate.connectivity_ok
    assert any("DISCONNECTED" in m for m in gate.messages())


# --------------------------------------------------------------------------- #
# ranking + bootstrap + consensus
# --------------------------------------------------------------------------- #

def test_rank_configs_orders_sharp_first_with_sigma():
    sigmas = {"a": 0.6, "b": 0.9, "c": 1.2, "d": 1.5}
    psd, meta = _synthetic_psd_meta(sigmas)
    ranking = X.rank_configs(psd, meta, 0.10, n_boot=20)
    assert list(ranking.table.sid) == ["a", "b", "c", "d"]
    assert (ranking.table.sigma >= 0).all()
    assert ranking.gate.passed


def test_subject_mode_reintroduces_the_confound():
    # the SUBJECT-freq control: blur grows with M, but at a fixed subject (grid)
    # frequency the higher-M (blurrier here) configs are NOT systematically de-
    # credited the same way — the control is provided so callers can demonstrate the
    # sensor-freq axis is what does the de-confounding. Here we just assert the two
    # modes give different edges (they read different grid frequencies per config).
    sigmas = {"a": 0.6, "b": 1.2}
    psd, meta = _synthetic_psd_meta(sigmas)
    # give the two configs DIFFERENT px_per_unit so sensor vs subject diverge.
    meta.loc[meta.sid == "b", "px_per_unit"] = 2 * X.SAMPLES_PER_UNIT
    ppu = dict(zip(meta.sid, meta.px_per_unit))
    e_sensor, _ = X.build_edges(psd, ppu, 0.10, mode="sensor")
    e_subject, _ = X.build_edges(psd, ppu, 0.10, mode="subject")
    d_sensor = next(d for a, b, d, _ in e_sensor)
    d_subject = next(d for a, b, d, _ in e_subject)
    assert d_sensor != pytest.approx(d_subject)


def test_cross_estimator_agreement_and_consensus():
    a = {"x": 3.0, "y": 2.0, "z": 1.0, "w": 0.0, "v": -1.0, "u": -2.0}
    b = {"x": 2.9, "y": 2.1, "z": 0.8, "w": 0.1, "v": -1.2, "u": -1.9}  # ~agrees
    c = {"x": -2.0, "y": -1.0, "z": 0.0, "w": 1.0, "v": 2.0, "u": 3.0}  # reversed
    mat = X.cross_estimator_agreement({"A": a, "B": b, "C": c})
    assert mat.loc["A", "B"] > 0.8
    assert mat.loc["A", "C"] < 0
    cons = X.consensus_ranking({"A": a, "B": b}, ["A", "B"])
    assert cons.iloc[0].sid == "x"
    assert list(cons.consensus_rank) == list(range(1, len(cons) + 1))


def test_caveats_header_states_the_fence():
    h = X.caveats_header(0.10)
    assert "RELATIVE" in h
    assert "FIXED-SENSOR-FREQUENCY" in h
    assert "NOT an absolute MTF" in h
    assert "0.08-0.15" in h
    # every line is comment-prefixed for CSV embedding
    assert all(ln.startswith("# ") for ln in h.splitlines())
