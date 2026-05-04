from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rail_coverage.scan import (
    CropFrame,
    build_series,
    find_cropped_dirs,
    parse_seq,
    read_crop_series,
    read_scenario,
)


class TestParseSeq:
    def test_extracts_leading_integer(self):
        assert parse_seq("03488|Sigma|1_1|210mm|F8|alm-1.jpg") == 3488

    def test_handles_zero_padded(self):
        assert parse_seq("00001|x|y.jpg") == 1

    def test_returns_none_for_no_pipe(self):
        assert parse_seq("12345.jpg") is None

    def test_returns_none_for_non_numeric_head(self):
        assert parse_seq("abcd|x|y.jpg") is None

    def test_returns_none_for_empty(self):
        assert parse_seq("") is None


class TestBuildSeries:
    def test_drops_undersized_files(self):
        frames = build_series(
            [("01|x.jpg", 500), ("02|x.jpg", 5000)],
            min_size=1024,
        )
        assert [f.seq for f in frames] == [2]

    def test_drops_unparseable_filenames(self):
        frames = build_series([("garbage.jpg", 5000), ("03|x.jpg", 5000)])
        assert [f.seq for f in frames] == [3]

    def test_sorts_by_seq(self):
        frames = build_series(
            [("05|x.jpg", 5000), ("02|x.jpg", 5000), ("03|x.jpg", 5000)]
        )
        assert [f.seq for f in frames] == [2, 3, 5]

    def test_preserves_size(self):
        frames = build_series([("01|x.jpg", 1234)], min_size=0)
        assert frames[0].size == 1234


class TestReadCropSeries:
    def test_excludes_pick_jpg_and_non_jpg(self, tmp_path: Path):
        crop = tmp_path / "center"
        crop.mkdir()
        (crop / "01|x|y|z|alm.jpg").write_bytes(b"x" * 5000)
        (crop / "02|x|y|z|alm.jpg").write_bytes(b"x" * 6000)
        (crop / "pick.jpg").write_bytes(b"x" * 9999)
        (crop / "notes.txt").write_text("hi")

        series = read_crop_series(crop)

        assert series.name == "center"
        assert [f.seq for f in series.frames] == [1, 2]

    def test_paths_are_absolute_to_crop_dir(self, tmp_path: Path):
        crop = tmp_path / "left-edge"
        crop.mkdir()
        (crop / "07|x|y|z|alm.jpg").write_bytes(b"x" * 5000)
        series = read_crop_series(crop)
        assert series.frames[0].path == crop / "07|x|y|z|alm.jpg"


class TestFindCroppedDirs:
    def test_yields_only_directories_named_cropped(self, tmp_path: Path):
        (tmp_path / "lens/F8/cropped/center").mkdir(parents=True)
        (tmp_path / "lens/F11/cropped/center").mkdir(parents=True)
        (tmp_path / "lens/F8/notes/cropped").mkdir(parents=True)
        (tmp_path / "lens/F8/cropped.txt").touch()

        found = sorted(find_cropped_dirs(tmp_path))
        assert len(found) == 3
        assert all(p.name == "cropped" and p.is_dir() for p in found)

    def test_skips_dotted_directories(self):
        # rglob result is mocked so we can assert the filter logic in isolation
        with patch.object(Path, "rglob") as rglob:
            rglob.return_value = iter(
                [
                    Path("/root/lens/.cache/cropped"),
                    Path("/root/lens/F8/cropped"),
                ]
            )
            with patch.object(Path, "is_dir", return_value=True):
                results = list(find_cropped_dirs(Path("/root")))
        assert results == [Path("/root/lens/F8/cropped")]


class TestReadScenario:
    def test_aggregates_each_crop_subdir(self, tmp_path: Path):
        cropped = tmp_path / "Lens/1_1/F8/cropped"
        for crop in ("center", "top-left", "right-edge"):
            d = cropped / crop
            d.mkdir(parents=True)
            (d / "01|a|b|c|alm.jpg").write_bytes(b"x" * 5000)

        scenario = read_scenario(cropped)
        assert scenario.cropped_dir == cropped
        assert sorted(c.name for c in scenario.crops) == [
            "center",
            "right-edge",
            "top-left",
        ]
        for crop in scenario.crops:
            assert len(crop.frames) == 1


class TestCropFrameDataclass:
    def test_frame_is_hashable(self):
        # frozen=True so we can use frames in sets if needed
        f = CropFrame(seq=1, size=100, path=Path("/x"))
        {f}  # should not raise


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("03488|Sigma APO Macro 150mm F2.8|1_1|210.0 mm|F8|alm-20260130-222036-953.jpg", 3488),
        ("0|x|y.jpg", 0),
        ("123|.jpg", 123),
    ],
)
def test_parse_seq_parametric(filename: str, expected: int):
    assert parse_seq(filename) == expected
