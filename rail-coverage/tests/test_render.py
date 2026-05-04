from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from rail_coverage.detect import (
    CropAnalysis,
    CropStatus,
    ScenarioAnalysis,
    ScenarioStatus,
)
from rail_coverage.labels import ScenarioLabel
from rail_coverage.render import (
    CropRow,
    ScenarioRow,
    build_crop_row,
    build_scenario_row,
    lens_breakdown,
    render_report,
    render_reshoot,
    sort_rows_for_reshoot,
    sort_rows_for_summary,
)


def _label(lens="Sigma 150mm", mag="1_1", focal="210mm", ap="F8") -> ScenarioLabel:
    return ScenarioLabel(
        lens=lens,
        magnification=mag,
        magnification_pretty=mag.replace("_", ":"),
        magnification_value=1.0,
        focal_length=focal,
        aperture=ap,
    )


def _ok_crop(name: str = "center") -> CropAnalysis:
    return CropAnalysis(
        name=name,
        status=CropStatus.OK,
        n_frames=30,
        peak_idx=15,
        peak_pct=0.5,
        max_size=131_047,
        min_size=83_356,
    )


def _truncated_crop(name: str = "center", end: bool = True) -> CropAnalysis:
    return CropAnalysis(
        name=name,
        status=CropStatus.TRUNCATED_END if end else CropStatus.TRUNCATED_START,
        n_frames=30,
        peak_idx=29 if end else 0,
        peak_pct=0.97 if end else 0.0,
        max_size=131_047,
        min_size=83_356,
    )


def _off_target_crop(name: str = "top-edge") -> CropAnalysis:
    return CropAnalysis(
        name=name,
        status=CropStatus.OFF_TARGET,
        n_frames=30,
        peak_idx=None,
        peak_pct=None,
        max_size=72_000,
        min_size=71_000,
    )


def _scenario(
    crops: list[CropAnalysis],
    *,
    cropped_dir: Path = Path("/tmp/Lens/1_1/210mm/F8/cropped"),
    status: ScenarioStatus = ScenarioStatus.OK,
) -> ScenarioAnalysis:
    return ScenarioAnalysis(cropped_dir=cropped_dir, status=status, crops=crops)


class TestBuildCropRow:
    def test_ok_crop(self):
        row = build_crop_row(_ok_crop(), slug="my-slug")
        assert row.status_label == "OK"
        assert row.status_class == "ok"
        assert row.peak_pct == "50%"
        assert row.max_kb == "128"
        assert row.min_kb == "81"
        assert row.chart_src == "assets/charts/my-slug/center.png"
        assert row.is_off_target is False

    def test_truncated_crop_uses_truncated_class(self):
        row = build_crop_row(_truncated_crop(end=True), slug="s")
        assert row.status_class == "truncated"
        assert row.status_label == "TRUNCATED_END"

    def test_off_target_crop(self):
        row = build_crop_row(_off_target_crop(), slug="s")
        assert row.is_off_target is True
        assert row.status_class == "offtarget"
        assert row.peak_pct == ""

    def test_empty_crop_has_no_chart(self):
        empty = CropAnalysis(
            name="x",
            status=CropStatus.EMPTY,
            n_frames=0,
            peak_idx=None,
            peak_pct=None,
            max_size=None,
            min_size=None,
        )
        row = build_crop_row(empty, slug="s")
        assert row.chart_src == ""
        assert row.max_kb == ""
        assert row.min_kb == ""


class TestBuildScenarioRow:
    def test_ok_scenario(self):
        scn = _scenario([_ok_crop("a"), _ok_crop("b")])
        row = build_scenario_row(scn, slug="my-slug", label=_label())
        assert row.scenario_status == "OK"
        assert row.scenario_status_class == "ok"
        assert row.n_truncated == 0
        assert row.n_off_target == 0
        assert row.anchor == "my-slug"
        assert len(row.crops) == 2
        assert row.representative_chart is None

    def test_reshoot_scenario_picks_most_extreme_truncated_crop(self):
        # truncated_END at 0.97 vs TRUNCATED_END at 0.93 — first is more extreme
        more_extreme = _truncated_crop("more-extreme", end=True)  # peak_pct = 0.97
        less_extreme = CropAnalysis(
            name="less-extreme",
            status=CropStatus.TRUNCATED_END,
            n_frames=30,
            peak_idx=27,
            peak_pct=0.93,
            max_size=100_000,
            min_size=80_000,
        )
        scn = _scenario(
            [_ok_crop("ok"), less_extreme, more_extreme],
            status=ScenarioStatus.NEEDS_RESHOOT,
        )
        row = build_scenario_row(scn, slug="s", label=_label())
        assert row.scenario_status == "NEEDS_RESHOOT"
        assert row.n_truncated == 2
        assert row.representative_chart == "assets/charts/s/more-extreme.png"
        assert set(row.truncated_crop_names) == {"less-extreme", "more-extreme"}

    def test_label_inferred_from_path_when_omitted(self):
        scn = _scenario(
            [_ok_crop()],
            cropped_dir=Path("/data/Sigma APO/1_1/210mm/F8/cropped"),
        )
        row = build_scenario_row(scn, slug="s")
        assert row.label.lens == "Sigma APO"
        assert row.label.aperture == "F8"


class TestSorting:
    def _row(self, lens="A", mag_value=1.0, focal="100mm", ap="F8", status="OK"):
        return ScenarioRow(
            label=ScenarioLabel(
                lens=lens,
                magnification="x",
                magnification_pretty="x",
                magnification_value=mag_value,
                focal_length=focal,
                aperture=ap,
            ),
            cropped_dir=Path("/x"),
            scenario_status=status,
            scenario_status_class="ok",
            n_truncated=0,
            n_off_target=0,
            anchor="a",
            crops=[],
            truncated_crop_names=[],
            representative_chart=None,
        )

    def test_summary_puts_reshoot_first(self):
        a = self._row(lens="A", status="OK")
        b = self._row(lens="B", status="NEEDS_RESHOOT")
        ordered = sort_rows_for_summary([a, b])
        assert [r.label.lens for r in ordered] == ["B", "A"]

    def test_summary_apertures_sorted_numerically(self):
        rows = [
            self._row(ap="F11"),
            self._row(ap="F2.8"),
            self._row(ap="F8"),
        ]
        ordered = sort_rows_for_summary(rows)
        assert [r.label.aperture for r in ordered] == ["F2.8", "F8", "F11"]

    def test_reshoot_groups_by_lens(self):
        rows = [
            self._row(lens="B"),
            self._row(lens="A"),
            self._row(lens="A"),
            self._row(lens="B"),
        ]
        ordered = sort_rows_for_reshoot(rows)
        assert [r.label.lens for r in ordered] == ["A", "A", "B", "B"]


class TestLensBreakdown:
    def test_counts_per_lens_descending(self):
        rows = [
            ScenarioRow(
                label=_label(lens="A"),
                cropped_dir=Path("/x"),
                scenario_status="NEEDS_RESHOOT",
                scenario_status_class="needs-reshoot",
                n_truncated=1,
                n_off_target=0,
                anchor=f"a{i}",
                crops=[],
                truncated_crop_names=[],
                representative_chart=None,
            )
            for i in range(3)
        ] + [
            ScenarioRow(
                label=_label(lens="B"),
                cropped_dir=Path("/x"),
                scenario_status="NEEDS_RESHOOT",
                scenario_status_class="needs-reshoot",
                n_truncated=1,
                n_off_target=0,
                anchor=f"b{i}",
                crops=[],
                truncated_crop_names=[],
                representative_chart=None,
            )
            for i in range(1)
        ]
        assert lens_breakdown(rows) == [("A", 3), ("B", 1)]


class TestRenderReport:
    def test_renders_summary_and_detail(self):
        scn_ok = _scenario([_ok_crop("c")], status=ScenarioStatus.OK)
        scn_bad = _scenario(
            [_truncated_crop("c"), _off_target_crop("o")],
            cropped_dir=Path("/d/Lens/1_1/100mm/F11/cropped"),
            status=ScenarioStatus.NEEDS_RESHOOT,
        )
        rows = [
            build_scenario_row(scn_ok, slug="ok-slug", label=_label(ap="F8")),
            build_scenario_row(scn_bad, slug="bad-slug", label=_label(ap="F11")),
        ]
        html = render_report(rows, source="/data", generated_at="2026-05-04")
        assert "Rail-coverage diagnostic" in html
        assert "needs reshoot 1" in html
        assert "ok-slug" in html
        assert "bad-slug" in html
        assert "TRUNCATED_END" in html
        # Off-target row should be marked off-target so CSS can de-emphasise it
        assert 'class="off-target"' in html

    def test_summary_table_has_link_to_anchor(self):
        scn = _scenario([_ok_crop("c")], status=ScenarioStatus.OK)
        rows = [build_scenario_row(scn, slug="my-slug", label=_label())]
        html = render_report(rows, source="/data", generated_at="2026-05-04")
        assert 'href="#my-slug"' in html
        assert 'id="my-slug"' in html


class TestRenderReshoot:
    def test_lists_only_reshoot_scenarios(self):
        scn_ok = _scenario([_ok_crop("c")], status=ScenarioStatus.OK)
        scn_bad = _scenario(
            [_truncated_crop("c")],
            cropped_dir=Path("/d/MyLens/1_1/100mm/F11/cropped"),
            status=ScenarioStatus.NEEDS_RESHOOT,
        )
        rows = [
            build_scenario_row(scn_ok, slug="ok-slug", label=_label(ap="F8")),
            build_scenario_row(scn_bad, slug="bad-slug", label=_label(lens="MyLens", ap="F11")),
        ]
        html = render_reshoot(rows, generated_at="2026-05-04")
        assert "1 scenarios need reshoot" in html
        assert "MyLens" in html
        assert "bad-slug" in html
        assert "ok-slug" not in html
        # Direction info must NOT be present (subject distance can't be reproduced)
        assert "extend rail" not in html.lower()
        assert "rail direction" not in html.lower()

    def test_empty_when_no_reshoots(self):
        scn_ok = _scenario([_ok_crop("c")], status=ScenarioStatus.OK)
        rows = [build_scenario_row(scn_ok, slug="s", label=_label())]
        html = render_reshoot(rows, generated_at="2026-05-04")
        assert "0 scenarios need reshoot" in html
        assert "No scenarios need reshoot" in html

    def test_lens_breakdown_in_summary(self):
        # Two reshoot scenarios on lens A, one on lens B
        rows = []
        for i, lens in enumerate(["A", "A", "B"]):
            scn = _scenario(
                [_truncated_crop("c")],
                cropped_dir=Path(f"/d/{lens}/1_1/100mm/F{i+8}/cropped"),
                status=ScenarioStatus.NEEDS_RESHOOT,
            )
            rows.append(
                build_scenario_row(scn, slug=f"s{i}", label=_label(lens=lens, ap=f"F{i+8}"))
            )
        html = render_reshoot(rows, generated_at="2026-05-04")
        assert "2 A" in html
        assert "1 B" in html


class TestEnvironment:
    def test_uses_package_loader(self):
        # Defensive: make sure render imports template via PackageLoader, not file path.
        # If someone refactors to use FileSystemLoader, this guards against breaking
        # `uv tool install` / wheel installs.
        from rail_coverage import render

        with patch("rail_coverage.render.PackageLoader") as PL:
            PL.return_value = render._env().loader  # reuse a working loader
            render._env()
            PL.assert_called_with("rail_coverage", "templates")
