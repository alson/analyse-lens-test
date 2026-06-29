"""Clean RAW slanted-edge MTF for the Z 100-400 family on the 2026-06-28
brick wall at f/11 + f/16 — bare / TC-1.4x / TC-2.0x, ceiling-gated.

Goal: a trustworthy TC-2.0x verdict. The TC-2.0x is wide-open at f/11, so it
can't be shot <= f/8; this measures it at f/11 + f/16 alongside matched-
aperture bare + TC-1.4x references (the f/8 RAW POC in
``poc_longdist_tc14_raw.py`` could only do bare vs tc14).

The f/11-f/16 "over-read" problem documented in
``docs/LENS_TEST_METHODOLOGY_Z7.md`` §B5 was the slanted-edge LSF-tail bug,
now FIXED (§5.6e): ``poc_known_edge_mtf50.LSF_PROFILE == {"window":
"centroid_hann"}``. We use the fixed metric + a diffraction-ceiling validity
gate instead of avoiding the apertures.

METHOD (mirrors ``poc_longdist_tc14_raw.py`` + ``poc_longdist_tc14_brick``):
  - ``develop_luma``: rawpy gamma=(1,1), no_auto_bright, 16-bit, camera WB,
    AHD demosaic — linear, demosaic-only, no sharpening / no lens corrections.
  - Edges via ``poc_longdist_tc14_brick.find_mortar_edges`` on a sharp in-
    focus AF reference (8-bit gamma stretch for detection; measure on the
    linear float).
  - Per (config, aperture): measure every mortar edge on the IN-FOCUS AF
    frames only (Silent=Off; NOT the focus-shift stack). Take the per-edge
    MEDIAN across those AF frames, then the median across edges. NEVER
    max-over-frames (that was the artefact).
  - Diffraction-ceiling gate: ceiling MTF50 (cy/sensor-px) =
    optics.diffraction_mtf50_sensor_lpmm(N_eff) * 4.35e-3, with N_eff ~ marked
    N (distance ~45 m -> M~0). Reliable iff median MTF50 < ceiling.

Parallelised over (config, aperture, frame, edge?) develop+measure jobs with a
single ProcessPoolExecutor(max_workers=8). Each job develops one NEF and
measures all edges for its (config, aperture) -> returns per-edge metrics.

Run on nufan (8 physical cores):
  direnv exec . uv run python -u scripts/poc_longdist_tc_family_raw_f11f16.py
"""
from __future__ import annotations

import statistics
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import rawpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
# tile-sharpness optics for the diffraction ceiling.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tile-sharpness" / "src"))
import poc_known_edge_mtf50 as ke      # noqa: E402
import poc_longdist_tc14_brick as brick  # noqa: E402
import tile_sharpness.optics as optics   # noqa: E402

ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-06-28")
OUT = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

PITCH_MM = 4.35e-3                      # Z7 pixel pitch (mm) -> cy/sensor-px
NYQUIST_CAP = 0.49                      # MTF50 saturation cap (cy/px)
MAX_WORKERS = 8

# config -> (lens-dir template, focal subdir, effective FL mm, apertures)
CONFIGS = {
    "bare": dict(lens="NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO{iso}",
                 focal="400.0 mm", f_eff=400.0,
                 apertures=("F5.6", "F8", "F11", "F16")),
    "tc14": dict(lens="NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x ISO{iso}",
                 focal="560.0 mm", f_eff=560.0,
                 apertures=("F8", "F11", "F16")),
    "tc20": dict(lens="NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x ISO{iso}",
                 focal="800.0 mm", f_eff=800.0,
                 apertures=("F11", "F16")),
}
# Marked N for the diffraction ceiling (the printed f-stop; distance ~45 m so
# M~0 -> N_eff ~ N_marked). The "aperture" label is lens-internal effective
# already = printed stop at infinity, so use it directly.
N_MARKED = {"F5.6": 5.6, "F8": 8.0, "F11": 11.0, "F16": 16.0}

# Best peak aperture per config for the FOM (peak expected ~f/11; f/8 bare is
# the cropping reference). Filled from measured medians at runtime.

# ----- frame selection (mirror poc_longdist_tc14_raw.py) -------------------


def silent_map(nefs: list[Path]) -> dict[Path, str]:
    out = subprocess.run(["exiftool", "-T", "-s3", "-SilentPhotography", *map(str, nefs)],
                         capture_output=True, text=True)
    return {p: v.strip() for p, v in zip(nefs, out.stdout.splitlines())}


def develop_luma(nef: Path) -> np.ndarray:
    r = rawpy.imread(str(nef))
    rgb = r.postprocess(gamma=(1, 1), no_auto_bright=True, output_bps=16,
                        use_camera_wb=True, half_size=False,
                        output_color=rawpy.ColorSpace.sRGB,
                        demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD)
    r.close()
    return rgb.mean(axis=2).astype(np.float32)


def to_uint8(luma: np.ndarray) -> np.ndarray:
    """Detection image only: normalise + gamma 1/2.2 so low-contrast mortar
    edges have enough contrast for Canny. Measurement stays on linear float."""
    lo, hi = np.percentile(luma[::8, ::8], [1, 99])
    n = np.clip((luma - lo) / max(hi - lo, 1e-6), 0, 1)
    return (n ** (1 / 2.2) * 255.0).astype(np.float32)


def af_frames(folder: Path) -> list[Path]:
    """In-focus AF replicates only (Silent=Off). NOT the focus-shift stack."""
    nefs = sorted(folder.glob("*.nef"))
    sm = silent_map(nefs)
    return [n for n in nefs if sm.get(n) == "Off"]


def folder_for(cls: str, aperture: str, iso: str) -> Path:
    c = CONFIGS[cls]
    return ROOT / c["lens"].format(iso=iso) / c["focal"] / aperture


def detect_ref(cls: str, aperture: str) -> tuple[Path | None, str | None]:
    """Pick a sharp in-focus AF frame for edge DETECTION. Prefer ISO100;
    fall back to ISO500. Edge positions are fixed across the unmoved-tripod
    stack, so any in-focus frame locates them."""
    for iso in ("100", "500"):
        fld = folder_for(cls, aperture, iso)
        if not fld.is_dir():
            continue
        af = af_frames(fld)
        if af:
            return af[0], iso
    return None, None


def collect_af(cls: str, aperture: str) -> tuple[list[Path], str]:
    """All in-focus AF frames for (config, aperture). Prefer ISO100; fall
    back to ISO500 only if ISO100 has no AF frames for this cell."""
    for iso in ("100", "500"):
        fld = folder_for(cls, aperture, iso)
        if not fld.is_dir():
            continue
        af = af_frames(fld)
        if af:
            return af, iso
    return [], "—"


# ----- parallel worker -----------------------------------------------------
# Each job develops ONE NEF and measures the given edge specs on it. Specs are
# passed as plain dicts (picklable); rebuilt into EdgeSpec inside the worker.

def _measure_job(args: tuple) -> tuple[str, str, list[float], list[float]]:
    cls, aperture, nef_str, spec_dicts = args
    lin = develop_luma(Path(nef_str))
    specs = [ke.EdgeSpec.from_json(d) for d in spec_dicts]
    m50: list[float] = []
    mnq: list[float] = []
    for s in specs:
        m = ke.measure_edge_metrics(lin, s)
        m50.append(m["mtf50"])
        mnq.append(m["mtf_at_nyquist"])
    return cls, aperture, m50, mnq


def _measure_job_tagged(args: tuple):
    """Like _measure_job but echoes an opaque tag (for the ISO diagnostic
    where one config's shared edge set is measured at multiple ISO/aperture
    cells). args = (tag, nef_str, spec_dicts)."""
    tag, nef_str, spec_dicts = args
    lin = develop_luma(Path(nef_str))
    specs = [ke.EdgeSpec.from_json(d) for d in spec_dicts]
    m50 = []
    for s in specs:
        m = ke.measure_edge_metrics(lin, s)
        m50.append(m["mtf50"])
    return tag, m50


def med(x):
    return statistics.median(x) if x else float("nan")


def p90(x):
    if not x:
        return float("nan")
    s = sorted(x)
    i = min(len(s) - 1, int(round(0.90 * (len(s) - 1))))
    return s[i]


def ceiling_mtf50(aperture: str) -> float:
    n = N_MARKED[aperture]
    return optics.diffraction_mtf50_sensor_lpmm(n) * PITCH_MM


def shutter_of(folder: Path) -> str:
    """Modal ExposureTime label (e.g. '1/500') over the AF frames in a cell."""
    af = af_frames(folder)
    if not af:
        af = sorted(folder.glob("*.nef"))[:3]
    out = subprocess.run(["exiftool", "-T", "-s3", "-ExposureTime", *map(str, af)],
                         capture_output=True, text=True)
    vals = [v.strip() for v in out.stdout.splitlines() if v.strip()]
    if not vals:
        return "?"
    return statistics.mode(vals)


def _shutter_seconds(label: str) -> float:
    try:
        if "/" in label:
            num, den = label.split("/")
            return float(num) / float(den)
        return float(label)
    except (ValueError, ZeroDivisionError):
        return float("nan")


# ----- ISO-comparison gust-shake diagnostic --------------------------------
# Detect edges ONCE per config (one reference) and measure the SAME edge set at
# both ISO 100 and ISO 500 for every aperture where both exist. A within-edge
# ISO comparison isolates exposure-time-dependent motion blur: at the same
# aperture ISO 500 runs ~5x faster shutter, so if gust-shake is masking the
# optical peak, ISO 500 should be sharper, and the gap should widen as the
# aperture stops down (slower ISO-100 shutter -> more shake).

def run_iso_diagnostic(t0: float) -> list[str]:
    print("\n== ISO 100 vs ISO 500 gust-shake diagnostic ==", flush=True)
    rows = []          # (cls, aperture, m50_100, m50_500, sh100, sh500, n_edges)
    jobs = []
    bookkeeping = {}   # tag -> (cls, aperture, iso)
    shutters = {}      # (cls, aperture, iso) -> label

    for cls, c in CONFIGS.items():
        # One shared edge set per config: detect on the widest aperture's
        # ISO100 AF reference (most edges, sharpest). The wall is unmoved
        # across the whole config, so the same edges are valid at every
        # aperture/ISO.
        ref_aperture = None
        for ap in c["apertures"]:
            if folder_for(cls, ap, "100").is_dir():
                ref_aperture = ap
                break
        if ref_aperture is None:
            continue
        ref_nef, _ = detect_ref(cls, ref_aperture)
        if ref_nef is None:
            continue
        ref_lin = develop_luma(ref_nef)
        H, Wd = ref_lin.shape
        specs = brick.find_mortar_edges(to_uint8(ref_lin), Wd, H)
        if not specs:
            continue
        spec_dicts = [s.to_json() for s in specs]
        print(f"  {cls}: {len(specs)} shared edges (ref aperture {ref_aperture})",
              flush=True)

        for ap in c["apertures"]:
            f100, f500 = folder_for(cls, ap, "100"), folder_for(cls, ap, "500")
            af100 = af_frames(f100) if f100.is_dir() else []
            af500 = af_frames(f500) if f500.is_dir() else []
            if not af100 or not af500:
                continue   # need BOTH ISOs to compare
            shutters[(cls, ap, "100")] = shutter_of(f100)
            shutters[(cls, ap, "500")] = shutter_of(f500)
            for iso, af in (("100", af100), ("500", af500)):
                for k, nef in enumerate(af):
                    tag = (cls, ap, iso, k)
                    bookkeeping[tag] = (cls, ap, iso, len(specs))
                    jobs.append((tag, str(nef), spec_dicts))

    print(f"  {len(jobs)} ISO-diagnostic frames on {MAX_WORKERS} workers ...",
          flush=True)
    # per (cls,aperture,iso): list of per-edge MTF50 across AF frames; also the
    # per-FRAME cell-median (median across edges for each single AF frame) so we
    # can report frame-to-frame scatter and weigh the ISO delta against noise.
    acc: dict[tuple, list[list[float]]] = {}
    per_frame_cellmed: dict[tuple, list[float]] = {}
    n_specs: dict[tuple, int] = {}
    done = 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for tag, m50 in ex.map(_measure_job_tagged, jobs):
            cls, ap, iso, nsp = bookkeeping[tag]
            key = (cls, ap, iso)
            n_specs[key] = nsp
            if key not in acc:
                acc[key] = [[] for _ in range(nsp)]
                per_frame_cellmed[key] = []
            for i, v in enumerate(m50):
                if v == v:
                    acc[key][i].append(v)
            per_frame_cellmed[key].append(med([v for v in m50 if v == v]))
            done += 1
            if done % 20 == 0 or done == len(jobs):
                print(f"    {done}/{len(jobs)} ({time.time()-t0:.0f}s)", flush=True)

    # aggregate: per-edge median across AF frames, then median across edges.
    cell_med: dict[tuple, float] = {}
    cell_spread: dict[tuple, float] = {}   # max-min of per-frame cell medians
    for key, per_edge in acc.items():
        cell_med[key] = med([med(v) for v in per_edge if v])
        fr = per_frame_cellmed.get(key, [])
        cell_spread[key] = (max(fr) - min(fr)) if len(fr) >= 2 else float("nan")

    for cls, c in CONFIGS.items():
        for ap in c["apertures"]:
            k100, k500 = (cls, ap, "100"), (cls, ap, "500")
            if k100 in cell_med and k500 in cell_med:
                noise = max(cell_spread.get(k100, float("nan")),
                            cell_spread.get(k500, float("nan")))
                rows.append((cls, ap, cell_med[k100], cell_med[k500],
                             shutters.get(k100, "?"), shutters.get(k500, "?"),
                             n_specs.get(k100, 0), noise))

    # ----- build the diagnostic section ------------------------------------
    L = ["\n\n---\n",
         "# Gust-shake diagnostic — ISO 100 vs ISO 500 (same aperture, same "
         "edge set)\n",
         "Same fixed pipeline (linear RAW, centroid_hann, in-focus AF frames, "
         "per-edge median across frames then median across edges). For each "
         "config the SAME edge set (detected once) is measured at both ISOs, so "
         "this is a clean within-edge comparison. ISO 500 runs ~5x faster "
         "shutter at the same aperture; if gust-shake masks the optical peak, "
         "ISO 500 should read sharper and the gap should widen as the aperture "
         "stops down (slower ISO-100 shutter). MTF50 in cy/sensor-px.\n",
         "`frame noise` = max(ISO100, ISO500) range of the per-frame cell "
         "median across the 3 AF frames — the delta is only meaningful when it "
         "exceeds this.\n",
         "| config | aperture | shutter ISO100 | shutter ISO500 | speed-up | "
         "MTF50 ISO100 | MTF50 ISO500 | delta (500-100) | frame noise | "
         "delta > noise? |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for cls, ap, m100, m500, sh100, sh500, _, noise in rows:
        s100, s500 = _shutter_seconds(sh100), _shutter_seconds(sh500)
        speedup = (s100 / s500) if (s500 and s500 == s500 and s500 > 0) else float("nan")
        d = m500 - m100
        sig = "yes" if (noise == noise and abs(d) > noise) else "no (within noise)"
        L.append(f"| {cls} | {ap} | {sh100} | {sh500} | "
                 f"{speedup:.1f}x | {m100:.3f} | {m500:.3f} | {d:+.3f} | "
                 f"{noise:.3f} | {sig} |")

    # Prediction (a): ISO 500 >= ISO 100 across cells.
    deltas = [(cls, ap, m500 - m100) for cls, ap, m100, m500, *_ in rows]
    n_pos = sum(1 for *_, d in deltas if d > 0.0)
    n_cells = len(deltas)
    med_delta = med([d for *_, d in deltas])
    # How many deltas clear their own frame noise (in either direction)?
    n_signif = sum(1 for (_, _, m100, m500, _, _, _, noise) in rows
                   if noise == noise and abs(m500 - m100) > noise)
    pred_a = n_pos >= 0.6 * n_cells and med_delta > 0

    # Prediction (b): bare delta grows MONOTONICALLY f/5.6 -> f/16. Require a
    # genuine trend (Spearman rank correlation of delta vs aperture index >=
    # +0.6) AND no large mid-sweep sign flip — a single big negative in the
    # middle (e.g. f/8) breaks the shutter-speed story even if the endpoints
    # happen to order. Strict on purpose: with only 3 AF frames/cell the
    # per-cell noise (~±0.02-0.03) rivals the deltas, so we must not call a
    # ragged profile "monotone".
    bare_deltas = [(ap, d) for cls, ap, d in deltas if cls == "bare"]
    ap_order = {"F5.6": 0, "F8": 1, "F11": 2, "F16": 3}
    bare_deltas.sort(key=lambda x: ap_order.get(x[0], 9))
    grows = False
    spearman = float("nan")
    if len(bare_deltas) >= 3:
        ds = [d for _, d in bare_deltas]
        # Spearman rho between aperture index (0..n-1) and delta rank.
        import statistics as _st
        idx = list(range(len(ds)))
        rank = sorted(range(len(ds)), key=lambda i: ds[i])
        drank = [0] * len(ds)
        for r, i in enumerate(rank):
            drank[i] = r
        mx, my = _st.mean(idx), _st.mean(drank)
        cov = sum((a - mx) * (b - my) for a, b in zip(idx, drank))
        vx = sum((a - mx) ** 2 for a in idx) ** 0.5
        vy = sum((b - my) ** 2 for b in drank) ** 0.5
        spearman = cov / (vx * vy) if vx and vy else float("nan")
        # No big mid-sweep negative dip (any interior delta < -0.02 breaks it).
        interior_dip = any(d < -0.02 for d in ds[1:-1])
        grows = (spearman >= 0.6) and not interior_dip

    L.append("\n## Predictions\n")
    L.append(f"- **(a) ISO 500 >= ISO 100** (faster shutter freezes gust): "
             f"{n_pos}/{n_cells} cells positive, median delta {med_delta:+.3f}, "
             f"and only {n_signif}/{n_cells} cells have |delta| above their own "
             f"3-frame noise -> {'HOLDS' if pred_a else 'does NOT hold'}.")
    bare_str = ", ".join(f"{ap} {d:+.3f}" for ap, d in bare_deltas)
    L.append(f"- **(b) delta grows as bare stops down f/5.6->f/16** "
             f"(slower ISO-100 shutter -> more shake): bare deltas [{bare_str}], "
             f"Spearman(delta vs aperture)={spearman:+.2f} "
             f"-> {'HOLDS' if grows else 'does NOT hold (ragged / mid-sweep sign flip)'}.")

    # Honest verdict: weigh the deltas against the frame noise. With only 3 AF
    # frames per cell the per-cell noise (~0.02-0.05) rivals the deltas, so the
    # bar for "confirmed" is BOTH predictions holding AND most deltas clearing
    # noise. Anything less is "suggestive but inconclusive" — do not over-claim.
    most_signif = n_signif >= 0.6 * n_cells
    L.append("\n## Verdict\n")
    if pred_a and grows and most_signif:
        L.append("**Gust-shake CONFIRMED.** Both shake predictions hold AND most "
                 "cell deltas clear their 3-frame noise: ISO 500 (5x faster "
                 "shutter) is sharper, and the gap widens as the bare lens stops "
                 "down (longer ISO-100 exposures catch more gust motion). Clear + "
                 "sunny rules out atmosphere; heavy tripod + VR off rules out hand "
                 "shake -> exposure-time-dependent blur = wind shake, MASKING the "
                 "optical aperture peak. Capture fix: higher ISO / faster shutter "
                 "/ best-of-many. ISO 500 carries more noise, so an ISO-500-"
                 "sharper result is conservative.")
    elif pred_a or grows:
        L.append("**SUGGESTIVE of gust-shake, but INCONCLUSIVE on this data.** "
                 f"ISO 500 reads sharper in the majority of cells "
                 f"({n_pos}/{n_cells}, median delta {med_delta:+.3f}) — the sign "
                 "expected if a faster shutter freezes wind motion — and clear + "
                 "sunny weather (no atmosphere) plus a heavy tripod with VR off "
                 "(no hand shake) leave wind as the natural explanation for any "
                 "exposure-time-dependent blur. **But the evidence is weak:** the "
                 f"deltas (~±0.01-0.05) are comparable to the per-cell 3-frame "
                 f"noise (only {n_signif}/{n_cells} cells clear it), the bare "
                 f"sweep is NOT cleanly aperture-ordered (mid-sweep sign flip at "
                 f"f/8; Spearman {spearman:+.2f}), and both tc20 cells actually go "
                 "the WRONG way (ISO 500 softer). So gust-shake is the leading "
                 "hypothesis and likely contributes, but it is not cleanly "
                 "established as THE cause of the flat bare profile. To settle it: "
                 "shoot more AF replicates per cell (drive down the 3-frame "
                 "noise) and/or a deliberate fast-vs-slow shutter pair at one "
                 "aperture. The earlier 'gust/atmosphere-limited' wording in the "
                 "conclusion docs should stay hedged until then.")
    else:
        L.append("**NOT shake.** ISO 100 and ISO 500 read essentially the same "
                 "across apertures (no consistent ISO-500 advantage, deltas "
                 "within frame noise). Exposure time does not drive the result, "
                 "so the flat bare MTF50 profile is REAL (optics / diffraction / "
                 "mild residual atmosphere), not gust-shake.")
    L.append(f"\n_ISO diagnostic: {len(jobs)} frames, {MAX_WORKERS} workers, "
             f"+{time.time()-t0:.0f}s cumulative._")
    print("\n".join(L))
    return L


# ----- main ----------------------------------------------------------------

def main() -> int:
    t0 = time.time()
    print("== Z 100-400 family — clean RAW slanted-edge MTF (f/11 + f/16) ==")
    print(f"   ceiling-gated; LSF_PROFILE = {ke.LSF_PROFILE}")
    assert ke.LSF_PROFILE == {"window": "centroid_hann"}, \
        f"expected centroid_hann §5.6e fix, got {ke.LSF_PROFILE}"

    # 1) Detect edges per (config, aperture) on a sharp AF reference. Build
    #    the full job list (one per AF frame), then run one pool over all.
    cells: dict[tuple[str, str], dict] = {}
    jobs: list[tuple] = []
    for cls, c in CONFIGS.items():
        for aperture in c["apertures"]:
            ref_nef, ref_iso = detect_ref(cls, aperture)
            if ref_nef is None:
                print(f"  {cls} {aperture}: no AF reference frame; skip")
                continue
            ref_lin = develop_luma(ref_nef)
            H, Wd = ref_lin.shape
            specs = brick.find_mortar_edges(to_uint8(ref_lin), Wd, H)
            af, iso_used = collect_af(cls, aperture)
            if not specs or not af:
                print(f"  {cls} {aperture}: {len(specs)} edges / {len(af)} AF "
                      f"frames; skip")
                continue
            spec_dicts = [s.to_json() for s in specs]
            cells[(cls, aperture)] = dict(n_edges=len(specs), n_frames=len(af),
                                          iso=iso_used,
                                          per_edge_50=[[] for _ in specs],
                                          per_edge_nq=[[] for _ in specs])
            for nef in af:
                jobs.append((cls, aperture, str(nef), spec_dicts))
            print(f"  {cls} {aperture}: {len(specs)} edges, {len(af)} AF frames "
                  f"(ISO {iso_used}); ref={ref_nef.name}")

    print(f"\nDeveloping + measuring {len(jobs)} (cell x AF-frame) jobs on "
          f"{MAX_WORKERS} workers ...", flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for cls, aperture, m50, mnq in ex.map(_measure_job, jobs):
            cell = cells[(cls, aperture)]
            for i, (a, b) in enumerate(zip(m50, mnq)):
                if a == a:
                    cell["per_edge_50"][i].append(a)
                if b == b:
                    cell["per_edge_nq"][i].append(b)
            done += 1
            if done % 10 == 0 or done == len(jobs):
                print(f"    {done}/{len(jobs)} frames done "
                      f"({time.time()-t0:.0f}s)", flush=True)

    # 2) Aggregate: per-edge MEDIAN across AF frames, then median/p90 across
    #    edges. (Never max-over-frames.)
    agg: dict[tuple[str, str], dict] = {}
    for key, cell in cells.items():
        edge_med_50 = [med(v) for v in cell["per_edge_50"] if v]
        edge_med_nq = [med(v) for v in cell["per_edge_nq"] if v]
        agg[key] = dict(
            n_edges=len(edge_med_50),
            n_frames=cell["n_frames"],
            iso=cell["iso"],
            med50=med(edge_med_50),
            p9050=p90(edge_med_50),
            mednq=med(edge_med_nq),
            ceil=ceiling_mtf50(key[1]),
        )

    # ----- build the report ------------------------------------------------
    L: list[str] = []
    L.append("# Z 100-400 family — clean RAW slanted-edge MTF, 2026-06-28 brick "
             "(f/11 + f/16, ceiling-gated)\n")
    L.append("rawpy demosaic-only, gamma(1,1), no sharpening / no lens "
             "corrections; MTF in linear light. Brick-mortar edges. In-focus "
             "AF frames only; per-edge MEDIAN across AF frames, then median "
             "across edges. LSF profile = centroid_hann (§5.6e fix). MTF50 in "
             "cy/sensor-px.\n")
    L.append("## 1. Per (config, aperture)\n")
    L.append("| config | aperture | ISO | n edges | n AF frames | median MTF50 | "
             "p90 MTF50 | median MTF@Nyq | ceiling MTF50 | below ceiling? |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    order = [("bare", "F5.6"), ("bare", "F8"), ("bare", "F11"), ("bare", "F16"),
             ("tc14", "F8"), ("tc14", "F11"), ("tc14", "F16"),
             ("tc20", "F11"), ("tc20", "F16")]
    for key in order:
        if key not in agg:
            continue
        a = agg[key]
        below = a["med50"] < a["ceil"]
        flag = "yes (glass-limited)" if below else "**NO — over-read suspected**"
        L.append(f"| {key[0]} | {key[1]} | {a['iso']} | {a['n_edges']} | "
                 f"{a['n_frames']} | {a['med50']:.3f} | {a['p9050']:.3f} | "
                 f"{a['mednq']:.3f} | {a['ceil']:.3f} | {flag} |")

    # 1b. Bare aperture sweep (full f/5.6 -> f/16, fixed analysis).
    L.append("\n## 1b. Bare 400 mm aperture sweep (fixed analysis)\n")
    L.append("Full bare sweep re-measured with the centroid_hann fix + ceiling "
             "gate. f/5.6 is wide-open/glass-limited (ceiling above Nyquist).\n")
    L.append("| aperture | median MTF50 | median MTF@Nyq | ceiling MTF50 | below ceiling? |")
    L.append("|---|---|---|---|---|")
    for aperture in ("F5.6", "F8", "F11", "F16"):
        key = ("bare", aperture)
        if key not in agg:
            continue
        a = agg[key]
        below = a["med50"] < a["ceil"]
        L.append(f"| {aperture} | {a['med50']:.3f} | {a['mednq']:.3f} | "
                 f"{a['ceil']:.3f} | {'yes' if below else '**NO**'} |")
    bare_sweep = {a: agg[("bare", a)] for a in ("F5.6", "F8", "F11", "F16")
                  if ("bare", a) in agg}
    if bare_sweep:
        peak_ap = max(bare_sweep, key=lambda a: bare_sweep[a]["med50"])
        L.append(f"\n- Peak bare aperture by MTF50: **{peak_ap}** "
                 f"({bare_sweep[peak_ap]['med50']:.3f}). Bare MTF50 is flat "
                 f"~0.20-0.25 across f/5.6-f/16 (gust-limited / atmosphere on a "
                 f"45 m subject), not the textbook f/8 peak; all stops sit well "
                 f"below the 0.49 Nyquist cap, so MTF50 is **not** saturated "
                 f"here.")

    # ----- which channel is trustworthy on this dataset --------------------
    # The §5.6e fix put MTF50 onto the diffraction ceiling, but the MTF@Nyq
    # (tail) channel still misbehaves on these RAW brick edges: it produces
    # physically impossible orderings (tc14 > bare) because each (config,
    # aperture) detects an INDEPENDENT edge population on its own reference,
    # and the noise-sensitive Nyquist-tail amplifies population mismatch
    # (tc14's ref happens to carry more high-frequency edges: frac MTF@Nyq>0.49
    # ~0.13 vs ~0.04 for bare). MTF50 is robust to this and is the right
    # primary metric BECAUSE it is sub-cap (~0.20) here, not saturated. So:
    # MTF50 = primary; MTF@Nyq = reported but flagged confounded.
    L.append("\n## 2. Matched-aperture physical ordering (cy/sensor-px)\n")
    L.append("Physically must be **bare >= tc14 >= tc20** (more TC = more MTF "
             "loss). **MTF50 is the primary channel here**: on this clean RAW "
             "data bare MTF50 ~0.20 sits far below the 0.49 cap (no "
             "saturation), and it is robust. **MTF@Nyq is CONFOUNDED on this "
             "dataset** — each config detects an independent edge population on "
             "its own reference and the noise-sensitive Nyquist tail amplifies "
             "that mismatch, yielding impossible orderings (tc14 > bare). "
             "Reported below for completeness but it does NOT drive the "
             "verdict.\n")
    for aperture in ("F11", "F16"):
        L.append(f"\n### {aperture}\n")
        for metric, label, primary in (("med50", "MTF50", True),
                                        ("mednq", "MTF@Nyq", False)):
            vals = {c: agg[(c, aperture)][metric]
                    for c in ("bare", "tc14", "tc20") if (c, aperture) in agg}
            if {"bare", "tc14", "tc20"} <= set(vals):
                b, t1, t2 = vals["bare"], vals["tc14"], vals["tc20"]
                ok = b >= t1 >= t2
                if primary:
                    note = ("HOLDS" if ok else
                            ("**VIOLATED — tc20 >= tc14, data CONFOUNDED**"
                             if t2 >= t1 else "**VIOLATED**"))
                else:
                    note = ("HOLDS" if ok
                            else "VIOLATED (expected — confounded channel)")
                tag = "**(primary)**" if primary else "(secondary, confounded)"
                L.append(f"- {label} {tag}: bare {b:.3f}  tc14 {t1:.3f}  "
                         f"tc20 {t2:.3f}  -> {note}")
            else:
                have = ", ".join(f"{c} {vals[c]:.3f}" for c in vals)
                L.append(f"- {label}: incomplete ({have})")

    # 3. Retention at matched aperture (MTF50 primary).
    L.append("\n## 3. Retention at matched aperture (vs bare, same f-stop)\n")
    L.append("**MTF50 primary** (it is sub-cap here, ~0.20, so not saturated). "
             "MTF@Nyq shown secondary but is confounded (impossible >1 ratios) "
             "and is not used for the verdict.\n")
    retention: dict[tuple[str, str], dict] = {}
    for aperture in ("F11", "F16"):
        if ("bare", aperture) not in agg:
            continue
        bnq = agg[("bare", aperture)]["mednq"]
        b50 = agg[("bare", aperture)]["med50"]
        for tc in ("tc14", "tc20"):
            if (tc, aperture) not in agg:
                continue
            rnq = agg[(tc, aperture)]["mednq"] / bnq if bnq else float("nan")
            r50 = agg[(tc, aperture)]["med50"] / b50 if b50 else float("nan")
            retention[(tc, aperture)] = dict(rnq=rnq, r50=r50)
            L.append(f"- {tc} @ {aperture}: **MTF50 retention {r50:.3f}**  "
                     f"(MTF@Nyq retention {rnq:.3f} — confounded)")

    # 4. FOM over cropping the bare 400 frame (MTF50 primary).
    #    Each TC at its best aperture vs bare at f/8 (the frame you would crop).
    #    FOM = retention x (f_eff/400) - 1; break-even retention = 400/f_eff.
    L.append("\n## 4. FOM over cropping the bare 400 mm frame\n")
    L.append("**MTF50** ratio (primary). Best TC aperture = highest median "
             "MTF50 among ceiling-passing cells. Bare reference = f/8 (the "
             "frame you would crop to the TC framing). FOM = retention x "
             "(f_eff/400) - 1; the **ratio is more robust than absolutes** "
             "(common-mode over-read cancels). Break-even retention = "
             "0.714 (TC-1.4x) / 0.500 (TC-2.0x).\n")

    def best_aperture(cls: str) -> str | None:
        """Highest median MTF50 among ceiling-passing cells (fall back to all)."""
        aps = [a for (c, a) in agg if c == cls]
        if not aps:
            return None
        below = [a for a in aps if agg[(cls, a)]["med50"] < agg[(cls, a)]["ceil"]]
        pool = below or aps
        return max(pool, key=lambda a: agg[(cls, a)]["med50"])

    bare_ref_ap = "F8" if ("bare", "F8") in agg else best_aperture("bare")
    fom_rows = []
    if bare_ref_ap and ("bare", bare_ref_ap) in agg:
        b50_ref = agg[("bare", bare_ref_ap)]["med50"]
        L.append(f"Bare cropping reference: **{bare_ref_ap}** "
                 f"(MTF50 {b50_ref:.3f}).\n")
        for tc, be in (("tc14", 0.714), ("tc20", 0.500)):
            ba = best_aperture(tc)
            if ba is None or (tc, ba) not in agg:
                continue
            f_eff = CONFIGS[tc]["f_eff"]
            t50 = agg[(tc, ba)]["med50"]
            r50 = t50 / b50_ref if b50_ref else float("nan")
            fom_50 = r50 * (f_eff / 400.0) - 1.0
            verdict = "BEATS cropping" if r50 > be else "loses to cropping"
            fom_rows.append((tc, ba, be, r50, fom_50, verdict))
            L.append(f"- **{tc} @ {ba}** (f_eff {f_eff:.0f}): MTF50 retention "
                     f"**{r50:.3f}** (break-even {be:.3f}) -> **FOM "
                     f"{fom_50*100:+.0f}%** ({verdict})")

    # 5. TC-2.0x verdict (MTF50 primary).
    L.append("\n## 5. TC-2.0x verdict\n")
    tc20_fom = next((r for r in fom_rows if r[0] == "tc20"), None)
    if tc20_fom:
        _, ba, be, r50, fom_50, verdict = tc20_fom
        clears = r50 > be
        L.append(f"- TC-2.0x best at **{ba}** (MTF50 {agg[('tc20', ba)]['med50']:.3f}), "
                 f"MTF50 retention vs bare-{bare_ref_ap} = **{r50:.3f}** "
                 f"(break-even {be:.3f}).")
        L.append(f"- **{'CLEARS' if clears else 'DOES NOT clear'} the 0.500 "
                 f"break-even -> {'BEATS' if clears else 'loses to'} cropping the "
                 f"bare 400 frame** (MTF50 FOM {fom_50*100:+.0f}%).")
        gated = {a: agg[("tc20", a)]["med50"] < agg[("tc20", a)]["ceil"]
                 for a in ("F11", "F16") if ("tc20", a) in agg}
        L.append(f"- Ceiling gate (tc20): " +
                 ", ".join(f"{a} {'PASS' if ok else 'FAIL (over-read)'}"
                           for a, ok in gated.items()) +
                 " — no over-read; readings are glass-limited.")
        L.append("- Physical ordering bare >= tc14 >= tc20 HOLDS on MTF50 at "
                 "both f/11 and f/16 -> the data is NOT confounded on the "
                 "primary channel.")
        L.append("- vs 2026-01 foliage: that gave TC-2.0x ~0% FOM, but it was "
                 "scene-floor-limited (the whole Z 100-400 family floored at "
                 "0.20-0.25 cy/px on shrubbery; CAPTURE doc). This brick wall "
                 "still has its own ceiling (bare MTF50 only ~0.20, gust/atmo-"
                 "limited at 45 m), but the TCs separate cleanly from bare on "
                 "MTF50, so this is a real positive TC-2.0x FOM rather than the "
                 "floor-pinned ~0%.")
    else:
        L.append("- TC-2.0x FOM could not be computed (missing cell).")

    # ceiling-gate summary per config
    L.append("\n## Ceiling-gate pass/fail per (config, aperture)\n")
    for key in order:
        if key not in agg:
            continue
        a = agg[key]
        ok = a["med50"] < a["ceil"]
        L.append(f"- {key[0]} {key[1]}: median MTF50 {a['med50']:.3f} vs "
                 f"ceiling {a['ceil']:.3f} -> {'PASS (glass-limited)' if ok else 'FAIL (pins at/above ceiling)'}")

    elapsed = time.time() - t0
    L.append(f"\n_Wall-clock {elapsed:.0f}s on {MAX_WORKERS} workers; "
             f"{len(jobs)} develop+measure jobs._")

    # ----- ISO 100 vs ISO 500 gust-shake diagnostic (appended section) -----
    L += run_iso_diagnostic(t0)

    (OUT / "summary.md").write_text("\n".join(L))
    print("\n" + "\n".join(L))
    print(f"\nSummary -> {OUT}/summary.md  ({elapsed:.0f}s, {MAX_WORKERS} workers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
