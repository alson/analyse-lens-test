"""Bounded RAW-vs-JPEG MTF50 diagnostic (one lens aperture series).

Tests whether the cross-config ranking's subject-MTF50 over-reads the diffraction
ceiling because it is measured on 8-bit in-camera JPEGs (sharpening + near-Nyquist
quantisation + gamma). For one lens at several apertures it measures scribe-LSF
MTF50 at the SAME wafer scribes three ways:

  * jpg      — 8-bit gamma-encoded grey (what the pipeline does);
  * jpg_lin  — the same JPEG, sRGB-linearised (isolates gamma);
  * raw      — the matching NEF decoded linear/unsharpened via dcraw (green),
               i.e. no sharpening, no 8-bit JPEG quantisation, no gamma.

Scribe placement is ATLAS-ANCHORED (wafer-atlas reg_auto): we register the sweep
once and read MTF50 at fixed grid-line scribes — DETERMINISTIC (no probabilistic
Hough) and robust on low-contrast linear RAW (no blind detection needed). The
wafer is on a fixed mount and the rail moves only axially, so one affine applies
to every shot/aperture. Compared against the diffraction ceiling
(optics.diffraction_mtf50_subject_lpmm). If `raw` respects the ceiling and falls
monotonically with stopping down while `jpg` does not, JPEG processing is the
inflation source. dcraw must be on PATH (present on nufan). Run on nufan.

FINDING (2026-06-27, AF200 1:1, 10 atlas-anchored central scribes):
  * At f/8 (sharp, good contrast) jpg/jpg_lin/raw roughly agree and sit near the
    ceiling; at f/11 and f/16 ALL THREE over-read it (raw up to 2.2x). RAW is NOT
    systematically lower than JPEG.
  * Scribe-to-scribe spread is huge (IQR ±10-26 lp/mm on medians of 30-50).
  => The over-read is NOT a JPEG/input-format artifact (RAW over-reads too); it is
  a MEASUREMENT-METHODOLOGY problem: the slanted-edge LSF-MTF50 inflates on
  low-contrast (diffraction-blurred) edges and has large edge-to-edge variance
  (field-tilt focus differences + scribe quality + super-resolution noise).
  Switching to RAW will not fix the inflated ranking. Lean on the diffraction
  ceiling (physics + atlas-measured M) for diffraction-limited configs; trust the
  measured MTF50 only where it is comfortably below the ceiling (glass-limited).
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tile_sharpness.methods.lsf import Segment, cross_section, lsf_mtf50
from tile_sharpness.optics import diffraction_mtf50_subject_lpmm, effective_fnumber

RAW_DIR = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
JPG_BASE = RAW_DIR / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1"
APERTURES = ["F8", "F11", "F16"]
M = 1.0
LPMM_PER_CYPX = 1000.0 / 4.35
HALF_WIN, SPP = 28, 4.0
IMAGE_W, IMAGE_H = 8256, 5504

# wafer-atlas reg_auto (autonomous registration + grid_xy_distorted)
_WA = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/"
           "wafer-atlas/scripts")
_spec = importlib.util.spec_from_file_location("reg_auto", _WA / "reg_auto.py")
reg_auto = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reg_auto)


def srgb_to_linear(g8):
    v = g8.astype(np.float32) / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def central_crop(img, side=1600):
    h, w = img.shape[:2]
    return img[h // 2 - side // 2:h // 2 + side // 2, w // 2 - side // 2:w // 2 + side // 2]


def best_focus_jpg(ap_dir):
    best, best_v = None, -1.0
    for jp in sorted(ap_dir.glob("*.jpg")):
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        v = cv2.Laplacian(central_crop(g).astype(np.float32), cv2.CV_32F).var()
        if v > best_v:
            best_v, best = v, jp
    return best


def find_nef(jpg):
    nef = RAW_DIR / (jpg.stem + ".nef")
    return nef if nef.exists() else None


def decode_raw_green(nef):
    """Linear 16-bit green channel via dcraw (-4 linear, -q 3 AHD, no sharpening)."""
    p = subprocess.run(["dcraw", "-4", "-T", "-q", "3", "-w", "-o", "1", "-c", str(nef)],
                       capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"dcraw failed: {p.stderr[:200]!r}")
    with tempfile.NamedTemporaryFile(suffix=".tiff", delete=False) as f:
        f.write(p.stdout)
        tmp = f.name
    try:
        img = cv2.imread(tmp, cv2.IMREAD_UNCHANGED)
    finally:
        os.unlink(tmp)
    if img is None:
        raise RuntimeError("could not read dcraw TIFF")
    return (img[..., 1] if img.ndim == 3 else img).astype(np.float32)


def _seg_ok(xa, ya, xb, yb):
    return (200 < xa < IMAGE_W - 200 and 200 < xb < IMAGE_W - 200
            and 200 < ya < IMAGE_H - 200 and 200 < yb < IMAGE_H - 200)


def central_scribes(affine, n=10, near_px=2200):
    """Up to n near-central grid-line scribes (both vertical col-lines and
    horizontal row-lines, each spanning one cell), tilted by the wafer rotation
    -> slanted edges. Deterministic from the affine; restricted near the frame
    centre so they share focus with the central-crop best shot."""
    cx, cy = IMAGE_W / 2, IMAGE_H / 2
    cands = []
    for cl in range(reg_auto.N_COL_LINES):          # vertical scribes
        for r0 in range(reg_auto.N_ROW_LINES - 1):
            xa, ya = reg_auto.grid_xy_distorted(cl, r0, affine)
            xb, yb = reg_auto.grid_xy_distorted(cl, r0 + 1, affine)
            if not _seg_ok(xa, ya, xb, yb):
                continue
            d = np.hypot((xa + xb) / 2 - cx, (ya + yb) / 2 - cy)
            if d < near_px:
                cands.append((d, Segment(x0=xa, y0=ya, x1=xb, y1=yb)))
    for rl in range(reg_auto.N_ROW_LINES):          # horizontal scribes
        for c0 in range(reg_auto.N_COL_LINES - 1):
            xa, ya = reg_auto.grid_xy_distorted(c0, rl, affine)
            xb, yb = reg_auto.grid_xy_distorted(c0 + 1, rl, affine)
            if not _seg_ok(xa, ya, xb, yb):
                continue
            d = np.hypot((xa + xb) / 2 - cx, (ya + yb) / 2 - cy)
            if d < near_px:
                cands.append((d, Segment(x0=xa, y0=ya, x1=xb, y1=yb)))
    cands.sort(key=lambda c: c[0])
    return [s for _, s in cands[:n]]


def mtf50_at(gray, scribes):
    """(median, IQR, n) scribe-LSF MTF50 (cy/px) over the fixed scribes; no detection."""
    vals = []
    for seg in scribes:
        prof = cross_section(gray.astype(np.float32), seg, half_window_px=HALF_WIN,
                             samples_per_pixel=SPP)
        m = lsf_mtf50(prof)
        if m:
            vals.append(m)
    if not vals:
        return None, None, 0
    a = np.array(vals)
    return float(np.median(a)), float(np.percentile(a, 75) - np.percentile(a, 25)), len(a)


def main():
    print(f"RAW-vs-JPEG MTF50 diagnostic — Nikon AF 200/4D @ 1:1 (M={M})")
    print("atlas-anchored scribes (deterministic); identical LSF on all inputs.\n")
    aff = reg_auto.register_and_refine("sweep2_M1.0")
    if aff is None:
        print("registration failed"); return 1
    scribes = central_scribes(aff)
    print(f"registered (fit {aff['reg_fit_rmse_px']:.2f}px); {len(scribes)} central scribes\n")

    print(f"{'ap':>4}{'Neff':>6}{'ceil':>7} | {'jpg':>6}{'hdrm':>6} | {'jpg_lin':>8}{'hdrm':>6} | "
          f"{'raw':>6}{'hdrm':>6}   (subject lp/mm)")
    rows = []
    for ap in APERTURES:
        jp = best_focus_jpg(JPG_BASE / ap)
        if jp is None:
            print(f"{ap:>4}  no jpgs"); continue
        nef = find_nef(jp)
        n = float(ap.lstrip("F"))
        n_eff, ceil = effective_fnumber(n, M), diffraction_mtf50_subject_lpmm(n, M)

        g8 = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        m_jpg, iqr_j, nj = mtf50_at(g8.astype(np.float32), scribes)
        m_lin, _, _ = mtf50_at(srgb_to_linear(g8), scribes)
        m_raw, iqr_r, nr = (mtf50_at(decode_raw_green(nef), scribes) if nef else (None, None, 0))

        lpmm = lambda m: (m * LPMM_PER_CYPX * M) if m else float("nan")
        hd = lambda m: (lpmm(m) / ceil) if (m and ceil > 0) else float("nan")
        iqrl = lambda i: (i * LPMM_PER_CYPX * M) if i else float("nan")
        print(f"{ap:>4}{n_eff:6.1f}{ceil:7.1f} | {lpmm(m_jpg):6.1f}{hd(m_jpg):6.2f} | "
              f"{lpmm(m_lin):8.1f}{hd(m_lin):6.2f} | {lpmm(m_raw):6.1f}{hd(m_raw):6.2f}"
              f"   n={nj}/{nr} IQR jpg±{iqrl(iqr_j):.0f} raw±{iqrl(iqr_r):.0f}"
              f"{'' if nef else '  [NO NEF]'}")
        rows.append((lpmm(m_jpg), lpmm(m_lin), lpmm(m_raw)))

    mono = lambda vs: all(a >= b for a, b in zip([v for v in vs if v == v],
                                                 [v for v in vs if v == v][1:]))
    print("\nmonotonic falloff f/8>=f/11>=f/16 (must hold optically):")
    for i, lbl in ((0, "jpg"), (1, "jpg_lin"), (2, "raw")):
        print(f"  {lbl:>8}: {'YES' if mono([r[i] for r in rows]) else 'NO (artifact)'}")


if __name__ == "__main__":
    sys.exit(main())
