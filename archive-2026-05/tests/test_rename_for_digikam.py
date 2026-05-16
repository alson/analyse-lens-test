"""Unit tests for rename_for_digikam pure helpers."""

from __future__ import annotations

import pytest

from archive_2026_05.rename_for_digikam import (
    build_digikam_name,
    format_aperture,
    format_focal_length,
    format_magnification,
    sanitise_filename_component,
)


class TestFormatMagnification:
    """Reproduce the existing 2026-01-29 / 2026-02-18 dir naming."""

    @pytest.mark.parametrize("mag, expected", [
        (1.0,    "1_1"),
        (1.3,    "1.3_1"),
        (1.27,   "1.27_1"),
        (1.4,    "1.4_1"),
        (2.0,    "2_1"),
        (1.0 / 2.60, "1_2.6"),
        (1.0 / 1.19, "1_1.19"),
        (1.0 / 2.47, "1_2.47"),
        (1.07,   "1.07_1"),
    ])
    def test_known_values(self, mag: float, expected: str) -> None:
        assert format_magnification(mag) == expected

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            format_magnification(0)
        with pytest.raises(ValueError):
            format_magnification(-1.0)
        with pytest.raises(ValueError):
            format_magnification(float("nan"))


class TestFormatAperture:
    @pytest.mark.parametrize("inp, out", [
        ("f/5.6", "F5.6"),
        ("f/11",  "F11"),
        ("f/8",   "F8"),
        ("f/4",   "F4"),
        ("f/16",  "F16"),
        ("F/2.8", "F2.8"),    # case-insensitive
    ])
    def test_known_apertures(self, inp: str, out: str) -> None:
        assert format_aperture(inp) == out

    def test_strips_trailing_zero(self) -> None:
        # Some shots.csv entries have "f/8.0" — should become "F8".
        assert format_aperture("f/8.0") == "F8"
        assert format_aperture("f/11.0") == "F11"

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            format_aperture("bogus")


class TestFormatFocalLength:
    def test_one_decimal(self) -> None:
        assert format_focal_length(150.0) == "150.0 mm"
        assert format_focal_length(105.0) == "105.0 mm"
        assert format_focal_length(120.0) == "120.0 mm"

    def test_partial_focal(self) -> None:
        assert format_focal_length(120.5) == "120.5 mm"


class TestSanitiseFilename:
    def test_passes_clean_chars(self) -> None:
        assert sanitise_filename_component(
            "NIKKOR Z MC 105mm f_2.8 VR S + 61mm extension"
        ) == "NIKKOR Z MC 105mm f_2.8 VR S + 61mm extension"

    def test_replaces_slashes(self) -> None:
        assert sanitise_filename_component("a/b\\c") == "a_b_c"

    def test_replaces_control_chars(self) -> None:
        # Common forbidden chars on at least one FS.
        assert sanitise_filename_component("a:b|c") == "a_b_c"
        assert sanitise_filename_component("a<b>c") == "a_b_c"


class TestBuildDigikamName:
    def test_canonical_example(self) -> None:
        # Matches a real 2026-01-29 filename shape.
        name = build_digikam_name(
            seq=3211,
            slug="Sigma APO Macro 150mm F2.8 EX DG OS HSM",
            mag_label="1_1",
            focal_mm=150.0,
            aperture="f/11",
            original_filename="alm-20260130-212359-655.jpg",
        )
        assert name == (
            "03211|Sigma APO Macro 150mm F2.8 EX DG OS HSM"
            "|1_1|150.0 mm|F11|alm-20260130-212359-655.jpg"
        )

    def test_runner_step_filename(self) -> None:
        # The 2026-05 runner names its captures step_NNNN[_bc].jpg.
        name = build_digikam_name(
            seq=1,
            slug="NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension",
            mag_label="1_2.1",
            focal_mm=400.0,
            aperture="f/8",
            original_filename="step_0127.jpg",
        )
        assert name == (
            "00001|NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension"
            "|1_2.1|400.0 mm|F8|step_0127.jpg"
        )

    def test_zero_padded_5_digits(self) -> None:
        assert build_digikam_name(
            seq=1, slug="X", mag_label="1_1", focal_mm=50.0,
            aperture="f/4", original_filename="y.jpg",
        ).startswith("00001|")
        assert build_digikam_name(
            seq=99999, slug="X", mag_label="1_1", focal_mm=50.0,
            aperture="f/4", original_filename="y.jpg",
        ).startswith("99999|")
