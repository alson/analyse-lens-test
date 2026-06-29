"""Route 2 — flat-edge slanted-edge MTF on the 2B serpent horizontal lines.

The 2B middle band is long BRIGHT horizontal metal lines on a DARK substrate (a
FLAT reflectance pattern: symmetric dips, no specular rim — verified by profile).
Each line gives TWO long isolated edges: a RISING edge (dark gap -> bright line,
scanning +y) and a FALLING edge (bright line -> dark gap). These are the longest
isolated flat reflectance steps the wafer offers.

We:
  1. register + locate the de-rotated 2B block (lib_2b),
  2. detect the horizontal bright-line edges from the block row-mean profile,
  3. for each candidate edge, fit it per-column in the ORIGINAL (rotated ~5deg)
     frame to a slanted Segment (slant needed for ISO super-resolution),
  4. measure per-side clearance + line/gap width + specular-rim flag,
  5. gate edges (clean clearance >= a few x PSF, real contrast), then
     MTF50 via slanted_edge.mtf50_step_erf (single monotone step, quality gate)
     cross-checked with mtf50_step_iso,
  6. report top-edge vs bottom-edge agreement (the flatness test) + vs ceiling.

Subject lp/mm = MTF50_cypx * M * 229.9. Ceiling = diffraction_mtf50_sensor_lpmm
at N_eff = N*(1+M), times 229.9-equivalent (we compare in cy/px directly).
Run on nufan.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib_2b as L  # noqa: E402
sys.path.insert(0, str(HERE.parent.parent / "tile-sharpness" / "src"))
from tile_sharpness.methods.lsf import Segment  # noqa: E402
from tile_sharpness.methods import slanted_edge as se  # noqa: E402
from tile_sharpness import optics  # noqa: E402
import cv2  # noqa: E402


def _subpix(mag, k):
    if k <= 0 or k >= len(mag) - 1:
        return 0.0
    den = mag[k - 1] - 2 * mag[k] + mag[k + 1]
    return 0.5 * (mag[k - 1] - mag[k + 1]) / den if den else 0.0


def derot_to_orig(xb, yb, bbox, theta_deg, full_shape, crop_shape):
    """Map a point in the de-rotated block back to ORIGINAL full-image coords.
    pf.derotate rotates the CROP about its own centre by +theta (cv2 convention),
    then trims a seam of t px each side. Invert: undo trim, undo rotation, add bbox."""
    ix0, iy0, ix1, iy1 = bbox
    ch, cw = crop_shape
    t = max(2, int(0.08 * min(ch, cw)))
    # de-rotated block coords -> coords in the (untrimmed) rotated crop
    xr, yr = xb + t, yb + t
    # cv2.getRotationMatrix2D(center, theta, 1) rotates; invert it
    Mrot = cv2.getRotationMatrix2D((cw / 2.0, ch / 2.0), theta_deg, 1.0)
    Minv = cv2.invertAffineTransform(Mrot)
    xc = Minv[0, 0] * xr + Minv[0, 1] * yr + Minv[0, 2]
    yc = Minv[1, 0] * xr + Minv[1, 1] * yr + Minv[1, 2]
    return ix0 + xc, iy0 + yc


def detect_line_edges(block, M):
    """From the de-rotated block, return candidate horizontal edges as
    (y_block, kind, half_clear_up, half_clear_dn, line_w, gap_w) where kind is
    'rising' (dark->bright down the column) or 'falling'. Uses the row-mean profile.
    Restrict to the central x band (dodge the bond-pad columns)."""
    H, W = block.shape
    x0, x1 = int(0.20 * W), int(0.80 * W)
    prof = block[:, x0:x1].mean(axis=1)
    g = np.gradient(prof)
    from scipy.signal import find_peaks
    # bright lines ~ pitch; detect both rising (g>0) and falling (g<0) zero... use
    # gradient extrema as edges. Expected pitch ~26px at M=1, scales with M.
    min_dist = max(4, int(8 * M))
    ris, _ = find_peaks(g, distance=min_dist, prominence=2.0)
    fal, _ = find_peaks(-g, distance=min_dist, prominence=2.0)
    all_edges = sorted([k for k in ris] + [k for k in fal])
    edges = [(int(k), "rising") for k in ris] + [(int(k), "falling") for k in fal]
    edges.sort()
    out = []
    bright = float(np.percentile(prof, 80))
    dark = float(np.percentile(prof, 20))
    mid = 0.5 * (bright + dark)
    for k, kind in edges:
        # clearance = distance to the NEAREST other edge (rising or falling),
        # i.e. how far the flat asymptote extends before the next transition.
        others = [e for e in all_edges if e != k]
        up_e = [e for e in others if e < k]
        dn_e = [e for e in others if e > k]
        cu = (k - max(up_e)) if up_e else k
        cd = (min(dn_e) - k) if dn_e else (H - 1 - k)
        out.append((k, kind, int(cu), int(cd), prof[max(0, k - 1)], prof[min(H - 1, k + 1)]))
    return out, prof, (bright, dark, mid)


def fit_edge_segment(full, x_lo, x_hi, y_orig_guess, kind, theta_deg, search=10):
    """Per-column sub-pixel fit of a near-horizontal edge in the ORIGINAL frame,
    over columns [x_lo,x_hi], starting near y_orig_guess (slope ~tan(theta))."""
    H, W = full.shape
    slope = np.tan(np.radians(theta_deg))
    pts = []
    x_lo = max(0, int(x_lo)); x_hi = min(W, int(x_hi))
    for cx in range(x_lo, x_hi):
        yc = y_orig_guess + slope * (cx - x_lo)
        lo = max(0, int(yc - search)); hi = min(H, int(yc + search))
        col = full[lo:hi, cx].astype(np.float32)
        if col.size < 6:
            continue
        gr = np.gradient(col)
        k = int(np.argmax(gr)) if kind == "rising" else int(np.argmin(gr))
        if 1 <= k <= len(col) - 2:
            off = _subpix(np.abs(gr), k)
            pts.append((cx, lo + k + off))
    if len(pts) < 30:
        return None
    pts = np.array(pts)
    xs, ys = pts[:, 0], pts[:, 1]
    A = np.polyfit(xs, ys, 1)
    resid = ys - np.polyval(A, xs)
    keep = np.abs(resid) < 2.5 * (np.std(resid) + 1e-6)
    xs, ys = xs[keep], ys[keep]
    if xs.size < 30:
        return None
    A = np.polyfit(xs, ys, 1)
    off_axis = abs(np.degrees(np.arctan(A[0])))
    xa, xb = float(xs.min()), float(xs.max())
    seg = Segment(x0=xa, y0=float(np.polyval(A, xa)), x1=xb, y1=float(np.polyval(A, xb)))
    return seg, off_axis, float(np.std(resid))


def perp_profile_orig(full, seg, half=40.0, step=0.5, n_along=60):
    """Mean intensity vs signed perpendicular distance d (px) along the edge, in the
    ORIGINAL frame. +d defined as the direction of increasing image-y component of
    the perpendicular."""
    L = seg.length_px
    ux, uy = (seg.x1 - seg.x0) / L, (seg.y1 - seg.y0) / L
    perpx, perpy = -uy, ux
    if perpy < 0:
        perpx, perpy = -perpx, -perpy   # make +d point toward larger y
    H, W = full.shape
    ds = np.arange(-half, half + step, step)
    ts = np.linspace(0.15 * L, 0.85 * L, n_along)
    prof = np.full(ds.size, np.nan)
    for i, d in enumerate(ds):
        vals = []
        for t in ts:
            cx = seg.x0 + ux * t + perpx * d
            cy = seg.y0 + uy * t + perpy * d
            xi, yi = int(round(cx)), int(round(cy))
            if 0 <= xi < W and 0 <= yi < H:
                vals.append(full[yi, xi])
        if vals:
            prof[i] = float(np.mean(vals))
    return ds, prof


def specular_rim(ds, prof, kind):
    """Test for a bright rim just past the edge on the DARK side. Returns
    (rim_flag, dark_level, bright_level). For a flat step the dark side is a flat
    plateau; a rim is a local bump above that plateau within ~2..12 px."""
    finite = np.isfinite(prof)
    if finite.sum() < 10:
        return False, np.nan, np.nan
    zero = int(np.argmin(np.abs(ds)))
    stepsz = float(ds[1] - ds[0])
    # bright side / dark side depend on kind: rising = dark at -d, bright at +d
    if kind == "rising":
        bright = float(np.nanmedian(prof[zero + int(15 / stepsz):]))
        dark = float(np.nanmedian(prof[:max(1, zero - int(15 / stepsz))]))
        # dark side is -d; look for a rim just before the edge (more negative side)
        i_hi = zero - int(2.0 / stepsz)
        i_lo = max(0, zero - int(14.0 / stepsz))
    else:
        bright = float(np.nanmedian(prof[:max(1, zero - int(15 / stepsz))]))
        dark = float(np.nanmedian(prof[zero + int(15 / stepsz):]))
        i_lo = zero + int(2.0 / stepsz)
        i_hi = min(ds.size, zero + int(14.0 / stepsz))
    if i_hi - i_lo < 4:
        return False, dark, bright
    seg_open = prof[i_lo:i_hi]
    fin = np.isfinite(seg_open)
    if fin.sum() < 4:
        return False, dark, bright
    lo = float(np.nanmin(seg_open)); hi = float(np.nanmax(seg_open))
    k = int(np.nanargmax(seg_open))
    contrast = bright - dark
    rose = (hi - lo) > 0.30 * abs(contrast)
    settled = lo < dark + 0.25 * abs(contrast)
    rim = bool(rose and settled and 0 < k < (i_hi - i_lo - 1))
    return rim, dark, bright


def measure_config(lens, mag, ap, n_eval=60, save_prefix=None):
    ap_dir = L.RAW / lens / mag / ap
    rmse, aff, jp0, jpgs = L.register_best(ap_dir)
    if aff is None:
        return dict(config=f"{lens}|{mag}|{ap}", ok=False, reason="reg-fail")
    M = aff["scale"] / L.M_ANCHOR_SCALE
    theta = aff.get("theta_deg", 0.0)
    n_eff = float(ap.replace("F", "").replace("_", ".")) * (1.0 + M)
    ceil_cypx = optics.diffraction_mtf50_sensor_lpmm(n_eff) / L.LPMM_PER_CYPX

    info = L.get_block(jp0, aff, want_type=(2, 1), derotate=True)
    if info is None:
        return dict(config=f"{lens}|{mag}|{ap}", ok=False, reason="no-2b")
    block, bbox = info["block"], info["bbox"]
    ix0, iy0, ix1, iy1 = bbox
    crop_shape = (iy1 - iy0, ix1 - ix0)
    edges, prof, (bright, dark, mid) = detect_line_edges(block, M)

    # pick the field-tilt-aware best-focus frame near this block centre across the sweep
    full0 = info["full"]
    H, W = full0.shape
    Hb, Wb = block.shape
    cx_b, cy_b = 0.5 * Wb, 0.5 * Hb
    cxo, cyo = derot_to_orig(cx_b, cy_b, bbox, theta, (H, W), crop_shape)

    def lapvar_at(g, mx, my, half=120):
        y0, y1 = max(0, int(my - half)), min(g.shape[0], int(my + half))
        x0, x1 = max(0, int(mx - half)), min(g.shape[1], int(mx + half))
        r = g[y0:y1, x0:x1]
        return cv2.Laplacian(r.astype(np.float32), cv2.CV_32F).var() if r.size else -1.0

    bestjp, bestlv = jp0, -1.0
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        lv = lapvar_at(g, cxo, cyo)
        if lv > bestlv:
            bestlv, bestjp = lv, jp
    full = cv2.imread(str(bestjp), cv2.IMREAD_GRAYSCALE).astype(np.float32)

    # central x band of the block in block coords -> original x range for fitting
    bx_lo, bx_hi = int(0.20 * Wb), int(0.80 * Wb)
    # convert the two block-x extremes (at the edge's y) to original coords below.

    # half-window for super-res: must fit within per-side clearance; cap to ~min
    # clearance and to a sensible absolute. Edge PSF ~ a few px; need >= ~8-10px.
    results = []
    # sort edges by min clearance desc to prefer the most isolated
    edges2 = sorted(edges, key=lambda e: -min(e[2], e[3]))
    for (yk, kind, cu, cd, _, _) in edges2:
        clear = min(cu, cd)
        if clear < 5:                 # too close to neighbour
            continue
        # half-window MUST fit inside the clearance to neighbouring edges, else the
        # super-res window spans multiple lines -> a periodic ridge (gate rejects).
        # Keep a 1px margin off the neighbour; need >= ~6px for a usable ESF.
        half = float(min(clear - 1.0, 24.0))
        if half < 6.0:
            continue
        # original-frame guess for this edge's y at block-x = bx_lo
        ox0, oy0 = derot_to_orig(bx_lo, yk, bbox, theta, (H, W), crop_shape)
        ox1, oy1 = derot_to_orig(bx_hi, yk, bbox, theta, (H, W), crop_shape)
        fit = fit_edge_segment(full, ox0, ox1, oy0, kind, theta)
        if fit is None:
            continue
        seg, off_axis, straight = fit
        if not (1.5 < off_axis < 9.0):    # need slant for super-res, but not a wrong line
            continue
        ds, pp = perp_profile_orig(full, seg, half=max(40.0, half + 10))
        rim, dlev, blev = specular_rim(ds, pp, kind)
        contrast = abs(blev - dlev)
        if contrast < 15:
            continue
        m_erf = se.mtf50_step_erf(full, seg, half_window_px=half, quality_gate=True)
        m_iso = se.mtf50_step_iso(full, seg, half_window_px=half)
        results.append(dict(y_block=yk, kind=kind, clear_up=cu, clear_dn=cd,
                            half=half, seg_len=seg.length_px, off_axis=off_axis,
                            straight_resid=straight, contrast=contrast, rim=rim,
                            dark=dlev, bright=blev,
                            mtf50_erf=m_erf, mtf50_iso=m_iso,
                            over_erf=(m_erf / ceil_cypx if m_erf else None)))
        if len(results) >= n_eval:
            break
    return dict(config=f"{lens}|{mag}|{ap}", ok=True, M=M, theta=theta, rmse=rmse,
                n_eff=n_eff, ceil_cypx=ceil_cypx, ceil_lpmm=ceil_cypx * L.LPMM_PER_CYPX * M,
                label=info["label"], jp=bestjp.name, n_edges=len(edges),
                line_pitch_est=float(np.median(np.diff(sorted(e[0] for e in edges)))) if len(edges) > 2 else None,
                results=results)


def fmt(r):
    if not r["ok"]:
        return f"{r['config']}: FAIL ({r['reason']})"
    lines = [f"\n=== {r['config']} ===",
             f" M={r['M']:.3f} theta={r['theta']:.2f} rmse={r['rmse']:.2f} N_eff={r['n_eff']:.1f}"
             f" ceil={r['ceil_cypx']:.3f}cy/px ({r['ceil_lpmm']:.1f}lp/mm) die={r['label']}"
             f" line_pitch~{r['line_pitch_est']}px frame={r['jp'][:24]}"]
    lines.append(f" {'y':>4} {'kind':>7} {'clrU':>4} {'clrD':>4} {'half':>4} {'len':>5} {'off':>4}"
                 f" {'con':>4} {'rim':>4} {'erf':>7} {'iso':>7} {'over':>5}")
    passing = [x for x in r["results"] if x["mtf50_erf"]]
    rising = [x for x in passing if x["kind"] == "rising"]
    falling = [x for x in passing if x["kind"] == "falling"]
    lines.append(f" n_edges_detected={r['n_edges']}  erf-PASSING={len(passing)}  "
                 f"(rising {len(rising)}, falling {len(falling)})")
    for x in passing:
        e = f"{x['mtf50_erf']:.3f}"
        i = f"{x['mtf50_iso']:.3f}" if x["mtf50_iso"] else "   -  "
        o = f"{x['over_erf']:.2f}" if x["over_erf"] else "  -  "
        lines.append(f" {x['y_block']:>4} {x['kind']:>7} {x['clear_up']:>4} {x['clear_dn']:>4}"
                     f" {x['half']:>4.0f} {x['seg_len']:>5.0f} {x['off_axis']:>4.1f}"
                     f" {x['contrast']:>4.0f} {str(x['rim']):>4} {e:>7} {i:>7} {o:>5}")
    if passing:
        allm = [x["mtf50_erf"] for x in passing]
        n_over = sum(1 for x in passing if x["over_erf"] and x["over_erf"] > 1.0)
        n_rim = sum(1 for x in passing if x["rim"])
        lines.append(f" erf cy/px: median={np.median(allm):.3f} range=[{min(allm):.3f},{max(allm):.3f}]  "
                     f"OVER-ceiling={n_over}/{len(passing)}  with-rim={n_rim}/{len(passing)}  "
                     f"median lp/mm={np.median(allm)*r['M']*L.LPMM_PER_CYPX:.1f}")
    if rising and falling:
        mr = np.median([x["mtf50_erf"] for x in rising])
        mf = np.median([x["mtf50_erf"] for x in falling])
        lines.append(f" RISING(dark->bright) median erf={mr:.3f}  FALLING(bright->dark) median erf={mf:.3f}  "
                     f"agree ratio={max(mr,mf)/min(mr,mf):.2f}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="+", default=None,
                    help="lens|mag|ap triples")
    args = ap.parse_args()
    default = [
        "Nikon AF Micro-Nikkor 200mm f_4D IF-ED|1_1|F8",
    ]
    triples = args.configs or default
    for t in triples:
        lens, mag, apr = t.split("|")
        r = measure_config(lens, mag, apr)
        print(fmt(r))


if __name__ == "__main__":
    main()
