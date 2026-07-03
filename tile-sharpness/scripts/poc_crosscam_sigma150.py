#!/usr/bin/env python3
"""POC: same-physical-patch CROSS-CAMERA PSD ratio for the Sigma 150 (Z7 vs D7200).

Goal: empirically measure the D7200 sensor+OLPF MTF penalty relative to the Z7 by
ratioing the two cameras' per-patch PSD for the SAME wafer patch, SAME lens, SAME
effective aperture, at ~same M. Optics (lens x diffraction) and the target's own
spectrum are identical across cameras at a matched SUBJECT frequency (both patches
are resampled to the same atlas grid -> shared `f_grid`), so:

    sqrt( PSD_D7200(patch,f) / PSD_Z7(patch,f) )
        ~=  [MTF_sensor+OLPF,D7200 / MTF_sensor,Z7](f)  x  exposure_factor

LEAD CAVEATS (see report): first-order only; ~6% M-offset (1.03 Z7 vs 1.09 D7200) is
NOT eliminated (D7200 gone, no re-shoot) -> small residual diffraction + cy/px-shift
term; exposure normalised out via the low-frequency ratio; the resampled grid (700
samples/atlas-unit) band-limits the PSD to ~0.27-0.29 cy/px, BELOW sensor Nyquist
(0.5), so the OLPF's strongest near-Nyquist attenuation is OUT OF BAND; OLPF is
orientation-dependent; one lens only.
"""
import glob
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPU = 700.0
Z7 = dict(dir=os.path.join(ROOT, "out_relmtf_311"), pitch=4.35, sid_re=r"^S150__F.*@260513$")
D72 = dict(dir=os.path.join(ROOT, "out_relmtf_d7200"), pitch=3.91, sid_re=r"^S150__F.*@250819$")
APS = ["F5.6", "F8", "F11", "F16"]


def _read_all(pattern):
    frames = []
    for f in glob.glob(pattern):
        try:
            frames.append(pd.read_csv(f))
        except pd.errors.EmptyDataError:
            continue
    return pd.concat(frames, ignore_index=True)


def load(camera):
    psd = _read_all(os.path.join(camera["dir"], "psd_shard_*.csv"))
    meta = _read_all(os.path.join(camera["dir"], "meta_shard_*.csv"))
    psd = psd[psd.sid.str.match(camera["sid_re"])].copy()
    meta = meta[meta.sid.str.match(camera["sid_re"])].copy()
    return psd, meta


def ap_of(sid):
    return sid.split("__")[1].split("@")[0]


def per_patch_curves(psd, ap):
    """{patch: (f_grid[], psd[])} for the given aperture, sorted by f_grid."""
    sub = psd[psd.sid.map(ap_of) == ap]
    out = {}
    for patch, g in sub.groupby("patch"):
        g = g.sort_values("f_grid")
        out[patch] = (g.f_grid.to_numpy(), g.psd.to_numpy())
    return out


def main():
    zp, zm = load(Z7)
    dp, dm = load(D72)
    ppu_z = {ap_of(s): v for s, v in zip(zm.sid, zm.px_per_unit)}
    ppu_d = {ap_of(s): v for s, v in zip(dm.sid, dm.px_per_unit)}

    print("=== Sigma 150 cross-camera PSD ratio (D7200 / Z7) ===")
    print(f"{'ap':>5} {'shared':>6} {'expo_ratio(lowf)':>16} {'expo_CV':>7} "
          f"{'ratio@0.10cy/px':>15} {'ratio@0.20cy/px':>15} {'ratio@bandmax':>13}")
    pooled = {}  # f_grid -> list of normalised MTF ratios across all aps/patches
    for ap in APS:
        zc = per_patch_curves(zp, ap)
        dc = per_patch_curves(dp, ap)
        shared = sorted(set(zc) & set(dc))
        if not shared:
            print(f"{ap:>5}  (no shared patches)")
            continue
        # common f_grid across all shared patches (both cameras share the same grid)
        fg = zc[shared[0]][0]
        lowmask = (fg >= 0.015) & (fg <= 0.05)   # low-freq band for exposure normalisation
        expo, norm_curves = [], []
        for p in shared:
            fz, pz = zc[p]
            fd, pdd = dc[p]
            if len(fz) != len(fg) or len(fd) != len(fg):
                continue
            with np.errstate(divide="ignore", invalid="ignore"):
                r = np.sqrt(pdd / pz)              # per-patch MTF ratio (incl. exposure)
            if not np.isfinite(r[lowmask]).any():
                continue
            e = np.nanmedian(r[lowmask])           # per-patch exposure factor
            if not np.isfinite(e) or e <= 0:
                continue
            expo.append(e)
            norm_curves.append(r / e)              # exposure-removed -> sensor-MTF shape
        expo = np.array(expo)
        norm = np.nanmedian(np.vstack(norm_curves), axis=0)
        for f, v in zip(fg, norm):
            pooled.setdefault(round(float(f), 6), []).append(v)
        # sensor cy/px axis for D7200 (the OLPF-bearing sensor)
        cyx_d = fg * SPU / ppu_d[ap]

        def at(target):
            return float(np.interp(target, cyx_d, norm))
        bandmax = cyx_d.max()
        print(f"{ap:>5} {len(shared):>6} {np.median(expo):>16.4f} "
              f"{np.std(expo)/np.median(expo):>7.2f} "
              f"{at(0.10):>15.3f} {at(0.20):>15.3f} "
              f"{norm[-1]:>10.3f}@{bandmax:.2f}")

    # pooled curve vs subject f_grid + D7200 sensor cy/px (F8 ppu as representative)
    print("\n=== pooled normalised ratio (median over aps+patches) vs D7200 sensor cy/px ===")
    fgs = np.array(sorted(pooled))
    pooledv = np.array([np.nanmedian(pooled[f]) for f in fgs])
    cyx = fgs * SPU / ppu_d["F8"]
    print(f"{'cy/px_D':>8} {'f_grid':>8} {'ratio':>7}")
    for c, f, v in zip(cyx, fgs, pooledv):
        if abs(c * 20 - round(c * 20)) < 0.02 or f in (fgs[0], fgs[-1]):  # ~every 0.05 cy/px
            print(f"{c:>8.3f} {f:>8.4f} {v:>7.3f}")
    zN = 0.5
    print(f"\nD7200 sensor Nyquist = 0.5 cy/px; PSD band tops out at "
          f"{cyx.max():.3f} cy/px ({cyx.max()/zN*100:.0f}% of Nyquist) -> "
          f"near-Nyquist OLPF roll-off is OUT OF BAND.")


if __name__ == "__main__":
    main()
