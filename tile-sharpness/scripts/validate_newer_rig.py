"""One-off script: run phase1 on newer-rig sweeps with M injected from session.json.

The newer-rig path layout doesn't carry mag_label in the sweep label, so
``m_lookup.resolve`` returns NaN and phase1 skips. This script patches
``phase1.resolve`` to read M from the session.json under each sweep's
output root, then writes per_shot_per_tile.csv + peaks_v2.csv.

Hard-coded for session 2026-05-13_230021, Sigma 150 + 6T at M=1.6.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import tile_sharpness.phase1 as phase1_mod
from tile_sharpness.m_lookup import MagLookup, MLookup
from tile_sharpness.sweeps import discover_newer

SESSION_ROOT = Path("/home/alson/macro-lens-test-output/2026-05-13_230021")
TARGET_LENS = "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 6T"
OUT_DIR = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness/out_newer_validation")


def m_from_session_json(lens: str) -> float:
    data = json.loads((SESSION_ROOT / "session.json").read_text())
    for cfg in data["lens_configs"]:
        if cfg["slug"] == lens:
            return float(cfg["magnification"])
    raise KeyError(f"no lens_config matching {lens!r}")


def main() -> None:
    M = m_from_session_json(TARGET_LENS)
    print(f"M (from session.json) for {TARGET_LENS!r} = {M}")

    original_resolve = phase1_mod.resolve

    def patched_resolve(sweep, mlookup):
        if sweep.family == "newer-rig" and sweep.lens == TARGET_LENS:
            return MagLookup(
                measured=M, source="session_json", confidence="planned",
            )
        return original_resolve(sweep, mlookup)

    phase1_mod.resolve = patched_resolve

    sweeps = [
        s for s in discover_newer()
        if s.lens == TARGET_LENS
        and "2026-05-13_230021" in s.label
    ]
    print(f"Found {len(sweeps)} sweeps")
    for s in sweeps:
        print(f"  {s.id}  ({len(s.shots)} shots)")

    OUT_DIR.mkdir(exist_ok=True)
    all_rows, peaks_rows = [], []
    mlookup = MLookup()
    for sweep in sweeps:
        print(f"Scoring {sweep.label}...")
        rows, peaks = phase1_mod.analyse_sweep_phase1(
            sweep, mlookup, workers=8,
        )
        print(f"  → {len(rows)} per-shot-per-tile rows, {len(peaks)} peaks_v2 rows")
        all_rows.extend(rows)
        peaks_rows.extend(peaks)

    pd.DataFrame(all_rows).to_csv(OUT_DIR / "per_shot_per_tile.csv", index=False)
    pd.DataFrame(peaks_rows).to_csv(OUT_DIR / "peaks_v2.csv", index=False)
    print(f"Wrote {OUT_DIR / 'per_shot_per_tile.csv'}")


if __name__ == "__main__":
    main()
