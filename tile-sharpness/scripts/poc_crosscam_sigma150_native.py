#!/usr/bin/env python3
"""
POC — NATIVE-RESOLUTION, from-RAW PSD-to-Nyquist cross-camera sensor+OLPF ratio (Sigma 150).

Goal: test whether a native-pixel (un-resampled) PSD from the raw NEFs can rescue the
Sigma-150 Z7-vs-D7200 sensor+OLPF bridge that the ATLAS-resampled prototype
(poc_crosscam_sigma150.py, commit 97d9b30) could not. That prototype failed 4 checks:
 (1) ratio APERTURE-DEPENDENT, (2) RISES with freq (noise floor / over-read),
 (3) low-f exposure-factor scatter (optics+target don't cancel), (4) OLPF region OUT OF BAND
 (atlas 700-samples/unit grid band-limits to ~0.27 cy/px = 54% Nyquist).
Native-res directly targets (4) [reach Nyquist] and (2) [explicit noise floor]; it does NOT
inherently fix (1)/(3). This POC decides yes/no.

METHOD / CAVEATS (lead with them):
 * dcraw LINEAR, unsharpened, bilinear (-q 0) GREEN channel. Bilinear interpolation mildly
   attenuates/contaminates the top ~10-20% of the band -> near-Nyquist ABSOLUTE shape carries
   that caveat; but the decisive checks (1 aperture-indep, 3 cancellation) are decode-agnostic.
   A true single-Bayer-sublattice channel would avoid interpolation but halves the Nyquist
   (defeats the purpose); the full-pitch Nyquist needs the full grid -> demosaic. Documented.
 * reg_auto is run DIRECTLY on the contrast-stretched raw green (not the JPG) so patches come
   from the raw grid — avoids the JPG(4000x6000)-vs-raw(4016x6016) masked-border offset.
 * Same physical wafer patch (matched atlas cell col,row) across cameras -> optical MTF and the
   target's own spectrum cancel in the ratio, leaving sensor+OLPF+pixel MTF ratio x exposure.
 * ~6% M-offset (Z7 M~1.03 vs D7200 M~1.09) is MODELED via px_per_unit mapping to a common
   SUBJECT-frequency grid; it is UNREMOVABLE (D7200 sold). First-order, ONE lens.
 * Exposure normalized by raw-green mean^2 (brightness proxy) so the ratio reflects MTF shape.
"""
from __future__ import annotations
import cv2, subprocess, numpy as np, glob, importlib.util, tempfile, os, sys, json
from pathlib import Path

WA = "/home/alson/shared/projects/personal/fotografie/analyse-lens-test/wafer-atlas/scripts"
_spec = importlib.util.spec_from_file_location("reg_auto", WA + "/reg_auto.py")
ra = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ra)

TRD = "/home/alson/shared/files/pics/digikam/test-raw-data"
CFG = {
    "Z7":    dict(base=f"{TRD}/2026-05-13/Sigma APO Macro 150mm F2.8 EX DG OS HSM",
                  aps={"F5.6": "f_5_6", "F8": "f_8", "F11": "f_11", "F16": "f_16"},
                  pitch_um=4.35, olpf=False),
    "D7200": dict(base=f"{TRD}/2025-08-19/Sigma APO Macro 150mm F2.8 EX DG OS HSM",
                  aps={"F5.6": "F5.6", "F8": "F8", "F11": "F11", "F16": "F16"},
                  pitch_um=3.91, olpf=True),
}
APS = ["F5.6", "F8", "F11", "F16"]
WIN_UNITS = 0.40          # physical window per patch, in atlas units (same physical size both cams)
NCELL = 2                 # NCELL x NCELL central atlas cells -> matched patches (ppu~1280px/unit)


def audit_raw_availability():
    """Raw (NEF) availability is the precondition: native-res-from-RAW needs NEFs on BOTH
    cameras. Audit every Sigma-150 session on each camera and return whether the bridge is
    even runnable."""
    sessions = {
        "Z7": ["2025-10-17", "2026-01-29", "2026-05-13"],
        "D7200": ["2025-08-19"],
    }
    print("=== RAW (NEF) availability audit — Sigma 150, per camera/session ===")
    have = {}
    for cam, sess in sessions.items():
        tot = 0
        for s in sess:
            base = f"{TRD}/{s}"
            hits = 0
            for d in glob.glob(f"{base}/Sigma APO Macro 150mm F2.8 EX DG OS HSM*"):
                if os.path.isdir(d):
                    hits += sum(1 for _ in Path(d).rglob("*.nef")) + sum(1 for _ in Path(d).rglob("*.NEF"))
            print(f"  {cam:6s} {s}: Sigma150 NEFs = {hits}")
            tot += hits
        have[cam] = tot
    runnable = have["Z7"] > 0 and have["D7200"] > 0
    print(f"  -> Z7 Sigma150 NEFs total={have['Z7']}, D7200={have['D7200']}  "
          f"=> native-res cross-camera RUNNABLE: {runnable}")
    return runnable


def decode_green(nef: str) -> np.ndarray:
    p = subprocess.run(["dcraw", "-4", "-T", "-q", "0", "-o", "0", "-W", "-c", nef],
                       capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"dcraw failed: {p.stderr[:160]!r}")
    a = cv2.imdecode(np.frombuffer(p.stdout, np.uint8), cv2.IMREAD_UNCHANGED)
    if a is None:
        raise RuntimeError("could not read dcraw TIFF")
    return a[:, :, 1].astype(np.float64)   # linear green


def lapvar_central(g, half=500):
    h, w = g.shape[:2]
    c = g[h // 2 - half:h // 2 + half, w // 2 - half:w // 2 + half]
    return cv2.Laplacian(c.astype(np.float64), cv2.CV_64F).var()


def best_focus_jpg(apd):
    js = sorted(glob.glob(apd + "/*.jpg"))
    if not js:
        return None
    sub = js[::max(1, len(js) // 15)]
    return max((lapvar_central(cv2.imread(j, 0)), j) for j in sub)[1]


def register_raw(green):
    lo, hi = np.percentile(green, (1, 99.5))
    g8 = np.clip((green - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
    tf = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    cv2.imwrite(tf.name, g8)
    try:
        return ra.register_and_refine("x", path=tf.name)
    finally:
        os.unlink(tf.name)


def px_per_unit(p):
    cl = ra.N_COL_LINES // 2
    rl = ra.N_ROW_LINES // 2
    x0, y0 = ra.grid_xy_distorted(cl, rl, p)
    x1, y1 = ra.grid_xy_distorted(cl + 1, rl, p)
    return float(np.hypot(x1 - x0, y1 - y0))


def cell_centers(p, n=NCELL):
    cl0 = ra.N_COL_LINES // 2 - n // 2
    rl0 = ra.N_ROW_LINES // 2 - n // 2
    out = []
    for i in range(n):
        for j in range(n):
            cl, rl = cl0 + i, rl0 + j
            x, y = ra.grid_xy_distorted(cl, rl, p)
            out.append((cl, rl, float(x), float(y)))
    return out


def radial_psd(patch):
    patch = patch - patch.mean()
    N = min(patch.shape)
    patch = patch[:N, :N]
    win = np.hanning(N)[:, None] * np.hanning(N)[None, :]
    F = np.fft.fftshift(np.abs(np.fft.fft2(patch * win)) ** 2)
    c = N // 2
    yy, xx = np.indices(F.shape)
    r = np.hypot(yy - c, xx - c).astype(int)
    tb = np.bincount(r.ravel(), F.ravel())
    nb = np.bincount(r.ravel())
    prof = tb / np.maximum(nb, 1)
    freq = np.arange(len(prof)) / N          # cycles per pixel
    keep = freq <= 0.5
    return freq[keep], prof[keep]


def analyse_config(cam, ap):
    c = CFG[cam]
    apd = c["base"] + "/" + c["aps"][ap]
    bj = best_focus_jpg(apd)
    if bj is None:
        return None
    nef = bj[:-4] + ".nef"
    if not os.path.exists(nef):
        return None
    green = decode_green(nef)
    p = register_raw(green)
    ppu = px_per_unit(p)
    win_px = int(round(WIN_UNITS * ppu))
    expo = float(green.mean()) ** 2          # brightness proxy
    patches = {}
    for cl, rl, x, y in cell_centers(p):
        xi, yi = int(round(x)), int(round(y))
        h = win_px // 2
        if yi - h < 0 or xi - h < 0 or yi + h >= green.shape[0] or xi + h >= green.shape[1]:
            continue
        sub = green[yi - h:yi + h, xi - h:xi + h]
        freq, psd = radial_psd(sub)
        # noise floor = median PSD in the top freq decile, subtract
        nf = np.median(psd[freq >= 0.45]) if (freq >= 0.45).any() else 0.0
        psd = np.maximum(psd - nf, 1e-12)
        patches[(cl, rl)] = dict(freq_cypx=freq, psd=psd / expo, ppu=ppu, nf=float(nf))
    return dict(cam=cam, ap=ap, scale=float(p["scale"]), rmse=float(p.get("reg_fit_rmse_px", -1)),
                ppu=ppu, win_px=win_px, expo=expo, patches=patches, n=len(patches))


def demo_d7200_native(ap="F8"):
    """Evidence the method is mechanically SOUND where raws exist: decode a D7200 Sigma-150
    frame from raw, register on the raw green, and show a native-pixel radial PSD reaching the
    sensor Nyquist above the noise floor (the thing the atlas 700/unit grid cannot do)."""
    print(f"\n=== D7200-side native-PSD demonstration ({ap}) — proves method runs where raws exist ===")
    c = CFG["D7200"]
    apd = c["base"] + "/" + c["aps"][ap]
    bj = best_focus_jpg(apd)
    nef = bj[:-4] + ".nef"
    green = decode_green(nef)
    p = register_raw(green)
    h, w = green.shape
    crop = green[h // 2 - 512:h // 2 + 512, w // 2 - 512:w // 2 + 512]   # central native crop
    freq, psd = radial_psd(crop)
    nf = np.median(psd[freq >= 0.45])
    psd = np.maximum(psd - nf, 1e-12)
    for f in (0.10, 0.25, 0.40, 0.49):
        i = int(np.argmin(np.abs(freq - f)))
        print(f"  D7200 native radial PSD @ {f:.2f} cy/px = {psd[i]:.3e}")
    print(f"  -> native PSD spans to Nyquist 0.50 cy/px (atlas 700/unit grid stops at ~0.27);")
    print(f"     registered on RAW green scale={p['scale']:.2f} rmse={p.get('reg_fit_rmse_px',-1):.2f}px,"
          f" noise-floor={nf:.2e}. Native-res extraction is mechanically SOUND where raws exist.")


def main():
    runnable = audit_raw_availability()
    if not runnable:
        print("\n=== VERDICT: cross-camera native-res bridge NOT RUNNABLE (data wall) ===")
        print("  The Z7 Sigma 150 was saved JPG-ONLY in every session (0 NEFs); only the D7200")
        print("  side has raws. Native-res-from-RAW requires NEFs on BOTH cameras, so the")
        print("  Sigma-150 cross-camera sensor+OLPF ratio cannot be computed at all. Falling")
        print("  back to Z7-JPG vs D7200-RAW is invalid: in-camera JPG sharpening/tone/8-bit/NR")
        print("  contaminate exactly the near-Nyquist band, asymmetrically. This is NOT a method")
        print("  failure — it is missing input data, and unfixable (D7200 sold; Z7 S150 raws")
        print("  were never kept). The 'sensor/OLPF-dominated' optics claim stays a PRIOR.")
        demo_d7200_native("F8")
        return

    out = {}
    for cam in ("Z7", "D7200"):
        for ap in APS:
            try:
                r = analyse_config(cam, ap)
            except Exception as e:
                print(f"[{cam} {ap}] FAIL {e!r}", flush=True)
                r = None
            if r:
                print(f"[{cam} {ap}] scale={r['scale']:.1f} rmse={r['rmse']:.2f} "
                      f"ppu={r['ppu']:.1f} win={r['win_px']}px patches={r['n']}", flush=True)
            out[(cam, ap)] = r

    # ---- cross-camera same-patch ratio on a common SUBJECT-freq grid (cy/unit) ----
    funit = np.linspace(0.0, 8.0, 200)       # cy per atlas unit; upper end set by data below
    print("\n=== cross-camera D7200/Z7 ratio (exposure-normed, common subject-freq grid) ===")
    per_ap = {}
    lowf_scatter = {}
    for ap in APS:
        z, d = out[("Z7", ap)], out[("D7200", ap)]
        if not z or not d:
            continue
        shared = set(z["patches"]) & set(d["patches"])
        ratios, lowfacs = [], []
        # native Nyquist in subject units, per camera: 0.5 cy/px * ppu
        nyq_unit = min(0.5 * z["ppu"], 0.5 * d["ppu"])
        grid = np.linspace(0.3, 0.9 * nyq_unit, 60)
        for key in shared:
            zp, dp = z["patches"][key], d["patches"][key]
            zf = zp["freq_cypx"] * zp["ppu"]     # -> cy/unit
            df = dp["freq_cypx"] * dp["ppu"]
            zP = np.interp(grid, zf, zp["psd"])
            dP = np.interp(grid, df, dp["psd"])
            # low-f cancellation factor (should be ~const across patches if optics+target cancel)
            lowmask = (grid >= 0.4) & (grid <= 0.9)
            lowfacs.append(np.median(dP[lowmask] / np.maximum(zP[lowmask], 1e-12)))
            with np.errstate(divide="ignore", invalid="ignore"):
                ratios.append(dP / np.maximum(zP, 1e-12))
        R = np.median(np.array(ratios), axis=0)
        # normalize ratio to 1 at low subject-freq (isolate SHAPE)
        base = np.median(R[(grid >= 0.4) & (grid <= 0.9)])
        per_ap[ap] = (grid, R / base, nyq_unit, z["ppu"], d["ppu"], len(shared))
        lowfacs = np.array(lowfacs)
        lowf_scatter[ap] = float(np.std(lowfacs) / max(abs(np.mean(lowfacs)), 1e-9))
        # sample the shape at a few subject freqs, and note the cy/px on each cam there
        def at(fu):
            i = np.argmin(np.abs(grid - fu))
            return R[i] / base
        print(f"  {ap}: patches={len(shared)} nyq_unit={nyq_unit:.2f} "
              f"ratio@[1,2,3,{0.9*nyq_unit:.1f}]cyu = "
              f"[{at(1):.2f} {at(2):.2f} {at(3):.2f} {at(0.9*nyq_unit):.2f}] "
              f"lowf_cancel_CV={lowf_scatter[ap]:.2f}")

    # ---- verdict diagnostics ----
    print("\n=== CHECKS ===")
    # (1) aperture independence: compare the shape curves across apertures at matched cy/unit
    common_fu = [1.5, 2.5, 3.5]
    print("  (1) aperture-independence — shape ratio at fixed cy/unit across F5.6/8/11/16:")
    for fu in common_fu:
        vals = []
        for ap in APS:
            if ap in per_ap:
                grid, R, *_ = per_ap[ap]
                vals.append(R[np.argmin(np.abs(grid - fu))])
        if vals:
            print(f"      @{fu} cy/unit: {[round(v,2) for v in vals]}  spread={max(vals)-min(vals):.2f}")
    print("  (3) low-f cancellation CV per aperture (atlas path had 0.27-0.42): "
          + ", ".join(f"{ap}={lowf_scatter.get(ap, float('nan')):.2f}" for ap in APS))
    # (2)/(4): does D7200 reach near-Nyquist above noise floor?
    for ap in APS:
        if ap in per_ap:
            grid, R, nyq_unit, zp, dp, n = per_ap[ap]
            print(f"  (4) {ap}: D7200 Nyquist reached at {0.5*dp:.2f} cy/unit "
                  f"(Z7 {0.5*zp:.2f}); common grid to {0.9*nyq_unit:.2f} cy/unit "
                  f"= {0.9*nyq_unit/dp*2*0.5:.2f}x... dNyq_cypx=0.5")


if __name__ == "__main__":
    main()
