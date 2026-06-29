"""Task D: atlas-anchored centre+4-corner subject-MTF50 ranking for every native
accessory config (the method validated 2026-06-27 in atlas_corner_mtf.py, which
closed the high-M coverage gap the blind per-tile pipeline leaves).

Per (lens, mag_label) combo we register ONCE on a clean stack (prefer F8) via
reg_auto and reuse that affine across the combo's apertures (framing is fixed
within a capture session; only the focus rail moves). Per aperture we read MTF50
at each of 5 field positions (centre + 4 corners) at THAT position's own
best-focus shot (field-tilt-aware). Subject lp/mm uses the atlas-measured M; the
diffraction ceiling (optics.py) flags glass- vs diffraction-limited positions.

CAVEAT (carried from the 2026-06-27 work): scribe-LSF MTF50 over-reads above the
ceiling on low-contrast/diffraction-blurred edges. Trust values comfortably BELOW
the ceiling (glass-limited: corners, wider apertures); for diffraction-limited
positions read the ceiling, not the measured value. Per-position scribe noise
~±5 lp/mm. Output is RELATIVE across configs (shared systematic).
"""
from __future__ import annotations
import csv, importlib.util, os, sys, time
from pathlib import Path
import numpy as np

TS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TS / "src"))
from tile_sharpness import optics
from tile_sharpness.methods.lsf import cross_section, lsf_mtf50

# reuse the validated atlas_corner_mtf machinery
_spec = importlib.util.spec_from_file_location("acm", TS / "scripts" / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(acm)

# IN/OUT overridable via env so the same driver ranks accessory OR bare configs.
IN = Path(os.environ.get("RANK_CONFIGS",
    str(Path(__file__).resolve().parent.parent.parent / "wafer-atlas/scripts/accessory_configs.csv")))
OUT = Path(os.environ.get("RANK_OUT",
    str(Path(__file__).resolve().parent.parent / "out_accessory_atlas/accessory_ranking.csv")))
PIPELINE_DATES = {"2026-01-29", "2026-02-18"}
APS = {"F8", "F8.0", "F11", "F11.0"}
AP_REG_PREF = ["F8", "F8.0", "F11", "F11.0"]
FIELDS = ["lens", "mag_label", "nominal_M", "atlas_M", "aperture", "n_marked",
          "n_eff", "ceiling_lpmm", "centre", "TL", "TR", "BL", "BR",
          "corner_mean", "uniformity", "centre_headroom", "reg_rmse_px",
          "n_int", "covered", "status"]


def n_marked_from_ap(ap: str) -> float:
    return float(ap.lstrip("Ff_").replace("_", "."))


def measure_aperture(aff, M, ap_dir):
    """5-position MTF50 (subject lp/mm) using a fixed affine on ap_dir's stack."""
    jpgs = sorted(ap_dir.glob("*.jpg")) or sorted(ap_dir.glob("*.JPG"))
    if not jpgs:
        return None, {}
    scribes = acm.pick_scribes(aff)
    best = {name: (-1.0, None) for name in scribes}
    for jp in jpgs:
        g = acm.decode(jp)
        if g is None:
            continue
        for name, (mx, my, seg) in scribes.items():
            lv = acm.roi_lapvar(g, mx, my)
            if lv > best[name][0]:
                prof = cross_section(g.astype(np.float32), seg,
                                     half_window_px=acm.HALF_WIN, samples_per_pixel=acm.SPP)
                best[name] = (lv, lsf_mtf50(prof, combine="min"))
    out = {}
    for name in scribes:
        m = best[name][1]
        out[name] = (m * acm.LPMM_PER_CYPX * M) if m else None
    return len(jpgs), out


def main():
    rows = [r for r in csv.DictReader(open(IN))
            if r["date"] in PIPELINE_DATES and r["aperture"] in APS]
    combos = {}
    for r in rows:
        combos.setdefault((r["lens"], r["mag_label"]), []).append(r)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Shard mode (SHARD="i/N"): worker i handles combos with index%N==i and writes
    # its own CSV; combos already in the MAIN csv are skipped. Merge shards after.
    shard = os.environ.get("SHARD")
    if shard:
        si, sn = (int(x) for x in shard.split("/"))
        out_path = OUT.with_name(OUT.stem + f"_shard{si}of{sn}.csv")
    else:
        si = sn = None
        out_path = OUT

    done = set()
    for src in {OUT, out_path}:                 # main csv + this shard's own csv
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
        # register once on the preferred aperture stack
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
        if not (0.05 < M < 4.0):   # scale-collapse / absurd fit -> don't trust
            for ap in aps:
                w.writerow(dict.fromkeys(FIELDS, "") | dict(lens=lens, mag_label=mag,
                    nominal_M=f"{nominal:.4f}", atlas_M=f"{M:.4f}", aperture=ap,
                    reg_rmse_px=f"{rmse:.2f}", n_int=n_int, status="degenerate_M"))
            f.flush()
            print(f"[{ci}/{len(items)}] {lens[:42]:42} {mag:8} DEGENERATE M={M:.4f} "
                  f"rmse={rmse:.1f} ({time.time()-t0:.0f}s)", flush=True)
            continue
        for ap, ap_dir in sorted(aps.items()):
            if (lens, mag, ap) in done:
                continue
            n_marked = n_marked_from_ap(ap)
            n_eff = n_marked * (1.0 + M)
            ceil = optics.diffraction_mtf50_subject_lpmm(n_marked, M)
            n_jpgs, lp = measure_aperture(aff, M, ap_dir)
            cor = [lp.get(k) for k in ("TL", "TR", "BL", "BR") if lp.get(k) is not None]
            cmean = float(np.mean(cor)) if cor else None
            cen = lp.get("centre")
            unif = (cmean / cen) if (cen and cmean) else None
            def fs(v): return f"{v:.1f}" if isinstance(v, float) else ""
            w.writerow(dict(lens=lens, mag_label=mag, nominal_M=f"{nominal:.4f}",
                atlas_M=f"{M:.4f}", aperture=ap, n_marked=f"{n_marked:.1f}",
                n_eff=f"{n_eff:.1f}", ceiling_lpmm=f"{ceil:.1f}",
                centre=fs(cen), TL=fs(lp.get("TL")), TR=fs(lp.get("TR")),
                BL=fs(lp.get("BL")), BR=fs(lp.get("BR")), corner_mean=fs(cmean),
                uniformity=(f"{unif:.2f}" if unif else ""),
                centre_headroom=(f"{cen/ceil:.2f}" if cen else ""),
                reg_rmse_px=f"{rmse:.2f}", n_int=n_int,
                covered="+".join(sorted(lp)), status="ok"))
            f.flush()
        print(f"[{ci}/{len(items)}] {lens[:42]:42} {mag:8} M={M:.3f} rmse={rmse:.1f} "
              f"aps={sorted(aps)} ({time.time()-t0:.0f}s)", flush=True)
    f.close()
    print("DONE")


if __name__ == "__main__":
    main()
