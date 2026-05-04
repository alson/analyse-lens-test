from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from rail_coverage.plots import make_chart_png, write_chart


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class TestMakeChartPng:
    def test_returns_png_bytes(self):
        png = make_chart_png([1000, 2000, 5000, 8000, 5000, 2000, 1000])
        assert png.startswith(PNG_MAGIC)
        assert len(png) > 200  # not just a header stub

    def test_handles_empty_input(self):
        png = make_chart_png([])
        assert png.startswith(PNG_MAGIC)

    def test_with_peak_marker(self):
        # Peak in interior — should not crash and should emit a valid PNG
        png = make_chart_png([1, 5, 10, 5, 1], peak_idx=2)
        assert png.startswith(PNG_MAGIC)

    def test_peak_idx_out_of_range_is_ignored(self):
        # 99 is out of range; chart should still render without erroring
        png = make_chart_png([1, 2, 3], peak_idx=99)
        assert png.startswith(PNG_MAGIC)

    def test_does_not_leave_figures_open(self):
        # Repeated calls must not leak matplotlib figures
        import matplotlib.pyplot as plt

        for _ in range(5):
            make_chart_png([1, 2, 3, 4, 5])
        # plt.get_fignums returns figure ids still alive
        assert plt.get_fignums() == []


class TestWriteChart:
    def test_creates_parents(self, tmp_path: Path):
        target = tmp_path / "deep" / "nested" / "out.png"
        write_chart(target, b"data")
        assert target.read_bytes() == b"data"

    def test_overwrites_existing(self, tmp_path: Path):
        target = tmp_path / "out.png"
        target.write_bytes(b"old")
        write_chart(target, b"new")
        assert target.read_bytes() == b"new"

    def test_only_touches_target_path(self, tmp_path: Path):
        # Sanity: write_chart should not invoke any plotting code
        target = tmp_path / "out.png"
        with patch("rail_coverage.plots.make_chart_png") as fake:
            write_chart(target, b"data")
            fake.assert_not_called()
        assert target.read_bytes() == b"data"
