from pathlib import Path

from tile_sharpness.geometry import Tile
from tile_sharpness.on_target import label_tiles


def _tile(ix: int, iy: int) -> Tile:
    return Tile(ix=ix, iy=iy, x=ix * 1024, y=iy * 1024, size=1024)


def test_off_target_flagged_below_factor():
    on = _tile(0, 0)
    off = _tile(1, 1)
    sizes = {
        on: [100, 110, 105, 90, 80],
        off: [20, 22, 24, 21, 23],
    }
    paths_per_shot = [{on: Path("/tmp/x"), off: Path("/tmp/y")} for _ in range(5)]
    labels = label_tiles(sizes, paths_per_shot, factor=0.4, ambiguous_band=(0.4, 0.6))
    assert labels[on].on_target is True
    assert labels[off].on_target is False
    assert "peak_below_factor" in labels[off].reason


def test_peak_above_factor_skips_content_check_in_clear_band():
    on = _tile(0, 0)
    off = _tile(1, 1)
    sizes = {
        on: [100, 110, 105, 90, 80],
        off: [80, 82, 85, 84, 83],  # peak=85, 0.85*100=85, just above
    }
    paths_per_shot = [{on: Path("/tmp/x"), off: Path("/tmp/y")} for _ in range(5)]
    labels = label_tiles(sizes, paths_per_shot, factor=0.4, ambiguous_band=(0.4, 0.6))
    assert labels[off].on_target is True
