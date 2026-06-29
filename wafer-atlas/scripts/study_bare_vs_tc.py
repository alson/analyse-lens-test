"""(3) CONTROLLED bare-vs-TC comparison, k-normalised at a COMMON subject frequency.

Goal: (a) the bare ranking Sigma105 vs Sigma150 vs AF200; (b) the TC-tolerance signal
— each lens's MTF drop bare -> +TC-1401 -> +TC-2001. The headline question: is the
Sigma 105 intrinsically sharper than the 150, or does it merely tolerate TCs better?

Confound to remove: raw periodic contrast is M-confounded (higher M samples a LOWER
subject frequency, where contrast is naturally higher; REPORT §G.1). So we compare at
a COMMON SUBJECT frequency on a COMMON feature, k-normalised.

Method (per config):
  * register, locate the 2B serpent (the single shared physical feature),
  * de-rotate, build the perpendicular (row-mean) profile of the matte line band,
  * estimate the serpent duty d -> k_intrinsic = (2/pi)|sin(pi d)| (fundamental) and
    per-harmonic k_n = (2/(n pi))|sin(n pi d)| (used only to extend the curve),
  * read bounded Michelson contrast C at a SET of sensor frequencies and convert each
    to a SUBJECT frequency f_subj = f_sensor * M and to MTF = C / k(that harmonic),
  * build MTF(f_subj) and INTERPOLATE to the common target subject frequency F_COMMON.
  * gate every value <= the diffraction ceiling at that f (optics.diffraction_mtf_at).

F_COMMON is chosen in the band resolvable by ALL configs (low enough that even M=1
configs carry it, high enough to discriminate). We report MTF@F_COMMON per config.

Sigma 105 + TC-2001 does NOT register (§I); we try the robust reg and, if it still
fails, report that cell MISSING (never guessed).

Runs on nufan. Output: study_bare_vs_tc.csv + a ranking / TC-tolerance summary.
"""
from __future__ import annotations
import csv, math, sys, os
from pathlib import Path
import numpy as np, cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib_2b as L  # noqa: E402
import route2_flat_edge as R2  # noqa: E402
sys.path.insert(0, str(HERE.parent.parent / "tile-sharpness" / "src"))
from tile_sharpness.methods import periodic_fft as pf  # noqa: E402
from tile_sharpness.methods.harmonic_mtf import estimate_duty_cycle  # noqa: E402
from tile_sharpness import optics  # noqa: E402

LPMM = L.LPMM_PER_CYPX  # 229.9 lp/mm per cy/px

# common target subject frequency (lp/mm). The serpent fundamental at M=1 lands ~8-19
# lp/mm; we read a band and interpolate. 18 lp/mm is carried by every config's band.
F_COMMON_LPMM = 18.0

# (lens, mag, aperture). Bare macros @1:1, + TC-1401 @1:1 and @1.4:1, + TC-2001 @2:1.
CONFIGS = [
    ("bare", "Sigma Macro 105mm F2.8 EX DG OS HSM", "1_1", "F8"),
    ("bare", "Sigma APO Macro 150mm F2.8 EX DG OS HSM", "1_1", "F8"),
    ("bare", "Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "1_1", "F8"),
    ("TC-1401", "Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401", "1_1", "F8"),
    ("TC-1401", "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-1401", "1_1", "F8"),
    ("TC-2001", "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001", "2_1", "F11"),
    ("TC-2001", "Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001", "2_1", "F11"),  # §I: expected reg-fail
]


def k_n(duty, n):
    """Intrinsic Michelson-style coefficient of the n-th harmonic of a bar/space
    pattern of bright duty d (relative to DC), assuming dark level ~0: (2/(n pi))|sin(n pi d)|."""
    d = float(np.clip(duty, 0.02, 0.98))
    return (2.0 / (n * math.pi)) * abs(math.sin(n * math.pi * d))


def serpent_profile(block_derot):
    """Row-mean perpendicular profile of the matte serpent LINE band (upper region,
    central x). Lines run horizontally -> periodicity along rows (v)."""
    H, W = block_derot.shape
    x0, x1 = int(0.20 * W), int(0.80 * W)
    y0, y1 = int(0.05 * H), int(0.45 * H)
    strip = block_derot[y0:y1, x0:x1]
    return strip, strip.mean(axis=1)


def contrast_at_freq(prof, f_cypx, half_bw_frac=0.18):
    """Bounded Michelson contrast 2|F(f)|/|F(0)| at an arbitrary sensor frequency f
    on a 1-D profile (keeps DC). Searches +-half_bw_frac*f for the local peak to
    absorb pitch error. Returns (contrast, f_used, snr) or None."""
    n = prof.size
    if n < 16 or f_cypx <= 0 or f_cypx >= 0.5:
        return None
    win = np.hanning(n)
    spec = np.abs(np.fft.rfft(prof * win))
    freqs = np.fft.rfftfreq(n, 1.0)
    dc = spec[0]
    if dc <= 0:
        return None
    bw = max(1, int(round(half_bw_frac * f_cypx * n)))
    idx0 = int(np.argmin(np.abs(freqs - f_cypx)))
    lo, hi = max(1, idx0 - bw), min(len(spec), idx0 + bw + 1)
    if hi <= lo:
        return None
    kpk = lo + int(np.argmax(spec[lo:hi]))
    fund = spec[kpk]
    slo, shi = max(1, kpk - 4 * bw), min(len(spec), kpk + 4 * bw + 1)
    side = np.concatenate([spec[slo:max(slo, kpk - bw)], spec[min(shi, kpk + bw + 1):shi]])
    sidemed = float(np.median(side)) if side.size else 0.0
    return (float(min(1.0, 2.0 * fund / dc)), float(freqs[kpk]),
            float(fund / sidemed) if sidemed > 0 else float("inf"))


def measure_config(group, lens, mag, ap):
    ap_dir = L.RAW / lens / mag / ap
    if not ap_dir.exists():
        return dict(group=group, config=f"{lens}|{mag}", ok=False, reason="no-dir")
    rmse, aff, jp0, jpgs = L.register_best(ap_dir)
    if aff is None:
        return dict(group=group, config=f"{lens}|{mag}", ok=False, reason="reg-fail")
    M = aff["scale"] / L.M_ANCHOR_SCALE
    n_eff = float(ap.replace("F", "").replace("_", ".")) * (1.0 + M)
    info = L.get_block(jp0, aff, want_type=(2, 1), derotate=True)
    if info is None:
        return dict(group=group, config=f"{lens}|{mag}", ok=False, reason="no-2b")
    # pick the serpent's best-focus frame across the sweep at the block centre
    theta = aff.get("theta_deg", 0.0)
    bbox = info["bbox"]; ix0, iy0, ix1, iy1 = bbox

    def lapvar_central(g):
        cy0, cy1 = max(0, iy0), min(g.shape[0], iy1)
        cx0, cx1 = max(0, ix0), min(g.shape[1], ix1)
        r = g[cy0:cy1, cx0:cx1]
        return cv2.Laplacian(r.astype(np.float32), cv2.CV_32F).var() if r.size else -1.0

    best_g, best_lv = info["full"], -1.0
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        lv = lapvar_central(g)
        if lv > best_lv:
            best_lv, best_g = lv, g.astype(np.float32)
    crop = best_g[max(0, iy0):iy1, max(0, ix0):ix1]
    block = pf.derotate(crop, theta)
    strip, prof = serpent_profile(block)
    # discover the serpent fundamental in subject-resolvable band
    d = pf.discover_fundamental(strip, axis="v", band=(0.04, 0.45), exclude=None)
    if d is None:
        return dict(group=group, config=f"{lens}|{mag}", ok=False, reason="no-fundamental")
    f0 = d["f0_cy_per_px"]; pitch = d["pitch_px"]
    duty = estimate_duty_cycle(prof)

    # Build MTF(f_subj) from harmonics n=1..5: C_n / k_n, gate <= ceiling.
    pts = []
    for n in range(1, 6):
        fn = n * f0
        if fn >= 0.48:
            break
        cf = contrast_at_freq(prof, fn)
        if cf is None:
            continue
        C, f_used, snr = cf
        kk = k_n(duty, n)
        if kk < 0.05:                 # near a sinc null -> unstable
            continue
        mtf = min(1.0, C / kk)
        f_subj = f_used * M * LPMM
        f_sensor_lpmm = f_used * (1000.0 / 4.35)
        ceil = optics.diffraction_mtf_at(f_sensor_lpmm, n_eff)
        pts.append((f_subj, mtf, ceil, snr, n, C, kk))

    if len(pts) < 1:
        return dict(group=group, config=f"{lens}|{mag}", ok=False, reason="no-harmonics")
    pts.sort()
    fs = np.array([p[0] for p in pts]); ms = np.array([p[1] for p in pts])
    ceils = np.array([p[2] for p in pts]); cs = np.array([p[5] for p in pts])
    # interpolate to the common subject frequency. Report BOTH the k-normalised MTF
    # (C/k_n) and the RAW Michelson contrast C: since this is the SAME physical serpent
    # in every config, the raw-C ranking is k-independent and immune to per-config duty
    # noise (the cleaner relative comparison); C/k_n adds the absolute-MTF interpretation.
    mtf_common = ceil_common = c_common = None
    in_span = fs.min() - 1e-6 <= F_COMMON_LPMM <= fs.max() + 1e-6
    if in_span and len(fs) >= 2:
        mtf_common = float(np.interp(F_COMMON_LPMM, fs, ms))
        ceil_common = float(np.interp(F_COMMON_LPMM, fs, ceils))
        c_common = float(np.interp(F_COMMON_LPMM, fs, cs))
    elif len(fs) == 1 or not in_span:
        j = int(np.argmin(np.abs(fs - F_COMMON_LPMM)))
        mtf_common = float(ms[j]); ceil_common = float(ceils[j]); c_common = float(cs[j])

    return dict(group=group, config=f"{lens}|{mag}", ok=True, die=info["label"],
                M=round(M, 3), n_eff=round(n_eff, 2), rmse=round(rmse, 2),
                f0_cypx=round(f0, 4), pitch_px=round(pitch, 1), duty=round(duty, 3),
                n_harmonics=len(pts),
                f_subj_span=f"[{fs.min():.1f},{fs.max():.1f}]",
                mtf_at_common=round(mtf_common, 4) if mtf_common is not None else None,
                raw_C_at_common=round(c_common, 4) if c_common is not None else None,
                ceil_at_common=round(ceil_common, 4) if ceil_common is not None else None,
                over_at_common=(round(mtf_common / ceil_common, 3)
                                if (mtf_common and ceil_common) else None),
                harmonics=";".join(f"n{p[4]}:f{p[0]:.1f}/M{p[1]:.3f}/c{p[2]:.3f}/snr{p[3]:.0f}" for p in pts))


def main():
    shard = os.environ.get("SHARD")
    items = list(enumerate(CONFIGS))
    if shard:
        i, n = map(int, shard.split("/"))
        items = [(k, v) for k, v in items if k % n == i]
    rows = []
    for k, (group, lens, mag, ap) in items:
        r = measure_config(group, lens, mag, ap)
        rows.append(r)
        if not r["ok"]:
            print(f"[{group}] {lens[:40]} {mag}: FAIL ({r['reason']})", flush=True)
            continue
        print(f"[{group}] {r['config'][:50]} die={r['die']} M={r['M']} N_eff={r['n_eff']} "
              f"rmse={r['rmse']} duty={r['duty']}\n"
              f"    serpent f0={r['f0_cypx']} (pitch {r['pitch_px']}px); {r['n_harmonics']} harmonics; "
              f"f_subj span {r['f_subj_span']} lp/mm\n"
              f"    MTF@{F_COMMON_LPMM:.0f}lp/mm = {r['mtf_at_common']} "
              f"(ceiling {r['ceil_at_common']}, over {r['over_at_common']})\n"
              f"    harmonics: {r['harmonics']}", flush=True)
    out = HERE / (f"study_bare_vs_tc{'_' + shard.replace('/', 'of') if shard else ''}.csv")
    keys = ["group", "config", "ok", "reason", "die", "M", "n_eff", "rmse", "f0_cypx",
            "pitch_px", "duty", "n_harmonics", "f_subj_span", "mtf_at_common",
            "raw_C_at_common", "ceil_at_common", "over_at_common", "harmonics"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in keys})
    print(f"\nwrote {out}", flush=True)

    # summary: bare ranking + TC-tolerance per lens
    ok = {r["config"]: r for r in rows if r.get("ok")}
    print(f"\n=== MTF @ {F_COMMON_LPMM:.0f} lp/mm (subject), k-normalised, serpent ===")
    for r in rows:
        tag = f"{r['mtf_at_common']}" if r.get("ok") else f"MISSING ({r.get('reason')})"
        print(f"  [{r['group']:8s}] {r['config'][:48]:48s} -> {tag}")


if __name__ == "__main__":
    main()
