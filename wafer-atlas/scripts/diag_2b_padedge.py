"""Diagnostic: find the 2B two-pad die (appearance-based), isolate ONE long pad
edge, and measure ABSOLUTE MTF50 vs the diffraction ceiling, with the isolation
clearance reported per edge. Validates the metric before any ranking.

Run on nufan:
  WT=.../.claude/worktrees/2b-padedge
  PY=~/.cache/uv-venvs/tile-sharpness/bin/python
  cd $WT/wafer-atlas/scripts
  PYTHONPATH=$WT/tile-sharpness/src $PY diag_2b_padedge.py <config_key>
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
import cv2, numpy as np

HERE = Path(__file__).resolve().parent
WA = HERE.parent; ROOT = WA.parent
sys.path.insert(0, str(ROOT / "tile-sharpness" / "src"))
from tile_sharpness.methods.slanted_edge import mtf50_long_edge, mtf50_step_erf  # noqa: E402
from tile_sharpness.methods import pad_long_edge as ple  # noqa: E402
from tile_sharpness import optics  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


reg_auto = _load("reg_auto")
ATLAS = json.load(open(WA / "atlas.json"))
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
IMAGE_W, IMAGE_H = 8256, 5504
LPMM_PER_CYPX = 1000.0 / 4.35
M_ANCHOR_SCALE = 1.6549
# central block spanning BOTH pads (atlas experimental bbox_uv), grown a little in v
# so a partly-out pad is still captured for the finder.
EXP_BBOX_UV = (0.0, 0.266, 0.999, 0.881)
OUTDIR = HERE / "diag_2b_padedge_out"; OUTDIR.mkdir(exist_ok=True)

CONFIGS = {
    "AF200_1to1_F8": (RAW / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1" / "F8", 8.0),
    "AF200_1to1_F11": (RAW / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1" / "F11", 11.0),
    "Sigma150_1to1_F8": (RAW / "Sigma APO Macro 150mm F2.8 EX DG OS HSM" / "1_1" / "F8", 8.0),
    "Sigma105_1to1_F8": (RAW / "Sigma Macro 105mm F2.8 EX DG OS HSM" / "1_1" / "F8", 8.0),
    "105VR_1to1_F8": (RAW / "NIKKOR Z MC 105mm f_2.8 VR S" / "1_1" / "F8", 8.0),
    "6T_F8": (RAW / "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T" / "1.27_1" / "F8", 8.0),
    "Canon500D_F8": (RAW / "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D" / "1.07_1" / "F8", 8.0),
    "MCON35_F8": (RAW / "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Olympus MCON-35" / "1_1.16" / "F8", 8.0),
}


def central_lapvar(g):
    c = g[IMAGE_H // 2 - 800:IMAGE_H // 2 + 800, IMAGE_W // 2 - 800:IMAGE_W // 2 + 800]
    return cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var()


def register(jpgs):
    lv = []
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        lv.append((central_lapvar(g) if g is not None else -1.0, jp))
    lv.sort(reverse=True)
    cand = [jp for _, jp in lv[:5]]
    cand += [jpgs[int(len(jpgs) * f)] for f in (0.35, 0.5, 0.65)]
    best = None
    for jp in dict.fromkeys(cand):
        try:
            p = reg_auto.register_and_refine("diag", path=str(jp), anchors=None)
        except Exception:
            continue
        if p is None or not p.get("n_refine_intersections"):
            continue
        r = p["reg_fit_rmse_px"]
        if best is None or r < best[0]:
            best = (r, p)
    return best[1] if best else None


def block_bbox(col, row, aff, grow_v=0.10):
    u0, v0, u1, v1 = EXP_BBOX_UV
    v0 -= grow_v; v1 += grow_v
    cor = [reg_auto.grid_xy_distorted(col + u, row + v, aff)
           for (u, v) in [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
    xs = [c[0] for c in cor]; ys = [c[1] for c in cor]
    return min(xs), min(ys), max(xs), max(ys)


def _two_stacked(pads):
    """True if the top-2 pad bboxes form the 2B TWO-STACKED-PAD pattern: vertically
    stacked (one above the other), x-spans overlapping, similar widths. This is the
    DISTINCTIVE signature of die type (2,1); it rejects single-uniform-region dies
    (off-wafer background, other die types) that the finder would otherwise grab."""
    if len(pads) < 2:
        return False
    p0, p1 = pads[0], pads[1]
    xov = max(0, min(p0[2], p1[2]) - max(p0[0], p1[0]))
    w0, w1 = p0[2] - p0[0], p1[2] - p1[0]
    wmin = min(w0, w1)
    if wmin <= 0 or xov < 0.5 * wmin:
        return False
    if max(w0, w1) / wmin > 2.5:           # widths must be comparable
        return False
    # vertically separated (one clearly above the other), not side-by-side
    yov = max(0, min(p0[3], p1[3]) - max(p0[1], p1[1]))
    h0, h1 = p0[3] - p0[1], p1[3] - p1[1]
    if yov > 0.4 * min(h0, h1):            # too much y-overlap -> side-by-side
        return False
    return True


def find_twopad_die(g, aff, *, require_type21=True):
    """Scan in-FOV die cells for the 2B TWO-STACKED-PAD die. Returns
    (col,row,block_bbox,pad_bboxes) for the best genuine two-pad die, or None.

    A candidate must (a) be a (2,1)-type die in the atlas periodicity when
    ``require_type21`` (the labelling can be row-offset, so we ALSO accept the
    distinctive two-stacked-pad appearance on a non-(2,1)-labelled die — see below),
    and (b) show the two-stacked-pad signature. We score by total pad area and keep
    the best that passes the signature gate, so single-uniform-region dies (other
    types / off-wafer) are rejected even if larger."""
    best = None
    for col in range(0, 11):
        for row in range(0, 6):
            is_21 = (col % 4, row % 4) == (2, 1)
            bx0, by0, bx1, by1 = block_bbox(col, row, aff)
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            if not (60 < cx < IMAGE_W - 60 and 60 < cy < IMAGE_H - 60):
                continue
            ix0, iy0 = max(0, int(bx0)), max(0, int(by0))
            ix1, iy1 = min(IMAGE_W, int(bx1)), min(IMAGE_H, int(by1))
            if ix1 - ix0 < 100 or iy1 - iy0 < 100:
                continue
            frac = ((ix1 - ix0) * (iy1 - iy0)) / max(1, (bx1 - bx0) * (by1 - by0))
            if frac < 0.85:
                continue
            pads = ple.find_bright_pad(g, (ix0, iy0, ix1, iy1))
            if not _two_stacked(pads):
                continue
            # The two-stacked-pad pattern is unique to (2,1). reg_auto's absolute row
            # label can be offset by a row (REPORT_taskAD), so accept any die showing
            # the signature; prefer (2,1)-labelled dies by a score bonus.
            score = sum((p[2] - p[0]) * (p[3] - p[1]) for p in pads[:2])
            if is_21:
                score *= 1.5
            if best is None or score > best[0]:
                best = (score, col, row, (ix0, iy0, ix1, iy1), pads)
    if best is None:
        return None
    _, col, row, blk, pads = best
    return col, row, blk, pads


def roi_lapvar(g, x, y, half=200):
    y0, y1 = max(0, int(y - half)), min(g.shape[0], int(y + half))
    x0, x1 = max(0, int(x - half)), min(g.shape[1], int(x + half))
    r = g[y0:y1, x0:x1]
    return cv2.Laplacian(r.astype(np.float32), cv2.CV_32F).var() if r.size else -1.0


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "AF200_1to1_F8"
    ap_dir, N = CONFIGS[key]
    jpgs = sorted(ap_dir.glob("*.jpg"))
    print(f"=== {key}: {len(jpgs)} jpgs, N={N} ===")
    if not jpgs:
        print("no jpgs"); return
    aff = register(jpgs)
    if aff is None:
        print("registration FAILED"); return
    M = aff["scale"] / M_ANCHOR_SCALE
    n_eff = N * (1.0 + M)
    ceil_cypx = optics.diffraction_mtf50_sensor_lpmm(n_eff) / LPMM_PER_CYPX
    ceil_sub = optics.diffraction_mtf50_subject_lpmm(N, M)
    print(f"reg rmse={aff['reg_fit_rmse_px']:.2f}px  M={M:.3f}  N_eff={n_eff:.1f}  "
          f"ceil={ceil_cypx:.4f} cy/px  ceil_sub={ceil_sub:.1f} lp/mm")

    # locate the two-pad die on the sharpest-by-central-lapvar frame
    lv = [(central_lapvar(cv2.imread(str(j), cv2.IMREAD_GRAYSCALE)), j) for j in jpgs[::max(1, len(jpgs)//12)]]
    lv.sort(reverse=True)
    g_scan = cv2.imread(str(lv[0][1]), cv2.IMREAD_GRAYSCALE).astype(np.float32)
    found = find_twopad_die(g_scan, aff)
    if found is None:
        print("NO two-pad die found in FOV."); return
    col, row, blk, pads = found
    lbl = f"{col}{'ABCDEF'[row]}"
    print(f"two-pad die: {lbl} type=({col%4},{row%4}) block={blk}  "
          f"pads(area-sorted)={pads[:3]}")

    # best-focus shot at the chosen pad region
    mx, my = (pads[0][0] + pads[0][2]) / 2, (pads[0][1] + pads[0][3]) / 2
    bb = (-1.0, None)
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        l = roi_lapvar(g, mx, my)
        if l > bb[0]:
            bb = (l, jp)
    print(f"best-focus shot at pad: {bb[1].name} (lapvar {bb[0]:.0f})")
    g = cv2.imread(str(bb[1]), cv2.IMREAD_GRAYSCALE).astype(np.float32)
    # re-find pads on the actual focus frame (small shift between frames)
    pads = ple.find_bright_pad(g, blk)
    if not pads:
        print("pads vanished on focus frame"); return

    HW = 12.0
    MIN_TILT = 3.0          # a real ~5deg grid edge; <3deg = a bad/axis-aligned detect
    MIN_OPEN_CLEAR = 2.0 * HW    # open field must be clean >= 2*half-window
    rows = []
    for pi, pad in enumerate(pads[:2]):
        for side in ("top", "bottom"):
            res = ple.refine_pad_hedge(g, pad, side=side)
            if res is None:
                print(f"  pad{pi} [{side}] edge refine FAILED")
                continue
            seg, off = res
            pad_clear, open_clear, spec = ple.isolation_clearance(g, seg, pad, side)
            m_long = mtf50_long_edge(g, seg, half_window_px=HW)
            m_step = mtf50_step_erf(g, seg, half_window_px=HW)
            sub_long = m_long * LPMM_PER_CYPX * M if m_long else None
            vc = (m_long / ceil_cypx) if m_long else None
            # GATE: real tilt, isolated open field, no specular rim, fit succeeded
            gate_ok = (off >= MIN_TILT and open_clear >= MIN_OPEN_CLEAR
                       and not spec and m_long is not None)
            flag = "OK " if gate_ok else "rej"
            print(f"  [{flag}] pad{pi} [{side}] L={seg.length_px:.0f}px off={off:.2f}deg  "
                  f"clear pad={pad_clear:.0f} open={open_clear:.0f} spec={int(spec)} (HW={HW:.0f})  "
                  f"mtf50_long={m_long if m_long is None else round(m_long,4)} "
                  f"vs_ceil={vc if vc is None else round(vc,2)}x  "
                  f"sub={sub_long if sub_long is None else round(sub_long,1)}lp/mm  "
                  f"step_erf={m_step if m_step is None else round(m_step,4)}")
            if gate_ok:
                rows.append((pi, side, off, open_clear, m_long, vc, sub_long, m_step))
            ey = int((seg.y0 + seg.y1) / 2)
            sy0, sy1 = max(0, ey - 35), min(IMAGE_H, ey + 35)
            strip = g[sy0:sy1, int(seg.x0):int(seg.x1)]
            if strip.size:
                cv2.imwrite(str(OUTDIR / f"{key}_{lbl}_p{pi}_{side}.png"),
                            np.clip(strip, 0, 255).astype(np.uint8))
    if rows:
        ml = [r[4] for r in rows]
        print(f"  >>> GATE-PASSING edges: n={len(rows)}  mtf50_long cy/px="
              f"{[round(x,3) for x in ml]}  vs_ceil={[round(r[5],2) for r in rows]}  "
              f"sub_lpmm={[round(r[6],1) for r in rows if r[6]]}")
    else:
        print("  >>> NO gate-passing edges (all edges rejected: tilt/isolation/specular/fit)")


if __name__ == "__main__":
    main()
