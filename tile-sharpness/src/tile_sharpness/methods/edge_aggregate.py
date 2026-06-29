"""Direction-aware aggregation of flat-edge MTF50 reads over many parallel edges.

REPORT_taskAD §H/§J established that the flat 2B serpent gives MANY parallel
isolated reflectance edges, each of which can be measured (``slanted_edge`` step
estimators). The cross-config edge↔FFT study (2026-06-29) found the *aggregation*
of those per-edge reads is the soft spot: on Sigma150+TC the per-edge medians split
RISING (dark→bright) ~0.112 vs FALLING (bright→dark) ~0.186 cy/px — a 1.66× direction
asymmetry that inflates the naive median to 0.168 cy/px (38.7 lp/mm), well over the
periodic-FFT read of the SAME feature.

The serpent is MATTE (confirmed by the glint check — symmetric dips, no specular
rim), so the split is NOT a specular over-read. Under a matte feature a genuine
rising≠falling difference can only come from:

  (a) the feature's own asymmetric edge PROFILE (etch bevel — one mask wall steeper
      than the other; the captured edge is ``lens ⊗ feature-profile`` so the two
      scan directions differ for real and *consistently* across lines/configs),
  (b) a FOCUS / field-tilt gradient across the line band (the rising and falling
      edges of a line sit at slightly different best-focus rail positions, so a
      single fixed frame favours one direction — washes out if each edge is read at
      ITS OWN best-focus frame and averaged over many lines), or
  (c) an algorithmic detection / re-centring direction bias (would be constant in
      sign and present even on a synthetic symmetric edge).

This module provides the three reusable aggregation strategies the study compares,
plus a small diagnosis helper that classifies which mechanism dominates from the
per-edge table. None of these touch the per-edge estimator (``slanted_edge``) — they
operate on already-measured per-edge records, so they are cheap and unit-testable
with synthetic records.

A per-edge record is a mapping with at least:
  ``mtf50``      — cy/px (float) for this edge, or None if the estimator rejected it,
  ``kind``       — "rising" | "falling",
  ``over``       — measured/ceiling ratio (None if no MTF),
  ``flag``       — truthy if the edge was flagged unreliable (rim / bad fit / etc.),
optionally for diagnosis:
  ``t_along``    — along-axis position (px) of the edge (for field-gradient tests),
  ``settled``    — bool: ESF asymptotes flat on BOTH sides (clean step),
  ``focus_idx``  — which frame this edge was read at (per-edge best focus).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np


def _vals(records: Sequence[Mapping], kind: str | None = None,
          drop_flagged: bool = False, drop_over: float | None = None) -> list[float]:
    out = []
    for r in records:
        m = r.get("mtf50")
        if m is None:
            continue
        if kind is not None and r.get("kind") != kind:
            continue
        if drop_flagged and r.get("flag"):
            continue
        if drop_over is not None and r.get("over") is not None and r["over"] > drop_over:
            continue
        out.append(float(m))
    return out


# --------------------------------------------------------------------------- #
# Strategy 1 — conservative / clean aggregation.
# --------------------------------------------------------------------------- #

def aggregate_conservative(records: Sequence[Mapping], *,
                           over_ceiling: float = 1.0,
                           combine: str = "min_direction") -> dict | None:
    """Drop over-ceiling / flagged edges, then combine rising+falling conservatively.

    ``over_ceiling`` — edges whose ``over`` (measured/ceiling) exceeds this are
        dropped (physically impossible reads). A small tolerance (e.g. 1.05) absorbs
        ceiling/M uncertainty.
    ``combine`` — how to fuse the two directions after cleaning:
        * ``"min_direction"`` — take the LOWER of the two per-direction medians (the
          contaminated direction over-reads, so the lower median is the conservative
          estimate). This is the headline conservative read.
        * ``"pooled_median"`` — median over all surviving edges of both directions.
        * ``"min_edge"``      — the single lowest surviving per-edge MTF50.

    Returns a dict with ``mtf50`` (the aggregate), ``n``, ``rising_med``,
    ``falling_med``, ``rule``, or ``None`` if nothing survives.
    """
    clean = [r for r in records if r.get("mtf50") is not None
             and not r.get("flag")
             and (r.get("over") is None or r["over"] <= over_ceiling)]
    if not clean:
        return None
    ris = [float(r["mtf50"]) for r in clean if r.get("kind") == "rising"]
    fal = [float(r["mtf50"]) for r in clean if r.get("kind") == "falling"]
    all_m = [float(r["mtf50"]) for r in clean]
    rmed = float(np.median(ris)) if ris else None
    fmed = float(np.median(fal)) if fal else None
    if combine == "min_direction":
        cand = [x for x in (rmed, fmed) if x is not None]
        agg = min(cand) if cand else float(np.median(all_m))
    elif combine == "pooled_median":
        agg = float(np.median(all_m))
    elif combine == "min_edge":
        agg = float(min(all_m))
    else:
        raise ValueError(f"unknown combine={combine!r}")
    return dict(mtf50=agg, n=len(clean), rising_med=rmed, falling_med=fmed,
                rule=f"conservative/{combine}")


# --------------------------------------------------------------------------- #
# Strategy 2 — per-edge-focus, direction-independent, line-averaged.
# (Matte reinterpretation of the old "rim/overshoot model": no overshoot to
#  subtract; instead remove per-edge focus variation by reading each edge at its
#  own best-focus frame and averaging over many lines.)
# --------------------------------------------------------------------------- #

def aggregate_per_edge_focus(records: Sequence[Mapping], *,
                             over_ceiling: float = 1.0) -> dict | None:
    """Average over MANY edges, each already measured at ITS OWN best-focus frame,
    treating rising and falling edges as independent samples of the same feature.

    The caller is responsible for having populated each record's ``mtf50`` from that
    edge's per-edge best-focus frame (see the study driver's ``per_edge_focus``
    path). Here we simply pool the (cleaned) per-edge reads — the per-edge focus +
    many-line averaging is what washes out mechanism (b). We report the rising and
    falling sub-medians too, so the residual split AFTER per-edge focus is visible:
    if it shrinks toward 1.0, (b) dominated; if it persists, (a) or (c) does.

    Returns ``mtf50`` (mean over surviving edges — mean, not median, to use all the
    independent samples), ``median``, ``n``, ``rising_med``, ``falling_med``,
    ``split_ratio`` (max/min of the two direction medians).
    """
    clean = [r for r in records if r.get("mtf50") is not None
             and not r.get("flag")
             and (r.get("over") is None or r["over"] <= over_ceiling)]
    if not clean:
        return None
    ris = [float(r["mtf50"]) for r in clean if r.get("kind") == "rising"]
    fal = [float(r["mtf50"]) for r in clean if r.get("kind") == "falling"]
    all_m = [float(r["mtf50"]) for r in clean]
    rmed = float(np.median(ris)) if ris else None
    fmed = float(np.median(fal)) if fal else None
    split = (max(rmed, fmed) / min(rmed, fmed)) if (rmed and fmed) else None
    return dict(mtf50=float(np.mean(all_m)), median=float(np.median(all_m)),
                n=len(clean), rising_med=rmed, falling_med=fmed,
                split_ratio=split, rule="per_edge_focus/mean")


# --------------------------------------------------------------------------- #
# Strategy 3 — physically-consistent polarity / side selection.
# --------------------------------------------------------------------------- #

def aggregate_polarity_selected(records: Sequence[Mapping], *,
                                reference_cypx: float | None = None,
                                ceiling_cypx: float | None = None,
                                prefer_settled: bool = True) -> dict | None:
    """Pick the physically-consistent edge direction and report ITS median.

    Selection priority:
      1. if ``prefer_settled`` and the records carry a ``settled`` flag, restrict to
         the direction with the higher fraction of settled (flat-asymptote-both-sides)
         edges — under matte feature-profile asymmetry the cleaner direction is the
         one whose ESF settles flat on both sides;
      2. among the directions still in play, drop any whose median exceeds
         ``ceiling_cypx`` (impossible); then
      3. if ``reference_cypx`` (e.g. the FFT MTF at f_serpent, or the ceiling) is
         given, prefer the direction whose median is CLOSEST to it AND not above the
         ceiling — i.e. the one consistent with the independent physical anchor.
      Falls back to the lower-median direction if no anchor is supplied.

    Returns ``mtf50`` (the chosen direction's median), ``chosen`` ("rising"/"falling"),
    ``rising_med``, ``falling_med``, ``reason``.
    """
    clean = [r for r in records if r.get("mtf50") is not None and not r.get("flag")]
    if not clean:
        return None

    def med(kind):
        v = [float(r["mtf50"]) for r in clean if r.get("kind") == kind]
        return float(np.median(v)) if v else None

    def settled_frac(kind):
        v = [r for r in clean if r.get("kind") == kind and "settled" in r]
        return (sum(1 for r in v if r.get("settled")) / len(v)) if v else None

    rmed, fmed = med("rising"), med("falling")
    if rmed is None and fmed is None:
        return None
    if rmed is None:
        return dict(mtf50=fmed, chosen="falling", rising_med=None, falling_med=fmed,
                    reason="only-falling")
    if fmed is None:
        return dict(mtf50=rmed, chosen="rising", rising_med=rmed, falling_med=None,
                    reason="only-rising")

    in_play = {"rising": rmed, "falling": fmed}
    reason = []

    if prefer_settled:
        sr, sf = settled_frac("rising"), settled_frac("falling")
        if sr is not None and sf is not None and abs(sr - sf) > 0.15:
            keep = "rising" if sr > sf else "falling"
            in_play = {keep: in_play[keep]}
            reason.append(f"settled({keep})")

    if ceiling_cypx is not None:
        in_play = {k: v for k, v in in_play.items() if v <= ceiling_cypx * 1.05} or in_play
        if len(in_play) < 2:
            reason.append("ceiling-cut")

    if len(in_play) == 1:
        k = next(iter(in_play))
        return dict(mtf50=in_play[k], chosen=k, rising_med=rmed, falling_med=fmed,
                    reason="+".join(reason) or "single-direction")

    if reference_cypx is not None:
        # closest to the anchor that is also <= ceiling (if known)
        def score(kv):
            k, v = kv
            penalty = 0.0
            if ceiling_cypx is not None and v > ceiling_cypx * 1.05:
                penalty = 1e3
            return abs(v - reference_cypx) + penalty
        k = min(in_play.items(), key=score)[0]
        reason.append("closest-to-anchor")
        return dict(mtf50=in_play[k], chosen=k, rising_med=rmed, falling_med=fmed,
                    reason="+".join(reason))

    # no anchor: conservative lower direction
    k = min(in_play, key=in_play.get)
    reason.append("lower-direction")
    return dict(mtf50=in_play[k], chosen=k, rising_med=rmed, falling_med=fmed,
                reason="+".join(reason))


# --------------------------------------------------------------------------- #
# Diagnosis — which mechanism (a)/(b)/(c) drives the rising≠falling split?
# --------------------------------------------------------------------------- #

def diagnose_asymmetry(records: Sequence[Mapping]) -> dict:
    """Classify the dominant cause of the rising≠falling MTF50 split.

    Tests (each only run if the data supports it):
      * SIGN CONSISTENCY across lines — does rising>falling hold per-line, or flip?
        A consistent sign points to (a) feature-profile asymmetry or (c) algorithmic
        bias; a flipping sign across the field/lines points to (b) focus/field tilt.
      * FIELD GRADIENT — does the per-edge MTF50 (or the rising−falling gap) trend
        with along-axis position ``t_along``? A trend ⇒ (b).
      * FOCUS SENSITIVITY — if edges carry ``focus_idx``, does the rising/falling
        split shrink when each is read at its own best focus (the caller passes both
        a fixed-frame and a per-edge-focus record set via ``records`` twice — here we
        just expose the split so the driver can compare)。

    Returns a dict with ``rising_med``, ``falling_med``, ``split_ratio``,
    ``per_line_sign`` (fraction of lines where rising>falling), ``field_trend``
    (Spearman-like sign of MTF50 vs t_along, or None), and a ``verdict`` string.
    """
    ris = _vals(records, "rising")
    fal = _vals(records, "falling")
    rmed = float(np.median(ris)) if ris else None
    fmed = float(np.median(fal)) if fal else None
    split = (max(rmed, fmed) / min(rmed, fmed)) if (rmed and fmed) else None

    # per-line sign: group edges by an integer line id if present, else by nearest
    # rising/falling pairing along t_along.
    per_line_sign = None
    paired = [r for r in records if r.get("mtf50") is not None and r.get("t_along") is not None]
    if paired and ris and fal:
        rr = sorted([r for r in paired if r.get("kind") == "rising"], key=lambda r: r["t_along"])
        ff = sorted([r for r in paired if r.get("kind") == "falling"], key=lambda r: r["t_along"])
        signs = []
        for r in rr:
            # nearest falling edge by position
            if not ff:
                break
            nf = min(ff, key=lambda f: abs(f["t_along"] - r["t_along"]))
            signs.append(1 if float(r["mtf50"]) > float(nf["mtf50"]) else 0)
        if signs:
            per_line_sign = float(np.mean(signs))

    # field gradient: correlation of MTF50 with t_along over all edges
    field_trend = None
    allp = [(r["t_along"], float(r["mtf50"])) for r in records
            if r.get("mtf50") is not None and r.get("t_along") is not None]
    if len(allp) >= 6:
        t = np.array([p[0] for p in allp]); m = np.array([p[1] for p in allp])
        if np.std(t) > 0 and np.std(m) > 0:
            field_trend = float(np.corrcoef(t, m)[0, 1])

    verdict = "insufficient-data"
    if split is not None:
        if split < 1.15:
            verdict = "no-meaningful-split"
        elif per_line_sign is not None and (per_line_sign > 0.8 or per_line_sign < 0.2):
            verdict = "(a)-feature-profile-or-(c)-algorithmic: consistent sign across lines"
        elif field_trend is not None and abs(field_trend) > 0.4:
            verdict = "(b)-focus/field-gradient: MTF50 trends with field position"
        elif per_line_sign is not None and 0.3 < per_line_sign < 0.7:
            verdict = "(b)-focus/field: split sign flips across lines (per-edge focus should wash it out)"
        else:
            verdict = "split-present-cause-ambiguous"
    return dict(rising_med=rmed, falling_med=fmed, split_ratio=split,
                per_line_sign=per_line_sign, field_trend=field_trend, verdict=verdict)
