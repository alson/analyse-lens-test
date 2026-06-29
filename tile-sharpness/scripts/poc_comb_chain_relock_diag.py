"""Stage Relock — diagnostic: dump the raw per-axis 1-D spectra (low floor) and the top
2-D FFT peaks for a few regions, so we can SEE what the true lattice is and whether the
detector's ~21 px lock is a real harmonic / sub-feature or an artifact.

UNTRACKED / read-only imports. Run on nufan.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_lib as L  # noqa: E402

spec = importlib.util.spec_from_file_location("apf", HERE / "atlas_periodic_fft.py")
apf = importlib.util.module_from_spec(spec); spec.loader.exec_module(apf)  # noqa: E402
from tile_sharpness.methods.periodic_fft import derotate  # noqa: E402

SWEEP_DIR = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
    "Sigma Macro 105mm F2.8 EX DG OS HSM/1_1/F8"
)
WANT = ["5D/(1, 3)#2", "5C/(1, 2)#2", "8C/(0, 2)#1"]


def sat_of(bgr):
    b, g, r = (bgr[:, :, i].astype(np.float64) for i in range(3))
    mx = np.maximum(np.maximum(r, g), b); mn = np.minimum(np.minimum(r, g), b)
    return np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 0) * 255.0


def best_focus(jpgs, box):
    x0, y0, x1, y1 = box
    best = None
    step = max(1, len(jpgs) // 40)
    for jp in jpgs[::step]:
        bgr = cv2.imread(str(jp), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        sub = bgr[y0:y1, x0:x1]
        if sub.size == 0:
            continue
        g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
        lv = float(cv2.Laplacian(g.astype(np.float32), cv2.CV_32F).var())
        if best is None or lv > best[0]:
            best = (lv, sat_of(sub))
    return best[1] if best else None


def topk_1d(prof, floor, k=8, maze_band=None):
    n = prof.size
    prof = prof - prof.mean()
    amp = np.abs(np.fft.rfft(prof * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=1.0)
    m = (freqs >= floor) & (freqs <= 0.48)
    if maze_band is not None:
        m &= ~((freqs >= maze_band[1]) & (freqs <= maze_band[2]))
    idx = np.where(m)[0]
    # local maxima
    peaks = [i for i in idx if 0 < i < len(amp) - 1 and amp[i] >= amp[i-1] and amp[i] >= amp[i+1]]
    peaks.sort(key=lambda i: -amp[i])
    out = []
    med = float(np.median(amp[idx])) if idx.size else 1.0
    for i in peaks[:k]:
        f = freqs[i]
        out.append((float(f), 1.0/f if f > 0 else 0, float(amp[i]/med)))
    return out


def main():
    jpgs = sorted(SWEEP_DIR.glob("*.jpg")) + sorted(SWEEP_DIR.glob("*.JPG"))
    p = apf.register(jpgs)
    M = p["scale"] / apf.M_ANCHOR_SCALE
    theta = p["theta_deg"]
    mb = L.maze_band_cy_per_px(M)
    print(f"M={M:.4f} theta={theta:.3f} maze_band={mb[1]:.3f}-{mb[2]:.3f}")
    regions = apf.enumerate_regions(p, p["scale"])
    by = {r["label"]: r for r in regions}
    for label in WANT:
        reg = by.get(label)
        if reg is None:
            print(f"{label}: not in FOV"); continue
        box = [int(v) for v in reg["bbox"]]
        sat = best_focus(jpgs, box)
        if sat is None:
            print(f"{label}: no ROI"); continue
        d = derotate(sat, theta)
        h, w = d.shape
        print(f"\n=== {label}  ROI {h}x{w}  zone={reg['zone']} ===")
        print(f"  atlas super-pitch u/v = (declared in audit)")
        # low-floor 1-D peaks (floor 0.004 = period 250 px)
        for axis, prof in (("u", d.mean(axis=0)), ("v", d.mean(axis=1))):
            pk = topk_1d(prof, 0.004, maze_band=mb)
            s = "  ".join(f"{px:.1f}px(f{f:.4f},snr{snr:.1f})" for f, px, snr in pk)
            print(f"  1D {axis}-axis top peaks (floor 0.004): {s}")
        # what the production detector returns
        det, _ = L.discover_pad_fundamental(d, M)
        if det:
            print(f"  DETECTOR: pitch={det['pitch_px']:.2f}px f0={det['f0_cy_per_px']:.4f} "
                  f"axis={det['axis']} (band floor {L.resolvable_band_cy_per_px(M)[0]:.4f})")
        # ALSO: what does it return with the SAME low floor (0.004)? does the coarse grid win?
        from tile_sharpness.methods.periodic_fft import discover_fundamental
        det_lo = discover_fundamental(d, band=(0.004, 0.45),
                                      exclude=(mb[1], mb[2]) if mb else None)
        if det_lo:
            print(f"  DETECTOR (low floor 0.004): pitch={det_lo['pitch_px']:.2f}px "
                  f"f0={det_lo['f0_cy_per_px']:.4f} axis={det_lo['axis']}")


if __name__ == "__main__":
    main()
