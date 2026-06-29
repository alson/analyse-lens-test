"""Zoom + perpendicular profile of the 2B serpent horizontal lines.

Crops a clean strip of the long horizontal lines (top region of the 2B block),
dumps a big PNG and the column-of-row-means perpendicular profile so we can:
  (a) measure line pitch + line width + gap width in native px,
  (b) test the FLAT / NO-SPECULAR-RIM claim: across each bright line the profile
      should be a symmetric bump with the surrounding dark gaps as a flat floor,
      and across each DARK gap edge the max-adjacent intensity must not exceed
      the line-body level by a rim (no emboss glint).
"""
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path
import cv2, numpy as np

HERE = Path(__file__).resolve().parent
WA = HERE.parent; ROOT = WA.parent
sys.path.insert(0, str(ROOT / "tile-sharpness" / "src"))
from tile_sharpness.methods import periodic_fft as pf  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


reg_auto = _load("reg_auto")
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
IMAGE_W, IMAGE_H = 8256, 5504
M_ANCHOR_SCALE = 1.6549
EXP_BBOX_UV = (0.0, 0.266, 0.999, 0.881)
OUTDIR = HERE / "diag_2b_serpent_out"; OUTDIR.mkdir(exist_ok=True)


def central_lapvar(g):
    c = g[IMAGE_H // 2 - 800:IMAGE_H // 2 + 800, IMAGE_W // 2 - 800:IMAGE_W // 2 + 800]
    return cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var()


def register_best(ap_dir):
    jpgs = sorted(ap_dir.glob("*.jpg"))
    lv = []
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        lv.append((central_lapvar(g) if g is not None else -1, jp))
    lv.sort(reverse=True)
    cand = [j for _, j in lv[:5]] + [jpgs[int(len(jpgs) * f)] for f in (0.35, 0.5, 0.65)]
    best = None
    for jp in dict.fromkeys(cand):
        try:
            p = reg_auto.register_and_refine("d", path=str(jp), anchors=None)
        except Exception:
            continue
        if p is None or not p.get("n_refine_intersections"):
            continue
        r = p["reg_fit_rmse_px"]
        if best is None or r < best[0]:
            best = (r, p, jp)
    return best, jpgs


def block_bbox(col, row, aff):
    u0, v0, u1, v1 = EXP_BBOX_UV
    cor = [reg_auto.grid_xy_distorted(col + u, row + v, aff) for u, v in
           [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
    xs = [c[0] for c in cor]; ys = [c[1] for c in cor]
    return min(xs), min(ys), max(xs), max(ys)


def pad_score(block):
    h, w = block.shape
    if h < 60 or w < 60:
        return 0.0
    ws = max(5, int(0.05 * min(h, w)) | 1)
    blur = cv2.blur(block, (ws, ws)); sq = cv2.blur(block * block, (ws, ws))
    lstd = np.sqrt(np.maximum(sq - blur * blur, 0))
    uni = ((lstd < np.percentile(lstd, 30)) & (block > np.percentile(block, 45))).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, ws // 2) | 1, max(3, ws // 2) | 1))
    uni = cv2.morphologyEx(uni, cv2.MORPH_OPEN, k, 1)
    uni = cv2.morphologyEx(uni, cv2.MORPH_CLOSE, k, 2)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(uni, connectivity=8)
    areas = [stats[i, cv2.CC_STAT_AREA] for i in range(1, n)]
    return (max(areas) / (h * w)) if areas else 0.0


def find_2b(g, aff):
    res = []
    for col in range(11):
        for row in range(6):
            bx0, by0, bx1, by1 = block_bbox(col, row, aff)
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            if not (60 < cx < IMAGE_W - 60 and 60 < cy < IMAGE_H - 60):
                continue
            ix0, iy0 = max(0, int(bx0)), max(0, int(by0))
            ix1, iy1 = min(IMAGE_W, int(bx1)), min(IMAGE_H, int(by1))
            if ix1 - ix0 < 80 or iy1 - iy0 < 80:
                continue
            if ((ix1 - ix0) * (iy1 - iy0)) / max(1, (bx1 - bx0) * (by1 - by0)) < 0.85:
                continue
            res.append((pad_score(g[iy0:iy1, ix0:ix1]), col, row, (ix0, iy0, ix1, iy1)))
    res.sort(reverse=True)
    for sc, col, row, bb in res:
        if (col % 4, row % 4) == (2, 1):
            return col, row, bb
    return (res[0][1], res[0][2], res[0][3]) if res else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lens", default="Nikon AF Micro-Nikkor 200mm f_4D IF-ED")
    ap.add_argument("--mag", default="1_1")
    ap.add_argument("--ap", default="F8")
    args = ap.parse_args()
    tag = f"{args.mag}_{args.ap}".replace(" ", "")
    best, jpgs = register_best(RAW / args.lens / args.mag / args.ap)
    if best is None:
        print("reg FAIL"); return
    rmse, aff, jp = best
    M = aff["scale"] / M_ANCHOR_SCALE
    theta = aff.get("theta_deg", 0.0)
    print(f"{tag}: rmse={rmse:.2f} M={M:.3f} theta={theta:.2f}deg jp={jp.name[:28]}")
    g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE).astype(np.float32)
    found = find_2b(g, aff)
    if not found:
        print("no 2B"); return
    col, row, bb = found
    lbl = f"{col}{'ABCDEF'[row]}"
    ix0, iy0, ix1, iy1 = bb
    crop = g[iy0:iy1, ix0:ix1]
    der = pf.derotate(crop, theta)
    H, W = der.shape
    print(f"2B die {lbl} block size {W}x{H} (de-rotated)")

    # Strip near the TOP of the block (the long lines region), central x to dodge
    # the bond-pad columns at the very edges.
    sx0, sx1 = int(0.18 * W), int(0.78 * W)
    sy0, sy1 = int(0.06 * H), int(0.30 * H)
    strip = der[sy0:sy1, sx0:sx1]
    cv2.imwrite(str(OUTDIR / f"toplines_{tag}_{lbl}.png"), np.clip(strip, 0, 255).astype(np.uint8))
    cv2.imwrite(str(OUTDIR / f"block_derot_{tag}_{lbl}.png"), np.clip(der, 0, 255).astype(np.uint8))

    # Perpendicular profile = mean over columns (lines are horizontal -> vary in y)
    prof = strip.mean(axis=1)
    print(f"\nTOP-LINES strip {strip.shape} x=[{sx0},{sx1}] y=[{sy0},{sy1}] (rel to block)")
    print("row-mean profile (y idx : value):")
    s = "  ".join(f"{i}:{int(v)}" for i, v in enumerate(prof))
    print(s)
    # FFT the profile to get the line pitch
    p = prof - prof.mean()
    amp = np.abs(np.fft.rfft(p * np.hanning(len(p))))
    fr = np.fft.rfftfreq(len(p), 1.0)
    band = (fr >= 0.02) & (fr <= 0.45)
    k = np.where(band)[0][np.argmax(amp[band])]
    print(f"\nline pitch (FFT): {1/fr[k]:.1f}px  f0={fr[k]:.3f}cy/px  -> subject f0*M={fr[k]*M:.3f}, lp/mm={fr[k]*M*229.9:.1f}")
    # peak/trough analysis: bright lines vs dark gaps; line width via FWHM-ish
    from scipy.signal import find_peaks
    pk, _ = find_peaks(prof, distance=max(3, int(0.6 / max(fr[k], 1e-6))))
    tr, _ = find_peaks(-prof, distance=max(3, int(0.6 / max(fr[k], 1e-6))))
    print(f"bright-line centres (y idx): {list(pk)}")
    print(f"dark-gap centres   (y idx): {list(tr)}")
    if len(pk) >= 2:
        print(f"mean line-to-line pitch: {np.mean(np.diff(pk)):.1f}px")
    # rim test: for each bright line, is there a dark dip on BOTH sides that is
    # symmetric, and does the inter-line max ever exceed the line peak (a rim)?
    if len(pk) >= 3 and len(tr) >= 2:
        bright = float(np.median(prof[pk]))
        dark = float(np.median(prof[tr]))
        print(f"bright-line median={bright:.0f}  dark-gap median={dark:.0f}  contrast(DN)={bright-dark:.0f}")
        # check no point between two adjacent troughs exceeds bright+rim
        rim_flags = []
        for a, b in zip(tr[:-1], tr[1:]):
            seg = prof[a:b + 1]
            rim_flags.append(float(seg.max()) > bright + 0.10 * (bright - dark))
        print(f"segments with a >10% rim above bright median: {sum(rim_flags)}/{len(rim_flags)}")


if __name__ == "__main__":
    main()
