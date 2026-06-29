"""TC-1.4x retention POC on UNSHARPENED LINEAR RAW (bare vs tc14, f/8).

Tests the hypothesis: on JPEG, MTF@Nyquist is contaminated by in-camera
sharpening (halos push it >1.0) and MTF50 saturates at the 0.49 Nyquist cap.
On linear, demosaic-only RAW (no sharpening, no lens corrections, linear
gamma — the physically correct domain for MTF) MTF@Nyquist should sit <=1.0
and finally discriminate -> a clean, physical bare >= tc14 retention.

RAW dev: rawpy.postprocess(gamma=(1,1), no_auto_bright, 16-bit, camera WB,
AHD demosaic). No sharpening / no lens correction by construction.

Edges: reuse the brick-mortar finder (long, slightly-tilted, low-contrast,
central) on a sharp developed reference (detection on an 8-bit stretch;
measurement on the linear float). Best-focus per edge across the f/8 AF
frames + a strided focus-shift subset.

Run: uv run python -u scripts/poc_longdist_tc14_raw.py
"""
from __future__ import annotations

import statistics
import subprocess
import sys
from pathlib import Path

import numpy as np
import rawpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import poc_known_edge_mtf50 as ke
import poc_longdist_tc14_brick as brick

ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-06-28")
OUT = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

F_EFF = {"bare": 400.0, "tc14": 560.0}
STACK_STRIDE = 6
LENS_DIR = {
    "bare": "NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO{iso}",
    "tc14": "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x ISO{iso}",
}
FOCAL = {"bare": "400.0 mm", "tc14": "560.0 mm"}


def folders(cls):
    return [d for iso in ("100", "500")
            if (d := ROOT / LENS_DIR[cls].format(iso=iso) / FOCAL[cls] / "F8").is_dir()]


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
    edges have enough contrast for Canny (linear light gives ~0 edges; gamma
    gives ~260). Measurement stays on the linear float."""
    lo, hi = np.percentile(luma[::8, ::8], [1, 99])
    n = np.clip((luma - lo) / max(hi - lo, 1e-6), 0, 1)
    return (n ** (1 / 2.2) * 255.0).astype(np.float32)


def silent_map(nefs: list[Path]) -> dict[Path, str]:
    out = subprocess.run(["exiftool", "-T", "-s3", "-SilentPhotography", *map(str, nefs)],
                         capture_output=True, text=True)
    return {p: v.strip() for p, v in zip(nefs, out.stdout.splitlines())}


def select(folder: Path) -> list[Path]:
    nefs = sorted(folder.glob("*.nef"))
    sm = silent_map(nefs)
    af = [n for n in nefs if sm.get(n) == "Off"]
    stack = [n for n in nefs if sm.get(n) == "On"]
    return af + stack[::STACK_STRIDE]


def detect_ref(folder: Path) -> Path:
    """Reference for edge DETECTION: the first Pinpoint-AF frame (Silent=Off)
    — guaranteed in-focus at centre, reliably yields the full mortar grid.
    Edge positions are fixed across the unmoved-tripod stack, so any in-focus
    frame locates them."""
    nefs = sorted(folder.glob("*.nef"))
    sm = silent_map(nefs)
    af = [n for n in nefs if sm.get(n) == "Off"]
    return af[0] if af else nefs[0]


def measure(cls: str) -> dict:
    fs = folders(cls)
    if not fs:
        print(f"  {cls}: no f/8 folder"); return {}
    ref_lin = develop_luma(detect_ref(fs[0]))
    H, Wd = ref_lin.shape
    specs = brick.find_mortar_edges(to_uint8(ref_lin), Wd, H)
    if not specs:
        print(f"  {cls}: no mortar edges on RAW ref"); return {}
    frames = [p for f in fs for p in select(f)]
    best50 = [float("nan")] * len(specs)
    bestnq = [float("nan")] * len(specs)
    for nef in frames:
        lin = develop_luma(nef)
        for i, s in enumerate(specs):
            m = ke.measure_edge_metrics(lin, s)
            if m["mtf50"] == m["mtf50"] and not (best50[i] >= m["mtf50"]):
                best50[i] = m["mtf50"]
            if m["mtf_at_nyquist"] == m["mtf_at_nyquist"] and not (bestnq[i] >= m["mtf_at_nyquist"]):
                bestnq[i] = m["mtf_at_nyquist"]
        del lin
    v50 = [v for v in best50 if v == v]
    vnq = [v for v in bestnq if v == v]
    print(f"  {cls}: {len(specs)} edges, {len(frames)} RAW frames developed, "
          f"{sum(v < 0.49 for v in v50)}/{len(v50)} sub-Nyquist (MTF50); "
          f"MTF@Nyq max={max(vnq):.2f}")
    return dict(v50=v50, vnq=vnq, n=len(specs), nframes=len(frames))


def med(x):
    return statistics.median(x) if x else float("nan")


def main() -> int:
    print("== bare vs tc14 at f/8 — LINEAR RAW (rawpy, demosaic-only, no sharpen) ==")
    r = {c: measure(c) for c in ("bare", "tc14")}
    L = ["# TC-1.4x retention — LINEAR RAW (f/8, brick mortar edges)\n",
         "rawpy demosaic-only, gamma(1,1), no sharpening / no lens corrections. "
         "MTF measured in linear light (correct domain). Best-focus per edge.\n",
         "| config | f_eff | n edges | median MTF50 | sub-Nyq | median MTF@Nyq | max MTF@Nyq |",
         "|---|---|---|---|---|---|---|"]
    agg = {}
    for c in ("bare", "tc14"):
        d = r.get(c) or {}
        if not d or not d.get("v50"):
            L.append(f"| {c} | {F_EFF[c]:.0f} | 0 | — | | | |"); continue
        agg[c] = dict(m50=med(d["v50"]), mnq=med(d["vnq"]), n=len(d["v50"]))
        L.append(f"| {c} | {F_EFF[c]:.0f} | {len(d['v50'])} | {med(d['v50']):.3f} | "
                 f"{sum(v<0.49 for v in d['v50'])}/{len(d['v50'])} | "
                 f"{med(d['vnq']):.3f} | {max(d['vnq']):.2f} |")
    if "bare" in agg and "tc14" in agg:
        be = 400.0 / 560.0
        r50 = agg["tc14"]["m50"] / agg["bare"]["m50"] if agg["bare"]["m50"] else float("nan")
        rnq = agg["tc14"]["mnq"] / agg["bare"]["mnq"] if agg["bare"]["mnq"] else float("nan")
        L.append("\n## Retention (tc14 / bare)\n")
        L.append(f"- **MTF@Nyquist: {rnq:.2f}**  (break-even {be:.3f}, "
                 f"FOM {(rnq*560/400-1)*100:+.0f}%) → {'PASS' if rnq>be else 'FAIL'}")
        L.append(f"- MTF50: {r50:.2f}")
        L.append(f"- physical ordering (MTF@Nyq): bare {agg['bare']['mnq']:.3f} "
                 f"{'>=' if agg['bare']['mnq']>=agg['tc14']['mnq'] else '<'} "
                 f"tc14 {agg['tc14']['mnq']:.3f}")
        halo = "GONE (<=1.0)" if max(agg['bare']['mnq'], agg['tc14']['mnq']) <= 1.0 else "still present"
        L.append(f"- sharpening halo (median MTF@Nyq <=1?): {halo}")
    (OUT / "summary.md").write_text("\n".join(L))
    print("\n".join(L))
    print(f"\nSummary in {OUT}/summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
