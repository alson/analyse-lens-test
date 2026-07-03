#!/usr/bin/env python3
"""POC: probe whether the Z7 relmtf pipeline can absorb the D7200 wafer macro data.

Sample-tests two things on a handful of 2025-08-06 / 2025-08-19 D7200 sweeps
(NOT a production run; writes only to out_d7200_probe/):

  1. Autonomous reg_auto registration (via relmtf_run.register_config — the exact
     production frame-selection + reg_auto estimator). Reports fit RMSE (px),
     recovered scale, implied atlas-M, and object-space RMSE computed with BOTH the
     Z7 pitch (4.35um, what the pipeline currently hardcodes) and the D7200 pitch
     (3.91um, correct) to show the reg_guard mis-calibration.

  2. Lighting variation: per-shot central-ROI mean luma across each sweep, plus a Z7
     manual baseline sweep, to quantify drift that would confound a through-focus
     amplitude metric.

Run on nufan (heavy JPEG decode):
  ssh nufan; cd .../tile-sharpness
  export UV_PROJECT_ENVIRONMENT="$HOME/.cache/uv-venvs/tile-sharpness"
  uv run --no-sync python scripts/poc_d7200_probe.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

TS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TS / "src"))
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data")
OUT = TS / "out_d7200_probe"
OUT.mkdir(exist_ok=True)

D7200_PITCH_UM = 3.91
Z7_PITCH_UM = 4.35


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


RR = _load("relmtf_run", TS / "scripts" / "relmtf_run.py")

# Sweeps: (session, relative sweep dir). Span lenses + both dates; Sigma150 F8 on
# BOTH dates for a direct cross-date lighting check.
D7200_SWEEPS = [
    ("2025-08-06", "Nikon AF Micro-Nikkor 200mm f_4D IF-ED/F7.1"),
    ("2025-08-06", "Sigma APO Macro 150mm F2.8 EX DG OS HSM/F8"),
    ("2025-08-19", "Sigma APO Macro 150mm F2.8 EX DG OS HSM/F8"),
    ("2025-08-19", "Nikon Micro-Nikkor 55mm f_2.8 AIS 287318/F8"),
]
# Z7 manual baseline (2025-10-17 shares the D7200 <lens>/<aperture>/ layout).
Z7_BASELINE = ("2025-10-17", None)  # resolved at runtime: first lens/F8-ish sweep


def sweep_jpgs(d: Path):
    js = sorted(d.glob("*.jpg")) + sorted(d.glob("*.JPG"))
    return [j for j in js if j.name != "pick.jpg"]


def central_luma_profile(jpgs, frac=0.25):
    """Mean luma of the central ROI per shot (draft-decoded small for speed)."""
    vals = []
    for jp in jpgs:
        im = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        h, w = im.shape
        cy, cx = h // 2, w // 2
        ry, rx = int(h * frac / 2), int(w * frac / 2)
        roi = im[cy - ry:cy + ry, cx - rx:cx + rx]
        vals.append(float(roi.mean()))
    return np.asarray(vals, float)


def lighting_stats(name, vals):
    if len(vals) == 0:
        return dict(sweep=name, n=0)
    mn, mx, mean = float(vals.min()), float(vals.max()), float(vals.mean())
    cv = float(vals.std() / mean) if mean else float("nan")
    # peak-to-peak in stops (log2 of max/min brightness)
    stops = float(np.log2(mx / mn)) if mn > 0 else float("nan")
    return dict(sweep=name, n=len(vals), luma_min=round(mn, 1), luma_max=round(mx, 1),
                luma_mean=round(mean, 1), cv=round(cv, 4), pp_stops=round(stops, 3))


def probe_registration(session, rel):
    d = RAW / session / rel
    jpgs = sweep_jpgs(d)
    rec = dict(session=session, sweep=rel, n_jpg=len(jpgs))
    if not jpgs:
        rec["error"] = "no jpgs"
        return rec
    try:
        p, M, _ = RR.register_config(d, node=None)
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"register_config raised: {e!r}"
        return rec
    if p is None:
        rec["registered"] = False
        rec["note"] = "no plausible lock (reg_guard rejected all candidate frames)"
        return rec
    rmse_px = float(p.get("reg_fit_rmse_px", float("nan")))
    rec.update(
        registered=True,
        M=round(float(M), 4),
        scale=round(float(p["scale"]), 4),
        theta_deg=round(float(p.get("theta_deg", float("nan"))), 3),
        rmse_px=round(rmse_px, 3),
        n_refine_int=int(p.get("n_refine_intersections", 0) or 0),
        rmse_um_z7pitch=round(rmse_px * Z7_PITCH_UM / M, 2),
        rmse_um_d7200pitch=round(rmse_px * D7200_PITCH_UM / M, 2),
        model=p.get("distortion_model", p.get("model", "?")),
    )
    rec["passes_guard_25um_d7200"] = rec["rmse_um_d7200pitch"] <= 25.0
    return rec


def resolve_z7_baseline():
    base = RAW / "2025-10-17"
    if not base.is_dir():
        return None
    for lensdir in sorted(base.glob("*")):
        if not lensdir.is_dir() or lensdir.name.lower().startswith("results"):
            continue
        for ap in ("F8", "F7.1", "F11", "F5.6"):
            d = lensdir / ap
            if d.is_dir() and sweep_jpgs(d):
                return ("2025-10-17", f"{lensdir.name}/{ap}")
    return None


def main():
    report = {"registration": [], "lighting": []}

    print("=== REGISTRATION PROBE (D7200) ===", flush=True)
    for session, rel in D7200_SWEEPS:
        r = probe_registration(session, rel)
        report["registration"].append(r)
        print(json.dumps(r), flush=True)

    print("\n=== LIGHTING PROBE ===", flush=True)
    lighting_targets = list(D7200_SWEEPS)
    z7b = resolve_z7_baseline()
    if z7b:
        lighting_targets.append(z7b)
        print(f"(Z7 baseline: {z7b[1]})", flush=True)
    for session, rel in lighting_targets:
        d = RAW / session / rel
        vals = central_luma_profile(sweep_jpgs(d))
        s = lighting_stats(f"{session}/{rel}", vals)
        report["lighting"].append(s)
        print(json.dumps(s), flush=True)

    (OUT / "probe_report.json").write_text(json.dumps(report, indent=2))
    print(f"\nWROTE {OUT / 'probe_report.json'}", flush=True)


if __name__ == "__main__":
    main()
