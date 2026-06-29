"""TC-1.4x retention — bare vs TC-1.4x at f/8, colour placards MASKED OUT.

Rationale (user): the bright green/purple placards saturate slanted-edge
MTF50 (pinned at the 0.49 Nyquist cap, MTF@Nyq >1 from JPEG sharpening). So
(1) mask the placards and measure only brick/chalk edges, and (2) use f/8 —
both bare and TC-1.4x were shot there, it dodges the documented f/11-f/16
MTF50 over-read, and it's near wide-open for the TC so the lens MTF is lower
(edges more likely to fall BELOW Nyquist and actually discriminate).

tc20 has no f/8 (wide-open f/11), so this is a bare-vs-tc14 comparison —
which is the point: tc14 is the copy under test.

Per config: discover edges on a sharp f/8 reference with the green+purple
regions masked, drop any edge whose midpoint lands in (a dilation of) the
mask, restrict to the bare∩tc14 overlap (central ~71% of the bare frame),
measure best-focus MTF50 across strided f/8 frames. Report the edge MTF50
distribution + retention. Key checks: are edges sub-Nyquist (<0.49, i.e.
not saturated)? and is bare >= tc14 (physical)?

Run: uv run python -u scripts/poc_longdist_tc14_f8_masked.py
"""
from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import poc_known_edge_mtf50 as ke

ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-06-28")
OUT = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

F_EFF = {"bare": 400.0, "tc14": 560.0}
APERTURE = "F8"
STRIDE = 4
CENTRAL = 0.71          # bare∩tc14 overlap fraction (tc14 = 1.4x crop of centre)
LENS_DIR = {
    "bare": "NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO{iso}",
    "tc14": "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x ISO{iso}",
}
FOCAL = {"bare": "400.0 mm", "tc14": "560.0 mm"}


def folders(cls):
    return [d for iso in ("100", "500")
            if (d := ROOT / LENS_DIR[cls].format(iso=iso) / FOCAL[cls] / APERTURE).is_dir()]


def placard_mask(rgb):
    """Mask bright green + purple placards (dilated)."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    green = cv2.inRange(hsv, (35, 60, 40), (85, 255, 255))
    purple = cv2.inRange(hsv, (120, 50, 30), (165, 255, 255))
    m = cv2.bitwise_or(green, purple)
    return cv2.dilate(m, np.ones((41, 41), np.uint8))


def sharp_ref(folder):
    return max(folder.glob("*.jpg"), key=lambda p: p.stat().st_size)


def measure(cls):
    fs = folders(cls)
    if not fs:
        print(f"  {cls}: no {APERTURE} folder"); return {}
    ref = sharp_ref(fs[0])
    rgb = ke.load_rgb(ref)
    H, Wd = rgb.shape[:2]
    mask = placard_mask(rgb)
    luma = rgb.mean(axis=2).astype(np.float32)
    specs = ke.discover_edges(luma, top_k=30, min_line_px=150)
    # central-overlap window (centred) — for bare keep central 71%; tc14 is
    # already that crop so keep all but still apply to be symmetric.
    half = CENTRAL / 2 if cls == "bare" else 0.5
    x0, x1 = (0.5 - half) * Wd, (0.5 + half) * Wd
    y0, y1 = (0.5 - half) * H, (0.5 + half) * H
    kept = []
    for s in specs:
        mx, my = int(round(s.mid_x)), int(round(s.mid_y))
        if not (x0 <= mx <= x1 and y0 <= my <= y1):
            continue
        if mask[min(my, H - 1), min(mx, Wd - 1)] > 0:     # inside placard
            continue
        kept.append(s)
    if not kept:
        print(f"  {cls}: no non-placard central edges"); return {}
    # overlay
    canvas = rgb.copy()
    canvas[mask > 0] = (canvas[mask > 0] * 0.4).astype(np.uint8)   # dim masked
    for s in kept:
        tx, ty = math.cos(s.angle_rad), math.sin(s.angle_rad)
        h = min(s.length_px, 256) / 2
        cv2.line(canvas, (int(s.mid_x - h * tx), int(s.mid_y - h * ty)),
                 (int(s.mid_x + h * tx), int(s.mid_y + h * ty)), (255, 0, 0), 4)
    cv2.imwrite(str(OUT / f"f8_{cls}.jpg"),
                cv2.cvtColor(cv2.resize(canvas, (1600, int(1600 * H / Wd))), cv2.COLOR_RGB2BGR))
    # best-focus per edge across strided f/8 frames
    frames = [p for f in fs for p in sorted(f.glob("*.jpg"))[::STRIDE]]
    best = [float("nan")] * len(kept)
    for jp in frames:
        lu = ke.load_luma(jp)
        for i, s in enumerate(kept):
            m = ke.measure_edge_metrics(lu, s)["mtf50"]
            if m == m and not (best[i] >= m):
                best[i] = m
    vals = [v for v in best if v == v]
    print(f"  {cls}: {len(kept)} edges kept, {len(frames)} frames, "
          f"{sum(v < 0.49 for v in vals)}/{len(vals)} sub-Nyquist; ref={ref.name}")
    return dict(vals=vals, n=len(vals))


def main():
    print(f"== bare vs tc14 at {APERTURE}, placards masked ==")
    r = {c: measure(c) for c in ("bare", "tc14")}
    L = [f"# TC-1.4x retention — bare vs tc14 at {APERTURE}, placards masked\n",
         "Brick/chalk edges only (green+purple masked), central overlap, "
         "best-focus per edge.\n",
         "| config | f_eff | n edges | median MTF50 | p75 MTF50 | max MTF50 | sub-Nyquist |",
         "|---|---|---|---|---|---|---|"]
    agg = {}
    for c in ("bare", "tc14"):
        d = r.get(c) or {}
        if not d:
            L.append(f"| {c} | {F_EFF[c]:.0f} | 0 | — | | | |"); continue
        v = sorted(d["vals"])
        med = statistics.median(v)
        p75 = v[min(len(v) - 1, int(0.75 * len(v)))]
        agg[c] = dict(med=med, p75=p75, mx=max(v))
        L.append(f"| {c} | {F_EFF[c]:.0f} | {len(v)} | {med:.3f} | {p75:.3f} | {max(v):.3f} "
                 f"| {sum(x < 0.49 for x in v)}/{len(v)} |")
    if "bare" in agg and "tc14" in agg:
        L.append("\n## Retention (median MTF50, cy/sensor-px)\n")
        rr = agg["tc14"]["med"] / agg["bare"]["med"] if agg["bare"]["med"] else float("nan")
        be = 400.0 / 560.0
        gain = (rr * 560.0 / 400.0 - 1) * 100
        verdict = "PASS (adds detail)" if rr > be else "FAIL (crop as good)"
        L.append(f"- tc14/bare median MTF50 = **{rr:.2f}**  (break-even {be:.3f}; "
                 f"FOM gain {gain:+.0f}%) → {verdict}")
        L.append(f"- physical sanity: bare ({agg['bare']['med']:.3f}) "
                 f"{'≥' if agg['bare']['med'] >= agg['tc14']['med'] else '<'} "
                 f"tc14 ({agg['tc14']['med']:.3f})")
        L.append("\n> If most edges are sub-Nyquist AND bare ≥ tc14, this is a "
                 "trustworthy retention. If edges still saturate (max=0.49, few "
                 "sub-Nyquist), f/8 didn't escape the cap either.")
    (OUT / "summary.md").write_text("\n".join(L))
    print("\n".join(L))
    print(f"\nOverlays + summary in {OUT}/  (check f8_*.jpg)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
