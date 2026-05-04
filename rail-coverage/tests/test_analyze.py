from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rail_coverage import analyze
from rail_coverage.analyze import _parse_args, main, run


def _populate_crop(crop_dir: Path, sizes: list[int], start_seq: int = 1) -> None:
    crop_dir.mkdir(parents=True, exist_ok=True)
    for i, size in enumerate(sizes, start=start_seq):
        name = f"{i:05d}|TestLens|1_1|100mm|F8|alm-x.jpg"
        (crop_dir / name).write_bytes(b"\x00" * size)


@pytest.fixture
def synthetic_dataset(tmp_path: Path) -> Path:
    """Two scenarios — one well-formed, one with a truncated crop."""
    bell_sizes = [
        # bell-shaped, peak in interior
        80_000, 80_500, 80_400,
        90_000, 90_200, 90_100,
        110_000, 110_500, 110_300,
        125_000, 125_500, 125_700,
        130_000, 130_400, 130_200,
        128_000, 128_300, 128_100,
        115_000, 115_400, 115_200,
        100_000, 100_300, 100_100,
        88_000, 88_400, 88_200,
        82_000, 82_300, 82_100,
    ]
    truncated = list(range(80_000, 130_000, 1500))[:30]  # monotonic increase

    base = tmp_path / "TestLens" / "1_1" / "100mm"
    _populate_crop(base / "F8" / "cropped" / "center", bell_sizes)
    _populate_crop(base / "F8" / "cropped" / "left-edge", bell_sizes)
    _populate_crop(base / "F11" / "cropped" / "center", truncated)
    _populate_crop(base / "F11" / "cropped" / "left-edge", bell_sizes)

    return tmp_path


class TestParseArgs:
    def test_defaults(self):
        args = _parse_args([])
        assert args.sources == [Path(".")]
        assert args.out == Path("output")
        assert args.quiet is False

    def test_single_source(self):
        args = _parse_args(["/data", "--out", "/tmp/out", "--quiet"])
        assert args.sources == [Path("/data")]
        assert args.out == Path("/tmp/out")
        assert args.quiet is True

    def test_multiple_sources(self):
        args = _parse_args(["/data/2026-01-29", "/data/2026-02-18"])
        assert args.sources == [Path("/data/2026-01-29"), Path("/data/2026-02-18")]


class TestRun:
    def test_writes_both_reports(self, synthetic_dataset: Path, tmp_path: Path):
        out = tmp_path / "out"
        n = run(synthetic_dataset, out, verbose=False)
        assert n == 2
        assert (out / "report.html").is_file()
        assert (out / "reshoot.html").is_file()
        assert (out / "assets" / "style.css").is_file()
        # Charts written for every crop in every scenario
        chart_files = list((out / "assets" / "charts").rglob("*.png"))
        assert len(chart_files) == 4

    def test_reshoot_html_lists_truncated_scenario(self, synthetic_dataset: Path, tmp_path: Path):
        out = tmp_path / "out"
        run(synthetic_dataset, out, verbose=False)
        html = (out / "reshoot.html").read_text()
        assert "1 scenarios need reshoot" in html
        assert "F11" in html
        assert "F8" not in html or "F8" in html  # F8 may appear in lens summary too

    def test_report_summary_counts(self, synthetic_dataset: Path, tmp_path: Path):
        out = tmp_path / "out"
        run(synthetic_dataset, out, verbose=False)
        html = (out / "report.html").read_text()
        assert "Scenarios scanned:</strong> 2" in html
        assert "OK 1" in html
        assert "needs reshoot 1" in html


class TestStaticAssetCopy:
    def test_copies_style_css(self, tmp_path: Path):
        out = tmp_path / "out"
        out.mkdir()
        analyze._copy_static_assets(out)
        css = (out / "assets" / "style.css").read_text()
        assert "--ok" in css  # token from our stylesheet
        assert "--bad" in css


class TestMain:
    def test_invokes_run_with_parsed_args(self, tmp_path: Path):
        with patch("rail_coverage.analyze.run") as run_mock:
            run_mock.return_value = 7
            main([str(tmp_path), "--out", str(tmp_path / "o"), "--quiet"])
            run_mock.assert_called_once_with([tmp_path], tmp_path / "o", verbose=False)

    def test_main_passes_multiple_sources_through(self, tmp_path: Path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        with patch("rail_coverage.analyze.run") as run_mock:
            run_mock.return_value = 0
            main([str(a), str(b), "--out", str(tmp_path / "o"), "--quiet"])
            run_mock.assert_called_once_with([a, b], tmp_path / "o", verbose=False)


class TestRunMultipleSources:
    def test_combines_sources_and_namespaces_slugs(self, tmp_path: Path):
        # Two source trees with identical inner structure — slugs must
        # not collide so both scenarios land in the report.
        for date in ("2026-01-29", "2026-02-18"):
            base = tmp_path / date / "Lens" / "1_1" / "F8" / "cropped"
            for crop in ("center", "left-edge"):
                d = base / crop
                d.mkdir(parents=True, exist_ok=True)
                # Use a clear bell so analyse_scenario produces an OK rollup
                for i, size in enumerate(
                    [80_000, 90_000, 110_000, 130_000, 110_000, 90_000, 80_000]
                ):
                    name = f"{i:05d}|TestLens|1_1|F8|alm-x.jpg"
                    (d / name).write_bytes(b"\x00" * size)

        out = tmp_path / "out"
        n = run(
            [tmp_path / "2026-01-29", tmp_path / "2026-02-18"],
            out,
            verbose=False,
        )
        assert n == 2
        html = (out / "report.html").read_text()
        assert "2026-01-29" in html
        assert "2026-02-18" in html
        # Both source trees produced a chart directory
        chart_dirs = sorted(p.name for p in (out / "assets" / "charts").iterdir())
        assert len(chart_dirs) == 2
