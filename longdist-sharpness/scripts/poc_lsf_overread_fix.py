"""POC: fix the slanted-edge MTF over-read (LONGDIST_HANDOVER §5.6e).

The known-edge MTF estimator (`poc_known_edge_mtf50.measure_edge_metrics`)
over-reads MTF50 above the diffraction ceiling at f/11-f/16 and produces
MTF@Nyquist outliers > 1.0 even on linear, unsharpened RAW. The
2026-06-28 diagnosis localises the cause to **LSF asymmetry**: the
end-tapered ROI keeps the full, asymmetric noisy LSF tails, and the
longer tail inflates the high-frequency FFT magnitude. The standard ISO
12233 remedy is to window the LSF *symmetrically about its centroid*.

This POC compares LSF-handling variants on two independent yardsticks:

  A. SYNTHETIC — build an ESF from a known PSF (symmetric Gaussian range,
     asymmetric half-Gaussian = the over-read driver, diffraction Airy),
     optionally off-centred in the array and noisy, with the *analytic*
     MTF50 / MTF@Nyquist as ground truth. Measures each variant's bias.

  B. REAL RAW — 2026-06-28 brick-wall NEFs (bare Z 100-400 @ 400 mm) at
     f/8, f/11, f/16. The diffraction ceiling (optics.py) is a hard
     upper bound on MTF50; a correct variant must sit under it and keep
     MTF@Nyq <= 1.0. Ordering across apertures must stay monotonic.

Run (on nufan, faster cores):
    direnv exec . uv run python -u scripts/poc_lsf_overread_fix.py
    direnv exec . uv run python -u scripts/poc_lsf_overread_fix.py --synthetic-only
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import numpy as np
from scipy.special import erf, j1
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent))
import poc_known_edge_mtf50 as ke  # noqa: E402

# tile-sharpness optics module for the diffraction ceiling.
_TS = Path(__file__).resolve().parents[2] / "tile-sharpness" / "src"
sys.path.insert(0, str(_TS))
try:
    from tile_sharpness import optics  # noqa: E402
    HAVE_OPTICS = True
except Exception:  # pragma: no cover
    HAVE_OPTICS = False

OUT = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

Z7_PITCH_UM = 4.35
BIN = 0.25  # px, the supersample spacing used by measure_edge_metrics

# ---- candidate LSF-handling variants ------------------------------------
# kwargs forwarded to ke._esf_to_metrics
VARIANTS: dict[str, dict] = {
    "baseline_endtaper":      dict(window="endtaper"),
    "centroid_hann_full":     dict(window="centroid_hann"),
    "centroid_tukey_hw8":     dict(window="centroid_tukey", half_window_px=8),
    "centroid_tukey_hw12":    dict(window="centroid_tukey", half_window_px=12),
    "centroid_tukey_hw16":    dict(window="centroid_tukey", half_window_px=16),
    "centroid_tukey_hw24":    dict(window="centroid_tukey", half_window_px=24),
    "centroid_hamming_hw12":  dict(window="centroid_hamming", half_window_px=12),
    "centroid_tukey_hw12_dc": dict(window="centroid_tukey", half_window_px=12,
                                   deriv_correct=True),
    "mirror_min":             dict(mirror="min"),
    "mirror_mean":            dict(mirror="mean"),
}


# =========================================================================
# A. SYNTHETIC
# =========================================================================

def _psf_fine(kind: str, param, xf: np.ndarray):
    """PSF sampled on fine grid xf (normalised to sum=1)."""
    if kind == "gauss":
        s = float(param)
        p = np.exp(-0.5 * (xf / s) ** 2)
    elif kind == "asym":          # half-Gaussian: different sigma each side
        sL, sR = param
        p = np.where(xf < 0, np.exp(-0.5 * (xf / sL) ** 2),
                     np.exp(-0.5 * (xf / sR) ** 2))
    elif kind == "airy":          # diffraction PSF, param = (lambda_um, N)
        lam, N = param
        # cutoff (cy/px) and Airy radius in px. Airy PSF ~ (2 J1(z)/z)^2,
        # z = pi * r / (lambda*N) in length; convert to px via pitch.
        lam_px = (lam * 1e-3) / Z7_PITCH_UM * 1000.0  # lambda in px units? keep simple
        # Work directly in px: spatial scale a = lambda*N / pitch (px).
        a = (lam * N) / Z7_PITCH_UM
        z = np.pi * np.abs(xf) / a
        z = np.where(z == 0, 1e-9, z)
        p = (2 * j1(z) / z) ** 2
    else:
        raise ValueError(kind)
    p = np.clip(p, 0, None)
    return p / p.sum()


def _truth_mtf(kind: str, param, xf: np.ndarray, dxf: float):
    """Analytic MTF50 (cy/px) and MTF@Nyquist (value at 0.5) from the PSF."""
    p = _psf_fine(kind, param, xf)
    f = np.linspace(0, 0.5, 2001)
    # OTF(f) = sum p(x) exp(-i 2pi f x) dx ; MTF = |OTF| (p real, sum=1 -> OTF(0)=1)
    phase = np.exp(-1j * 2 * np.pi * np.outer(f, xf))
    otf = np.abs(phase @ p)
    nyq = float(otf[-1])
    below = np.where(otf < 0.5)[0]
    if len(below) == 0 or below[0] == 0:
        mtf50 = 0.5
    else:
        i = below[0]
        f0, f1 = f[i - 1], f[i]; m0, m1 = otf[i - 1], otf[i]
        mtf50 = float(f0 + (f1 - f0) * (m0 - 0.5) / (m0 - m1))
    return mtf50, nyq


def _synth_esf(kind: str, param, offset_px: float, noise: float,
               rng: np.random.Generator, n: int = 360, bg_slope: float = 0.0,
               bg_texture: float = 0.0):
    """ESF on the 0.25 px grid: integral of PSF, edge shifted by offset.

    ``bg_slope`` adds a linear trend across the whole window (a non-flat
    background — the real over-read driver: it makes the endpoint-median
    contrast estimate wrong, scaling the un-renormalised MTF). With an
    off-centre edge the two plateaus then mis-estimate asymmetrically.
    ``bg_texture`` adds low-frequency plateau wobble (brick speckle).
    """
    xf = np.arange(-30, 30, 0.01)
    p = _psf_fine(kind, param, xf)
    # ESF as cumulative PSF (step convolved with PSF), evaluated at grid pts.
    cdf = np.cumsum(p)                      # 0..1 across xf
    grid = (np.arange(n) - n / 2) * BIN - offset_px
    esf = np.interp(grid, xf, cdf, left=0.0, right=1.0)
    contrast = 1000.0
    esf = esf * contrast
    if bg_slope:
        ramp = (np.arange(n) - n / 2) / n
        esf = esf + bg_slope * contrast * ramp
    if bg_texture:
        wob = rng.normal(0, 1, size=n)
        wob = ndi.gaussian_filter1d(wob, sigma=12.0)
        wob /= max(wob.std(), 1e-9)
        esf = esf + bg_texture * contrast * wob
    if noise > 0:
        esf = esf + rng.normal(0, noise * contrast, size=esf.shape)
    esf = ndi.gaussian_filter1d(esf, sigma=1.0)   # match measure_edge_metrics
    return esf


SYNTH_CASES = [
    ("gauss", 0.6, "g0.6 sharp"),
    ("gauss", 0.9, "g0.9"),
    ("gauss", 1.2, "g1.2"),
    ("gauss", 1.6, "g1.6"),
    ("gauss", 2.2, "g2.2 soft"),
    ("asym", (0.7, 1.8), "asym 0.7/1.8"),
    ("asym", (1.0, 2.6), "asym 1.0/2.6"),
    ("asym", (0.6, 1.2), "asym 0.6/1.2"),
    ("airy", (0.55, 11.0), "airy f/11"),
    ("airy", (0.55, 16.0), "airy f/16"),
    ("airy", (0.55, 8.0), "airy f/8"),
]
OFFSETS = [0.0, 8.0, -12.0]
NOISE = 0.004
REPS = 24
# (bg_slope, bg_texture): "clean" = flat plateaus; "stress" = non-flat
# background (the real over-read driver — wrong endpoint-contrast estimate).
REGIMES = {
    "clean":  (0.0, 0.0),
    "stress": (0.10, 0.06),
}


def _synth_regime(slope, texture, rng, xf):
    per_variant = {v: dict(b50=[], s50=[], over=0, ntot=0, nyqx=[], badmtf50=0)
                   for v in VARIANTS}
    for kind, param, label in SYNTH_CASES:
        t50, tnyq = _truth_mtf(kind, param, xf, 0.01)
        for off in OFFSETS:
            for _ in range(REPS):
                esf = _synth_esf(kind, param, off, NOISE, rng,
                                 bg_slope=slope, bg_texture=texture)
                for vname, kw in VARIANTS.items():
                    r = ke._esf_to_metrics(esf, BIN, **kw)
                    m50, mnyq = r["mtf50"], r["mtf_at_nyquist"]
                    d = per_variant[vname]
                    d["ntot"] += 1
                    if m50 == m50 and t50 > 0:
                        d["b50"].append(abs(m50 / t50 - 1))
                        d["s50"].append(m50 / t50 - 1)
                        if m50 > t50 * 1.20:       # over the true MTF50 by >20%
                            d["badmtf50"] += 1
                    if mnyq == mnyq:
                        d["nyqx"].append(mnyq - tnyq)
                        if mnyq > 1.0 or mnyq > tnyq + 0.15:
                            d["over"] += 1
    return per_variant


def run_synthetic():
    rng = np.random.default_rng(12345)
    xf = np.arange(-30, 30, 0.01)
    lines = ["## A. Synthetic (analytic-MTF ground truth)\n",
             f"{len(SYNTH_CASES)} PSF cases x {len(OFFSETS)} offsets x {REPS} reps, "
             f"noise={NOISE}. **stress** adds a non-flat background "
             "(slope+texture) — the over-read driver.\n"]
    summary = {}
    for rname, (slope, tex) in REGIMES.items():
        pv = _synth_regime(slope, tex, rng, xf)
        lines += [f"\n### regime: {rname} (bg_slope={slope}, bg_texture={tex})\n",
                  "| variant | median \\|bias50\\| | signed bias50 | MTF50-overread frac | MTF@Nyq overread frac | med Nyq excess |",
                  "|---|---|---|---|---|---|"]
        for vname, d in pv.items():
            ab = statistics.median(d["b50"]) if d["b50"] else float("nan")
            sb = statistics.median(d["s50"]) if d["s50"] else float("nan")
            bad = d["badmtf50"] / max(len(d["b50"]), 1)
            of = d["over"] / max(d["ntot"], 1)
            nx = statistics.median(d["nyqx"]) if d["nyqx"] else float("nan")
            summary[(rname, vname)] = dict(abias=ab, sbias=sb, badmtf50=bad,
                                           over=of, nyqx=nx)
            lines.append(f"| {vname} | {ab*100:.1f}% | {sb*100:+.1f}% | "
                         f"{bad*100:.0f}% | {of*100:.0f}% | {nx:+.3f} |")
    return "\n".join(lines), summary


# =========================================================================
# B. REAL RAW (2026-06-28 brick)
# =========================================================================

ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-06-28")
BARE = "NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO{iso}"
TC14 = "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x ISO{iso}"


def _ceiling_cy_px(n_marked: float) -> float:
    if not HAVE_OPTICS:
        # fallback: 0.404 / (lambda*N) lp/mm * pitch_mm
        lp = 0.404 / (0.55e-3 * n_marked)
        return lp * (Z7_PITCH_UM * 1e-3)
    lp = optics.diffraction_mtf50_sensor_lpmm(n_marked)
    return lp * (Z7_PITCH_UM * 1e-3)


def _af_frames(folder, rawpoc):
    """In-focus frames only (Pinpoint AF, Silent=Off) — no focus-shift
    stack. Avoids the max-over-frames focus-pick that biases MTF50 up."""
    nefs = sorted(folder.glob("*.nef"))
    sm = rawpoc.silent_map(nefs)
    return [n for n in nefs if sm.get(n) == "Off"]


def _pct(xs, q):
    if not xs:
        return float("nan")
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def run_real(stride: int = 8):
    import poc_longdist_tc14_brick as brick
    import poc_longdist_tc14_raw as rawpoc

    def folders(tmpl, focal, ap):
        return [d for iso in ("100", "500")
                if (d := ROOT / tmpl.format(iso=iso) / focal / ap).is_dir()]

    configs = [
        ("bare f/8", BARE, "400.0 mm", "F8", 8.0),
        ("bare f/11", BARE, "400.0 mm", "F11", 11.0),
        ("bare f/16", BARE, "400.0 mm", "F16", 16.0),
        ("tc14 f/8", TC14, "560.0 mm", "F8", 8.0),
        ("tc14 f/11", TC14, "560.0 mm", "F11", 11.0),
    ]
    lines = ["\n## B. Real RAW — 2026-06-28 brick wall (in-focus AF frames; "
             "per-edge MEDIAN across frames — NO max-over-frames pick)\n",
             "MTF50 in cy/sensor-px. Ceiling = diffraction MTF50 at the marked "
             "f-number (hard upper bound; M~0). At f/16 the lens is "
             "diffraction-limited so true MTF50 ~= ceiling and true MTF@Nyq ~= 0. "
             "A correct variant: per-edge **median MTF50 distribution centred at/below "
             "the ceiling**, low over-ceiling fraction, **MTF@Nyq tail near 0** "
             "(p95 << 1, not the max-pick artefact), ordering f/8 > f/11 > f/16.\n",
             "| config | ceiling | variant | n edges | med50 | p90-50 | over-ceil | med Nyq | p95 Nyq | Nyq>1 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    real_summary = {}
    for cname, tmpl, focal, ap, nmark in configs:
        fs = folders(tmpl, focal, ap)
        if not fs:
            lines.append(f"| {cname} | — | (no folder) | | | | | | | |"); continue
        ceil = _ceiling_cy_px(nmark)
        ref_lin = rawpoc.develop_luma(rawpoc.detect_ref(fs[0]))
        H, Wd = ref_lin.shape
        specs = brick.find_mortar_edges(rawpoc.to_uint8(ref_lin), Wd, H)
        if not specs:
            lines.append(f"| {cname} | {ceil:.3f} | (no edges) | | | | | | | |"); continue
        frames = [p for f in fs for p in _af_frames(f, rawpoc)]
        # Per (edge, variant): collect across-frame measurements, then take
        # the per-edge MEDIAN (robust central estimate; defocus and spurious
        # spikes both fall away). The over-read question is about the central
        # tendency vs the ceiling, not the luckiest frame.
        acc = {v: [[] for _ in specs] for v in VARIANTS}      # m50 per edge
        accn = {v: [[] for _ in specs] for v in VARIANTS}     # nyq per edge
        for nef in frames:
            lin = rawpoc.develop_luma(nef)
            for i, s in enumerate(specs):
                built = ke._build_esf(lin, s)
                if built is None:
                    continue
                esf, bs = built
                for vname, kw in VARIANTS.items():
                    r = ke._esf_to_metrics(esf, bs, **kw)
                    if r["mtf50"] == r["mtf50"]:
                        acc[vname][i].append(r["mtf50"])
                    if r["mtf_at_nyquist"] == r["mtf_at_nyquist"]:
                        accn[vname][i].append(r["mtf_at_nyquist"])
            del lin
        for vname in VARIANTS:
            e50 = [statistics.median(c) for c in acc[vname] if c]
            enq = [statistics.median(c) for c in accn[vname] if c]
            if not e50:
                continue
            med50 = statistics.median(e50)
            p90_50 = _pct(e50, 0.90)
            overc = sum(x > ceil for x in e50) / len(e50)
            medn = statistics.median(enq) if enq else float("nan")
            p95n = _pct(enq, 0.95)
            nyq1 = (sum(x > 1.0 for x in enq) / len(enq)) if enq else float("nan")
            real_summary[(cname, vname)] = dict(
                ceil=ceil, med50=med50, p90_50=p90_50, overc=overc,
                medn=medn, p95n=p95n, nyq1=nyq1, n=len(e50))
            lines.append(
                f"| {cname} | {ceil:.3f} | {vname} | {len(e50)} | {med50:.3f} | "
                f"{p90_50:.3f} | {overc*100:.0f}% | {medn:.3f} | {p95n:.2f} | {nyq1*100:.0f}% |")
    return "\n".join(lines), real_summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic-only", action="store_true")
    ap.add_argument("--stride", type=int, default=8)
    args = ap.parse_args()

    parts = ["# LSF over-read fix — variant comparison\n"]
    syn_txt, syn = run_synthetic()
    parts.append(syn_txt)
    print(syn_txt)

    if not args.synthetic_only:
        real_txt, real = run_real(stride=args.stride)
        parts.append(real_txt)
        print(real_txt)

    (OUT / "summary.md").write_text("\n".join(parts) + "\n")
    print(f"\nWrote {OUT/'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
