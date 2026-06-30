"""Cross-magnification RELATIVE glass-MTF estimator (fixed-sensor-frequency).

================================================================================
READ THIS BEFORE USING THE OUTPUT. THIS IS A DELIBERATELY FENCED TOOL.
================================================================================

What this measures
------------------
A **relative**, **fixed-SENSOR-frequency** glass-MTF ranking across configurations
that differ in magnification (M). It answers exactly one question:

    "Which lens has the higher MTF at a given PIXEL frequency (cy/px)?"

It is NOT an absolute MTF and NOT a subject-resolution ranking. It does NOT, and
must not, tell you "which config resolves more detail per mm on the subject" — that
question legitimately credits magnification and is answered by the within-M periodic
ranking + the diffraction ceiling + tolerance ratios (the §L references). Used for
the wrong question this estimator looks broken (it refuses to credit empty
magnification — by design).

Why it works (and why the fence)
--------------------------------
The estimate is the amplitude (sqrt-PSD) RATIO of the SAME PHYSICAL wafer patch
imaged by two configs, resampled to a common subject-space grid so the intrinsic
target spectrum S(f) cancels exactly. Read at a fixed SENSOR (pixel) frequency the
common body's sensor MTF is identical for both configs, so the ratio isolates the
glass MTF (including the bellows N_eff effect). Pairwise log-ratios are chained
transitively (weighted least squares, zero-mean gauge) into a global per-config
relative score. M~2 configs share only a thin overlap region with the low-M
configs, so their scores are reached via a (validated-robust) transitive bridge.

The validated trustworthy window is **f_px = 0.08-0.15 cy/px**. Outside it the
estimator breaks: the M~2 / diopter configs fall past their common-grid Nyquist
(coverage collapses), the de-confounding flips positive, and empty-magnification
configs start to float above bare lenses. The tool enforces this window.

Validation provenance
----------------------
Promoted from the Stage AltEst / AltEst-2 POC (scripts/poc_comb_chain_REPORT.md).
On the 38-config validation set the primary estimator (P1) cleared all four gates:
M de-confounded (corr(M,score) negative), no empty-magnification float through
f_px~0.15, the §L known orderings reproduced (modern macros lead, vintage 55/60
mid-pack, diopter/extension tail), and repeatable (split-half Spearman 0.98-1.00).
Three estimators on different physical principles agree (same-patch spectral ratio
P1, pad-edge averaged-ESF P3.1, through-focus defocus response P2) — that mutual
agreement is the evidence the signal is real, not a single-method artifact.

The PSD-ratio chain (P1) is the PRIMARY estimator. The pad-edge ESF, relative
deconvolution, and the through-focus defocus response (P2) are built-in CROSS-CHECKS
reported as a cross-estimator Spearman agreement + a consensus rank-average; they
raise confidence, they are not the axis. P2 is a PER-CONFIG score on a different
physical principle (the width of the focus-stack sharpness response, no spectrum at
all): its self-check is corr(N_eff) ~ 0 rather than the f_px window the spectral
estimators fence, and it folds into the consensus as a fourth rank input.

Module layout
-------------
This module holds the validated, target-agnostic ESTIMATOR CORE (edge building,
the transitive chain, the f_px-window enforcement, the de-confound self-check gate,
the graph-connectivity check, bootstrap sigma, and the cross-estimator consensus).
It operates on per-(patch, config) radial-PSD curves supplied as a tidy DataFrame
plus a per-config metadata table; it imports only numpy / pandas / scipy. The heavy
image extraction (register -> resample same patch to common grid -> radial PSD;
pad-edge ESF; relative deconvolution) lives in the committed driver
``scripts/cross_m_relative_mtf_run.py``, which reuses the production registration
and optics infra read-only.

Physics constant: f_subj(lp/mm) = f_px(cy/px) * 229.9 * M (Z7 4.35um pitch).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# fence constants — the validated trustworthy window and gate thresholds
# --------------------------------------------------------------------------- #

#: Validated trustworthy fixed-sensor-frequency window (cy/px). Outside this the
#: estimator is NOT trustworthy: above it M~2/diopter configs lose coverage, the
#: de-confounding flips positive and empty-magnification configs float (AltEst-2).
FPX_WINDOW = (0.08, 0.15)

#: Window centre — the recommended single operating point.
FPX_DEFAULT = 0.10

#: Resampling samples-per-grid-unit the common-grid patches were built with. PSD
#: curves are in cy per common-grid px; sensor cy/px maps via px_per_unit / SPU.
SAMPLES_PER_UNIT = 700.0

#: De-confound self-check: corr(M, score) must be <= this (a small positive slack
#: tolerates noise but rejects a genuinely M-credited / empty-magnification axis).
DECONFOUND_MAX_CORR = 0.10

#: A config flagged isolated/under-bridged if it shares fewer than this many
#: cells with the rest of the graph.
MIN_ANCHOR_CELLS = 3

#: P2 (through-focus) de-confound self-check: |corr(N_eff, P2-score)| must be <=
#: this. P2 is a defocus-based corroborator on a DIFFERENT physical principle (the
#: width of the focus-stack sharpness response), so its de-confounding axis is the
#: aperture / depth-of-field one (N_eff), not the spectral M axis the f_px estimators
#: fence. The validated AltEst-2 value is corr(N_eff)=-0.10 (corr(M)=-0.22).
P2_DECONFOUND_MAX_ABS_CORR = 0.30

#: P2 degenerate-fit guard: a Gaussian-of-defocus FWHM (in frames) above this is a
#: failed fit (no clean focus peak in the stack) and is dropped before aggregation.
#: One AltEst-2 config (S105+5T+6T) produced FWHM~200 and was excluded this way.
P2_MAX_VALID_FWHM = 60.0


#: Incomplete-coverage guard. A focus stack whose best-focus frame sits within this
#: fraction of either END of the sweep almost certainly did not bracket the true
#: sharpness peak (the peak is at or past a stack edge). Manual-tier sessions (start /
#: stop set by hand, fixed step COUNT) sometimes fail to span the peak for some
#: apertures / corners; such a config is unreliable for ALL estimators and is flagged.
COVERAGE_EDGE_FRAC = 0.06


def focus_peak_at_edge(seqs, vals, *, edge_frac=COVERAGE_EDGE_FRAC):
    """True if the through-focus peak sits at a STACK EDGE (coverage incomplete).

    ``seqs`` = frame indices scanned, ``vals`` = the per-frame sharpness response
    (e.g. Laplacian variance). The best-focus frame is ``argmax(vals)``; if it falls
    within ``edge_frac`` of the first or last scanned frame, the sweep likely did not
    bracket the true peak (it is at or past an edge) and the config is unreliable for
    every estimator, not just P2. Returns False when there are too few frames to
    judge (caller treats unknown as not-flagged). Pure / unit-tested."""
    seqs = np.asarray(seqs, float)
    vals = np.asarray(vals, float)
    if len(vals) < 5:
        return False
    order = np.argsort(seqs)
    seqs = seqs[order]
    vals = vals[order]
    lo, hi = seqs[0], seqs[-1]
    span = hi - lo
    if span <= 0:
        return False
    peak = seqs[int(np.argmax(vals))]
    margin = edge_frac * span
    return bool(peak <= lo + margin or peak >= hi - margin)


def coverage_ok(edge_flags):
    """Per-config coverage verdict from per-patch edge flags.

    ``edge_flags`` = iterable of bools (one per patch, from :func:`focus_peak_at_edge`).
    A config is judged coverage-incomplete when a MAJORITY of its patches peak at a
    stack edge (a few edge-field patches peaking late is normal field curvature; a
    majority means the whole sweep missed the peak). Empty -> True (unknown = keep).
    Returns True when coverage is acceptable."""
    flags = [bool(f) for f in edge_flags]
    if not flags:
        return True
    return sum(flags) <= len(flags) / 2.0


def p2_rail_available(rail_ok):
    """Whether the P2 through-focus corroborator is usable for a config.

    P2 measures the WIDTH of the focus-stack sharpness response in FRAMES; it is
    only comparable across configs when the focus-rail step is constant and
    registered (frame index then maps linearly to physical defocus). Sessions
    recorded with a non-constant / UNREGISTERED rail step (e.g. the 2025-10-17 Z7
    wafer session, which predates the rail-coverage script) carry a frame axis that
    is not a defocus axis, so their FWHM-in-frames is not comparable — P2 must be
    marked UNAVAILABLE for them and they degrade to the spectral / pad-edge / decon
    estimators only. ``rail_ok`` is the per-config flag (truthy / "true"/"1"/"yes",
    or empty -> defaults True for backward compatibility with subsets that omit the
    column). Returns a bool; the driver skips emitting psffoc rows when False."""
    if rail_ok is None:
        return True
    if isinstance(rail_ok, str):
        s = rail_ok.strip().lower()
        if s == "":
            return True
        return s in ("1", "true", "yes", "y", "t")
    return bool(rail_ok)


# --------------------------------------------------------------------------- #
# the validated estimator core (pure numeric — fully unit-tested)
# --------------------------------------------------------------------------- #

def chain_solve(edges, nodes):
    """Weighted-least-squares transitive chain with a zero-mean gauge.

    ``edges`` = list of ``(i, j, d_ij, w_ij)`` meaning ``s_i - s_j ~= d_ij`` with
    weight ``w_ij``; ``nodes`` = ordered config ids. Returns ``{node: score}``.
    The zero-mean constraint fixes the global gauge (scores are RELATIVE).
    """
    idx = {n: k for k, n in enumerate(nodes)}
    n = len(nodes)
    rows, rhs, ws = [], [], []
    for i, j, d, w in edges:
        r = np.zeros(n)
        r[idx[i]] = 1.0
        r[idx[j]] = -1.0
        rows.append(r)
        rhs.append(d)
        ws.append(w)
    # gauge row: mean(scores) == 0
    rows.append(np.ones(n))
    rhs.append(0.0)
    ws.append(float(len(edges) or 1.0))
    A = np.asarray(rows)
    b = np.asarray(rhs)
    W = np.sqrt(np.asarray(ws))
    sol, *_ = np.linalg.lstsq(A * W[:, None], b * W, rcond=None)
    return {nd: float(sol[k]) for nd, k in idx.items()}


def build_edges(psd, px_per_unit, f_px, *, mode="sensor", spu=SAMPLES_PER_UNIT):
    """Build same-physical-patch amplitude-log-ratio edges at a fixed frequency.

    For every atlas patch (cell) shared by >= 2 configs, interpolate each config's
    amplitude (sqrt-PSD) curve at the target frequency and add an edge
    ``log(amp_a / amp_b)``. In ``"sensor"`` mode the target is a fixed sensor cy/px
    mapped per-config to common-grid cy/px via ``px_per_unit / spu`` (this is the
    VALID glass-MTF axis). ``"subject"`` mode reads a fixed common-grid frequency
    for every config and is the M-CONFOUNDED control (kept only for the gate check).

    Parameters
    ----------
    psd : DataFrame with columns {sid, patch, f_grid, psd}.
    px_per_unit : mapping sid -> image px per atlas grid-unit (from meta).
    f_px : target frequency (sensor cy/px for "sensor"; common-grid cy/px for "subject").

    Returns ``(edges, pair_cells)`` where ``pair_cells[(a, b)]`` is the set of
    cells contributing to that pair (used for connectivity / bootstrap / jackknife).
    """
    edges = []
    pair_cells = {}
    for patch, g in psd.groupby("patch"):
        curves = {}
        for sid, gg in g.groupby("sid"):
            gg = gg.sort_values("f_grid")
            amp = np.sqrt(np.clip(gg.psd.to_numpy(float), 1e-30, None))
            curves[sid] = (gg.f_grid.to_numpy(float), amp)
        present = list(curves)
        for a in range(len(present)):
            for b in range(a + 1, len(present)):
                sa, sb = present[a], present[b]
                fa, va = curves[sa]
                fb, vb = curves[sb]
                if mode == "subject":
                    fga = fgb = f_px
                else:
                    if sa not in px_per_unit or sb not in px_per_unit:
                        continue
                    fga = f_px * px_per_unit[sa] / spu
                    fgb = f_px * px_per_unit[sb] / spu
                if not (fa.min() <= fga <= fa.max() and fb.min() <= fgb <= fb.max()):
                    continue
                ma = float(np.interp(fga, fa, va))
                mb = float(np.interp(fgb, fb, vb))
                if ma <= 0 or mb <= 0:
                    continue
                edges.append((sa, sb, float(np.log(ma / mb)), 1.0))
                pair_cells.setdefault((sa, sb), set()).add(patch)
    return edges, pair_cells


def connected_components(edges):
    """Union-find over the edge graph. Returns ``(n_components, {node: root})``."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j, *_ in edges:
        parent[find(i)] = find(j)
    roots = {n: find(n) for n in parent}
    return len({r for r in roots.values()}), roots


def solve_chain(edges):
    """Solve the chain and report graph diagnostics.

    Returns ``(scores, n_components, resid_rms)`` or ``(None, None, None)`` if the
    graph is too small. ``resid_rms`` is the RMS edge residual (chain consistency).
    """
    nodes = sorted({e[0] for e in edges} | {e[1] for e in edges})
    if len(nodes) < 2:
        return None, None, None
    scores = chain_solve(edges, nodes)
    ncomp, _ = connected_components(edges)
    resid = float(np.sqrt(np.mean(
        [(scores[i] - scores[j] - d) ** 2 for i, j, d, _ in edges])))
    return scores, ncomp, resid


def deconfound_corr(scores, m_by_sid):
    """corr(M, score) — the de-confounding self-check statistic.

    A valid fixed-sensor-frequency glass axis is M de-confounded, so this should be
    <= 0 (or only marginally positive). A clearly positive value means the axis is
    crediting empty magnification — refuse / flag (see :func:`gate_self_check`).
    """
    sids = [s for s in scores if s in m_by_sid and np.isfinite(m_by_sid[s])]
    if len(sids) < 3:
        return float("nan")
    M = np.array([m_by_sid[s] for s in sids])
    S = np.array([scores[s] for s in sids])
    if np.std(M) == 0 or np.std(S) == 0:
        return float("nan")
    return float(np.corrcoef(M, S)[0, 1])


def empty_magnification_floats(scores):
    """Accessory (``+``) configs whose score exceeds the best bare-lens score.

    Any such config is an 'empty-magnification float' — a teleconverter / extension
    tube / diopter ranking ABOVE the sharpest bare lens, which the relative
    glass-MTF axis must never do. Returns the offending sids (empty list = clean).
    """
    bare = {s: v for s, v in scores.items() if "+" not in s}
    acc = {s: v for s, v in scores.items() if "+" in s}
    if not bare or not acc:
        return []
    top_bare = max(bare.values())
    return sorted([s for s, v in acc.items() if v > top_bare])


@dataclass
class GateResult:
    """Outcome of the self-check gates run on an input config set."""

    f_px: float
    n_nodes: int
    n_edges: int
    n_components: int
    resid_rms: float
    corr_M: float
    empty_mag_floats: list
    isolated_configs: list
    in_window: bool

    @property
    def deconfound_ok(self):
        return np.isfinite(self.corr_M) and self.corr_M <= DECONFOUND_MAX_CORR

    @property
    def connectivity_ok(self):
        return self.n_components == 1 and not self.isolated_configs

    @property
    def empty_mag_ok(self):
        return not self.empty_mag_floats

    @property
    def passed(self):
        return (self.in_window and self.deconfound_ok
                and self.connectivity_ok and self.empty_mag_ok)

    def messages(self):
        msgs = []
        if not self.in_window:
            msgs.append(
                f"f_px={self.f_px:.3f} is OUTSIDE the trustworthy window "
                f"{FPX_WINDOW[0]}-{FPX_WINDOW[1]} cy/px — ranking NOT trustworthy.")
        if not self.deconfound_ok:
            msgs.append(
                f"DE-CONFOUND FAIL: corr(M, score)={self.corr_M:+.3f} > "
                f"{DECONFOUND_MAX_CORR} — the axis is crediting magnification "
                f"(empty-magnification confound); refuse/flag this input set.")
        if not self.empty_mag_ok:
            msgs.append(
                "EMPTY-MAGNIFICATION FLOAT: accessory config(s) rank above the "
                f"best bare lens: {', '.join(self.empty_mag_floats)}.")
        if self.n_components != 1:
            msgs.append(
                f"GRAPH DISCONNECTED: {self.n_components} components — configs in "
                "different components are not comparable.")
        if self.isolated_configs:
            msgs.append(
                "UNDER-BRIDGED config(s) (< "
                f"{MIN_ANCHOR_CELLS} shared cells): "
                f"{', '.join(self.isolated_configs)} — scores rest on thin overlap.")
        return msgs


def enforce_fpx_window(f_px, *, strict=False):
    """Check ``f_px`` against the validated window; warn (or raise if ``strict``).

    Returns True if inside the window. A False return means the ranking must not be
    trusted as a glass-MTF axis.
    """
    lo, hi = FPX_WINDOW
    inside = lo <= f_px <= hi
    if not inside:
        msg = (f"f_px={f_px:.3f} cy/px is outside the validated trustworthy window "
               f"{lo}-{hi}; the cross-M relative MTF ranking is NOT trustworthy here "
               "(coverage loss + M-confound flips positive above the window).")
        if strict:
            raise ValueError(msg)
        warnings.warn(msg, stacklevel=2)
    return inside


def gate_self_check(psd, meta, f_px, *, strict=False):
    """Run the full self-check gate battery for one ``f_px`` and return a GateResult.

    Computes the chain, then evaluates: f_px-window membership, the de-confound
    self-check corr(M, score) <= 0, the empty-magnification float check, graph
    connectivity (one component), and per-config bridge thinness. With ``strict``,
    an out-of-window f_px or a failed de-confound check raises instead of warning.
    """
    px_per_unit = dict(zip(meta.sid, meta.px_per_unit))
    m_by_sid = dict(zip(meta.sid, meta.M))
    in_window = enforce_fpx_window(f_px, strict=strict)
    edges, pair_cells = build_edges(psd, px_per_unit, f_px, mode="sensor")
    scores, ncomp, resid = solve_chain(edges)
    if scores is None:
        raise ValueError(f"f_px={f_px}: too few connected configs to rank.")
    corr = deconfound_corr(scores, m_by_sid)
    floats = empty_magnification_floats(scores)
    # per-config shared-cell counts (bridge thinness)
    cells_by_sid = {s: 0 for s in scores}
    for (a, b), cells in pair_cells.items():
        cells_by_sid[a] = cells_by_sid.get(a, 0) + len(cells)
        cells_by_sid[b] = cells_by_sid.get(b, 0) + len(cells)
    isolated = sorted([s for s, c in cells_by_sid.items() if c < MIN_ANCHOR_CELLS])
    res = GateResult(f_px=f_px, n_nodes=len(scores), n_edges=len(edges),
                     n_components=ncomp, resid_rms=resid, corr_M=corr,
                     empty_mag_floats=floats, isolated_configs=isolated,
                     in_window=in_window)
    if strict and not res.deconfound_ok:
        raise ValueError(res.messages()[0] if res.messages() else "de-confound fail")
    return res, scores, pair_cells


def bootstrap_sigma(psd, meta, f_px, *, n_boot=120, seed=0):
    """Per-config bootstrap sigma by resampling patches (cells) with replacement.

    Returns ``{sid: sigma}``. Captures the uncertainty from the finite set of shared
    cells each config rests on (well-covered configs ~0.01-0.03; thinly-bridged M~2
    and extension stacks larger).
    """
    px_per_unit = dict(zip(meta.sid, meta.px_per_unit))
    pats = sorted(psd.patch.unique())
    rng = np.random.default_rng(seed)
    boots = {}
    for _ in range(n_boot):
        bp = set(rng.choice(pats, size=len(pats), replace=True))
        edges, _ = build_edges(psd[psd.patch.isin(bp)], px_per_unit, f_px, mode="sensor")
        bs, _, _ = solve_chain(edges)
        if bs:
            for s, v in bs.items():
                boots.setdefault(s, []).append(v)
    return {s: float(np.std(v)) if v else float("nan") for s, v in boots.items()}


def split_half_spearman(psd, meta, f_px):
    """Repeatability: Spearman between scores from two disjoint halves of the cells."""
    from scipy.stats import spearmanr
    px_per_unit = dict(zip(meta.sid, meta.px_per_unit))
    pats = sorted(psd.patch.unique())
    h1, h2 = set(pats[::2]), set(pats[1::2])
    e1, _ = build_edges(psd[psd.patch.isin(h1)], px_per_unit, f_px, mode="sensor")
    e2, _ = build_edges(psd[psd.patch.isin(h2)], px_per_unit, f_px, mode="sensor")
    s1, _, _ = solve_chain(e1)
    s2, _, _ = solve_chain(e2)
    if not s1 or not s2:
        return float("nan"), 0
    common = sorted(set(s1) & set(s2))
    if len(common) < 3:
        return float("nan"), len(common)
    rho, _ = spearmanr([s1[k] for k in common], [s2[k] for k in common])
    return float(rho), len(common)


def jackknife_bridge(psd, meta, f_px, targets, pair_cells):
    """Bridge robustness for high-M ``targets``: drop each anchor, re-solve, measure
    the target's score shift. Returns ``{target: worst_abs_shift}``."""
    px_per_unit = dict(zip(meta.sid, meta.px_per_unit))
    edges, _ = build_edges(psd, px_per_unit, f_px, mode="sensor")
    base_scores, _, _ = solve_chain(edges)
    all_sids = set(base_scores)
    out = {}
    for target in targets:
        if target not in base_scores:
            continue
        anchors = {(b if a == target else a) for (a, b) in pair_cells if target in (a, b)}
        worst = 0.0
        for drop in anchors:
            sub = psd[psd.sid.isin(all_sids - {drop})]
            e2, _ = build_edges(sub, px_per_unit, f_px, mode="sensor")
            s2, _, _ = solve_chain(e2)
            if s2 and target in s2:
                worst = max(worst, abs(s2[target] - base_scores[target]))
        out[target] = worst
    return out


@dataclass
class Ranking:
    """A cross-M relative-MTF ranking at one f_px, with uncertainty + gates."""

    f_px: float
    table: pd.DataFrame  # columns: sid, score, M, sigma, n_cells (sorted sharp->soft)
    gate: GateResult


def rank_configs(psd, meta, f_px=FPX_DEFAULT, *, n_boot=120, strict=False):
    """Produce the primary cross-M relative-MTF ranking at ``f_px``.

    Higher score = sharper (higher relative glass MTF at this pixel frequency).
    Runs the gate battery, computes bootstrap sigma, and returns a :class:`Ranking`.
    """
    gate, scores, pair_cells = gate_self_check(psd, meta, f_px, strict=strict)
    sigma = bootstrap_sigma(psd, meta, f_px, n_boot=n_boot)
    cells_by_sid = {}
    for (a, b), cells in pair_cells.items():
        cells_by_sid[a] = cells_by_sid.get(a, 0) + len(cells)
        cells_by_sid[b] = cells_by_sid.get(b, 0) + len(cells)
    m_by_sid = dict(zip(meta.sid, meta.M))
    rows = [dict(sid=s, score=v, M=m_by_sid.get(s),
                 sigma=sigma.get(s, float("nan")),
                 n_cells=cells_by_sid.get(s, 0))
            for s, v in scores.items()]
    table = (pd.DataFrame(rows).sort_values("score", ascending=False)
             .reset_index(drop=True))
    return Ranking(f_px=f_px, table=table, gate=gate)


# --------------------------------------------------------------------------- #
# P2 — through-focus defocus-response estimator (the 4th corroborator)
# --------------------------------------------------------------------------- #
#
# A PER-CONFIG (not pairwise) score on a DIFFERENT physical principle from the
# spectral f_px estimators: it uses no spectrum at all, only the SHAPE of the
# focus-stack sharpness response. As the focus rail steps through best focus, a
# patch's Laplacian-variance (lapvar) traces a peak vs frame; a SHARPER optic
# produces a NARROWER, more sharply-peaked response. Fitting a Gaussian-of-defocus
# to the lapvar(z) peak yields a continuous, sub-frame FWHM (in frames) per patch;
# the per-config score is -median(FWHM) so HIGHER == sharper, aligned with P1.
#
# Validated in AltEst-2 (poc_comb_chain_REPORT.md §"Stage AltEst-2"): genuinely
# de-confounded (corr with N_eff -0.10, corr with M -0.22), the coarse-FWHM macro
# ties are BROKEN by the sub-frame fit, §L order holds (modern < vintage < diopter),
# and it AGREES with P1 at Spearman +0.40 (f_px=0.10) -> +0.58 (f_px=0.15). It is a
# corroborator folded into the consensus; it is NOT a fixed-sensor-frequency axis and
# does not share P1's f_px window — its self-check is corr(N_eff) instead.


def gaussian_defocus_fwhm(seqs, vals):
    """Fit a Gaussian-of-defocus to the lapvar(z) peak; return sub-frame FWHM (frames).

    ``seqs`` = frame indices, ``vals`` = the through-focus sharpness response (e.g.
    Laplacian variance) at those frames. A baseline (10th percentile) is subtracted,
    the peak region (>= 25% of peak height) is selected, and ``log(y)`` is fit to a
    weighted quadratic in ``z`` — i.e. a Gaussian ``exp(-(z-mu)^2 / 2 sigma^2)``. The
    FWHM is ``2.3548 * sigma`` and is continuous (NOT quantised to integer frames),
    which is what breaks the coarse-FWHM macro ties. Returns ``(sigma_z, fwhm, mu)``
    in frames, or ``(nan, nan, peak_frame_or_nan)`` if there is no clean peak.
    """
    seqs = np.asarray(seqs, float)
    vals = np.asarray(vals, float)
    if len(vals) < 7:
        return float("nan"), float("nan"), float("nan")
    base = np.percentile(vals, 10)
    v0 = np.clip(vals - base, 0, None)
    pk = int(np.argmax(v0))
    peak = v0[pk]
    if peak <= 0:
        return float("nan"), float("nan"), float("nan")
    sel = v0 >= 0.25 * peak
    z = seqs[sel]
    y = v0[sel]
    if len(z) < 5 or np.ptp(z) < 2:
        return float("nan"), float("nan"), float(seqs[pk])
    w = y / y.max()
    A = np.column_stack([np.ones_like(z), z, z * z])
    coef, *_ = np.linalg.lstsq(A * w[:, None], np.log(np.clip(y, 1e-9, None)) * w,
                               rcond=None)
    _, c1, c2 = coef  # log(y) ~ c0 + c1 z + c2 z^2; c0 (peak height) unused
    if c2 >= 0:  # upward parabola -> no peak
        return float("nan"), float("nan"), float(seqs[pk])
    sigma_z = float(np.sqrt(-1.0 / (2 * c2)))
    mu = float(-c1 / (2 * c2))
    fwhm = 2.3548 * sigma_z
    return sigma_z, fwhm, mu


def through_focus_scores(tf, *, max_valid_fwhm=P2_MAX_VALID_FWHM):
    """Per-config P2 score from per-(config, patch) through-focus FWHMs.

    ``tf`` = DataFrame with columns ``{sid, fwhm}`` (one row per (config, patch);
    ``fwhm`` from :func:`gaussian_defocus_fwhm`). Per config the median FWHM across
    its patches is the focus-response width; the score is its negation so HIGHER ==
    sharper (aligned with P1). FWHMs above ``max_valid_fwhm`` frames are degenerate
    fits and dropped before the median; a config with no valid FWHM is omitted.
    Returns ``{sid: score}``.
    """
    out = {}
    good = tf[np.isfinite(tf["fwhm"]) & (tf["fwhm"] <= max_valid_fwhm)]
    for sid, g in good.groupby("sid"):
        vals = g["fwhm"].to_numpy(float)
        if len(vals) == 0:
            continue
        out[str(sid)] = -float(np.median(vals))
    return out


def p2_deconfound_corr(scores, n_eff_by_sid):
    """corr(N_eff, P2-score) — the P2 de-confounding self-check statistic.

    P2 is a defocus-based corroborator, so its confound axis is the depth-of-field /
    aperture one (effective f-number), not the spectral M axis. A valid P2 score is
    de-confounded from N_eff, so this should be near zero (AltEst-2: -0.10); a clearly
    positive or large value means the focus-width score is just tracking DOF.
    """
    sids = [s for s in scores if s in n_eff_by_sid
            and np.isfinite(n_eff_by_sid[s])]
    if len(sids) < 3:
        return float("nan")
    N = np.array([n_eff_by_sid[s] for s in sids])
    S = np.array([scores[s] for s in sids])
    if np.std(N) == 0 or np.std(S) == 0:
        return float("nan")
    return float(np.corrcoef(N, S)[0, 1])


def p2_deconfound_ok(corr_n_eff):
    """True if the P2 N_eff de-confound self-check passes (|corr| <= threshold)."""
    return bool(np.isfinite(corr_n_eff)
                and abs(corr_n_eff) <= P2_DECONFOUND_MAX_ABS_CORR)


# --------------------------------------------------------------------------- #
# cross-estimator consensus (confidence signal — the "3 estimators agree" value)
# --------------------------------------------------------------------------- #

def cross_estimator_agreement(series):
    """Spearman cross-agreement matrix over a dict ``{name: {sid: aligned_score}}``.

    All series must be aligned so HIGHER == sharper. Returns a DataFrame matrix
    (rho where the pair shares >= 6 configs, else NaN).
    """
    from scipy.stats import spearmanr
    names = list(series)
    M = pd.DataFrame(index=names, columns=names, dtype=float)
    for a in names:
        for b in names:
            common = sorted(set(series[a]) & set(series[b]))
            if len(common) >= 6:
                rho, _ = spearmanr([series[a][k] for k in common],
                                   [series[b][k] for k in common])
                M.loc[a, b] = round(float(rho), 3)
    return M


def consensus_ranking(series, members):
    """Rank-average consensus over the gate-passing estimator ``members``.

    ``series`` = ``{name: {sid: aligned_score}}`` (higher == sharper). Returns a
    DataFrame with consensus_rank, mean_rank, rank_std (per-config disagreement =
    honest uncertainty), n_estimators, and each member's per-config rank.
    """
    members = [m for m in members if m in series]
    all_sids = sorted({k for m in members for k in series[m]})
    rank_tbl = {}
    for m in members:
        order = sorted(series[m], key=lambda k: -series[m][k])
        rank_tbl[m] = {k: i + 1 for i, k in enumerate(order)}
    rows = []
    for sid in all_sids:
        rks = [rank_tbl[m][sid] for m in members if sid in rank_tbl[m]]
        if not rks:
            continue
        rows.append(dict(sid=sid, mean_rank=float(np.mean(rks)),
                         rank_std=float(np.std(rks)), n_estimators=len(rks),
                         **{m: rank_tbl[m].get(sid) for m in members}))
    cons = pd.DataFrame(rows).sort_values("mean_rank").reset_index(drop=True)
    cons.insert(0, "consensus_rank", range(1, len(cons) + 1))
    return cons


# --------------------------------------------------------------------------- #
# the caveats header — baked into every emitted output
# --------------------------------------------------------------------------- #

def caveats_header(f_px=FPX_DEFAULT, *, comment="# "):
    """The mandatory caveats block, prefixed with ``comment`` for CSV/markdown."""
    lo, hi = FPX_WINDOW
    lines = [
        "CROSS-MAGNIFICATION RELATIVE GLASS-MTF RANKING",
        "RELATIVE, FIXED-SENSOR-FREQUENCY ranking: 'which lens has the higher MTF",
        "at this PIXEL frequency'. It is NOT an absolute MTF and NOT a",
        "subject-resolution ranking. It deliberately refuses to credit empty",
        "magnification; for 'resolves more subject detail' use within-M periodic",
        "ranking + diffraction ceiling + tolerance ratios (the SHARPNESS_METRICS / §L",
        "references), NOT this.",
        f"Trustworthy ONLY at f_px = {lo}-{hi} cy/px (read here at {f_px:g}). M~2 configs",
        "are reached via a transitive bridge (validated robust). Scores are relative",
        "(zero-mean gauge), not tied to the diffraction ceiling.",
        "Higher score / lower rank = sharper. See cross_m_relative_mtf.py docstring.",
    ]
    return "\n".join(comment + ln for ln in lines)
