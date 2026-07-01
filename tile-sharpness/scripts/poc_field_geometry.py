#!/usr/bin/env python3
"""POC 4 driver — decentering + field curvature from the best-focus surface.

Joins the POC 3 per-patch physical focus table (``mu_mm`` per patch) to the
POC 1 field-geometry shards (``px, py, field_height, angle_deg`` per patch),
then for each config fits:

  1. a plane ``mu_mm ≈ a·px + b·py + c`` → subject-space tilt (deg) + azimuth,
  2. the plane-removed radial residual vs field_height² → field curvature
     (sag µm, RMS µm),
  3. left-right / top-bottom best-focus asymmetry → decentering direction,
  4. (astigmatism — only if a per-patch edge orientation is available; this
     dataset has none, so it is reported as unavailable).

The load-bearing question: does the 2026-01-29 cohort's apparent top-vs-bottom
"decentering" survive excluding under-covered patches? So every config is run
TWICE — ALL patches, and patches with ``coverage_flag == ok`` & not
``fwhm_imputed`` only ("clean"). ``step_low_confidence`` (M>1.10) sweeps have an
uncertain ABSOLUTE mm scale: tilt DIRECTION/azimuth and decentering SIGN are
still valid (step is a global scale), but absolute curvature µm and tilt-deg are
flagged ``step_low_confidence=True``.

Pure fitting only — light compute. Reads CSVs produced by POCs 1-3.

Usage:
    uv run python scripts/poc_field_geometry.py \
        [--physical out_poc_refine_fwhm/per_patch_physical_2026-01-29.csv] \
        [--fieldtag-glob 'cross_m_relative_mtf_poc_focus_out/fieldtag_shard_*.csv'] \
        [--out-dir out_poc_field_geometry]
"""

from __future__ import annotations

import argparse
import glob
import math
from pathlib import Path

import numpy as np
import pandas as pd

from tile_sharpness.field_geometry_focus import analyse_field_geometry

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DEFAULT_PHYSICAL = ROOT / "out_poc_refine_fwhm" / "per_patch_physical_2026-01-29.csv"
DEFAULT_FIELDTAG_GLOB = str(
    ROOT / "cross_m_relative_mtf_poc_focus_out" / "fieldtag_shard_*.csv"
)
DEFAULT_OUT = ROOT / "out_poc_field_geometry"


def load_joined(physical_csv: Path, fieldtag_glob: str) -> pd.DataFrame:
    """Join the POC 3 physical table to the POC 1 field-geometry shards."""
    phys = pd.read_csv(physical_csv)
    shards = sorted(glob.glob(fieldtag_glob))
    if not shards:
        raise SystemExit(f"no fieldtag shards matched {fieldtag_glob!r}")
    ft = pd.concat([pd.read_csv(s) for s in shards], ignore_index=True)
    geo_cols = ["config", "sid", "patch", "px", "py", "dist_px",
                "field_height", "angle_deg"]
    ft = ft[geo_cols].drop_duplicates(subset=["config", "sid", "patch"])
    joined = phys.merge(ft, on=["config", "sid", "patch"], how="left")
    miss = joined["px"].isna().sum()
    if miss:
        print(f"[warn] {miss} patches missing field geometry after join")
    return joined


def _result_row(config: str, M: float, step_low_conf: bool,
                subset: str, n_total: int, sub: pd.DataFrame) -> dict:
    """Run the geometry on one patch subset and flatten to a CSV row."""
    n = len(sub)
    base = {
        "config": config,
        "M": M,
        "step_low_confidence": step_low_conf,
        "subset": subset,
        "n_patches": n,
        "n_patches_all": n_total,
    }
    if n < 4:
        base["note"] = "too_few_patches"
        return base
    res = analyse_field_geometry(
        sub["px"].to_numpy(float), sub["py"].to_numpy(float),
        sub["mu_mm"].to_numpy(float),
        sub["field_height"].to_numpy(float),
        sub["angle_deg"].to_numpy(float),
        float(M),
    )
    p, c, d, a = res.plane, res.curvature, res.decentering, res.astigmatism
    base.update({
        "tilt_x_deg": p.tilt_x_deg,
        "tilt_y_deg": p.tilt_y_deg,
        "tilt_mag_deg": p.tilt_mag_deg,
        "tilt_azimuth_deg": p.tilt_azimuth_deg,
        "plane_rms_mm": p.rms_residual_mm,
        "curv_sag_um": c.sag_um,
        "curv_coef_mm_per_fh2": c.curv_coef_mm_per_fh2,
        "curv_rms_um": c.rms_residual_um,
        "dec_lr_mm": d.lr_mm,
        "dec_tb_mm": d.tb_mm,
        "dec_n_left": d.n_left, "dec_n_right": d.n_right,
        "dec_n_top": d.n_top, "dec_n_bottom": d.n_bottom,
        "astig_available": a.available,
        "astig_delta_mm": a.delta_mm,
        "astig_note": a.note,
        "note": "",
    })
    return base


def run(physical_csv: Path, fieldtag_glob: str, out_dir: Path) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    joined = load_joined(physical_csv, fieldtag_glob)
    joined.to_csv(out_dir / "joined_per_patch.csv", index=False)

    rows: list[dict] = []
    for config, g in joined.groupby("config", sort=True):
        g = g[g["px"].notna() & g["mu_mm"].notna()].copy()
        M = float(g["M"].iloc[0])
        step_low_conf = bool(g["step_low_confidence"].iloc[0])
        n_total = len(g)
        clean = g[(g["coverage_flag"] == "ok") & (~g["fwhm_imputed"].astype(bool))]
        rows.append(_result_row(config, M, step_low_conf, "all", n_total, g))
        rows.append(_result_row(config, M, step_low_conf, "clean", n_total, clean))

    res = pd.DataFrame(rows)
    out_csv = out_dir / "per_config_field_geometry.csv"
    res.to_csv(out_csv, index=False)
    print(f"[ok] wrote {out_csv} ({len(res)} rows, "
          f"{res['config'].nunique()} configs × {{all,clean}})")
    return res


def _print_summary(res: pd.DataFrame) -> None:
    pd.set_option("display.width", 240)
    pd.set_option("display.max_colwidth", 52)
    wide = res.pivot_table(
        index="config",
        columns="subset",
        values=["tilt_mag_deg", "curv_sag_um", "dec_tb_mm", "dec_lr_mm",
                "n_patches"],
        aggfunc="first",
    )
    print("\n=== tilt magnitude (deg), curvature sag (µm), T-B/L-R decentering (mm) ===")
    print("    [all] vs [clean] = coverage_flag==ok & not imputed\n")
    show = res[["config", "subset", "M", "step_low_confidence", "n_patches",
                "tilt_mag_deg", "tilt_azimuth_deg", "curv_sag_um", "curv_rms_um",
                "dec_lr_mm", "dec_tb_mm"]].copy()
    for col in ["tilt_mag_deg", "tilt_azimuth_deg", "curv_sag_um", "curv_rms_um",
                "dec_lr_mm", "dec_tb_mm"]:
        show[col] = show[col].round(3)
    print(show.to_string(index=False))


# --------------------------------------------------------------------------- #
# Cross-check vs characterise.py on the matching peaks_v2 sweeps
# --------------------------------------------------------------------------- #
# Maps a POC-3 config → (peaks_v2 sweep-id substring) for the 2026-01-29 F8
# sweeps that exist in the committed peaks_v2 outputs. characterise uses a
# DIFFERENT focus metric (argmax_shot_idx) and patch set (≤9 ring tiles) than
# POC 4 (Gaussian mu_mm over ~85 dense patches); feeding it the SAME DoF step
# isolates the comparison to metric+patch-set.
_CROSSCHECK_FRAGS = {
    "NIKKOR Z MC 105mm f_2.8 VR S | 1_1 | F8": "NIKKOR_Z_MC_105mm_f_2.8_VR_S__1_1__F8",
    "Nikon AF Micro-Nikkor 200mm f_4D IF-ED | 1_1 | F8": "200mm_f_4D_IF-ED__1_1__F8",
    "Nikon Micro-Nikkor 55mm f_2.8 AIS 287318 | 1_1 | F8": "55mm_f_2.8_AIS_287318__1_1__F8",
    "Nikon Micro-Nikkor Auto 55mm f_3.5 209088 | 1_1 | F8": "Auto_55mm_f_3.5_209088__1_1__F8",
    "Sigma APO Macro 150mm F2.8 EX DG OS HSM | 1_1 | F8": "Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM__1_1__F8",
    "Sigma Macro 105mm F2.8 EX DG OS HSM | 1_1 | F8": "Sigma_Macro_105mm_F2.8_EX_DG_OS_HSM__1_1__F8",
}


def crosscheck_characterise(physical_csv: Path, out_dir: Path) -> pd.DataFrame:
    """Run characterise_sweep on the matching peaks_v2 sweeps for comparison."""
    from tile_sharpness.characterise import characterise_sweep

    phys = pd.read_csv(physical_csv)
    steps = phys.groupby("config")["step_mm"].first()
    frames = []
    for f in glob.glob(str(ROOT / "out_*" / "peaks_v2.csv")):
        d = pd.read_csv(f)
        frames.append(d)
    if not frames:
        print("[warn] no peaks_v2.csv found for cross-check")
        return pd.DataFrame()
    allp = pd.concat(frames, ignore_index=True)
    older = allp[allp["sweep"].str.contains("older-2026-01-29")
                 & allp["sweep"].str.contains("F8")]
    rows = []
    for cfg, frag in _CROSSCHECK_FRAGS.items():
        sw = older[older["sweep"].str.contains(frag, regex=False)]
        if sw.empty or cfg not in steps.index:
            continue
        swid = sw["sweep"].iloc[0]
        g = sw[sw["sweep"] == swid]
        out = characterise_sweep(g, rail_step_mm=float(steps[cfg]))
        tx, ty = out["subject_tilt_x_deg"], out["subject_tilt_y_deg"]
        if np.isfinite(tx) and np.isfinite(ty):
            mag = math.degrees(math.atan(math.hypot(math.tan(math.radians(tx)),
                                                    math.tan(math.radians(ty)))))
        else:
            mag = float("nan")
        rows.append({
            "config": cfg, "n_positions": out["n_positions"],
            "chr_tilt_x_deg": tx, "chr_tilt_y_deg": ty, "chr_tilt_mag_deg": mag,
            "chr_field_curv_um_rms": out["field_curvature_um_rms"],
            "chr_dec_fx_lr": out.get("decentering_fx_lr"),
            "chr_dec_fx_tb": out.get("decentering_fx_tb"),
            "step_mm_used": float(steps[cfg]),
        })
    cc = pd.DataFrame(rows)
    cc.to_csv(out_dir / "crosscheck_characterise.csv", index=False)
    print(f"[ok] wrote {out_dir/'crosscheck_characterise.csv'} ({len(cc)} configs)")
    return cc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--physical", type=Path, default=DEFAULT_PHYSICAL)
    ap.add_argument("--fieldtag-glob", default=DEFAULT_FIELDTAG_GLOB)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-crosscheck", action="store_true",
                    help="skip the characterise.py cross-check")
    args = ap.parse_args()
    res = run(args.physical, args.fieldtag_glob, args.out_dir)
    _print_summary(res)
    if not args.no_crosscheck:
        cc = crosscheck_characterise(args.physical, args.out_dir)
        if not cc.empty:
            pd.set_option("display.width", 200)
            print("\n=== cross-check: characterise.py on matching peaks_v2 (same step) ===")
            print(cc.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
