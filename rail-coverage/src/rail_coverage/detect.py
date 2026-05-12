"""Per-scenario sharpness analysis for the offline rail-coverage tool.

The five numerical primitives (``smooth``, ``peak_index``,
``truncation_status``, ``is_flat``, ``off_target_by_cross_compare``)
plus ``CropStatus`` come from ``lens-test-detect-core``. The live
``sharpness`` package (in ``run-lens-test/``) imports the same
primitives so both tools speak the same language about bell curves.

This module keeps the offline-specific scaffolding: ``CropAnalysis``
and ``ScenarioAnalysis`` aggregates, the per-scenario rollup that
classifies the whole (lens, mag, focal, aperture) tuple as ``OK`` or
``NEEDS_RESHOOT``, and the offline defaults for ``edge_shots`` and the
off-target factor. Edge-zone size is 6 here because the offline data
has ~3 shots per rail position, vs the live module's 1 shot per rail
step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from lens_test_detect_core import (
    CropStatus,
    is_flat,
    off_target_by_cross_compare,
    peak_index,
    smooth,
)
from lens_test_detect_core import truncation_status as _truncation_status_core

from rail_coverage.scan import CropSeries, Scenario


__all__ = [
    "CropAnalysis",
    "CropStatus",
    "ScenarioAnalysis",
    "ScenarioStatus",
    "analyze_crop",
    "analyze_scenario",
    "is_flat",
    "off_target_by_cross_compare",
    "peak_index",
    "smooth_sizes",
    "truncation_status",
]

# Offline defaults: ~3 shots per rail position in the source data, so an
# "edge zone" of 6 raw shots ≈ 2 rail positions of buffer. The live
# package uses 2 because it sees one shot per rail step.
DEFAULT_EDGE_SHOTS = 6
DEFAULT_OFF_TARGET_FACTOR = 0.25


# Backwards-compat alias for the old name. The shared primitive is just
# called ``smooth``; rail-coverage code historically called it
# ``smooth_sizes`` so existing imports keep working.
smooth_sizes = smooth


def truncation_status(
    peak_idx: int,
    n: int,
    *,
    edge_shots: int = DEFAULT_EDGE_SHOTS,
) -> CropStatus:
    """Offline wrapper around the shared primitive.

    The shared primitive is unopinionated about the edge-zone size. The
    offline data has ~3 shots per rail position, so the default here is
    6 (≈ 2 rail positions). The argument is named ``edge_shots`` to
    make that granularity explicit at the call site.
    """
    return _truncation_status_core(peak_idx, n, edge_steps=edge_shots)


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


# --- top-level analysis -------------------------------------------------


def analyze_crop(
    crop: CropSeries,
    *,
    flagged_off_target: bool,
    edge_shots: int = DEFAULT_EDGE_SHOTS,
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
    cross_compare_factor: float = DEFAULT_OFF_TARGET_FACTOR,
    edge_shots: int = DEFAULT_EDGE_SHOTS,
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
