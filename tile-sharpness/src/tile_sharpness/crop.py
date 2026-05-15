"""Lossless tile extraction with on-disk cache.

Each source JPEG is decoded only for its MCU dimensions; the actual
crop is done by :func:`turbojpeg.TurboJPEG.crop_multiple`, which
re-packs encoded blocks into independent tile JPEGs. Crops inherit the
source's encoded quality exactly.

The cache layout is::

    <cache_root>/<shard>/<source-stem>__<source-size>__<source-mtime>/<tile_size>/<ix>_<iy>.jpg

``<shard>`` is the first 2 hex chars of ``sha256(absolute source path)``
to keep individual directories from ballooning. ``<source-size>`` and
``<source-mtime>`` together act as the cache invalidation key — if
either changes the cache entry is regenerated.

A 78-shot sweep × 35 tiles ≈ 2730 cached tiles per (sweep, tile-size).
At ~150 KB per 1024-tile this is roughly 400 MB per sweep cached.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path

from turbojpeg import TurboJPEG

from .geometry import Tile

DEFAULT_CACHE_ROOT = (
    Path.home() / "shared/projects/personal/fotografie/.tile-sharpness-cache"
)
"""Tile cache lives on the shared mount so nufan can read tiles by path.

Method 1 (slanted-edge MTF via mtf_mapper) runs on nufan over SSH —
the binary needs the tile JPEG accessible at a path that resolves on
both hosts.  Keeping the cache on the shared filesystem avoids
shuttling each tile over SSH.
"""


@dataclass(frozen=True)
class TilePath:
    tile: Tile
    path: Path


_tj_local = threading.local()


def _tj() -> TurboJPEG:
    inst = getattr(_tj_local, "tj", None)
    if inst is None:
        inst = TurboJPEG()
        _tj_local.tj = inst
    return inst


def _source_key(src: Path) -> str:
    abs_src = str(src.resolve())
    stat = src.stat()
    digest = hashlib.sha256(abs_src.encode()).hexdigest()
    return f"{digest[:2]}/{digest[2:16]}__{stat.st_size}__{int(stat.st_mtime)}"


def image_dimensions(src: Path) -> tuple[int, int]:
    w, h, _, _ = _tj().decode_header(src.read_bytes())
    return w, h


def extract_tiles(
    src: Path,
    tiles: list[Tile],
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> list[TilePath]:
    """Lossless-crop ``tiles`` from ``src`` into the cache.

    Existing cached tiles are returned as-is. Missing ones are produced
    in a single :func:`crop_multiple` call.
    """
    if not tiles:
        return []
    sizes = {t.size for t in tiles}
    if len(sizes) != 1:
        raise ValueError(f"all tiles must share one size; got {sorted(sizes)}")
    size = sizes.pop()

    key = _source_key(src)
    base = cache_root / key / str(size)
    base.mkdir(parents=True, exist_ok=True)

    missing_idx: list[int] = []
    out: list[TilePath] = []
    for i, t in enumerate(tiles):
        target = base / f"{t.ix:+d}_{t.iy:+d}.jpg"
        out.append(TilePath(tile=t, path=target))
        if not target.exists():
            missing_idx.append(i)

    if missing_idx:
        raw = src.read_bytes()
        params = [
            (tiles[i].x, tiles[i].y, tiles[i].size, tiles[i].size) for i in missing_idx
        ]
        crops = _tj().crop_multiple(raw, params)
        for i, data in zip(missing_idx, crops, strict=True):
            out[i].path.write_bytes(data)
    return out
