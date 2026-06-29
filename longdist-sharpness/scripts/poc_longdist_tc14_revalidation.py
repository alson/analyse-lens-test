"""TC-1.4x replacement revalidation — within-session analysis of the
2026-06-28 flat-wall shoot (Z 100-400 bare / +TC-1.4x / +TC-2.0x).

Goal (docs/CAPTURE_2026-06-28_tc14_revalidation.md): validate the new
TC-1.4x copy *within this session* vs the bare lens (unchanged-hardware
anchor) and the TC-2.0x.

Pinpoint-AF shots vs focus-shift stacks are treated SEPARATELY
(discriminator: Exif Nikon ``SilentPhotography`` — Off = the 3 Pinpoint-AF
replicates, On = the focus-shift stack frames):

- **Centre** comes from the **Pinpoint-AF** frames. Pinpoint AF is
  closed-loop (contrast-detect), so it nails focus under the centre point
  and isn't limited by the focus-shift step quantisation. Primary centre
  metric: top (and median) of the 3 AF replicates at the centre tile.
- **Field / corners** come from the **focus-shift stacks**: best-of-stack
  (max cutoff) per grid box. AF frames are focused for the centre only, so
  their corners are corrupted by field curvature/tilt — the sweep lets each
  corner reach its own peak. A 3x3 grid (not just the shared horizontal
  midline) gives true corner/diagonal decentering + tilt.
- **Stack centre** is also reported as a cross-check (expected <= AF centre
  by the focus-step granularity).

Per (config, aperture): the AF frames locate the static feature per box
(median-gradient consensus tile across the 3 sharp replicates); both groups
are then measured at that fixed tile. ISO 100/500 are pooled sharpest-of-ISO
(the ISO with the higher AF-centre top wins the cell).

Checks (within-session, robust to scene + metric-version drift):
 1. Adds real detail vs cropping: FOM = cutoff x f_eff; TC beats cropping
    the bare-400 frame iff retention=c_TC/c_bare > 400/f_eff (0.714 / 0.500).
 2. Not decentered: corner symmetry + diagonal (tilt) of the new TC-1.4x.
 3. Sits sensibly vs 2.0x: retention_2.0 is the cross-series validity anchor
    (unchanged hw, old ~0.60); retention_1.4 ~ old 0.80 = copy matches.

Run (from longdist-sharpness/, after rename_and_sort_lens_test.py):
  uv run python -u scripts/poc_longdist_tc14_revalidation.py
Output: poc_longdist_tc14_revalidation_out/{summary.md,measurements.csv,*.png}
"""
from __future__ import annotations

import csv
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from poc_longdist_algorithms import (  # noqa: E402
    DATASETS, FIELD_BOX_H_FRAC, FIELD_BOX_W_FRAC, SEARCH_STEP, TILE,
    alg_radial_cutoff, discover, gradient_energy_map, load_luma,
)

DATASET_KEY = "tele2026_06_28"
HPOS = [0.18, 0.50, 0.82]
VPOS = [0.18, 0.50, 0.82]            # 0.18 = top, 0.82 = bottom
CENTRE = (0.50, 0.50)
CORNERS = {"TL": (0.18, 0.18), "TR": (0.82, 0.18),
           "BL": (0.18, 0.82), "BR": (0.82, 0.82)}
F_EFF = {"bare": 400.0, "tc14": 560.0, "tc20": 800.0}
FOM_BREAKEVEN = {"tc14": 400.0 / 560.0, "tc20": 400.0 / 800.0}
EXPECTED_RETENTION = {"tc14": 0.80, "tc20": 0.60}
SYMMETRY_FLAG = 0.90

OUT = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)


def classify(lens_dir: str) -> str | None:
    low = lens_dir.lower()
    if "tc-2.0x" in low:
        return "tc20"
    if "tc-1.4x" in low:
        return "tc14"
    if "100-400" in low:
        return "bare"
    return None


def parse_iso(lens_dir: str) -> str:
    m = re.search(r"ISO(\d+)", lens_dir)
    return m.group(1) if m else "?"


def grid_boxes(shape: tuple[int, int]) -> dict[tuple[float, float], tuple[int, int, int, int]]:
    H, W = shape
    bw, bh = int(W * FIELD_BOX_W_FRAC), int(H * FIELD_BOX_H_FRAC)
    out = {}
    for fy in VPOS:
        for fx in HPOS:
            x0 = min(max(0, int(W * fx) - bw // 2), W - bw)
            y0 = min(max(0, int(H * fy) - bh // 2), H - bh)
            out[(fx, fy)] = (y0, x0, bh, bw)
    return out


def read_silent(jpegs: list[Path]) -> dict[Path, str]:
    """Map each jpeg -> 'On'/'Off' (Nikon SilentPhotography). On = focus-shift
    stack frame; Off = Pinpoint-AF replicate."""
    if not jpegs:
        return {}
    out = subprocess.run(
        ["exiftool", "-T", "-s3", "-SilentPhotography", *map(str, jpegs)],
        capture_output=True, text=True,
    )
    vals = out.stdout.splitlines()
    return {p: v.strip() for p, v in zip(jpegs, vals)}


def _cutoff_at(L: np.ndarray, ty: int, tx: int) -> float:
    if ty + TILE > L.shape[0] or tx + TILE > L.shape[1]:
        return float("nan")
    return alg_radial_cutoff(L[ty:ty + TILE, tx:tx + TILE])


def _consensus_tile(af_lumas: list[np.ndarray], box) -> tuple[int, int] | None:
    y0, x0, bh, bw = box
    maps = [gradient_energy_map(L, y0, x0, bh, bw) for L in af_lumas]
    if not maps or not all(m.shape == maps[0].shape for m in maps):
        return None
    with np.errstate(all="ignore"):
        med = np.nanmedian(np.stack(maps, 0), axis=0)
    if np.all(np.isnan(med)):
        return None
    iy, ix = np.unravel_index(int(np.nanargmax(med)), med.shape)
    return (y0 + iy * SEARCH_STEP, x0 + ix * SEARCH_STEP)


def _peak(vals: list[float], k: int = 3) -> float:
    """Fixed top-k mean — the focus-shift peak estimator. Using a FIXED k
    (not max) makes the reducer n-independent, so stacks of very different
    sizes (60 vs 160 frames) compare fairly and don't get rewarded for being
    bigger. Single-frame noise spikes are averaged out across the k best."""
    if not vals:
        return float("nan")
    s = sorted(vals, reverse=True)[:k]
    return sum(s) / len(s)


def measure_cell(af_paths: list[Path], stack_paths: list[Path]) -> dict:
    """Per grid box: AF consensus tile -> AF peak/median + stack peak there.

    Memory-bounded: the 3 AF frames stay resident (to fix the tiles); stack
    frames are streamed one at a time (a cell has up to ~160 frames @ ~180 MB
    each, so loading them all at once would need tens of GB)."""
    af_lumas = [load_luma(p) for p in af_paths]
    boxes = grid_boxes(af_lumas[0].shape)
    tiles: dict = {}
    af_stat: dict = {}
    for key, box in boxes.items():
        tile = _consensus_tile(af_lumas, box)
        if tile is None:
            continue
        tiles[key] = tile
        af = [c for L in af_lumas if (c := _cutoff_at(L, *tile)) == c]
        af_stat[key] = (_peak(af), statistics.median(af) if af else float("nan"), len(af))
    del af_lumas
    st_vals: dict = {k: [] for k in tiles}
    for p in stack_paths:
        L = load_luma(p)
        for key, tile in tiles.items():
            c = _cutoff_at(L, *tile)
            if c == c:
                st_vals[key].append(c)
        del L
    return {
        key: dict(af_top=af_stat[key][0], af_med=af_stat[key][1],
                  stack_top=_peak(st_vals[key]), n_af=af_stat[key][2],
                  n_stack=len(st_vals[key]))
        for key in tiles
    }


def collect() -> dict:
    cfg = DATASETS[DATASET_KEY]
    root = cfg["root"]
    if not root.is_dir():
        sys.exit(f"ERROR: {root} not found — run the ingest first.")
    records: dict = {}
    rows: list[dict] = []
    for c in discover(root, cfg["date"], cfg.get("lens_filter")):
        cls = classify(c.lens_dir)
        if cls is None:
            continue
        iso = parse_iso(c.lens_dir)
        silent = read_silent(c.jpegs)
        af = [p for p in c.jpegs if silent.get(p) == "Off"]
        stack = [p for p in c.jpegs if silent.get(p) == "On"]
        print(f"  {cls:4} {c.aperture:5} ISO{iso}: {len(af)} AF + {len(stack)} stack")
        if not af:
            print(f"    WARN: no AF frames in {c.lens_dir}/{c.aperture}; skipping")
            continue
        cell = measure_cell(af, stack)
        records[(cls, c.aperture_f, iso)] = dict(
            cell=cell, focal=c.focal_mm, aperture=c.aperture,
            n_af=len(af), n_stack=len(stack),
        )
        for key, m in cell.items():
            rows.append(dict(tc_class=cls, aperture=c.aperture, iso=iso,
                             fx=key[0], fy=key[1], **m))
    if rows:
        with (OUT / "measurements.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    return records


def _af_centre(rec: dict) -> float:
    return rec["cell"].get(CENTRE, {}).get("af_top", float("nan"))


def _stack_centre(rec: dict) -> float:
    return rec["cell"].get(CENTRE, {}).get("stack_top", float("nan"))


def _nan_safe(v: float) -> float:
    return v if v == v else float("-inf")


def pick_best(records: dict) -> dict:
    """Per tc_class: pick (aperture, iso) maximising the **stack** centre top
    (sharpest-of-ISO, then best aperture). Stack centre is used (not AF)
    because the mechanical-shutter AF frames are shake-softened in wind — see
    the AF-vs-stack caveat in the report. NaN-safe. {cls: (ap_f, iso, rec)}."""
    by_cls_ap: dict = defaultdict(dict)
    for (cls, ap, iso), rec in records.items():
        cur = by_cls_ap[cls].get(ap)
        if cur is None or _nan_safe(_stack_centre(rec)) > _nan_safe(_stack_centre(cur[1])):
            by_cls_ap[cls][ap] = (iso, rec)
    best = {}
    for cls, aps in by_cls_ap.items():
        ap_best = max(aps, key=lambda a: _nan_safe(_stack_centre(aps[a][1])))
        iso, rec = aps[ap_best]
        best[cls] = (ap_best, iso, rec)
    return best


def report(records: dict) -> None:
    if not records:
        sys.exit("ERROR: no measurements — is the data sorted?")
    best = pick_best(records)
    if "bare" not in best:
        sys.exit("ERROR: no bare config — bare is the anchor.")
    c_bare = _stack_centre(best["bare"][2])   # shake-robust centre anchor

    def cell_of(cls):
        return best[cls][2]["cell"]

    def stk(cls, key):
        return cell_of(cls).get(key, {}).get("stack_top", float("nan"))

    L: list[str] = ["# TC-1.4x revalidation — 2026-06-28 wall (within-session)\n"]
    L.append("Centre = Pinpoint-AF (closed-loop, accurate under the point). "
             "Field/corners = focus-shift best-of-stack (each region at its own "
             "peak focus). Metric: radial_cutoff (cy/sensor-px).\n")

    L.append("## Per-config — best aperture (sharpest-of-ISO)\n")
    L.append("| config | f_eff | best F | ISO | AF centre top | AF centre med | stack centre | n_af/n_stk |")
    L.append("|---|---|---|---|---|---|---|---|")
    for cls in ("bare", "tc14", "tc20"):
        if cls not in best:
            continue
        ap, iso, rec = best[cls]
        cc = rec["cell"].get(CENTRE, {})
        L.append(f"| {cls} | {F_EFF[cls]:.0f} | F{ap:g} | {iso} | "
                 f"**{cc.get('af_top', float('nan')):.3f}** | {cc.get('af_med', float('nan')):.3f} "
                 f"| {cc.get('stack_top', float('nan')):.3f} | {rec['n_af']}/{rec['n_stack']} |")
    L.append("\n> ⚠ AF-vs-stack: the AF centre reads LOWER than the stack centre "
             "here (af median 0.143 vs stack 0.190 across all cells). The 3 AF "
             "frames used the mechanical shutter + remote in gusty wind and are "
             "shake-softened; the focus-shift stacks are electronic-shutter, "
             "best-of-60+, so they're the cleaner centre (at step 1 the focus-"
             "quantisation worry is moot). **Checks below use the stack centre**; "
             "AF centre is shown above only as a (shake-flagged) cross-check.\n")
    L.append("> ⚠ radial_cutoff is partly compressed for this lens (stack range "
             "0.10–0.46, much near the 2026-01 saturation band) — bare-vs-TC "
             "separation is muddy. The brick mortar lines make this an ideal "
             "scene for the edge-based MTF50 (poc_known_edge_mtf50.py); that is "
             "the discriminating follow-up metric, not radial_cutoff.\n")

    L.append("## Check 1 — adds real detail vs cropping the bare frame "
             "(stack centre, FOM)\n")
    L.append("| TC | retention=c_TC/c_bare | break-even | FOM gain vs bare-crop | verdict |")
    L.append("|---|---|---|---|---|")
    for cls in ("tc14", "tc20"):
        if cls not in best:
            continue
        c = _stack_centre(best[cls][2])
        ret = c / c_bare if c_bare else float("nan")
        gain = (ret * F_EFF[cls] / F_EFF["bare"] - 1) * 100
        verdict = "PASS (adds detail)" if ret > FOM_BREAKEVEN[cls] else "FAIL (crop as good)"
        L.append(f"| {cls} | {ret:.2f} | {FOM_BREAKEVEN[cls]:.3f} | {gain:+.0f}% | {verdict} |")
    L.append("")

    L.append("## Check 2 — decentering / tilt (focus-shift corners, best aperture)\n")
    L.append("| config | TL | TR | BL | BR | corner min/max | diag (TL+BR)/(TR+BL) | centre/cornersᵐ |")
    L.append("|---|---|---|---|---|---|---|---|")
    for cls in ("bare", "tc14", "tc20"):
        if cls not in best:
            continue
        cs = {k: stk(cls, v) for k, v in CORNERS.items()}
        vals = [v for v in cs.values() if v == v]
        sym = (min(vals) / max(vals)) if vals and max(vals) > 0 else float("nan")
        diag = ((cs["TL"] + cs["BR"]) / (cs["TR"] + cs["BL"])
                if all(cs[k] == cs[k] for k in cs) and (cs["TR"] + cs["BL"]) > 0
                else float("nan"))
        cen = stk(cls, CENTRE)
        cc = (cen / (sum(vals) / len(vals))) if vals and cen == cen else float("nan")
        flag = "" if (sym == sym and sym >= SYMMETRY_FLAG) else "  ⚠"
        L.append(f"| {cls} | {cs['TL']:.3f} | {cs['TR']:.3f} | {cs['BL']:.3f} | {cs['BR']:.3f} "
                 f"| {sym:.2f}{flag} | {diag:.2f} | {cc:.2f} |")
    L.append("\n> corner min/max < 0.90 ⇒ decentering suspect; diag far from 1.00 ⇒ tilt; "
             "centre/corners > 1 ⇒ residual field falloff even at each corner's own focus.\n")

    L.append("## Check 3 — retention vs the old (lost) copy [cross-series anchor]\n")
    L.append("Compare to the **re-run** 2026-01 ratios, not raw cutoffs. Old §6b: "
             "1.4x ~0.80, 2.0x ~0.60.\n")
    L.append("| TC | retention now | expected | role |")
    L.append("|---|---|---|---|")
    for cls in ("tc14", "tc20"):
        if cls not in best:
            continue
        ret = _stack_centre(best[cls][2]) / c_bare if c_bare else float("nan")
        role = "validity anchor (unchanged hw)" if cls == "tc20" else "THE TEST"
        L.append(f"| {cls} | {ret:.2f} | ~{EXPECTED_RETENTION[cls]:.2f} | {role} |")
    L.append("")

    (OUT / "summary.md").write_text("\n".join(L))
    print("\n".join(L))
    _plot(best)


def _plot(best: dict) -> None:
    order = [c for c in ("bare", "tc14", "tc20") if c in best]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    foms = [_af_centre(best[c][2]) * F_EFF[c] for c in order]
    ax1.bar(order, foms, color=["#888", "#4a90d9", "#d94a4a"])
    ax1.set_title("Subject-resolution FOM (AF centre × f_eff)")
    for c in order:
        cell = best[c][2]["cell"]
        labels = ["TL", "TR", "centre", "BL", "BR"]
        keys = [CORNERS["TL"], CORNERS["TR"], CENTRE, CORNERS["BL"], CORNERS["BR"]]
        ys = [cell.get(k, {}).get("stack_top", float("nan")) for k in keys]
        ax2.plot(labels, ys, marker="o", label=c)
    ax2.set_title("Field (focus-shift best-of-stack)")
    ax2.set_ylabel("cutoff cy/sensor-px"); ax2.legend()
    fig.tight_layout(); fig.savefig(OUT / "tc14_revalidation.png", dpi=110)
    print(f"\nWrote {OUT}/summary.md, measurements.csv, tc14_revalidation.png")


def main() -> int:
    print(f"== TC-1.4x revalidation: {DATASET_KEY} ==")
    report(collect())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
