"""TC-1.4x retention via the BRICK MORTAR edges (low-contrast, dense, central).

User's point: low contrast was an analysis failure, not a subject one — every
brick has 4 mortar edges, so the wall is a dense grid of low-contrast edges
covering the centre (where bare had no chalk/placard edges). The slanted-edge
detector ignored them because it rejects near-axis edges and its score favours
high-contrast chalk. This script targets the **long, slightly-tilted mortar
courses** directly: low contrast (won't saturate), central, and the SAME
physical joint in every config (just magnified).

Approach: Canny+Hough, keep LONG near-horizontal courses (and near-vertical
joints) that have a SMALL slant (0.5°–12° off-axis — enough to sub-pixel
sample the ESF, which is why a perfectly-squared wall would actually be bad
here). No contrast/score gating toward bright features. Restrict to the
central overlap region; measure best-focus MTF50 across the focus-shift +
AF frames. Compare bare vs tc14 at f/8 (widest common aperture).

Run: uv run python -u scripts/poc_longdist_tc14_brick.py
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
CENTRAL = 0.60
MIN_SLANT, MAX_SLANT = 0.5, 12.0     # degrees off the nearest axis
MIN_LEN_H = 700                       # courses are long
MIN_LEN_V = 180                       # head joints are short
LENS_DIR = {
    "bare": "NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO{iso}",
    "tc14": "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x ISO{iso}",
}
FOCAL = {"bare": "400.0 mm", "tc14": "560.0 mm"}


def folders(cls):
    return [d for iso in ("100", "500")
            if (d := ROOT / LENS_DIR[cls].format(iso=iso) / FOCAL[cls] / APERTURE).is_dir()]


def sharp_ref(folder):
    return max(folder.glob("*.jpg"), key=lambda p: p.stat().st_size)


def _axis_slant_deg(angle_rad):
    """Slant from the nearest axis (0 or 90), in degrees, + which axis."""
    deg = math.degrees(angle_rad) % 180
    d_h = min(deg, 180 - deg)        # distance to horizontal
    d_v = abs(deg - 90)              # distance to vertical
    return (d_h, "H") if d_h <= d_v else (d_v, "V")


def find_mortar_edges(luma, Wd, H):
    """Long, slightly-tilted near-axis segments (mortar courses/joints)."""
    segs = ke._canny_hough_segments(luma.astype(np.uint8), min_line_px=MIN_LEN_V)
    half = CENTRAL / 2
    x0, x1, y0, y1 = (0.5 - half) * Wd, (0.5 + half) * Wd, (0.5 - half) * H, (0.5 + half) * H
    out = []
    for x1s, y1s, x2s, y2s in segs:
        length = math.hypot(x2s - x1s, y2s - y1s)
        _, ang = ke._segment_to_polar(float(x1s), float(y1s), float(x2s), float(y2s))
        slant, axis = _axis_slant_deg(ang)
        if not (MIN_SLANT <= slant <= MAX_SLANT):
            continue
        if axis == "H" and length < MIN_LEN_H:
            continue
        if axis == "V" and length < MIN_LEN_V:
            continue
        mx, my = (x1s + x2s) / 2.0, (y1s + y2s) / 2.0
        if not (x0 <= mx <= x1 and y0 <= my <= y1):
            continue
        out.append(ke.EdgeSpec(mid_x=float(mx), mid_y=float(my), angle_rad=float(ang),
                               length_px=float(length), grad_mean=0.0, contrast=0.0,
                               score=0.0, edge_id=len(out)))
    return out


def measure(cls):
    fs = folders(cls)
    if not fs:
        print(f"  {cls}: no {APERTURE} folder"); return {}
    ref = sharp_ref(fs[0])
    rgb = ke.load_rgb(ref)
    H, Wd = rgb.shape[:2]
    luma = rgb.mean(axis=2).astype(np.float32)
    specs = find_mortar_edges(luma, Wd, H)
    if not specs:
        print(f"  {cls}: no mortar edges found (wall may be too perfectly squared)")
        return {}
    canvas = rgb.copy()
    for s in specs:
        tx, ty = math.cos(s.angle_rad), math.sin(s.angle_rad)
        h = min(s.length_px, 256) / 2
        cv2.line(canvas, (int(s.mid_x - h * tx), int(s.mid_y - h * ty)),
                 (int(s.mid_x + h * tx), int(s.mid_y + h * ty)), (255, 0, 0), 3)
    cv2.imwrite(str(OUT / f"brick_{cls}.jpg"),
                cv2.cvtColor(cv2.resize(canvas, (1600, int(1600 * H / Wd))), cv2.COLOR_RGB2BGR))
    frames = [p for f in fs for p in sorted(f.glob("*.jpg"))[::STRIDE]]
    best = [float("nan")] * len(specs)
    contrasts = [0.0] * len(specs)
    for jp in frames:
        lu = ke.load_luma(jp)
        for i, s in enumerate(specs):
            m = ke.measure_edge_metrics(lu, s)["mtf50"]
            if m == m and not (best[i] >= m):
                best[i] = m
    vals = [v for v in best if v == v]
    print(f"  {cls}: {len(specs)} mortar edges, {len(vals)} measured, "
          f"{sum(v < 0.49 for v in vals)}/{len(vals)} sub-Nyquist; ref={ref.name}")
    return dict(vals=vals)


def main():
    print(f"== bare vs tc14 at {APERTURE}, BRICK MORTAR edges (central {CENTRAL:.0%}) ==")
    r = {c: measure(c) for c in ("bare", "tc14")}
    L = [f"# TC-1.4x retention — brick mortar edges, {APERTURE}, central {CENTRAL:.0%}\n",
         "Low-contrast mortar courses/joints (slightly tilted), best-focus per edge.\n",
         "| config | f_eff | n edges | median MTF50 | p25 | p75 | sub-Nyquist |",
         "|---|---|---|---|---|---|---|"]
    agg = {}
    for c in ("bare", "tc14"):
        d = r.get(c) or {}
        if not d or not d["vals"]:
            L.append(f"| {c} | {F_EFF[c]:.0f} | 0 | — | | | |"); continue
        v = sorted(d["vals"])
        agg[c] = statistics.median(v)
        p25 = v[max(0, int(0.25 * len(v)) - 1)]; p75 = v[min(len(v) - 1, int(0.75 * len(v)))]
        L.append(f"| {c} | {F_EFF[c]:.0f} | {len(v)} | {statistics.median(v):.3f} | "
                 f"{p25:.3f} | {p75:.3f} | {sum(x < 0.49 for x in v)}/{len(v)} |")
    if "bare" in agg and "tc14" in agg:
        rr = agg["tc14"] / agg["bare"] if agg["bare"] else float("nan")
        be = 400.0 / 560.0
        L.append(f"\n## Retention: tc14/bare median MTF50 = **{rr:.2f}** "
                 f"(break-even {be:.3f}, FOM {(rr*560/400-1)*100:+.0f}%) → "
                 f"{'PASS' if rr > be else 'FAIL'}")
        L.append(f"- physical: bare {agg['bare']:.3f} "
                 f"{'≥' if agg['bare'] >= agg['tc14'] else '<'} tc14 {agg['tc14']:.3f}")
    (OUT / "summary.md").write_text("\n".join(L))
    print("\n".join(L))
    print(f"\nOverlays + summary in {OUT}/  (check brick_*.jpg)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
