"""Tile-grid origin computation for sharpness analysis.

One tile is pinned to the optical axis (image centre, MCU-aligned).
Neighbouring tiles step outward in 2D by ``size`` pixels, with each
origin snapped down to a 16-multiple via
:func:`lens_test_detect_core.align_down`. Tiles whose right or bottom
edge would exceed the frame are dropped.
"""

from __future__ import annotations

from dataclasses import dataclass

from lens_test_detect_core import MCU_SIZE, align_down


@dataclass(frozen=True)
class Tile:
    ix: int
    iy: int
    x: int
    y: int
    size: int

    @property
    def name(self) -> str:
        return f"{self.ix:+d}_{self.iy:+d}"


def compute_tiles(image_w: int, image_h: int, size: int) -> list[Tile]:
    if size % MCU_SIZE:
        raise ValueError(f"tile size {size} must be a multiple of {MCU_SIZE}")
    if image_w < size or image_h < size:
        raise ValueError(
            f"image {image_w}x{image_h} smaller than tile {size}x{size}"
        )

    cx = align_down((image_w - size) // 2)
    cy = align_down((image_h - size) // 2)

    nx_neg = cx // size
    nx_pos = (image_w - cx - size) // size
    ny_neg = cy // size
    ny_pos = (image_h - cy - size) // size

    tiles: list[Tile] = []
    for iy in range(-ny_neg, ny_pos + 1):
        for ix in range(-nx_neg, nx_pos + 1):
            x = cx + ix * size
            y = cy + iy * size
            if x < 0 or y < 0 or x + size > image_w or y + size > image_h:
                continue
            tiles.append(Tile(ix=ix, iy=iy, x=x, y=y, size=size))
    return tiles


def grid_shape(tiles: list[Tile]) -> tuple[int, int]:
    """Return ``(width_tiles, height_tiles)`` of the grid extent."""
    ixs = [t.ix for t in tiles]
    iys = [t.iy for t in tiles]
    return max(ixs) - min(ixs) + 1, max(iys) - min(iys) + 1
