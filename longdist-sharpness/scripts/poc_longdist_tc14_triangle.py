"""TC-1.4x revalidation — SAME-FEATURE retention via the green triangle.

The flat-wall scene's centre (where bare/TC FOVs overlap) is plain brick;
the only strong central-ish feature is the green "1" route-marker placard.
Its two slanted sides are clean diagonal high-contrast (green-vs-brick)
edges — ideal for slanted-edge MTF50 and, crucially, the SAME physical
edge in all three configs (just magnified). Measuring that one feature
gives a true like-for-like retention, unlike pooling differently-placed
chalk edges per config.

Per config (bare/tc14/tc20), at the common aperture **f/11**:
  1. colour-segment the green triangle on a sharp reference frame,
  2. extract its two slanted sides as EdgeSpecs,
  3. measure MTF50 / MTF@Nyquist on a strided set of focus-shift + AF
     frames, take the best-focus value per edge (the triangle is off-axis,
     so it peaks at its own focus step),
  4. retention = c_TC / c_bare (sensor cy/px); FOM = MTF50 x f_eff.

Run: uv run python -u scripts/poc_longdist_tc14_triangle.py
Outputs overlays (verify detection!) + summary under
poc_longdist_tc14_triangle_out/.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import poc_known_edge_mtf50 as ke  # EdgeSpec, measure_edge_metrics, load_luma/rgb

ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-06-28")
OUT = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

F_EFF = {"bare": 400.0, "tc14": 560.0, "tc20": 800.0}
FOM_BREAKEVEN = {"tc14": 400.0 / 560.0, "tc20": 400.0 / 800.0}
APERTURE = "F11"          # common to all three configs
STRIDE = 5                # subsample frames for the best-focus search

LENS_DIR = {
    "bare": "NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO{iso}",
    "tc14": "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x ISO{iso}",
    "tc20": "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x ISO{iso}",
}
FOCAL = {"bare": "400.0 mm", "tc14": "560.0 mm", "tc20": "800.0 mm"}


def folders(cls: str) -> list[Path]:
    out = []
    for iso in ("100", "500"):
        d = ROOT / LENS_DIR[cls].format(iso=iso) / FOCAL[cls] / APERTURE
        if d.is_dir():
            out.append(d)
    return out


def detect_triangle_edges(rgb: np.ndarray) -> list[ke.EdgeSpec]:
    """Colour-segment the green placard, fit a triangle, return its two
    slanted sides as EdgeSpecs (base/near-horizontal side dropped)."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    # Green: OpenCV hue ~35-85, decent saturation/value.
    mask = cv2.inRange(hsv, (35, 60, 40), (85, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return []
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 5000:                # too small / not found
        return []
    peri = cv2.arcLength(c, True)
    approx = cv2.approxPolyDP(c, 0.06 * peri, True).reshape(-1, 2)
    if len(approx) != 3:
        # try a coarser epsilon
        approx = cv2.approxPolyDP(c, 0.10 * peri, True).reshape(-1, 2)
        if len(approx) != 3:
            return []
    specs = []
    for i in range(3):
        p1 = approx[i].astype(float)
        p2 = approx[(i + 1) % 3].astype(float)
        ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        # canonicalise to [-pi/2, pi/2)
        if ang >= math.pi / 2:
            ang -= math.pi
        elif ang < -math.pi / 2:
            ang += math.pi
        if ke._is_too_axis_aligned(ang):          # drop the ~horizontal base
            continue
        length = float(math.hypot(*(p2 - p1)))
        mid = (p1 + p2) / 2.0
        specs.append(ke.EdgeSpec(mid_x=float(mid[0]), mid_y=float(mid[1]),
                                 angle_rad=float(ang), length_px=length,
                                 grad_mean=0.0, contrast=0.0, score=0.0,
                                 edge_id=len(specs)))
    return specs


def sharp_ref(folder: Path) -> Path:
    return max(folder.glob("*.jpg"), key=lambda p: p.stat().st_size)


def measure_config(cls: str) -> dict:
    fs = folders(cls)
    if not fs:
        return {}
    ref = sharp_ref(fs[0])
    specs = detect_triangle_edges(ke.load_rgb(ref))
    if not specs:
        print(f"  {cls}: triangle NOT found on {ref.name}")
        return {}
    # overlay for visual verification
    canvas = ke.load_rgb(ref).copy()
    for s in specs:
        tx, ty = math.cos(s.angle_rad), math.sin(s.angle_rad)
        h = s.length_px / 2
        p1 = (int(s.mid_x - h * tx), int(s.mid_y - h * ty))
        p2 = (int(s.mid_x + h * tx), int(s.mid_y + h * ty))
        cv2.line(canvas, p1, p2, (255, 0, 0), 4)
    cv2.imwrite(str(OUT / f"triangle_{cls}.jpg"),
                cv2.cvtColor(cv2.resize(canvas, (1600, int(1600 * canvas.shape[0] / canvas.shape[1]))),
                             cv2.COLOR_RGB2BGR))
    # best-focus per edge across strided frames of all f/11 folders
    frames = []
    for f in fs:
        frames += sorted(f.glob("*.jpg"))[::STRIDE]
    best = [dict(mtf50=float("nan"), nyq=float("nan")) for _ in specs]
    for jp in frames:
        luma = ke.load_luma(jp)
        for i, s in enumerate(specs):
            m = ke.measure_edge_metrics(luma, s)
            if m["mtf50"] == m["mtf50"] and not (best[i]["mtf50"] >= m["mtf50"]):
                best[i]["mtf50"] = m["mtf50"]
            if m["mtf_at_nyquist"] == m["mtf_at_nyquist"] and not (best[i]["nyq"] >= m["mtf_at_nyquist"]):
                best[i]["nyq"] = m["mtf_at_nyquist"]
    print(f"  {cls}: triangle found ({len(specs)} sides), {len(frames)} frames scanned; "
          f"ref={ref.name}")
    return dict(specs=specs, best=best, ref=ref.name, n_frames=len(frames))


def main() -> int:
    print(f"== green-triangle same-feature retention (aperture {APERTURE}) ==")
    res = {c: measure_config(c) for c in ("bare", "tc14", "tc20")}
    L = ["# TC-1.4x — same-feature (green triangle) retention, f/11\n",
         "Same physical edge (triangle sides) across configs → like-for-like. "
         "Best-focus per edge across the focus-shift stack.\n",
         "| config | f_eff | edge MTF50 (best side) | mean of sides | MTF@Nyq (best) | ref frame |",
         "|---|---|---|---|---|---|"]
    agg = {}
    for c in ("bare", "tc14", "tc20"):
        r = res.get(c) or {}
        if not r:
            L.append(f"| {c} | {F_EFF[c]:.0f} | — not found — | | | |")
            continue
        m50 = [b["mtf50"] for b in r["best"] if b["mtf50"] == b["mtf50"]]
        nyq = [b["nyq"] for b in r["best"] if b["nyq"] == b["nyq"]]
        best50 = max(m50) if m50 else float("nan")
        mean50 = sum(m50) / len(m50) if m50 else float("nan")
        bnyq = max(nyq) if nyq else float("nan")
        agg[c] = dict(best50=best50, mean50=mean50, bnyq=bnyq)
        L.append(f"| {c} | {F_EFF[c]:.0f} | {best50:.3f} | {mean50:.3f} | {bnyq:.3f} | {r['ref']} |")
    L.append("")
    if "bare" in agg:
        L.append("## Retention vs bare (same triangle edge)\n")
        L.append("| TC | retention MTF50 | retention Nyq | break-even | FOM gain | verdict |")
        L.append("|---|---|---|---|---|---|")
        b50, bnq = agg["bare"]["best50"], agg["bare"]["bnyq"]
        for c in ("tc14", "tc20"):
            if c not in agg:
                continue
            r50 = agg[c]["best50"] / b50 if b50 else float("nan")
            rnq = agg[c]["bnyq"] / bnq if bnq else float("nan")
            gain = (r50 * F_EFF[c] / F_EFF["bare"] - 1) * 100
            verdict = "PASS (adds detail)" if r50 > FOM_BREAKEVEN[c] else "FAIL (crop as good)"
            L.append(f"| {c} | {r50:.2f} | {rnq:.2f} | {FOM_BREAKEVEN[c]:.3f} | {gain:+.0f}% | {verdict} |")
        L.append("\n> Expect bare > tc14 > tc20 in cy/sensor-px. Check the "
                 "triangle_*.jpg overlays — a misdetected/clipped edge invalidates the row.")
    (OUT / "summary.md").write_text("\n".join(L))
    print("\n".join(L))
    print(f"\nOverlays + summary in {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
