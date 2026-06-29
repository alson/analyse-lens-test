"""Stage Relock — Phase B step 1: RE-ANCHOR the comb on each region's TRUE per-axis
2-D pad-grid fundamental and re-extract the harmonic-comb amplitudes A_n.

UNTRACKED / exploratory. Mirrors poc_comb_chain_tn_extract.py (same atlas registration,
saturation channel, focus selection, bounded-Michelson read, sharded runner) EXCEPT the
ANCHORING:

  PRODUCTION (tn_extract): L.discover_pad_fundamental -> discover_fundamental with the
    M-aware floor (~0.045-0.06 cy/px). Phase A showed this floor (a) clips the dominant
    coarse v-axis pad grid (~30 px, f~0.033, SNR up to 254) and (b) forces the cross-axis
    "auto" argmax onto the WEAKER u-axis ~21 px feature, and the pick flips with M.

  RELOCK (here): per region, per axis (u AND v SEPARATELY), discover the STRONGEST
    periodic fundamental with a LOW floor (0.004 cy/px, period ~250 px) so the genuine
    coarse grid is the anchor. The fundamental sits at MTF~=1 (no discrimination); the MTF
    info is in its HARMONICS n*f0 that climb into the resolvable/sub-Nyquist band. Predict
    the harmonic series for n=1..7, read bounded Michelson contrast at each rung ON THAT
    AXIS (axis-locked, not auto, so the u and v combs never cross-talk), ceiling-validate.

Each row: (config, region, axis, anchor_pitch_px, feature, harmonic_order, f_subj_lpmm,
           f_px, contrast, snr, ceiling, over_ceiling). 'feature' = "pad_u"/"pad_v"; the
maze is read identically to tn_extract (fundamental + 2f-4f) for the cross-structure check.

Usage (nufan):
  SHARD=0/8 RANK_CONFIGS=subset.csv RANK_OUT=out/relock_shard_0.csv \
    PYTHONPATH=<src> python scripts/poc_comb_chain_relock_b_extract.py
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
LOW_FLOOR = 0.004   # period ~250 px; admits the genuine coarse pad grid


def true_axis_fundamental(roi, axis, *, maze_band=None):
    """Strongest periodic fundamental of the axis-collapsed profile, LOW floor (admits
    the coarse grid the production floor clips). axis='u' -> vary across columns. Returns
    (f0_cy_per_px, pitch_px, snr) or None."""
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


def read_relock_comb(frames, theta_deg, M, n_marked, *, label_prefix=""):
    """Re-anchored comb read. For EACH axis (u,v) lock the true low-floor fundamental on
    the best-focus frame, predict n*f0 (n=1..7), read AXIS-LOCKED bounded Michelson
    contrast at each rung over the best-focus frames. Plus the maze (fundamental + 2-4f).
    """
    if not frames:
        return []
    der_frames = [(lv, seq, derotate(roi.astype(np.float64), theta_deg))
                  for lv, seq, roi in frames]
    der_bf = der_frames[0][2]
    mb = L.maze_band_cy_per_px(M)
    n_eff = optics.effective_fnumber(n_marked, M)
    samples = []

    def _read_at(f_px, feature, order, axis, anchor_pitch, anchor_snr):
        if not (0.02 < f_px < NYQ - 1e-3):
            return None
        pitch = 1.0 / f_px
        best = None
        for _lv, _seq, der in der_frames:
            c = periodic_contrast(der, pitch_px=pitch, axis=axis)  # AXIS-LOCKED
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

    # maze comb (read on auto axis as in tn_extract; M-invariant subject frequency)
    if mb is not None:
        for order in range(1, MAZE_HARMONICS + 1):
            f_px = L.subj_to_px(L.MAZE_SUBJ_LPMM * order, M)
            if not (0.02 < f_px < NYQ - 1e-3):
                continue
            pitch = 1.0 / f_px
            best = None
            for _lv, _seq, der in der_frames:
                c = periodic_contrast(der, pitch_px=pitch, axis="auto")
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


def topk_per_region_sat(jpgs, regions, topk=4):
    import heapq
    boxes = {i: [int(v) for v in r["bbox"]] for i, r in enumerate(regions)}
    heaps = {i: [] for i in range(len(regions))}
    for seq, jp in enumerate(jpgs):
        bgr = cv2.imread(str(jp), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        for i, (x0, y0, x1, y1) in boxes.items():
            sub = bgr[y0:y1, x0:x1]
            if sub.size == 0 or min(sub.shape[:2]) < 16:
                continue
            roi_g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
            lv = float(cv2.Laplacian(roi_g.astype(np.float32), cv2.CV_32F).var())
            roi_s = sat_of(sub)
            h = heaps[i]
            if len(h) < topk:
                heapq.heappush(h, (lv, seq, roi_s.copy()))
            elif lv > h[0][0]:
                heapq.heapreplace(h, (lv, seq, roi_s.copy()))
    return {i: sorted(h, reverse=True) for i, h in heaps.items()}


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
    framed = topk_per_region_sat(jpgs, regions, topk=4)
    rows = []
    for ri, reg in enumerate(regions):
        frames = framed.get(ri) or []
        samples = read_relock_comb(frames, theta, M, n_marked, label_prefix=reg["label"])
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
    fields = ["config", "lens", "mag_label", "aperture", "M", "rmse", "region",
              "cls", "zone", "axis", "anchor_pitch_px", "anchor_snr", "feature",
              "harmonic_order", "f_subj_lpmm", "f_px", "contrast", "snr",
              "ceiling", "over_ceiling"]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
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
                    ceiling=round(s["ceiling"], 4), over_ceiling=round(s["over_ceiling"], 4)))
            fh.flush()
            print(f"  M={res['M']:.3f} rmse={res['rmse']:.2f} regions={res['n_regions']} "
                  f"samples={len(res['rows'])}", flush=True)


if __name__ == "__main__":
    main()
