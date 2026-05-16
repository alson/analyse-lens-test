"""Validation tests for measure_wafer_squares against ground-truth
magnification labels in 2026-01-29.

The path-encoded magnification (e.g. ``1.3_1`` → 1.3×) is the ground
truth from the user's manual GIMP measurements at archival time.

Threshold: 10 % mean absolute deviation. Most configs come in well
under that (median ~3 %); a few outliers (typically labelled
duplicates, e.g. TC-1401 at both 1:1 and 1.4:1) drag the mean up
slightly but stay under 10 %.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from archive_2026_05.measure_wafer_squares import (
    detect_tilt_via_gradient,
    detect_wafer_mask,
    extract_long_line_columns,
    load_gray,
    measure,
    parse_mag_label,
    sharpest_f11_centre_crop,
)

import numpy as np


# ---- Pure helpers ---------------------------------------------------------


class TestParseMagLabel:
    def test_simple_ratio(self) -> None:
        assert parse_mag_label("1_1") == 1.0
        assert parse_mag_label("1.3_1") == 1.3
        assert parse_mag_label("1_2.47") == pytest.approx(0.4048, abs=1e-3)
        assert parse_mag_label("2_1") == 2.0

    def test_malformed_returns_nan(self) -> None:
        import math
        assert math.isnan(parse_mag_label(""))
        assert math.isnan(parse_mag_label("not_a_ratio"))


# ---- Validation against 2026-01-29 ground truth ---------------------------


VALIDATION_ROOT = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29"
)
ANCHOR_SLUG = "Sigma APO Macro 150mm F2.8 EX DG OS HSM"


@pytest.fixture(scope="module")
def anchor_period() -> float:
    if not VALIDATION_ROOT.exists():
        pytest.skip(f"{VALIDATION_ROOT} not on disk")
    anchor_dir = VALIDATION_ROOT / ANCHOR_SLUG / "1_1"
    f = sharpest_f11_centre_crop(anchor_dir)
    if f is None:
        pytest.skip(f"no anchor frame at {anchor_dir}")
    m = measure(f)
    assert m.period_px is not None, f"anchor measurement failed: {m.reason}"
    return m.period_px


# Hand-picked cases covering the full magnification range. The
# tolerances reflect the realistic algorithm accuracy plus possible
# 1-decimal-place rounding in the path-encoded GT.
VALIDATION_CASES = [
    # (slug, mag-dir, expected magnification, tolerance %)
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM",         "1_1",    1.000,  3.0),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T",    "1.3_1",  1.300,  8.0),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + 6T",    "1.6_1",  1.600,  10.0),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + 6T + 5T", "1.8_1", 1.800, 10.0),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM",             "1_1",    1.000,  8.0),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + 5T",        "1.27_1", 1.27,   8.0),
    ("NIKKOR Z MC 105mm f_2.8 VR S",                    "1_1",    1.000,  8.0),
    ("NIKKOR Z MC 105mm f_2.8 VR S + 5T",               "1.2_1",  1.200,  8.0),
    ("NIKKOR Z MC 105mm f_2.8 VR S + 6T",               "1.4_1",  1.400,  8.0),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 5T",     "1.4_1",  1.400,  8.0),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 6T",     "1.7_1",  1.700,  8.0),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 5T + 6T", "2_1",   2.000,  8.0),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 6T + 5T", "2_1",   2.000,  8.0),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D",  "1.07_1", 1.07,  10.0),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 5T",    "1_1.19", 1/1.19, 10.0),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T",    "1.27_1", 1.27,  10.0),
]


@pytest.mark.parametrize("slug, mag_dir, expected_mag, tol_pct", VALIDATION_CASES)
def test_measured_magnification(
    slug: str, mag_dir: str, expected_mag: float, tol_pct: float,
    anchor_period: float,
) -> None:
    if not VALIDATION_ROOT.exists():
        pytest.skip(f"{VALIDATION_ROOT} not on disk")
    config_dir = VALIDATION_ROOT / slug / mag_dir
    if not config_dir.is_dir():
        pytest.skip(f"{config_dir} not on disk")
    f = sharpest_f11_centre_crop(config_dir)
    assert f is not None, f"no sharpest F11 frame at {config_dir}"
    m = measure(f)
    assert m.period_px is not None, f"measurement failed: {m.reason}"
    measured_mag = m.period_px / anchor_period
    error_pct = abs(measured_mag - expected_mag) / expected_mag * 100
    assert error_pct <= tol_pct, (
        f"{slug}/{mag_dir}: measured {measured_mag:.3f}× vs expected "
        f"{expected_mag:.3f}× (error {error_pct:.1f}%, tol {tol_pct:.1f}%)"
    )


# ---- Regression: tilt-detector aliasing-spike suppression ------------------

# A 55mm AIS 537016 / 1_1 / F5.6 frame whose tilt result was +0.12° before the
# fix (the algo's central-bin spike from Lanczos-downsample aliasing of tilted
# scribes), while the true tilt is ~+4° (every well-focused frame in the same
# dir + GIMP-measured scribe angle of 4.27°). After zeroing the 0°-adjacent
# bins the detector recovers the real peak.
TILT_ZERO_BIN_FRAME = (
    VALIDATION_ROOT
    / "Nikon Micro-Nikkor 55mm f_2.8 AIS 537016"
    / "1_1" / "F5.6"
    / "16461|Nikon Micro-Nikkor 55mm f_2.8 AIS 537016|1_1|55.0 mm|F5.6|alm-20260205-115105-243.jpg"
)


def test_detect_tilt_via_gradient_recovers_real_peak_past_aliasing_spike() -> None:
    """Without the 0°-bin suppression this frame returns +0.12° — a
    single-bin pile-up from downsample aliasing dominating a weak real
    signal at +4°. With suppression the detector returns a value in
    the +3-5° band, matching every well-focused sibling frame."""
    if not TILT_ZERO_BIN_FRAME.exists():
        pytest.skip(f"{TILT_ZERO_BIN_FRAME} not on disk")
    img = load_gray(TILT_ZERO_BIN_FRAME)
    masked = img[detect_wafer_mask(img)]
    tilt = detect_tilt_via_gradient(masked)
    assert 3.0 < tilt < 5.0, (
        f"expected tilt in (+3°, +5°), got {tilt:+.2f}° — "
        f"without the fix this frame returns +0.12°"
    )


# ---- Regression: scribe-gap-bridge retry -----------------------------------

# A 55mm AIS 537016 / 1_1 / F11 frame where shallow lighting brings out dust
# spots on the wafer; the dust visibly interrupts scribes into segments
# shorter than the 40%-of-height long-line opening's threshold, so the
# primary pipeline returns 0 peaks and the FFT fallback locks onto a 2x
# harmonic (returns 2.247×). With the retry that pre-bridges short gaps via
# binary_closing the algorithm recovers the true ~1.0× measurement.
GAP_BRIDGE_FRAME = (
    VALIDATION_ROOT
    / "Nikon Micro-Nikkor 55mm f_2.8 AIS 537016"
    / "1_1" / "F11"
    / "16667|Nikon Micro-Nikkor 55mm f_2.8 AIS 537016|1_1|55.0 mm|F11|alm-20260205-121401-466.jpg"
)


def test_measure_gap_bridge_recovers_dust_broken_scribes(
    anchor_period: float,
) -> None:
    """The picked-sharpest-F11 frame from this dir has scribes
    interrupted by dust-spot reflections; primary long-line opening
    returns 0 peaks at the default L=40% threshold. The retry with
    gap_bridge_px=15 recovers 6 peaks and a magnification close to
    the true 1.0× (matches every other measurable F11/F16 frame in
    the same dir + GIMP-verified manual measurement)."""
    if not GAP_BRIDGE_FRAME.exists():
        pytest.skip(f"{GAP_BRIDGE_FRAME} not on disk")
    m = measure(GAP_BRIDGE_FRAME)
    assert m.period_px is not None, (
        f"measurement still failed after gap-bridge retry: reason={m.reason!r}"
    )
    mag = m.period_px / anchor_period
    assert 0.93 < mag < 1.08, (
        f"expected ~1.0×, got {mag:.3f}× (period={m.period_px:.2f}, "
        f"n_lines={m.n_lines}, reason={m.reason!r}). Without the retry "
        f"this frame returns 2.247× via FFT fallback."
    )
    # Sanity: the retry mechanism should have been triggered (the
    # primary couldn't have found 4 peaks here).
    assert "gap_bridge" in m.reason, (
        f"expected the retry path to fire (gap_bridge in reason), "
        f"got reason={m.reason!r}"
    )


def test_detect_tilt_via_gradient_handles_no_signal() -> None:
    """Edge case: an image with no detectable edges anywhere in the
    detector's window must not raise. Returning either of the
    zeroed-out central bins after suppression would mean the function
    crashes on argmax of an all-zero array; instead argmax falls back
    to a non-zeroed bin (here the first one)."""
    flat = np.zeros((64, 64), dtype=np.float32)
    tilt = detect_tilt_via_gradient(flat)
    # On a flat input, all-zero histogram → np.histogram + suppression
    # leaves everything zero; argmax returns 0 → the most negative bin
    # centre. Just check it didn't raise and returned something sane.
    assert -7.0 < tilt < 7.0
