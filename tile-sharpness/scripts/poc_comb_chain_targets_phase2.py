"""Stage Targets — Phase 2: cross-M self-calibration stability per promising target.

UNTRACKED / exploratory. Pure-CSV re-analysis of poc_comb_chain_out/tn_all.csv (the
saturation-channel comb amplitudes from poc_comb_chain_tn_extract.py, all 16 configs,
M 0.90-2.09). No production / committed-lib module modified; we reuse the self-cal
machinery from poc_comb_chain_tn_analyse (imported) but apply it per target type and add
a dedicated SINGLE-PITCH maze test.

The decisive test (same as Stage T_n): across the M-range, does a target's harmonic
content collapse onto a SINGLE MTF(f_px) curve? Collapse residual (log-contrast units)
compared against:
  - the per-order-only null (remove a per-order mean, ignore MTF rolloff): if MTF is
    real the collapse must fall well below this;
  - the WITHIN-single-config floor (same M -> only region-replicate + measurement
    scatter): the cross-M residual cannot beat this; approaching it = stable.

Prior reference numbers (Stage T_n, this same data): magenta.P11 cross-M collapse 0.790
(orders<=3: 0.686) vs per-order null 0.866/0.719 vs WITHIN-config floor 0.382.

This phase answers the three user questions explicitly:
  Q1 MAZE on its own — it is single-pitch (one subject frequency, M-invariant), so its
     teeth at different M sample ONE MTF curve directly. We test whether all configs'
     maze contrasts fall on a single isotonic MTF(f_px): the maze "collapse residual" is
     then a pure cross-M stability number with no T_n freedom. Resolved range M>=0.7.
  Q2 CYAN regions — self-cal per cyan structure type; clean stable comb?
  Q3 OTHER magenta pitch clusters (P16, P35) vs P11.

Usage (nufan):
  PYTHONPATH=<src> ~/.cache/uv-venvs/tile-sharpness/bin/python \
      scripts/poc_comb_chain_targets_phase2.py
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_comb_chain_tn_analyse as T  # noqa: E402  (self_calibrate, isotonic, structure_type, load, valid)

OUT = HERE / "poc_comb_chain_out" / "targets"
OUT.mkdir(parents=True, exist_ok=True)

SNR_MIN = 3.0
MAX_OVER = 0.05
MIN_C = 1e-3


def within_config_floor(teeth):
    """Median over configs of the per-config self-cal collapse residual = the noise
    floor a single M imposes (region-replicate + measurement scatter, no cross-M)."""
    byc = defaultdict(list)
    for t in teeth:
        byc[t["config"]].append(t)
    res = []
    for cfg, ts in byc.items():
        if len(ts) < 6 or len(set(t["order"] for t in ts)) < 2:
            continue
        cal = T.self_calibrate(ts)
        res.append(cal["residual_rms"])
    return float(np.median(res)) if res else float("nan"), len(res)


def per_order_null(teeth):
    null_res = []
    for o in set(t["order"] for t in teeth):
        vals = np.array([t["logA"] for t in teeth if t["order"] == o])
        ww = np.array([t["w"] for t in teeth if t["order"] == o])
        if len(vals) < 2:
            continue
        null_res.append(np.sum(ww * (vals - np.average(vals, weights=ww)) ** 2))
    null_n = sum(t["w"] for t in teeth)
    return float(np.sqrt(sum(null_res) / null_n)) if null_n else float("nan")


def maze_single_pitch_collapse(maze_teeth):
    """The maze is single-pitch: one subject frequency, M-invariant. Its teeth across M
    land at different f_px -> they directly sample MTF(f_px). Fit ONE isotonic
    MTF(f_px) to ALL maze fundamentals (order 1) and report the collapse residual.
    Higher orders (only at high M) are kept separately for an even-harmonic note but the
    headline collapse is order-1-only (the genuine single-pitch cross-M test).

    Returns (collapse_resid_order1, within_config_floor, n_teeth, n_configs, M_span,
             fpx_span, curve).
    """
    o1 = [t for t in maze_teeth if t["order"] == 1]
    fpx = np.array([t["f_px"] for t in o1])
    logA = np.array([t["logA"] for t in o1])
    w = np.array([t["w"] for t in o1])
    fit = T.isotonic_decreasing(fpx, logA, w)
    resid = float(np.sqrt(np.sum(w * (logA - fit) ** 2) / np.sum(w)))
    # within-config floor: scatter of logA WITHIN each config (same M, same f_px region
    # replicates) around the config's own weighted mean.
    byc = defaultdict(list)
    for t in o1:
        byc[t["config"]].append(t)
    fl = []
    for cfg, ts in byc.items():
        if len(ts) < 3:
            continue
        vals = np.array([t["logA"] for t in ts]); ww = np.array([t["w"] for t in ts])
        m = np.average(vals, weights=ww)
        fl.append(np.sqrt(np.sum(ww * (vals - m) ** 2) / np.sum(ww)))
    floor = float(np.median(fl)) if fl else float("nan")
    Ms = sorted(set(round(t["M"], 2) for t in o1))
    return dict(resid=resid, floor=floor, n=len(o1), nconf=len(byc),
                Mspan=(min(Ms), max(Ms)), fpxspan=(float(fpx.min()), float(fpx.max())),
                curve=(fpx, np.exp(fit)))


def main():
    rows = T.load(HERE / "poc_comb_chain_out" / "tn_all.csv")
    rows = [r for r in rows if T.valid(r)]
    for r in rows:
        r["stype"] = T.structure_type(r)
        r["logA"] = np.log(max(r["C"], MIN_C))
        r["w"] = float(np.log1p(r["snr"]))
    typed = [r for r in rows if r["stype"] is not None]

    by_type = defaultdict(list)
    for r in typed:
        by_type[r["stype"]].append(r)

    print("=" * 78)
    print("PHASE 2 — cross-M self-calibration collapse per target type")
    print("  resid = cross-M collapse (want -> within-config floor ~0.38)")
    print("=" * 78)
    print(f"{'target':<16}{'nteeth':<8}{'configs':<9}{'orders':<14}"
          f"{'collapse':<10}{'perOrdNull':<12}{'withinFloor':<12}{'verdict'}")

    results = []
    for st in sorted(by_type):
        teeth = by_type[st]
        nconf = len(set(t["config"] for t in teeth))
        ords = sorted(set(t["order"] for t in teeth))
        if len(teeth) < 8 or len(ords) < 2:
            print(f"{st:<16}{len(teeth):<8}{nconf:<9}{str(ords):<14}"
                  f"{'--too few':<10}")
            continue
        cal = T.self_calibrate(teeth)
        null = per_order_null(teeth)
        floor, nfloor = within_config_floor(teeth)
        # verdict: stable if collapse approaches the floor AND beats the null
        margin_null = (null - cal["residual_rms"]) / null if null else 0
        approach = cal["residual_rms"] / floor if floor and floor == floor else float("inf")
        if approach < 1.3 and margin_null > 0.2:
            verdict = "STABLE*"
        elif margin_null > 0.15:
            verdict = "marginal"
        else:
            verdict = "UNSTABLE"
        print(f"{st:<16}{len(teeth):<8}{nconf:<9}{str(ords):<14}"
              f"{cal['residual_rms']:<10.3f}{null:<12.3f}{floor:<12.3f}{verdict}")
        results.append((st, len(teeth), nconf, ords, cal["residual_rms"], null, floor, verdict))

    # low-order-only variant for the data-rich magenta clusters (cleaner signal)
    print("\n--- low-order-only (orders<=3) for magenta clusters ---")
    for st in sorted(by_type):
        if not st.startswith("magenta"):
            continue
        teeth = [t for t in by_type[st] if t["order"] <= 3]
        if len(teeth) < 8 or len(set(t["order"] for t in teeth)) < 2:
            continue
        cal = T.self_calibrate(teeth)
        null = per_order_null(teeth)
        floor, _ = within_config_floor(teeth)
        print(f"  {st:<14} orders<=3: collapse={cal['residual_rms']:.3f} "
              f"null={null:.3f} floor={floor:.3f}")

    # ===== Q1: MAZE on its own (single-pitch cross-M MTF test) =====
    print("\n" + "=" * 78)
    print("Q1 — MAZE on its own (single-pitch; resid = pure cross-M stability, no T_n)")
    print("=" * 78)
    maze = by_type.get("maze", [])
    if maze:
        mz = maze_single_pitch_collapse(maze)
        print(f"  maze order-1 fundamentals: n={mz['n']} configs={mz['nconf']}")
        print(f"  M span {mz['Mspan'][0]:.2f}-{mz['Mspan'][1]:.2f}  "
              f"f_px span {mz['fpxspan'][0]:.3f}-{mz['fpxspan'][1]:.3f} cy/px")
        print(f"  single-MTF collapse residual = {mz['resid']:.3f}  "
              f"(within-config floor {mz['floor']:.3f})")
        ratio = mz['resid'] / mz['floor'] if mz['floor'] == mz['floor'] else float('nan')
        print(f"  ratio resid/floor = {ratio:.2f}  "
              f"(STABLE if ~<1.3, i.e. cross-M scatter ~= same-M noise)")
        # even-harmonic note
        o2 = [t for t in maze if t["order"] == 2]
        print(f"  maze order-2 teeth (even content): n={len(o2)} "
              f"(only resolvable at high M where 2f<Nyquist)")
        # also the resolved-range-only (M>=0.7) is all of them; report M>=1.0 subset too
        o1hi = [t for t in maze if t["order"] == 1 and t["M"] >= 1.0]
        if len(o1hi) >= 6:
            fpx = np.array([t["f_px"] for t in o1hi]); logA = np.array([t["logA"] for t in o1hi])
            w = np.array([t["w"] for t in o1hi])
            fit = T.isotonic_decreasing(fpx, logA, w)
            r = float(np.sqrt(np.sum(w * (logA - fit) ** 2) / np.sum(w)))
            print(f"  (M>=1.0 subset: collapse residual {r:.3f}, n={len(o1hi)})")
        results.append(("maze_singlepitch", mz['n'], mz['nconf'], [1],
                        mz['resid'], float('nan'), mz['floor'],
                        "STABLE*" if ratio < 1.3 else "UNSTABLE"))

    # write results CSV
    csvp = OUT / "phase2_collapse.csv"
    with csvp.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["target", "n_teeth", "n_configs", "orders",
                    "collapse_resid", "per_order_null", "within_config_floor", "verdict"])
        for r in results:
            w.writerow([r[0], r[1], r[2], "|".join(map(str, r[3])),
                        round(r[4], 4), (round(r[5], 4) if r[5] == r[5] else ""),
                        (round(r[6], 4) if r[6] == r[6] else ""), r[7]])
    print(f"\nWROTE {csvp}")


if __name__ == "__main__":
    main()
