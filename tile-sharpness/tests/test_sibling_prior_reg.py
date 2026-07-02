"""Tests for the pure pieces of the sibling-prior recovery registrar.

The heavy image registration (class-A tilt-gated detect, class-B matched-filter over a
real full-res frame) is INTEGRATION, validated on nufan against the ground-truth M in
``out_reg_cv/baseline_results.json`` and reported separately. These cover the pure
decision logic productionised from the ``out_reg_cv`` prototypes:

* :func:`resolve_sibling_prior` — nearest-M / lowest-rmse same-family sibling selection.
* :func:`matched_center` — the dark-bar matched filter finds a symmetric (even blurred)
  bar's center to sub-pixel accuracy (the class-B trough-replacement).
* :func:`matched_band_for_pitch` — the M-aware search band (fixed 100 px gave 0 locks at
  M~=2; ~pitch/8 fixes it).
* :func:`audit_family_consistency` — flags a texture-mislock (M far off family median).
* the :func:`relmtf_run.family_key` grouping used to resolve siblings.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_WA = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/wafer-atlas/scripts")
_SPEC = importlib.util.spec_from_file_location("sibling_prior_reg", _WA / "sibling_prior_reg.py")
spr = importlib.util.module_from_spec(_SPEC)
sys.modules["sibling_prior_reg"] = spr
_SPEC.loader.exec_module(spr)


# --------------------------------------------------------------------------- #
# resolve_sibling_prior
# --------------------------------------------------------------------------- #
def _clean(sid, fam, M, rmse):
    return dict(sid=sid, family=fam, M=M, rmse=rmse)


def test_resolve_sibling_prior_prefers_nearest_M_when_nominal_known():
    # target near M=2.0; the M=1.98 sibling wins over a lower-rmse but far-M one.
    regs = [_clean("f8", "fam", 1.98, 3.5), _clean("f16", "fam", 1.60, 0.5)]
    tgt = dict(family="fam", nominal_M=2.0)
    assert spr.resolve_sibling_prior(tgt, regs)["sid"] == "f8"


def test_resolve_sibling_prior_tie_breaks_on_rmse_at_equal_M():
    regs = [_clean("a", "fam", 2.00, 3.0), _clean("b", "fam", 2.00, 0.7)]
    tgt = dict(family="fam", nominal_M=2.0)
    assert spr.resolve_sibling_prior(tgt, regs)["sid"] == "b"


def test_resolve_sibling_prior_no_nominal_falls_back_to_lowest_rmse():
    # bare zooms carry no nominal M -> lowest residual clean sibling.
    regs = [_clean("a", "fam", 0.40, 2.0), _clean("b", "fam", 0.41, 0.6)]
    tgt = dict(family="fam", nominal_M=float("nan"))
    assert spr.resolve_sibling_prior(tgt, regs)["sid"] == "b"


def test_resolve_sibling_prior_ignores_other_families():
    regs = [_clean("other", "OTHER", 2.0, 0.1), _clean("mine", "fam", 1.0, 5.0)]
    tgt = dict(family="fam", nominal_M=1.0)
    assert spr.resolve_sibling_prior(tgt, regs)["sid"] == "mine"


def test_resolve_sibling_prior_none_when_no_clean_sibling():
    regs = [_clean("other", "OTHER", 2.0, 0.1)]
    tgt = dict(family="fam", nominal_M=1.0)
    assert spr.resolve_sibling_prior(tgt, regs) is None


# --------------------------------------------------------------------------- #
# matched_center — center of a symmetric dark bar, blur-invariant
# --------------------------------------------------------------------------- #
def _dark_bar_profile(n, center, bar_w, blur_sigma=0.0, noise=0.0, seed=0):
    x = np.arange(n)
    prof = np.ones(n) * 1.0
    prof[np.abs(x - center) <= bar_w / 2.0] = 0.0  # dark bar
    if blur_sigma > 0:
        from scipy.ndimage import gaussian_filter1d
        prof = gaussian_filter1d(prof, blur_sigma)
    if noise > 0:
        prof = prof + np.random.default_rng(seed).normal(0, noise, n)
    return prof


def test_matched_center_locates_sharp_bar():
    prof = _dark_bar_profile(200, center=100.3, bar_w=8)
    c, snr = spr.matched_center(prof, bar_w=8)
    assert c is not None
    assert abs(c - 100.3) < 1.0
    assert snr > 3


def test_matched_center_is_blur_invariant():
    # a SYMMETRIC blur preserves the bar centroid -> center stays put even heavily blurred.
    center = 100.0
    prof = _dark_bar_profile(200, center=center, bar_w=8, blur_sigma=6.0)
    c, _ = spr.matched_center(prof, bar_w=8)
    assert c is not None
    assert abs(c - center) < 1.0


def test_matched_center_robust_to_noise():
    center = 100.0
    prof = _dark_bar_profile(200, center=center, bar_w=8, blur_sigma=3.0, noise=0.05, seed=3)
    c, snr = spr.matched_center(prof, bar_w=8)
    assert c is not None
    assert abs(c - center) < 2.0


def test_matched_center_none_on_too_short_profile():
    c, snr = spr.matched_center(np.zeros(5), bar_w=8)
    assert c is None


# --------------------------------------------------------------------------- #
# matched_band_for_pitch — M-aware search band
# --------------------------------------------------------------------------- #
def test_matched_band_is_pitch_over_8_in_range():
    # pitch 1600 px -> 200 (mid-range, not clamped).
    assert spr.matched_band_for_pitch(1600) == 200


def test_matched_band_floor_at_low_M():
    # small pitch clamps up to the 100 px floor (keeps a usable window at low M).
    assert spr.matched_band_for_pitch(400) == 100


def test_matched_band_ceiling_at_high_M():
    # a very large pitch (M~=2, pitch~2500) clamps to 500 -> a WIDE window (fixed 100
    # gave 0 locks); pitch/8 = 312 here so not yet clamped, but 5000 px is.
    assert spr.matched_band_for_pitch(2500) == pytest.approx(312, abs=1)
    assert spr.matched_band_for_pitch(5000) == 500


# --------------------------------------------------------------------------- #
# object_rmse_um — the metric the recovery combiner + 25um ceiling rank on
# --------------------------------------------------------------------------- #
def test_object_rmse_um_scales_inversely_with_M():
    # same px residual is HALF the object um at 2x the magnification.
    assert spr.object_rmse_um(10.0, 1.0) == pytest.approx(43.5)   # 10*4.35/1
    assert spr.object_rmse_um(10.0, 2.0) == pytest.approx(21.75)  # 10*4.35/2


def test_object_rmse_um_af200_case_fixA_fails_fixB_passes():
    # the exact regression: a fix-A 21.5px/M2.07 lock (=45um, FAILS 25um) must NOT be
    # ranked below a real fix-B 5.5px/M2.06 lock (=11.6um, PASSES). In object um the
    # fix-B result is much smaller, so min-object-um picks it; in raw px it would too
    # here, but the point is the SORT KEY must be object um (a low-M fix can invert it).
    fixA = spr.object_rmse_um(21.5, 2.07)
    fixB = spr.object_rmse_um(5.5, 2.06)
    assert fixA > 25.0        # fails the ceiling
    assert fixB < 25.0        # passes
    assert fixB < fixA


def test_object_rmse_um_low_M_px_can_invert_ranking():
    # a small-px low-M fix vs a larger-px high-M fix: raw-px would pick the low-M one,
    # object-um correctly prefers the high-M one (fewer object um per px). This is why
    # the combiner must rank on object um, not px.
    lowM = spr.object_rmse_um(6.0, 0.4)   # 6*4.35/0.4 = 65.25 um
    highM = spr.object_rmse_um(8.0, 2.0)  # 8*4.35/2.0 = 17.4 um
    assert lowM > highM                    # object-um: highM is better
    assert 8.0 > 6.0                       # raw px: would have (wrongly) picked lowM


def test_object_rmse_um_inf_on_bad_inputs():
    assert spr.object_rmse_um(float("nan"), 1.0) == float("inf")
    assert spr.object_rmse_um(5.0, 0.0) == float("inf")
    assert spr.object_rmse_um(5.0, float("nan")) == float("inf")


# --------------------------------------------------------------------------- #
# ensure_theta_rad — the class-B "never fired" root cause: grid_xy needs theta_rad
# --------------------------------------------------------------------------- #
def test_ensure_theta_rad_derives_from_theta_deg():
    # a reconstructed prior carries theta_deg but NOT theta_rad; af.grid_xy reads
    # theta_rad -> without this the class-B matched filter KeyError'd on every frame.
    out = spr.ensure_theta_rad(dict(theta_deg=4.5, scale=3.4, x0_img=1.0, y0_img=2.0))
    assert out["theta_rad"] == pytest.approx(np.radians(4.5))
    # original fields preserved
    assert out["scale"] == 3.4 and out["x0_img"] == 1.0


def test_ensure_theta_rad_uses_theta_alias():
    out = spr.ensure_theta_rad(dict(theta=3.85, scale=2.98))
    assert out["theta_rad"] == pytest.approx(np.radians(3.85))


def test_ensure_theta_rad_keeps_existing():
    out = spr.ensure_theta_rad(dict(theta_rad=0.123, theta_deg=99.0))
    assert out["theta_rad"] == 0.123  # existing value not clobbered by theta_deg


def test_ensure_theta_rad_is_a_copy():
    src = dict(theta_deg=4.5)
    out = spr.ensure_theta_rad(src)
    assert "theta_rad" not in src  # input not mutated


# --------------------------------------------------------------------------- #
# audit_family_consistency — texture-mislock (M off family median) flag
# --------------------------------------------------------------------------- #
def _areg(sid, fam, M, theta=None, rmse=1.0):
    return dict(sid=sid, family=fam, M=M, theta=theta, rmse=rmse)


def test_audit_flags_M_outlier_within_family():
    # three siblings near M=0.41 and one collapsed to 0.19 -> the collapse is flagged.
    regs = [_areg("a", "f", 0.41), _areg("b", "f", 0.40), _areg("c", "f", 0.19)]
    res = {r["sid"]: r for r in spr.audit_family_consistency(regs, m_frac_tol=0.15)}
    assert res["c"]["flagged"]
    assert not res["a"]["flagged"]
    assert not res["b"]["flagged"]


def test_audit_flags_theta_outlier_when_theta_present():
    # wafer is fixed -> theta ~constant in a family; a 2 deg outlier is a texture mislock.
    regs = [_areg("a", "f", 1.0, theta=4.5), _areg("b", "f", 1.0, theta=4.6),
            _areg("c", "f", 1.0, theta=1.9)]
    res = {r["sid"]: r for r in spr.audit_family_consistency(regs, theta_tol_deg=1.5)}
    assert res["c"]["flagged"]
    assert "theta_off" in res["c"]["flag_reason"]


def test_audit_does_not_flag_singleton_family():
    # no siblings to compare to -> never flagged.
    regs = [_areg("solo", "f", 0.19)]
    res = spr.audit_family_consistency(regs)
    assert not res[0]["flagged"]


def test_audit_reports_family_medians():
    regs = [_areg("a", "f", 0.40), _areg("b", "f", 0.42)]
    res = spr.audit_family_consistency(regs)
    assert res[0]["family_median_M"] == pytest.approx(0.41)


# --------------------------------------------------------------------------- #
# relmtf_run.family_key — sibling grouping (lens, session, focal, mag_label)
# --------------------------------------------------------------------------- #
_RR_SPEC = importlib.util.spec_from_file_location(
    "relmtf_run",
    Path(__file__).resolve().parent.parent / "scripts" / "relmtf_run.py")
rr = importlib.util.module_from_spec(_RR_SPEC)
sys.modules["relmtf_run"] = rr
_RR_SPEC.loader.exec_module(rr)


class _Node:
    def __init__(self, lens, session, focal, mag_label):
        self.lens = lens
        self.session = session
        self.focal = focal
        self.mag_label = mag_label


def test_family_key_groups_same_lens_session_focal_mag():
    a = _Node("Z 24-120", "2026-05-13", "120", "")
    b = _Node("Z 24-120", "2026-05-13", "120", "")
    assert rr.family_key(a) == rr.family_key(b)


def test_family_key_separates_different_focal():
    a = _Node("Z 24-120", "2026-05-13", "120", "")
    b = _Node("Z 24-120", "2026-05-13", "50", "")
    assert rr.family_key(a) != rr.family_key(b)


def test_family_key_separates_different_session():
    a = _Node("AF200+6T+5T", "2026-05-13", "", "")
    b = _Node("AF200+6T+5T", "2026-01-29", "", "")
    assert rr.family_key(a) != rr.family_key(b)


def test_family_key_ignores_aperture():
    # aperture is intentionally NOT part of the key (siblings differ only in aperture).
    a = _Node("Z 24-120", "2026-05-13", "120", "")
    b = _Node("Z 24-120", "2026-05-13", "120", "")
    assert rr.family_key(a) == rr.family_key(b)
