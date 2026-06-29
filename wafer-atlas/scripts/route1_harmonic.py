"""Route 1 — harmonic-decay MTF on the flat 2B serpent line grating.

Register + locate the de-rotated 2B serpent block, pick the cleanest uniform-pitch
horizontal-line sub-window (strongest periodic peak, low pitch variance), then
compute the self-normalised MTF shape MTF(n*f0)/MTF(f0) via harmonic_mtf. Gate
each point <= 1 and <= the diffraction MTF at n*f0 (optics.diffraction_mtf_at).
Cross-check the fundamental contrast against periodic_fft.periodic_contrast.

Subject frequency of harmonic n = n*f0 * M ; lp/mm = that * 229.9.
Run on nufan.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np
import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib_2b as L  # noqa: E402
sys.path.insert(0, str(HERE.parent.parent / "tile-sharpness" / "src"))
from tile_sharpness.methods import harmonic_mtf as hm  # noqa: E402
from tile_sharpness.methods import periodic_fft as pf  # noqa: E402
from tile_sharpness import optics  # noqa: E402


def best_line_window(block, M, win_h=None, axis="v"):
    """Slide a window over the block; return (y0,y1,prof,f0,peakiness) for the
    sub-window with the strongest, cleanest horizontal-line fundamental.

    axis 'v' = lines are horizontal (vary along rows -> profile = column-collapse).
    Window height ~ enough to hold many periods; we collapse along x (columns) to
    get the perpendicular profile, FFT it."""
    H, W = block.shape
    x0, x1 = int(0.18 * W), int(0.82 * W)
    if win_h is None:
        win_h = int(np.clip(0.32 * H, 120, 600))
    best = None
    step = max(8, win_h // 6)
    for y0 in range(0, max(1, H - win_h), step):
        y1 = y0 + win_h
        sub = block[y0:y1, x0:x1]
        prof = sub.mean(axis=1)
        p = prof - prof.mean()
        n = p.size
        if n < 32:
            continue
        amp = np.abs(np.fft.rfft(p * np.hanning(n)))
        fr = np.fft.rfftfreq(n, 1.0)
        # serpent line subject pitch ~ tens of px; search a broad band, avoid DC
        band = (fr >= 0.02) & (fr <= 0.30)
        if not band.any():
            continue
        k = np.where(band)[0][np.argmax(amp[band])]
        peak = amp[k]
        med = np.median(amp[band])
        peakiness = peak / (med + 1e-6)
        f0 = fr[k]
        # require enough periods and a real peak
        if n * f0 < 4 or peakiness < 4:
            continue
        contrast = float(np.percentile(prof, 85) - np.percentile(prof, 15))
        score = peakiness * contrast
        rec = (score, y0, y1, prof.copy(), float(f0), float(peakiness), contrast)
        if best is None or score > best[0]:
            best = rec
    return best


def measure(lens, mag, ap):
    ap_dir = L.RAW / lens / mag / ap
    rmse, aff, jp0, jpgs = L.register_best(ap_dir)
    if aff is None:
        return dict(config=f"{lens}|{mag}|{ap}", ok=False, reason="reg-fail")
    M = aff["scale"] / L.M_ANCHOR_SCALE
    n_marked = float(ap.replace("F", "").replace("_", "."))
    n_eff = n_marked * (1.0 + M)
    info = L.get_block(jp0, aff, want_type=(2, 1), derotate=True)
    if info is None:
        return dict(config=f"{lens}|{mag}|{ap}", ok=False, reason="no-2b")
    # field-tilt-aware best focus near block centre
    full0 = info["full"]; bbox = info["bbox"]
    cyo = 0.5 * (bbox[1] + bbox[3]); cxo = 0.5 * (bbox[0] + bbox[2])

    def lv_at(g):
        y0, y1 = max(0, int(cyo - 150)), min(g.shape[0], int(cyo + 150))
        x0, x1 = max(0, int(cxo - 150)), min(g.shape[1], int(cxo + 150))
        return cv2.Laplacian(g[y0:y1, x0:x1].astype(np.float32), cv2.CV_32F).var()
    bestjp, bl = jp0, -1
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        v = lv_at(g)
        if v > bl:
            bl, bestjp = v, jp
    info = L.get_block(bestjp, aff, want_type=(2, 1), derotate=True)
    block = info["block"]
    bw = best_line_window(block, M)
    if bw is None:
        return dict(config=f"{lens}|{mag}|{ap}", ok=False, reason="no-clean-grating", M=M)
    score, y0, y1, prof, f0, peakiness, contrast = bw

    res = hm.harmonic_mtf(prof, f0, n_harmonics=6)
    pc = pf.periodic_contrast(block[y0:y1, int(0.18*block.shape[1]):int(0.82*block.shape[1])],
                              pitch_px=1.0 / f0, axis="v")
    out = dict(config=f"{lens}|{mag}|{ap}", ok=True, M=M, n_eff=n_eff, rmse=rmse,
               label=info["label"], jp=bestjp.name, f0=f0, pitch=1.0 / f0,
               peakiness=peakiness, contrast=contrast, y0=y0, y1=y1,
               periodic_contrast=(pc["contrast"] if pc else None))
    if res is None:
        out["harmonic"] = None
        out["reason2"] = "harmonics-unresolved"
        return out
    # ceiling per harmonic (sensor-plane diffraction MTF at n*f0 cy/px -> lp/mm)
    f_lpmm = [f * L.LPMM_PER_CYPX for f in res["f_cy_per_px"]]
    ceil = [optics.diffraction_mtf_at(fl, n_eff) for fl in f_lpmm]
    # MTF(f0) absolute ceiling at the fundamental too
    ratio = res["mtf_ratio"]
    # the self-normalised shape is MTF(n f0)/MTF(f0); to gate against absolute
    # ceiling we compare ratio[n] <= ceil[n]/ceil[0] (the ceiling's own shape) is
    # NOT required; instead gate ratio<=1 (monotone) and the ABSOLUTE check is:
    # ratio cannot exceed ceil[n]/MTF(f0)_true, but MTF(f0)_true<=ceil[0] so the
    # strongest valid statement is ratio[n] <= ceil[n]/ (something<=ceil[0]).
    # Simplest physical gate: the implied MTF shape must be <= the ceiling SHAPE
    # (ceil[n]/ceil[0]) only if the lens is diffraction-limited; in general a real
    # MTF decays FASTER than diffraction, so ratio[n] <= ceil[n]/ceil[0] is the
    # ceiling on the self-normalised shape. Flag violations.
    ceil_shape = [c / ceil[0] if ceil[0] > 0 else np.nan for c in ceil]
    out["harmonic"] = dict(f_cy_per_px=res["f_cy_per_px"], f_subj_lpmm=[f*M*L.LPMM_PER_CYPX for f in res["f_cy_per_px"]],
                           mtf_ratio=ratio, snr=res["snr"], duty=res["duty"],
                           raw_ratio=res["raw_ratio"], ceil_shape=ceil_shape,
                           over1=[r > 1.02 for r in ratio],
                           over_ceil=[ (r > cs + 0.02) if np.isfinite(cs) else False
                                       for r, cs in zip(ratio, ceil_shape)])
    return out


def fmt(o):
    if not o["ok"]:
        return f"{o['config']}: FAIL ({o['reason']})" + (f" M={o.get('M'):.2f}" if o.get('M') else "")
    s = [f"\n=== {o['config']} ===",
         f" M={o['M']:.3f} n_eff={o['n_eff']:.1f} rmse={o['rmse']:.2f} die={o['label']} "
         f"f0={o['f0']:.4f}cy/px pitch={o['pitch']:.1f}px peakiness={o['peakiness']:.1f} "
         f"contrast={o['contrast']:.0f} window_y=[{o['y0']},{o['y1']}] "
         f"periodic_contrast(f0)={o['periodic_contrast']}"]
    h = o["harmonic"]
    if h is None:
        s.append(f" harmonic: {o.get('reason2')}")
        return "\n".join(s)
    s.append(f" duty={h['duty']:.2f}")
    s.append(f" {'harm':>5} {'f_cypx':>8} {'f_subj':>8} {'raw':>7} {'MTF_ratio':>10} {'ceil_shape':>10} {'snr':>7} flags")
    for i, fc in enumerate(h["f_cy_per_px"]):
        flag = []
        if h["over1"][i]:
            flag.append(">1")
        if h["over_ceil"][i]:
            flag.append(">ceil")
        if h["snr"][i] < 3:
            flag.append("lowSNR")
        s.append(f" {i+1:>5} {fc:>8.4f} {h['f_subj_lpmm'][i]:>8.1f} {h['raw_ratio'][i]:>7.3f} "
                 f"{h['mtf_ratio'][i]:>10.3f} {h['ceil_shape'][i]:>10.3f} {h['snr'][i]:>7.1f} {','.join(flag)}")
    return "\n".join(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="+", default=["Nikon AF Micro-Nikkor 200mm f_4D IF-ED|1_1|F8"])
    args = ap.parse_args()
    for t in args.configs:
        lens, mag, apr = t.split("|")
        print(fmt(measure(lens, mag, apr)))


if __name__ == "__main__":
    main()
