"""POC library for the multi-frequency-spectrum cross-config sharpness ranking.

UNTRACKED / exploratory. Do not import from production modules in a way that
mutates them; we only READ their helpers. This file holds:

  * A5 — M-aware band + maze-frequency labelling utilities.
  * A1 — atlas-predicted harmonic-comb spectrum reader (per config -> long table).
  * B1 — transitive least-squares chain solver + the four gate metrics.

Physics constants (from the plan / production modules, NOT re-derived):

  f_subj(lp/mm) = f_px(cy/px) * 229.9 * M           (229.9 = 1000/4.35)
  f_px_maze     = 4.35 / (13 * M)  cy/px            (maze = 77 lp/mm, M-invariant)
  pad fundamental ~ 18 lp/mm subject; odd harmonics 3f,5f,7f (near-square wave),
    even harmonics appear if duty != 0.5.

Subject->pixel: f_px = f_subj / (229.9 * M).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from tile_sharpness.methods.periodic_fft import periodic_contrast, derotate, discover_fundamental  # noqa: E402
from tile_sharpness.methods.harmonic_mtf import harmonic_amplitudes  # noqa: E402
from tile_sharpness.methods.maze_fft import maze_freq_cy_per_px, MAZE_PITCH_UM, SENSOR_PITCH_UM_Z7  # noqa: E402
from tile_sharpness import optics  # noqa: E402

LPMM_PER_CYPX = 1000.0 / SENSOR_PITCH_UM_Z7   # 229.885 lp/mm per cy/px at M=1
MAZE_SUBJ_LPMM = LPMM_PER_CYPX * (SENSOR_PITCH_UM_Z7 / MAZE_PITCH_UM)  # ~76.9 (M-invariant)

NYQUIST = 0.5


# --------------------------------------------------------------------------- #
# A5 — M-aware bands + maze labelling
# --------------------------------------------------------------------------- #

def maze_band_cy_per_px(M: float, half_bw_frac: float = 0.10) -> tuple[float, float, float] | None:
    """Return (f_maze, lo, hi) maze exclusion band in cy/px for this M, or None if
    the maze aliases past Nyquist. Width is a fraction of the maze freq so it tracks
    the maze as it slides with M (the A5 fix: at high M the maze drops INTO the old
    static 0.06-0.30 discovery band)."""
    fz = maze_freq_cy_per_px(M)
    if fz + half_bw_frac * fz > NYQUIST or fz <= 0:
        return None
    hw = half_bw_frac * fz
    return fz, max(0.0, fz - hw), min(NYQUIST, fz + hw)


def resolvable_band_cy_per_px(M: float, pad_f1_subj_lpmm: float = 18.0,
                              floor_margin: float = 0.6, nyq_frac: float = 0.5
                              ) -> tuple[float, float]:
    """M-aware resolvable band (cy/px). The OLD static 0.06 floor is M-naive: at low
    M the pad fundamental sits at a HIGHER cy/px than at high M (f_px = f_subj/(229.9 M)).
    Floor is set a bit below where the pad fundamental would land so f1 stays in-band
    but DC bleed / super-element (< ~0.5 f1) is excluded. Hi = nyq_frac * Nyquist."""
    f1_px = pad_f1_subj_lpmm / (LPMM_PER_CYPX * M)
    lo = floor_margin * f1_px
    hi = nyq_frac * NYQUIST  # default 0.25; periodic_contrast also guards Nyquist
    # never let lo exceed hi
    lo = min(lo, 0.8 * hi)
    return float(lo), float(hi)


def subj_to_px(f_subj_lpmm: float, M: float) -> float:
    return f_subj_lpmm / (LPMM_PER_CYPX * M)


def px_to_subj(f_px: float, M: float) -> float:
    return f_px * LPMM_PER_CYPX * M


def discover_pad_fundamental(der_bf: np.ndarray, M: float):
    """A5: discover the pad fundamental, EXCLUDING the maze band (M-aware), inside an
    M-aware resolvable band. Returns (rec_or_None, maze_band). The returned rec is the
    production discover_fundamental dict with pitch_px/f0_cy_per_px/axis/amp."""
    mb = maze_band_cy_per_px(M)
    lo, hi = resolvable_band_cy_per_px(M)
    # cap the discovery hi a touch below Nyquist so we never lock onto alias junk
    hi = min(hi, 0.40)
    exclude = (mb[1], mb[2]) if mb is not None else None
    rec = discover_fundamental(der_bf, band=(lo, hi), exclude=exclude)
    return rec, mb


# --------------------------------------------------------------------------- #
# A1 — atlas-predicted harmonic-comb spectrum
# --------------------------------------------------------------------------- #

def predict_comb_subj(pad_f1_subj_lpmm: float, max_order: int = 7):
    """Predict the pad comb in SUBJECT space: f1, 2f1, 3f1, ... up to max_order, plus
    the maze (added separately by the caller from M physics). Returns list of
    (feature, order, f_subj_lpmm). We include even orders too (duty may != 0.5); the
    SNR / ceiling gate drops the ones that aren't really there."""
    out = []
    for n in range(1, max_order + 1):
        out.append(("pad", n, pad_f1_subj_lpmm * n))
    return out


def read_comb_contrast(frames, theta_deg, M, n_marked, *, label_prefix=""):
    """Given the topk best-focus ROI frames (list of (lapvar, seq, roi)) for ONE
    region, de-rotate, discover the pad fundamental (A5), predict the comb, and read
    bounded Michelson contrast at each comb rung + the maze. Returns a list of sample
    dicts (the long-table rows) for this region, or [] if no pad periodicity found.

    Each sample: feature ('pad'/'maze'), harmonic_order, f_subj_lpmm, f_px,
    contrast, snr, ceiling, over_ceiling, valid (bool: resolvable & SNR-ok & not-over).
    """
    if not frames:
        return []
    der_frames = [(lv, seq, derotate(roi.astype(np.float64), theta_deg))
                  for lv, seq, roi in frames]
    der_bf = der_frames[0][2]
    pad_rec, mb = discover_pad_fundamental(der_bf, M)
    n_eff = optics.effective_fnumber(n_marked, M)

    samples = []

    def _read_at(f_subj, feature, order):
        f_px = subj_to_px(f_subj, M)
        if not (0.02 < f_px < NYQUIST - 1e-3):
            return None
        pitch = 1.0 / f_px
        # read peak Michelson contrast over the best-focus frames at this locked pitch
        best = None
        for _lv, _seq, der in der_frames:
            c = periodic_contrast(der, pitch_px=pitch, axis="auto")
            if c and (best is None or c["contrast"] > best["contrast"]):
                best = c
        if best is None:
            return None
        f_sensor_lpmm = f_px * LPMM_PER_CYPX
        ceil = optics.diffraction_mtf_at(f_sensor_lpmm, n_eff)
        over = best["contrast"] - ceil
        return dict(feature=feature, harmonic_order=order,
                    f_subj_lpmm=float(f_subj), f_px=float(f_px),
                    contrast=float(best["contrast"]), snr=float(best["snr"]),
                    ceiling=float(ceil), over_ceiling=float(over))

    if pad_rec is not None:
        pad_f1_subj = px_to_subj(pad_rec["f0_cy_per_px"], M)
        for feature, order, f_subj in predict_comb_subj(pad_f1_subj, max_order=7):
            s = _read_at(f_subj, feature, order)
            if s is not None:
                samples.append(s)

    # maze rung (physics, M-invariant subject freq)
    if mb is not None:
        s = _read_at(MAZE_SUBJ_LPMM, "maze", 1)
        if s is not None:
            samples.append(s)

    for s in samples:
        s["label"] = label_prefix
    return samples


# --------------------------------------------------------------------------- #
# B1 — transitive least-squares chain
# --------------------------------------------------------------------------- #

def build_chain(long_rows, *, freq_tol_lpmm=4.0, snr_min=3.0, max_over=0.05,
                min_contrast=1e-3, agg="median", min_node_n=3, drop_features=()):
    """Build the comparison graph + solve the least-squares sharpness scores.

    long_rows: iterable of dicts with keys config, M, feature, harmonic_order,
      f_subj_lpmm, contrast, snr, ceiling, over_ceiling. (One per (config,region,rung);
      we aggregate to one contrast per (config, shared-frequency-node) by max over
      regions — pad highlights make some regions specular; max is the cleanest read.)

    A shared frequency NODE is a (feature, harmonic_order) pair matched within
    freq_tol_lpmm in subject space across configs. We require the per-config sample to
    be SNR-ok and ceiling-valid (over_ceiling <= max_over) to enter the graph.

    Returns dict with: scores {config: s}, ranking [(config, s)], n_nodes, n_edges,
      components, residual_rms, n_cycles_violated (sign-inconsistent triangles),
      edges (list), freq_nodes (config -> {node_key: contrast}).
    """
    # 1. filter valid samples and bucket into frequency nodes
    valid = [r for r in long_rows
             if r["snr"] >= snr_min and r["over_ceiling"] <= max_over
             and r["contrast"] > min_contrast and r["feature"] not in drop_features]
    # node key: feature + harmonic_order + rounded subject frequency bucket
    # bucket width = freq_tol; this groups e.g. pad-3f at M=1 (54 lpmm) with pad-3f at
    # M=2 (also 54 lpmm subject) — the shared rung.
    def node_key(r):
        bucket = round(r["f_subj_lpmm"] / freq_tol_lpmm)
        return (r["feature"], bucket)

    # config -> node -> aggregated contrast over the region replicates.
    #   agg="max"    — dodge pad specular dropouts but amplifies extreme-value noise.
    #   agg="median" — robust central read across the region replicates (recommended;
    #                  the max-aggregation injected ~0.6-log spurious gaps between
    #                  near-identical configs in the first run).
    # Require >= min_node_n region replicates per (config,node) so a single specular
    # region cannot define a chain edge.
    from collections import defaultdict
    raw = defaultdict(lambda: defaultdict(list))   # cfg -> node -> [(C, snr, f)]
    for r in valid:
        raw[r["config"]][node_key(r)].append((r["contrast"], r["snr"], r["f_subj_lpmm"]))
    cfg_node = {}
    for cfg, nodes in raw.items():
        d = {}
        for k, vals in nodes.items():
            if len(vals) < min_node_n:
                continue
            cs = np.array([v[0] for v in vals])
            snrs = np.array([v[1] for v in vals])
            fs = np.array([v[2] for v in vals])
            c = float(np.max(cs)) if agg == "max" else float(np.median(cs))
            d[k] = (c, float(np.median(snrs)), float(np.median(fs)))
        if d:
            cfg_node[cfg] = d

    configs = sorted(cfg_node)
    idx = {c: i for i, c in enumerate(configs)}

    # 2. edges: for every node shared by >=2 configs, add pairwise equations
    from collections import defaultdict
    node_members = defaultdict(list)  # node_key -> [(config, contrast, snr, f)]
    for cfg, d in cfg_node.items():
        for k, (c, snr, f) in d.items():
            node_members[k].append((cfg, c, snr, f))

    # aggregate per (config_i, config_j) over all shared nodes: mean log-ratio, weight
    pair_diffs = defaultdict(list)   # (i,j) i<j -> list of (logratio, weight)
    for k, members in node_members.items():
        if len(members) < 2:
            continue
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                ci, cci, si, _ = members[a]
                cj, ccj, sj, _ = members[b]
                if cci <= 0 or ccj <= 0:
                    continue
                lr = np.log(cci / ccj)
                w = min(si, sj)
                ii, jj = idx[ci], idx[cj]
                if ii < jj:
                    pair_diffs[(ii, jj)].append((lr, w))
                else:
                    pair_diffs[(jj, ii)].append((-lr, w))

    edges = []
    for (ii, jj), lst in pair_diffs.items():
        lrs = np.array([x[0] for x in lst]); ws = np.array([x[1] for x in lst])
        wmean = float(np.sum(lrs * ws) / np.sum(ws))
        edges.append((ii, jj, wmean, float(np.sum(ws)), len(lst)))

    n = len(configs)
    # 3. connectivity (components) over the edge graph
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        parent[find(a)] = find(b)
    for ii, jj, *_ in edges:
        union(ii, jj)
    comps = defaultdict(list)
    for c in range(n):
        comps[find(c)].append(configs[c])
    components = sorted(comps.values(), key=len, reverse=True)

    # 4. least squares: s_i - s_j = wmean, weighted, gauge = zero-mean per component
    #    Build A (n_edges x n), W diag. Add a tiny zero-mean anchor row per component.
    if edges:
        rows_A = []; rhs = []; wts = []
        for ii, jj, wmean, wsum, _ in edges:
            row = np.zeros(n); row[ii] = 1.0; row[jj] = -1.0
            rows_A.append(row); rhs.append(wmean); wts.append(wsum)
        # gauge: zero-mean over each component (weak constraint)
        for comp_members in components:
            row = np.zeros(n)
            for cfg in comp_members:
                row[idx[cfg]] = 1.0
            rows_A.append(row); rhs.append(0.0); wts.append(1e3)
        A = np.array(rows_A); b = np.array(rhs); W = np.sqrt(np.array(wts))
        Aw = A * W[:, None]; bw = b * W
        sol, *_ = np.linalg.lstsq(Aw, bw, rcond=None)
        scores = {configs[i]: float(sol[i]) for i in range(n)}
        # residuals on the data edges only
        resid = []
        for ii, jj, wmean, wsum, _ in edges:
            resid.append((sol[ii] - sol[jj]) - wmean)
        residual_rms = float(np.sqrt(np.mean(np.square(resid)))) if resid else 0.0
    else:
        scores = {c: 0.0 for c in configs}
        residual_rms = 0.0

    # 5. cycle / transitivity consistency: count sign-inconsistent triangles
    n_tri, n_tri_bad = _triangle_consistency(edges, n)

    ranking = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return dict(scores=scores, ranking=ranking, configs=configs,
                n_nodes=len([k for k, m in node_members.items() if len(m) >= 2]),
                n_edges=len(edges), components=components,
                residual_rms=residual_rms, edges=edges,
                cfg_node=cfg_node, node_members=dict(node_members),
                n_triangles=n_tri, n_triangles_inconsistent=n_tri_bad)


def _triangle_consistency(edges, n):
    """Count triangles (i,j,k all pairwise connected) whose summed log-ratios deviate
    from zero by more than a tolerance — i.e. A>B>C>A contradictions."""
    from collections import defaultdict
    g = {}
    for ii, jj, wmean, *_ in edges:
        g[(ii, jj)] = wmean
        g[(jj, ii)] = -wmean
    adj = defaultdict(set)
    for ii, jj, *_ in edges:
        adj[ii].add(jj); adj[jj].add(ii)
    nodes = sorted(adj)
    n_tri = 0; n_bad = 0
    for a in nodes:
        for b in adj[a]:
            if b <= a:
                continue
            for c in adj[b]:
                if c <= b or c not in adj[a]:
                    continue
                # triangle a-b-c
                cyc = g[(a, b)] + g[(b, c)] + g[(c, a)]
                n_tri += 1
                if abs(cyc) > 0.20:   # > ~0.2 in log-contrast = ~22% inconsistency
                    n_bad += 1
    return n_tri, n_bad
