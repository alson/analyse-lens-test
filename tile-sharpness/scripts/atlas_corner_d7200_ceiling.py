#!/usr/bin/env python3
"""Diffraction+Nyquist ceiling overlay for the D7200 atlas centre/corner MTF50.

Post-processes ``out_atlas_corner_d7200/atlas_corner_d7200.csv`` (no re-measurement):
for each config compute the physical subject-space MTF50 ceiling and the headroom
(measured/ceiling) at centre + each corner, so the documented scribe-LSF over-read
(which grows stopping down — centre rises F8->F16, corners can exceed centre) is
flagged and only glass-limited readings drive the ranking.

Ceiling = min(diffraction, sensor-Nyquist), subject space (lp/mm on the subject):
  * diffraction: ``optics.diffraction_mtf50_sensor_lpmm(N_eff) * M``. The CSV ``n_eff``
    is ALREADY the effective (bellows-corrected) f-number — the DX folder aperture is
    effective and was used directly — so we do NOT re-apply (1+M) here (that would
    double-count the bellows factor). Hence sensor-MTF50(N_eff) * M, not
    ``diffraction_mtf50_subject_lpmm`` (which takes a MARKED N and applies 1+M).
  * Nyquist: ``(0.5 / pitch_mm) * M`` with the D7200 DX pitch 3.91 um (from cameras.py).

Regime (matches scripts/diffraction_ranking.py):
  headroom > 1.05  -> OVER-READ (physically impossible; slanted-edge artifact)
  0.75..1.05       -> diffraction-limited (at the wall; measured ~= physical bound)
  0.40..0.75       -> transition
  < 0.40           -> glass/focus-limited (robustly so — over-read only inflates, so a
                      low-headroom read is a trustworthy lower bound)
"Glass-limited" (trustworthy for ranking) = headroom < 0.75.

CAVEATS (lead with these):
  * OLPF: the D7200 has an anti-alias filter, which lowers the TRUE achievable MTF
    BELOW the bare-diffraction ceiling used here. So the ceiling is optimistic for
    D7200 — a reading near/above it is doubly an artifact, and headroom understates how
    over-read a stopped-down config is. The glass-limited classification stays safe
    (OLPF only lowers the true value further below a low-headroom read).
  * The diffraction/Nyquist ceiling catches APERTURE/diffraction over-reads (the F16
    inflation) but NOT sub-ceiling corner-to-corner scribe asymmetry (e.g. one corner
    2-3x another while both sit under the ceiling) — that residual LSF artifact is
    reported via corner spread, not the ceiling.
  * Absolute lp/mm is NOT comparable to the Z7 (different pitch + OLPF). Within-D7200
    only.
"""
from __future__ import annotations

import csv
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from tile_sharpness import optics                      # noqa: E402
from tile_sharpness.cameras import get_camera          # noqa: E402

IN_CSV = os.path.join(os.path.dirname(__file__), "..",
                      "out_atlas_corner_d7200", "atlas_corner_d7200.csv")
OUT_CSV = os.path.join(os.path.dirname(__file__), "..",
                       "out_atlas_corner_d7200", "atlas_corner_d7200_ceiling.csv")

CORNERS = ("TL", "TR", "BL", "BR")
GLASS_LIMITED_MAX = 0.75   # headroom below this -> trustworthy (glass/focus-limited)
OVER_READ_MIN = 1.05       # headroom above this -> physically impossible over-read
PITCH_UM = get_camera("D7200").pitch_um   # 3.91


def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def regime(h):
    if h is None:
        return "n/a"
    if h > OVER_READ_MIN:
        return "over-read"
    if h >= 0.75:
        return "diffraction-ltd"
    if h >= 0.40:
        return "transition"
    return "glass-ltd"


def subject_ceiling(n_eff, M):
    """min(diffraction, Nyquist) subject-space MTF50 (lp/mm). n_eff is EFFECTIVE."""
    diff = optics.diffraction_mtf50_sensor_lpmm(n_eff) * M      # n_eff already effective
    nyq = (0.5 / (PITCH_UM / 1000.0)) * M
    kind = "diffraction" if diff <= nyq else "nyquist"
    return min(diff, nyq), kind


def main():
    with open(IN_CSV, newline="") as fh:
        rows = list(csv.DictReader(fh))

    out = []
    for r in rows:
        M = _f(r.get("M"))
        n_eff = _f(r.get("n_eff"))
        reg = str(r.get("registered", "")).lower() == "true"
        rec = dict(label=r["label"], aperture=_f(r.get("aperture")), M=M, n_eff=n_eff,
                   centre=_f(r.get("centre")))
        if not (reg and M and n_eff and M > 0 and n_eff > 0):
            rec.update(ceiling=None, ceiling_kind="n/a", centre_headroom=None,
                       centre_regime="n/a", corners_over_read=None, corner_spread=None)
            out.append(rec)
            continue
        ceil, kind = subject_ceiling(n_eff, M)
        rec["ceiling"] = round(ceil, 1)
        rec["ceiling_kind"] = kind
        cen = rec["centre"]
        rec["centre_headroom"] = round(cen / ceil, 3) if cen else None
        rec["centre_regime"] = regime(rec["centre_headroom"])
        cvals = []
        n_over = 0
        for c in CORNERS:
            v = _f(r.get(c))
            h = round(v / ceil, 3) if v else None
            rec[f"{c}_headroom"] = h
            if h is not None:
                cvals.append(v)
                if h > OVER_READ_MIN:
                    n_over += 1
        rec["corners_over_read"] = n_over
        # sub-ceiling corner asymmetry guard (LSF artifact the ceiling can't catch)
        rec["corner_spread"] = (round(max(cvals) / min(cvals), 2)
                                if len(cvals) >= 2 and min(cvals) > 0 else None)
        out.append(rec)

    cols = (["label", "aperture", "M", "n_eff", "centre", "ceiling", "ceiling_kind",
             "centre_headroom", "centre_regime"]
            + [f"{c}_headroom" for c in CORNERS]
            + ["corners_over_read", "corner_spread"])
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for rec in out:
            w.writerow({k: rec.get(k) for k in cols})

    # ---- calibrated report -------------------------------------------------- #
    reg = [r for r in out if r.get("centre_headroom") is not None]
    n_total = len(reg)
    n_cen_over = sum(1 for r in reg if r["centre_regime"] == "over-read")
    n_cen_diff = sum(1 for r in reg if r["centre_regime"] == "diffraction-ltd")
    n_cen_glass = sum(1 for r in reg if r["centre_headroom"] < GLASS_LIMITED_MAX)
    n_any_corner_over = sum(1 for r in reg if (r.get("corners_over_read") or 0) > 0)

    # Per-lens over-read diagnostic: the LSF over-read GROWS with N_eff, so a centre
    # that RISES from F8 to F11/F16 (instead of falling with diffraction) is inflated
    # throughout — its absolute value is upper-biased. Taking max-over-apertures would
    # reward the over-read, so we DON'T rank on it.
    by_lens_ap = {}
    for r in reg:
        by_lens_ap.setdefault(r["label"].split(" | ")[0], {})[r["aperture"]] = r["centre"]

    def rises_stopping_down(aps):
        c8, c11, c16 = aps.get(8.0), aps.get(11.0), aps.get(16.0)
        return (c8 and c11 and c11 > c8 * 1.05) or (c11 and c16 and c16 > c11 * 1.05)

    # PRIMARY: fixed F8-effective centre (least-inflated fair cross-lens comparison),
    # glass-limited only. F8-eff is a common aperture across the set and the widest that
    # is glass-limited for essentially all configs, so the over-read bias is smallest.
    f8 = [r for r in reg if r["aperture"] == 8.0 and r["centre_headroom"] < GLASS_LIMITED_MAX]
    f8.sort(key=lambda r: r["centre"], reverse=True)

    print(f"D7200 atlas centre/corner — diffraction+Nyquist ceiling overlay "
          f"(pitch {PITCH_UM} um)\n{'='*72}")
    print(f"configs: {n_total}   centre over-read (>1.05): {n_cen_over}   "
          f"centre diffraction-ltd (0.75-1.05): {n_cen_diff}   "
          f"centre glass-ltd (<0.75, trustworthy): {n_cen_glass}")
    print(f"configs with >=1 over-read CORNER: {n_any_corner_over} "
          f"(corner scribe-LSF artifact, mostly sub-ceiling asymmetry)")
    print("CAVEAT: even glass-limited absolute centre values are UPPER-BIASED by the LSF "
          "over-read (worse stopping down); OLPF lowers the true value further. So the\n"
          "        ranking below is a within-D7200 comparison at a FIXED WIDE aperture "
          "(F8-eff, least-inflated); treat values as upper bounds, order as indicative.\n")
    print("CALIBRATED centre ranking @ F8-effective (glass-limited, least-inflated fair "
          "comparison):")
    print(f"  {'lens':<50} {'ctr':>5} {'M':>5} {'hdrm':>5} {'cnrSpread':>9} {'trend':>6}")
    for r in f8:
        lens = r["label"].split(" | ")[0]
        trend = "RISES" if rises_stopping_down(by_lens_ap.get(lens, {})) else "ok"
        print(f"  {lens:<50} {r['centre']:>5.1f} {r['M']:>5.2f} "
              f"{r['centre_headroom']:>5.2f} {str(r.get('corner_spread')):>9} {trend:>6}")
    print("  (trend=RISES: this lens's centre climbs when stopped down -> over-read-"
          "contaminated, absolute value especially untrustworthy)")
    diff_only = sorted(
        (r for r in reg if r["centre_headroom"] >= GLASS_LIMITED_MAX),
        key=lambda r: r["centre_headroom"], reverse=True)
    print(f"\nDIFFRACTION-LIMITED / OVER-READ centres (measured NOT trustworthy; "
          f"physical bound = ceiling):")
    for r in diff_only[:12]:
        print(f"  {r['label']:<58} centre={r['centre']:>5.1f} "
              f"ceiling={r['ceiling']:>5.1f} hdrm={r['centre_headroom']:.2f} "
              f"[{r['centre_regime']}]")
    print(f"\nwrote {OUT_CSV}")


if __name__ == "__main__":
    main()
