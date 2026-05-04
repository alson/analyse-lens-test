"""Cache scan results so a re-render doesn't have to walk the tree again.

Walking ``test-raw-data/`` over NFS, stat-ing ~400 K crop JPEGs, takes
the longest single chunk of analyzer wall time. The data we need from
that scan is small — just ``(seq, size)`` pairs per crop — so we
serialise the post-scan ``Scenario`` objects to a JSON file. Subsequent
runs that point at the same sources can read the cache and skip the
filesystem entirely; only the (also slow) matplotlib chart rendering
and HTML emission run.

Schema (``version: 1``)::

    {
      "version": 1,
      "generated_at": "2026-05-04T12:34:56Z",
      "sources": ["/.../2026-01-29", "/.../2026-02-18"],
      "scenarios": [
        {
          "source": "/.../2026-01-29",
          "cropped_dir": "/.../2026-01-29/Lens/1_1/F8/cropped",
          "crops": [
            {"name": "center",     "frames": [[931, 88089], [932, 88276], ...]},
            {"name": "left-edge",  "frames": [...]},
            ...
          ]
        }
      ]
    }

Frame paths are intentionally NOT stored — chart rendering only needs
sizes, and re-deriving paths from a future cache hit would be tied to
the original filesystem layout.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rail_coverage.scan import CropFrame, CropSeries, Scenario


CACHE_VERSION = 1


@dataclass(frozen=True)
class CachedScan:
    """A loaded cache: sources + scenarios paired with their source root."""

    sources: list[Path]
    items: list[tuple[Path, Scenario]]  # (source_root, scenario)


def dump_cache(
    path: Path,
    sources: list[Path],
    items: list[tuple[Path, Scenario]],
) -> None:
    """Write a scan result to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": [str(s) for s in sources],
        "scenarios": [_scenario_to_dict(src, scn) for src, scn in items],
    }
    path.write_text(json.dumps(payload, indent=2))


def load_cache(path: Path) -> CachedScan:
    """Read a cache previously written by ``dump_cache``.

    Raises ``ValueError`` for unknown schema versions or malformed data.
    """
    payload = json.loads(path.read_text())
    version = payload.get("version")
    if version != CACHE_VERSION:
        raise ValueError(
            f"unsupported cache version {version!r} (expected {CACHE_VERSION})"
        )
    sources = [Path(s) for s in payload["sources"]]
    items: list[tuple[Path, Scenario]] = []
    for entry in payload["scenarios"]:
        items.append(
            (
                Path(entry["source"]),
                _scenario_from_dict(entry),
            )
        )
    return CachedScan(sources=sources, items=items)


def _scenario_to_dict(source: Path, scenario: Scenario) -> dict:
    return {
        "source": str(source),
        "cropped_dir": str(scenario.cropped_dir),
        "crops": [
            {
                "name": c.name,
                "frames": [[f.seq, f.size] for f in c.frames],
            }
            for c in scenario.crops
        ],
    }


def _scenario_from_dict(entry: dict) -> Scenario:
    cropped_dir = Path(entry["cropped_dir"])
    crops: list[CropSeries] = []
    for crop_entry in entry["crops"]:
        # We don't store per-frame paths — chart rendering only needs sizes.
        # Reconstruct a synthetic path so consumer code that touches
        # CropFrame.path doesn't crash, but flag it as cache-derived.
        frames = [
            CropFrame(seq=int(seq), size=int(size), path=cropped_dir / crop_entry["name"])
            for seq, size in crop_entry["frames"]
        ]
        crops.append(CropSeries(name=crop_entry["name"], frames=frames))
    return Scenario(cropped_dir=cropped_dir, crops=crops)
