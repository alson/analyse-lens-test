"""Stage Targets — Phase 1: 2D-FFT cleanliness survey of EVERY structured wafer target.

UNTRACKED / exploratory. No production or committed-lib module is modified; production
helpers (atlas_periodic_fft register/enumerate_regions, periodic_fft derotate) are
imported read-only.

WHY. The cross-M "not viable" verdict (poc_comb_chain_REPORT.md, Stage T_n) rested on
ONE dominant magenta pad pattern (magenta.P11) + the maze, whose harmonic content was
texture/specular-UNSTABLE across configs (self-cal collapse residual 0.79 vs a 0.38
within-config floor). The instability is plausibly PAD-SPECIFIC. This phase surveys the
FULL catalogue of candidate periodic/structured regions on ONE clean low-M shot (bare
Sigma 105 @ 1:1, best focus) with a full 2D FFT (not the 1D collapse discover_fundamental
does), to find which targets are cleanest / most multi-harmonic before committing the
expensive multi-M extraction (Phase 2) to only the promising ones.

WHAT it does per region (magenta bond-pads, cyan experimental, cyan_se slanted-edge):
  1. register the sweep (reg_auto), enumerate regions, crop the best-focus ROI,
     derotate to the wafer u/v axes (theta from registration).
  2. decode the SATURATION channel (specular-suppressed; diag-2 winner) AND luma.
  3. run a FULL 2D rFFT on the Hann-windowed ROI. Collapse to a 1D u-profile-spectrum
     (mean over rows -> FFT along columns) and a 1D v-profile-spectrum, AND a 2D
     magnitude image. For each axis find the fundamental + harmonic peaks in the
     resolvable band, with peak SNR (peak / local sideband median).
  4. also seed from the atlas pad_pitch_px (u and v) for that region: the atlas declares
     the SUPER-element pitch; the sub-element fundamental we want is discovered, but the
     atlas pitch tells us the structure class + whether u/v are distinct pitches.
  5. emit one row per (region, axis) with: cls, die-type, atlas pitch u/v, discovered
     fundamental (cy/px + subj lp/mm at M), #clean harmonics (peaks at n*f0 with SNR>=3
     below Nyquist), best-harmonic SNR, and a "clean periodic comb?" verdict.
  6. save 2D-FFT magnitude PNGs for the notable regions.

Run on nufan:
  PYTHONPATH=<src> ~/.cache/uv-venvs/tile-sharpness/bin/python \
      scripts/poc_comb_chain_targets_phase1.py
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_lib as L  # noqa: E402

spec = importlib.util.spec_from_file_location("apf", HERE / "atlas_periodic_fft.py")
apf = importlib.util.module_from_spec(spec); spec.loader.exec_module(apf)  # noqa: E402

from tile_sharpness.methods.periodic_fft import derotate  # noqa: E402

OUT = HERE / "poc_comb_chain_out" / "targets"
OUT.mkdir(parents=True, exist_ok=True)
FFTDIR = OUT / "fft2d"
FFTDIR.mkdir(parents=True, exist_ok=True)

# Bare Sigma 105 @ 1:1 F8 — the clean low-M reference shot from the subset.
SWEEP_DIR = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
    "Sigma Macro 105mm F2.8 EX DG OS HSM/1_1/F8"
)
N_MARKED = 8.0
NYQ = L.NYQUIST


def sat_of(bgr):
    b = bgr[:, :, 0].astype(np.float64)
    g = bgr[:, :, 1].astype(np.float64)
    r = bgr[:, :, 2].astype(np.float64)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    return np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 0) * 255.0


def best_focus_rois(jpgs, regions):
    """One COLOR decode per frame; for EACH region keep the sharpest-focus (luma-lapvar)
    frame and return its (sat_roi, luma_roi). O(frames) decodes, not O(frames*regions)."""
    boxes = {i: [int(v) for v in r["bbox"]] for i, r in enumerate(regions)}
    best = {i: None for i in range(len(regions))}   # i -> (lv, sat, luma)
    # Best-focus plateau is wide; subsample frames to ~40 to cut decode cost.
    step = max(1, len(jpgs) // 40)
    for jp in jpgs[::step]:
        bgr = cv2.imread(str(jp), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        for i, (x0, y0, x1, y1) in boxes.items():
            sub = bgr[y0:y1, x0:x1]
            if sub.size == 0 or min(sub.shape[:2]) < 24:
                continue
            gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
            lv = float(cv2.Laplacian(gray.astype(np.float32), cv2.CV_32F).var())
            if best[i] is None or lv > best[i][0]:
                best[i] = (lv, sat_of(sub), gray.astype(np.float64))
    return best


def axis_spectrum(roi, axis):
    """1D collapsed spectrum along an axis. axis='u' -> stripes vary across columns
    (average rows, FFT columns); axis='v' -> vary across rows. Returns (freqs, amp)."""
    prof = roi.mean(axis=0) if axis == "u" else roi.mean(axis=1)
    n = prof.size
    if n < 32:
        return None, None
    prof = prof - prof.mean()
    amp = np.abs(np.fft.rfft(prof * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=1.0)
    return freqs, amp


def find_fundamental_and_harmonics(freqs, amp, M, *, band=(0.04, 0.45),
                                   maze_band=None, snr_min=3.0, max_order=7):
    """In the resolvable band, find the strongest peak as the fundamental, then look for
    harmonics at n*f0. Returns dict(f0, n_clean_harmonics, peak_snr, harm_snrs) or None.

    SNR of a peak = amp[peak] / median(local sidebands excluding the peak neighbourhood).
    """
    if freqs is None:
        return None
    m = (freqs >= band[0]) & (freqs <= band[1])
    if maze_band is not None:
        m &= ~((freqs >= maze_band[1]) & (freqs <= maze_band[2]))
    idx = np.where(m)[0]
    if idx.size < 4:
        return None

    def peak_snr(k):
        bw = max(2, int(0.04 * len(amp)))
        lo, hi = max(1, k - 5 * bw), min(len(amp), k + 5 * bw + 1)
        side = np.concatenate([amp[lo:max(lo, k - bw)], amp[min(hi, k + bw + 1):hi]])
        sm = float(np.median(side)) if side.size else 0.0
        return float(amp[k] / sm) if sm > 0 else float("inf")

    # fundamental = strongest in-band peak
    kf = idx[int(np.argmax(amp[idx]))]
    f0 = float(freqs[kf])
    if f0 <= 0:
        return None
    fund_snr = peak_snr(kf)
    # harmonics at n*f0
    df = freqs[1] - freqs[0]
    harm = []
    for n in range(1, max_order + 1):
        ftarget = n * f0
        if ftarget >= NYQ - 1e-3:
            break
        ktarget = int(round(ftarget / df))
        # local max within +-1 bin to absorb scale slop
        lo, hi = max(1, ktarget - 1), min(len(amp), ktarget + 2)
        kk = lo + int(np.argmax(amp[lo:hi]))
        s = peak_snr(kk)
        harm.append((n, float(freqs[kk]), s))
    n_clean = sum(1 for (_, _, s) in harm if s >= snr_min)
    peak_snr_best = max((s for (_, _, s) in harm), default=0.0)
    return dict(f0=f0, fund_snr=fund_snr, harm=harm, n_clean=n_clean,
                peak_snr=peak_snr_best, f0_subj=L.px_to_subj(f0, M))


def fft2d_mag(roi):
    """Hann-windowed centred 2D FFT log-magnitude for visualisation."""
    h, w = roi.shape
    win = np.outer(np.hanning(h), np.hanning(w))
    F = np.fft.fftshift(np.fft.fft2((roi - roi.mean()) * win))
    return np.log1p(np.abs(F))


def main():
    jpgs = sorted(SWEEP_DIR.glob("*.jpg")) + sorted(SWEEP_DIR.glob("*.JPG"))
    print(f"sweep: {SWEEP_DIR}  ({len(jpgs)} frames)")
    p = apf.register(jpgs)
    if p is None:
        print("registration FAILED"); return
    M = p["scale"] / apf.M_ANCHOR_SCALE
    theta = p["theta_deg"]
    print(f"registered: M={M:.3f} theta={theta:.3f} rmse={p['reg_fit_rmse_px']:.2f}")
    regions = apf.enumerate_regions(p, p["scale"])
    print(f"enumerated {len(regions)} regions "
          f"(magenta={sum(r['cls']=='magenta' for r in regions)}, "
          f"cyan={sum(r['cls']=='cyan' for r in regions)}, "
          f"cyan_se={sum(r['cls']=='cyan_se' for r in regions)})")

    mb = L.maze_band_cy_per_px(M)

    # atlas pad_pitch lookup per (die-type, comp index) so we can label the structure.
    def atlas_pitch(region):
        typ = region["type"]; bi = region["comp"]; cls = region["cls"]
        fi = apf.ATLAS["die_types"].get(typ, {}).get("feature_inventory", {})
        key = {"magenta": "bond_pads", "cyan": "experimental",
               "cyan_se": "slanted_edge"}[cls]
        lst = fi.get(key, [])
        if bi < len(lst):
            pp = lst[bi].get("pad_pitch_px")
            if pp:
                return pp.get("pitch_u_px"), pp.get("pitch_v_px")
        return None, None

    best = best_focus_rois(jpgs, regions)

    rows = []
    notable = []
    for ri, reg in enumerate(regions):
        if best.get(ri) is None:
            continue
        _, sat, luma = best[ri]
        sat_d = derotate(sat, theta)
        luma_d = derotate(luma, theta)
        pu, pv = atlas_pitch(reg)
        for axis in ("u", "v"):
            for chan_name, roi in (("sat", sat_d), ("luma", luma_d)):
                freqs, amp = axis_spectrum(roi, axis)
                res = find_fundamental_and_harmonics(freqs, amp, M, maze_band=mb)
                if res is None:
                    continue
                # "clean periodic comb?" verdict heuristic:
                #   >=2 harmonics with SNR>=3 AND fundamental SNR>=5
                comb = (res["n_clean"] >= 2 and res["fund_snr"] >= 5.0)
                rows.append(dict(
                    region=reg["label"], die_type=reg["type"], cls=reg["cls"],
                    zone=reg["zone"], axis=axis, channel=chan_name,
                    atlas_pitch_u=pu, atlas_pitch_v=pv,
                    f0_cypx=round(res["f0"], 4),
                    f0_subj_lpmm=round(res["f0_subj"], 2),
                    fund_snr=round(res["fund_snr"], 2),
                    n_clean_harmonics=res["n_clean"],
                    best_harm_snr=round(res["peak_snr"], 2),
                    comb=comb,
                    harm_snrs="|".join(f"{n}:{s:.1f}" for n, _, s in res["harm"])))
        # collect notable on sat channel (best comb across axes)
        sat_rows = [r for r in rows if r["region"] == reg["label"] and r["channel"] == "sat"]
        if sat_rows:
            bestrow = max(sat_rows, key=lambda r: r["n_clean_harmonics"])
            notable.append((bestrow["n_clean_harmonics"], bestrow["fund_snr"], reg, sat_d))

    # write the full survey table
    csvp = OUT / "phase1_survey.csv"
    fields = ["region", "die_type", "cls", "zone", "axis", "channel",
              "atlas_pitch_u", "atlas_pitch_v", "f0_cypx", "f0_subj_lpmm",
              "fund_snr", "n_clean_harmonics", "best_harm_snr", "comb", "harm_snrs"]
    with csvp.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nWROTE {csvp}  ({len(rows)} region-axis-channel rows)")

    # save 2D FFT PNGs for the top notable regions (sat channel)
    notable.sort(key=lambda t: (t[0], t[1]), reverse=True)
    seen = set()
    saved = 0
    for nclean, fsnr, reg, sat_d in notable:
        if reg["label"] in seen:
            continue
        seen.add(reg["label"])
        if saved >= 16:
            break
        mag = fft2d_mag(sat_d)
        fig, ax = plt.subplots(1, 2, figsize=(10, 5))
        ax[0].imshow(sat_d, cmap="magma"); ax[0].set_title(f"{reg['label']} sat ROI")
        ax[1].imshow(mag, cmap="viridis"); ax[1].set_title(
            f"2D FFT |log| (n_clean={nclean}, fundSNR={fsnr:.1f})")
        for a in ax:
            a.axis("off")
        fig.tight_layout()
        safe = reg["label"].replace("/", "_").replace(" ", "").replace(",", "")
        fig.savefig(FFTDIR / f"{reg['cls']}_{safe}.png", dpi=90)
        plt.close(fig)
        saved += 1
    print(f"WROTE {saved} 2D-FFT PNGs to {FFTDIR}")

    # ranked summary by cls+atlas-pitch class (sat channel only)
    print("\n" + "=" * 78)
    print("RANKED SUMMARY (saturation channel) — by (cls, die-type, comp)")
    print("=" * 78)
    sat = [r for r in rows if r["channel"] == "sat"]
    # group by region, keep best axis
    byreg = defaultdict(list)
    for r in sat:
        byreg[(r["cls"], r["region"])].append(r)
    summary = []
    for (cls, region), rs in byreg.items():
        best = max(rs, key=lambda r: (r["n_clean_harmonics"], r["fund_snr"]))
        summary.append(best)
    summary.sort(key=lambda r: (r["n_clean_harmonics"], r["fund_snr"]), reverse=True)
    print(f"{'region':<16}{'cls':<8}{'atlasU/V':<14}{'axis':<5}"
          f"{'f0(cy/px)':<10}{'f0_subj':<9}{'fSNR':<7}{'#harm':<6}{'comb':<5}")
    for r in summary:
        ap = f"{r['atlas_pitch_u']}/{r['atlas_pitch_v']}"
        print(f"{r['region']:<16}{r['cls']:<8}{ap:<14}{r['axis']:<5}"
              f"{r['f0_cypx']:<10.4f}{r['f0_subj_lpmm']:<9.1f}{r['fund_snr']:<7.1f}"
              f"{r['n_clean_harmonics']:<6}{'Y' if r['comb'] else '-':<5}")


if __name__ == "__main__":
    main()
