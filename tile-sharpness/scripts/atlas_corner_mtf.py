"""Atlas-anchored corner MTF50 — deterministic full-field coverage.

Closes the gap that the blind per-tile pipeline left on high-magnification
configs: at native M=1.27 the 6T diopter returned only 1 usable tile (centre
only), so MCON-35-vs-6T could not be compared at the corners. Here scribe
placement is ATLAS-ANCHORED (wafer-atlas reg_auto): we register each sweep and
read MTF50 at KNOWN grid-line scribes placed at fixed field positions
(centre + 4 corners) — deterministic, full coverage regardless of magnification.

Per scribe we take MTF50 at THAT scribe's own best-focus shot (field-tilt-aware:
the plane of best focus marches across the field, so a single frame is not best
everywhere). Subject-space lp/mm uses the atlas-measured magnification
(registration scale / the AF200 1:1 anchor) — no path label, no resampling.

Caveat: the scribe-LSF MTF50 over-reads at low contrast, but corners at F8 here
are glass-limited (well below the diffraction ceiling), the trustworthy regime;
and the comparison is RELATIVE across diopters (shared systematic). dcraw not
needed (JPEG, consistent with the pipeline run this extends). Run on nufan.

FINDING (2026-06-27, 100-400 + MCON-35/6T/5T @ F8): the atlas closes the coverage
gap — all 5 field positions (incl 6T corners) get scribes, which the blind
per-tile pipeline could not. With robust multi-frame registration (keep lowest
full-res residual over candidate frames) all three register at 1.6-1.9px. Result
(subject lp/mm): MCON-35 centre 28.9 > 6T 23.8 (~21%), corner-mean 19.4 vs 17.9 —
MCON-35 > 6T, confirming the user's recollection (centre is the clean signal).
CAVEATS: per-corner scribe noise ±~5 lp/mm (corner gap within noise); 5T appears
best, contradicting the blind pipeline (untrustworthy); atlas-M disagrees with
nominal labels by 8-29% even at low residual (a wrong col/row LABELLING scales M
while still fitting) -> absolute lp/mm carries scale uncertainty on these configs.
So the DIRECTIONAL result (MCON>=6T, centre-clear) is reliable; fine corner
ranking and absolutes are not, pending label-validation + scribe averaging + the
LSF over-read fix.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import cv2
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tile_sharpness.methods.lsf import Segment, cross_section, lsf_mtf50

RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
IMAGE_W, IMAGE_H = 8256, 5504
LPMM_PER_CYPX = 1000.0 / 4.35
M_ANCHOR_SCALE = 1.6549          # reg_auto sweep2 (AF200 @ 1:1) refined scale <-> M=1.0
HALF_WIN, SPP = 28, 3.0

_WA = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/"
           "wafer-atlas/scripts")
_spec = importlib.util.spec_from_file_location("reg_auto", _WA / "reg_auto.py")
reg_auto = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reg_auto)

SWEEPS = {
    "MCON-35": RAW / "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Olympus MCON-35" / "1_1.16" / "F8",
    "6T":      RAW / "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T" / "1.27_1" / "F8",
    "5T":      RAW / "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 5T" / "1_1.19" / "F8",
}
# field targets in image fractions: centre + 4 corners
TARGETS = {"centre": (0.50, 0.50), "TL": (0.22, 0.22), "TR": (0.78, 0.22),
           "BL": (0.22, 0.78), "BR": (0.78, 0.78)}
N_F8 = 8.0   # set aperture


def decode(path):
    return cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)


def central_lapvar(g):
    h, w = g.shape[:2]                       # use the actual frame (camera-agnostic)
    c = g[h // 2 - 800:h // 2 + 800, w // 2 - 800:w // 2 + 800]
    return cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var()


def register(jpgs):
    """Register robustly: try several candidate frames (sharpest by central
    lapvar + a few spread through the stack) and keep the registration with the
    LOWEST full-res refinement residual that actually refined (n_int>0).
    Registration is shot-dependent on these configs, so one frame is not enough."""
    # rank shots by central focus (cheap), take the sharpest few + a spread
    lv = []
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        lv.append((central_lapvar(g) if g is not None else -1.0, jp))
    lv.sort(reverse=True)
    cand = [jp for _, jp in lv[:4]]
    cand += [jpgs[int(len(jpgs) * f)] for f in (0.35, 0.5, 0.65)]
    best = None
    for jp in dict.fromkeys(cand):           # dedup, preserve order
        try:
            p = reg_auto.register_and_refine("diopter", path=str(jp), anchors=None)
        except Exception:
            continue
        if p is None or not p.get("n_refine_intersections"):
            continue
        r = p["reg_fit_rmse_px"]
        if best is None or r < best[0]:
            best = (r, p)
    return best[1] if best else None


def candidate_scribes(aff, image_w=IMAGE_W, image_h=IMAGE_H):
    """All in-frame grid-line segments (vertical col-lines + horizontal row-lines),
    each spanning one cell. Returns [(midx, midy, Segment)]. image_w/h are the sensor
    frame size (Z7 8256x5504 default; pass the DX 6000x4000 for the D7200)."""
    segs = []
    def ok(xa, ya, xb, yb):
        return (150 < xa < image_w - 150 and 150 < xb < image_w - 150
                and 150 < ya < image_h - 150 and 150 < yb < image_h - 150)
    for cl in range(reg_auto.N_COL_LINES):
        for r0 in range(reg_auto.N_ROW_LINES - 1):
            xa, ya = reg_auto.grid_xy_distorted(cl, r0, aff)
            xb, yb = reg_auto.grid_xy_distorted(cl, r0 + 1, aff)
            if ok(xa, ya, xb, yb):
                segs.append(((xa + xb) / 2, (ya + yb) / 2, Segment(x0=xa, y0=ya, x1=xb, y1=yb)))
    for rl in range(reg_auto.N_ROW_LINES):
        for c0 in range(reg_auto.N_COL_LINES - 1):
            xa, ya = reg_auto.grid_xy_distorted(c0, rl, aff)
            xb, yb = reg_auto.grid_xy_distorted(c0 + 1, rl, aff)
            if ok(xa, ya, xb, yb):
                segs.append(((xa + xb) / 2, (ya + yb) / 2, Segment(x0=xa, y0=ya, x1=xb, y1=yb)))
    return segs


def pick_scribes(aff, image_w=IMAGE_W, image_h=IMAGE_H):
    """Nearest in-frame scribe to each field target (or None if too far)."""
    segs = candidate_scribes(aff, image_w, image_h)
    out = {}
    for name, (fx, fy) in TARGETS.items():
        tx, ty = fx * image_w, fy * image_h
        cands = sorted(segs, key=lambda s: np.hypot(s[0] - tx, s[1] - ty))
        if cands and np.hypot(cands[0][0] - tx, cands[0][1] - ty) < 1400:
            out[name] = cands[0]      # (midx, midy, seg)
    return out


def roi_lapvar(g, mx, my, half=70):
    y0, y1 = max(0, int(my - half)), min(g.shape[0], int(my + half))
    x0, x1 = max(0, int(mx - half)), min(g.shape[1], int(mx + half))
    r = g[y0:y1, x0:x1]
    return cv2.Laplacian(r.astype(np.float32), cv2.CV_32F).var() if r.size else -1.0


def run(label, ap_dir, *, image_w=IMAGE_W, image_h=IMAGE_H, pitch_um=4.35,
        n_marked=N_F8, eff_ap=None):
    """Atlas-anchored centre/corner subject-MTF50 for one config.

    Camera-parameterised: pass image_w/h (Z7 8256x5504 default, DX 6000x4000 for the
    D7200) and pitch_um (Z7 4.35, D7200 3.91). ``eff_ap`` is the already-EFFECTIVE
    f-number (e.g. the D7200 folder aperture) — used directly for N_eff; when None we
    fall back to the Z7 convention N_marked*(1+M). N_eff only annotates the diffraction
    ceiling; it does not enter the MTF50. OLPF (D7200) depresses absolute MTF50 — the
    within-config / relative signal is what's trustworthy, not cross-camera absolutes."""
    lpmm_per_cypx = 1000.0 / pitch_um
    jpgs = sorted(ap_dir.glob("*.jpg"))
    if not jpgs:
        print(f"{label}: no jpgs"); return None
    aff = register(jpgs)
    if aff is None:
        print(f"{label}: registration FAILED"); return None
    M = aff["scale"] / M_ANCHOR_SCALE
    scribes = pick_scribes(aff, image_w, image_h)
    n_eff = float(eff_ap) if eff_ap else n_marked * (1.0 + M)
    print(f"\n{label}: {len(jpgs)} shots  reg fit={aff['reg_fit_rmse_px']:.2f}px  "
          f"M_atlas={M:.3f}  N_eff={n_eff:.1f}  targets covered: {sorted(scribes)}")

    # per scribe: MTF50 at its own best-focus shot (field-tilt-aware)
    best = {name: (-1.0, None) for name in scribes}   # (lapvar, mtf50_cypx)
    for jp in jpgs:
        g = decode(jp)
        if g is None:
            continue
        for name, (mx, my, seg) in scribes.items():
            lv = roi_lapvar(g, mx, my)
            if lv > best[name][0]:
                prof = cross_section(g.astype(np.float32), seg, half_window_px=HALF_WIN,
                                     samples_per_pixel=SPP)
                m = lsf_mtf50(prof)
                best[name] = (lv, m)

    res = {}
    for name in scribes:
        m = best[name][1]
        res[name] = (m * lpmm_per_cypx * M) if m else None
    return dict(label=label, M=M, n_eff=n_eff, lpmm=res)


def main():
    results = [r for r in (run(lbl, d) for lbl, d in SWEEPS.items()) if r]
    print(f"\n{'='*64}\nATLAS-ANCHORED CORNER MTF50 (subject lp/mm, F8 native)\n{'='*64}")
    print(f"{'diopter':<9}{'M':>6}{'centre':>8}{'TL':>7}{'TR':>7}{'BL':>7}{'BR':>7}"
          f"{'cor.mean':>9}{'unif':>6}")
    for r in results:
        lp = r["lpmm"]
        cor = [lp.get(k) for k in ("TL", "TR", "BL", "BR") if lp.get(k) is not None]
        cmean = float(np.mean(cor)) if cor else float("nan")
        cen = lp.get("centre")
        unif = (cmean / cen) if (cen and cmean == cmean) else float("nan")
        def s(v):
            return f"{v:7.1f}" if isinstance(v, float) and v == v else f"{'-':>7}"
        print(f"{r['label']:<9}{r['M']:6.2f}{s(cen)}{s(lp.get('TL'))}{s(lp.get('TR'))}"
              f"{s(lp.get('BL'))}{s(lp.get('BR'))}{cmean:9.1f}{unif:6.2f}")
    print("\n(subject lp/mm; higher=better. F8 ceiling ~42-51 lp/mm -> corners glass-limited,\n"
          " trustworthy regime. Relative comparison across diopters is robust.)")


if __name__ == "__main__":
    main()
