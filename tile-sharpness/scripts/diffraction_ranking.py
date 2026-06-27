"""Diffraction-ceiling overlay on the cross-config resolution ranking.

Reads every ``lens_characteristics*.csv`` (Phase 3 / ``characterise.py`` output:
subject-space MTF50 at centre / DX-corner / FX-corner, with measured M), parses
the working aperture from the slug, and for each config computes the
diffraction-limited subject-space MTF50 ceiling at its EFFECTIVE aperture
(``optics.diffraction_mtf50_subject_lpmm``). The ratio measured/ceiling
("headroom") classifies each config:

  * headroom >= 0.75  -> DIFFRACTION-limited (at the physical wall; more
    magnification via tubes/TCs only dims it further);
  * 0.40-0.75         -> mixed;
  * < 0.40            -> GLASS/FOCUS-limited (a better lens / wider aperture /
    refocus would help — the resolution shortfall is not diffraction);
  * > 1.05            -> measurement optimistic vs theory (slanted-edge over-read
    or a mis-stated effective aperture) — flagged.

This separates "real resolving power" from "empty magnification", which is the
key to the accessory questions (extension tubes / TCs push the effective
aperture to f/20+ where the ceiling collapses).

Pupil magnification is assumed 1 (symmetric) — conservative for telephotos
(24-120 / 100-400), whose true ceiling is a little higher. Override per lens if
needed. Output: scripts/diffraction_ranking_out/diffraction_ranking.{csv,png}
+ a printed ranked table.
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tile_sharpness.optics import diffraction_mtf50_subject_lpmm, effective_fnumber

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "diffraction_ranking_out"


def parse_slug(slug: str):
    """(lens, magnification_label, aperture N) from a sweep slug; N=None if absent."""
    tail = slug.split("/")[-1]
    parts = tail.split("__")
    n = None
    for tok in reversed(parts):
        mobj = re.fullmatch(r"[Ff]_?([0-9]+(?:\.[0-9]+)?)", tok)
        if mobj:
            n = float(mobj.group(1))
            break
    # lens name: drop a leading date token, keep up to the magnification label
    body = [p for p in parts if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", p)]
    lens = body[0] if body else tail
    mag_label = next((p for p in parts if re.fullmatch(r"\d+_\d+(\.\d+)?", p)), "")
    return lens, mag_label, n


def regime(headroom):
    if headroom is None or headroom != headroom:
        return "?"
    if headroom > 1.05:
        return "measured>theory!"
    if headroom >= 0.75:
        return "diffraction-ltd"
    if headroom >= 0.40:
        return "mixed"
    return "glass/focus-ltd"


def load():
    rows = []
    for f in sorted(glob.glob(str(ROOT / "out*" / "lens_characteristics*.csv"))):
        src = Path(f).parent.name
        df = pd.read_csv(f)
        for _, r in df.iterrows():
            lens, mag_label, n = parse_slug(str(r["sweep"]))
            try:
                M = float(r["m"])
            except (ValueError, TypeError):
                M = float("nan")
            cen = pd.to_numeric(r.get("mtf50_centre_lpmm"), errors="coerce")
            dx = pd.to_numeric(r.get("mtf50_dx_corner_mean_lpmm"), errors="coerce")
            fx = pd.to_numeric(r.get("mtf50_fx_corner_mean_lpmm"), errors="coerce")
            if not (M == M) or n is None or not (cen == cen):
                ceil = float("nan")
            else:
                ceil = diffraction_mtf50_subject_lpmm(n, M)
            rows.append(dict(src=src, lens=lens, mag=mag_label, N=n, M=M,
                             N_eff=(effective_fnumber(n, M) if (n and M == M) else float("nan")),
                             centre=cen, dx=dx, fx=fx, ceiling=ceil,
                             headroom=(cen / ceil if (ceil == ceil and ceil > 0) else float("nan"))))
    df = pd.DataFrame(rows)
    # dedup identical slugs across overlapping output dirs (keep first valid centre)
    df = df.sort_values("centre", ascending=False, na_position="last")
    df = df.drop_duplicates(subset=["lens", "mag", "N"], keep="first")
    return df


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = load()
    ranked = df[df["centre"].notna()].sort_values("centre", ascending=False).reset_index(drop=True)
    ranked["regime"] = ranked["headroom"].map(regime)
    # physically-defensible resolution: a real lens cannot beat its diffraction
    # ceiling, so clamp. Where measured > ceiling the true value is unknown
    # (over-read); the cap is the best lower-bound-consistent estimate.
    ranked["resolution_capped"] = ranked[["centre", "ceiling"]].min(axis=1)
    ranked.to_csv(OUT / "diffraction_ranking.csv", index=False)

    n_over = int((ranked["headroom"] > 1.05).sum())
    print(f"FINDING: {n_over}/{len(ranked)} configs report centre MTF50 ABOVE the "
          f"diffraction ceiling (physically impossible) — the scribe-LSF subject-MTF50\n"
          f"over-reads, worst when stopped down (f/11-f/16, where N_eff is largest and\n"
          f"true resolution lowest). The raw lp/mm ranking is therefore not physically\n"
          f"calibrated and over-rewards stopped-down configs. Use resolution_capped /\n"
          f"fix the metric (atlas-anchored, ceiling-validated) before ranking accessories.\n")

    print(f"{'centre':>7}{'ceil':>7}{'hdrm':>6}{'N':>5}{'Neff':>6}{'M':>6}  "
          f"{'regime':<16} lens [mag]")
    for _, r in ranked.iterrows():
        print(f"{r['centre']:7.1f}{r['ceiling']:7.1f}{r['headroom']:6.2f}"
              f"{(r['N'] or 0):5.1f}{r['N_eff']:6.1f}{r['M']:6.2f}  {r['regime']:<16} "
              f"{r['lens'][:34]} [{r['mag']}]")

    # scatter: measured centre vs diffraction ceiling; y=x line = the wall.
    fig, ax = plt.subplots(figsize=(9, 8))
    cmap = {"diffraction-ltd": "C3", "mixed": "C1", "glass/focus-ltd": "C0",
            "measured>theory!": "C4", "?": "0.6"}
    for reg, g in ranked.groupby("regime"):
        ax.scatter(g["ceiling"], g["centre"], s=55, alpha=0.8, color=cmap.get(reg, "k"), label=reg)
    lim = max(ranked["ceiling"].max(), ranked["centre"].max()) * 1.1
    ax.plot([0, lim], [0, lim], "k--", lw=1, alpha=.6, label="diffraction wall (y=x)")
    for _, r in ranked.iterrows():
        ax.annotate(f"{r['lens'][:14]} {r['mag']} f/{r['N']:g}", (r["ceiling"], r["centre"]),
                    fontsize=6, alpha=.7, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("diffraction ceiling, subject lp/mm (at N_eff)")
    ax.set_ylabel("measured centre MTF50, subject lp/mm")
    ax.set_title("Cross-config resolution vs diffraction ceiling\n"
                 "near the y=x wall = diffraction-limited; well below = glass/focus-limited")
    ax.set_xlim(0, lim); ax.set_ylim(0, lim); ax.grid(alpha=.3); ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "diffraction_ranking.png", dpi=120)
    print(f"\nsaved {OUT/'diffraction_ranking.csv'} and .png  ({len(ranked)} configs)")


if __name__ == "__main__":
    sys.exit(main())
