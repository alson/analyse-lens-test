from tile_sharpness.geometry import compute_tiles, grid_shape


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
