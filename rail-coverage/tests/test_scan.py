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
    select_primary_chunk,
    split_at_gaps,
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


def _frames(seqs: list[int]) -> list[CropFrame]:
    return [CropFrame(seq=s, size=10_000, path=Path(f"/x/{s}.jpg")) for s in seqs]


class TestSplitAtGaps:
    def test_single_contiguous_chunk(self):
        frames = _frames(list(range(100, 105)))
        chunks = split_at_gaps(frames)
        assert len(chunks) == 1
        assert [f.seq for f in chunks[0]] == list(range(100, 105))

    def test_splits_on_large_gap(self):
        # First session: 100..130, second session: 5000..5030
        frames = _frames(list(range(100, 131)) + list(range(5000, 5031)))
        chunks = split_at_gaps(frames)
        assert len(chunks) == 2
        assert chunks[0][0].seq == 100
        assert chunks[1][0].seq == 5000

    def test_does_not_split_small_gaps(self):
        # Frames every other seq (gap=2) is still contiguous-ish
        frames = _frames(list(range(100, 110, 2)))  # 100, 102, 104, 106, 108
        chunks = split_at_gaps(frames, gap_threshold=30)
        assert len(chunks) == 1

    def test_threshold_boundary(self):
        # gap of exactly 30 → still one chunk
        frames = _frames([100, 130])
        assert len(split_at_gaps(frames, gap_threshold=30)) == 1
        # gap of 31 → splits
        frames = _frames([100, 131])
        assert len(split_at_gaps(frames, gap_threshold=30)) == 2

    def test_empty_input(self):
        assert split_at_gaps([]) == []


class TestSelectPrimaryChunk:
    def test_short_input_returned_as_is(self):
        # Below target_size → no chunking needed
        frames = _frames(list(range(50)))
        assert select_primary_chunk(frames, target_size=75) is frames

    def test_long_single_chunk_returned_as_is(self):
        # 100 frames, all contiguous → caller asked for a long sweep
        frames = _frames(list(range(100, 200)))
        result = select_primary_chunk(frames, target_size=75)
        assert len(result) == 100

    def test_picks_longer_of_two_chunks(self):
        # Partial reshoot: 30 frames day-1, 75 frames day-2 → pick day-2
        first = list(range(100, 130))
        second = list(range(5000, 5075))
        frames = _frames(first + second)
        result = select_primary_chunk(frames, target_size=75)
        assert [f.seq for f in result] == second

    def test_breaks_tie_in_favour_of_later_chunk(self):
        # Two equally-long chunks → take the later one (the re-run)
        first = list(range(100, 200))
        second = list(range(5000, 5100))
        frames = _frames(first + second)
        result = select_primary_chunk(frames, target_size=75)
        assert [f.seq for f in result] == second

    def test_three_chunks_with_clear_winner(self):
        a = list(range(100, 110))   # 10
        b = list(range(5000, 5080))  # 80 (winner)
        c = list(range(9000, 9020))  # 20
        frames = _frames(a + b + c)
        result = select_primary_chunk(frames, target_size=75)
        assert [f.seq for f in result] == b


class TestReadCropSeriesWithPartialReshoot:
    def test_filters_to_primary_chunk(self, tmp_path: Path):
        crop = tmp_path / "center"
        crop.mkdir()
        # Day 1 (interrupted): seqs 100..115 (16 frames)
        for s in range(100, 116):
            (crop / f"{s:05d}|x|y|z|alm.jpg").write_bytes(b"x" * 5000)
        # Day 2 (full re-run): seqs 5000..5079 (80 frames)
        for s in range(5000, 5080):
            (crop / f"{s:05d}|x|y|z|alm.jpg").write_bytes(b"x" * 5000)

        series = read_crop_series(crop)
        assert len(series.frames) == 80
        assert series.frames[0].seq == 5000
        assert series.frames[-1].seq == 5079

    def test_preserves_short_complete_session(self, tmp_path: Path):
        # Single contiguous session of 75 frames — no filtering applied
        crop = tmp_path / "center"
        crop.mkdir()
        for s in range(100, 175):
            (crop / f"{s:05d}|x|y|z|alm.jpg").write_bytes(b"x" * 5000)
        series = read_crop_series(crop)
        assert len(series.frames) == 75
