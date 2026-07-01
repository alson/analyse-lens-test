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


# --------------------------------------------------------------------------- #
# POC-1 — focus-coverage classifier
# --------------------------------------------------------------------------- #

def test_coverage_flag_peak_well_inside_is_ok():
    # peak fitted at frame 20 of a 41-frame stack, narrow FWHM that fits with margin
    # to spare on both sides -> ok.
    seqs, vals = _synthetic_focus_curve(3.0, n_frames=41, peak_frame=20.0)
    _, fwhm, mu = X.gaussian_defocus_fwhm(seqs, vals)
    assert X.coverage_flag(mu, fwhm, nstack=41) == "ok"
    # geometry helpers on this ok case
    assert X.peak_pos_frac(mu, 41) == pytest.approx(20.0 / 40.0, abs=0.02)
    assert X.edge_dist_frames(mu, 41) == pytest.approx(20.0, abs=0.5)


def test_coverage_flag_peak_at_first_frame_is_truncated_low():
    # the captured stack starts AT the peak: best focus is at/before frame 0.
    seqs, vals = _synthetic_focus_curve(3.0, n_frames=41, peak_frame=0.0)
    _, fwhm, mu = X.gaussian_defocus_fwhm(seqs, vals)
    assert mu <= X.COVERAGE_EDGE_MARGIN_FRAMES
    assert X.coverage_flag(mu, fwhm, nstack=41) == "truncated_low"
    # pure-classifier check independent of the fit
    assert X.coverage_flag(0.0, 6.0, 41) == "truncated_low"


def test_coverage_flag_peak_at_last_frame_is_truncated_high():
    # the captured stack ends AT the peak: best focus is at/past the last frame.
    seqs, vals = _synthetic_focus_curve(3.0, n_frames=41, peak_frame=40.0)
    _, fwhm, mu = X.gaussian_defocus_fwhm(seqs, vals)
    assert mu >= 40.0 - X.COVERAGE_EDGE_MARGIN_FRAMES
    assert X.coverage_flag(mu, fwhm, nstack=41) == "truncated_high"
    assert X.coverage_flag(40.0, 6.0, 41) == "truncated_high"


def test_coverage_flag_peak_inside_but_fwhm_clipped():
    # peak CENTRE comfortably inside (frame 5 of 41, > margin from edge) but the
    # half-max width (HWHM = fwhm/2) runs off the low edge -> fwhm_truncated.
    # Pure classifier: mu=5, fwhm=20 -> HWHM=10 -> mu-HWHM=-5 < 0.
    assert X.coverage_flag(5.0, 20.0, nstack=41) == "fwhm_truncated"
    # and a synthetic wide curve whose peak is near (but not at) the start:
    seqs, vals = _synthetic_focus_curve(8.0, n_frames=41, peak_frame=6.0)
    _, fwhm, mu = X.gaussian_defocus_fwhm(seqs, vals)
    assert mu > X.COVERAGE_EDGE_MARGIN_FRAMES          # centre is inside
    assert (mu - fwhm / 2.0) < 0.0                      # but half-max clips the edge
    assert X.coverage_flag(mu, fwhm, nstack=41) == "fwhm_truncated"


def test_coverage_flag_edge_takes_priority_over_fwhm_clip():
    # a centre AT frame 0 with a clipped HWHM is reported truncated_low, not
    # fwhm_truncated (centre-edge truncation has priority).
    assert X.coverage_flag(0.0, 20.0, nstack=41) == "truncated_low"


def test_coverage_flag_unknown_inputs_default_ok():
    # non-finite mu or a too-short stack -> treated as unknown (ok); callers also
    # require a finite fwhm before trusting the patch.
    assert X.coverage_flag(float("nan"), 5.0, 41) == "ok"
    assert X.coverage_flag(10.0, 5.0, nstack=1) == "ok"
    assert np.isnan(X.peak_pos_frac(float("nan"), 41))
    assert np.isnan(X.edge_dist_frames(20.0, 1))


def test_through_focus_scores_excludes_truncated_patches():
    # a config whose narrow (sharp) patches are all truncated and whose only ok
    # patches are wide must score on the ok patches, not the truncated ones.
    rows = [
        # ok patches: moderate width
        dict(sid="cfg", patch="P0", fwhm=10.0, coverage_flag="ok"),
        dict(sid="cfg", patch="P1", fwhm=12.0, coverage_flag="ok"),
        # truncated patches with artificially small FWHM (clipped curve) -> excluded
        dict(sid="cfg", patch="P2", fwhm=2.0, coverage_flag="truncated_low"),
        dict(sid="cfg", patch="P3", fwhm=2.0, coverage_flag="fwhm_truncated"),
    ]
    scores = X.through_focus_scores(pd.DataFrame(rows))
    # median over the two ok patches {10, 12} = 11, score = -11
    assert scores["cfg"] == pytest.approx(-11.0)
    # opting out of the coverage filter -> median over all four {2,2,10,12}=6
    s_nocov = X.through_focus_scores(pd.DataFrame(rows), require_coverage_ok=False)
    assert s_nocov["cfg"] == pytest.approx(-6.0)


def test_through_focus_scores_fallback_when_no_ok_patch():
    # if a config has NO ok patch, it falls back to its valid FWHMs (not dropped).
    rows = [
        dict(sid="alltrunc", patch="P0", fwhm=4.0, coverage_flag="truncated_high"),
        dict(sid="alltrunc", patch="P1", fwhm=6.0, coverage_flag="truncated_high"),
    ]
    scores = X.through_focus_scores(pd.DataFrame(rows))
    assert scores["alltrunc"] == pytest.approx(-5.0)


def test_through_focus_coverage_summary_counts_and_fraction():
    rows = [
        dict(sid="A", patch="P0", fwhm=5.0, coverage_flag="ok"),
        dict(sid="A", patch="P1", fwhm=5.0, coverage_flag="ok"),
        dict(sid="A", patch="P2", fwhm=5.0, coverage_flag="truncated_low"),
        dict(sid="A", patch="P3", fwhm=5.0, coverage_flag="fwhm_truncated"),
        dict(sid="B", patch="P0", fwhm=5.0, coverage_flag="ok"),
    ]
    cov = X.through_focus_coverage_summary(pd.DataFrame(rows))
    a = cov[cov.sid == "A"].iloc[0]
    assert a.n_total == 4 and a.ok == 2 and a.truncated_low == 1
    assert a.fwhm_truncated == 1
    assert a.frac_truncated == pytest.approx(0.5)
    b = cov[cov.sid == "B"].iloc[0]
    assert b.frac_truncated == pytest.approx(0.0)


def test_through_focus_scores_backward_compatible_without_coverage_column():
    # a psffoc frame from before POC-1 (no coverage_flag column) behaves as before.
    rows = [dict(sid="x", patch="P0", fwhm=8.0),
            dict(sid="x", patch="P1", fwhm=10.0)]
    scores = X.through_focus_scores(pd.DataFrame(rows))
    assert scores["x"] == pytest.approx(-9.0)


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
# LOCATION-AWARE field analysis (distance/angle from frame centre)
# --------------------------------------------------------------------------- #

IMG_W, IMG_H = 8256, 5504
CX, CY = IMG_W / 2.0, IMG_H / 2.0
HALF_DIAG = 0.5 * np.hypot(IMG_W, IMG_H)


def test_field_geometry_centre_is_zero():
    g = X.field_geometry(CX, CY, CX, CY, IMG_W, IMG_H, m=1.0)
    assert g["dist_px"] == pytest.approx(0.0)
    assert g["field_height"] == pytest.approx(0.0)
    assert g["dist_subject_mm"] == pytest.approx(0.0)


def test_field_geometry_corner_is_field_height_one():
    # the extreme image corner is field_height == 1.0 (normalised by half-diagonal).
    g = X.field_geometry(IMG_W, IMG_H, CX, CY, IMG_W, IMG_H)
    assert g["field_height"] == pytest.approx(1.0, rel=1e-9)


def test_field_geometry_angle_convention():
    # +x (right) = 0deg; up (smaller image-y) = +90deg; left = 180; down = -90.
    assert X.field_geometry(CX + 100, CY, CX, CY, IMG_W, IMG_H)["angle_deg"] == pytest.approx(0.0)
    assert X.field_geometry(CX, CY - 100, CX, CY, IMG_W, IMG_H)["angle_deg"] == pytest.approx(90.0)
    assert abs(X.field_geometry(CX - 100, CY, CX, CY, IMG_W, IMG_H)["angle_deg"]) == pytest.approx(180.0)
    assert X.field_geometry(CX, CY + 100, CX, CY, IMG_W, IMG_H)["angle_deg"] == pytest.approx(-90.0)


def test_field_geometry_subject_mm_scales_inverse_with_M():
    # for a fixed pixel offset, subject distance shrinks as 1/M.
    g1 = X.field_geometry(CX + 1000, CY, CX, CY, IMG_W, IMG_H, m=1.0)
    g2 = X.field_geometry(CX + 1000, CY, CX, CY, IMG_W, IMG_H, m=2.0)
    assert g1["dist_subject_mm"] == pytest.approx(2 * g2["dist_subject_mm"])
    assert g1["dist_subject_mm"] == pytest.approx(1000 * X.SENSOR_PITCH_MM)


def test_field_zone_binning():
    assert X.field_zone(0.0) == "centre"
    assert X.field_zone(0.32) == "centre"
    assert X.field_zone(0.33) == "mid"
    assert X.field_zone(0.65) == "mid"
    assert X.field_zone(0.66) == "corner"
    assert X.field_zone(1.0) == "corner"
    assert X.field_zone(float("nan")) is None


def _synthetic_field(sid, fhs, angles, amps, sag=None, tan=None):
    rows = []
    for i, (fh, ang, amp) in enumerate(zip(fhs, angles, amps)):
        r = dict(sid=sid, patch=f"P{i}", field_height=fh, angle_deg=ang, amp=amp)
        if sag is not None:
            r["amp_sag"] = sag[i]
        if tan is not None:
            r["amp_tan"] = tan[i]
        rows.append(r)
    return pd.DataFrame(rows)


def test_field_coverage_flags_degenerate_high_M_cluster():
    # a tight high-M cluster (all patches at nearly the same small field height)
    # is flagged degenerate -> not a genuine field profile, do not over-interpret.
    fhs = [0.10, 0.11, 0.12, 0.13]
    f = _synthetic_field("hiM", fhs, [10, 20, 30, 40], [1.0, 1.0, 1.0, 1.0])
    cov = X.field_coverage(f)
    row = cov[cov.sid == "hiM"].iloc[0]
    assert row.degenerate_cluster
    assert not row.field_supported
    assert row.field_height_span == pytest.approx(0.03)


def test_field_coverage_reports_zone_population_and_span():
    # spread across centre..corner with >=2 patches each -> supported, 3 zones.
    fhs = [0.05, 0.10, 0.45, 0.50, 0.80, 0.90]
    f = _synthetic_field("rich", fhs, [0, 45, 90, 135, 180, -90], [1.0] * 6)
    cov = X.field_coverage(f)
    row = cov.iloc[0]
    assert row.sid == "rich"
    assert row.n_zones_populated == 3
    assert "centre" in row.zones_populated and "corner" in row.zones_populated
    assert row.field_supported
    assert row.field_height_span == pytest.approx(0.85)
    assert row.angle_span_deg > 180  # spread around the circle


def test_radial_falloff_recovers_centre_to_corner_direction():
    # amp DECREASES with field height (classic corner softening) -> corner/centre < 1.
    fhs = [0.05, 0.10, 0.45, 0.50, 0.80, 0.90]
    amps = [1.0, 0.98, 0.7, 0.68, 0.4, 0.38]
    f = _synthetic_field("soft_corners", fhs, [0, 90, 180, -90, 45, 135], amps)
    zone_tbl, ratio_tbl = X.radial_falloff(f, value_col="amp")
    r = ratio_tbl.iloc[0]
    assert r.falloff_supported
    assert r.corner_centre_ratio < 1.0
    assert r.mid_centre_ratio < 1.0
    assert r.corner_centre_ratio < r.mid_centre_ratio  # monotone falloff
    # the centre zone mean is the mean of the two centre patches
    cen = zone_tbl[(zone_tbl.sid == "soft_corners") & (zone_tbl.zone == "centre")].iloc[0]
    assert cen["mean"] == pytest.approx(0.99)
    assert not cen.is_sparse


def test_radial_falloff_flags_sparse_zone_and_nan_ratio():
    # corner zone has only ONE patch (< MIN_PATCHES_PER_ZONE) -> sparse, ratio NaN.
    fhs = [0.05, 0.10, 0.45, 0.50, 0.85]
    f = _synthetic_field("nocorner", fhs, [0, 90, 180, -90, 45], [1.0, 1.0, 0.8, 0.8, 0.5])
    zone_tbl, ratio_tbl = X.radial_falloff(f, value_col="amp")
    corner = zone_tbl[(zone_tbl.sid == "nocorner") & (zone_tbl.zone == "corner")].iloc[0]
    assert corner.n == 1
    assert corner.is_sparse
    assert np.isnan(ratio_tbl.iloc[0].corner_centre_ratio)
    assert not ratio_tbl.iloc[0].falloff_supported


def test_azimuthal_asymmetry_recovers_decentering_sign_and_direction():
    # build a field where the RIGHT side is systematically sharper than the LEFT
    # (a decentering signature): right patches (|angle|<90) get higher amp.
    fhs = [0.5, 0.5, 0.5, 0.5, 0.7, 0.7, 0.7, 0.7]
    angles = [0, 45, -45, 30, 180, 135, -135, -150]  # first four right, last four left
    amps = [1.0, 1.0, 1.0, 1.0, 0.6, 0.6, 0.6, 0.6]
    f = _synthetic_field("decentered", fhs, angles, amps)
    azi = X.azimuthal_asymmetry(f, value_col="amp")
    r = azi.iloc[0]
    assert r.supported
    assert r.lr > 0  # right sharper than left
    assert r.asymmetry_mag > 0
    assert abs(r.asymmetry_dir_deg) < 45  # gradient points to the right (~0 deg)


def test_azimuthal_asymmetry_unsupported_when_one_sided():
    # all in-band patches on the right -> no left patches -> lr NaN -> unsupported.
    f = _synthetic_field("oneside", [0.5, 0.6, 0.7, 0.8], [0, 30, -30, 10], [1.0] * 4)
    azi = X.azimuthal_asymmetry(f, value_col="amp")
    assert not azi.iloc[0].supported


def test_astigmatism_index_recovers_sagittal_vs_tangential():
    # sagittal sharper than tangential everywhere in-band -> index > 0.
    fhs = [0.5, 0.6, 0.7, 0.8]
    sag = [1.0, 1.0, 1.0, 1.0]
    tan = [0.5, 0.5, 0.5, 0.5]
    f = _synthetic_field("astig", fhs, [0, 90, 180, -90], [1.0] * 4, sag=sag, tan=tan)
    astig = X.astigmatism_index(f, sag_col="amp_sag", tan_col="amp_tan")
    r = astig.iloc[0]
    assert r.supported
    assert r.astig_index == pytest.approx(np.log(2.0), rel=1e-6)


def test_astigmatism_index_unsupported_without_axis_columns():
    f = _synthetic_field("noaxis", [0.5, 0.6, 0.7], [0, 90, 180], [1.0] * 3)
    astig = X.astigmatism_index(f, sag_col="amp_sag", tan_col="amp_tan")
    assert not astig.iloc[0].supported
    assert np.isnan(astig.iloc[0].astig_index)


def test_field_resolved_ranking_runs_per_zone():
    # two configs, sharp vs soft, fully covering centre + corner zones; the per-zone
    # ranking must order sharp above soft in each populated zone.
    freqs = np.linspace(0.0, 0.4, 40)
    rows = []
    # patches P0,P1 -> centre (fh 0.1); P2,P3 -> corner (fh 0.8)
    fh_map = {"P0": 0.1, "P1": 0.1, "P2": 0.8, "P3": 0.8}
    for sid, sigma in (("sharp", 0.6), ("soft", 1.4)):
        psd_c = _blurred_psd_curve(sigma, freqs)
        for pk in fh_map:
            for fr, ps in zip(freqs, psd_c):
                rows.append(dict(sid=sid, patch=pk, f_grid=fr, psd=ps))
    psd = pd.DataFrame(rows)
    meta = pd.DataFrame([dict(sid=s, M=1.0, px_per_unit=X.SAMPLES_PER_UNIT)
                         for s in ("sharp", "soft")])
    field = pd.DataFrame([dict(sid=s, patch=pk, field_height=fh)
                          for s in ("sharp", "soft") for pk, fh in fh_map.items()])
    zrank = X.field_resolved_ranking(psd, meta, field, f_px=0.10)
    assert "centre" in zrank and "corner" in zrank
    for z in ("centre", "corner"):
        order = list(zrank[z].table.sid)
        assert order.index("sharp") < order.index("soft")


def test_field_radial_falloff_agrees_with_characterise_uniformity_sign():
    # AGREEMENT-WITH-CHARACTERISE sanity: characterise reports uniformity =
    # corner_MTF50/centre_MTF50 (< 1 when corners soften) and decentering L-R as a
    # signed peak-value asymmetry. Build ONE synthetic field that softens to the
    # corners AND is sharper on the right, and confirm the new field products report
    # the SAME signs: radial corner/centre < 1, and azimuthal lr > 0 (right sharper),
    # matching characterise's uniformity<1 + a positive L-R decentering.
    fhs = [0.05, 0.10, 0.45, 0.50, 0.80, 0.85, 0.80, 0.85]
    angles = [0, 180, 30, 150, 20, -20, 160, -160]
    # corner softening + right-bias: amp falls with fh, and right (|ang|<90) > left.
    base = {0.05: 1.0, 0.10: 1.0, 0.45: 0.75, 0.50: 0.75, 0.80: 0.5, 0.85: 0.5}
    amps = []
    for fh, ang in zip(fhs, angles):
        a = base[fh]
        a *= 1.15 if abs(ang) < 90 else 0.85  # right sharper (decentering)
        amps.append(a)
    f = _synthetic_field("realistic", fhs, angles, amps)
    _, ratio_tbl = X.radial_falloff(f, value_col="amp")
    azi = X.azimuthal_asymmetry(f, value_col="amp")
    assert ratio_tbl.iloc[0].corner_centre_ratio < 1.0   # uniformity_fx < 1 (agrees)
    assert azi.iloc[0].lr > 0                            # L-R decentering: right sharper


def test_caveats_header_states_the_fence():
    h = X.caveats_header(0.10)
    assert "RELATIVE" in h
    assert "FIXED-SENSOR-FREQUENCY" in h
    assert "NOT an absolute MTF" in h
    assert "0.08-0.15" in h
    # every line is comment-prefixed for CSV embedding
    assert all(ln.startswith("# ") for ln in h.splitlines())


# --------------------------------------------------------------------------- #
# P2 rail-availability tier gate (multi-session: 2025-10-17 unregistered-rail)
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
# POC-1-native config-level coverage verdict (coverage_config_ok)
# --------------------------------------------------------------------------- #

def test_coverage_config_ok_counts_ok_patches():
    # >= min_ok "ok" patches -> keep; below -> drop.
    assert X.coverage_config_ok(["ok", "ok", "ok"], min_ok=3) is True
    assert X.coverage_config_ok(["ok", "ok"], min_ok=3) is False
    assert X.coverage_config_ok(["ok", "ok", "ok", "ok"], min_ok=3) is True


def test_coverage_config_ok_only_ok_flag_counts():
    # truncated_* and fwhm_truncated are all not-ok; unknown flags too.
    flags = ["ok", "truncated_low", "truncated_high", "fwhm_truncated", "ok"]
    assert X.coverage_config_ok(flags, min_ok=2) is True   # 2 ok
    assert X.coverage_config_ok(flags, min_ok=3) is False  # only 2 ok
    # an unrecognised flag is conservatively not-ok
    assert X.coverage_config_ok(["ok", "weird", "ok"], min_ok=3) is False


def test_coverage_config_ok_empty_is_dropped():
    # no patches -> nothing to trust -> drop.
    assert X.coverage_config_ok([]) is False


def test_coverage_config_ok_default_threshold():
    # default COVERAGE_MIN_OK_PATCHES applies when min_ok is not given.
    n = X.COVERAGE_MIN_OK_PATCHES
    assert X.coverage_config_ok(["ok"] * n) is True
    assert X.coverage_config_ok(["ok"] * (n - 1)) is False
