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

# --------------------------------------------------------------------------- #
# focus-COVERAGE awareness (POC 1)
# --------------------------------------------------------------------------- #
#
# A focus stack is a sequence of shots at increasing rail positions; the per-patch
# Laplacian-variance vs frame index traces a defocus peak. If the FITTED peak
# centre (``mu``, from :func:`gaussian_defocus_fwhm`) sits at or beyond the FIRST
# or LAST captured frame, the true best-focus position is OUTSIDE the captured
# range — both the "best focus" position AND the FWHM are unreliable (the curve is
# truncated). This bites the MANUAL-tier sweeps (start/stop set by hand) and, for a
# given config, the OFF-AXIS / corner patches first: field curvature shifts their
# best focus along the rail, so a sweep that brackets the centre can clip the
# corners. The 2026-01-29 handover specifically warns that an apparent top-vs-bottom
# "decentering" in that cohort is LIKELY this under-coverage artifact (corner
# patches truncated at the stack edge), not real decentering — these helpers let us
# quantify it.

#: Minimum frames a peak (and at least its HWHM) must sit inside a stack edge before
#: we call coverage ``ok``. A 1-frame floor: a peak landing exactly on frame 0 or the
#: last frame is unambiguously truncated, but we also require the half-max width to
#: fit (see :func:`coverage_flag`), which is the binding constraint in practice.
COVERAGE_EDGE_MARGIN_FRAMES = 1.0

#: coverage_flag values, in priority order (a peak truncated at an edge is reported
#: as that, not as fwhm_truncated, even if its HWHM is also clipped).
COVERAGE_FLAGS = ("ok", "truncated_low", "truncated_high", "fwhm_truncated")


def coverage_flag(mu, fwhm, nstack, *, margin=COVERAGE_EDGE_MARGIN_FRAMES):
    """Classify focus-coverage of a single fitted through-focus peak.

    Given the FITTED peak centre ``mu`` (frames, from :func:`gaussian_defocus_fwhm`),
    the fitted ``fwhm`` (frames), and ``nstack`` = number of frames in the stack
    (valid frame indices span ``[0, nstack-1]``), return one of
    :data:`COVERAGE_FLAGS`:

    * ``truncated_low``  — ``mu <= margin``: the peak is at/below the first frames,
      so the true best focus is at or before the start of the captured range.
    * ``truncated_high`` — ``mu >= (nstack-1) - margin``: peak at/beyond the last
      frames; true best focus is at or past the end of the range.
    * ``fwhm_truncated`` — the peak CENTRE is inside, but ``mu +/- HWHM`` (HWHM =
      ``fwhm/2``) extends outside ``[0, nstack-1]``: the curve's half-max width is
      clipped by the stack edge, so the measured FWHM is under-estimated.
    * ``ok``             — peak centre comfortably inside (> ``margin`` from each
      edge) AND the full half-max width fits inside ``[0, nstack-1]``.

    DESIGN RULE (stated explicitly): a patch is ``ok`` only if the peak plus at
    least its HWHM is inside the stack, with a small ``margin``-frame floor on the
    centre. The HWHM-inside requirement is what makes a fit's FWHM trustworthy:
    if the half-max points fall off the captured range the Gaussian width was
    measured on a clipped curve. Edge truncation of the CENTRE takes priority over
    HWHM clipping (a centre at frame 0 is reported ``truncated_low``, not
    ``fwhm_truncated``). A non-finite ``mu`` or ``nstack < 2`` yields ``"ok"``
    treated as unknown — callers should additionally require a finite ``fwhm``
    before trusting the patch.

    Pure / unit-tested.
    """
    if not np.isfinite(mu) or nstack is None or nstack < 2:
        return "ok"
    last = float(nstack) - 1.0
    if mu <= margin:
        return "truncated_low"
    if mu >= last - margin:
        return "truncated_high"
    if np.isfinite(fwhm):
        hwhm = 0.5 * float(fwhm)
        if (mu - hwhm) < 0.0 or (mu + hwhm) > last:
            return "fwhm_truncated"
    return "ok"


def peak_pos_frac(mu, nstack):
    """Fractional peak position: ``mu / (nstack - 1)`` (0 = first frame, 1 = last)."""
    if not np.isfinite(mu) or nstack is None or nstack < 2:
        return float("nan")
    return float(mu) / (float(nstack) - 1.0)


def edge_dist_frames(mu, nstack):
    """Distance (frames) from ``mu`` to the nearest stack edge: ``min(mu, last-mu)``."""
    if not np.isfinite(mu) or nstack is None or nstack < 2:
        return float("nan")
    last = float(nstack) - 1.0
    return float(min(mu, last - mu))

# --------------------------------------------------------------------------- #
# LOCATION-AWARE (field-position) constants
# --------------------------------------------------------------------------- #
#
# Every per-patch read already has a frame pixel location (the production
# registration maps the patch's atlas-grid centre to image x,y). We tag each
# per-patch measurement with its DISTANCE and ANGLE from the FRAME CENTRE and bin
# it into field zones to resolve sharpness across the frame (radial falloff,
# azimuthal decentering, astigmatism, field-resolved relative ranking).
#
# CAVEAT — field coverage is intrinsically M-dependent and incomplete; sparse
# coverage is NOT a failure. At high M (~2) the wafer is hugely magnified so the
# registered patches cluster with little positional spread (limited field-height
# range + azimuth); at low M the wafer occupies only PART of the frame so the true
# frame CORNERS may simply not be sampled. Location-aware results are only
# meaningful where patches actually exist; we emit a per-config COVERAGE descriptor
# and flag sparse/unsupported maps rather than extrapolating into empty regions.

#: Z7 sensor pixel pitch (mm). Subject distance(mm) = dist_px * pitch / M.
SENSOR_PITCH_MM = 4.35e-3

#: Field-zone edges in FRACTION OF THE FRAME HALF-DIAGONAL (0 = centre, 1 = frame
#: corner). centre = [0, 0.33), mid = [0.33, 0.66), corner = [0.66, inf).
FIELD_ZONE_EDGES = (0.33, 0.66)
FIELD_ZONES = ("centre", "mid", "corner")

#: A field zone is reported "populated" for a config only if at least this many
#: patches fall in it; below this the zone aggregate is flagged sparse.
MIN_PATCHES_PER_ZONE = 2

#: A per-config field map is flagged degenerate (not a true field profile, just a
#: tight cluster) when the sampled field-height SPAN is below this fraction of the
#: half-diagonal — the high-M clustering case the caller warned about.
MIN_FIELD_HEIGHT_SPAN = 0.10


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


def through_focus_scores(tf, *, max_valid_fwhm=P2_MAX_VALID_FWHM,
                          require_coverage_ok=True):
    """Per-config P2 score from per-(config, patch) through-focus FWHMs.

    ``tf`` = DataFrame with columns ``{sid, fwhm}`` (one row per (config, patch);
    ``fwhm`` from :func:`gaussian_defocus_fwhm`). Per config the median FWHM across
    its patches is the focus-response width; the score is its negation so HIGHER ==
    sharper (aligned with P1). FWHMs above ``max_valid_fwhm`` frames are degenerate
    fits and dropped before the median; a config with no valid FWHM is omitted.
    Returns ``{sid: score}``.

    POC-1 focus-coverage: when ``require_coverage_ok`` is True AND ``tf`` carries a
    ``coverage_flag`` column, patches whose flag != ``"ok"`` are EXCLUDED from the
    per-config median (their FWHM was measured on a stack-clipped curve and is
    under-measured). If, after the coverage filter, a config has no ``ok`` patch
    left, it falls back to its valid (finite, <= max_valid_fwhm) FWHMs so the config
    is not silently dropped — but see :func:`through_focus_coverage_summary` for the
    per-config truncated fraction that flags such configs. DataFrames lacking a
    ``coverage_flag`` column behave exactly as before (backward compatible).
    """
    out = {}
    valid = np.isfinite(tf["fwhm"]) & (tf["fwhm"] <= max_valid_fwhm)
    good = tf[valid]
    use_cov = require_coverage_ok and ("coverage_flag" in tf.columns)
    for sid, g in good.groupby("sid"):
        if use_cov:
            g_ok = g[g["coverage_flag"] == "ok"]
            if len(g_ok) > 0:
                g = g_ok
        vals = g["fwhm"].to_numpy(float)
        if len(vals) == 0:
            continue
        out[str(sid)] = -float(np.median(vals))
    return out


def through_focus_coverage_summary(tf):
    """Per-config focus-coverage summary from a per-patch ``coverage_flag`` column.

    ``tf`` = DataFrame with at least ``{sid, coverage_flag}`` (one row per patch).
    Returns a DataFrame, one row per config, with the patch count per
    :data:`COVERAGE_FLAGS` class, ``n_total``, and ``frac_truncated`` (fraction of
    patches whose flag != ``"ok"``). Empty / no-column input returns an empty frame.
    """
    if "coverage_flag" not in tf.columns or len(tf) == 0:
        return pd.DataFrame(
            columns=["sid", "n_total", *COVERAGE_FLAGS, "frac_truncated"])
    rows = []
    for sid, g in tf.groupby("sid"):
        counts = {f: int((g["coverage_flag"] == f).sum()) for f in COVERAGE_FLAGS}
        n_total = int(len(g))
        n_ok = counts["ok"]
        rows.append(dict(sid=str(sid), n_total=n_total, **counts,
                         frac_truncated=(n_total - n_ok) / n_total
                         if n_total else float("nan")))
    return (pd.DataFrame(rows)
            .sort_values("frac_truncated", ascending=False)
            .reset_index(drop=True))


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
# LOCATION-AWARE field analysis (pure numeric — fully unit-tested)
# --------------------------------------------------------------------------- #
#
# A per-patch read at frame pixel (px, py) is tagged with its position RELATIVE TO
# THE FRAME CENTRE: distance (field height) + azimuth angle. The per-patch sharpness
# the field analysis consumes is the SAME per-patch amplitude (sqrt-PSD) read at the
# fixed sensor frequency that the cross-M relative chain uses — so the field maps and
# the global ranking are the same physical quantity, just resolved by position.


def field_geometry(px, py, cx, cy, image_w, image_h, *, m=None,
                   pitch_mm=SENSOR_PITCH_MM):
    """Position of a patch centre relative to the FRAME CENTRE.

    ``(px, py)`` patch centre in image pixels; ``(cx, cy)`` frame centre (the
    registration/optical centre, ~image centre); ``image_w/h`` frame size in px.
    Returns a dict with:

    * ``dist_px`` — radial distance from centre (image px),
    * ``field_height`` — ``dist_px`` normalised by the frame HALF-DIAGONAL, so 0.0
      is dead centre and 1.0 is the extreme frame corner (the sensible field-height
      normalisation: aspect-independent and 1.0 at the corner),
    * ``angle_deg`` — azimuth in degrees, math convention with image-y FLIPPED so
      +x (right) = 0deg, up = +90deg, left = 180deg, down = -90deg,
    * ``dist_subject_mm`` — ``dist_px`` mapped to SUBJECT mm via ``pitch/M`` (only if
      ``m`` is given and > 0; else NaN). Subject mm shrinks with M for a fixed pixel
      offset, which is why field height (the pixel/frame fraction) is the primary axis.
    """
    dx = float(px) - float(cx)
    dy = float(py) - float(cy)
    dist_px = float(np.hypot(dx, dy))
    half_diag = 0.5 * float(np.hypot(image_w, image_h))
    field_height = dist_px / half_diag if half_diag > 0 else float("nan")
    # image y grows downward; flip so "up" is +90deg (standard math azimuth).
    angle_deg = float(np.degrees(np.arctan2(-dy, dx)))
    if m is not None and np.isfinite(m) and m > 0:
        dist_subject_mm = dist_px * pitch_mm / m
    else:
        dist_subject_mm = float("nan")
    return dict(dist_px=dist_px, field_height=field_height, angle_deg=angle_deg,
                dist_subject_mm=dist_subject_mm)


def field_zone(field_height, *, edges=FIELD_ZONE_EDGES):
    """Bin a field height (fraction of half-diagonal) into centre/mid/corner."""
    if not np.isfinite(field_height):
        return None
    lo, hi = edges
    if field_height < lo:
        return "centre"
    if field_height < hi:
        return "mid"
    return "corner"


def assign_field_zones(field, *, edges=FIELD_ZONE_EDGES):
    """Add a ``zone`` column to a per-patch field DataFrame (``field_height`` col)."""
    field = field.copy()
    field["zone"] = field["field_height"].map(lambda h: field_zone(h, edges=edges))
    return field


def field_coverage(field):
    """Per-config field-COVERAGE descriptor — where patches actually exist.

    ``field`` = per-patch DataFrame with ``{sid, field_height, angle_deg}`` (and
    optionally ``dist_subject_mm``). For each config returns one row with the sampled
    field-height range, the azimuthal span, the per-zone patch counts, which zones are
    populated (>= MIN_PATCHES_PER_ZONE), and a ``sparse`` / ``degenerate`` flag set when
    the field-height span is too small to be a genuine field profile (the high-M tight
    cluster) — so downstream code does NOT over-interpret a cluster or extrapolate into
    empty zones. Returns a DataFrame, one row per config (richest coverage = most
    trustworthy for field analysis).
    """
    field = assign_field_zones(field)
    rows = []
    for sid, g in field.groupby("sid"):
        fh = g["field_height"].to_numpy(float)
        fh = fh[np.isfinite(fh)]
        ang = g["angle_deg"].to_numpy(float)
        ang = ang[np.isfinite(ang)]
        counts = {z: int((g["zone"] == z).sum()) for z in FIELD_ZONES}
        populated = [z for z in FIELD_ZONES if counts[z] >= MIN_PATCHES_PER_ZONE]
        span = float(fh.max() - fh.min()) if fh.size else float("nan")
        # azimuthal span: max gap on the circle subtracted from 360 (covered arc).
        if ang.size >= 2:
            s = np.sort(ang % 360.0)
            gaps = np.diff(np.concatenate([s, [s[0] + 360.0]]))
            angle_span = float(360.0 - gaps.max())
        else:
            angle_span = 0.0
        degenerate = (not np.isfinite(span)) or span < MIN_FIELD_HEIGHT_SPAN
        rows.append(dict(
            sid=sid, n_patches=int(g.shape[0]),
            field_height_min=float(fh.min()) if fh.size else float("nan"),
            field_height_max=float(fh.max()) if fh.size else float("nan"),
            field_height_span=span, angle_span_deg=angle_span,
            n_centre=counts["centre"], n_mid=counts["mid"], n_corner=counts["corner"],
            zones_populated=";".join(populated) or "none",
            n_zones_populated=len(populated),
            degenerate_cluster=bool(degenerate),
            field_supported=bool((not degenerate) and len(populated) >= 2),
        ))
    return (pd.DataFrame(rows).sort_values(["n_zones_populated", "field_height_span"],
                                           ascending=False).reset_index(drop=True))


def radial_falloff(field, *, value_col="amp", edges=FIELD_ZONE_EDGES):
    """Per-config relative sharpness vs field-height zone — the centre->corner curve.

    ``field`` = per-patch DataFrame with ``{sid, field_height, <value_col>}`` where
    ``value_col`` is the per-patch sharpness (default ``amp`` = sqrt-PSD at the fixed
    sensor frequency; also used with the pad-edge per-patch MTF). For each config and
    each populated zone returns the mean/median value and patch count, plus a
    ``corner_centre_ratio`` (corner mean / centre mean) — < 1 means the lens softens
    toward the corner (the expected falloff DIRECTION). Zones with fewer than
    MIN_PATCHES_PER_ZONE patches are emitted with ``is_sparse=True`` and not used in the
    ratio. Returns ``(zone_table, ratio_table)``.
    """
    field = assign_field_zones(field, edges=edges)
    zrows, rrows = [], []
    for sid, g in field.groupby("sid"):
        zmean = {}
        for z in FIELD_ZONES:
            gz = g[g["zone"] == z]
            vals = gz[value_col].to_numpy(float)
            vals = vals[np.isfinite(vals)]
            n = int(vals.size)
            sparse = n < MIN_PATCHES_PER_ZONE
            mean = float(np.mean(vals)) if n else float("nan")
            zrows.append(dict(sid=sid, zone=z, n=n, mean=mean,
                              median=float(np.median(vals)) if n else float("nan"),
                              is_sparse=bool(sparse)))
            if not sparse:
                zmean[z] = mean
        ratio = (zmean["corner"] / zmean["centre"]
                 if "corner" in zmean and "centre" in zmean and zmean["centre"] > 0
                 else float("nan"))
        mid_ratio = (zmean["mid"] / zmean["centre"]
                     if "mid" in zmean and "centre" in zmean and zmean["centre"] > 0
                     else float("nan"))
        rrows.append(dict(sid=sid, corner_centre_ratio=ratio,
                          mid_centre_ratio=mid_ratio,
                          falloff_supported=bool(np.isfinite(ratio))))
    return pd.DataFrame(zrows), pd.DataFrame(rrows)


def azimuthal_asymmetry(field, *, value_col="amp", radius_band=(0.33, 1.0),
                        min_patches=4):
    """Decentering / tilt signature: per-config MTF asymmetry vs azimuth at matched radius.

    Within an annulus (``radius_band`` in field-height units, default the mid+corner
    field where decentering shows) the per-patch sharpness is projected onto a
    left-right and a top-bottom axis. ``lr = (mean_right - mean_left)/mean`` and
    ``tb = (mean_top - mean_bottom)/mean`` (signed, same construction as
    characterise's peak-value L-R / T-B). The asymmetry MAGNITUDE is ``hypot(lr, tb)``
    and the DIRECTION is the azimuth ``atan2(tb, lr)`` of the soft->sharp gradient.
    Configs with fewer than ``min_patches`` in-band patches (or no opposing patches on
    an axis) get NaN and ``supported=False``. Returns a DataFrame, one row per config.

    Sign convention (matches :func:`field_geometry` azimuth): right = +x, top = +y;
    a POSITIVE ``lr`` means the RIGHT side is sharper than the LEFT, a POSITIVE ``tb``
    means the TOP is sharper than the BOTTOM. NOTE for cross-checking against
    ``characterise``: its ``decentering_*_lr`` is ``(left - right)/mean`` so its lr is
    the NEGATIVE of this one (its ``tb`` = ``(top - bottom)/mean`` AGREES in sign).
    """
    lo, hi = radius_band
    rows = []
    for sid, g in field.groupby("sid"):
        band = g[(g["field_height"] >= lo) & (g["field_height"] < hi)]
        band = band[np.isfinite(band[value_col].astype(float))]
        ang = band["angle_deg"].to_numpy(float)
        val = band[value_col].to_numpy(float)
        n = int(val.size)

        def _axis(mask_pos, mask_neg):
            vp, vn = val[mask_pos], val[mask_neg]
            if vp.size == 0 or vn.size == 0:
                return float("nan")
            mp, mn = vp.mean(), vn.mean()
            m = 0.5 * (mp + mn)
            return float((mp - mn) / m) if m != 0 else float("nan")

        # right: |angle|<90 ; left: |angle|>90 ; top: angle>0 ; bottom: angle<0
        right = np.abs(ang) < 90.0
        left = np.abs(ang) > 90.0
        top = ang > 0.0
        bottom = ang < 0.0
        lr = _axis(right, left)
        tb = _axis(top, bottom)
        supported = (n >= min_patches and np.isfinite(lr) and np.isfinite(tb))
        mag = float(np.hypot(lr, tb)) if supported else float("nan")
        direction = (float(np.degrees(np.arctan2(tb, lr)))
                     if supported else float("nan"))
        rows.append(dict(sid=sid, n_in_band=n, lr=lr, tb=tb,
                         asymmetry_mag=mag, asymmetry_dir_deg=direction,
                         supported=bool(supported)))
    return pd.DataFrame(rows)


def astigmatism_index(field, *, sag_col="amp_sag", tan_col="amp_tan",
                      radius_band=(0.33, 1.0), min_patches=3):
    """Sagittal vs tangential sharpness -> a per-config astigmatism index.

    Requires per-patch SAGITTAL and TANGENTIAL amplitudes (``sag_col``/``tan_col``),
    computed by the driver from the 2D PSD in wedges aligned to each patch's RADIAL
    direction (sagittal = along the field radius, tangential = perpendicular). Within
    the ``radius_band`` annulus (astigmatism vanishes at the centre) the index is
    ``mean(log(amp_sag / amp_tan))`` — 0 = no astigmatism, >0 = sagittal sharper,
    <0 = tangential sharper. Configs lacking the per-axis columns or with too few
    in-band patches get NaN and ``supported=False`` (then report as follow-up).
    Returns a DataFrame, one row per config.
    """
    lo, hi = radius_band
    rows = []
    has_cols = sag_col in field.columns and tan_col in field.columns
    for sid, g in field.groupby("sid"):
        if not has_cols:
            rows.append(dict(sid=sid, n_in_band=0, astig_index=float("nan"),
                             supported=False))
            continue
        band = g[(g["field_height"] >= lo) & (g["field_height"] < hi)]
        s = band[sag_col].to_numpy(float)
        t = band[tan_col].to_numpy(float)
        ok = np.isfinite(s) & np.isfinite(t) & (s > 0) & (t > 0)
        s, t = s[ok], t[ok]
        n = int(s.size)
        supported = n >= min_patches
        idx = float(np.mean(np.log(s / t))) if supported else float("nan")
        rows.append(dict(sid=sid, n_in_band=n, astig_index=idx,
                         supported=bool(supported)))
    return pd.DataFrame(rows)


def field_resolved_ranking(psd, meta, field, f_px=FPX_DEFAULT, *,
                           edges=FIELD_ZONE_EDGES):
    """Cross-config relative-MTF ranking run PER FIELD ZONE (centre / mid / corner).

    Restricts the same-patch chain to the patches whose field zone matches, then runs
    the validated estimator on each zone independently. ``field`` = per-patch DataFrame
    with ``{sid, patch, field_height}``; ``psd``/``meta`` as for :func:`rank_configs`.
    Answers "which configs hold their corners across M". A zone is skipped (with a note)
    if too few configs/patches survive the restriction to form a connected graph.
    Returns ``{zone: Ranking}`` for the zones that produced a ranking.
    """
    field = assign_field_zones(field, edges=edges)
    zone_of = {(r.sid, r.patch): r.zone for r in field.itertuples()}
    out = {}
    for z in FIELD_ZONES:
        keep = psd.apply(lambda r: zone_of.get((r["sid"], r["patch"])) == z, axis=1)
        zpsd = psd[keep]
        if zpsd.empty or zpsd.sid.nunique() < 2:
            continue
        zmeta = meta[meta.sid.isin(zpsd.sid.unique())]
        try:
            ranking = rank_configs(zpsd, zmeta, f_px, n_boot=0, strict=False)
        except ValueError:
            continue
        out[z] = ranking
    return out


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
