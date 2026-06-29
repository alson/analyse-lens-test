"""Find a well-framed SERPENT die at high M by APPEARANCE, not absolute label.
Scan all in-FOV dies across the sharpest frames; score serpent-ness (long
horizontal lines dominate: row periodicity >> col periodicity) and in-FOV frac.
Save the best serpent crops so we can confirm the 2:1 target is framed."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import cv2, numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib_2b as L  # noqa: E402
sys.path.insert(0, str(HERE.parent.parent / "tile-sharpness" / "src"))
from tile_sharpness.methods import periodic_fft as pf  # noqa: E402
OUTDIR = HERE / "diag_2b_serpent_out"; OUTDIR.mkdir(exist_ok=True)


def serpent_score(block):
    h, w = block.shape
    if h < 80 or w < 80:
        return 0.0, 0.0, 0.0
    rp = block[:, int(0.2 * w):int(0.8 * w)].mean(axis=1)
    rp = rp - rp.mean()
    ra = np.abs(np.fft.rfft(rp * np.hanning(len(rp))))
    rf = np.fft.rfftfreq(len(rp), 1.0)
    rb = (rf >= 0.02) & (rf <= 0.25)
    row_per = float(ra[rb].max() / (np.median(ra[rb]) + 1e-6)) if rb.any() else 0
    cp = block[int(0.2 * h):int(0.8 * h), :].mean(axis=0)
    cp = cp - cp.mean()
    ca = np.abs(np.fft.rfft(cp * np.hanning(len(cp))))
    cf = np.fft.rfftfreq(len(cp), 1.0)
    cb = (cf >= 0.02) & (cf <= 0.25)
    col_per = float(ca[cb].max() / (np.median(ca[cb]) + 1e-6)) if cb.any() else 0
    contrast = float(np.percentile(block, 85) - np.percentile(block, 15))
    return row_per, col_per, contrast


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lens", required=True)
    ap.add_argument("--mag", required=True)
    ap.add_argument("--ap", required=True)
    args = ap.parse_args()
    ap_dir = L.RAW / args.lens / args.mag / args.ap
    jpgs = sorted(ap_dir.glob("*.jpg"))
    lv = sorted([(L.central_lapvar(cv2.imread(str(jp), 0)) if cv2.imread(str(jp), 0) is not None else -1, jp)
                 for jp in jpgs], reverse=True)
    cands = [j for _, j in lv[:5]] + [jpgs[int(len(jpgs) * f)] for f in (0.4, 0.6)]
    tag = f"{args.mag}_{args.ap}".replace(" ", "")
    found_any = False
    for jp in dict.fromkeys(cands):
        try:
            aff = L.reg_auto.register_and_refine("d", path=str(jp), anchors=None)
        except Exception as e:
            print(f"{jp.name[:20]}: EXC {e}"); continue
        if aff is None or not aff.get("n_refine_intersections"):
            print(f"{jp.name[:20]}: reg fail/none"); continue
        M = aff["scale"] / L.M_ANCHOR_SCALE
        if not (0.15 < M < 3.5) or aff["reg_fit_rmse_px"] > 8.0:
            print(f"{jp.name[:20]}: M={M:.3f} rmse={aff['reg_fit_rmse_px']:.1f} (rejected)"); continue
        theta = aff.get("theta_deg", 0.0)
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE).astype(np.float32)
        best = None
        for col in range(11):
            for row in range(6):
                bx0, by0, bx1, by1 = L.block_bbox(col, row, aff)
                ix0, iy0 = int(bx0), int(by0); ix1, iy1 = int(bx1), int(by1)
                vx0, vy0 = max(0, ix0), max(0, iy0); vx1, vy1 = min(L.IMAGE_W, ix1), min(L.IMAGE_H, iy1)
                if vx1 - vx0 < 200 or vy1 - vy0 < 200:
                    continue
                infrac = ((vx1 - vx0) * (vy1 - vy0)) / max(1, (ix1 - ix0) * (iy1 - iy0))
                if infrac < 0.6:
                    continue
                der = pf.derotate(g[vy0:vy1, vx0:vx1], theta)
                rp, cp, con = serpent_score(der)
                serp = rp / (cp + 1e-6)
                rec = (serp * con, col, row, infrac, rp, cp, con, der, (col % 4, row % 4))
                if best is None or rec[0] > best[0]:
                    best = rec
        if best:
            sc, col, row, infrac, rp, cp, con, der, typ = best
            lbl = f"{col}{'ABCDEF'[row]}"
            print(f"{jp.name[:20]}: M={M:.3f} rmse={aff['reg_fit_rmse_px']:.2f} -> best serpent die {lbl} "
                  f"type={typ} infrac={infrac:.2f} row_per={rp:.1f} col_per={cp:.1f} con={con:.0f} "
                  f"{'SERPENT' if rp > cp*1.3 and con > 25 else 'NOT-serpent'}")
            if rp > cp * 1.3 and con > 25 and infrac > 0.7:
                cv2.imwrite(str(OUTDIR / f"serp2_{tag}_{lbl}_{jp.name.split('|')[0]}.png"),
                            np.clip(der, 0, 255).astype(np.uint8))
                found_any = True
    print("serpent framed:", found_any)


if __name__ == "__main__":
    main()
