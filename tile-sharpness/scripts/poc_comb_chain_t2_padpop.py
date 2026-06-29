"""TASK 2 — pad-population diagnostic: are the metal cells TWO brightness populations
(some pads dark, some light -> partial fundamental cancellation) or ONE?

UNTRACKED / exploratory. Run on nufan (decodes JPEGs).

This is distinct from the substrate-vs-metal bimodality (the expected grid contrast).
We ask whether the METAL CELLS THEMSELVES split into two brightness modes.

Plan:
  1. Use SATURATION (diag-2 winner: clean high-contrast grid) to LOCATE & segment cells:
     - discover pad pitch along u and v (periodic_fft.discover_fundamental on the
       de-rotated saturation ROI, per axis),
     - recover grid PHASE from the FFT phase at each fundamental,
     - tile into per-cell regions on the (u,v) lattice.
  2. Classify each cell substrate-vs-metal by its saturation (substrate = high-sat brown;
     metal cell = low-sat). For each METAL cell compute a specular-robust central
     brightness (MEDIAN and p40) on LUMA and on R-B. Histogram those per-cell values.
     Bimodal (two pad types) or unimodal? Report Otsu split, valley depth, peak
     separation, fraction per mode.
  3. If bimodal: PNG mapping each cell to its mode; verdict INTERLEAVED (cancels the
     fundamental) vs SEPARATE BLOCKS; per-population vs mixed Michelson contrast.

Reuses the registration / region / best-focus plumbing from contrast_inspect.
Primary config: low-M bare Sigma 105 @ 1:1 best-focus (same ROI as diag 1/2).
Outputs: poc_comb_chain_out/contrast_inspect/padpop/
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_lib as L  # noqa: E402

spec = importlib.util.spec_from_file_location("apf", HERE / "atlas_periodic_fft.py")
apf = importlib.util.module_from_spec(spec); spec.loader.exec_module(apf)  # noqa: E402
spec2 = importlib.util.spec_from_file_location("ci", HERE / "poc_comb_chain_contrast_inspect.py")
ci = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(ci)  # noqa: E402
from tile_sharpness.methods.periodic_fft import derotate, discover_fundamental, periodic_contrast  # noqa: E402

OUT = HERE / "poc_comb_chain_out" / "contrast_inspect" / "padpop"
OUT.mkdir(parents=True, exist_ok=True)

# primary + a high-M cross-check (same as inspect CONFIGS)
CONFIGS = ci.CONFIGS


def sat_luma_rb(bgr):
    b, g, r = (bgr[:, :, 0].astype(np.float64), bgr[:, :, 1].astype(np.float64),
               bgr[:, :, 2].astype(np.float64))
    mx = np.maximum(np.maximum(r, g), b); mn = np.minimum(np.minimum(r, g), b)
    sat = np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 0) * 255.0
    luma = 0.114 * b + 0.587 * g + 0.299 * r
    rb = r - b
    return sat, luma, rb


def fundamental_phase(prof, f0):
    """Phase of the FFT at frequency f0 (cy/px), used to locate grid line positions.
    Returns the spatial offset (in px) of the first bright-line center from index 0."""
    n = prof.size
    x = np.arange(n)
    # project onto cos/sin at f0
    c = np.sum((prof - prof.mean()) * np.cos(2 * np.pi * f0 * x))
    s = np.sum((prof - prof.mean()) * np.sin(2 * np.pi * f0 * x))
    phase = np.arctan2(s, c)   # peak where cos(2pi f0 x - phase)=1 -> x = phase/(2pi f0)
    off = (phase / (2 * np.pi * f0)) % (1.0 / f0)
    return off


def recover_grid(sat_der):
    """Discover pad pitch along u (columns) and v (rows) on the de-rotated SATURATION
    ROI, recover phase. Returns (pu, ou, pv, ov) pitch/offset px per axis, or None."""
    band = (0.02, 0.40)
    ru = discover_fundamental(sat_der, band=band, axis="u")
    rv = discover_fundamental(sat_der, band=band, axis="v")
    if ru is None or rv is None:
        return None
    pu = ru["pitch_px"]; pv = rv["pitch_px"]
    prof_u = sat_der.mean(axis=0)   # over columns
    prof_v = sat_der.mean(axis=1)   # over rows
    ou = fundamental_phase(prof_u, 1.0 / pu)
    ov = fundamental_phase(prof_v, 1.0 / pv)
    return pu, ou, pv, ov


def cell_stats(sat_der, luma_der, rb_der, grid):
    """Tile into cells on the (u,v) lattice; per cell compute central (inner 50%)
    median/p40 of luma, R-B, and median saturation (for substrate/metal classification).
    Returns list of dicts."""
    pu, ou, pv, ov = grid
    h, w = sat_der.shape
    cells = []
    # cell centers at ou + (k+0.5)*pu  ... actually phase gives a bright-line center; the
    # lattice of cell centers is offset by pu/2 from line centers. We just tile uniformly
    # from ou with step pu and take the cell as [c-pu/2, c+pu/2].
    us = np.arange(ou, w, pu)
    vs = np.arange(ov, h, pv)
    inner = 0.5   # central fraction of the cell to sample (specular-robust + avoids edges)
    for cv in vs:
        for cu in us:
            x0 = int(round(cu - inner * pu / 2)); x1 = int(round(cu + inner * pu / 2))
            y0 = int(round(cv - inner * pv / 2)); y1 = int(round(cv + inner * pv / 2))
            if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 - x0 < 2 or y1 - y0 < 2:
                continue
            sat_c = sat_der[y0:y1, x0:x1]
            lum_c = luma_der[y0:y1, x0:x1]
            rb_c = rb_der[y0:y1, x0:x1]
            cells.append(dict(
                cu=float(cu), cv=float(cv), x0=x0, x1=x1, y0=y0, y1=y1,
                sat_med=float(np.median(sat_c)),
                lum_med=float(np.median(lum_c)), lum_p40=float(np.percentile(lum_c, 40)),
                rb_med=float(np.median(rb_c)), rb_p40=float(np.percentile(rb_c, 40)),
            ))
    return cells


def otsu_1d(v):
    return ci.otsu_threshold(np.asarray(v, float))


def bimodality(values):
    """Otsu split + valley depth + peak separation on a 1-D set."""
    v = np.asarray(values, float)
    thr, _ = otsu_1d(v)
    dark = v[v <= thr]; bright = v[v > thr]
    md = float(dark.mean()) if dark.size else 0.0
    mb = float(bright.mean()) if bright.size else 0.0
    hist, edges = np.histogram(v, bins=max(8, int(np.sqrt(len(v)))))
    centers = 0.5 * (edges[:-1] + edges[1:])
    ti = int(np.argmin(np.abs(centers - thr)))
    left = hist[:max(1, ti)].max() if ti > 0 else hist[0]
    right = hist[ti:].max() if ti < len(hist) else hist[-1]
    valley = hist[ti]
    valley_depth = 1.0 - valley / max(1, min(left, right))
    # Michelson on the two-population means (the "are pads two types" contrast)
    mich = (mb - md) / (mb + md) if (mb + md) > 0 else 0.0
    return dict(thr=thr, mean_dark=md, mean_bright=mb, n_dark=int(dark.size),
                n_bright=int(bright.size), valley_depth=float(valley_depth),
                peak_sep=float(mb - md), michelson=float(mich),
                frac_dark=float(dark.size / max(1, v.size)))


def main():
    summary = []
    for name, n_marked, sweep_dir in CONFIGS:
        sd = Path(sweep_dir)
        jpgs = sorted(sd.glob("*.jpg")) + sorted(sd.glob("*.JPG"))
        print(f"\n=== {name} ({len(jpgs)} frames) ===", flush=True)
        p = apf.register(jpgs)
        if p is None:
            print("  REG FAILED"); continue
        M = p["scale"] / apf.M_ANCHOR_SCALE
        theta = p["theta_deg"]
        sel = ci.best_pad_region(jpgs, p, M, theta)
        if sel is None:
            print("  no region"); continue
        _score, region, roi_gray, der_gray, seq, rec = sel
        x0, y0, x1, y1 = [int(v) for v in region["bbox"]]
        bgr = cv2.imread(str(jpgs[seq]), cv2.IMREAD_COLOR)[y0:y1, x0:x1]
        sat, luma, rb = sat_luma_rb(bgr)
        sat_d = derotate(sat, theta); luma_d = derotate(luma, theta); rb_d = derotate(rb, theta)
        grid = recover_grid(sat_d)
        if grid is None:
            print("  grid recovery FAILED"); continue
        pu, ou, pv, ov = grid
        print(f"  M={M:.3f} region={region['label']} roi={y1-y0}x{x1-x0} seq={seq}")
        print(f"  grid: pitch_u={pu:.1f}px off_u={ou:.1f}  pitch_v={pv:.1f}px off_v={ov:.1f}")
        cells = cell_stats(sat_d, luma_d, rb_d, grid)
        print(f"  tiled {len(cells)} cells")
        if len(cells) < 12:
            print("  too few cells"); continue

        # --- classify substrate vs metal by saturation ---
        sats = np.array([c["sat_med"] for c in cells])
        sthr, _ = otsu_1d(sats)
        # substrate = HIGH saturation (brown), metal cell = LOW saturation
        metal = [c for c in cells if c["sat_med"] <= sthr]
        substrate = [c for c in cells if c["sat_med"] > sthr]
        print(f"  sat split={sthr:.1f} -> {len(metal)} metal cells, {len(substrate)} substrate cells")
        if len(metal) < 10:
            print("  too few metal cells, using ALL cells as 'metal' fallback")
            metal = cells

        # --- bimodality of METAL cells on luma + R-B (median and p40) ---
        for chan, keymed, keyp40 in (("luma", "lum_med", "lum_p40"),
                                     ("R-B", "rb_med", "rb_p40")):
            for stat, key in (("median", keymed), ("p40", keyp40)):
                vals = [c[key] for c in metal]
                bm = bimodality(vals)
                flag = "BIMODAL" if bm["valley_depth"] > 0.15 else "unimodal"
                print(f"  metal cells [{chan} {stat:>6}]: {flag} "
                      f"valley={bm['valley_depth']:.2f} peak_sep={bm['peak_sep']:.1f} "
                      f"Otsu_C={bm['michelson']:.3f} darkfrac={bm['frac_dark']:.2f} "
                      f"(dark μ={bm['mean_dark']:.1f} n={bm['n_dark']}, bright μ={bm['mean_bright']:.1f} n={bm['n_bright']})")
                summary.append(dict(config=name, M=round(M, 3), pool="metal", channel=chan,
                                    stat=stat, n=len(vals), **{k: round(v, 4) if isinstance(v, float) else v
                                                               for k, v in bm.items()}))

        # --- headline: luma-median bimodality drives the spatial map + verdict ---
        vals = np.array([c["lum_med"] for c in metal])
        bm = bimodality(vals)
        bimodal = bm["valley_depth"] > 0.15
        # spatial arrangement: assign mode, look at how often neighbors (in grid index)
        # differ -> interleaved (checkerboard, high alternation) vs blocks (low alternation)
        # build grid indices
        us = sorted(set(round((c["cu"] - ou) / pu) for c in metal))
        vsi = sorted(set(round((c["cv"] - ov) / pv) for c in metal))
        uidx = {u: i for i, u in enumerate(us)}; vidx = {v: i for i, v in enumerate(vsi)}
        grid_mode = {}
        for c in metal:
            iu = uidx[round((c["cu"] - ou) / pu)]; iv = vidx[round((c["cv"] - ov) / pv)]
            grid_mode[(iv, iu)] = 1 if c["lum_med"] > bm["thr"] else 0
        # alternation rate among horizontal+vertical neighbor pairs
        diff = 0; tot = 0
        for (iv, iu), m in grid_mode.items():
            for dv, du in ((0, 1), (1, 0)):
                nb = grid_mode.get((iv + dv, iu + du))
                if nb is not None:
                    tot += 1; diff += (nb != m)
        alt = diff / tot if tot else float("nan")
        # interleaved if neighbors differ often (>~0.6 ~ checkerboard); blocks if rarely (<~0.3)
        arrangement = ("INTERLEAVED (checkerboard-like, cancels fundamental)" if alt > 0.55 else
                       "SEPARATE BLOCKS (consistent polarity per block)" if alt < 0.35 else
                       "MIXED / weak")
        print(f"  >>> METAL luma-median: {'BIMODAL' if bimodal else 'UNIMODAL'}; "
              f"neighbor alternation={alt:.2f} -> {arrangement}")

        # per-population vs mixed Michelson contrast (luma med)
        if bm["n_dark"] >= 3 and bm["n_bright"] >= 3:
            print(f"      per-population mean luma: dark={bm['mean_dark']:.1f} bright={bm['mean_bright']:.1f} "
                  f"=> two-pop Michelson={bm['michelson']:.3f}")

        # --- PNG: cell-mode map over the saturation ROI ---
        vis = cv2.cvtColor(ci_norm8(sat_d), cv2.COLOR_GRAY2BGR)
        for c in cells:
            col = (180, 180, 180)  # substrate gray
            if c in metal:
                col = (60, 60, 230) if c["lum_med"] > bm["thr"] else (230, 160, 60)  # bright=red dark=blue
            cv2.rectangle(vis, (c["x0"], c["y0"]), (c["x1"], c["y1"]), col, 1)
        up = cv2.resize(vis, (vis.shape[1] * 3, vis.shape[0] * 3), interpolation=cv2.INTER_NEAREST)
        mapp = OUT / f"{name}__cellmode_map.png"
        cv2.imwrite(str(mapp), up)
        # histogram PNG
        plt.figure(figsize=(6, 4))
        plt.hist([c["lum_med"] for c in metal], bins=max(8, int(np.sqrt(len(metal)))),
                 color="darkgreen", alpha=0.8)
        plt.axvline(bm["thr"], color="red", ls="--", label=f"Otsu={bm['thr']:.0f}")
        plt.title(f"{name}\nmetal-cell luma MEDIAN  valley={bm['valley_depth']:.2f} "
                  f"{'BIMODAL' if bimodal else 'unimodal'}  alt={alt:.2f}")
        plt.xlabel("per-cell luma median"); plt.ylabel("# metal cells"); plt.legend(fontsize=8)
        plt.tight_layout()
        plt.savefig(str(OUT / f"{name}__metal_luma_median_hist.png"), dpi=110); plt.close()
        print(f"  WROTE {mapp.name}, {name}__metal_luma_median_hist.png")

    csvp = OUT / "padpop_stats.csv"
    if summary:
        keys = list(summary[0].keys())
        with csvp.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys); w.writeheader()
            for r in summary:
                w.writerow(r)
    print(f"\nWROTE {csvp}")


def ci_norm8(a):
    lo, hi = np.percentile(a, 1), np.percentile(a, 99)
    if hi <= lo:
        return np.zeros_like(a, np.uint8)
    return np.clip((a - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)


if __name__ == "__main__":
    main()
