"""Task 2: atlas-measure M for every distinct (lens, mag_label) accessory combo.

M is geometric -> aperture-independent, and the characterise manifest is keyed on
(slug, mag_label), so ONE registration per (lens, mag_label) serves all apertures.
For each combo we pick a clean moderate-aperture stack (prefer F8/F11), rank frames
by reduced-res central lapvar (fast), then robustly register the sharpest few +
a spread and keep the LOWEST full-res refinement residual (n_int>0).

Writes atlas_m_results.csv incrementally (resumable: skips combos already done).
Compares atlas-M to nominal/path-parsed M and flags the gap.
"""
from __future__ import annotations
import csv, importlib.util, time, sys
from pathlib import Path
import cv2
import numpy as np

WA = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("reg_auto", WA / "reg_auto.py")
ra = importlib.util.module_from_spec(spec); spec.loader.exec_module(ra)

M_ANCHOR_SCALE = 1.6549
IMAGE_W, IMAGE_H = 8256, 5504
IN = WA / "accessory_configs.csv"
OUT = WA / "atlas_m_results.csv"
AP_PREF = ["F8", "F8.0", "f_8", "F11", "F11.0", "f_11", "F5.6", "f_5_6", "F16"]
FIELDS = ["lens", "mag_label", "nominal_M", "ap_used", "date", "n_shots",
          "atlas_M", "gap_pct", "ref_rmse_px", "n_int", "col_first", "col_method",
          "row_first", "row_method", "frame", "status"]


def reduced_lapvar(path):
    g = cv2.imread(str(path), cv2.IMREAD_REDUCED_GRAYSCALE_4)
    if g is None:
        return -1.0
    h, w = g.shape
    c = g[h//2-200:h//2+200, w//2-200:w//2+200]
    return float(cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var())


def robust_register(jpgs):
    lv = sorted(((reduced_lapvar(jp), jp) for jp in jpgs), reverse=True)
    cand = [jp for _, jp in lv[:3]] + [jpgs[int(len(jpgs)*f)] for f in (0.4, 0.6)]
    best = None
    for jp in dict.fromkeys(cand):
        try:
            p = ra.register_and_refine("cfg", path=str(jp), anchors=None)
        except Exception:
            continue
        if p is None or not p.get("n_refine_intersections"):
            continue
        r = p["reg_fit_rmse_px"]
        if best is None or r < best[0]:
            best = (r, jp, p)
    return best


def pick_ap_dir(rows_for_combo):
    """rows_for_combo: list of CSV rows (same lens,mag) differing by aperture.
    Prefer F8/F11; return (ap_dir_path, ap_name, n_shots, date)."""
    by_ap = {r["aperture"]: r for r in rows_for_combo}
    for ap in AP_PREF:
        if ap in by_ap:
            r = by_ap[ap]
            return Path(r["sample"]).parent, ap, int(r["n_shots"]), r["date"]
    # else the one with most shots
    r = max(rows_for_combo, key=lambda r: int(r["n_shots"]))
    return Path(r["sample"]).parent, r["aperture"], int(r["n_shots"]), r["date"]


def main():
    rows = list(csv.DictReader(open(IN)))
    combos = {}
    for r in rows:
        combos.setdefault((r["lens"], r["mag_label"]), []).append(r)

    done = set()
    if OUT.exists():
        for r in csv.DictReader(open(OUT)):
            done.add((r["lens"], r["mag_label"]))
    new = not OUT.exists()
    f = OUT.open("a", newline="")
    w = csv.DictWriter(f, fieldnames=FIELDS)
    if new:
        w.writeheader(); f.flush()

    items = sorted(combos.items())
    for i, ((lens, mag), crows) in enumerate(items, 1):
        if (lens, mag) in done:
            continue
        ap_dir, ap, n, date = pick_ap_dir(crows)
        nominal = float(crows[0]["nominal_M"])
        jpgs = sorted(ap_dir.glob("*.jpg")) or sorted(ap_dir.glob("*.JPG"))
        t0 = time.time()
        rec = dict(lens=lens, mag_label=mag, nominal_M=f"{nominal:.4f}", ap_used=ap,
                   date=date, n_shots=len(jpgs), atlas_M="", gap_pct="", ref_rmse_px="",
                   n_int="", col_first="", col_method="", row_first="", row_method="",
                   frame="", status="")
        try:
            br = robust_register(jpgs) if jpgs else None
            if br is None:
                rec["status"] = "FAILED"
            else:
                rmse, frame, p = br
                M = p["scale"] / M_ANCHOR_SCALE
                rec.update(atlas_M=f"{M:.4f}", gap_pct=f"{(M/nominal-1)*100:+.1f}",
                           ref_rmse_px=f"{rmse:.2f}", n_int=p["n_refine_intersections"],
                           col_first=p["reg_col_first"], col_method=p["reg_col_method"].split("(")[0],
                           row_first=p["reg_row_first"], row_method=p["reg_row_method"],
                           frame=frame.name, status="ok")
        except Exception as e:
            rec["status"] = f"ERROR:{type(e).__name__}"
        w.writerow(rec); f.flush()
        print(f"[{i}/{len(items)}] {lens[:45]:45} {mag:9} nom={nominal:.3f} "
              f"-> {rec['status']:8} M={rec['atlas_M'] or '-':>7} "
              f"gap={rec['gap_pct'] or '-':>6} rmse={rec['ref_rmse_px'] or '-':>6} "
              f"({time.time()-t0:.0f}s)", flush=True)
    f.close()
    print("DONE")


if __name__ == "__main__":
    main()
