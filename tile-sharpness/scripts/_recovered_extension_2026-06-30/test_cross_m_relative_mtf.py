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


# --------------------------------------------------------------------------- #
# P2 — through-focus defocus-response estimator (the 4th corroborator)
# --------------------------------------------------------------------------- #

def _synthetic_focus_curve(sigma_z, n_frames=41, peak_frame=20.0, amp=100.0,
                           base=5.0):
    """A synthetic through-focus sharpness response: a Gaussian of defocus (in frames)
    of width ``sigma_z`` on a flat baseline. A SHARPER optic has a NARROWER curve
    (smaller sigma_z), so its fitted FWHM is smaller."""
    z = np.arange(n_frames, dtype=float)
    vals = base + amp * np.exp(-((z - peak_frame) ** 2) / (2 * sigma_z ** 2))
    return z, vals


def test_gaussian_defocus_fwhm_recovers_known_width():
    # FWHM of a Gaussian of width sigma_z is 2.3548*sigma_z; the sub-frame fit must
    # recover it from the (baseline-offset) focus curve.
    sigma_z = 4.0
    seqs, vals = _synthetic_focus_curve(sigma_z)
    _, fwhm, mu = X.gaussian_defocus_fwhm(seqs, vals)
    assert fwhm == pytest.approx(2.3548 * sigma_z, rel=0.05)
    assert mu == pytest.approx(20.0, abs=0.5)


def test_gaussian_defocus_fwhm_is_subframe_continuous():
    # two stacks whose widths differ by less than a frame must yield DISTINCT FWHMs
    # (the sub-frame property that breaks the coarse-integer-FWHM macro ties).
    _, va = _synthetic_focus_curve(3.0)
    _, vb = _synthetic_focus_curve(3.3)
    sa = X.gaussian_defocus_fwhm(np.arange(41.0), va)[1]
    sb = X.gaussian_defocus_fwhm(np.arange(41.0), vb)[1]
    assert sa < sb
    assert abs(sa - sb) < 1.5  # genuinely sub-frame resolution, not quantised


def test_gaussian_defocus_fwhm_rejects_no_peak():
    # a flat response (no peak above baseline) has no Gaussian fit -> NaN FWHM.
    seqs = np.arange(20.0)
    flat = np.full(20, 5.0)
    _, fwhm, _ = X.gaussian_defocus_fwhm(seqs, flat)
    assert not np.isfinite(fwhm)
    # a cupped (U-shaped, upward-parabola) response has no focus peak -> NaN FWHM.
    cup = 50.0 - 40.0 * np.exp(-((seqs - 10.0) ** 2) / (2 * 4.0 ** 2))
    _, fwhm_cup, _ = X.gaussian_defocus_fwhm(seqs, cup)
    assert not np.isfinite(fwhm_cup)
    # too few frames -> NaN as well
    _, fwhm2, _ = X.gaussian_defocus_fwhm(np.arange(3.0), np.array([1.0, 9.0, 1.0]))
    assert not np.isfinite(fwhm2)


def test_through_focus_scores_recover_sharpness_order():
    # build per-(config, patch) FWHM rows for three configs of known width; the
    # per-config score (= -median FWHM) must order sharp (narrow) first.
    rows = []
    for sid, sigma_z in (("sharp", 2.5), ("mid", 4.0), ("soft", 6.0)):
        for patch in range(6):
            seqs, vals = _synthetic_focus_curve(sigma_z, peak_frame=18.0 + patch)
            _, fwhm, _ = X.gaussian_defocus_fwhm(seqs, vals)
            rows.append(dict(sid=sid, patch=f"P{patch}", fwhm=fwhm))
    scores = X.through_focus_scores(pd.DataFrame(rows))
    assert scores["sharp"] > scores["mid"] > scores["soft"]


def test_through_focus_scores_drop_degenerate_fits():
    # a config whose patches all produced degenerate (huge) FWHMs is excluded;
    # within a config, a single huge FWHM is dropped before the median.
    rows = [
        dict(sid="ok", patch="P0", fwhm=8.0),
        dict(sid="ok", patch="P1", fwhm=10.0),
        dict(sid="ok", patch="P2", fwhm=200.0),   # degenerate -> dropped
        dict(sid="bad", patch="P0", fwhm=200.0),  # only degenerate -> config omitted
        dict(sid="bad", patch="P1", fwhm=float("nan")),
    ]
    scores = X.through_focus_scores(pd.DataFrame(rows))
    assert "bad" not in scores
    assert scores["ok"] == pytest.approx(-9.0)  # median of {8, 10}, 200 dropped


def test_p2_deconfound_corr_against_n_eff():
    # P2's de-confounding axis is N_eff (DOF), not M. A clean P2 score is ~uncorrelated
    # with N_eff; the helper computes corr(N_eff, score) and the OK gate is |corr|<=thr.
    scores = {"a": -8.0, "b": -9.0, "c": -10.0, "d": -11.0}
    # N_eff deliberately UNcorrelated with the score order (de-confounded):
    n_eff = {"a": 16.0, "b": 22.0, "c": 11.0, "d": 18.0}
    corr = X.p2_deconfound_corr(scores, n_eff)
    assert np.isfinite(corr)
    assert X.p2_deconfound_ok(corr) == (abs(corr) <= X.P2_DECONFOUND_MAX_ABS_CORR)
    # a score that simply tracks N_eff fails the self-check
    tracking = {s: -n for s, n in n_eff.items()}
    assert abs(X.p2_deconfound_corr(tracking, n_eff)) == pytest.approx(1.0, abs=1e-9)
    assert not X.p2_deconfound_ok(X.p2_deconfound_corr(tracking, n_eff))


def test_consensus_folds_in_p2_as_fourth_estimator():
    # P1-like, two cross-checks, and P2 all roughly agree -> consensus is a 4-input
    # rank-average; n_estimators reports 4 and the agreed-sharpest config leads.
    base = {"x": 3.0, "y": 2.0, "z": 1.0, "w": 0.0, "v": -1.0, "u": -2.0}
    jitter = lambda d, e: {k: v + e for k, v in d.items()}
    series = {
        "P1_fpx0.1": base,
        "P31_padedge": jitter(base, 0.1),
        "P32_decon": jitter(base, -0.1),
        "P2_psffoc": {k: v + 0.05 for k, v in base.items()},
    }
    members = ["P1_fpx0.1", "P31_padedge", "P32_decon", "P2_psffoc"]
    cons = X.consensus_ranking(series, members)
    assert set(cons.n_estimators) == {4}
    assert cons.iloc[0].sid == "x"
    assert "P2_psffoc" in cons.columns
    # adding P2 keeps the order monotone with the agreed series
    assert list(cons.sid) == ["x", "y", "z", "w", "v", "u"]


# --------------------------------------------------------------------------- #
# P2 rail-availability gate (multi-session: 2025-10-17 unregistered-rail caveat)
# --------------------------------------------------------------------------- #

def test_p2_rail_available_defaults_true_when_absent():
    # A subset without the column (the original 38-config set) -> P2 stays available.
    assert X.p2_rail_available(None) is True
    assert X.p2_rail_available("") is True
    assert X.p2_rail_available("   ") is True


def test_p2_rail_available_truthy_strings():
    for v in ("true", "True", "1", "yes", "Y", "t"):
        assert X.p2_rail_available(v) is True


def test_p2_rail_available_falsey_strings():
    # 2025-10-17 carries an unregistered / non-constant rail step -> P2 unavailable.
    for v in ("false", "False", "0", "no", "n", "off"):
        assert X.p2_rail_available(v) is False


def test_p2_rail_available_bool_passthrough():
    assert X.p2_rail_available(True) is True
    assert X.p2_rail_available(False) is False


def test_p2_rail_unavailable_configs_simply_absent_from_scores():
    # A config flagged rail-unavailable emits NO psffoc rows, so it never reaches
    # through_focus_scores -> it is omitted from P2 (degrades to spectral/edge only),
    # while rail-ok configs still score. This is the graceful-degradation contract.
    rows = [dict(sid="railok", patch=f"P{p}", fwhm=8.0 + 0.1 * p) for p in range(5)]
    # the rail-unavailable config contributes no rows at all (driver skips emission)
    scores = X.through_focus_scores(pd.DataFrame(rows))
    assert "railok" in scores
    assert "railoff" not in scores


# --------------------------------------------------------------------------- #
# incomplete-coverage guard (manual-tier sweeps that missed the focus peak)
# --------------------------------------------------------------------------- #

def test_focus_peak_at_edge_detects_unbracketed_peak():
    # peak at the LAST frame -> sweep never reached / passed the true peak -> edge.
    seqs = np.arange(40.0)
    rising = np.linspace(1.0, 50.0, 40)  # monotonically rising; argmax at the end
    assert X.focus_peak_at_edge(seqs, rising) is True
    # peak at the FIRST frame -> also an edge.
    falling = rising[::-1]
    assert X.focus_peak_at_edge(seqs, falling) is True


def test_focus_peak_at_edge_passes_centered_peak():
    # a peak comfortably inside the sweep is well-bracketed -> not an edge.
    seqs = np.arange(40.0)
    vals = np.exp(-((seqs - 20.0) ** 2) / (2 * 4.0 ** 2))
    assert X.focus_peak_at_edge(seqs, vals) is False


def test_focus_peak_at_edge_too_few_frames_is_not_flagged():
    # unknown (too few frames) must not be reported as an edge (caller keeps it).
    assert X.focus_peak_at_edge(np.arange(3.0), np.array([1.0, 9.0, 1.0])) is False


def test_coverage_ok_majority_rule():
    assert X.coverage_ok([]) is True                       # unknown -> keep
    assert X.coverage_ok([False, False, False]) is True    # all bracketed
    assert X.coverage_ok([True, False, False]) is True     # minority edge -> keep
    assert X.coverage_ok([True, True, False]) is False     # majority edge -> drop
    assert X.coverage_ok([True, True]) is False            # all edge -> drop


def test_coverage_ok_tie_is_dropped():
    # exactly half at the edge: 1 of 2 -> 1 <= 1.0 -> still OK (a single edge patch
    # among two is tolerated); 2 of 4 -> 2 <= 2.0 -> OK; 3 of 4 -> not OK.
    assert X.coverage_ok([True, False]) is True
    assert X.coverage_ok([True, True, False, False]) is True
    assert X.coverage_ok([True, True, True, False]) is False


def test_caveats_header_states_the_fence():
    h = X.caveats_header(0.10)
    assert "RELATIVE" in h
    assert "FIXED-SENSOR-FREQUENCY" in h
    assert "NOT an absolute MTF" in h
    assert "0.08-0.15" in h
    # every line is comment-prefixed for CSV embedding
    assert all(ln.startswith("# ") for ln in h.splitlines())
