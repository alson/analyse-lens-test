#!/usr/bin/env python3
"""POC 4 driver — FIELD CURVATURE from the best-focus surface (tilt regressed out).

Joins the POC 3 per-patch physical focus table (``mu_mm`` per patch) to the
POC 1 field-geometry shards (``px, py, field_height`` per patch), then for each
config fits the best-focus surface JOINTLY as

    mu_mm ≈ c + a·x + b·y + k·(x²+y²)

so the plane TILT (a,b,c) is regressed out SIMULTANEOUSLY with the curvature k.
The plane tilt is rig / sensor-vs-subject alignment (degenerate with any
lens-induced tilt from a single config) — it is NOT a lens property, so it is
CORRECTED and NOT reported. Everything downstream is derived from k / from the
residual of the full fit, on the tilt-REMOVED surface:

  * PRIMARY field curvature = DoF-normalised centre→corner sag = sag_mm / median
    through-focus FWHM (dimensionless, step-calibration-free, M-robust).
  * signed physical sag µm (+ = corners focus farther) + surface radius mm
    (flagged low-confidence where step is DoF-estimated at M>1),
  * RMS residual after the plane+quadratic fit (field irregularity),
  * decentering as the tilt-INDEPENDENT curvature-vertex offset from frame
    centre (reported only when robustly estimable).

All numbers are reported on the COVERAGE-CLEAN subset (coverage_flag==ok AND not
fwhm_imputed); N_used / N_excluded are reported.

Also emits, per config: a tilt-removed best-focus residual MAP (PNG) and a radial
best-focus-vs-field-height profile with the fitted quadratic overlaid.

Usage:
    uv run python scripts/poc_field_geometry.py \
        [--physical out_poc_refine_fwhm/per_patch_physical_2026-01-29.csv] \
        [--fieldtag-glob 'cross_m_relative_mtf_poc_focus_out/fieldtag_shard_*.csv'] \
        [--out-dir out_poc_field_geometry] [--no-maps]
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from tile_sharpness.field_geometry_focus import (
    Z7_CENTRE,
    Z7_HALF_DIAG_PX,
    analyse_field_geometry,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DEFAULT_PHYSICAL = ROOT / "out_poc_refine_fwhm" / "per_patch_physical_2026-01-29.csv"
DEFAULT_FIELDTAG_GLOB = str(
    ROOT / "cross_m_relative_mtf_poc_focus_out" / "fieldtag_shard_*.csv"
)
DEFAULT_OUT = ROOT / "out_poc_field_geometry"

CX, CY = Z7_CENTRE


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


def _slug(config: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in config).strip("_")[:80]


def _result_row(config: str, M: float, step_low_conf: bool,
                n_total: int, clean: pd.DataFrame) -> tuple[dict, object | None]:
    """Run the tilt-removed geometry on the coverage-clean patches → CSV row."""
    n_used = len(clean)
    n_excl = n_total - n_used
    base = {
        "config": config, "M": M, "step_low_confidence": step_low_conf,
        "n_used": n_used, "n_excluded": n_excl, "n_total": n_total,
    }
    if n_used < 4:
        base["note"] = "too_few_clean_patches"
        return base, None
    fwhm_med = float(clean["fwhm_mm"].median())
    res = analyse_field_geometry(
        clean["px"].to_numpy(float), clean["py"].to_numpy(float),
        clean["mu_mm"].to_numpy(float), fwhm_med,
        cx=CX, cy=CY, half_diag_px=Z7_HALF_DIAG_PX,
    )
    c, v, a = res.curvature, res.vertex, res.astigmatism
    base.update({
        "fwhm_mm_median": fwhm_med,
        "sag_dof": c.sag_dof,                 # PRIMARY
        "sag_um": c.sag_um,                   # signed physical sag
        "sag_sign": "corners_farther" if c.sag_um > 0 else "corners_nearer",
        "curv_radius_mm": c.radius_mm,
        "curv_k_mm_per_px2": c.k_mm_per_px2,
        "rms_residual_um": c.rms_residual_um,  # field irregularity (after tilt+curv)
        "fh_max": c.fh_max,
        "vertex_estimable": v.estimable,
        "vertex_offset_px": v.offset_px,
        "vertex_offset_field_frac": v.offset_field_frac,
        "vertex_dx0_px": v.dx0_px,
        "vertex_dy0_px": v.dy0_px,
        "vertex_note": v.note,
        "astig_available": a.available,
        "astig_note": a.note,
        "note": "",
    })
    return base, (res, clean, fwhm_med)


def _make_maps(config: str, res, clean: pd.DataFrame, fwhm_med: float,
               out_dir: Path) -> str:
    """Tilt-removed residual map + radial profile with fitted quadratic overlay."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    c = res.curvature
    px = clean["px"].to_numpy(float)
    py = clean["py"].to_numpy(float)
    mu = clean["mu_mm"].to_numpy(float)
    fh = clean["field_height"].to_numpy(float)
    xr, yr = px - CX, py - CY
    r2 = xr * xr + yr * yr
    # tilt-removed surface = mu minus the fitted PLANE (keep curvature + resid)
    plane = c.c_mm + c.a_mm_per_px * xr + c.b_mm_per_px * yr
    detrended = (mu - plane) * 1000.0   # µm, curvature + irregularity, tilt gone

    fig, (axm, axp) = plt.subplots(1, 2, figsize=(13, 5.2))
    # -- map: detrended best-focus over the frame --
    med = float(np.nanmedian(detrended))
    vmax = float(np.nanpercentile(np.abs(detrended - med), 98)) or 1.0
    sc = axm.scatter(px, py, c=detrended - med,
                     cmap="RdBu_r", vmin=-vmax, vmax=vmax, s=42,
                     edgecolors="k", linewidths=0.2)
    axm.set_xlim(0, 8256); axm.set_ylim(5504, 0)   # image-y down
    axm.set_aspect("equal")
    axm.scatter([CX], [CY], marker="+", c="k", s=140, label="frame centre")
    if res.vertex.estimable:
        axm.scatter([res.vertex.x0_px], [res.vertex.y0_px], marker="x",
                    c="green", s=140, label="curvature vertex")
    axm.set_title(f"tilt-removed best-focus residual (µm)\n{config[:52]}", fontsize=9)
    axm.set_xlabel("px"); axm.set_ylabel("py (image-y down)")
    axm.legend(fontsize=7, loc="upper right")
    fig.colorbar(sc, ax=axm, fraction=0.046, pad=0.04, label="µm about median")
    # -- radial profile: tilt-removed residual (plane incl. intercept removed) vs
    #    field height, so points sit ON the fitted quadratic (k·r² + irregularity) --
    axp.scatter(fh, detrended, s=22, alpha=0.6, c="tab:blue",
                label="patches (tilt removed)")
    fhg = np.linspace(0, fh.max(), 100)
    px_at = fhg * Z7_HALF_DIAG_PX
    axp.plot(fhg, c.k_mm_per_px2 * px_at * px_at * 1000.0, "r-", lw=2,
             label=f"fitted quadratic  sag={c.sag_um:+.0f}µm  ({c.sag_dof:+.2f} DoF)")
    axp.set_xlabel("field height (0=centre, 1=corner)")
    axp.set_ylabel("best-focus shift from centre (µm)")
    axp.set_title(f"radial curvature profile  (FWHM={fwhm_med:.2f}mm)", fontsize=9)
    axp.legend(fontsize=8); axp.grid(alpha=0.3)
    fig.tight_layout()
    p = out_dir / f"map_{_slug(config)}.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return str(p)


def run(physical_csv: Path, fieldtag_glob: str, out_dir: Path,
        make_maps: bool = True) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    joined = load_joined(physical_csv, fieldtag_glob)
    joined.to_csv(out_dir / "joined_per_patch.csv", index=False)

    rows: list[dict] = []
    map_paths: list[str] = []
    for config, g in joined.groupby("config", sort=True):
        g = g[g["px"].notna() & g["mu_mm"].notna()].copy()
        M = float(g["M"].iloc[0])
        step_low_conf = bool(g["step_low_confidence"].iloc[0])
        n_total = len(g)
        clean = g[(g["coverage_flag"] == "ok")
                  & (~g["fwhm_imputed"].astype(bool))].copy()
        row, artifacts = _result_row(config, M, step_low_conf, n_total, clean)
        rows.append(row)
        if make_maps and artifacts is not None:
            res, cl, fwhm_med = artifacts
            map_paths.append(_make_maps(config, res, cl, fwhm_med, out_dir))

    res = pd.DataFrame(rows)
    out_csv = out_dir / "per_config_field_geometry.csv"
    res.to_csv(out_csv, index=False)
    print(f"[ok] wrote {out_csv} ({len(res)} configs, coverage-clean only)")
    if map_paths:
        print(f"[ok] wrote {len(map_paths)} maps to {out_dir}/map_*.png")
    return res


def _print_summary(res: pd.DataFrame) -> None:
    pd.set_option("display.width", 240)
    cols = ["config", "M", "step_low_confidence", "n_used", "n_excluded",
            "sag_dof", "sag_um", "sag_sign", "curv_radius_mm", "rms_residual_um",
            "vertex_estimable", "vertex_offset_px"]
    show = res[[c for c in cols if c in res.columns]].copy()
    for c in ["sag_dof", "sag_um", "curv_radius_mm", "rms_residual_um",
              "vertex_offset_px"]:
        if c in show.columns:
            show[c] = show[c].round(3)
    print("\n=== FIELD CURVATURE (tilt removed, coverage-clean) ===")
    print("primary = sag_dof (centre→corner sag / median through-focus FWHM)\n")
    print(show.to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--physical", type=Path, default=DEFAULT_PHYSICAL)
    ap.add_argument("--fieldtag-glob", default=DEFAULT_FIELDTAG_GLOB)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-maps", action="store_true")
    args = ap.parse_args()
    res = run(args.physical, args.fieldtag_glob, args.out_dir,
              make_maps=not args.no_maps)
    _print_summary(res)


if __name__ == "__main__":
    main()
