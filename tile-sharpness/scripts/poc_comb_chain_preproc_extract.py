"""Stage Preproc — cause-isolation: re-extract the per-axis re-anchored comb on the
SATURATION channel, but with optional LINEAR / MTF-PRESERVING pre-processing applied to
the de-rotated ROI before the FFT contrast read. The point of the POC is to add the
pre-processing steps ONE AT A TIME and watch the Stage-T_n collapse residual (and the
residual/within-config-floor RATIO) move, isolating WHICH measurement-induced source (if
any) drives the cross-M instability that Stages T_n / Targets / Relock left
inferred-but-unproven.

UNTRACKED / exploratory. Mirrors poc_comb_chain_relock_b_extract.py EXACTLY (same atlas
registration, per-axis LOW-FLOOR anchoring on the TRUE coarse grid — so we are NOT
re-contaminated by the mislocking bug Relock found — saturation channel, axis-locked
bounded-Michelson read, sharded runner) EXCEPT for the pre-processing controlled by env:

  PREPROC : comma-separated subset of {flat, phasewin, specmask, clip}, applied
            CUMULATIVELY in that canonical order (so the ablation is monotone). Empty =
            baseline (should reproduce ~the Relock 0.64 / ratio ~1.46).
              flat     -- flat-fielding: divide by a heavily low-passed copy (Gaussian,
                          sigma ~ several pad pitches). Removes the slow illumination /
                          field-brightness gradient. LINEAR per-pixel gain -> MTF-safe at
                          the comb frequencies (the low-pass kernel only touches DC-ish
                          spatial scales far below f0..7f0).
              specmask -- specular masking / robust read: detect saturated/outlier pixels
                          on the ACHROMATIC luma (speculars are achromatic; the sat channel
                          already suppresses them but residuals remain) and REPLACE them
                          with the local low-pass value (inpaint-by-blur) before the FFT.
                          Excludes outliers rather than thresholding the signal -> MTF-safe
                          on the unmasked structure.
              phasewin -- sub-pixel phase-aligned windowing: handled in the contrast read
                          (PHASEWIN=1) — crop each 1-D profile to an INTEGER number of
                          periods anchored on the grid phase before windowing, so window
                          scalloping / spectral leakage does not vary across configs.
              clip     -- NEGATIVE CONTROL (INVALID): hard intensity clip at p2/p98 then
                          rescale. NONLINEAR — destroys the MTF by compressing modulation;
                          included only to demonstrate it falsely "collapses". FLAGGED.

  FOCUS  : argmax (default; per-region best-focus, the Relock behaviour) | fixed
            (consistent cross-config focus criterion: pick the frame at the PEAK of the
            GLOBAL through-focus curve — one criterion for every config/region — instead
            of a per-region argmax that can land on different relative focus per config).

Each row mirrors relock_b_extract plus a `preproc` and `focus` column. Sharded like
relock_b_run.sh.

Usage (nufan):
  SHARD=0/8 PREPROC=flat FOCUS=argmax RANK_CONFIGS=subset.csv \
    RANK_OUT=out/preproc_flat_shard_0.csv \
    PYTHONPATH=<src> python scripts/poc_comb_chain_preproc_extract.py
"""
from __future__ import annotations

import csv
import importlib.util
import os
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_lib as L  # noqa: E402

spec = importlib.util.spec_from_file_location("apf", HERE / "atlas_periodic_fft.py")
apf = importlib.util.module_from_spec(spec); spec.loader.exec_module(apf)  # noqa: E402

from tile_sharpness.methods.periodic_fft import periodic_contrast, derotate  # noqa: E402
from tile_sharpness import optics  # noqa: E402

NYQ = L.NYQUIST
MAX_ORDER = 7
MAZE_HARMONICS = 4
LOW_FLOOR = 0.004   # period ~250 px; admits the genuine coarse pad grid (Relock anchor)

PREPROC = [s.strip() for s in os.environ.get("PREPROC", "").split(",") if s.strip()]
FOCUS = os.environ.get("FOCUS", "argmax").strip()
_KNOWN = {"flat", "phasewin", "specmask", "clip"}
for _s in PREPROC:
    if _s not in _KNOWN:
        raise SystemExit(f"unknown PREPROC step {_s!r}; known={_KNOWN}")
DO_FLAT = "flat" in PREPROC
DO_SPECMASK = "specmask" in PREPROC
DO_PHASEWIN = "phasewin" in PREPROC
DO_CLIP = "clip" in PREPROC


# --------------------------------------------------------------------------- #
# LINEAR / MTF-PRESERVING pre-processing on the de-rotated saturation ROI
# --------------------------------------------------------------------------- #

# Hard cap on the flat-field low-pass sigma. The illumination gradient is smooth over the
# whole ROI; we only need sigma large enough to sit well BELOW the comb fundamental (so
# f0..7f0 survive the division) but the kernel must stay small enough to be fast and to
# not span the entire ROI. The coarse pad super-pitch can be ~250 px (the diagnostic
# LOW_FLOOR), which would blow the kernel up to thousands of px — so we cap sigma here.
FLAT_SIGMA_MAX = 64.0


def _lowpass(roi: np.ndarray, sigma: float) -> np.ndarray:
    # cap sigma so the gaussian kernel never spans more than the ROI (and stays fast);
    # also never exceed ~1/4 of the smaller ROI dimension so the gradient estimate is local.
    sigma = float(min(sigma, 0.25 * min(roi.shape)))
    sigma = max(2.0, sigma)
    k = int(min(round(sigma * 6), 2 * min(roi.shape) - 1))
    k = max(3, k | 1)
    return cv2.GaussianBlur(roi.astype(np.float32), (k, k), sigma).astype(np.float64)


def flat_field(roi: np.ndarray, pitch_hint_px: float) -> np.ndarray:
    """Divide out the slow illumination / field-brightness profile. sigma chosen ~2x the
    coarse pad pitch (capped at FLAT_SIGMA_MAX and 1/4 ROI) so the low-pass holds ONLY the
    smooth gradient (well below f0); the comb (f0..7f0) is untouched. Linear per-pixel
    gain g(x,y)=mean/lp(x,y). MTF-safe (the kernel only attenuates DC-ish scales)."""
    sigma = min(FLAT_SIGMA_MAX, max(8.0, 2.0 * float(pitch_hint_px)))
    lp = _lowpass(roi, sigma)
    lp = np.maximum(lp, 1e-6)
    g = roi.mean() / lp
    return roi * g


def specmask_inpaint(roi: np.ndarray, luma_roi: np.ndarray) -> np.ndarray:
    """Replace achromatic-specular / outlier pixels with the local low-pass value so they
    do not inject broadband energy into the FFT. Outliers flagged on the ACHROMATIC luma
    (speculars are bright-and-neutral) AND on the channel's own robust upper tail. The
    replacement is a smooth-fill (no edge), so the comb structure on the unmasked majority
    is preserved -> robust read, not a threshold of the signal of interest."""
    lt = np.percentile(luma_roi, 99.5)
    ut = np.percentile(roi, 99.5)
    mask = (luma_roi >= lt) | (roi >= ut)
    if not mask.any():
        return roi
    # local fill = heavily blurred copy (sigma ~ moderate); replace only masked pixels.
    fill = _lowpass(roi, max(6.0, 0.02 * max(roi.shape)))
    out = roi.copy()
    out[mask] = fill[mask]
    return out


def clip_rescale(roi: np.ndarray) -> np.ndarray:
    """NEGATIVE CONTROL — INVALID. Hard p2/p98 clip + rescale. NONLINEAR: compresses the
    modulation that IS the MTF signal. Included only to show it can falsely 'collapse'."""
    lo, hi = np.percentile(roi, 2), np.percentile(roi, 98)
    if hi <= lo:
        return roi
    return np.clip((roi - lo) / (hi - lo), 0.0, 1.0) * 255.0


def apply_preproc(der: np.ndarray, luma_der: np.ndarray, pitch_hint_px: float) -> np.ndarray:
    out = der
    if DO_FLAT:
        out = flat_field(out, pitch_hint_px)
    if DO_SPECMASK:
        out = specmask_inpaint(out, luma_der)
    if DO_CLIP:
        out = clip_rescale(out)
    return out


# --------------------------------------------------------------------------- #
# phase-aligned windowed contrast read (PHASEWIN) — linear; reduces leakage
# variation across configs by cropping to an integer number of periods on the grid phase.
# --------------------------------------------------------------------------- #

def periodic_contrast_phasewin(roi, pitch_px, *, axis, half_bw_frac=0.25, min_periods=3.0):
    """Like periodic_fft.periodic_contrast but, per axis, crops the 1-D profile to an
    INTEGER number of periods phase-anchored on the grid (the profile's own fundamental
    phase) before applying the Hann window. This makes the window edges fall at the same
    grid phase for every config, so scalloping / spectral leakage at the fundamental does
    not vary config-to-config. Purely a re-sampling of the SAME data (linear)."""
    if roi.ndim != 2 or roi.size == 0 or pitch_px is None or pitch_px < 2.5:
        return None
    f0 = 1.0 / pitch_px
    if f0 >= 0.5 - 1e-6:
        return None
    axes = ("u", "v") if axis == "auto" else (axis,)
    best = None
    for ax in axes:
        prof = roi.mean(axis=0) if ax == "u" else roi.mean(axis=1)
        n = prof.size
        if n < 8 or n * f0 < min_periods:
            continue
        # estimate the grid phase at f0 from the full profile, then choose a window of an
        # integer number of periods starting at a consistent phase (peak of the cosine).
        nper = int(np.floor(n * f0))
        if nper < int(min_periods):
            continue
        wlen = int(round(nper / f0))
        wlen = min(wlen, n)
        p = prof - prof.mean()
        # phase of fundamental over the full profile
        kf = int(round(f0 * n))
        kf = max(1, min(len(p) // 2, kf))
        ph = np.angle(np.fft.rfft(p * np.hanning(n))[kf])
        # start offset so the window begins at a fixed phase (phase 0 of the grid)
        start = int(round((-ph / (2 * np.pi)) * pitch_px)) % max(1, int(round(pitch_px)))
        start = min(max(0, start), max(0, n - wlen))
        seg = prof[start:start + wlen]
        if seg.size < 8 or seg.size * f0 < min_periods:
            seg = prof
        m = seg.size
        win = np.hanning(m)
        wmean = float((seg * win).sum())
        if wmean <= 0:
            continue
        spec = np.fft.rfft(seg * win)
        amp = np.abs(spec)
        freqs = np.fft.rfftfreq(m, d=1.0)
        dc = amp[0]
        if dc <= 0:
            continue
        bw = max(1, int(round(half_bw_frac * f0 * m)))
        idx0 = int(np.argmin(np.abs(freqs - f0)))
        lo, hi = max(1, idx0 - bw), min(len(amp), idx0 + bw + 1)
        if hi <= lo:
            continue
        kpk = lo + int(np.argmax(amp[lo:hi]))
        fund = amp[kpk]
        side_lo, side_hi = max(1, kpk - 4 * bw), min(len(amp), kpk + 4 * bw + 1)
        side = np.concatenate([amp[side_lo:max(side_lo, kpk - bw)],
                               amp[min(side_hi, kpk + bw + 1):side_hi]])
        side_med = float(np.median(side)) if side.size else 0.0
        contrast = float(min(1.0, 2.0 * fund / dc))
        snr = float(fund / side_med) if side_med > 0 else float("inf")
        rec = dict(contrast=contrast, f0_cy_per_px=float(freqs[kpk]), axis=ax,
                   n_periods=float(m * f0), snr=snr, pitch_px=float(pitch_px))
        if best is None or rec["contrast"] > best["contrast"]:
            best = rec
    return best


def read_contrast(der, pitch, axis):
    if DO_PHASEWIN:
        return periodic_contrast_phasewin(der, pitch, axis=axis)
    return periodic_contrast(der, pitch_px=pitch, axis=axis)


# --------------------------------------------------------------------------- #
# anchoring (verbatim from relock_b_extract — TRUE per-axis low-floor fundamental)
# --------------------------------------------------------------------------- #

def true_axis_fundamental(roi, axis, *, maze_band=None):
    prof = roi.mean(axis=0) if axis == "u" else roi.mean(axis=1)
    n = prof.size
    if n < 32:
        return None
    prof = prof - prof.mean()
    amp = np.abs(np.fft.rfft(prof * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=1.0)
    m = (freqs >= LOW_FLOOR) & (freqs <= 0.48)
    if maze_band is not None:
        m &= ~((freqs >= maze_band[1]) & (freqs <= maze_band[2]))
    idx = np.where(m)[0]
    if idx.size < 3:
        return None
    k = idx[int(np.argmax(amp[idx]))]
    in_band_med = float(np.median(amp[idx]))
    if amp[k] <= max(1e-9, 2.0 * in_band_med):
        return None
    bw = max(2, int(0.03 * len(amp)))
    lo, hi = max(1, k - 5 * bw), min(len(amp), k + 5 * bw + 1)
    side = np.concatenate([amp[lo:max(lo, k - bw)], amp[min(hi, k + bw + 1):hi]])
    sm = float(np.median(side)) if side.size else 0.0
    snr = float(amp[k] / sm) if sm > 0 else float("inf")
    f = float(freqs[k])
    return (f, 1.0 / f, snr)


def read_preproc_comb(frames, theta_deg, M, n_marked, *, label_prefix=""):
    """frames: list of (lapvar, seq, sat_roi, luma_roi). De-rotate, optionally pre-process
    (flat/specmask/clip), then per axis lock the TRUE low-floor fundamental, predict
    n*f0 (n=1..7), read AXIS-LOCKED contrast at each rung over the (selected) frames. Plus
    the maze. Anchoring uses the SAME pre-processed best-focus ROI so the anchor is
    consistent with the read."""
    if not frames:
        return []
    mb = L.maze_band_cy_per_px(M)

    # de-rotate + pre-process each frame. pitch hint for flat-fielding = a coarse pad pitch
    # estimate from the best-focus frame (before flat) so sigma is set sensibly.
    der_sat0 = derotate(frames[0][2].astype(np.float64), theta_deg)
    der_lum0 = derotate(frames[0][3].astype(np.float64), theta_deg)
    pitch_hint = 30.0
    fu = true_axis_fundamental(der_sat0, "u", maze_band=mb)
    fv = true_axis_fundamental(der_sat0, "v", maze_band=mb)
    cand = [r[1] for r in (fu, fv) if r is not None]
    if cand:
        pitch_hint = float(max(cand))  # coarsest grid -> largest sigma -> safest flat

    der_frames = []
    for lv, seq, sat_roi, lum_roi in frames:
        der_s = derotate(sat_roi.astype(np.float64), theta_deg)
        der_l = derotate(lum_roi.astype(np.float64), theta_deg)
        der_s = apply_preproc(der_s, der_l, pitch_hint)
        der_frames.append((lv, seq, der_s))
    der_bf = der_frames[0][2]
    n_eff = optics.effective_fnumber(n_marked, M)
    samples = []

    def _read_at(f_px, feature, order, axis, anchor_pitch, anchor_snr):
        if not (0.02 < f_px < NYQ - 1e-3):
            return None
        pitch = 1.0 / f_px
        best = None
        for _lv, _seq, der in der_frames:
            c = read_contrast(der, pitch, axis)
            if c and (best is None or c["contrast"] > best["contrast"]):
                best = c
        if best is None:
            return None
        f_sensor_lpmm = f_px * L.LPMM_PER_CYPX
        f_subj = f_sensor_lpmm * M
        ceil = optics.diffraction_mtf_at(f_sensor_lpmm, n_eff)
        return dict(feature=feature, harmonic_order=order, axis=axis,
                    anchor_pitch_px=float(anchor_pitch), anchor_snr=float(anchor_snr),
                    f_subj_lpmm=float(f_subj), f_px=float(f_px),
                    contrast=float(best["contrast"]), snr=float(best["snr"]),
                    ceiling=float(ceil), over_ceiling=float(best["contrast"] - ceil))

    for axis in ("u", "v"):
        fund = true_axis_fundamental(der_bf, axis, maze_band=mb)
        if fund is None:
            continue
        f0, pitch0, snr0 = fund
        for n in range(1, MAX_ORDER + 1):
            s = _read_at(f0 * n, f"pad_{axis}", n, axis, pitch0, snr0)
            if s is not None:
                samples.append(s)

    if mb is not None:
        for order in range(1, MAZE_HARMONICS + 1):
            f_px = L.subj_to_px(L.MAZE_SUBJ_LPMM * order, M)
            if not (0.02 < f_px < NYQ - 1e-3):
                continue
            pitch = 1.0 / f_px
            best = None
            for _lv, _seq, der in der_frames:
                c = read_contrast(der, pitch, "auto")
                if c and (best is None or c["contrast"] > best["contrast"]):
                    best = c
            if best is None:
                continue
            f_sensor = f_px * L.LPMM_PER_CYPX
            ceil = optics.diffraction_mtf_at(f_sensor, n_eff)
            samples.append(dict(
                feature="maze", harmonic_order=order, axis=best["axis"],
                anchor_pitch_px=float("nan"), anchor_snr=float("nan"),
                f_subj_lpmm=float(L.MAZE_SUBJ_LPMM * order), f_px=float(f_px),
                contrast=float(best["contrast"]), snr=float(best["snr"]),
                ceiling=float(ceil), over_ceiling=float(best["contrast"] - ceil)))

    for s in samples:
        s["label"] = label_prefix
    return samples


def _ap_to_n(aperture: str) -> float:
    return float(aperture.replace("F", "").replace("f_", "").replace("f", ""))


def sat_of(bgr):
    b = bgr[:, :, 0].astype(np.float64)
    g = bgr[:, :, 1].astype(np.float64)
    r = bgr[:, :, 2].astype(np.float64)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    return np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 0) * 255.0


def topk_per_region(jpgs, regions, topk=4):
    """Per region collect the topk frames. Stores BOTH the saturation ROI (for the FFT)
    and the achromatic LUMA ROI (for specular masking) plus the global focus metric for
    the FIXED-focus criterion. Returns dict region->sorted [(lapvar, seq, sat, luma)] and
    a per-seq GLOBAL focus curve (mean luma-laplacian-var over all regions)."""
    import heapq
    boxes = {i: [int(v) for v in r["bbox"]] for i, r in enumerate(regions)}
    heaps = {i: [] for i in range(len(regions))}
    global_focus = {}  # seq -> mean lapvar over regions (the cross-config focus criterion)
    for seq, jp in enumerate(jpgs):
        bgr = cv2.imread(str(jp), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        lvs = []
        for i, (x0, y0, x1, y1) in boxes.items():
            sub = bgr[y0:y1, x0:x1]
            if sub.size == 0 or min(sub.shape[:2]) < 16:
                continue
            roi_g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
            lv = float(cv2.Laplacian(roi_g.astype(np.float32), cv2.CV_32F).var())
            lvs.append(lv)
            roi_s = sat_of(sub)
            roi_l = roi_g.astype(np.float64)
            h = heaps[i]
            if len(h) < topk:
                heapq.heappush(h, (lv, seq, roi_s.copy(), roi_l.copy()))
            elif lv > h[0][0]:
                heapq.heapreplace(h, (lv, seq, roi_s.copy(), roi_l.copy()))
        if lvs:
            global_focus[seq] = float(np.mean(lvs))
    framed = {i: sorted(h, key=lambda t: t[0], reverse=True) for i, h in heaps.items()}
    return framed, global_focus


def select_fixed_focus(framed, global_focus, regions):
    """Cross-config FIXED focus criterion: instead of each region's own argmax, pick the
    single GLOBAL best-focus seq (peak of the mean-over-regions focus curve) and, for each
    region, return the topk frames CLOSEST to that seq. Same relative through-focus
    position for every config -> removes per-region defocus variability."""
    if not global_focus:
        return framed
    best_seq = max(global_focus, key=global_focus.get)
    out = {}
    for i, frames in framed.items():
        if not frames:
            out[i] = frames
            continue
        # rank this region's stored frames by proximity to the global best seq
        ordered = sorted(frames, key=lambda t: abs(t[1] - best_seq))
        out[i] = ordered
    return out


def run_config(c):
    sweep_dir = Path(c["sample"]).parent
    jpgs = sorted(sweep_dir.glob("*.jpg")) + sorted(sweep_dir.glob("*.JPG"))
    if not jpgs:
        return None, "no_frames"
    p = apf.register(jpgs)
    if p is None:
        return None, "reg_failed"
    M = p["scale"] / apf.M_ANCHOR_SCALE
    theta = p["theta_deg"]
    if not (0.2 < M < 3.5):
        return None, f"scale_collapse_M={M:.2f}"
    regions = apf.enumerate_regions(p, p["scale"])
    regions = [r for r in regions if r["cls"] in ("magenta", "cyan")]
    if not regions:
        return None, "no_regions"
    n_marked = _ap_to_n(c["aperture"])
    framed, global_focus = topk_per_region(jpgs, regions, topk=4)
    if FOCUS == "fixed":
        framed = select_fixed_focus(framed, global_focus, regions)
    rows = []
    for ri, reg in enumerate(regions):
        frames = framed.get(ri) or []
        samples = read_preproc_comb(frames, theta, M, n_marked, label_prefix=reg["label"])
        for s in samples:
            s.update(zone=reg["zone"], cls=reg["cls"], region=reg["label"])
            rows.append(s)
    return dict(M=M, theta=theta, rmse=p["reg_fit_rmse_px"], n_marked=n_marked,
                n_regions=len(regions), rows=rows), "ok"


def main():
    cfg_csv = Path(os.environ["RANK_CONFIGS"])
    out_csv = Path(os.environ["RANK_OUT"])
    shard = os.environ.get("SHARD")
    with cfg_csv.open() as fh:
        configs = list(csv.DictReader(fh))
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        configs = [c for k, c in enumerate(configs) if k % n == i]
    preproc_tag = "+".join(PREPROC) if PREPROC else "baseline"
    fields = ["config", "lens", "mag_label", "aperture", "M", "rmse", "region",
              "cls", "zone", "axis", "anchor_pitch_px", "anchor_snr", "feature",
              "harmonic_order", "f_subj_lpmm", "f_px", "contrast", "snr",
              "ceiling", "over_ceiling", "preproc", "focus"]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    print(f"PREPROC={preproc_tag} FOCUS={FOCUS}", flush=True)
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for c in configs:
            config_id = f"{c['lens']} | {c['mag_label']} | {c['aperture']}"
            print(f"=== {config_id} ===", flush=True)
            try:
                res, status = run_config(c)
            except Exception as e:  # noqa: BLE001
                print(f"  EXC {e}", flush=True)
                continue
            if res is None:
                print(f"  DROPPED ({status})", flush=True)
                continue
            for s in res["rows"]:
                w.writerow(dict(
                    config=config_id, lens=c["lens"], mag_label=c["mag_label"],
                    aperture=c["aperture"], M=round(res["M"], 4),
                    rmse=round(res["rmse"], 2), region=s["region"], cls=s["cls"],
                    zone=s["zone"], axis=s["axis"],
                    anchor_pitch_px=(round(s["anchor_pitch_px"], 2)
                                     if s["anchor_pitch_px"] == s["anchor_pitch_px"] else ""),
                    anchor_snr=(round(s["anchor_snr"], 1)
                                if s["anchor_snr"] == s["anchor_snr"] else ""),
                    feature=s["feature"], harmonic_order=s["harmonic_order"],
                    f_subj_lpmm=round(s["f_subj_lpmm"], 2), f_px=round(s["f_px"], 4),
                    contrast=round(s["contrast"], 4), snr=round(s["snr"], 2),
                    ceiling=round(s["ceiling"], 4), over_ceiling=round(s["over_ceiling"], 4),
                    preproc=preproc_tag, focus=FOCUS))
            fh.flush()
            print(f"  M={res['M']:.3f} rmse={res['rmse']:.2f} regions={res['n_regions']} "
                  f"samples={len(res['rows'])}", flush=True)


if __name__ == "__main__":
    main()
