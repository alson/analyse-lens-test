from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np

from rail_coverage.scan import CropSeries, Scenario


class CropStatus(str, Enum):
    OK = "OK"
    TRUNCATED_START = "TRUNCATED_START"
    TRUNCATED_END = "TRUNCATED_END"
    OFF_TARGET = "OFF_TARGET"
    EMPTY = "EMPTY"

    @property
    def is_truncated(self) -> bool:
        return self in (CropStatus.TRUNCATED_START, CropStatus.TRUNCATED_END)


class ScenarioStatus(str, Enum):
    OK = "OK"
    NEEDS_RESHOOT = "NEEDS_RESHOOT"


@dataclass(frozen=True)
class CropAnalysis:
    name: str
    status: CropStatus
    n_frames: int
    peak_idx: int | None
    peak_pct: float | None  # 0.0 = first, 1.0 = last
    max_size: int | None
    min_size: int | None


@dataclass
class ScenarioAnalysis:
    cropped_dir: Path
    status: ScenarioStatus
    crops: list[CropAnalysis] = field(default_factory=list)

    @property
    def truncated_crops(self) -> list[CropAnalysis]:
        return [c for c in self.crops if c.status.is_truncated]

    @property
    def off_target_crops(self) -> list[CropAnalysis]:
        return [c for c in self.crops if c.status == CropStatus.OFF_TARGET]


# --- pure helpers --------------------------------------------------------


def smooth_sizes(sizes: list[int] | np.ndarray, window: int = 3) -> np.ndarray:
    """Centred moving average of width ``window``.

    Returns an array of length ``len(sizes) - window + 1``. With the default
    window of 3 (one rail position = 3 shots) this gives the smoothed
    bell-curve over rail positions.
    """
    arr = np.asarray(sizes, dtype=float)
    if arr.size < window:
        return arr.copy()
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(arr, kernel, mode="valid")


def peak_index(sizes: list[int] | np.ndarray, window: int = 3) -> int:
    """Index (in the *raw* series) of the smoothed peak.

    A 3-wide moving average shifts indices by 1, so the returned index is
    ``argmax(smoothed) + (window - 1) // 2``.
    """
    smoothed = smooth_sizes(sizes, window=window)
    if smoothed.size == 0:
        return 0
    offset = (window - 1) // 2
    return int(np.argmax(smoothed)) + offset


def truncation_status(
    peak_idx: int,
    n: int,
    *,
    edge_shots: int = 3,
) -> CropStatus:
    """Classify a peak position as TRUNCATED_START, TRUNCATED_END, or OK.

    ``edge_shots`` defines the size of the "edge zone" — by default the first
    3 / last 3 raw shots (one rail position).
    """
    if n == 0:
        return CropStatus.EMPTY
    if peak_idx < edge_shots:
        return CropStatus.TRUNCATED_START
    if peak_idx > n - 1 - edge_shots:
        return CropStatus.TRUNCATED_END
    return CropStatus.OK


def is_flat(sizes: list[int] | np.ndarray, *, ratio_threshold: float = 1.15) -> bool:
    """True if the size series varies less than ``ratio_threshold`` (max/min).

    A bell-curve scenario shows max/min ≈ 1.6; a crop covering only
    out-of-focus background varies much less.
    """
    arr = np.asarray(sizes, dtype=float)
    if arr.size == 0 or arr.min() <= 0:
        return False
    return float(arr.max() / arr.min()) < ratio_threshold


def off_target_by_cross_compare(
    crop_maxes: dict[str, int],
    *,
    factor: float = 0.65,
) -> set[str]:
    """Crops whose peak file size is below ``factor × best`` across the scenario.

    The reference is the *maximum* peak across all crops, not the median:
    when more than half the crops miss the wafer (common at low magnifications
    where the wafer doesn't fill the frame), a median-based cutoff sits
    inside the off-target cluster and flags nothing.

    Threshold of 0.65 derived from the Nikon 70-180+5T @ 1:1.33 @ F11 sample:
    on-target peaks 100–128 KB (best 128 KB), off-target peaks 71–74 KB.
    Cutoff at 0.65 × 128 KB ≈ 83 KB cleanly separates the two groups while
    leaving honest aperture-driven variation (e.g. 103 KB corners vs 130 KB
    centre on the Sigma scenario) on the on-target side.
    """
    if len(crop_maxes) < 2:
        return set()
    values = list(crop_maxes.values())
    cutoff = max(values) * factor
    return {name for name, m in crop_maxes.items() if m < cutoff}


# --- top-level analysis -------------------------------------------------


def analyze_crop(
    crop: CropSeries,
    *,
    flagged_off_target: bool,
    edge_shots: int = 3,
) -> CropAnalysis:
    """Build a CropAnalysis for one crop subfolder."""
    sizes = [f.size for f in crop.frames]
    n = len(sizes)
    if n == 0:
        return CropAnalysis(
            name=crop.name,
            status=CropStatus.EMPTY,
            n_frames=0,
            peak_idx=None,
            peak_pct=None,
            max_size=None,
            min_size=None,
        )
    if flagged_off_target or is_flat(sizes):
        return CropAnalysis(
            name=crop.name,
            status=CropStatus.OFF_TARGET,
            n_frames=n,
            peak_idx=None,
            peak_pct=None,
            max_size=max(sizes),
            min_size=min(sizes),
        )
    pk = peak_index(sizes)
    pct = pk / max(1, n - 1)
    status = truncation_status(pk, n, edge_shots=edge_shots)
    return CropAnalysis(
        name=crop.name,
        status=status,
        n_frames=n,
        peak_idx=pk,
        peak_pct=pct,
        max_size=max(sizes),
        min_size=min(sizes),
    )


def analyze_scenario(
    scenario: Scenario,
    *,
    cross_compare_factor: float = 0.6,
    edge_shots: int = 3,
) -> ScenarioAnalysis:
    """Analyze every crop in a scenario and roll up an overall status."""
    crop_maxes: dict[str, int] = {}
    for crop in scenario.crops:
        if crop.frames:
            crop_maxes[crop.name] = max(f.size for f in crop.frames)
    cross_offtarget = off_target_by_cross_compare(
        crop_maxes, factor=cross_compare_factor
    )

    crops: list[CropAnalysis] = []
    for crop in scenario.crops:
        analysis = analyze_crop(
            crop,
            flagged_off_target=crop.name in cross_offtarget,
            edge_shots=edge_shots,
        )
        crops.append(analysis)

    status = (
        ScenarioStatus.NEEDS_RESHOOT
        if any(c.status.is_truncated for c in crops)
        else ScenarioStatus.OK
    )
    return ScenarioAnalysis(
        cropped_dir=scenario.cropped_dir, status=status, crops=crops
    )
