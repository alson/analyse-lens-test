"""Fix sweep1 detection: (1) tilt by SCRIBE-ALIGNMENT search (maximize long-line
response over a tilt range) instead of the gradient histogram, which fails at
low M; (2) long-line L relative to the wafer span, tuned prominence. Report
col/row peak counts and verify against true tilt +4.77."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import numpy as np
from scipy.ndimage import rotate as ndi_rotate, sobel, binary_opening
from scipy.signal import find_peaks

HERE = Path(__file__).parent; A = HERE.parent
def _load(m, f):
    s = importlib.util.spec_from_file_location(m, HERE / f); x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
mm = _load("mm", "register_method_morphological.py"); ra = _load("ra", "reg_auto.py")


def long_line(bp, mask, axis, pct=80.0, frac=0.40):
    work = bp if axis == 0 else bp.T
    mwork = mask if axis == 0 else mask.T
    edges = np.abs(sobel(work, axis=1))
    thr = np.percentile(edges, pct)
    em = edges > thr
    rows_w = np.where(mwork.any(axis=1))[0]
    span = (rows_w[-1] - rows_w[0]) if rows_w.size else work.shape[0]
    L = max(5, int(span * frac))
    opened = binary_opening(em, structure=np.ones((L, 1), bool))
    return opened.sum(axis=0).astype(np.float32), L


def tilt_search(gray, mask, rng=8.0, step=0.5):
    """Pick the tilt maximizing total long-line scribe response."""
    best, best_t = -1, 0.0
    scores = []
    for t in np.arange(-rng, rng + step, step):
        der = ndi_rotate(gray, t, reshape=False, order=1, mode="reflect")
        mder = ndi_rotate(mask.astype(np.float32), t, reshape=False, order=1) > 0.5
        bp = mm.bandpass_image(der)
        cs, _ = long_line(bp, mder, 0); rs, _ = long_line(bp, mder, 1)
        s = float(cs.sum() + rs.sum())
        scores.append((t, s))
        if s > best:
            best, best_t = s, t
    return best_t, scores


def count_peaks(gray, mask, tilt, prom=0.08, dist=6):
    der = ndi_rotate(gray, tilt, reshape=False, order=1, mode="reflect")
    mder = ndi_rotate(mask.astype(np.float32), tilt, reshape=False, order=1) > 0.5
    bp = mm.bandpass_image(der)
    out = {}
    for axis, nm in [(0, "col"), (1, "row")]:
        sig, L = long_line(bp, mder, axis)
        pk = find_peaks(sig / max(sig.max(), 1), distance=dist, prominence=prom)[0] if sig.max() > 0 else np.array([])
        out[nm] = (len(pk), L, pk.tolist())
    return out


path = ra.SWEEPS["sweep1_M0.385"][0]
gray, ds, _ = mm.load_gray_downscaled(path)
wafer, _ = ra.wafer_mask(gray)
t, scores = tilt_search(gray, wafer)
print(f"tilt-search best = {t:+.2f} deg  (true +4.77)")
top = sorted(scores, key=lambda s: -s[1])[:5]
print("  top tilts:", [(round(tt, 1), int(ss)) for tt, ss in top])
for prom in (0.10, 0.07, 0.05):
    r = count_peaks(gray, wafer, t, prom=prom)
    print(f"  prom={prom}: cols={r['col'][0]} (L={r['col'][1]}), rows={r['row'][0]} (L={r['row'][1]})  "
          f"col_x={r['col'][2]}  row_y={r['row'][2]}")
