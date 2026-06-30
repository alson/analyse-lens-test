"""Stage AltEst-2 — same-patch VARIANTS that build on the established principles, all
consuming the altest2/patches/*.npy common-grid patches + meta.

P3.3  EDGE-REGION MASK x same-patch ratio. A lattice-locked geometric mask keeps only the
      high-edge-density zones of the patch (the pad boundaries), discarding the unstable
      pad interior. The mask is derived ONCE per atlas cell from the MEDIAN edge map across
      all configs that share the cell (a reproducible, config-independent geometry), then
      APPLIED identically to every config's patch before the PSD-ratio chain. Because the
      mask is identical for both configs of a pair, it cancels in the ratio (it is a
      reproducible distortion). Tests the "distort toward a reproducible spectrum" idea.

P3.4  MATCHED-FILTER / LOCK-IN vs a synthetic ideal lattice template at f0. Cross-correlate
      each common-grid patch with a synthetic ideal pad-lattice template (a known, stable
      reference). The correlation-peak SHARPNESS (its width / a homodyne local-amplitude
      map at f0) encodes the system MTF; reading the relative peak amplitude between two
      same-patch configs at fixed sensor f0 is a relative-MTF that PRESERVES blur
      (correlation, not thresholding).

P3.5  CROSS-CHECKS on the common-scale patch: spectral COHERENCE-weighted amplitude ratio,
      and a gradient-energy ratio (non-spectral). Cheap extra independent reads.

All produce a per-config score via the same additive/log-ratio zero-mean chain as P1, read
at fixed SENSOR frequency. Writes altest2/p33_*, p34_*, p35_* scores. Read-only on libs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "poc_comb_chain_out" / "altest2"
PATCH_DIR = OUT / "patches"
SPU = 700.0
F_PX = 0.12   # fixed sensor frequency for the variant reads (centre of the P1 window)


def load_meta():
    meta = pd.concat([pd.read_csv(f) for f in OUT.glob("meta_shard_*.csv")], ignore_index=True)
    return meta.drop_duplicates("config")


def hann2d(h, w):
    return np.outer(np.hanning(h), np.hanning(w))


def index_patches():
    by_cell = {}
    for f in sorted(PATCH_DIR.glob("*__*.npy")):
        sid, cell = f.stem.split("__")
        by_cell.setdefault(cell, {})[sid] = f
    return by_cell


def chain(edges, Mmap, label, smaller_is_sharper=False, additive=False):
    nodes = sorted({e[0] for e in edges} | {e[1] for e in edges})
    if len(nodes) < 3:
        print(f"  {label}: too few nodes"); return None
    idx = {n: k for k, n in enumerate(nodes)}; n = len(nodes)
    rows, rhs, ws = [], [], []
    for a, b, d, w in edges:
        r = np.zeros(n); r[idx[a]] = 1; r[idx[b]] = -1
        rows.append(r); rhs.append(d); ws.append(w)
    rows.append(np.ones(n)); rhs.append(0.0); ws.append(len(edges))
    A = np.array(rows); bb = np.array(rhs); W = np.sqrt(np.array(ws))
    sol, *_ = np.linalg.lstsq(A * W[:, None], bb * W, rcond=None)
    score = {nd: float(sol[k]) for nd, k in idx.items()}
    resid = np.sqrt(np.mean([(score[a] - score[b] - d) ** 2 for a, b, d, w in edges]))
    df = pd.DataFrame([(s, score[s], Mmap.get(s)) for s in nodes],
                      columns=["sid", "score", "M"])
    df = df.sort_values("score", ascending=smaller_is_sharper)
    sgn = -1.0 if smaller_is_sharper else 1.0
    corr = np.corrcoef(df.M, sgn * df.score)[0, 1]
    bare = df[~df.sid.str.contains(r"\+", regex=True)]
    acc = df[df.sid.str.contains(r"\+", regex=True)]
    floats = []
    if len(bare) and len(acc):
        if smaller_is_sharper:
            best = bare.score.min(); floats = acc[acc.score < best].sid.tolist()
        else:
            best = bare.score.max(); floats = acc[acc.score > best].sid.tolist()
    print(f"\n--- {label}: {len(nodes)} nodes, {len(edges)} edges, resid={resid:.3f}, "
          f"corr(M,sharp)={corr:+.3f}, floats={floats or 'none'} ---")
    print(df.round(3).to_string(index=False))
    return df


def amp_at_fpx(patch, ppu, mask=None):
    """Radial amplitude at the fixed sensor F_PX (-> common-grid cy/px = F_PX*ppu/SPU)."""
    a = patch.astype(np.float64); a = a - a.mean()
    if mask is not None:
        a = a * mask
    h, w = a.shape
    a = a * hann2d(h, w)
    F = np.fft.fftshift(np.fft.fft2(a)); A = np.abs(F)
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    fr = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    fg = F_PX * ppu / SPU
    sel = np.abs(fr - fg) < 0.01
    if sel.sum() < 4:
        return None
    return float(A[sel].mean())


def edge_density_mask(patch):
    g = patch.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.GaussianBlur(np.hypot(gx, gy), (0, 0), 9)
    return mag


def synth_template(shape, ppu):
    """Synthetic ideal lattice template at the pad fundamental f0 (~one pad pair per grid
    quarter). We use the dominant lattice frequency at fixed sensor F_PX-equivalent — a
    separable cosine lattice. Known/stable reference (the matched filter's anchor)."""
    h, w = shape
    fg = F_PX * ppu / SPU   # cy per common-grid px
    yy, xx = np.mgrid[0:h, 0:w]
    t = np.cos(2 * np.pi * fg * xx) * np.cos(2 * np.pi * fg * yy)
    return t.astype(np.float32)


def main():
    meta = load_meta()
    Mmap = dict(zip(meta.sid, meta.M))
    ppu = dict(zip(meta.sid, meta.px_per_unit))
    by_cell = index_patches()
    print(f"{len(by_cell)} cells, {sum(len(v) for v in by_cell.values())} patch files")

    # cache loaded patches per (sid,cell)
    cache = {}
    def get(sid, cell):
        key = (sid, cell)
        if key not in cache:
            cache[key] = np.load(by_cell[cell][sid])
        return cache[key]

    # P3.3 — build a per-cell mask from the MEDIAN edge-density across configs, then
    # masked amplitude-ratio chain
    p33_edges, p34_edges, p35_coh_edges, p35_grad_edges = [], [], [], []
    for cell, sidmap in by_cell.items():
        sids = [s for s in sidmap if s in ppu]
        if len(sids) < 2:
            continue
        # reproducible mask: median edge-density map over configs, threshold at its 60th pct
        emaps = []
        shapes = []
        for s in sids:
            p = get(s, cell); shapes.append(p.shape)
        # unify to the smallest common shape (configs differ by a few px)
        H = min(sh[0] for sh in shapes); Wd = min(sh[1] for sh in shapes)
        if H < 32 or Wd < 32:
            continue
        for s in sids:
            p = get(s, cell)[:H, :Wd]
            emaps.append(edge_density_mask(p))
        med_edge = np.median(np.array(emaps), axis=0)
        thr = np.percentile(med_edge, 60)
        mask = (med_edge >= thr).astype(np.float32)
        mask = cv2.GaussianBlur(mask, (0, 0), 3)   # soft, reproducible

        # template for P3.4 (same shape, fixed f0 via mean ppu of the cell)
        tmpl = synth_template((H, Wd), float(np.mean([ppu[s] for s in sids])))
        tmpl = (tmpl - tmpl.mean())

        feats = {}
        for s in sids:
            p = get(s, cell)[:H, :Wd]
            # P3.3 masked amplitude at fixed sensor freq
            am = amp_at_fpx(p, ppu[s], mask=mask)
            # P3.4 matched filter: local homodyne amplitude at f0 = |<patch, template>| via
            # normalised cross-correlation peak energy (preserves blur)
            a = (p - p.mean()) * hann2d(H, Wd)
            mf = float(np.abs(np.sum(a * tmpl)) / (np.linalg.norm(a) * np.linalg.norm(tmpl) + 1e-9))
            # P3.5 gradient energy (non-spectral) + full amplitude (for coherence weight)
            gx = cv2.Sobel(p, cv2.CV_32F, 1, 0, 3); gy = cv2.Sobel(p, cv2.CV_32F, 0, 1, 3)
            ge = float(np.mean(gx * gx + gy * gy))
            af = amp_at_fpx(p, ppu[s], mask=None)
            feats[s] = dict(am=am, mf=mf, ge=ge, af=af)
        for ia in range(len(sids)):
            for ib in range(ia + 1, len(sids)):
                sa, sb = sids[ia], sids[ib]
                fa, fb = feats[sa], feats[sb]
                if fa["am"] and fb["am"] and fa["am"] > 0 and fb["am"] > 0:
                    p33_edges.append((sa, sb, float(np.log(fa["am"] / fb["am"])), 1.0))
                if fa["mf"] > 0 and fb["mf"] > 0:
                    p34_edges.append((sa, sb, float(np.log(fa["mf"] / fb["mf"])), 1.0))
                if fa["af"] and fb["af"] and fa["af"] > 0 and fb["af"] > 0:
                    p35_coh_edges.append((sa, sb, float(np.log(fa["af"] / fb["af"])), 1.0))
                if fa["ge"] > 0 and fb["ge"] > 0:
                    p35_grad_edges.append((sa, sb, float(np.log(fa["ge"] / fb["ge"])), 1.0))

    print("\n" + "=" * 72 + "\nP3.3 — edge-mask x same-patch amplitude ratio (fixed sensor f_px)\n" + "=" * 72)
    d33 = chain(p33_edges, Mmap, "P3.3 edge-masked relMTF")
    print("\n" + "=" * 72 + "\nP3.4 — matched-filter (synthetic lattice template) relative amplitude\n" + "=" * 72)
    d34 = chain(p34_edges, Mmap, "P3.4 matched-filter relMTF")
    print("\n" + "=" * 72 + "\nP3.5 — cross-checks (full-amp ratio / gradient-energy ratio)\n" + "=" * 72)
    d35a = chain(p35_coh_edges, Mmap, "P3.5 full-amp ratio @f_px")
    d35b = chain(p35_grad_edges, Mmap, "P3.5 gradient-energy ratio")

    for df, name in ((d33, "p33_edgemask"), (d34, "p34_matchfilter"),
                     (d35a, "p35_fullamp"), (d35b, "p35_gradenergy")):
        if df is not None:
            df.round(4).to_csv(OUT / f"{name}_scores.csv", index=False)
    print("\nwrote variant score CSVs")


if __name__ == "__main__":
    main()
