import csv
from pathlib import Path

import pytest

from tile_sharpness.m_lookup import (
    MLookup,
    load_manifests,
    mag_label_from_sweep_label,
    parse_mag_label,
    resolve,
)
from tile_sharpness.sweeps import Shot, Sweep


MANIFEST_COLUMNS = [
    "slug", "mag_label", "claimed_mag", "image_path", "image_size_bytes",
    "algo_period_px", "algo_tilt_deg", "algo_n_lines", "algo_confidence",
    "algo_cross_check_period_px", "algo_measured_mag", "algo_deviation_pct",
    "algo_apertures_tried", "algo_best_aperture",
    "algo_cross_aperture_dev_pct", "algo_aperture_warning",
    "visual_count", "visual_count_anchor", "vision_measured_mag",
    "vision_confidence", "notes",
]


def _write_manifest(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        w.writeheader()
        for r in rows:
            for col in MANIFEST_COLUMNS:
                r.setdefault(col, "")
            w.writerow(r)


def _mk_sweep(label: str, lens: str) -> Sweep:
    return Sweep(
        label=label,
        family="older-2026-01-29",
        lens=lens,
        aperture="F8",
        shots=[Shot(path=Path("/dev/null"), rail_step=0, rail_position_mm=None)],
    )


def test_parse_mag_label_basic():
    assert parse_mag_label("1_1") == 1.0
    assert parse_mag_label("1_2.60") == pytest.approx(1.0 / 2.60)
    assert parse_mag_label("2_1") == 2.0
    assert parse_mag_label("1.07_1") == pytest.approx(1.07)


def test_parse_mag_label_invalid():
    import math
    assert math.isnan(parse_mag_label("garbage"))
    assert math.isnan(parse_mag_label("no_underscore_only_words"))


def test_mag_label_from_sweep_label_bare_prime():
    label = "2026-01-29__Nikon_Micro-Nikkor_55mm_f_2.8_AIS_287318__1_1__F8"
    assert mag_label_from_sweep_label(label) == "1_1"


def test_mag_label_from_sweep_label_zoom():
    label = "2026-02-18__NIKKOR_Z_24-120mm_f_4_S_+_Raynox_M-150__1_1-resized__120.0_mm__F8"
    assert mag_label_from_sweep_label(label) == "1_1-resized"


def test_mag_label_from_sweep_label_newer_rig():
    # Newer-rig labels don't carry a mag_label slot.
    assert mag_label_from_sweep_label("session__lens__F8") is None


def test_load_manifests_and_get(tmp_path: Path):
    _write_manifest(tmp_path / "a.csv", [
        {"slug": "Sigma APO Macro 150mm F2.8 EX DG OS HSM",
         "mag_label": "1_1", "claimed_mag": "1.0",
         "algo_measured_mag": "1.005", "algo_confidence": "high"},
    ])
    mlookup = load_manifests([tmp_path / "a.csv"])
    assert len(mlookup) == 1
    row = mlookup.get("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "1_1")
    assert row is not None
    assert row["algo_measured_mag"] == "1.005"


def test_resolve_vision_wins(tmp_path: Path):
    _write_manifest(tmp_path / "m.csv", [
        {"slug": "Sigma APO Macro 150mm F2.8 EX DG OS HSM",
         "mag_label": "1_1", "claimed_mag": "1.0",
         "algo_measured_mag": "1.005", "algo_confidence": "high",
         "vision_measured_mag": "0.998", "vision_confidence": "high"},
    ])
    mlookup = load_manifests([tmp_path / "m.csv"])
    sweep = _mk_sweep(
        "2026-01-29__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM__1_1__F8",
        "Sigma APO Macro 150mm F2.8 EX DG OS HSM",
    )
    r = resolve(sweep, mlookup)
    assert r.measured == 0.998
    assert r.source == "vision"


def test_resolve_algo_high(tmp_path: Path):
    _write_manifest(tmp_path / "m.csv", [
        {"slug": "Sigma APO Macro 150mm F2.8 EX DG OS HSM",
         "mag_label": "1_1", "claimed_mag": "1.0",
         "algo_measured_mag": "1.005", "algo_confidence": "high"},
    ])
    mlookup = load_manifests([tmp_path / "m.csv"])
    sweep = _mk_sweep(
        "2026-01-29__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM__1_1__F8",
        "Sigma APO Macro 150mm F2.8 EX DG OS HSM",
    )
    r = resolve(sweep, mlookup)
    assert r.measured == 1.005
    assert r.source == "algo_high"


def test_resolve_algo_medium(tmp_path: Path):
    _write_manifest(tmp_path / "m.csv", [
        {"slug": "X", "mag_label": "1_1", "claimed_mag": "1.0",
         "algo_measured_mag": "0.977", "algo_confidence": "medium"},
    ])
    mlookup = load_manifests([tmp_path / "m.csv"])
    sweep = _mk_sweep("session__X__1_1__F8", "X")
    r = resolve(sweep, mlookup)
    assert r.measured == 0.977
    assert r.source == "algo_medium"


def test_resolve_algo_low_falls_back_to_claimed(tmp_path: Path):
    _write_manifest(tmp_path / "m.csv", [
        {"slug": "X", "mag_label": "1_1", "claimed_mag": "1.0",
         "algo_measured_mag": "1.500", "algo_confidence": "low"},
    ])
    mlookup = load_manifests([tmp_path / "m.csv"])
    sweep = _mk_sweep("session__X__1_1__F8", "X")
    r = resolve(sweep, mlookup)
    assert r.measured == 1.0
    assert r.source == "claimed"


def test_resolve_no_manifest_path_parsed_fallback():
    mlookup = MLookup()
    sweep = _mk_sweep(
        "2026-01-29__NIKKOR_Z_100-400mm_f_4.5-5.6_VR_S__1_2.60__F11",
        "NIKKOR Z 100-400mm f_4.5-5.6 VR S",
    )
    r = resolve(sweep, mlookup)
    assert r.measured == pytest.approx(1.0 / 2.60)
    assert r.source == "path_parsed"


def test_resolve_newer_rig_no_mag_label():
    """Newer-rig labels don't carry mag_label; result is NaN with empty source."""
    import math
    mlookup = MLookup()
    sweep = _mk_sweep("session__lens__F8", "lens")
    r = resolve(sweep, mlookup)
    assert math.isnan(r.measured)
    assert r.source == ""


def test_load_manifests_later_files_override(tmp_path: Path):
    _write_manifest(tmp_path / "a.csv", [
        {"slug": "X", "mag_label": "1_1", "claimed_mag": "1.0",
         "algo_measured_mag": "0.95", "algo_confidence": "medium"},
    ])
    _write_manifest(tmp_path / "b.csv", [
        {"slug": "X", "mag_label": "1_1", "claimed_mag": "1.0",
         "algo_measured_mag": "0.99", "algo_confidence": "high"},
    ])
    mlookup = load_manifests([tmp_path / "a.csv", tmp_path / "b.csv"])
    row = mlookup.get("X", "1_1")
    assert row["algo_measured_mag"] == "0.99"
    assert row["algo_confidence"] == "high"
