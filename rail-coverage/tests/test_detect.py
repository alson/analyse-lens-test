from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from rail_coverage.detect import (
    CropAnalysis,
    CropStatus,
    ScenarioAnalysis,
    ScenarioStatus,
    analyze_crop,
    analyze_scenario,
    is_flat,
    off_target_by_cross_compare,
    peak_index,
    smooth_sizes,
    truncation_status,
)
from rail_coverage.scan import CropFrame, CropSeries, Scenario


def _series(*sizes: int, name: str = "center") -> CropSeries:
    """Build a CropSeries with sequential seq numbers and the given sizes."""
    frames = [
        CropFrame(seq=i, size=s, path=Path(f"/tmp/{i}.jpg"))
        for i, s in enumerate(sizes)
    ]
    return CropSeries(name=name, frames=frames)


# Realistic stepped bell curve modelled on Sigma 150mm @ 1:1 @ F8 / center.
BELL = [
    88089, 88276, 87961,
    91120, 91103, 91128,
    94812, 94756, 94654,
    100022, 100097, 100053,
    107289, 107445, 107440,
    117244, 117366, 117092,
    126368, 126873, 126399,
    130881, 131047, 130921,
    128252, 128445, 129003,
    122391, 122200, 122057,
    116408, 116772, 116666,
    111131, 111088, 111202,
    106094, 106128, 106266,
    102341, 102466, 102421,
]


class TestSmoothSizes:
    def test_returns_shorter_array(self):
        out = smooth_sizes([1, 2, 3, 4, 5], window=3)
        assert out.shape == (3,)
        np.testing.assert_allclose(out, [2.0, 3.0, 4.0])

    def test_returns_copy_when_too_short(self):
        out = smooth_sizes([1, 2], window=3)
        assert out.shape == (2,)
        np.testing.assert_allclose(out, [1, 2])


class TestPeakIndex:
    def test_finds_centre_of_bell(self):
        # synthetic bell — peak at index 3
        peak = peak_index([1, 2, 4, 6, 4, 2, 1])
        assert peak == 3

    def test_real_bell_curve(self):
        # peak in the realistic Sigma curve is at raw index 22 (seq 953)
        peak = peak_index(BELL)
        assert 21 <= peak <= 23

    def test_monotonic_increasing_peaks_at_end(self):
        peak = peak_index([1, 2, 3, 4, 5, 6, 7, 8])
        assert peak == 6  # smoothed argmax at last full window


class TestTruncationStatus:
    def test_detects_start_truncation(self):
        assert truncation_status(1, 30) == CropStatus.TRUNCATED_START

    def test_detects_end_truncation(self):
        assert truncation_status(28, 30) == CropStatus.TRUNCATED_END

    def test_ok_when_centred(self):
        assert truncation_status(15, 30) == CropStatus.OK

    def test_empty(self):
        assert truncation_status(0, 0) == CropStatus.EMPTY

    @pytest.mark.parametrize("idx", [0, 1, 2, 3, 4, 5])
    def test_first_two_rail_positions_are_truncated(self, idx: int):
        # Default edge_shots=6 (~2 rail positions) flags peaks too close to start
        assert truncation_status(idx, 30) == CropStatus.TRUNCATED_START

    @pytest.mark.parametrize("idx", [24, 25, 26, 27, 28, 29])
    def test_last_two_rail_positions_are_truncated(self, idx: int):
        assert truncation_status(idx, 30) == CropStatus.TRUNCATED_END

    def test_idx_6_is_ok(self):
        # boundary: edge_shots=6 means idx 0..5 truncated; idx 6 is fine
        assert truncation_status(6, 30) == CropStatus.OK


class TestIsFlat:
    def test_bell_curve_is_not_flat(self):
        assert not is_flat(BELL)

    def test_constant_series_is_flat(self):
        assert is_flat([72_000] * 30)

    def test_low_variance_is_flat(self):
        # max/min = 72500/72000 ≈ 1.007 — very flat
        sizes = [72_000, 72_100, 72_500, 72_300, 72_200] * 6
        assert is_flat(sizes)

    def test_empty_returns_false(self):
        assert not is_flat([])


class TestOffTargetByCrossCompare:
    def test_nikon_style_bimodal(self):
        # Real maxes from Nikon 70-180+5T @ 1:1.33 @ F11. The off-target group
        # outnumbers the on-target group, so a median-based cutoff would fail.
        maxes = {
            "center": 128_824,
            "left-edge": 122_623,
            "bottom-edge": 99_953,
            "bottom-left": 102_233,
            "right-edge": 74_109,
            "top-edge": 71_665,
            "top-left": 72_011,
            "top-right": 72_815,
            "bottom-right": 71_833,
        }
        flagged = off_target_by_cross_compare(maxes)
        assert flagged == {
            "right-edge",
            "top-edge",
            "top-left",
            "top-right",
            "bottom-right",
        }

    def test_uniform_returns_empty(self):
        flagged = off_target_by_cross_compare(
            {"a": 100, "b": 100, "c": 100, "d": 100}
        )
        assert flagged == set()

    def test_modest_corner_falloff_not_flagged(self):
        # Honest aperture-driven sharpness variation should NOT be flagged —
        # corners 80% of centre is normal optics, not an off-target crop.
        maxes = {"center": 130_000, "corner": 105_000, "edge": 120_000}
        assert off_target_by_cross_compare(maxes) == set()

    def test_singleton_returns_empty(self):
        # need ≥ 2 crops to compare
        assert off_target_by_cross_compare({"center": 50}) == set()


class TestAnalyzeCrop:
    def test_bell_curve_is_ok(self):
        s = _series(*BELL)
        result = analyze_crop(s, flagged_off_target=False)
        assert result.status == CropStatus.OK
        assert result.n_frames == len(BELL)
        assert result.peak_idx is not None
        assert result.max_size == max(BELL)
        assert result.min_size == min(BELL)
        assert 0.40 < result.peak_pct < 0.70

    def test_monotonic_is_truncated_end(self):
        # Use values with enough dynamic range that is_flat won't fire
        # (max/min ratio >> 1.15).
        s = _series(*range(50_000, 50_000 + 30 * 1000, 1000))
        result = analyze_crop(s, flagged_off_target=False)
        assert result.status == CropStatus.TRUNCATED_END

    def test_decreasing_is_truncated_start(self):
        s = _series(*range(80_000, 50_000, -1000))
        result = analyze_crop(s, flagged_off_target=False)
        assert result.status == CropStatus.TRUNCATED_START

    def test_flagged_overrides_to_off_target(self):
        s = _series(*BELL)
        result = analyze_crop(s, flagged_off_target=True)
        assert result.status == CropStatus.OFF_TARGET
        assert result.peak_idx is None

    def test_flat_profile_is_off_target_even_without_flag(self):
        s = _series(*([72_000] * 30))
        result = analyze_crop(s, flagged_off_target=False)
        assert result.status == CropStatus.OFF_TARGET

    def test_empty_series(self):
        s = CropSeries(name="center", frames=[])
        result = analyze_crop(s, flagged_off_target=False)
        assert result.status == CropStatus.EMPTY
        assert result.n_frames == 0
        assert result.peak_idx is None


class TestAnalyzeScenario:
    def _scn(self, **crops: list[int]) -> Scenario:
        crop_series = [_series(*sizes, name=name) for name, sizes in crops.items()]
        return Scenario(cropped_dir=Path("/tmp/scn/cropped"), crops=crop_series)

    def test_all_ok_rolls_up_ok(self):
        scn = self._scn(center=BELL, left_edge=BELL)
        result = analyze_scenario(scn)
        assert result.status == ScenarioStatus.OK
        assert all(c.status == CropStatus.OK for c in result.crops)

    def test_one_truncated_crop_triggers_reshoot(self):
        # Monotonic series with realistic dynamic range so it isn't flat-flagged.
        truncated = list(range(80_000, 130_000, 2_000))
        scn = self._scn(center=truncated, left_edge=BELL)
        result = analyze_scenario(scn)
        assert result.status == ScenarioStatus.NEEDS_RESHOOT

    def test_off_target_alone_does_not_trigger_reshoot(self):
        # The center crop is flat (off-target) but the on-target crops are fine.
        scn = self._scn(
            center=BELL,
            top_edge=BELL,
            bottom_left=[72_000] * 30,  # flat / off-target
        )
        result = analyze_scenario(scn)
        assert result.status == ScenarioStatus.OK
        names_to_status = {c.name: c.status for c in result.crops}
        assert names_to_status["bottom_left"] == CropStatus.OFF_TARGET

    def test_cross_compare_off_target_then_no_truncation_check(self):
        # A "low" series with just enough dynamic range to NOT be is_flat-
        # flagged on its own — cross-compare alone should still catch it,
        # because its peak is far below the on-target crops'.
        low_monotone = list(range(40_000, 70_000, 1_000))
        scn = self._scn(
            center=BELL,
            left_edge=BELL,
            top_edge=BELL,
            top_left=low_monotone,
        )
        result = analyze_scenario(scn)
        names_to_status = {c.name: c.status for c in result.crops}
        assert names_to_status["top_left"] == CropStatus.OFF_TARGET
        assert result.status == ScenarioStatus.OK


class TestScenarioAnalysisHelpers:
    def test_truncated_and_off_target_filters(self):
        a = ScenarioAnalysis(
            cropped_dir=Path("/x"),
            status=ScenarioStatus.NEEDS_RESHOOT,
            crops=[
                CropAnalysis("c1", CropStatus.OK, 30, 15, 0.5, 1, 1),
                CropAnalysis("c2", CropStatus.TRUNCATED_END, 30, 28, 0.97, 1, 1),
                CropAnalysis("c3", CropStatus.OFF_TARGET, 30, None, None, 1, 1),
            ],
        )
        assert [c.name for c in a.truncated_crops] == ["c2"]
        assert [c.name for c in a.off_target_crops] == ["c3"]
