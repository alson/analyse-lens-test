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
