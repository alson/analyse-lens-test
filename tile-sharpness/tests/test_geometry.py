from tile_sharpness.geometry import compute_tiles, compute_tiles_for_roi, grid_shape


def test_centred_tile_on_z7_at_1024():
    tiles = compute_tiles(8256, 5504, 1024)
    centre = next(t for t in tiles if t.ix == 0 and t.iy == 0)
    assert centre.x == 3616
    assert centre.y == 2240
    assert all(t.x % 16 == 0 and t.y % 16 == 0 for t in tiles)
    assert grid_shape(tiles) == (7, 5)
    assert len(tiles) == 35


def test_tiles_stay_inside_frame():
    tiles = compute_tiles(8256, 5504, 1024)
    for t in tiles:
        assert 0 <= t.x and t.x + t.size <= 8256
        assert 0 <= t.y and t.y + t.size <= 5504


def test_size_512_grid_doubles():
    tiles = compute_tiles(8256, 5504, 512)
    w, h = grid_shape(tiles)
    assert w == 15
    assert h == 9


def test_roi_grid_matches_legacy_at_1024():
    """ROI grid with both ROIs at 1024 matches the legacy 5x7 grid."""
    rois = compute_tiles_for_roi(8256, 5504, lsf_roi_px=1024, maze_roi_px=1024)
    legacy = compute_tiles(8256, 5504, 1024)
    assert len(rois) == len(legacy) == 35
    # Centre tile alignment
    centre = next(t for t in rois if t.ix == 0 and t.iy == 0)
    assert centre.cx == 4128  # legacy centre top-left 3616 + size/2 512
    assert centre.cy == 2752
    # ix/iy pairs match exactly between the two grids.
    legacy_ixiy = {(t.ix, t.iy) for t in legacy}
    roi_ixiy = {(t.ix, t.iy) for t in rois}
    assert legacy_ixiy == roi_ixiy


def test_roi_grid_large_roi_shrinks_grid():
    """LSF ROI of 3328 px (M=1.0) drops outer cells but keeps inner ones."""
    rois = compute_tiles_for_roi(8256, 5504, lsf_roi_px=3328, maze_roi_px=1024)
    # 3328/2 = 1664; cx0=4128. Outermost ix that fits: cx-1664 >= 0
    # so ix in {-2, -1, 0, 1, 2}. iy: cy0=2752, only |iy| <= 1 fits.
    assert all(abs(t.ix) <= 2 and abs(t.iy) <= 1 for t in rois)
    assert (0, 0) in {(t.ix, t.iy) for t in rois}


def test_roi_grid_huge_roi_degenerates_to_centre():
    """ROI larger than the frame -> single centre tile."""
    rois = compute_tiles_for_roi(8256, 5504, lsf_roi_px=6400, maze_roi_px=256)
    # 6400/2 = 3200; cy0=2752 < 3200 → centre-only fallback.
    assert len(rois) == 1
    assert rois[0].ix == 0 and rois[0].iy == 0


def test_roi_grid_rejects_non_mcu_size():
    import pytest
    with pytest.raises(ValueError):
        compute_tiles_for_roi(8256, 5504, lsf_roi_px=1000, maze_roi_px=1024)
