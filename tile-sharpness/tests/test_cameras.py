"""Tests for tile_sharpness.cameras — the per-camera sensor-parameter table."""
from __future__ import annotations

from tile_sharpness.cameras import CAMERAS, camera_pitch_um, get_camera


def test_z7_and_d7200_pitch():
    assert camera_pitch_um("Z7") == 4.35
    assert camera_pitch_um("D7200") == 3.91


def test_olpf_flag():
    assert CAMERAS["Z7"].olpf is False
    assert CAMERAS["D7200"].olpf is True


def test_default_and_unknown_fall_back_to_z7():
    assert camera_pitch_um(None) == 4.35
    assert camera_pitch_um("") == 4.35
    assert camera_pitch_um("unknown-body") == 4.35
    assert get_camera("nope").name == "Z7"
