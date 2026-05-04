from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from typing import Iterable

from jinja2 import Environment, PackageLoader, select_autoescape

from rail_coverage.detect import (
    CropAnalysis,
    CropStatus,
    ScenarioAnalysis,
    ScenarioStatus,
)
from rail_coverage.labels import ScenarioLabel, aperture_sort_key, parse_scenario_label


@dataclass(frozen=True)
class CropRow:
    name: str
    status_label: str
    status_class: str
    peak_pct: str
    max_kb: str
    min_kb: str
    chart_src: str
    is_off_target: bool


@dataclass(frozen=True)
class ScenarioRow:
    label: ScenarioLabel
    cropped_dir: Path
    scenario_status: str
    scenario_status_class: str
    n_truncated: int
    n_off_target: int
    anchor: str
    crops: list[CropRow]
    truncated_crop_names: list[str]
    representative_chart: str | None


def _crop_status_class(status: CropStatus) -> str:
    if status.is_truncated:
        return "truncated"
    if status == CropStatus.OFF_TARGET:
        return "offtarget"
    if status == CropStatus.EMPTY:
        return "empty"
    return "ok"


def _kb(n: int | None) -> str:
    return "" if n is None else f"{n / 1024:.0f}"


def _pct(p: float | None) -> str:
    return "" if p is None else f"{p * 100:.0f}%"


def _crop_chart_src(slug: str, crop_name: str) -> str:
    return f"assets/charts/{slug}/{crop_name}.png"


def build_crop_row(crop: CropAnalysis, slug: str) -> CropRow:
    return CropRow(
        name=crop.name,
        status_label=crop.status.value,
        status_class=_crop_status_class(crop.status),
        peak_pct=_pct(crop.peak_pct),
        max_kb=_kb(crop.max_size),
        min_kb=_kb(crop.min_size),
        chart_src=_crop_chart_src(slug, crop.name) if crop.n_frames else "",
        is_off_target=crop.status == CropStatus.OFF_TARGET,
    )


def _representative_truncated_crop(crops: list[CropAnalysis]) -> CropAnalysis | None:
    """Pick the crop whose peak is closest to an edge (most truncated).

    Used as the single chart shown in ``reshoot.html``. Falls back to ``None``
    if no on-target truncated crop exists.
    """
    truncated = [c for c in crops if c.status.is_truncated and c.peak_pct is not None]
    if not truncated:
        return None
    return min(truncated, key=lambda c: min(c.peak_pct, 1 - c.peak_pct))


def build_scenario_row(
    analysis: ScenarioAnalysis,
    *,
    slug: str,
    label: ScenarioLabel | None = None,
) -> ScenarioRow:
    if label is None:
        label = parse_scenario_label(analysis.cropped_dir)
    crops = [build_crop_row(c, slug) for c in analysis.crops]
    truncated_names = [c.name for c in analysis.truncated_crops]
    rep = _representative_truncated_crop(analysis.crops)
    return ScenarioRow(
        label=label,
        cropped_dir=analysis.cropped_dir,
        scenario_status=analysis.status.value,
        scenario_status_class=(
            "needs-reshoot"
            if analysis.status == ScenarioStatus.NEEDS_RESHOOT
            else "ok"
        ),
        n_truncated=len(analysis.truncated_crops),
        n_off_target=len(analysis.off_target_crops),
        anchor=slug,
        crops=crops,
        truncated_crop_names=truncated_names,
        representative_chart=(
            _crop_chart_src(slug, rep.name) if rep is not None else None
        ),
    )


def sort_rows_for_summary(rows: Iterable[ScenarioRow]) -> list[ScenarioRow]:
    """NEEDS_RESHOOT first, then by lens / magnification / focal / aperture."""

    def key(r: ScenarioRow):
        primary = 0 if r.scenario_status == ScenarioStatus.NEEDS_RESHOOT.value else 1
        return (
            primary,
            r.label.lens,
            -r.label.magnification_value,  # higher mag first within lens
            r.label.focal_length,
            aperture_sort_key(r.label.aperture),
        )

    return sorted(rows, key=key)


def sort_rows_for_reshoot(rows: Iterable[ScenarioRow]) -> list[ScenarioRow]:
    """Group by lens for the reshoot session, then by magnification / focal / aperture."""

    def key(r: ScenarioRow):
        return (
            r.label.lens,
            -r.label.magnification_value,
            r.label.focal_length,
            aperture_sort_key(r.label.aperture),
        )

    return sorted(rows, key=key)


def lens_breakdown(rows: Iterable[ScenarioRow]) -> list[tuple[str, int]]:
    counts = Counter(r.label.lens for r in rows)
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))


def _env() -> Environment:
    return Environment(
        loader=PackageLoader("rail_coverage", "templates"),
        autoescape=select_autoescape(["html", "xml", "j2"]),
    )


def render_report(
    rows: list[ScenarioRow],
    *,
    source: str,
    generated_at: str,
) -> str:
    sorted_rows = sort_rows_for_summary(rows)
    counts = Counter(r.scenario_status for r in sorted_rows)
    any_focal = any(r.label.focal_length for r in sorted_rows)
    template = _env().get_template("report.html.j2")
    return template.render(
        rows=sorted_rows,
        source=source,
        generated_at=generated_at,
        total=len(sorted_rows),
        count_ok=counts.get(ScenarioStatus.OK.value, 0),
        count_reshoot=counts.get(ScenarioStatus.NEEDS_RESHOOT.value, 0),
        any_focal=any_focal,
    )


def render_reshoot(
    rows: list[ScenarioRow],
    *,
    generated_at: str,
) -> str:
    reshoot_rows = [
        r for r in rows if r.scenario_status == ScenarioStatus.NEEDS_RESHOOT.value
    ]
    sorted_rows = sort_rows_for_reshoot(reshoot_rows)
    by_lens: list[tuple[str, list[ScenarioRow]]] = [
        (lens, list(group))
        for lens, group in groupby(sorted_rows, key=lambda r: r.label.lens)
    ]
    breakdown = lens_breakdown(sorted_rows)
    # Total distinct lenses across ALL scenarios (not just truncated ones)
    # so the reshoot summary can read "X of Y lenses need reshoot".
    total_lenses = len({r.label.lens for r in rows})
    template = _env().get_template("reshoot.html.j2")
    return template.render(
        rows=sorted_rows,
        rows_by_lens=by_lens,
        lens_breakdown=breakdown,
        n_lenses=len(breakdown),
        total_lenses=total_lenses,
        total=len(sorted_rows),
        total_scenarios=len(rows),
        generated_at=generated_at,
    )
