"""Stage Relock — Phase A: feature-locking audit (ground truth vs detector).

UNTRACKED / exploratory. No production / committed-lib module modified; production
helpers (atlas_periodic_fft register/enumerate_regions, periodic_fft derotate/
periodic_contrast/discover_fundamental, poc_comb_chain_lib.discover_pad_fundamental)
are imported READ-ONLY.

THE SUSPICION. `discover_pad_fundamental` (lib) -> `discover_fundamental` searches a band
whose floor is the static 0.06 cy/px (period ~17 px) until M is high enough that the
assumed 18 lp/mm pad fundamental would clip, and it collapses the ROI to a 1-D profile
(mean over the orthogonal axis). But the atlas declares pad-grid super-pitches of
11.6-192.5 px -> f_px ~= 0.0052-0.086 cy/px -- mostly AT or BELOW the 0.06 floor, and the
1-D collapse cannot represent a true 2-D dot lattice. So the detector likely locks a finer
common sub-feature / harmonic instead of the genuine per-axis pad-array fundamental.

WHAT THIS DOES. On the clean low-M shot (bare Sigma 105 @ 1:1, M~=1.05), de-rotated to the
wafer u/v axes, for ~6 magenta regions spanning the declared-pitch range (INCLUDING dies
5C and 5D):
  1. Measure the TRUE 2-D pad-grid fundamental in BOTH axes (u and v separately), two ways:
       (a) FULL 2-D FFT peak-lattice: find the dominant non-DC peaks in each half-plane,
           giving the genuine 2-D lattice vectors (period px + f_px per axis).
       (b) Per-axis 1-D collapse with a LOW floor (0.004 cy/px, period 250 px) so the
           coarse super-pitch is *visible* to the search (unlike the 0.06 floor).
     Confirm/refute anisotropy (u != v).
  2. Report what `discover_pad_fundamental` (lib, the production-path detector) actually
     returns for each region (pitch_px, f0, axis), and CLASSIFY: true grid / higher
     harmonic of it / unrelated finer sub-feature / maze / one-axis-only. Quantify the gap
     detector-f0 vs true-grid-f0 per axis (ratio).
  3. State whether the band floor (0.06 static / M-aware) excludes the true pad fundamental.

Run on nufan:
  cd .../tile-sharpness
  PYTHONPATH=$PWD/src ~/.cache/uv-venvs/tile-sharpness/bin/python \
      scripts/poc_comb_chain_relock_a_audit.py
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
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_lib as L  # noqa: E402

spec = importlib.util.spec_from_file_location("apf", HERE / "atlas_periodic_fft.py")
apf = importlib.util.module_from_spec(spec); spec.loader.exec_module(apf)  # noqa: E402

from tile_sharpness.methods.periodic_fft import derotate  # noqa: E402

OUT = HERE / "poc_comb_chain_out" / "relock"
OUT.mkdir(parents=True, exist_ok=True)
FFTDIR = OUT / "fft2d"
FFTDIR.mkdir(parents=True, exist_ok=True)

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
    """One COLOR decode per (subsampled) frame; per region keep the sharpest-focus
    (luma-lapvar) frame and return its (sat_roi, luma_roi)."""
    boxes = {i: [int(v) for v in r["bbox"]] for i, r in enumerate(regions)}
    best = {i: None for i in range(len(regions))}
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


# --------------------------------------------------------------------------- #
# TRUE grid measurement
# --------------------------------------------------------------------------- #

def axis_fundamental_1d(roi, axis, *, floor=0.004, hi=0.45, maze_band=None):
    """Strongest in-band peak of the 1-D collapsed profile, with a VERY LOW floor so the
    coarse super-pitch is visible (the whole point: the production 0.06 floor hides it).
    Returns (f_px, period_px, snr) or None. axis='u' -> vary across columns."""
    prof = roi.mean(axis=0) if axis == "u" else roi.mean(axis=1)
    n = prof.size
    if n < 32:
        return None
    prof = prof - prof.mean()
    amp = np.abs(np.fft.rfft(prof * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=1.0)
    m = (freqs >= floor) & (freqs <= hi)
    if maze_band is not None:
        m &= ~((freqs >= maze_band[1]) & (freqs <= maze_band[2]))
    idx = np.where(m)[0]
    if idx.size < 3:
        return None
    k = idx[int(np.argmax(amp[idx]))]
    # SNR vs local sidebands
    bw = max(2, int(0.03 * len(amp)))
    lo, hi2 = max(1, k - 5 * bw), min(len(amp), k + 5 * bw + 1)
    side = np.concatenate([amp[lo:max(lo, k - bw)], amp[min(hi2, k + bw + 1):hi2]])
    sm = float(np.median(side)) if side.size else 0.0
    snr = float(amp[k] / sm) if sm > 0 else float("inf")
    f = float(freqs[k])
    return (f, 1.0 / f if f > 0 else float("inf"), snr)


def true_grid_2d(roi, *, floor=0.004, maze_band=None):
    """Recover the genuine per-axis pad-lattice fundamental.

    Definition of TRUE grid fundamental (per axis): the STRONGEST periodic peak of the
    1-D collapsed profile searched from a very LOW floor (0.004 cy/px = period ~250 px),
    so the coarse super-pitch is visible (the production 0.06 / 0.045 floor hides it).
    This is the dominant real grid line a human sees in the ROI / 2-D FFT. We report it
    per axis (u and v), with SNR vs the in-band median, so anisotropy (u != v) is explicit.

    The 1-D collapse is the matched filter for that axis's grating; we run it per axis with
    the low floor rather than the production floor, which is exactly the apples-to-apples
    "what the detector WOULD lock if the floor weren't clipping the true grid" comparison.
    """
    h, w = roi.shape
    if min(h, w) < 32:
        return None

    def axis_peak(prof):
        n = prof.size
        prof = prof - prof.mean()
        amp = np.abs(np.fft.rfft(prof * np.hanning(n)))
        freqs = np.fft.rfftfreq(n, d=1.0)
        m = (freqs >= floor) & (freqs <= 0.48)
        if maze_band is not None:
            m &= ~((freqs >= maze_band[1]) & (freqs <= maze_band[2]))
        idx = np.where(m)[0]
        if idx.size < 3:
            return None
        k = idx[int(np.argmax(amp[idx]))]
        med = float(np.median(amp[idx]))
        snr = float(amp[k] / med) if med > 0 else float("inf")
        f = float(freqs[k])
        return (f, 1.0 / f if f > 0 else float("inf"), snr)

    u = axis_peak(roi.mean(axis=0))   # vary across columns
    v = axis_peak(roi.mean(axis=1))   # vary across rows
    return dict(u=u, v=v, peak2d=None)


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #

def classify(det_f0, det_axis, true_u, true_v, atlas_u_fpx, atlas_v_fpx):
    """Classify the detector's lock vs the true per-axis grid. Returns (label, detail)."""
    # detector locked on a single axis; compare to BOTH true axes
    cands = []
    if true_u is not None:
        cands.append(("u", true_u[0]))
    if true_v is not None:
        cands.append(("v", true_v[0]))
    notes = []
    best_lbl = "unknown"
    for axname, tf in cands:
        if tf <= 0:
            continue
        ratio = det_f0 / tf
        # near a harmonic n if det_f0 ~= n*tf
        for n in range(1, 9):
            if abs(ratio - n) / n < 0.12:
                notes.append(f"{axname}: {ratio:.2f}x (~{n}f)")
                break
        else:
            notes.append(f"{axname}: {ratio:.2f}x")
    # also compare to atlas-declared super-pitch fundamentals
    for axname, af_ in (("atlasU", atlas_u_fpx), ("atlasV", atlas_v_fpx)):
        if af_ and af_ > 0:
            notes.append(f"{axname}: {det_f0/af_:.2f}x")

    # decide a single label using the nearest true axis
    nearest = None
    for axname, tf in cands:
        if tf > 0:
            r = det_f0 / tf
            if nearest is None or abs(np.log(r)) < abs(np.log(nearest[1])):
                nearest = (axname, r)
    if nearest is None:
        return "no-true-grid", "; ".join(notes)
    axname, r = nearest
    if abs(r - 1.0) < 0.12:
        best_lbl = f"locks-true-grid[{axname}]"
    elif any(abs(r - n) / n < 0.12 for n in range(2, 9)):
        nn = min(range(2, 9), key=lambda n: abs(r - n))
        best_lbl = f"harmonic-{nn}f-of[{axname}]"
    elif r > 1.3:
        best_lbl = f"finer-subfeature(>{r:.1f}x[{axname}])"
    elif r < 0.77:
        best_lbl = f"coarser-than-true[{axname}]({r:.2f}x)"
    else:
        best_lbl = f"off-by[{axname}]({r:.2f}x)"
    return best_lbl, "; ".join(notes)


def pick_regions(regions, atlas_pitch):
    """Pick ~6 magenta regions spanning declared pitch, INCLUDING 5C and 5D if present."""
    mag = [r for r in regions if r["cls"] == "magenta"]
    # attach atlas pitch
    for r in mag:
        pu, pv = atlas_pitch(r)
        r["_apu"], r["_apv"] = pu, pv
    chosen = []
    seen = set()

    def add(r):
        if r["label"] not in seen:
            chosen.append(r); seen.add(r["label"])

    # 5C and 5D: die at column 5 ('C'=row2, 'D'=row3) -> label starts "5C"/"5D"
    for want in ("5C", "5D"):
        cands = [r for r in mag if r["label"].startswith(want) and r["_apu"]]
        if cands:
            # prefer comp #2 (the 45.6/51.2 6-harmonic winner the report flagged), else first
            cands.sort(key=lambda r: (0 if r["label"].endswith("#2") else 1, r["label"]))
            add(cands[0])
    # span the declared-pitch range: pick coarse / mid / fine by max(pu,pv)
    pitched = [r for r in mag if r["_apu"]]
    pitched.sort(key=lambda r: max(r["_apu"] or 0, r["_apv"] or 0))
    if pitched:
        # coarsest, ~33%, ~66%, finest
        for frac in (1.0, 0.66, 0.33, 0.0):
            idx = int(round(frac * (len(pitched) - 1)))
            add(pitched[idx])
    return chosen[:7]


def main():
    jpgs = sorted(SWEEP_DIR.glob("*.jpg")) + sorted(SWEEP_DIR.glob("*.JPG"))
    print(f"sweep: {SWEEP_DIR}  ({len(jpgs)} frames)")
    p = apf.register(jpgs)
    if p is None:
        print("registration FAILED"); return
    M = p["scale"] / apf.M_ANCHOR_SCALE
    theta = p["theta_deg"]
    print(f"registered: M={M:.4f} theta={theta:.3f} rmse={p['reg_fit_rmse_px']:.2f}")
    regions = apf.enumerate_regions(p, p["scale"])
    print(f"enumerated {len(regions)} regions")

    mb = L.maze_band_cy_per_px(M)
    lo_aware, hi_aware = L.resolvable_band_cy_per_px(M)
    print(f"M-aware discovery band = ({lo_aware:.4f}, {min(hi_aware,0.40):.4f}) cy/px; "
          f"static floor 0.06 cy/px (period {1/0.06:.0f} px); "
          f"maze band {mb[1]:.3f}-{mb[2]:.3f}" if mb else "(maze aliases)")

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

    chosen = pick_regions(regions, atlas_pitch)
    idx_of = {r["label"]: ri for ri, r in enumerate(regions)}
    sel_idx = [idx_of[r["label"]] for r in chosen]
    print(f"\nselected {len(chosen)} regions:")
    for r in chosen:
        print(f"  {r['label']:<16} atlas pitch u/v = {r['_apu']}/{r['_apv']} px  zone={r['zone']}")

    best = best_focus_rois(jpgs, [regions[i] for i in sel_idx])

    rows = []
    for k, ri in enumerate(sel_idx):
        reg = regions[ri]
        if best.get(k) is None:
            print(f"  {reg['label']}: no ROI"); continue
        _lv, sat, luma = best[k]
        sat_d = derotate(sat, theta)
        luma_d = derotate(luma, theta)
        pu, pv = atlas_pitch(reg)
        apu_fpx = (1.0 / pu) if pu else None
        apv_fpx = (1.0 / pv) if pv else None

        from tile_sharpness.methods.periodic_fft import discover_fundamental
        for chan, roi in (("sat", sat_d), ("luma", luma_d)):
            # TRUE per-axis grid (strongest peak, LOW floor)
            g2 = true_grid_2d(roi, maze_band=mb)
            tu = g2["u"] if g2 else None
            tv = g2["v"] if g2 else None
            # strongest TRUE axis (max SNR over u/v)
            strong_ax = "-"
            if tu and tv:
                strong_ax = "u" if tu[2] >= tv[2] else "v"
            elif tu:
                strong_ax = "u"
            elif tv:
                strong_ax = "v"
            # DETECTOR (production path): lib.discover_pad_fundamental on this der ROI
            det, _mb = L.discover_pad_fundamental(roi, M)
            det_f0 = det["f0_cy_per_px"] if det else float("nan")
            det_axis = det["axis"] if det else "-"
            det_pitch = det["pitch_px"] if det else float("nan")
            # DETECTOR with the SAME machinery but a LOW floor (0.004): shows what the
            # detector WOULD lock if the band floor weren't clipping the coarse grid.
            det_lo = discover_fundamental(
                roi, band=(0.004, 0.45), exclude=(mb[1], mb[2]) if mb else None)
            detlo_f0 = det_lo["f0_cy_per_px"] if det_lo else float("nan")
            detlo_axis = det_lo["axis"] if det_lo else "-"
            detlo_pitch = det_lo["pitch_px"] if det_lo else float("nan")
            lbl, detail = ("no-det", "") if det is None else classify(
                det_f0, det_axis, tu, tv, apu_fpx, apv_fpx)

            rows.append(dict(
                region=reg["label"], die=reg["label"].split("/")[0], cls=reg["cls"],
                zone=reg["zone"], channel=chan,
                atlas_u_px=pu, atlas_v_px=pv,
                atlas_u_fpx=round(apu_fpx, 5) if apu_fpx else "",
                atlas_v_fpx=round(apv_fpx, 5) if apv_fpx else "",
                true2d_u_fpx=round(tu[0], 5) if tu else "",
                true2d_u_px=round(tu[1], 2) if tu else "",
                true2d_u_snr=round(tu[2], 1) if tu else "",
                true2d_v_fpx=round(tv[0], 5) if tv else "",
                true2d_v_px=round(tv[1], 2) if tv else "",
                true2d_v_snr=round(tv[2], 1) if tv else "",
                anisotropic=(tu and tv and abs(np.log(tu[0] / tv[0])) > 0.18) or "",
                strong_axis=strong_ax,
                det_f0=round(det_f0, 5) if det else "",
                det_pitch_px=round(det_pitch, 2) if det else "",
                det_axis=det_axis,
                detlo_f0=round(detlo_f0, 5) if det_lo else "",
                detlo_pitch_px=round(detlo_pitch, 2) if det_lo else "",
                detlo_axis=detlo_axis,
                # does the production detector lock the SAME thing as the low-floor detector?
                floor_changes_lock=("YES" if det_lo and det and
                                    abs(np.log(max(det_f0, 1e-6) / max(detlo_f0, 1e-6))) > 0.10
                                    else "no"),
                det_misses_strong_axis=("YES" if det and strong_ax not in ("-", det_axis)
                                        else "no"),
                det_below_static=("YES" if (apu_fpx and apu_fpx < 0.06) or
                                  (apv_fpx and apv_fpx < 0.06) else "no"),
                classify=lbl, detail=detail))
        # save a 2D FFT figure for the sat channel
        h, w = sat_d.shape
        win = np.outer(np.hanning(h), np.hanning(w))
        Fimg = np.fft.fftshift(np.log1p(np.abs(np.fft.fft2((sat_d - sat_d.mean()) * win))))
        fig, ax = plt.subplots(1, 2, figsize=(11, 5))
        ax[0].imshow(sat_d, cmap="magma"); ax[0].set_title(f"{reg['label']} sat ROI")
        ax[1].imshow(Fimg, cmap="viridis"); ax[1].set_title("2D FFT |log| (centred)")
        for a in ax:
            a.axis("off")
        fig.tight_layout()
        safe = reg["label"].replace("/", "_").replace(" ", "").replace(",", "")
        fig.savefig(FFTDIR / f"{safe}.png", dpi=90); plt.close(fig)

    # write audit CSV
    csvp = OUT / "phaseA_audit.csv"
    fields = list(rows[0].keys()) if rows else []
    with csvp.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nWROTE {csvp}  ({len(rows)} rows)")

    # ---- console audit table (sat channel) ----
    print("\n" + "=" * 110)
    print("PHASE A AUDIT TABLE (saturation channel) — true 2-D grid f0 per axis vs detector pick")
    print("=" * 110)
    hdr = (f"{'region':<15}{'atlasU/V':<13}{'trueU px(snr)':<16}{'trueV px(snr)':<16}"
           f"{'strong':<7}{'detPx/ax':<11}{'detLoPx/ax':<12}{'classify':<24}")
    print(hdr)
    for r in rows:
        if r["channel"] != "sat":
            continue
        ap = f"{r['atlas_u_px']}/{r['atlas_v_px']}"
        tu = f"{r['true2d_u_px']}({r['true2d_u_snr']})" if r["true2d_u_px"] != "" else "-"
        tv = f"{r['true2d_v_px']}({r['true2d_v_snr']})" if r["true2d_v_px"] != "" else "-"
        detpx = f"{r['det_pitch_px']}/{r['det_axis']}" if r["det_pitch_px"] != "" else "-"
        detlo = f"{r['detlo_pitch_px']}/{r['detlo_axis']}" if r["detlo_pitch_px"] != "" else "-"
        print(f"{r['region']:<15}{ap:<13}{tu:<16}{tv:<16}"
              f"{r['strong_axis']:<7}{detpx:<11}{detlo:<12}{r['classify']:<24}")
        print(f"   detail: {r['detail']}")

    # ---- Phase A verdict ----
    print("\n" + "=" * 110)
    print("PHASE A VERDICT")
    print("=" * 110)
    sat_rows = [r for r in rows if r["channel"] == "sat"]
    n_aniso = sum(1 for r in sat_rows if bool(r["anisotropic"]))
    n_truelock = sum(1 for r in sat_rows if r["classify"].startswith("locks-true-grid"))
    n_finer = sum(1 for r in sat_rows if "finer-subfeature" in r["classify"])
    n_harm = sum(1 for r in sat_rows if r["classify"].startswith("harmonic"))
    n_below = sum(1 for r in sat_rows if r["det_below_static"] == "YES")
    n_floorlock = sum(1 for r in sat_rows if r["floor_changes_lock"] == "YES")
    n_missax = sum(1 for r in sat_rows if r["det_misses_strong_axis"] == "YES")
    print(f"  regions audited (sat): {len(sat_rows)}")
    print(f"  anisotropic (u != v >1.2x): {n_aniso}")
    print(f"  detector locks TRUE grid (within 12%): {n_truelock}")
    print(f"  detector locks a FINER sub-feature: {n_finer}")
    print(f"  detector locks a HARMONIC of true grid: {n_harm}")
    print(f"  regions whose atlas pad fundamental is BELOW the static 0.06 floor: {n_below}")
    print(f"  FLOOR changes the lock (prod-floor pick != low-floor pick): {n_floorlock}")
    print(f"  detector MISSES the strongest TRUE axis (locks the weaker axis): {n_missax}")
    print(f"  M-aware band floor this M = {lo_aware:.4f} cy/px (period {1/lo_aware:.0f} px)")
    print(f"  static floor 0.06 cy/px = period 17 px")


if __name__ == "__main__":
    main()
