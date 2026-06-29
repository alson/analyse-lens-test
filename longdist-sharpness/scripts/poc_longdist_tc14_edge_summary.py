"""TC-1.4x revalidation — EDGE-MTF50 summary (primary metric).

Post-processes poc_known_edge_mtf50_out/tele2026_06_28/per_measurement.csv
(produced by `poc_known_edge_mtf50.py dataset tele2026_06_28`) into the
within-session bare/TC-1.4x/TC-2.0x comparison.

Why edge-MTF50 (not radial_cutoff): radial_cutoff saturates for the
Z 100-400 (gave physically impossible tc14<tc20). Slanted-edge MTF50 on the
wall's chalk/placard edges has real dynamic range (0.21–0.49 cy/px) and
physical units, and is measured per fixed edge (no focus-shift frame-count
bias). The focus-shift stack supplies each edge's peak focus: per edge we
take the **best-focus** value = max over all frames of that edge.

Two readings:
- **MTF50** (cy/sensor-px) — standard, but caps at ~0.49 (Nyquist) for the
  sharpest edges, so it saturates at the top.
- **MTF@Nyquist** (contrast at 0.5 cy/px, 0–1) — keeps discriminating in the
  saturated regime; used as the primary sharpness index here.

Aggregation: per (tc_class, aperture) pool both ISOs; per edge take its
best-focus value; summarise edges by median (typical) and p90 (best). Pick
each config's best aperture by median MTF@Nyquist. Retention = c_TC/c_bare.
Decentering: at best aperture, split edges left/right and top/bottom by
position and compare medians.

Run (after the dataset run finishes):
  uv run python -u scripts/poc_longdist_tc14_edge_summary.py
"""
from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path

IN = (Path(__file__).parent / "poc_known_edge_mtf50_out" / "tele2026_06_28"
      / "per_measurement.csv")
OUT = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

F_EFF = {"bare": 400.0, "tc14": 560.0, "tc20": 800.0}
FOM_BREAKEVEN = {"tc14": 400.0 / 560.0, "tc20": 400.0 / 800.0}
W, H = 8256, 5504            # Z7 frame, for L/R + T/B splits
LEFT_X, RIGHT_X = 0.40 * W, 0.60 * W
TOP_Y, BOT_Y = 0.40 * H, 0.60 * H


def classify(lens_dir: str) -> str | None:
    low = lens_dir.lower()
    if "tc-2.0x" in low:
        return "tc20"
    if "tc-1.4x" in low:
        return "tc14"
    if "100-400" in low:
        return "bare"
    return None


def _f(x: str) -> float:
    try:
        v = float(x)
        return v
    except (ValueError, TypeError):
        return float("nan")


def load_best_focus() -> list[dict]:
    """Per (lens_dir, focal, aperture_f, edge_id): best-focus = max over
    frames of mtf50 and (separately) mtf_at_nyquist. Returns edge records."""
    if not IN.is_file():
        raise SystemExit(f"ERROR: {IN} not found — run the dataset mode first:\n"
                         f"  uv run python scripts/poc_known_edge_mtf50.py "
                         f"dataset tele2026_06_28 --min-line-px 200 --top-k 15")
    agg: dict = {}
    for r in csv.DictReader(IN.open()):
        if r.get("role") != "test":          # skip the REF rows
            continue
        cls = classify(r["lens_dir"])
        if cls is None:
            continue
        key = (cls, r["lens_dir"], _f(r["aperture_f"]), r["edge_id"])
        m50, mnq = _f(r["mtf50"]), _f(r["mtf_at_nyquist"])
        cur = agg.get(key)
        if cur is None:
            agg[key] = dict(cls=cls, ap=_f(r["aperture_f"]),
                            edge_id=r["edge_id"], mid_x=_f(r["edge_mid_x"]),
                            mid_y=_f(r["edge_mid_y"]),
                            mtf50=m50, nyq=mnq)
        else:
            if m50 == m50 and not (cur["mtf50"] >= m50):
                cur["mtf50"] = m50
            if mnq == mnq and not (cur["nyq"] >= mnq):
                cur["nyq"] = mnq
    return list(agg.values())


def _med(xs):
    xs = [x for x in xs if x == x]
    return statistics.median(xs) if xs else float("nan")


def _p90(xs):
    xs = sorted(x for x in xs if x == x)
    return xs[min(len(xs) - 1, int(0.9 * len(xs)))] if xs else float("nan")


def main() -> int:
    edges = load_best_focus()
    # per (cls, aperture): pooled edge best-focus values
    per = defaultdict(lambda: defaultdict(list))   # cls -> ap -> [edge dict]
    for e in edges:
        per[e["cls"]][e["ap"]].append(e)

    # best aperture per cls by median MTF@Nyquist
    best = {}
    for cls, aps in per.items():
        ap_best = max(aps, key=lambda a: (_med([e["nyq"] for e in aps[a]])
                                          if aps[a] else float("-inf")))
        best[cls] = (ap_best, aps[ap_best])

    L = ["# TC-1.4x revalidation — EDGE-MTF50 (primary metric), 2026-06-28 wall\n"]
    L.append("Slanted-edge MTF50 on chalk/placard edges; per edge = best-focus "
             "(max over focus-shift frames). MTF@Nyquist is the un-saturated "
             "sharpness index.\n")
    if "bare" not in best:
        raise SystemExit("ERROR: no bare config in edge data.")

    L.append("## Per-config — best aperture (median over edges; n edges)\n")
    L.append("| config | f_eff | best F | n_edges | median MTF50 | p90 MTF50 | median MTF@Nyq | p90 MTF@Nyq |")
    L.append("|---|---|---|---|---|---|---|---|")
    summ = {}
    for cls in ("bare", "tc14", "tc20"):
        if cls not in best:
            continue
        ap, es = best[cls]
        m50s = [e["mtf50"] for e in es]
        nqs = [e["nyq"] for e in es]
        summ[cls] = dict(ap=ap, es=es, med50=_med(m50s), med_nq=_med(nqs))
        L.append(f"| {cls} | {F_EFF[cls]:.0f} | F{ap:g} | {len(es)} | "
                 f"{_med(m50s):.3f} | {_p90(m50s):.3f} | **{_med(nqs):.3f}** | {_p90(nqs):.3f} |")
    L.append("")

    L.append("## Check 1 — adds real detail vs cropping (MTF@Nyquist, FOM)\n")
    L.append("| TC | retention (Nyq) | retention (MTF50) | break-even | FOM gain | verdict |")
    L.append("|---|---|---|---|---|---|")
    b_nq, b_50 = summ["bare"]["med_nq"], summ["bare"]["med50"]
    for cls in ("tc14", "tc20"):
        if cls not in summ:
            continue
        r_nq = summ[cls]["med_nq"] / b_nq if b_nq else float("nan")
        r_50 = summ[cls]["med50"] / b_50 if b_50 else float("nan")
        gain = (r_nq * F_EFF[cls] / F_EFF["bare"] - 1) * 100
        verdict = "PASS (adds detail)" if r_nq > FOM_BREAKEVEN[cls] else "FAIL (crop as good)"
        L.append(f"| {cls} | {r_nq:.2f} | {r_50:.2f} | {FOM_BREAKEVEN[cls]:.3f} | {gain:+.0f}% | {verdict} |")
    L.append("\n> retention should order bare > tc14 > tc20 in cy/sensor-px "
             "(more TC = more MTF loss). If tc14 < tc20 the data is still "
             "confounded.\n")

    L.append("## Check 2 — decentering / tilt (best-focus edges by position)\n")
    L.append("| config | n L / R | median L | median R | L/R | n T / B | median T | median B | T/B |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for cls in ("bare", "tc14", "tc20"):
        if cls not in summ:
            continue
        es = summ[cls]["es"]
        Lh = [e["nyq"] for e in es if e["mid_x"] < LEFT_X]
        Rh = [e["nyq"] for e in es if e["mid_x"] > RIGHT_X]
        Th = [e["nyq"] for e in es if e["mid_y"] < TOP_Y]
        Bh = [e["nyq"] for e in es if e["mid_y"] > BOT_Y]
        lr = (min(_med(Lh), _med(Rh)) / max(_med(Lh), _med(Rh))
              if _med(Lh) == _med(Lh) and _med(Rh) == _med(Rh) else float("nan"))
        tb = (min(_med(Th), _med(Bh)) / max(_med(Th), _med(Bh))
              if _med(Th) == _med(Th) and _med(Bh) == _med(Bh) else float("nan"))
        L.append(f"| {cls} | {len(Lh)}/{len(Rh)} | {_med(Lh):.3f} | {_med(Rh):.3f} | {lr:.2f} "
                 f"| {len(Th)}/{len(Bh)} | {_med(Th):.3f} | {_med(Bh):.3f} | {tb:.2f} |")
    L.append("\n> L/R or T/B << 1.0 (with enough edges each side) ⇒ decentering/tilt. "
             "Few edges per side ⇒ low confidence (edges cluster where chalk is).\n")

    (OUT / "summary.md").write_text("\n".join(L))
    print("\n".join(L))
    print(f"\nWrote {OUT}/summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
