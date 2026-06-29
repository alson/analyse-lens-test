"""Pad-edge resolution ranking: the production replacement for the groove-scribe
LSF metric, which specular-over-reads the diffraction ceiling (REPORT_taskAD §E.4).

Per (lens, mag_label) combo: register ONCE via reg_auto (reused across the combo's
apertures — framing is fixed within a session). Per aperture, at each of the 5
field positions (centre + 4 corners) we locate the nearest in-FOV BOND-PAD region
(true metal->substrate reflectance edge, 14/16 die types), detect the longest
straight contrast edge slanted 2-15 deg off axis, pick THAT position's best-focus
shot (roi_lapvar argmax), and measure MTF50 with the super-resolved single-step
erf estimator (slanted_edge.mtf50_step_erf). Subject lp/mm = cy/px * 229.9 * M;
headroom = measured / diffraction ceiling (optics, N_eff = N*(1+M)).

Env: RANK_CONFIGS (input CSV), RANK_OUT (output CSV), SHARD="i/N" (shard), RANK_LIMIT.
"""
from __future__ import annotations
import csv, importlib.util, os, sys, time
from pathlib import Path
import cv2, numpy as np

TS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TS / "src"))
from tile_sharpness import optics
from tile_sharpness.methods.slanted_edge import mtf50_step_erf
from tile_sharpness.methods import pad_edge as pe

_spec = importlib.util.spec_from_file_location("acm", TS / "scripts" / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(acm)
reg_auto = acm.reg_auto
ATLAS = reg_auto.ATLAS

IN = Path(os.environ.get("RANK_CONFIGS",
    str(TS.parent / "wafer-atlas/scripts/accessory_configs.csv")))
OUT = Path(os.environ.get("RANK_OUT",
    str(TS / "out_padedge/accessory_padedge.csv")))
PIPELINE_DATES = {"2026-01-29", "2026-02-18"}
APS = {"F8", "F8.0", "F11", "F11.0"}
AP_REG_PREF = ["F8", "F8.0", "F11", "F11.0"]
HALF_WIN_ESF = 30.0
FIELDS = ["lens", "mag_label", "nominal_M", "atlas_M", "aperture",
          "n_eff", "ceiling_lpmm", "ceiling_cypx",
          "centre", "TL", "TR", "BL", "BR", "corner_mean", "uniformity",
          "centre_cypx", "centre_headroom", "n_targets", "reg_rmse_px",
          "n_int", "covered", "status"]


def grid_xy(col, row, u, v, p):
    if "k1" in p:
        return reg_auto.grid_xy_distorted(col + u, row + v, p)
    return reg_auto.af.grid_xy(col + u, row + v, p, ATLAS)


def n_marked_from_ap(ap: str) -> float:
    return float(ap.lstrip("Ff_").replace("_", "."))


def measure_aperture(aff, M, ap_dir, picks):
    """Per-target pad-edge MTF50 (subject lp/mm + cy/px) at each target's own
    best-focus shot. ``picks`` = {name: (region, seg, off, len)} from pick_padedge.
    Returns (n_jpgs, {name: lpmm}, {name: cypx})."""
    jpgs = sorted(ap_dir.glob("*.jpg")) or sorted(ap_dir.glob("*.JPG"))
    if not jpgs or not picks:
        return (len(jpgs), {}, {})
    best = {name: (-1.0, None) for name in picks}   # (lapvar, mtf50_cypx)
    for jp in jpgs:
        g = acm.decode(jp)
        if g is None:
            continue
        gf = g.astype(np.float32)
        for name, (r, seg, off, L) in picks.items():
            mx, my = (seg.x0 + seg.x1) / 2.0, (seg.y0 + seg.y1) / 2.0
            lv = acm.roi_lapvar(g, mx, my)
            if lv > best[name][0]:
                m = mtf50_step_erf(gf, seg, half_window_px=HALF_WIN_ESF)
                best[name] = (lv, m)
    lpmm, cypx = {}, {}
    for name in picks:
        m = best[name][1]
        if m:
            cypx[name] = m
            lpmm[name] = m * acm.LPMM_PER_CYPX * M
    return len(jpgs), lpmm, cypx


def main():
    rows = [r for r in csv.DictReader(open(IN))
            if r["date"] in PIPELINE_DATES and r["aperture"] in APS]
    combos = {}
    for r in rows:
        combos.setdefault((r["lens"], r["mag_label"]), []).append(r)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    shard = os.environ.get("SHARD")
    if shard:
        si, sn = (int(x) for x in shard.split("/"))
        out_path = OUT.with_name(OUT.stem + f"_shard{si}of{sn}.csv")
    else:
        si = sn = None
        out_path = OUT

    done = set()
    for src in {OUT, out_path}:
        if src.exists():
            for r in csv.DictReader(open(src)):
                done.add((r["lens"], r["mag_label"], r["aperture"]))
    new = not out_path.exists()
    f = out_path.open("a", newline=""); w = csv.DictWriter(f, fieldnames=FIELDS)
    if new:
        w.writeheader(); f.flush()

    items = sorted(combos.items())
    if sn is not None:
        items = [it for k, it in enumerate(items) if k % sn == si]
    if os.environ.get("RANK_LIMIT"):
        items = items[:int(os.environ["RANK_LIMIT"])]

    for ci, ((lens, mag), crows) in enumerate(items, 1):
        aps = {r["aperture"]: Path(r["sample"]).parent for r in crows}
        nominal = float(crows[0]["nominal_M"])
        if all((lens, mag, ap) in done for ap in aps):
            continue
        reg_ap = next((a for a in AP_REG_PREF if a in aps), next(iter(aps)))
        rjpgs = sorted(aps[reg_ap].glob("*.jpg")) or sorted(aps[reg_ap].glob("*.JPG"))
        t0 = time.time()
        try:
            aff = acm.register(rjpgs)
        except Exception as e:
            aff = None
            print(f"[{ci}/{len(items)}] {lens[:42]:42} {mag:8} REG-ERROR {type(e).__name__}", flush=True)
        if aff is None:
            for ap in aps:
                w.writerow(dict.fromkeys(FIELDS, "") | dict(lens=lens, mag_label=mag,
                    nominal_M=f"{nominal:.4f}", aperture=ap, status="reg_failed"))
            f.flush()
            print(f"[{ci}/{len(items)}] {lens[:42]:42} {mag:8} REG-FAILED ({time.time()-t0:.0f}s)", flush=True)
            continue
        M = aff["scale"] / acm.M_ANCHOR_SCALE
        rmse = aff["reg_fit_rmse_px"]; n_int = aff.get("n_refine_intersections", "")
        if not (0.05 < M < 4.0):
            for ap in aps:
                w.writerow(dict.fromkeys(FIELDS, "") | dict(lens=lens, mag_label=mag,
                    nominal_M=f"{nominal:.4f}", atlas_M=f"{M:.4f}", aperture=ap,
                    reg_rmse_px=f"{rmse:.2f}", n_int=n_int, status="degenerate_M"))
            f.flush()
            print(f"[{ci}/{len(items)}] {lens[:42]:42} {mag:8} DEGENERATE M={M:.4f} "
                  f"rmse={rmse:.1f} ({time.time()-t0:.0f}s)", flush=True)
            continue

        # pick pad-edge targets once (geometry only) on a mid-stack frame
        detimg = acm.decode(rjpgs[len(rjpgs) // 2])
        picks = pe.pick_padedge_targets(aff, ATLAS, grid_xy, acm.TARGETS, detimg,
                                        pad_px=25, max_dist_px=pe.MAX_TARGET_DIST_PX) if detimg is not None else {}

        for ap, ap_dir in sorted(aps.items()):
            if (lens, mag, ap) in done:
                continue
            n_marked = n_marked_from_ap(ap)
            n_eff = n_marked * (1.0 + M)
            ceil = optics.diffraction_mtf50_subject_lpmm(n_marked, M)
            ceil_cypx = optics.diffraction_mtf50_sensor_lpmm(n_eff) / acm.LPMM_PER_CYPX
            n_jpgs, lp, cp = measure_aperture(aff, M, ap_dir, picks)
            cor = [lp.get(k) for k in ("TL", "TR", "BL", "BR") if lp.get(k) is not None]
            cmean = float(np.mean(cor)) if cor else None
            cen = lp.get("centre"); cen_c = cp.get("centre")
            unif = (cmean / cen) if (cen and cmean) else None
            def fs(v): return f"{v:.1f}" if isinstance(v, float) else ""
            w.writerow(dict(lens=lens, mag_label=mag, nominal_M=f"{nominal:.4f}",
                atlas_M=f"{M:.4f}", aperture=ap, n_eff=f"{n_eff:.1f}",
                ceiling_lpmm=f"{ceil:.1f}", ceiling_cypx=f"{ceil_cypx:.3f}",
                centre=fs(cen), TL=fs(lp.get("TL")), TR=fs(lp.get("TR")),
                BL=fs(lp.get("BL")), BR=fs(lp.get("BR")), corner_mean=fs(cmean),
                uniformity=(f"{unif:.2f}" if unif else ""),
                centre_cypx=(f"{cen_c:.3f}" if cen_c else ""),
                centre_headroom=(f"{cen_c/ceil_cypx:.2f}" if cen_c else ""),
                n_targets=str(len(lp)), reg_rmse_px=f"{rmse:.2f}", n_int=n_int,
                covered="+".join(sorted(lp)), status="ok"))
            f.flush()
        print(f"[{ci}/{len(items)}] {lens[:42]:42} {mag:8} M={M:.3f} rmse={rmse:.1f} "
              f"picks={sorted(picks)} aps={sorted(aps)} ({time.time()-t0:.0f}s)", flush=True)
    f.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
