"""Paired same-edge check for the §5.6e over-read fix.

The aggregate run (poc_lsf_overread_fix.py) showed centroid_hann has a
lower median MTF50 than endtaper AND measures ~3x more edges. This script
rules out the confound "the lower median is just from adding softer
low-contrast edges": it compares endtaper vs centroid_hann on the
*same* edges (per-edge median across in-focus AF frames, intersection
of edges both variants measure) at the diffraction-limited apertures.

A genuine per-edge over-read reduction => paired delta < 0 on the common
set, and centroid_hann's over-ceiling fraction lower on that common set.

Run on nufan:
    direnv exec . uv run python -u scripts/poc_lsf_overread_paired.py
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import poc_known_edge_mtf50 as ke
import poc_longdist_tc14_brick as brick
import poc_longdist_tc14_raw as rawpoc
import poc_lsf_overread_fix as P

CONFIGS = [
    ("bare f/11", P.BARE, "400.0 mm", "F11", 11.0),
    ("bare f/16", P.BARE, "400.0 mm", "F16", 16.0),
    ("tc14 f/11", P.TC14, "560.0 mm", "F11", 11.0),
]
VARIANTS = {"endtaper": dict(window="endtaper"),
            "centroid_hann": dict(window="centroid_hann")}


def folders(tmpl, focal, ap):
    return [d for iso in ("100", "500")
            if (d := P.ROOT / tmpl.format(iso=iso) / focal / ap).is_dir()]


def main() -> int:
    out = ["# Paired same-edge: endtaper vs centroid_hann (per-edge median)\n"]
    for cname, tmpl, focal, ap, nmark in CONFIGS:
        fs = folders(tmpl, focal, ap)
        if not fs:
            out.append(f"## {cname}: no folder"); continue
        ceil = P._ceiling_cy_px(nmark)
        ref = rawpoc.develop_luma(rawpoc.detect_ref(fs[0]))
        H, Wd = ref.shape
        specs = brick.find_mortar_edges(rawpoc.to_uint8(ref), Wd, H)
        frames = [p for f in fs for p in P._af_frames(f, rawpoc)]
        acc = {v: [[] for _ in specs] for v in VARIANTS}
        accn = {v: [[] for _ in specs] for v in VARIANTS}
        for nef in frames:
            lin = rawpoc.develop_luma(nef)
            for i, s in enumerate(specs):
                built = ke._build_esf(lin, s)
                if built is None:
                    continue
                esf, bs = built
                for v, kw in VARIANTS.items():
                    r = ke._esf_to_metrics(esf, bs, **kw)
                    if r["mtf50"] == r["mtf50"]:
                        acc[v][i].append(r["mtf50"])
                    if r["mtf_at_nyquist"] == r["mtf_at_nyquist"]:
                        accn[v][i].append(r["mtf_at_nyquist"])
            del lin
        # per-edge medians; keep edges both variants measured
        e50 = {v: [statistics.median(c) if c else None for c in acc[v]] for v in VARIANTS}
        enq = {v: [statistics.median(c) if c else None for c in accn[v]] for v in VARIANTS}
        common = [i for i in range(len(specs))
                  if e50["endtaper"][i] is not None and e50["centroid_hann"][i] is not None]
        d50 = [e50["centroid_hann"][i] - e50["endtaper"][i] for i in common]
        dnq = [enq["centroid_hann"][i] - enq["endtaper"][i] for i in common
               if enq["endtaper"][i] is not None and enq["centroid_hann"][i] is not None]
        oc_base = sum(e50["endtaper"][i] > ceil for i in common) / max(len(common), 1)
        oc_hann = sum(e50["centroid_hann"][i] > ceil for i in common) / max(len(common), 1)
        out += [
            f"\n## {cname}  (ceiling {ceil:.3f} cy/px, {len(common)} common edges)\n",
            f"- median paired Δ MTF50 (hann − endtaper): **{statistics.median(d50):+.4f}** "
            f"(neg = hann reads lower on the same edge)",
            f"- median paired Δ MTF@Nyq: **{statistics.median(dnq):+.4f}**",
            f"- over-ceiling frac on common edges: endtaper {oc_base*100:.0f}% → "
            f"hann {oc_hann*100:.0f}%",
            f"- edges only endtaper measured: {sum(1 for i in range(len(specs)) if e50['endtaper'][i] is not None and e50['centroid_hann'][i] is None)}; "
            f"only hann: {sum(1 for i in range(len(specs)) if e50['centroid_hann'][i] is not None and e50['endtaper'][i] is None)}",
        ]
    txt = "\n".join(out)
    print(txt)
    OUTDIR = Path(__file__).parent / "poc_lsf_overread_fix_out"
    OUTDIR.mkdir(exist_ok=True)
    (OUTDIR / "paired.md").write_text(txt + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
