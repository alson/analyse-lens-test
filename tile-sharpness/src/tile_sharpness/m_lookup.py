"""Resolve measured magnification (M) for a sweep.

Phase 1 of the LSF + maze-FFT pipeline (SHARPNESS_METRICS.md
"2026-05-16 update") is M-driven: ROI sizes for both metrics scale with
the measured magnification, and the subject-space MTF50 conversion is
``mtf50_sensor × M × 229.9`` on Z7. M comes from the wafer-manifest
CSVs produced by ``archive-2026-05.measure_wafer_squares``; we fall
back to the path-encoded ``claimed_mag`` when no manifest covers the
sweep (`m_source == "path_parsed"`).

Precedence mirrors ``archive_2026_05.rename_for_digikam._select_measured_mag``:
``vision_measured_mag`` > ``algo_measured_mag`` (high-confidence only) >
``claimed_mag`` > path-parsed mag-label.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .sweeps import Sweep


@dataclass(frozen=True)
class MagLookup:
    measured: float
    source: str         # "vision" | "algo_high" | "algo_medium" | "claimed" | "path_parsed"
    confidence: str     # forwarded from the source row (or "" when path-parsed)


def parse_mag_label(mag_str: str) -> float:
    """Convert a ``<num>_<denom>`` mag-label dir name to a float ratio.

    Mirrors ``archive_2026_05.measure_wafer_squares.parse_mag_label`` so
    the two pipelines agree on the path-encoded fallback value.
    """
    if "_" not in mag_str:
        return float("nan")
    a, b = mag_str.split("_", 1)
    try:
        return float(a) / float(b)
    except ValueError:
        return float("nan")


def mag_label_from_sweep_label(label: str) -> str | None:
    """Extract the ``mag_label`` part from a tile-sharpness Sweep.label.

    Bare-prime layout: ``<root>__<slugified_lens>__<mag>__<F-aperture>``.
    Zoom layout:      ``<root>__<slugified_lens>__<mag>__<focal>__<F-aperture>``.

    Newer-rig labels don't carry mag in the label name (it's a session-
    level concept tracked in shots.csv) — return None for those.
    """
    parts = label.split("__")
    if len(parts) < 4:
        return None
    candidate = parts[2]
    # mag_label looks like "<num>_<denom>" or "<num>_<denom>-resized".
    # If it parses to a finite float it's a mag label.
    bare = candidate.removesuffix("-resized")
    if "_" not in bare:
        return None
    try:
        a, b = bare.split("_", 1)
        float(a) / float(b)
    except ValueError:
        return None
    return candidate


class MLookup:
    """In-memory index of manifest rows, keyed by ``(slug, mag_label)``.

    Multiple manifest CSVs can be loaded into one MLookup; later files
    override earlier ones for duplicate keys (so per-session refinements
    win over bulk runs).
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict[str, str]] = {}

    def add_csv(self, path: Path) -> int:
        n = 0
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row.get("slug", ""), row.get("mag_label", ""))
                if not key[0] or not key[1]:
                    continue
                self._rows[key] = row
                n += 1
        return n

    def get(self, slug: str, mag_label: str) -> dict[str, str] | None:
        return self._rows.get((slug, mag_label))

    def __len__(self) -> int:
        return len(self._rows)


def load_manifests(paths: list[Path]) -> MLookup:
    """Build an MLookup by reading every manifest CSV in ``paths``."""
    mlookup = MLookup()
    for p in paths:
        mlookup.add_csv(p)
    return mlookup


def _select_from_row(row: dict[str, str]) -> tuple[float | None, str, str]:
    """Apply the precedence policy to a single manifest row.

    Returns ``(measured_mag, source, confidence)`` or ``(None, "", "")``
    when no usable value is present.
    """
    vision = (row.get("vision_measured_mag") or "").strip()
    if vision:
        try:
            return float(vision), "vision", (row.get("vision_confidence") or "").strip()
        except ValueError:
            pass
    algo = (row.get("algo_measured_mag") or "").strip()
    conf = (row.get("algo_confidence") or "").strip()
    if algo:
        try:
            value = float(algo)
        except ValueError:
            value = None
        if value is not None:
            if conf == "high":
                return value, "algo_high", conf
            if conf == "medium":
                return value, "algo_medium", conf
            # "low" confidence: fall through to claimed_mag
    claimed = (row.get("claimed_mag") or "").strip()
    if claimed:
        try:
            return float(claimed), "claimed", ""
        except ValueError:
            pass
    return None, "", ""


def resolve(sweep: Sweep, mlookup: MLookup) -> MagLookup:
    """Resolve M for ``sweep``; fall back to path-parsed ``claimed_mag``.

    ``sweep.lens`` is the raw lens-config name (with spaces) and matches
    the manifest ``slug`` directly. The ``mag_label`` is extracted from
    the sweep label.
    """
    mag_label = mag_label_from_sweep_label(sweep.label)
    if mag_label is not None:
        row = mlookup.get(sweep.lens, mag_label)
        if row is not None:
            measured, source, confidence = _select_from_row(row)
            if measured is not None:
                return MagLookup(measured=measured, source=source, confidence=confidence)
    # Fallback: path-parsed mag label only.
    if mag_label is not None:
        m = parse_mag_label(mag_label)
        if m == m and m > 0:  # noqa: PLR0124 -- NaN-safe finite check
            return MagLookup(measured=m, source="path_parsed", confidence="")
    return MagLookup(measured=float("nan"), source="", confidence="")
