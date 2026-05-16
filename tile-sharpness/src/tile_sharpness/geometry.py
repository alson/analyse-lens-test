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


@dataclass(frozen=True)
class ROITile:
    """Tile position with per-metric ROI sizes for the LSF + maze pipeline.

    ``cx, cy`` are the tile **centre** in source pixels (MCU-aligned).
    The LSF and maze ROIs are square boxes of size ``lsf_roi_px`` and
    ``maze_roi_px`` respectively, centred on ``(cx, cy)``. ROIs may
    overlap with neighbouring tiles when ``max(lsf_roi_px, maze_roi_px)
    > grid_step_px`` — this is intentional per the
    accuracy-over-granularity policy (see ``MEMORY.md``).
    """
    ix: int
    iy: int
    cx: int
    cy: int
    lsf_roi_px: int
    maze_roi_px: int

    def lsf_box(self) -> tuple[int, int, int, int]:
        h = self.lsf_roi_px // 2
        return (self.cx - h, self.cy - h, self.cx + h, self.cy + h)

    def maze_box(self) -> tuple[int, int, int, int]:
        h = self.maze_roi_px // 2
        return (self.cx - h, self.cy - h, self.cx + h, self.cy + h)


def compute_tiles_for_roi(
    image_w: int,
    image_h: int,
    lsf_roi_px: int,
    maze_roi_px: int,
    *,
    grid_step_px: int = 1024,
) -> list[ROITile]:
    """Build an M-driven tile grid that respects per-metric ROI sizes.

    The centre tile is pinned to the image centre (MCU-aligned). Neighbours
    step outward by ``grid_step_px``. A tile is kept only if **the larger
    of the two ROIs** fits inside the frame at that position. When even
    the centre tile's larger ROI exceeds the frame, returns a single
    centre-only tile (the LSF can still read partial-ROI data; the maze
    will return ``None`` for that case — caller handles).
    """
    for size, name in [(lsf_roi_px, "lsf_roi_px"), (maze_roi_px, "maze_roi_px")]:
        if size <= 0:
            raise ValueError(f"{name} must be positive; got {size}")
        if size % MCU_SIZE:
            raise ValueError(f"{name}={size} must be a multiple of {MCU_SIZE}")
    if grid_step_px % MCU_SIZE:
        raise ValueError(f"grid_step_px={grid_step_px} must be a multiple of {MCU_SIZE}")

    cx0 = align_down(image_w // 2)
    cy0 = align_down(image_h // 2)
    max_roi = max(lsf_roi_px, maze_roi_px)
    half = max_roi // 2

    # Centre fits?
    if (cx0 - half < 0 or cy0 - half < 0
            or cx0 + half > image_w or cy0 + half > image_h):
        # Degenerate: centre-only with whatever ROI fits.
        return [ROITile(ix=0, iy=0, cx=cx0, cy=cy0,
                        lsf_roi_px=lsf_roi_px, maze_roi_px=maze_roi_px)]

    n_xneg = (cx0 - half) // grid_step_px
    n_xpos = (image_w - cx0 - half) // grid_step_px
    n_yneg = (cy0 - half) // grid_step_px
    n_ypos = (image_h - cy0 - half) // grid_step_px

    tiles: list[ROITile] = []
    for iy in range(-n_yneg, n_ypos + 1):
        for ix in range(-n_xneg, n_xpos + 1):
            cx = cx0 + ix * grid_step_px
            cy = cy0 + iy * grid_step_px
            if (cx - half < 0 or cy - half < 0
                    or cx + half > image_w or cy + half > image_h):
                continue
            tiles.append(ROITile(
                ix=ix, iy=iy, cx=cx, cy=cy,
                lsf_roi_px=lsf_roi_px, maze_roi_px=maze_roi_px,
            ))
    return tiles
