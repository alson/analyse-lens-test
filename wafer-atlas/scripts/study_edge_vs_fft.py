"""(2) SAME-FEATURE / SAME-FREQUENCY edge<->FFT cross-check on the 6B serpent.

The 2026-06-29 disagreement (Sigma150+TC: edge ~38.7 lp/mm "sharpest" vs periodic-FFT
"softest") is suspected to be a comparison artefact: the edge and FFT were read on
DIFFERENT features at DIFFERENT magnifications. This driver removes both confounds by
measuring BOTH metrics on the SAME feature (the 2B serpent, framed as die 6B) at the
SAME spatial frequency (the serpent's own fundamental f_serpent), per config.

FFT leg:
  * de-rotate the serpent block, collapse to the perpendicular profile,
  * measure the serpent line pitch -> f_serpent (cy/px),
  * estimate the serpent DUTY cycle d -> intrinsic fundamental modulation of a
    bar/space pattern: a square wave has fundamental coefficient (2/pi)*sin(pi*d)
    (relative to its own DC); we use k_intrinsic = (2/pi)*sin(pi*d),
  * read the bounded Michelson contrast C at f_serpent (methods.periodic_fft),
  * MTF(f_serpent)_FFT = C / k_intrinsic  (k is the target constant; dividing it out
    turns the relative contrast into an absolute MTF at f_serpent).

Edge leg (cleaned, direction-aware — the three edge_aggregate strategies):
  * detect the serpent's many parallel rising/falling edges,
  * fit each edge at ITS OWN per-edge best-focus frame (mechanism-(b) wash-out),
  * per-edge erf MTF50 (cy/px) + over-ceiling + a "settled" flat-asymptote flag,
  * aggregate with conservative / per-edge-focus / polarity-selected rules,
  * convert the chosen aggregate MTF50 to MTF AT f_serpent via the Gaussian-LSF
    relation MTF(f) = exp(-2 pi^2 sigma^2 f^2), sigma = 0.18739 / MTF50.

Compare MTF(f_serpent)_edge vs MTF(f_serpent)_FFT per config. Diagnose the rising/
falling asymmetry mechanism. Gate everything against the diffraction ceiling at
f_serpent (optics.diffraction_mtf_at). Runs on nufan.
"""
from __future__ import annotations
import csv, json, math, sys, os
from pathlib import Path
import numpy as np, cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib_2b as L  # noqa: E402
import route2_flat_edge as R2  # noqa: E402
sys.path.insert(0, str(HERE.parent.parent / "tile-sharpness" / "src"))
from tile_sharpness.methods import periodic_fft as pf  # noqa: E402
from tile_sharpness.methods import slanted_edge as se  # noqa: E402
from tile_sharpness.methods import edge_aggregate as EA  # noqa: E402
from tile_sharpness.methods.harmonic_mtf import estimate_duty_cycle  # noqa: E402
from tile_sharpness import optics  # noqa: E402

MTF50_PER_INV_SIGMA = se._MTF50_PER_INV_SIGMA  # 0.18739

# in-FOV 6B configs (from diag_2b_intermediate_fov: best_die==6B, centre_in, with a
# resolvable serpent pitch). Includes the Sigma150/105 + TC-1401 reconciliation pair.
CONFIGS = [
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-1401", "1_1", "F8"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401", "1_1", "F8"),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x", "1_1", "F8"),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Olympus MCON-35", "1_1.16", "F8"),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T", "1.27_1", "F8"),
    ("Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x", "1_1", "F8"),
]


def mtf_at(mtf50_cypx, f_cypx):
    """Gaussian-LSF MTF at f, given MTF50 (cy/px)."""
    if not mtf50_cypx or mtf50_cypx <= 0:
        return None
    sigma = MTF50_PER_INV_SIGMA / mtf50_cypx
    return float(math.exp(-2.0 * (math.pi * sigma * f_cypx) ** 2))


def k_intrinsic_square(duty):
    """Intrinsic fundamental modulation (a/m) of an ideal bar/space pattern of bright
    duty ``d``: Michelson-style coefficient = (2/pi)*sin(pi*d). For d=0.5 -> 2/pi."""
    return (2.0 / math.pi) * math.sin(math.pi * float(np.clip(duty, 0.02, 0.98)))


def fft_leg(block_derot, M, n_eff):
    """Discover f_serpent on the de-rotated serpent block, measure duty + contrast,
    return the FFT MTF at f_serpent. Returns dict or None."""
    H, W = block_derot.shape
    # central x band of the long-line region (dodge bond-pad columns top/bottom)
    x0, x1 = int(0.20 * W), int(0.80 * W)
    # serpent lines run horizontally -> periodicity along v (rows). discover_fundamental
    # 'v' axis: average columns, FFT along rows.
    strip = block_derot[:, x0:x1]
    d = pf.discover_fundamental(strip, axis="v", band=(0.04, 0.45), exclude=None)
    if d is None:
        return None
    pitch = d["pitch_px"]; f0 = d["f0_cy_per_px"]
    # duty cycle from the perpendicular (row-mean) profile
    prof = strip.mean(axis=1)
    duty = estimate_duty_cycle(prof)
    k = k_intrinsic_square(duty)
    c = pf.periodic_contrast(strip, pitch_px=pitch, axis="v")
    if c is None:
        return None
    C = c["contrast"]
    mtf_fft = min(1.0, C / k) if k > 0 else None
    ceil = optics.diffraction_mtf_at(f0 * (1000.0 / 4.35), n_eff)  # f in lp/mm sensor
    return dict(pitch_px=pitch, f0_cypx=f0, duty=duty, k_intrinsic=k,
                contrast=C, snr=c["snr"], mtf_fft=mtf_fft, ceiling=ceil)


def edge_leg(lens, mag, ap, f_serpent_cypx, n_eff, ceil_at_f):
    """Per-edge MTF50 on the serpent at each edge's OWN best-focus frame; build
    edge_aggregate records carrying mtf50/kind/over/flag/t_along/settled. Reuses the
    route2 geometry (register, locate 6B, detect edges)."""
    ap_dir = L.RAW / lens / mag / ap
    rmse, aff, jp0, jpgs = L.register_best(ap_dir)
    if aff is None:
        return None, None, "reg-fail"
    M = aff["scale"] / L.M_ANCHOR_SCALE
    theta = aff.get("theta_deg", 0.0)
    info = L.get_block(jp0, aff, want_type=(2, 1), derotate=True)
    if info is None:
        return None, None, "no-2b"
    block, bbox = info["block"], info["bbox"]
    ix0, iy0, ix1, iy1 = bbox
    crop_shape = (iy1 - iy0, ix1 - ix0)
    Hb, Wb = block.shape
    edges, prof, _ = R2.detect_line_edges(block, M)

    # pre-decode all frames once (grayscale) for per-edge best focus
    grays = []
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is not None:
            grays.append((jp, g.astype(np.float32)))
    if not grays:
        return None, None, "no-frames"

    ceil_cypx = optics.diffraction_mtf50_sensor_lpmm(n_eff) / L.LPMM_PER_CYPX
    bx_lo, bx_hi = int(0.20 * Wb), int(0.80 * Wb)

    def lapvar_at(g, mx, my, half=40):
        y0, y1 = max(0, int(my - half)), min(g.shape[0], int(my + half))
        x0, x1 = max(0, int(mx - half)), min(g.shape[1], int(mx + half))
        r = g[y0:y1, x0:x1]
        return cv2.Laplacian(r.astype(np.float32), cv2.CV_32F).var() if r.size else -1.0

    records = []
    edges2 = sorted(edges, key=lambda e: -min(e[2], e[3]))
    for (yk, kind, cu, cd, _, _) in edges2:
        clear = min(cu, cd)
        if clear < 5:
            continue
        half = float(min(clear - 1.0, 24.0))
        if half < 6.0:
            continue
        # original-frame guess for the edge endpoints at this block-y
        ox0, oy0 = R2.derot_to_orig(bx_lo, yk, bbox, theta, (None, None), crop_shape)
        ox1, oy1 = R2.derot_to_orig(bx_hi, yk, bbox, theta, (None, None), crop_shape)
        # per-edge best-focus frame: lapvar at the edge midpoint
        mxo, myo = 0.5 * (ox0 + ox1), 0.5 * (oy0 + oy1)
        best_g, best_lv, best_idx = None, -1.0, None
        for idx, (jp, g) in enumerate(grays):
            lv = lapvar_at(g, mxo, myo)
            if lv > best_lv:
                best_lv, best_g, best_idx = lv, g, idx
        if best_g is None:
            continue
        fit = R2.fit_edge_segment(best_g, ox0, ox1, oy0, kind, theta)
        if fit is None:
            continue
        seg, off_axis, straight = fit
        if not (1.5 < off_axis < 9.0):
            continue
        ds, pp = R2.perp_profile_orig(best_g, seg, half=max(40.0, half + 10))
        rim, dlev, blev = R2.specular_rim(ds, pp, kind)
        contrast = abs(blev - dlev)
        if contrast < 15:
            continue
        m_erf = se.mtf50_step_erf(best_g, seg, half_window_px=half, quality_gate=True)
        if m_erf is None:
            continue
        over = m_erf / ceil_cypx if ceil_cypx else None
        # "settled": ESF asymptotes flat on BOTH sides within the window. Use the
        # perp profile: both far ends within a small band of their plateau.
        settled = _settled(ds, pp, kind)
        records.append(dict(mtf50=float(m_erf), kind=kind, over=over,
                            flag=bool(rim), t_along=float(yk), settled=settled,
                            focus_idx=best_idx, half=half, contrast=contrast))
    return records, dict(M=M, rmse=rmse, ceil_cypx=ceil_cypx), "ok"


def _settled(ds, prof, kind):
    """Both sides of the edge reach a flat plateau (low slope) at the window ends."""
    fin = np.isfinite(prof)
    if fin.sum() < 12:
        return False
    n = ds.size
    a = prof[:max(3, n // 6)]; b = prof[-max(3, n // 6):]
    a = a[np.isfinite(a)]; b = b[np.isfinite(b)]
    if a.size < 3 or b.size < 3:
        return False
    rng = float(np.nanmax(prof) - np.nanmin(prof)) + 1e-6
    flat_a = (np.nanmax(a) - np.nanmin(a)) < 0.12 * rng
    flat_b = (np.nanmax(b) - np.nanmin(b)) < 0.12 * rng
    return bool(flat_a and flat_b)


def measure_config(lens, mag, ap):
    ap_dir = L.RAW / lens / mag / ap
    rmse, aff, jp0, jpgs = L.register_best(ap_dir)
    if aff is None:
        return dict(config=f"{lens}|{mag}", ok=False, reason="reg-fail")
    M = aff["scale"] / L.M_ANCHOR_SCALE
    n_eff = float(ap.replace("F", "").replace("_", ".")) * (1.0 + M)
    info = L.get_block(jp0, aff, want_type=(2, 1), derotate=True)
    if info is None:
        return dict(config=f"{lens}|{mag}", ok=False, reason="no-2b")
    fft = fft_leg(info["block"], M, n_eff)
    if fft is None:
        return dict(config=f"{lens}|{mag}", ok=False, reason="fft-fail")
    f_serpent = fft["f0_cypx"]
    ceil_at_f = fft["ceiling"]
    records, meta, status = edge_leg(lens, mag, ap, f_serpent, n_eff, ceil_at_f)
    out = dict(config=f"{lens}|{mag}", ok=True, M=round(M, 3), n_eff=round(n_eff, 2),
               die=info["label"], rmse=round(rmse, 2),
               f_serpent_cypx=round(f_serpent, 4),
               f_serpent_subj_lpmm=round(f_serpent * M * L.LPMM_PER_CYPX, 1),
               pitch_px=round(fft["pitch_px"], 1), duty=round(fft["duty"], 3),
               k_intrinsic=round(fft["k_intrinsic"], 4),
               C_fft=round(fft["contrast"], 4), snr_fft=round(fft["snr"], 1),
               mtf_fft_at_f=round(fft["mtf_fft"], 4) if fft["mtf_fft"] else None,
               ceil_at_f=round(ceil_at_f, 4),
               edge_status=status)
    if not records:
        out["edge_n"] = 0
        return out
    # three aggregation strategies
    cons = EA.aggregate_conservative(records, over_ceiling=1.05, combine="min_direction")
    pef = EA.aggregate_per_edge_focus(records, over_ceiling=1.05)
    # FFT MTF at f_serpent as the physical anchor for polarity selection
    pol = EA.aggregate_polarity_selected(records, reference_cypx=None,
                                         ceiling_cypx=meta["ceil_cypx"],
                                         prefer_settled=True)
    diag = EA.diagnose_asymmetry(records)
    # naive (old) median over all passing edges, for the artefact comparison
    all_m = [r["mtf50"] for r in records]
    naive_med = float(np.median(all_m))

    out.update(edge_n=len(records),
               edge_naive_med_cypx=round(naive_med, 4),
               edge_naive_mtf_at_f=round(mtf_at(naive_med, f_serpent), 4),
               edge_cons_cypx=round(cons["mtf50"], 4) if cons else None,
               edge_cons_mtf_at_f=round(mtf_at(cons["mtf50"], f_serpent), 4) if cons else None,
               edge_pef_cypx=round(pef["mtf50"], 4) if pef else None,
               edge_pef_mtf_at_f=round(mtf_at(pef["mtf50"], f_serpent), 4) if pef else None,
               edge_pol_cypx=round(pol["mtf50"], 4) if pol else None,
               edge_pol_chosen=pol["chosen"] if pol else None,
               edge_pol_mtf_at_f=round(mtf_at(pol["mtf50"], f_serpent), 4) if pol else None,
               rising_med=round(diag["rising_med"], 4) if diag["rising_med"] else None,
               falling_med=round(diag["falling_med"], 4) if diag["falling_med"] else None,
               split_ratio=round(diag["split_ratio"], 3) if diag["split_ratio"] else None,
               per_line_sign=round(diag["per_line_sign"], 2) if diag["per_line_sign"] is not None else None,
               field_trend=round(diag["field_trend"], 2) if diag["field_trend"] is not None else None,
               asym_verdict=diag["verdict"],
               edge_naive_lpmm=round(naive_med * M * L.LPMM_PER_CYPX, 1),
               edge_cons_lpmm=round(cons["mtf50"] * M * L.LPMM_PER_CYPX, 1) if cons else None)
    return out


def fmt(r):
    if not r["ok"]:
        return f"{r['config']}: FAIL ({r['reason']})"
    s = [f"\n=== {r['config']}  die={r['die']} M={r['M']} N_eff={r['n_eff']} rmse={r['rmse']} ==="]
    s.append(f"  f_serpent={r['f_serpent_cypx']:.4f} cy/px (pitch {r['pitch_px']}px, "
             f"{r['f_serpent_subj_lpmm']} lp/mm subj)  duty={r['duty']}  k={r['k_intrinsic']:.3f}")
    s.append(f"  FFT:  C={r['C_fft']:.3f} (snr {r['snr_fft']}) -> MTF(f_serpent)_FFT = C/k = "
             f"{r['mtf_fft_at_f']}   [ceiling@f = {r['ceil_at_f']}]")
    if r.get("edge_n", 0) == 0:
        s.append(f"  EDGE: no passing edges ({r.get('edge_status')})")
        return "\n".join(s)
    s.append(f"  EDGE n={r['edge_n']}  rising_med={r['rising_med']} falling_med={r['falling_med']} "
             f"split={r['split_ratio']}x  per_line_sign={r['per_line_sign']} field_trend={r['field_trend']}")
    s.append(f"        asym verdict: {r['asym_verdict']}")
    s.append(f"  MTF(f_serpent) comparison (edge vs FFT={r['mtf_fft_at_f']}):")
    s.append(f"     naive-median       MTF50={r['edge_naive_med_cypx']}  -> MTF@f={r['edge_naive_mtf_at_f']}")
    s.append(f"     conservative(min-dir) MTF50={r['edge_cons_cypx']} -> MTF@f={r['edge_cons_mtf_at_f']}")
    s.append(f"     per-edge-focus(mean)  MTF50={r['edge_pef_cypx']} -> MTF@f={r['edge_pef_mtf_at_f']}")
    s.append(f"     polarity({r['edge_pol_chosen']})    MTF50={r['edge_pol_cypx']} -> MTF@f={r['edge_pol_mtf_at_f']}")
    return "\n".join(s)


def main():
    shard = os.environ.get("SHARD")
    items = list(enumerate(CONFIGS))
    if shard:
        i, n = map(int, shard.split("/"))
        items = [(k, v) for k, v in items if k % n == i]
    rows = []
    for k, (lens, mag, ap) in items:
        r = measure_config(lens, mag, ap)
        print(fmt(r), flush=True)
        rows.append(r)
    out = HERE / (f"study_edge_vs_fft{'_' + shard.replace('/', 'of') if shard else ''}.csv")
    ok = [r for r in rows if r.get("ok")]
    if ok:
        keys = sorted({k for r in ok for k in r})
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
            for r in ok:
                w.writerow({k: r.get(k, "") for k in keys})
        print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    main()
