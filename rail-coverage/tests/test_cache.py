"""Tests for the scan cache (JSON round-trip)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rail_coverage.cache import (
    CACHE_VERSION,
    CachedScan,
    dump_cache,
    load_cache,
)
from rail_coverage.scan import CropFrame, CropSeries, Scenario


def _make_scenario(name: str, frames: list[tuple[int, int]]) -> Scenario:
    return Scenario(
        cropped_dir=Path(f"/data/2026-01-29/{name}/1_1/F8/cropped"),
        crops=[
            CropSeries(
                name="center",
                frames=[CropFrame(seq=s, size=sz, path=Path(f"/x/{s}.jpg")) for s, sz in frames],
            ),
            CropSeries(
                name="left-edge",
                frames=[CropFrame(seq=s, size=sz // 2, path=Path(f"/x/{s}.jpg")) for s, sz in frames],
            ),
        ],
    )


class TestDumpAndLoad:
    def test_round_trip(self, tmp_path: Path):
        src = Path("/data/2026-01-29")
        scn = _make_scenario("Lens A", [(1, 100_000), (2, 110_000), (3, 105_000)])
        cache_path = tmp_path / "cache.json"
        dump_cache(cache_path, [src], [(src, scn)])

        loaded = load_cache(cache_path)
        assert loaded.sources == [src]
        assert len(loaded.items) == 1
        loaded_src, loaded_scn = loaded.items[0]
        assert loaded_src == src
        assert loaded_scn.cropped_dir == scn.cropped_dir
        assert [c.name for c in loaded_scn.crops] == ["center", "left-edge"]
        assert [f.seq for f in loaded_scn.crops[0].frames] == [1, 2, 3]
        assert [f.size for f in loaded_scn.crops[0].frames] == [100_000, 110_000, 105_000]

    def test_creates_parent_dirs(self, tmp_path: Path):
        cache_path = tmp_path / "deep" / "nested" / "cache.json"
        dump_cache(cache_path, [], [])
        assert cache_path.is_file()

    def test_writes_indented_json(self, tmp_path: Path):
        cache_path = tmp_path / "cache.json"
        dump_cache(cache_path, [], [])
        text = cache_path.read_text()
        # Indented output is human-readable and diff-friendly
        assert "\n  " in text

    def test_records_metadata(self, tmp_path: Path):
        cache_path = tmp_path / "cache.json"
        dump_cache(cache_path, [Path("/x")], [])
        payload = json.loads(cache_path.read_text())
        assert payload["version"] == CACHE_VERSION
        assert payload["sources"] == ["/x"]
        assert "generated_at" in payload
        # ISO8601 with TZ
        assert payload["generated_at"].endswith("+00:00")

    def test_multiple_sources_and_scenarios(self, tmp_path: Path):
        a = Path("/data/2026-01-29")
        b = Path("/data/2026-02-18")
        scns = [
            (a, _make_scenario("LensA", [(0, 100), (1, 200)])),
            (b, _make_scenario("LensB", [(5, 300)])),
            (b, _make_scenario("LensC", [(10, 400), (11, 500)])),
        ]
        cache_path = tmp_path / "cache.json"
        dump_cache(cache_path, [a, b], scns)
        loaded = load_cache(cache_path)
        assert loaded.sources == [a, b]
        assert len(loaded.items) == 3
        assert [src for src, _ in loaded.items] == [a, b, b]


class TestVersioning:
    def test_rejects_unknown_version(self, tmp_path: Path):
        cache_path = tmp_path / "cache.json"
        cache_path.write_text(json.dumps({"version": 999, "sources": [], "scenarios": []}))
        with pytest.raises(ValueError, match="unsupported cache version"):
            load_cache(cache_path)

    def test_rejects_missing_version(self, tmp_path: Path):
        cache_path = tmp_path / "cache.json"
        cache_path.write_text(json.dumps({"sources": [], "scenarios": []}))
        with pytest.raises(ValueError, match="unsupported cache version"):
            load_cache(cache_path)


class TestCachedScanShape:
    def test_dataclass_fields(self):
        c = CachedScan(sources=[Path("/x")], items=[])
        assert c.sources == [Path("/x")]
        assert c.items == []
