"""Where is the (2,1) serpent die at high M? For a config, register the sharpest
frames and report every in-FOV (col%4,row%4)==(2,1) die's block bbox + a
'serpent-ness' score (fraction of the block dominated by long horizontal-line
periodicity vs pad-array speckle), and save crops. Tells us if a clean serpent
block is ever fully framed at 2:1."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import cv2, numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib_2b as L  # noqa: E402

OUTDIR = HERE / "diag_2b_serpent_out"; OUTDIR.mkdir(exist_ok=True)


def serpent_score(block):
    """High if the block is dominated by long HORIZONTAL lines (row-mean has strong
    periodic modulation AND lines span much of the width), low for pad-array speckle
    (which has strong modulation in BOTH axes / 2D grid)."""
    h, w = block.shape
    if h < 80 or w < 80:
        return 0.0, 0.0
    # horizontal-line strength: row-mean profile periodic energy in 0.02..0.2 cy/px
    rp = block[:, int(0.2 * w):int(0.8 * w)].mean(axis=1)
    rp = rp - rp.mean()
    ra = np.abs(np.fft.rfft(rp * np.hanning(len(rp))))
    rf = np.fft.rfftfreq(len(rp), 1.0)
    rb = (rf >= 0.02) & (rf <= 0.25)
    row_per = float(ra[rb].max() / (np.median(ra[rb]) + 1e-6))
    # column-mean periodic energy (pad arrays modulate columns too; pure lines don't)
    cp = block[int(0.2 * h):int(0.8 * h), :].mean(axis=0)
    cp = cp - cp.mean()
    ca = np.abs(np.fft.rfft(cp * np.hanning(len(cp))))
    cf = np.fft.rfftfreq(len(cp), 1.0)
    cb = (cf >= 0.02) & (cf <= 0.25)
    col_per = float(ca[cb].max() / (np.median(ca[cb]) + 1e-6))
    return row_per, col_per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lens", required=True)
    ap.add_argument("--mag", required=True)
    ap.add_argument("--ap", required=True)
    args = ap.parse_args()
    ap_dir = L.RAW / args.lens / args.mag / args.ap
    jpgs = sorted(ap_dir.glob("*.jpg"))
    # rank frames by central focus, take several
    lv = []
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        lv.append((L.central_lapvar(g) if g is not None else -1, jp))
    lv.sort(reverse=True)
    cands = [j for _, j in lv[:6]] + [jpgs[int(len(jpgs) * f)] for f in (0.3, 0.5, 0.7)]
    seen = set()
    tag = f"{args.mag}_{args.ap}".replace(" ", "")
    for jp in dict.fromkeys(cands):
        try:
            aff = L.reg_auto.register_and_refine("d", path=str(jp), anchors=None)
        except Exception:
            continue
        if aff is None or not aff.get("n_refine_intersections"):
            continue
        M = aff["scale"] / L.M_ANCHOR_SCALE
        if not (0.15 < M < 3.5) or aff["reg_fit_rmse_px"] > 8.0:
            continue
        theta = aff.get("theta_deg", 0.0)
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE).astype(np.float32)
        from tile_sharpness.methods import periodic_fft as pf
        print(f"\nframe {jp.name[:24]} rmse={aff['reg_fit_rmse_px']:.2f} M={M:.3f} col_first={aff.get('reg_col_first')} row_first={aff.get('reg_row_first')}")
        for col in range(11):
            for row in range(6):
                if (col % 4, row % 4) != (2, 1):
                    continue
                bx0, by0, bx1, by1 = L.block_bbox(col, row, aff)
                ix0, iy0 = int(bx0), int(by0); ix1, iy1 = int(bx1), int(by1)
                # in-FOV fraction
                vx0, vy0 = max(0, ix0), max(0, iy0)
                vx1, vy1 = min(L.IMAGE_W, ix1), min(L.IMAGE_H, iy1)
                if vx1 - vx0 < 80 or vy1 - vy0 < 80:
                    continue
                infrac = ((vx1 - vx0) * (vy1 - vy0)) / max(1, (ix1 - ix0) * (iy1 - iy0))
                crop = g[vy0:vy1, vx0:vx1]
                der = pf.derotate(crop, theta)
                rp, cp = serpent_score(der)
                lbl = f"{col}{'ABCDEF'[row]}"
                print(f"  die {lbl} infrac={infrac:.2f} size={vx1-vx0}x{vy1-vy0} "
                      f"row_per={rp:.1f} col_per={cp:.1f} {'<- serpent-like' if rp>cp*1.3 else ''}")
                key = (lbl, round(infrac, 1))
                if infrac > 0.6 and key not in seen:
                    seen.add(key)
                    cv2.imwrite(str(OUTDIR / f"cov_{tag}_{lbl}_{jp.name.split('|')[0]}.png"),
                                np.clip(der, 0, 255).astype(np.uint8))


if __name__ == "__main__":
    main()
