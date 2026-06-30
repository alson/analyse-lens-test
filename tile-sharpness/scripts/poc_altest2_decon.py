"""Stage AltEst-2 — P3.2 RELATIVE DECONVOLUTION on same-patch pairs.

For every atlas cell two configs share, both common-grid patches A,B carry the SAME
intrinsic scene S(f). The relative blur between them is well-posed precisely because the
scene is shared (the reference the per-image blind PSF lacked). We estimate, per pair,
the relative blur as a single scalar that CHAINS:

  * relative Gaussian width: the 2D amplitude ratio |FFT(A)|/|FFT(B)| as a function of
    radial sensor frequency is, for two Gaussian PSFs, log|A/B| = -2 pi^2 (sa^2 - sb^2) f^2.
    A weighted-LS line of log-ratio vs f^2 (over the trustworthy band) gives
    delta = sa^2 - sb^2 (px^2). delta>0 => A blurrier than B. This is a WHOLE-SPECTRUM
    relative-kernel fit (distinct from P1's single-frequency amplitude read), so it is a
    genuinely independent estimator that cross-checks P1.
  * We chain delta (= sa^2 - sb^2 additive) directly with a zero-mean gauge -> per-config
    relative blur-variance score (sharper = smaller). Sign is unambiguous (no log-ratio
    floor games); the band is the P1 trustworthy window in cy/px.

Reads the altest2/patches/*.npy + meta. Pure-Python (numpy), single process (cheap once
patches exist); no sharding needed. Reuses nothing mutating.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

OUT = HERE / "poc_comb_chain_out" / "altest2"
PATCH_DIR = OUT / "patches"
SPU = 700.0
# fit band in SENSOR cy/px (mapped per-config to common-grid cy/px via px_per_unit/SPU)
FPX_LO, FPX_HI = 0.06, 0.22


def hann2d(h, w):
    return np.outer(np.hanning(h), np.hanning(w))


def amp_radial(patch, nbins=48):
    """Radial AMPLITUDE (sqrt PSD) of a patch, freq in cy per common-grid px."""
    a = patch.astype(np.float64); a = a - a.mean()
    h, w = a.shape
    a = a * hann2d(h, w)
    F = np.fft.fftshift(np.fft.fft2(a))
    A = np.abs(F)
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    fr = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    bins = np.linspace(0, 0.5, nbins + 1)
    idx = np.digitize(fr.ravel(), bins) - 1
    amp = np.full(nbins, np.nan)
    for b in range(nbins):
        m = idx == b
        if m.any():
            amp[b] = A.ravel()[m].mean()
    fcen = 0.5 * (bins[:-1] + bins[1:])
    return fcen, amp


def main():
    meta = pd.concat([pd.read_csv(f) for f in OUT.glob("meta_shard_*.csv")], ignore_index=True)
    meta = meta.drop_duplicates("config")
    ppu = dict(zip(meta.sid, meta.px_per_unit))
    Mmap = dict(zip(meta.sid, meta.M))

    # index patches by atlas cell
    files = sorted(PATCH_DIR.glob("*__*.npy"))
    by_cell = {}
    amp_cache = {}
    for f in files:
        sid, cell = f.stem.split("__")
        by_cell.setdefault(cell, []).append((sid, f))

    edges = []  # (a, b, delta = sa^2 - sb^2 px^2, w)
    for cell, items in by_cell.items():
        # load + cache radial amplitude per (sid,cell)
        cur = {}
        for sid, f in items:
            key = (sid, cell)
            if key not in amp_cache:
                patch = np.load(f)
                amp_cache[key] = amp_radial(patch)
            cur[sid] = amp_cache[key]
        sids = list(cur)
        for ia in range(len(sids)):
            for ib in range(ia + 1, len(sids)):
                sa, sb = sids[ia], sids[ib]
                fa, Aa = cur[sa]; fb, Ab = cur[sb]
                if sa not in ppu or sb not in ppu:
                    continue
                # convert sensor band -> common-grid cy/px per config
                lo_a, hi_a = FPX_LO * ppu[sa] / SPU, FPX_HI * ppu[sa] / SPU
                lo_b, hi_b = FPX_LO * ppu[sb] / SPU, FPX_HI * ppu[sb] / SPU
                # common SENSOR-freq grid (so the ratio compares matched glass-MTF points)
                fpx = np.linspace(FPX_LO, FPX_HI, 16)
                fga = fpx * ppu[sa] / SPU; fgb = fpx * ppu[sb] / SPU
                if not (fa.min() <= fga.min() and fga.max() <= fa.max()
                        and fb.min() <= fgb.min() and fgb.max() <= fb.max()):
                    continue
                va = np.interp(fga, fa, Aa); vb = np.interp(fgb, fb, Ab)
                m = (va > 0) & (vb > 0)
                if m.sum() < 6:
                    continue
                # log|A/B| = -2 pi^2 (sa^2 - sb^2) f_sensor^2   (f in cy/px)
                lr = np.log(va[m] / vb[m])
                x = fpx[m] ** 2
                # weighted (down-weight high-f where SNR drops) LS slope through origin-ish
                w = 1.0 / (1.0 + 10 * fpx[m] ** 2)
                A1 = np.column_stack([np.ones_like(x), x])
                coef, *_ = np.linalg.lstsq(A1 * w[:, None], lr * w, rcond=None)
                slope = coef[1]
                delta = -slope / (2 * np.pi ** 2)   # sa^2 - sb^2 in px^2
                edges.append((sa, sb, float(delta), float(m.sum())))

    nodes = sorted({e[0] for e in edges} | {e[1] for e in edges})
    if len(nodes) < 2:
        print("no decon edges"); return
    # additive chain (delta = score_a - score_b), zero-mean gauge
    idx = {n: k for k, n in enumerate(nodes)}; n = len(nodes)
    rows, rhs, ws = [], [], []
    for a, b, d, w in edges:
        r = np.zeros(n); r[idx[a]] = 1; r[idx[b]] = -1
        rows.append(r); rhs.append(d); ws.append(w)
    rows.append(np.ones(n)); rhs.append(0.0); ws.append(len(edges))
    A = np.array(rows); bb = np.array(rhs); W = np.sqrt(np.array(ws))
    sol, *_ = np.linalg.lstsq(A * W[:, None], bb * W, rcond=None)
    score = {nd: float(sol[k]) for nd, k in idx.items()}  # relative blur-variance (px^2); smaller=sharper
    resid = np.sqrt(np.mean([(score[a] - score[b] - d) ** 2 for a, b, d, w in edges]))

    df = pd.DataFrame([(s, score[s], Mmap.get(s)) for s in nodes],
                      columns=["sid", "blur_var_px2", "M"]).sort_values("blur_var_px2")
    corr = np.corrcoef(df.M, -df.blur_var_px2)[0, 1]
    print(f"P3.2 relative deconvolution: {len(nodes)} nodes, {len(edges)} edges, "
          f"resid={resid:.3f} px^2")
    print(f"corr(M, sharpness=-blur_var) = {corr:+.3f}  (want ~0)")
    print(df.to_string(index=False))
    bare = df[~df.sid.str.contains(r"\+", regex=True)]
    acc = df[df.sid.str.contains(r"\+", regex=True)]
    if len(bare) and len(acc):
        best_bare = bare.blur_var_px2.min()
        floats = acc[acc.blur_var_px2 < best_bare]
        print(f"empty-mag: best bare blur_var={best_bare:.3f} ({bare.iloc[0].sid}); "
              f"accessory sharper than it: {'NONE (OK)' if not len(floats) else ', '.join(floats.sid)}")
    df.to_csv(OUT / "p32_decon_scores.csv", index=False)
    print("\nwrote p32_decon_scores.csv")


if __name__ == "__main__":
    main()
