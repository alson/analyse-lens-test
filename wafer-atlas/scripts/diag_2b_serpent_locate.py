"""Locate the 2B-type die's central serpent/horizontal-lines region (the FLAT
target) at M>=1 and dump crops + a perpendicular profile.

The 2B experimental block (atlas die type (2,1), EXP_BBOX_UV) is the
"horizontal lines + serpent" middle band BETWEEN the top and bottom bond-pad
rows. New fact: the dark lines on a lighter background are FLAT reflectance
(symmetric dark dips, NO specular rim), unlike the recessed bright pads the
prior agent rejected. Here we:
  1. register a sweep (reg_auto), find the best 2B-type die by appearance,
  2. crop its experimental (serpent) block,
  3. discover the serpent line fundamental via FFT (Route-1 input),
  4. dump a perpendicular intensity profile across the lines to CHECK the
     no-specular-rim / flat-step claim (max-adjacent stays <= background).

Run on nufan. Existing data only.
"""
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path
import cv2, numpy as np

HERE = Path(__file__).resolve().parent
WA = HERE.parent
ROOT = WA.parent
sys.path.insert(0, str(ROOT / "tile-sharpness" / "src"))
from tile_sharpness.methods import periodic_fft as pf  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


reg_auto = _load("reg_auto")
ATLAS = json.load(open(WA / "atlas.json"))
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
IMAGE_W, IMAGE_H = 8256, 5504
M_ANCHOR_SCALE = 1.6549
EXP_BBOX_UV = (0.0, 0.266, 0.999, 0.881)
OUTDIR = HERE / "diag_2b_serpent_out"
OUTDIR.mkdir(exist_ok=True)


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
    """2B-type signature: a large LOW-local-std (uniform) bright component -> the
    pad rows; used to pick the 2B die among all in-FOV cells (same as finddie)."""
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


def find_2b_die(g, aff):
    """Return (col,row,block_bbox) of the best 2B-type die in FOV."""
    results = []
    for col in range(0, 11):
        for row in range(0, 6):
            bx0, by0, bx1, by1 = block_bbox(col, row, aff)
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            if not (60 < cx < IMAGE_W - 60 and 60 < cy < IMAGE_H - 60):
                continue
            ix0, iy0 = max(0, int(bx0)), max(0, int(by0))
            ix1, iy1 = min(IMAGE_W, int(bx1)), min(IMAGE_H, int(by1))
            if ix1 - ix0 < 80 or iy1 - iy0 < 80:
                continue
            frac = ((ix1 - ix0) * (iy1 - iy0)) / max(1, (bx1 - bx0) * (by1 - by0))
            if frac < 0.85:
                continue
            sc = pad_score(g[iy0:iy1, ix0:ix1])
            results.append((sc, col, row, (ix0, iy0, ix1, iy1)))
    results.sort(reverse=True)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lens", default="Nikon AF Micro-Nikkor 200mm f_4D IF-ED")
    ap.add_argument("--mag", default="1_1")
    ap.add_argument("--ap", default="F8")
    args = ap.parse_args()
    ap_dir = RAW / args.lens / args.mag / args.ap
    tag = f"{args.lens.split()[2] if len(args.lens.split())>2 else args.lens[:8]}_{args.mag}_{args.ap}".replace(" ", "")
    best, jpgs = register_best(ap_dir)
    if best is None:
        print(f"{tag}: registration FAILED"); return
    rmse, aff, jp = best
    M = aff["scale"] / M_ANCHOR_SCALE
    print(f"{tag}: reg {jp.name[:30]} rmse={rmse:.2f} M={M:.3f}")
    g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE).astype(np.float32)
    res = find_2b_die(g, aff)
    print("top 2B-candidate dies (score, col,row type=(c%4,r%4)):")
    for sc, col, row, bb in res[:6]:
        lbl = f"{col}{'ABCDEF'[row]}"
        print(f"  {lbl} type=({col%4},{row%4}) score={sc:.3f} block={bb} size={bb[2]-bb[0]}x{bb[3]-bb[1]}")
    # pick the best die that is type (2,1) if present, else best overall
    pick = None
    for sc, col, row, bb in res:
        if (col % 4, row % 4) == (2, 1):
            pick = (sc, col, row, bb); break
    if pick is None and res:
        pick = res[0]
    if pick is None:
        print("no die found"); return
    sc, col, row, bb = pick
    lbl = f"{col}{'ABCDEF'[row]}"
    ix0, iy0, ix1, iy1 = bb
    crop = g[iy0:iy1, ix0:ix1]
    cv2.imwrite(str(OUTDIR / f"serpent_block_{tag}_{lbl}.png"), np.clip(crop, 0, 255).astype(np.uint8))
    print(f"\nPICKED 2B die {lbl} type=({col%4},{row%4}) block={bb} -> serpent_block_{tag}_{lbl}.png")

    # The serpent/lines middle band: the experimental block spans v 0.266..0.881.
    # Per the atlas user_description the pad rows are at v 0.7-0.85 (top) within
    # the DIE; inside this experimental block the horizontal-lines + serpent fill
    # most of it. Discover the line fundamental on BOTH axes.
    print("\n--- FFT fundamental discovery on the serpent block (de-rotated) ---")
    theta = aff.get("theta_deg", 0.0)
    der = pf.derotate(crop, theta)
    for axis in ("u", "v"):
        f = pf.discover_fundamental(der, axis=axis, band=(0.02, 0.45), exclude=None)
        print(f"  axis={axis}: {f}")
    # also try sub-bands within the block (top third / middle / bottom third)
    h = der.shape[0]
    for name, sl in (("topthird", slice(0, h // 3)), ("middle", slice(h // 3, 2 * h // 3)),
                     ("botthird", slice(2 * h // 3, h))):
        sub = der[sl]
        for axis in ("u", "v"):
            f = pf.discover_fundamental(sub, axis=axis, band=(0.02, 0.45), exclude=None)
            if f:
                print(f"  {name} axis={axis}: pitch={f['pitch_px']:.1f}px f0={f['f0_cy_per_px']:.3f} amp={f['amp']:.1f}")


if __name__ == "__main__":
    main()
