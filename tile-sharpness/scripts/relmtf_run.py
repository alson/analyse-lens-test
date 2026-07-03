#!/usr/bin/env python
"""P2 production driver / CLI for the cross-M relative glass-MTF pipeline.

This is the PRODUCTIONISED driver (Phase P2) that runs the whole cross-M
relative-MTF pipeline over the FROZEN multi-session subset
(``data/cross_m_relative_mtf_subset_multisession.csv``, 316 config-nodes;
151 rail-coverage-tier / 165 manual-tier). Its extract/analyse stages were
ported from the (now-removed) parked recovered driver and ADAPTED to the
CURRENT production modules (the recovered dir was deleted once its
multi-session/supersession/tier logic landed in ``multi_session`` +
``cross_m_relative_mtf``; git commit 4085c9c holds the provenance):

* ``tile_sharpness.multi_session`` — :func:`discover_config_nodes` / :func:`sid`
  / :func:`human` (frozen-subset iteration, @YYMMDD-tagged collision-free ids).
* ``tile_sharpness.cross_m_relative_mtf`` — the validated estimator core
  (P1 spectral ranking + gates), plus the P1 coverage helpers
  (:func:`coverage_flag` / :func:`p2_rail_available` (tier gate) /
  :func:`coverage_config_ok`), the location-aware field helpers, and P2 through-focus.
* ``tile_sharpness.focus_physical`` (POC 2/3) — :func:`resolve_step` (documented vs
  DoF-estimated) + :func:`patch_physical_row` (mu_mm / fwhm_mm / imputation).
* ``tile_sharpness.field_geometry_focus`` (POC 4) — :func:`analyse_field_geometry`
  (tilt-removed curvature + vertex offset).
* ``tile_sharpness.rail_calibration`` — :class:`EffectiveApertureLookup` (empirical
  effective aperture from the per-session ``effective_apertures.csv`` trees).

  ---------------------------------------------------------------------------------
  THIS IS A FENCED TOOL. The headline output is a RELATIVE, FIXED-SENSOR-FREQUENCY
  glass-MTF ranking ("which lens has the higher MTF at this pixel frequency"), NOT an
  absolute MTF and NOT a subject-resolution ranking. Trustworthy only at
  f_px = 0.08-0.15. See the cross_m_relative_mtf module docstring before using.
  ---------------------------------------------------------------------------------

Stages (sharded on nufan; each writes per-shard CSVs the analyse stage pools):

    extract   register each config (reg_auto, read-only) with a plausibility GUARD;
              resample the SAME physical atlas patch onto a common subject grid; radial
              PSD per patch (P1 substrate, ALL tiers); pad-edge averaged-ESF MTF (P3.1);
              relative-deconvolution patches (P3.2, saved .npy); per-patch location tag
              (field geometry, POC-4 substrate); and the through-focus per-patch
              Gaussian FWHM + mu + coverage_flag (P2) emitted ONLY for the rail-coverage
              tier (tier gate). Sharded by --shard i/N over the frozen subset.

    analyse   pool the shards; run the estimator core (chain + gates + bootstrap +
              jackknife + split-half); fold in P3.1/P3.2/P2 corroborators + consensus;
              resolve the per-sweep rail step (documented from shots.csv for 2026-05+,
              DoF-estimated for pre-2026-05 manual sweeps) + effective aperture (CSV
              trees) and emit POC-3 physical-mm + POC-4 field geometry. Tier-aware:
              the HEADLINE ranking is rail-coverage-tier-only; the manual tier is a
              secondary degraded view. M>1.10 configs are flagged low-confidence and
              excluded from the headline ranking/geometry.

Usage (on nufan via the per-host venv):

    relmtf_run.py extract --subset data/..._multisession.csv --out <dir> --shard 0/16
    ... (all shards) ...
    relmtf_run.py analyse --subset data/..._multisession.csv --out <dir> --tier rail-coverage
"""
from __future__ import annotations

import argparse
import csv as _csv
import importlib.util
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TS = HERE.parent
sys.path.insert(0, str(TS / "src"))

from tile_sharpness import cross_m_relative_mtf as X  # noqa: E402
from tile_sharpness import multi_session as MS  # noqa: E402
from tile_sharpness.cameras import camera_pitch_um  # noqa: E402
from tile_sharpness import m_lookup as ML  # noqa: E402
from tile_sharpness import optics  # noqa: E402
from tile_sharpness import focus_physical as FP  # noqa: E402
from tile_sharpness.field_geometry_focus import (  # noqa: E402
    Z7_CENTRE, Z7_HALF_DIAG_PX, analyse_field_geometry,
)
from tile_sharpness.rail_calibration import EffectiveApertureLookup  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# production registration infra (read-only) + the warm/saturation channel decode —
# loaded from the POC scripts exactly as the recovered / current drivers do.
apf = _load("apf", HERE / "atlas_periodic_fft.py")
reg_auto = apf.reg_auto
ccolor = _load("ccolor", HERE / "poc_comb_chain_contrast_color.py")
M_ANCHOR_SCALE = apf.M_ANCHOR_SCALE
IMAGE_W, IMAGE_H = apf.IMAGE_W, apf.IMAGE_H
# sibling-prior recovery (class A tilt/pitch gating + class B matched filter). Loaded
# from the wafer-atlas scripts dir next to reg_auto; its entry points only engage with a
# prior, so importing it does not change the one-pass extract's default registration.
_WA_SCRIPTS = (TS.parent / "wafer-atlas" / "scripts")
spr = _load("sibling_prior_reg", _WA_SCRIPTS / "sibling_prior_reg.py")

# raw-data root that holds the per-session effective_apertures.csv + shots.csv trees.
TEST_RAW_DATA = Path("/home/alson/shared/files/pics/digikam/test-raw-data")

# effective-aperture CSV trees (the sessions that ship a CSV). Never analytical (1+M/p):
# resolution is CSV -> directory-name aperture (see resolve_effective_aperture note).
EFF_AP_CSVS = [
    TEST_RAW_DATA / "2026-01-29" / "effective_apertures.csv",
    TEST_RAW_DATA / "2026-02-18" / "effective_apertures.csv",
    TEST_RAW_DATA / "2026-05-13" / "effective_apertures.csv",
]

# Documented step is available only for the rail-coverage (2026-05+) sessions whose
# lens-config dir carries shots.csv. Pre-2026-05 manual sweeps -> DoF-estimated.
DOCUMENTED_STEP_SESSIONS = ("2026-05-12", "2026-05-13")

# common-grid layout (validated AltEst-2 values).
PATCH_UNITS = 0.5
SAMPLES_PER_UNIT = int(X.SAMPLES_PER_UNIT)
GLOBAL_CL = (1.5, 11.0)
GLOBAL_RL = (0.5, 6.0)

# §L reference groupings for the known-orders gate report (baseline 2026-01-29 sids).
MODERN_MACRO_BARE = ["Z105_1_1_F8", "AF200_1_1_F8", "S105_1_1_F8", "S150_1_1_F8"]
VINTAGE = ["V55f28287318_1_1_F8", "V55f28537016_1_1_F8", "V55f35209088_1_1_F8",
           "V55f35258263_1_1_F8", "AF60_1_1_F8"]
DIOPTER_TAIL = ["Z100400+MCON-35_1_1.16_F8", "AF200+5T+6T_2_1_F8",
                "S150+5T+6T_1.8_1_F8", "AF200+6T_1.7_1_F8"]


# --------------------------------------------------------------------------- #
# reg_auto plausibility GUARD (ruling #5)
# --------------------------------------------------------------------------- #
# The atlas registration can succeed numerically yet be physically implausible. Three
# documented failure modes get a config DROPPED (never silently skipped — every drop is
# logged to dropped_configs.csv with a reason):
#   1. absolute-M out of a sane bound (M < REG_M_MIN or M > REG_M_MAX).
#   2. registration residual above an OBJECT-SPACE ceiling (rmse_px * pitch / M >
#      REG_RMSE_MAX_OBJECT_UM). Registration accuracy is a physical constant in object
#      space (~9um median, p99~20um, M-INDEPENDENT: corr(M, rmse_um)=-0.06 over 300 fits);
#      the per-pixel rmse rises with M (corr +0.66) ONLY because a pixel subtends pitch/M
#      in object space. A flat px ceiling is therefore too strict at high M (clips good
#      high-M fits at 12-18um) and too lenient at low M (would pass a 50um-off low-M lock);
#      the object-space ceiling fixes both.
#   3. the M~0 scale-COLLAPSE failure mode (HANDOVER 2026-06-28): a near-zero measured M
#      returned at a deceptively LOW residual. apf.register already fences scale/anchor
#      to (0.15, 3.5), but a collapse can still land just inside at an anomalously good
#      residual, so we additionally drop M below REG_M_COLLAPSE regardless of residual.
# The M>1.10 low-confidence flag (ruling #2) is ORTHOGONAL and handled in analyse; this
# guard is only the hard drop for non-physical registrations.
REG_M_MIN = 0.20          # sane lower magnification bound for this wafer rig
REG_M_MAX = 3.50          # sane upper bound (matches apf scale-collapse fence)
REG_M_COLLAPSE = 0.20     # M at/below this is the scale-collapse mode -> drop
SENSOR_PITCH_UM = 4.35            # Z7 pixel pitch, for object-space rmse conversion
REG_RMSE_MAX_OBJECT_UM = 25.0     # object-space residual ceiling. p99 of kept fits ~20um,
                                  # so 25um keeps every prior-good fit, ADMITS the high-M
                                  # near-ceiling group (12.6-17.6um; flat 6px clipped them),
                                  # and REJECTS wrong-locks (bare 24-120 F5.6/F8 at 255-293um).

# --------------------------------------------------------------------------- #
# min-residual-over-frames registration frame-selection (recovery fix, 2026-06-30)
# --------------------------------------------------------------------------- #
# The scale-COLLAPSE floor used DURING frame selection (distinct from the outer
# reg_guard REG_M_COLLAPSE=0.20, which is the final hard drop). The 316-config good run
# never produced an honest lock below M~0.382; documented collapses land at M~0.15-0.27
# at a deceptively LOW residual (24-120 F5.6 collapse M=0.193 rmse=10.3 beats the honest
# M=0.410 rmse=0.63 lock on another frame). A 0.30 floor sits in the clean gap between
# the two populations, so it rejects the collapse family without touching any honest fit.
REG_SELECT_M_FLOOR = 0.30
# when a nominal M is known (from mag_label), reject a lock whose measured M is below
# this fraction of nominal (a collapse) or wildly above it. atlas-M is validated to
# +-1.6% but nominal LABELS can be off by more, so the band is generous.
REG_SELECT_NOMINAL_LO = 0.55   # measured >= 0.55 * nominal (below => collapse)
REG_SELECT_NOMINAL_HI = 1.90   # measured <= 1.90 * nominal (above => wrong-lock)
# how many candidate frames to attempt registration on, per config. Registration is the
# expensive step, so we cap it: the sharpest N_TOPK central-lapvar frames plus a handful
# spread across the stack. The honest lock for the wrong-lock zooms sits ~20-30th by
# lapvar (the sharpest bracket registers WORST), so a top-3 window misses it. Per-config
# diagnostics put the deepest honest lock at rank ~16 (Z100400 F8), so 20 covers the
# observed ranks while staying much cheaper than all-frames.
REG_SELECT_TOPK = 20
REG_SELECT_SPREAD = (0.3, 0.5, 0.7)


def nominal_M_for(node) -> float:
    """Best-effort nominal magnification for a config node, or NaN if unknown.

    Prefers the explicit ``nominal_M`` CSV column; falls back to parsing the
    ``mag_label`` dir name (``<a>_<b>`` -> a/b, e.g. ``1_2.00`` -> 0.5, ``1.53_1`` ->
    1.53). Bare-zoom 2026-05 configs carry NEITHER (empty mag_label) -> NaN, and the
    selector then falls back to the absolute REG_SELECT_M_FLOOR only.
    """
    raw = (getattr(node, "nominal_M", "") or "").strip()
    if raw:
        try:
            v = float(raw)
            if math.isfinite(v) and v > 0:
                return v
        except ValueError:
            pass
    lbl = (getattr(node, "mag_label", "") or "").strip()
    if lbl:
        v = ML.parse_mag_label(lbl)
        if math.isfinite(v) and v > 0:
            return v
    return float("nan")


def _lock_plausible(M, nominal_M):
    """Is a candidate lock's measured ``M`` physically plausible for selection?

    Two-stage: (1) an ABSOLUTE collapse floor that always applies; (2) when a finite
    positive ``nominal_M`` is known, a generous band around it (rejects both a collapse
    that landed just above the floor and a 2x mis-lock). Pure / unit-tested.
    """
    if not (M is not None and np.isfinite(M) and M > 0):
        return False
    if M < REG_SELECT_M_FLOOR:
        return False
    if nominal_M is not None and np.isfinite(nominal_M) and nominal_M > 0:
        if M < REG_SELECT_NOMINAL_LO * nominal_M:
            return False
        if M > REG_SELECT_NOMINAL_HI * nominal_M:
            return False
    return True


def select_registration(candidates, nominal_M=float("nan")):
    """Pick the best registration among per-frame candidate locks (min-residual rule).

    ``candidates`` is an iterable of dicts each carrying at least ``M`` and ``rmse``
    (extra keys are preserved on the winner). Keep only PLAUSIBLE locks
    (:func:`_lock_plausible` — absolute collapse floor + optional nominal-M band), then
    return the one with the LOWEST finite ``rmse``. Returns ``None`` when no candidate is
    plausible (the config is then dropped upstream). This is the whole recovery decision;
    it is pure and unit-tested. Rejecting collapses HERE (not only via the outer
    reg_guard) is what lets an honest higher-M lock on a lower-lapvar frame win over a
    deceptively-low-residual collapse on the sharpest frame.
    """
    best = None
    for c in candidates:
        M = c.get("M")
        rmse = c.get("rmse")
        if rmse is None or not np.isfinite(rmse):
            continue
        if not _lock_plausible(M, nominal_M):
            continue
        if best is None or rmse < best["rmse"]:
            best = c
    return best


def reg_guard(M, rmse, pitch_um=SENSOR_PITCH_UM):
    """Return ``(ok, reason)`` for a registration's (M, reg_fit_rmse_px).

    ``ok`` False means DROP the config; ``reason`` is a short human tag logged to
    ``dropped_configs.csv``. Pure / unit-tested. Order of checks: collapse, then M
    bounds, then residual ceiling (so a collapse is reported as such, not "rmse").

    ``pitch_um`` is the config's sensor pixel pitch (Z7 4.35 µm default); the object-space
    ceiling is ``rmse_px * pitch_um / M``. Passing the per-camera pitch fixes the D7200
    over-strict guard — the hard-coded Z7 4.35 over-estimated D7200 (3.91) object rmse by
    4.35/3.91 = 11.3%.
    """
    if not (M is not None and np.isfinite(M)):
        return False, "reg_M_nonfinite"
    if M <= REG_M_COLLAPSE:
        return False, f"reg_scale_collapse(M={M:.3f}<= {REG_M_COLLAPSE})"
    if not (REG_M_MIN <= M <= REG_M_MAX):
        return False, f"reg_M_out_of_bounds(M={M:.3f})"
    if not (rmse is not None and np.isfinite(rmse)):
        return False, "reg_rmse_nonfinite"
    rmse_um = rmse * pitch_um / M
    if rmse_um > REG_RMSE_MAX_OBJECT_UM:
        return False, (f"reg_rmse_too_high(rmse={rmse:.2f}px={rmse_um:.1f}um"
                       f"> {REG_RMSE_MAX_OBJECT_UM}um)")
    return True, ""


# --------------------------------------------------------------------------- #
# step-source selection (ruling: documented for 2026-05+, DoF only pre-2026-05)
# --------------------------------------------------------------------------- #
def step_source_for_session(session, documented_step_mm):
    """Which step source a sweep should use given its session + documented lookup.

    Returns one of :data:`focus_physical.STEP_SOURCES`: ``"documented"`` when the
    session is a 2026-05+ rail-coverage session AND a finite positive documented step
    was resolved from its ``shots.csv``; otherwise ``"dof_estimated"``. NEVER
    DoF-estimate when a documented step exists (the binding rule). Pure / unit-tested.
    """
    session = (session or "").strip()
    if (session in DOCUMENTED_STEP_SESSIONS and documented_step_mm is not None
            and np.isfinite(documented_step_mm) and documented_step_mm > 0):
        return "documented"
    return "dof_estimated"


def documented_step_for(node):
    """Median-diff rail step (mm/frame) from the sweep's shots.csv, or None.

    For a 2026-05+ node the lens-config dir (``sweep_dir.parent``) carries
    ``shots.csv``; keep ``phase == "sweep"`` rows, match this node's aperture
    (directory ``f_<x>`` -> float), and take ``median(diff(sorted(distinct
    rail_position_mm)))`` (replica frames share a rail position, hence the set).
    Returns None for non-2026-05 sessions or when no documented step is derivable —
    the caller then DoF-estimates. Never analytical.
    """
    if (node.session or "").strip() not in DOCUMENTED_STEP_SESSIONS:
        return None
    shots = node.sweep_dir.parent / "shots.csv"
    if not shots.exists():
        return None
    ap_f = _ap_to_n(node.aperture)
    try:
        with open(shots, newline="") as fh:
            rows = [r for r in _csv.DictReader(fh) if r.get("phase") == "sweep"]
    except OSError:
        return None
    pos = set()
    for r in rows:
        av = _ap_str_to_f(str(r.get("aperture", "")))
        if av is not None and round(av, 2) == round(ap_f, 2):
            try:
                pos.add(float(r["rail_position_mm"]))
            except (ValueError, TypeError, KeyError):
                pass
    pos = sorted(pos)
    if len(pos) < 2:
        return None
    step = float(np.median(np.diff(pos)))
    return step if (np.isfinite(step) and step > 0) else None


def _ap_str_to_f(s):
    s = s.strip().lower().removeprefix("f/").removeprefix("f")
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# config id helpers (delegate to the multi_session production module)
# --------------------------------------------------------------------------- #
def _ap_to_n(a):
    return float(str(a).replace("F", "").replace("f_", "").replace("f", ""))


def _f_dir_name(node):
    """The aperture DIRECTORY name for the effective-aperture CSV key (F_dir_name)."""
    return node.sweep_dir.name


def patch_layout():
    out = []
    cl = GLOBAL_CL[0]
    i = 0
    while cl + PATCH_UNITS <= GLOBAL_CL[1]:
        rl = GLOBAL_RL[0]
        j = 0
        while rl + PATCH_UNITS <= GLOBAL_RL[1]:
            out.append((cl, rl, cl + PATCH_UNITS, rl + PATCH_UNITS, f"A{i:02d}{j:02d}"))
            rl += PATCH_UNITS
            j += 1
        cl += PATCH_UNITS
        i += 1
    return out


# --------------------------------------------------------------------------- #
# extraction primitives (ported from the validated location-aware POC driver;
# reg_auto is used read-only)
# --------------------------------------------------------------------------- #
def _central_lapvar(g):
    """Central-ROI Laplacian variance (focus proxy). Mirrors apf.central_lapvar."""
    c = g[IMAGE_H // 2 - 800:IMAGE_H // 2 + 800, IMAGE_W // 2 - 800:IMAGE_W // 2 + 800]
    return float(cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var())


def _register_candidate_frames(jpgs, topk=REG_SELECT_TOPK, spread=REG_SELECT_SPREAD):
    """Choose the candidate frames to attempt registration on for a config.

    The sharpest ``topk`` frames by central-ROI lapvar (ranked over a dense subsample —
    the focus plateau is wide so we needn't score every frame) PLUS a few spread across
    the stack as insurance. Returns a de-duplicated, order-preserving list of jpg paths.
    Wider than the legacy apf.register top-3 window: the honest lock for the wrong-lock
    bare zooms sits ~20-30th by lapvar (the SHARPEST exposure bracket registers worst),
    so a narrow window structurally misses it.
    """
    step = max(1, len(jpgs) // 120)
    sub = jpgs[::step]
    lv = []
    for jp in sub:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        lv.append((_central_lapvar(g) if g is not None else -1.0, jp))
    lv.sort(reverse=True, key=lambda t: t[0])
    cand = [jp for _, jp in lv[:topk]]
    cand += [jpgs[min(len(jpgs) - 1, int(len(jpgs) * f))] for f in spread]
    return list(dict.fromkeys(cand))


def _refine_distortion_if_helps(p):
    """Optionally re-fit a per-config radial (k1[,k2]) term over a lock's own
    correspondences, keeping it only when it meaningfully cuts the residual.

    ``reg_auto.refine_full_res`` ALREADY conditionally adds a radial term (>=12 pairs and
    >=20% RMSE drop), so a lock returned by ``register_and_refine`` may already carry
    ``k1``/``k2``. This is a no-op wrapper kept as the documented hook for the mode-B
    (distorting-glass) path: the empirical finding was that the honest per-frame affine
    lock already sits well under the 6px ceiling for the recoverable distorting configs
    (24-120+ext F11 affine rmse=1.71), so no ADDITIONAL distortion fit is applied here —
    doing so risks the term absorbing peak-localization noise instead of real distortion.
    Returns ``p`` unchanged; present so the distortion decision has a single named home.
    """
    return p


def register_config(sweep_dir, node=None):
    """Register a config via MIN-RESIDUAL-OVER-FRAMES selection.

    Ranks several candidate frames (:func:`_register_candidate_frames`), registers each
    with ``reg_auto.register_and_refine`` (unchanged estimator), and keeps the lock with
    the LOWEST fit residual AMONG PLAUSIBLE-M locks (:func:`select_registration`, which
    rejects scale-collapses via the absolute floor + optional nominal-M band). ``node``
    (when given) supplies the nominal M so the collapse rejection is config-aware; when
    absent the absolute floor alone applies. Returns ``(affine_p, M, jpgs)`` or
    ``(None, None, jpgs)`` if no plausible lock is found.

    Only the FRAME/LOCK SELECTION changes vs the legacy ``apf.register``; the detection,
    fit, refinement, geometry and downstream all use the same reg_auto code.
    """
    sweep_dir = Path(sweep_dir)
    jpgs = sorted(sweep_dir.glob("*.jpg")) + sorted(sweep_dir.glob("*.JPG"))
    if not jpgs:
        return None, None, []
    nominal_M = nominal_M_for(node) if node is not None else float("nan")
    candidates = []
    for jp in _register_candidate_frames(jpgs):
        try:
            p = reg_auto.register_and_refine("x", path=str(jp), anchors=None)
        except Exception:
            continue
        if p is None or not p.get("n_refine_intersections"):
            continue
        rmse = p.get("reg_fit_rmse_px")
        if rmse is None or not np.isfinite(rmse):
            continue
        M = p["scale"] / M_ANCHOR_SCALE
        candidates.append(dict(M=M, rmse=float(rmse), p=p, frame=jp.name))
    best = select_registration(candidates, nominal_M)
    if best is None:
        return None, None, jpgs
    p = _refine_distortion_if_helps(best["p"])
    return p, best["M"], jpgs


def _lapvar(a):
    return float(cv2.Laplacian(a.astype(np.float32), cv2.CV_32F).var())


def scan_all_boxes(jpgs, boxes):
    ib = {i: tuple(int(v) for v in b) for i, b in enumerate(boxes)}
    seqs = {i: [] for i in ib}
    lvs = {i: [] for i in ib}
    for seq, jp in enumerate(jpgs):
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        for i, (x0, y0, x1, y1) in ib.items():
            roi = g[y0:y1, x0:x1]
            if roi.size == 0 or min(roi.shape) < 16:
                continue
            seqs[i].append(seq)
            lvs[i].append(_lapvar(roi))
    return {i: (np.asarray(seqs[i], float), np.asarray(lvs[i], float)) for i in ib}


def _cum_vec(d4, k):
    d4 = np.asarray(d4, float)
    k = np.asarray(k, float)
    out = np.zeros_like(k)
    pos = k > 0
    kp = k[pos]
    k_int = np.floor(kp).astype(int)
    frac = kp - k_int
    full = k_int // 4
    rem = k_int % 4
    csum = np.concatenate([[0.0], np.cumsum(d4)])
    c = full * d4.sum() + csum[rem] + frac * d4[rem % 4]
    out[pos] = c
    return out


def atlas_rect_to_common_grid(img, p, cl0, rl0, cl1, rl1, samples_per_unit,
                              interp=cv2.INTER_CUBIC):
    """Resample the SAME physical atlas rectangle onto a fixed common subject grid."""
    W = int(round((cl1 - cl0) * samples_per_unit))
    H = int(round((rl1 - rl0) * samples_per_unit))
    if W < 16 or H < 16:
        return None
    cls = cl0 + (np.arange(W) + 0.5) / samples_per_unit
    rls = rl0 + (np.arange(H) + 0.5) / samples_per_unit
    CL, RL = np.meshgrid(cls, rls)
    th = p["theta_rad"]; x0 = p["x0_img"]; y0 = p["y0_img"]; s = p["scale"]
    U = _cum_vec(reg_auto.D_COL, CL.ravel()).reshape(CL.shape)
    V = _cum_vec(reg_auto.D_ROW, RL.ravel()).reshape(RL.shape)
    c, sn = np.cos(th), np.sin(th)
    xu = x0 + s * (c * U + sn * V)
    yu = y0 + s * (sn * U - c * V)
    if "k1" in p:
        dx = xu - reg_auto.DIST_CENTER[0]; dy = yu - reg_auto.DIST_CENTER[1]
        r2 = (dx * dx + dy * dy) / reg_auto.DIST_NORM ** 2
        f = 1.0 + p["k1"] * r2 + p["k2"] * r2 * r2
        xu = reg_auto.DIST_CENTER[0] + dx * f
        yu = reg_auto.DIST_CENTER[1] + dy * f
    mapx = xu.astype(np.float32); mapy = yu.astype(np.float32)
    if (mapx.min() < 2 or mapx.max() > IMAGE_W - 2
            or mapy.min() < 2 or mapy.max() > IMAGE_H - 2):
        return None
    return cv2.remap(img.astype(np.float32), mapx, mapy, interp,
                     borderMode=cv2.BORDER_REFLECT)


def decode_sat(jp):
    bgr = cv2.imread(str(jp), cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return ccolor.channel_stack(bgr)["sat"].astype(np.float32)


def _hann2d(h, w):
    return np.outer(np.hanning(h), np.hanning(w))


def radial_psd(patch, nbins=64):
    """Windowed radial PSD; freq in cy per common-grid px (units cancel in the ratio)."""
    a = patch - patch.mean()
    h, w = a.shape
    a = a * _hann2d(h, w)
    F = np.fft.fftshift(np.fft.fft2(a))
    P = F.real ** 2 + F.imag ** 2
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    fr = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    bins = np.linspace(0, 0.5, nbins + 1)
    idx = np.digitize(fr.ravel(), bins) - 1
    Pf = P.ravel()
    psd = np.full(nbins, np.nan)
    for b in range(nbins):
        m = idx == b
        if m.any():
            psd[b] = Pf[m].mean()
    fcen = 0.5 * (bins[:-1] + bins[1:])
    return fcen, psd


def directional_psd(patch, radial_angle_deg, nbins=64, wedge_deg=35.0):
    """Radial PSD split into SAGITTAL vs TANGENTIAL wedges (for astigmatism)."""
    a = patch - patch.mean()
    h, w = a.shape
    a = a * _hann2d(h, w)
    F = np.fft.fftshift(np.fft.fft2(a))
    P = F.real ** 2 + F.imag ** 2
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    fxn = (xx - cx) / w
    fyn = (yy - cy) / h
    fr = np.sqrt(fxn ** 2 + fyn ** 2)
    fang = np.degrees(np.arctan2(-fyn, fxn))

    def _axis_mask(axis_deg):
        d = np.abs(((fang - axis_deg + 90.0) % 180.0) - 90.0)
        return d <= wedge_deg
    sag = _axis_mask(radial_angle_deg)
    tan = _axis_mask(radial_angle_deg + 90.0)
    bins = np.linspace(0, 0.5, nbins + 1)
    idx = np.digitize(fr.ravel(), bins) - 1
    Pf = P.ravel()
    sagf = sag.ravel()
    tanf = tan.ravel()
    psd_sag = np.full(nbins, np.nan)
    psd_tan = np.full(nbins, np.nan)
    for b in range(nbins):
        m = idx == b
        ms = m & sagf
        mt = m & tanf
        if ms.any():
            psd_sag[b] = Pf[ms].mean()
        if mt.any():
            psd_tan[b] = Pf[mt].mean()
    fcen = 0.5 * (bins[:-1] + bins[1:])
    return fcen, psd_sag, psd_tan


# pad-edge averaged ESF (cross-check P3.1) ----------------------------------- #
HALF, BPP = 8.0, 4.0
TILT_LO, TILT_HI = 1.0, 14.0


def averaged_esf(g, half=HALF, bpp=BPP):
    g = g.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    thr = np.percentile(mag, 99.0)
    H, W = g.shape
    nb = int(round(2 * half * bpp))
    edges_bins = np.linspace(-half, half, nb + 1)
    sums = np.zeros(nb); cnts = np.zeros(nb)
    n_used = 0
    ang = np.degrees(np.arctan2(gy, gx))
    strong = mag > thr
    sel_v = strong & (((np.abs(ang) > TILT_LO) & (np.abs(ang) < TILT_HI))
                      | ((np.abs(np.abs(ang) - 180) > TILT_LO)
                         & (np.abs(np.abs(ang) - 180) < TILT_HI)))
    ys, xs = np.where(sel_v)
    for x, y in zip(xs, ys):
        if x < half + 2 or x > W - half - 2:
            continue
        row = g[y, int(x - half - 1):int(x + half + 2)]
        if row.size < 2 * half:
            continue
        d = np.arange(row.size) - (half + 1)
        v = row.astype(np.float64)
        if gx[y, x] < 0:
            v = v[::-1]; d = -d[::-1]
        idx = np.clip(np.digitize(d, edges_bins) - 1, 0, nb - 1)
        np.add.at(sums, idx, v); np.add.at(cnts, idx, 1.0)
        n_used += 1
    sel_h = strong & ((np.abs(np.abs(ang) - 90) > TILT_LO)
                      & (np.abs(np.abs(ang) - 90) < TILT_HI))
    ys, xs = np.where(sel_h)
    for x, y in zip(xs, ys):
        if y < half + 2 or y > H - half - 2:
            continue
        col = g[int(y - half - 1):int(y + half + 2), x]
        if col.size < 2 * half:
            continue
        d = np.arange(col.size) - (half + 1)
        v = col.astype(np.float64)
        if gy[y, x] < 0:
            v = v[::-1]; d = -d[::-1]
        idx = np.clip(np.digitize(d, edges_bins) - 1, 0, nb - 1)
        np.add.at(sums, idx, v); np.add.at(cnts, idx, 1.0)
        n_used += 1
    good = cnts >= 8
    if good.sum() < 10:
        return None, None, n_used
    centres = 0.5 * (edges_bins[:-1] + edges_bins[1:])
    return centres[good], sums[good] / cnts[good], n_used


def esf_to_mtf(centres, esf):
    if centres is None or len(centres) < 12:
        return None
    step = np.median(np.diff(centres))
    esf = np.asarray(esf, float)
    lo, hi = np.percentile(esf, 5), np.percentile(esf, 95)
    if hi - lo < 1e-6:
        return None
    e = (esf - lo) / (hi - lo)
    lsf = np.gradient(e, centres)
    win = np.hanning(len(lsf))
    F = np.fft.rfft(lsf * win)
    freqs = np.fft.rfftfreq(len(lsf), d=step)
    mtf = np.abs(F)
    m0 = mtf[0]
    if not np.isfinite(m0) or m0 <= 0:
        return None
    mtf = mtf / m0
    return freqs, mtf


# relative deconvolution (cross-check P3.2) ---------------------------------- #
FPX_LO, FPX_HI = 0.06, 0.22


def amp_radial(patch, nbins=48):
    a = patch.astype(np.float64); a = a - a.mean()
    h, w = a.shape
    a = a * _hann2d(h, w)
    F = np.fft.fftshift(np.fft.fft2(a))
    A = np.abs(F)
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    fr = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    bins = np.linspace(0, 0.5, nbins + 1)
    idx = np.digitize(fr.ravel(), bins) - 1
    Af = A.ravel()
    amp = np.full(nbins, np.nan)
    for b in range(nbins):
        m = idx == b
        if m.any():
            amp[b] = Af[m].mean()
    fcen = 0.5 * (bins[:-1] + bins[1:])
    return fcen, amp


# --------------------------------------------------------------------------- #
# extract stage
# --------------------------------------------------------------------------- #
def _new_accum() -> dict:
    """Fresh per-shard row accumulators for the extract/recover patch stage."""
    return {"psd": [], "meta": [], "padedge": [], "psffoc": [], "fieldtag": []}


def _write_extract_shards(out, tag, accum, dropped_rows):
    """Write the five per-patch shard CSVs + the dropped-configs shard for one tag.

    Shared by cmd_extract (tag=``i_N``) and cmd_recover (tag=``recover``); the
    analyse stage pools every ``*_shard_*.csv`` so a ``recover`` tag is folded in
    automatically."""
    pd.DataFrame(accum["psd"]).to_csv(out / f"psd_shard_{tag}.csv", index=False)
    pd.DataFrame(accum["meta"]).to_csv(out / f"meta_shard_{tag}.csv", index=False)
    pd.DataFrame(accum["padedge"]).to_csv(out / f"padedge_shard_{tag}.csv", index=False)
    pd.DataFrame(accum["psffoc"]).to_csv(out / f"psffoc_shard_{tag}.csv", index=False)
    pd.DataFrame(accum["fieldtag"]).to_csv(out / f"fieldtag_shard_{tag}.csv", index=False)
    # dropped_configs.csv: appended (each shard writes its own; analyse pools by glob).
    pd.DataFrame(dropped_rows).to_csv(out / f"dropped_configs_shard_{tag}.csv", index=False)
    print(f"WROTE shard {tag}: {len(accum['psd'])} psd, {len(accum['meta'])} meta, "
          f"{len(accum['padedge'])} padedge, {len(accum['psffoc'])} psffoc, "
          f"{len(accum['fieldtag'])} fieldtag, {len(dropped_rows)} dropped", flush=True)


def extract_config_patches(node, p, M, jpgs, patches, out, accum):
    """Per-config patch extraction: register-independent body shared by the extract
    stage and the recover stage (PASS 2 folds the sibling-prior-recovered configs
    into the SAME psd/meta/padedge/psffoc/fieldtag rows the estimator pools).

    ``p`` is a reg_auto-compatible affine (``register_config`` in extract; the
    ``best["affine"]`` sibling-prior recovery in recover). Rows are appended to the
    ``accum`` lists in place; patch arrays saved under ``out/patches``."""
    cid = MS.human(node); sid = MS.sid(node)
    rmse = p.get("reg_fit_rmse_px", float("nan"))
    psd_rows = accum["psd"]; meta_rows = accum["meta"]; padedge_rows = accum["padedge"]
    psffoc_rows = accum["psffoc"]; fieldtag_rows = accum["fieldtag"]
    cx_frame, cy_frame = reg_auto.DIST_CENTER
    FIELD_FPX = (0.10, 0.15)
    p2_rail_ok = bool(node.p2_rail_ok)
    n_marked = _ap_to_n(node.aperture)
    ccl = 0.5 * (GLOBAL_CL[0] + GLOBAL_CL[1]); crl = 0.5 * (GLOBAL_RL[0] + GLOBAL_RL[1])
    x00, y00 = reg_auto.grid_xy_distorted(ccl, crl, p)
    xu, yu = reg_auto.grid_xy_distorted(ccl + 1.0, crl, p)
    xv, yv = reg_auto.grid_xy_distorted(ccl, crl + 1.0, p)
    px_per_unit = 0.5 * (np.hypot(xu - x00, yu - y00) + np.hypot(xv - x00, yv - y00))
    n_eff = optics.effective_fnumber(n_marked, M)
    ceil_cypx = optics.diffraction_mtf50_sensor_lpmm(n_eff) / 229.9
    print(f"=== {sid} M={M:.3f} rmse={rmse:.1f} px/unit={px_per_unit:.0f} "
          f"p2_rail={'ok' if p2_rail_ok else 'OFF'} ===", flush=True)
    meta_rows.append(dict(config=cid, sid=sid, M=M, rmse=rmse,
                          n_marked=n_marked, n_eff=n_eff, px_per_unit=px_per_unit,
                          lens=node.lens, mag_label=node.mag_label,
                          aperture=node.aperture, date=node.session,
                          p2_rail_ok=p2_rail_ok, camera=node.camera))
    active = []
    for (a, b, a1, b1, plab) in patches:
        corners = [reg_auto.grid_xy_distorted(cc, rr, p)
                   for (cc, rr) in [(a, b), (a, b1), (a1, b), (a1, b1)]]
        xs = [pt[0] for pt in corners]; ys = [pt[1] for pt in corners]
        if (min(xs) < 60 or max(xs) > IMAGE_W - 60
                or min(ys) < 60 or max(ys) > IMAGE_H - 60):
            continue
        active.append((plab, a, b, a1, b1,
                       (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))))
    if not active:
        print("  no in-FOV patches", flush=True)
        return
    curves = scan_all_boxes(jpgs, [x[5] for x in active])
    # P2 through-focus (TIER-GATED): emit per-patch mu/fwhm/coverage_flag ONLY for
    # the rail-coverage tier. Manual-tier configs still get all of P1 (below) but
    # NO psffoc rows -> P2/POC-3/POC-4 degrade to the estimators that read best-focus
    # frame(s) and are robust to a non-constant / unregistered rail step.
    n_psffoc = 0
    nstack = len(jpgs)
    if p2_rail_ok:
        for bi, (plab, a, b, a1, b1, box) in enumerate(active):
            seqs, lvs = curves[bi]
            _, fwhm, mu = X.gaussian_defocus_fwhm(seqs, lvs)
            if np.isfinite(fwhm):
                psffoc_rows.append(dict(
                    config=cid, sid=sid, patch=plab, M=M,
                    n_marked=n_marked, n_eff=n_eff, nstack=nstack,
                    fwhm=fwhm, mu=mu,
                    peak_pos_frac=X.peak_pos_frac(mu, nstack),
                    edge_dist_frames=X.edge_dist_frames(mu, nstack),
                    coverage_flag=X.coverage_flag(mu, fwhm, nstack)))
                n_psffoc += 1
    by_frame = {}
    for bi, (plab, a, b, a1, b1, box) in enumerate(active):
        seqs, lvs = curves[bi]
        if len(seqs) == 0:
            continue
        seq = int(seqs[int(np.argmax(lvs))])
        by_frame.setdefault(seq, []).append((plab, a, b, a1, b1, box))
    per_patch_mtf = []
    ncfg_edges = 0
    for seq, group in by_frame.items():
        chan = decode_sat(jpgs[seq])
        gray = cv2.imread(str(jpgs[seq]), cv2.IMREAD_GRAYSCALE)
        if chan is None:
            continue
        for (plab, a, b, a1, b1, box) in group:
            patch = atlas_rect_to_common_grid(chan, p, a, b, a1, b1,
                                              samples_per_unit=SAMPLES_PER_UNIT)
            if patch is None:
                continue
            np.save(out / "patches" / f"{sid}__{plab}.npy", patch.astype(np.float32))
            f_grid, psd = radial_psd(patch)
            for fg, ps in zip(f_grid, psd):
                if np.isfinite(ps):
                    psd_rows.append(dict(config=cid, sid=sid, patch=plab, M=M,
                                         n_marked=n_marked, f_grid=fg, psd=ps))
            # location-aware field tag (POC-4 substrate).
            pcx, pcy = reg_auto.grid_xy_distorted(0.5 * (a + a1),
                                                  0.5 * (b + b1), p)
            geo = X.field_geometry(pcx, pcy, cx_frame, cy_frame,
                                   IMAGE_W, IMAGE_H, m=M)
            ft = dict(config=cid, sid=sid, patch=plab, M=M,
                      px=float(pcx), py=float(pcy),
                      dist_px=geo["dist_px"], field_height=geo["field_height"],
                      angle_deg=geo["angle_deg"],
                      dist_subject_mm=geo["dist_subject_mm"])
            amp_iso = np.sqrt(np.clip(psd, 1e-30, None))
            fsag, psd_sag, psd_tan = directional_psd(patch, geo["angle_deg"])
            amp_sag = np.sqrt(np.clip(psd_sag, 1e-30, None))
            amp_tan = np.sqrt(np.clip(psd_tan, 1e-30, None))
            for fpx in FIELD_FPX:
                fg_sensor = fpx * px_per_unit / SAMPLES_PER_UNIT

                def _read(fcurve, vcurve):
                    okm = np.isfinite(vcurve)
                    if okm.sum() < 2 or not (fcurve[okm].min() <= fg_sensor
                                             <= fcurve[okm].max()):
                        return float("nan")
                    return float(np.interp(fg_sensor, fcurve[okm], vcurve[okm]))
                ft[f"amp_fpx{fpx}"] = _read(f_grid, amp_iso)
                ft[f"amp_sag_fpx{fpx}"] = _read(fsag, amp_sag)
                ft[f"amp_tan_fpx{fpx}"] = _read(fsag, amp_tan)
            fieldtag_rows.append(ft)
            if gray is not None:
                x0, y0, x1, y1 = box
                crop = gray[y0:y1, x0:x1].astype(np.float32)
                if crop.size and min(crop.shape) >= 40:
                    cen, esf, ne = averaged_esf(crop)
                    ncfg_edges += ne
                    res = esf_to_mtf(cen, esf)
                    if res is not None:
                        per_patch_mtf.append((res[0], res[1], ne))
    if per_patch_mtf:
        common_f = np.linspace(0.0, 0.5, 64)
        stacks = [np.interp(common_f, fr, mt) for fr, mt, _ in per_patch_mtf]
        ws = np.array([ne for *_, ne in per_patch_mtf], float)
        ws = ws / ws.sum()
        mtf_agg = np.average(np.array(stacks), axis=0, weights=ws)
        rec = dict(config=cid, sid=sid, M=M, n_eff=n_eff, ceil_cypx=ceil_cypx,
                   n_edge_samples=ncfg_edges, n_patches=len(per_patch_mtf))
        for fpx in (0.10, 0.15):
            rec[f"mtf_fpx{fpx}"] = float(np.interp(fpx, common_f, mtf_agg))
        padedge_rows.append(rec)
    print(f"  {len(active)} in-FOV patches, {len(by_frame)} focus frames, "
          f"{ncfg_edges} pad edges, {n_psffoc} through-focus fits", flush=True)


def cmd_extract(args):
    subset = Path(args.subset)
    out = Path(args.out)
    nodes = MS.discover_config_nodes(subset)
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        nodes = [c for k, c in enumerate(nodes) if k % n == i]
    out.mkdir(parents=True, exist_ok=True)
    (out / "patches").mkdir(exist_ok=True)
    patches = patch_layout()
    accum = _new_accum()
    dropped_rows = []
    for node in nodes:
        cid = MS.human(node); sid = MS.sid(node)
        sd = node.sweep_dir
        p, M, jpgs = register_config(sd, node)
        if p is None:
            dropped_rows.append(dict(sid=sid, config=cid, session=node.session,
                                     stage="extract", reason="reg_fail"))
            print(f"DROP {sid}: reg fail", flush=True)
            continue
        rmse = p.get("reg_fit_rmse_px", float("nan"))
        ok, reason = reg_guard(M, rmse, pitch_um=camera_pitch_um(node.camera))
        if not ok:
            dropped_rows.append(dict(sid=sid, config=cid, session=node.session,
                                     stage="extract", reason=reason,
                                     M=M, rmse=rmse))
            print(f"DROP {sid}: {reason} (rmse={rmse:.2f})", flush=True)
            continue
        extract_config_patches(node, p, M, jpgs, patches, out, accum)

    tag = (args.shard or "0_1").replace("/", "_")
    _write_extract_shards(out, tag, accum, dropped_rows)


# --------------------------------------------------------------------------- #
# cross-check estimators pooled from the shards
# --------------------------------------------------------------------------- #
def decon_scores(meta, out):
    ppu = dict(zip(meta.sid, meta.px_per_unit))
    files = sorted((out / "patches").glob("*__*.npy"))
    by_cell = {}
    for f in files:
        # sid itself can contain "__" (multi_session ids join abbrev-lens+mag with
        # "__" when mag_label is empty), so split on the LAST separator only.
        sid, cell = f.stem.rsplit("__", 1)
        by_cell.setdefault(cell, []).append((sid, f))
    cache = {}
    edges = []
    for cell, items in by_cell.items():
        cur = {}
        for sid, f in items:
            if (sid, cell) not in cache:
                cache[(sid, cell)] = amp_radial(np.load(f))
            cur[sid] = cache[(sid, cell)]
        sids = [s for s in cur if s in ppu]
        for ia in range(len(sids)):
            for ib in range(ia + 1, len(sids)):
                sa, sb = sids[ia], sids[ib]
                fa, Aa = cur[sa]; fb, Ab = cur[sb]
                fpx = np.linspace(FPX_LO, FPX_HI, 16)
                fga = fpx * ppu[sa] / X.SAMPLES_PER_UNIT
                fgb = fpx * ppu[sb] / X.SAMPLES_PER_UNIT
                if not (fa.min() <= fga.min() and fga.max() <= fa.max()
                        and fb.min() <= fgb.min() and fgb.max() <= fb.max()):
                    continue
                va = np.interp(fga, fa, Aa); vb = np.interp(fgb, fb, Ab)
                m = (va > 0) & (vb > 0)
                if m.sum() < 6:
                    continue
                lr = np.log(va[m] / vb[m])
                xq = fpx[m] ** 2
                w = 1.0 / (1.0 + 10 * fpx[m] ** 2)
                A1 = np.column_stack([np.ones_like(xq), xq])
                coef, *_ = np.linalg.lstsq(A1 * w[:, None], lr * w, rcond=None)
                delta = -coef[1] / (2 * np.pi ** 2)
                edges.append((sa, sb, float(delta), float(m.sum())))
    nodes = sorted({e[0] for e in edges} | {e[1] for e in edges})
    if len(nodes) < 3:
        return {}
    scores = X.chain_solve(edges, nodes)
    return {s: -v for s, v in scores.items()}


def _read_csv_safe(f):
    """pd.read_csv that returns an empty frame for a header-less / empty shard CSV.

    A shard that registered 0 configs writes a size<=1 byte, column-less CSV; pd.read_csv
    then raises EmptyDataError ("No columns to parse from file"). Skip such shards (and a
    missing file) by returning an empty DataFrame instead of crashing the pool.
    """
    try:
        if os.path.getsize(f) <= 1:
            return pd.DataFrame()
    except OSError:
        return pd.DataFrame()
    try:
        return pd.read_csv(f)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _pool_shards(files):
    """Pool a list of ``*_shard_*.csv`` paths, skipping empty / header-less / missing ones.

    Returns a single concatenated DataFrame (row order = sorted file order), or an empty
    DataFrame when every shard is empty. Non-empty shards are concatenated unchanged, so
    behaviour is identical to a plain ``pd.concat([pd.read_csv(f) ...])`` whenever no
    shard is empty. This is the crash-safe replacement for pooling loops that fed
    ``pd.read_csv`` a 0-config shard directly.
    """
    frames = [d for d in (_read_csv_safe(f) for f in sorted(files)) if not d.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def p2_scores(out):
    files = list(out.glob("psffoc_shard_*.csv"))
    frames = [_read_csv_safe(f) for f in files]
    frames = [d for d in frames if not d.empty and "fwhm" in d.columns]
    if not frames:
        return {}, pd.DataFrame()
    tf = pd.concat(frames, ignore_index=True)
    return X.through_focus_scores(tf), tf


# --------------------------------------------------------------------------- #
# POC 3 physical-mm + POC 4 field geometry (per config-node)
# --------------------------------------------------------------------------- #
def build_physical_per_patch(psffoc, nodes_by_sid, eff_lookup, *, log=print):
    """POC-3 per-patch physical mm from the pooled psffoc shards.

    Per sid (one focus sweep): resolve the effective aperture (n_working) via the CSV
    lookup else the directory-name aperture (never analytical); resolve the per-sweep
    step (documented from shots.csv for 2026-05+; DoF-estimated for pre-2026-05); then
    convert every patch's mu/fwhm to mm via :func:`focus_physical.patch_physical_row`.
    Returns a DataFrame with the POC-3 physical columns + step provenance.
    """
    rows = []
    for sid, g in psffoc.groupby("sid"):
        sid = str(sid)
        node = nodes_by_sid.get(sid)
        m = float(g["M"].iloc[0])
        marked_f = float(g["n_marked"].iloc[0])
        # effective aperture: CSV (empirical bellows) -> directory-name aperture.
        n_working = None
        eff_src = "dir_aperture"
        if node is not None and eff_lookup is not None:
            csv_val = eff_lookup.get(node.lens, _f_dir_name(node))
            if csv_val is not None:
                n_working = float(csv_val)
                eff_src = "csv"
        if n_working is None:
            n_working = float(g["n_eff"].iloc[0])  # optics.effective_fnumber fallback
        # documented step ONLY for 2026-05+; else DoF-estimated. Never DoF when documented.
        documented = documented_step_for(node) if node is not None else None
        ok = g[g["coverage_flag"] == "ok"]
        base = ok if len(ok) else g
        sweep_fwhm_frames = float(np.nanmedian(base["fwhm"].to_numpy(float)))
        step = FP.resolve_step(m=m, n_working=n_working, marked_f=marked_f,
                               fwhm_frames=sweep_fwhm_frames,
                               documented_step_mm=documented)
        for r in g.itertuples():
            phys = FP.patch_physical_row(
                mu_frames=float(r.mu), fwhm_frames=float(r.fwhm),
                coverage_flag=str(r.coverage_flag), step=step,
                m=m, n_working=n_working, marked_f=marked_f)
            rows.append(dict(config=r.config, sid=sid, patch=r.patch, M=m,
                             n_marked=marked_f, n_eff=n_working, eff_source=eff_src,
                             nstack=int(r.nstack), mu_frames=float(r.mu),
                             fwhm_frames=float(r.fwhm),
                             peak_pos_frac=float(r.peak_pos_frac),
                             edge_dist_frames=float(r.edge_dist_frames),
                             **phys))
        log(f"  POC3 {sid:36s} M={m:5.3f} N_work={n_working:6.2f} "
            f"step={step.step_mm:.5f}mm ({step.step_source}"
            f"{' LOW-CONF' if step.low_confidence else ''}) eff={eff_src}",
            flush=True)
    return pd.DataFrame(rows)


def build_field_geometry(physical, fieldtag):
    """POC-4 per-config tilt-removed field geometry from POC-3 physical + fieldtag."""
    cx, cy = Z7_CENTRE
    geo_cols = ["config", "sid", "patch", "px", "py", "dist_px",
                "field_height", "angle_deg"]
    ft = fieldtag[[c for c in geo_cols if c in fieldtag.columns]].drop_duplicates(
        subset=["config", "sid", "patch"])
    joined = physical.merge(ft, on=["config", "sid", "patch"], how="left")
    rows = []
    for config, g in joined.groupby("config"):
        m = float(g["M"].iloc[0])
        low_conf = bool(g["step_low_confidence"].iloc[0]) if "step_low_confidence" in g else False
        clean = g[(g["coverage_flag"] == "ok")
                  & (~g["fwhm_imputed"].astype(bool))
                  & g["px"].notna()]
        n_total = int(len(g))
        base = dict(config=config, sid=str(g["sid"].iloc[0]), M=m,
                    step_low_confidence=low_conf, n_used=int(len(clean)),
                    n_excluded=n_total - int(len(clean)), n_total=n_total)
        if len(clean) < 4:
            base["note"] = "too_few_clean_patches"
            rows.append(base)
            continue
        fwhm_med = float(clean["fwhm_mm"].median())
        res = analyse_field_geometry(
            clean["px"].to_numpy(float), clean["py"].to_numpy(float),
            clean["mu_mm"].to_numpy(float), fwhm_med,
            cx=cx, cy=cy, half_diag_px=Z7_HALF_DIAG_PX)
        c, v, a = res.curvature, res.vertex, res.astigmatism
        base.update(dict(
            fwhm_mm_median=fwhm_med, sag_dof=c.sag_dof, sag_um=c.sag_um,
            sag_sign=("corners_farther" if c.sag_um > 0 else "corners_nearer"),
            curv_radius_mm=c.radius_mm, curv_k_mm_per_px2=c.k_mm_per_px2,
            rms_residual_um=c.rms_residual_um, fh_max=c.fh_max,
            vertex_estimable=v.estimable, vertex_offset_px=v.offset_px,
            vertex_offset_field_frac=v.offset_field_frac,
            vertex_dx0_px=v.dx0_px, vertex_dy0_px=v.dy0_px, vertex_note=v.note,
            astig_available=a.available, astig_note=a.note, note=""))
        rows.append(base)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# analyse stage
# --------------------------------------------------------------------------- #
def _rank_and_report(psd, meta, f_px, *, n_boot, label):
    """Run the estimator core on a (psd, meta) slice; print gates + table; return Ranking."""
    print("\n" + "=" * 72 + f"\n{label} @ f_px={f_px}\n" + "=" * 72)
    try:
        ranking = X.rank_configs(psd, meta, f_px, n_boot=n_boot, strict=False)
    except ValueError as e:
        print(f"  cannot rank: {e}")
        return None
    for msg in ranking.gate.messages():
        print("  [GATE] " + msg)
    print(ranking.table.round(4).to_string(index=False))
    return ranking


def cmd_analyse(args):
    out = Path(args.out)
    subset = Path(args.subset)
    nodes = MS.discover_config_nodes(subset)
    nodes_by_sid = {MS.sid(n): n for n in nodes}
    f_px = args.fpx

    # Pool shards crash-safely: a shard that registered 0 configs writes a header-less
    # 1-byte CSV that would make a bare pd.read_csv raise EmptyDataError.
    psd = _pool_shards(out.glob("psd_shard_*.csv"))
    meta = _pool_shards(out.glob("meta_shard_*.csv")).drop_duplicates("config")

    # dropped log (from extract) — pool + rewrite the canonical dropped_configs.csv.
    # Shards with zero drops write an empty (header-less) CSV, so read defensively.
    drop_files = list(out.glob("dropped_configs_shard_*.csv"))
    dropped = [_read_csv_safe(f) for f in drop_files]
    dropped = [d for d in dropped if not d.empty]
    dropped = pd.concat(dropped, ignore_index=True) if dropped else pd.DataFrame(
        columns=["sid", "config", "session", "stage", "reason"])
    # A config the recover PASS-2 folded back in is present in `meta` now, so its
    # stale extract-stage drop row is no longer true — drop it from the log.
    if not dropped.empty and "sid" in dropped.columns and "sid" in meta.columns:
        dropped = dropped[~dropped["sid"].isin(set(meta["sid"]))].reset_index(drop=True)

    # ---- ruling #2: M>1.10 low-confidence (excluded from headline ranking) -------- #
    m_by_sid = dict(zip(meta.sid, meta.M))
    meta["step_low_confidence"] = meta["M"] > FP.M_EXTRAPOLATION_THRESHOLD
    low_conf_sids = set(meta[meta["step_low_confidence"]].sid)
    if low_conf_sids:
        print(f"M>1.10 LOW-CONFIDENCE (excluded from headline ranking/geometry, "
              f"surfaced separately): {len(low_conf_sids)} configs")

    # ---- config-level focus-coverage drop (POC-1 coverage_config_ok) -------------- #
    # Pool the psffoc per-patch flags; a config retaining < COVERAGE_MIN_OK_PATCHES ok
    # patches is dropped from ranking. Manual-tier configs have no psffoc (tier gate),
    # so this bites only rail-coverage configs — logged, never silent.
    p2, tf = p2_scores(out)
    coverage_dropped = []
    if not tf.empty and "coverage_flag" in tf.columns:
        for sid, g in tf.groupby("sid"):
            if not X.coverage_config_ok(list(g["coverage_flag"])):
                coverage_dropped.append(str(sid))
        if coverage_dropped:
            print("DROP (POC-1 focus coverage too thin, < "
                  f"{X.COVERAGE_MIN_OK_PATCHES} ok patches): "
                  + ", ".join(sorted(coverage_dropped)))
            for s in coverage_dropped:
                node = nodes_by_sid.get(s)
                dropped = pd.concat([dropped, pd.DataFrame([dict(
                    sid=s, config=(MS.human(node) if node else ""),
                    session=(node.session if node else ""),
                    stage="analyse", reason="coverage_config_ok_fail")])],
                    ignore_index=True)
    dropped.to_csv(out / "dropped_configs.csv", index=False)

    # sids that stay in the HEADLINE ranking: not low-conf, not coverage-dropped.
    excluded = low_conf_sids | set(coverage_dropped)
    keep = set(meta.sid) - excluded
    hmeta = meta[meta.sid.isin(keep)].reset_index(drop=True)
    hpsd = psd[psd.sid.isin(keep)].reset_index(drop=True)
    print(f"loaded {psd.sid.nunique()} configs, {psd.patch.nunique()} patches; "
          f"{len(keep)} in headline pool, {len(excluded)} excluded")

    # ---- f_px window sweep (gate transparency) ----------------------------------- #
    print("\n" + "=" * 72 + "\nf_px window sweep (primary estimator P1)\n" + "=" * 72)
    sweep_rows = []
    for fp in (0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25):
        try:
            gate, _, _ = X.gate_self_check(hpsd, hmeta, fp)
        except ValueError as e:
            print(f"f_px={fp}: {e}")
            continue
        sweep_rows.append(dict(f_px=fp, n_nodes=gate.n_nodes, n_edges=gate.n_edges,
                               ncomp=gate.n_components, resid=round(gate.resid_rms, 3),
                               corr_M=round(gate.corr_M, 3),
                               in_window=gate.in_window, passed=gate.passed))
        print(f"f_px={fp:.2f}: nodes={gate.n_nodes:2d} edges={gate.n_edges:5d} "
              f"comp={gate.n_components} resid={gate.resid_rms:.3f} "
              f"corr(M,score)={gate.corr_M:+.3f} "
              f"{'PASS' if gate.passed else 'OUTSIDE-WINDOW/FAIL'}")
    pd.DataFrame(sweep_rows).to_csv(out / "fpx_sweep.csv", index=False)

    # ---- ruling #4: PRIMARY headline = rail-coverage tier only -------------------- #
    rail_sids = set(hmeta[hmeta["p2_rail_ok"].astype(bool)].sid)
    rmeta = hmeta[hmeta.sid.isin(rail_sids)].reset_index(drop=True)
    rpsd = hpsd[hpsd.sid.isin(rail_sids)].reset_index(drop=True)
    headline = None
    if len(rail_sids) >= 3:
        headline = _rank_and_report(
            rpsd, rmeta, f_px, n_boot=args.n_boot,
            label=f"HEADLINE rail-coverage-tier ranking ({len(rail_sids)} configs)")
    else:
        print(f"\n[headline] only {len(rail_sids)} rail-coverage configs in pool — "
              "too few for a standalone headline ranking")

    # ---- secondary / degraded views ---------------------------------------------- #
    full_ranking = _rank_and_report(
        hpsd, hmeta, f_px, n_boot=args.n_boot,
        label="SECONDARY full-pool ranking (rail + manual tiers, DEGRADED)")

    lowconf_ranking = None
    if low_conf_sids:
        lcmeta = meta[meta.sid.isin(low_conf_sids)].reset_index(drop=True)
        lcpsd = psd[psd.sid.isin(low_conf_sids)].reset_index(drop=True)
        lowconf_ranking = _rank_and_report(
            lcpsd, lcmeta, f_px, n_boot=max(40, args.n_boot // 3),
            label=f"LOW-CONFIDENCE M>1.10 view ({len(low_conf_sids)} configs; NOT headline)")

    # which ranking is the reported primary depends on --tier.
    primary = headline if (args.tier == "rail-coverage" and headline is not None) \
        else (full_ranking if full_ranking is not None else headline)

    # ---- corroborators + consensus (on the primary pool) -------------------------- #
    pool_meta = rmeta if (args.tier == "rail-coverage") else hmeta
    pool_psd = rpsd if (args.tier == "rail-coverage") else hpsd
    series = {}
    for fp in (0.10, 0.12, 0.15):
        try:
            _, sc, _ = X.gate_self_check(pool_psd, pool_meta, fp)
            series[f"P1_fpx{fp}"] = sc
        except ValueError:
            pass
    pe_files = list(out.glob("padedge_shard_*.csv"))
    pe_frames = [d for d in (_read_csv_safe(f) for f in pe_files) if not d.empty]
    if pe_frames:
        ped = pd.concat(pe_frames, ignore_index=True)
        if "mtf_fpx0.1" in ped:
            ped = ped[ped.sid.isin(set(pool_meta.sid))].dropna(subset=["mtf_fpx0.1"])
            series["P31_padedge"] = dict(zip(ped.sid, ped["mtf_fpx0.1"]))
    dec = decon_scores(pool_meta, out)
    if dec:
        series["P32_decon"] = dec
    if p2:
        p2_pool = {s: v for s, v in p2.items() if s in set(pool_meta.sid)}
        if p2_pool:
            series["P2_psffoc"] = p2_pool
            n_eff_by_sid = dict(zip(pool_meta.sid, pool_meta.n_eff))
            corr_neff = X.p2_deconfound_corr(p2_pool, n_eff_by_sid)
            print("\n" + "=" * 72 + "\nP2 through-focus corroborator\n" + "=" * 72)
            print(f"de-confound self-check: corr(N_eff, P2)={corr_neff:+.3f} "
                  f"({'OK' if X.p2_deconfound_ok(corr_neff) else 'FAIL'})")

    if series:
        print("\n" + "=" * 72 + "\nCross-estimator agreement (Spearman)\n" + "=" * 72)
        mat = X.cross_estimator_agreement(series)
        print(mat.to_string())
        mat.to_csv(out / "cross_estimator_agreement.csv")
        members = [k for k in ("P1_fpx0.1", "P1_fpx0.12", "P31_padedge", "P32_decon",
                               "P2_psffoc") if k in series]
        cons = X.consensus_ranking(series, members)
        print("\n" + "=" * 72 + "\nConsensus ranking\n" + "=" * 72)
        print(cons[["consensus_rank", "sid", "mean_rank", "rank_std",
                    "n_estimators"]].to_string(index=False))

    # ---- POC 3 physical-mm + POC 4 field geometry --------------------------------- #
    eff_lookup = EffectiveApertureLookup.from_csvs(
        [p for p in EFF_AP_CSVS if p.exists()])
    fieldtag_files = list(out.glob("fieldtag_shard_*.csv"))
    ft_frames = [d for d in (_read_csv_safe(f) for f in fieldtag_files) if not d.empty]
    fieldtag = pd.concat(ft_frames, ignore_index=True) if ft_frames else pd.DataFrame()
    if not tf.empty:
        print("\n" + "=" * 72 + "\nPOC 3 per-patch physical mm\n" + "=" * 72)
        physical = build_physical_per_patch(tf, nodes_by_sid, eff_lookup)
        physical.to_csv(out / "physical_per_patch.csv", index=False)
        print(f"WROTE physical_per_patch.csv ({len(physical)} patch rows, "
              f"{physical.sid.nunique()} configs)")
        # POC 4 field geometry on the NON-low-confidence configs only (ruling #2).
        if not fieldtag.empty:
            phys_headline = physical[~physical.sid.isin(low_conf_sids)]
            fg = build_field_geometry(phys_headline, fieldtag)
            fg.to_csv(out / "field_geometry_per_config.csv", index=False)
            print(f"WROTE field_geometry_per_config.csv ({len(fg)} configs)")
    else:
        print("\n[POC3/POC4] no psffoc rows (no rail-coverage configs in pool) — "
              "physical/field-geometry CSVs not produced")

    # ---- session summary (ruling #4) ---------------------------------------------- #
    ranked_sids = set(primary.table.sid) if primary is not None else set()
    rk = {s: i + 1 for i, s in enumerate(primary.table.sid)} if primary is not None else {}
    srows = []
    for date, g in meta.groupby("date"):
        sids = [s for s in g.sid if s in ranked_sids]
        srows.append(dict(
            session=date,
            tier=("rail-coverage" if bool(g.p2_rail_ok.iloc[0]) else "manual"),
            n_configs=int(len(g)),
            n_ranked=len(sids),
            best_rank=min((rk[s] for s in sids), default=None),
            worst_rank=max((rk[s] for s in sids), default=None)))
    pd.DataFrame(srows).to_csv(out / "session_summary.csv", index=False)

    # ---- write the primary ranking CSV (self-describing) -------------------------- #
    if primary is not None:
        ann = primary.table.merge(
            meta[["sid", "date", "p2_rail_ok", "step_low_confidence"]],
            on="sid", how="left")
        with (out / "cross_m_relative_mtf_ranking.csv").open("w", newline="") as fh:
            fh.write(X.caveats_header(primary.f_px, comment="# ") + "\n")
            ann.round(4).to_csv(fh, index=False)
        print(f"\nWROTE {out / 'cross_m_relative_mtf_ranking.csv'} "
              f"(primary tier={args.tier}), session_summary.csv, dropped_configs.csv")


# --------------------------------------------------------------------------- #
# PASS 2: sibling-prior recovery + class-A family-consistency audit
# --------------------------------------------------------------------------- #
def family_key(node):
    """Sibling-family key: (lens, session, focal, mag_label).

    NOT lens alone — a true prior is a SAME-framing / SAME-M sibling, so a zoom at a
    different focal or a config at a different marked mag is a different family (e.g.
    24-120@120mm vs 24-120@50mm). The aperture is intentionally EXCLUDED (siblings differ
    only in aperture). Values are normalised to strings so the key is hashable/stable.
    """
    return (
        (getattr(node, "lens", "") or "").strip(),
        (getattr(node, "session", "") or "").strip(),
        (getattr(node, "focal", "") or "").strip(),
        (getattr(node, "mag_label", "") or "").strip(),
    )


def _register_full(sweep_dir, node):
    """Register a config and return its FULL affine prior record (theta, scale, x0/y0,
    rmse, M, frame) or None. Used to reconstruct a sibling prior from a clean pass-1
    config (the pooled meta CSV keeps only M/rmse, not the affine)."""
    p, M, jpgs = register_config(sweep_dir, node)
    if p is None:
        return None
    return dict(theta=float(p["theta_deg"]), scale=float(p["scale"]),
                x0_img=float(p["x0_img"]), y0_img=float(p["y0_img"]), theta_deg=float(p["theta_deg"]),
                rmse=float(p.get("reg_fit_rmse_px", float("nan"))), M=float(M),
                frame=None, jpgs=jpgs, affine=p)


def _sibling_sharp_frame(prior_node):
    """Return the sibling frame that best registers (for class-B phase correlation)."""
    jpgs = sorted(prior_node.sweep_dir.glob("*.jpg")) + sorted(prior_node.sweep_dir.glob("*.JPG"))
    if not jpgs:
        return None
    ranked = spr.rank_frames(jpgs, k=1)
    return str(ranked[0]) if ranked else None


def build_family_priors(nodes, clean_sids, dropped_sids, flagged_sids):
    """Re-register the best clean sibling per family that has a config needing recovery.

    Only families that contain a DROPPED or AUDIT-FLAGGED config are processed (the 305
    clean regs are otherwise untouched). For each such family, pick the clean sibling
    NEAREST in nominal-M to the target (see :func:`spr.resolve_sibling_prior`) and re-fit
    its full affine as the prior. Returns ``{family_key: {"affine": rec, "node": node,
    "sharp_frame": path, "sid": sid}}`` and a list of families with NO clean sibling.
    """
    by_fam = {}
    for node in nodes:
        by_fam.setdefault(family_key(node), []).append(node)
    need = set()
    for node in nodes:
        sid = MS.sid(node)
        if sid in dropped_sids or sid in flagged_sids:
            need.add(family_key(node))
    priors = {}
    no_sibling = []
    for fam in sorted(need):
        members = by_fam.get(fam, [])
        # clean siblings in this family with a registered pass-1 reg
        clean_members = [(MS.sid(n), n) for n in members if MS.sid(n) in clean_sids]
        if not clean_members:
            no_sibling.append(fam)
            continue
        # rank clean siblings by lowest aperture-index proxy (sharpest tends to be f/8-16);
        # resolve_sibling_prior handles nearest-M, but we need the affine, so re-register
        # candidates cheapest-first (prefer higher f-number = sharper, more reliable).
        def _fnum(n):
            v = _ap_to_n(n.aperture)
            return v if v is not None else 0.0
        clean_members.sort(key=lambda sn: -_fnum(sn[1]))
        chosen = None
        for sid, n in clean_members:
            rec = _register_full(n.sweep_dir, n)
            if rec is not None:
                chosen = (sid, n, rec)
                break
        if chosen is None:
            no_sibling.append(fam)
            continue
        sid, n, rec = chosen
        priors[fam] = dict(affine=rec["affine"], node=n, sid=sid,
                           theta=rec["theta"], scale=rec["scale"],
                           x0_img=rec["x0_img"], y0_img=rec["y0_img"],
                           theta_deg=rec["theta_deg"], M=rec["M"], rmse=rec["rmse"],
                           sharp_frame=_sibling_sharp_frame(n))
    return priors, no_sibling


def cmd_relmtf_recover(args):
    """PASS 2 recovery: re-register pass-1 reg failures via same-family sibling priors,
    and audit the pass-1 clean regs for texture-mislock (class-A) inconsistency.

    Reads the pass-1 output dir (``--in``, defaults to ``--out``): pools ``meta_shard_*``
    (clean regs) + ``dropped_configs*`` (failures). Builds a per-family sharp-aperture
    prior, then for each dropped config runs the combined class-A/class-B recovery, taking
    the min-rmse of {tilt-gated, matched-filter} and applying the SAME reg_guard +
    select_registration plausibility as pass 1. Recovered configs are FOLDED IN via the
    shared :func:`extract_config_patches` and written as ``recover``-tagged per-patch
    shards (``{psd,meta,padedge,psffoc,fieldtag,dropped_configs}_shard_recover.csv``) so
    analyse pools them into the ranking/physical/geometry outputs alongside pass 1;
    pass-1 shards are NEVER rewritten. The audit is written to ``reg_family_audit.csv``.
    """
    subset = Path(args.subset)
    src = Path(getattr(args, "in_dir", None) or args.out)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "patches").mkdir(exist_ok=True)
    nodes = MS.discover_config_nodes(subset)
    by_sid = {MS.sid(n): n for n in nodes}

    # ---- pool pass-1 clean regs + dropped ----------------------------------------- #
    meta = _pool_shards(src.glob("meta_shard_*.csv"))
    if meta.empty:
        print(f"no pass-1 meta shards under {src}; nothing to recover")
        return
    dropped = _pool_shards(src.glob("dropped_configs_shard_*.csv"))
    if dropped.empty and (src / "dropped_configs.csv").exists():
        dropped = _read_csv_safe(src / "dropped_configs.csv")
    clean_sids = set(meta["sid"].astype(str))
    # recovery targets = configs dropped at the EXTRACT stage for a registration reason.
    drop_targets = []
    if not dropped.empty:
        d = dropped[dropped["stage"].astype(str) == "extract"] if "stage" in dropped else dropped
        drop_targets = sorted(set(d["sid"].astype(str)) - clean_sids)

    # ---- class-A family-consistency audit on the pass-1 CLEAN regs ---------------- #
    # meta keeps M but not theta; reconstruct theta per clean reg only where cheap is not
    # feasible for all 305, so the audit uses M-vs-family and (when available) theta from
    # re-registration of flagged candidates. To keep the audit cheap + deterministic, we
    # audit on M alone here (theta-based flagging additionally applies inside
    # spr.audit_family_consistency when theta is present).
    clean_regs = []
    for _, row in meta.iterrows():
        sid = str(row["sid"])
        node = by_sid.get(sid)
        fam = family_key(node) if node is not None else (str(row.get("lens", "")),
                                                         str(row.get("date", "")), "", str(row.get("mag_label", "")))
        clean_regs.append(dict(sid=sid, family=fam, M=float(row["M"]),
                               rmse=float(row["rmse"]) if np.isfinite(row["rmse"]) else float("nan"),
                               theta=None,  # not stored in meta; M-based audit
                               nominal_M=nominal_M_for(node) if node is not None else float("nan")))
    audit = spr.audit_family_consistency(clean_regs, m_frac_tol=0.15)
    flagged_sids = {a["sid"] for a in audit if a["flagged"]}
    pd.DataFrame(audit).to_csv(out / "reg_family_audit.csv", index=False)
    n_flagged = len(flagged_sids)
    print(f"AUDIT: {len(clean_regs)} clean regs, {n_flagged} flagged "
          f"(M inconsistent with family median by >15%)", flush=True)
    for a in audit:
        if a["flagged"]:
            print(f"  FLAG {a['sid']}: {a['flag_reason']}", flush=True)

    # ---- build sibling priors for the families needing recovery ------------------- #
    priors, no_sibling = build_family_priors(nodes, clean_sids, set(drop_targets), flagged_sids)
    if no_sibling:
        print(f"NO-SIBLING families (cannot recover — sharp aperture also failed): "
              f"{len(no_sibling)}", flush=True)
        for fam in no_sibling:
            print(f"  {fam}", flush=True)

    # ---- recover each dropped target ---------------------------------------------- #
    rec_accum = _new_accum()
    rec_dropped_rows, recover_log = [], []
    patches = patch_layout()
    for sid in drop_targets:
        node = by_sid.get(sid)
        if node is None:
            continue
        fam = family_key(node)
        prior = priors.get(fam)
        cid = MS.human(node)
        if prior is None:
            rec_dropped_rows.append(dict(sid=sid, config=cid, session=node.session,
                                         stage="recover", reason="no_clean_sibling"))
            recover_log.append(dict(sid=sid, recovered=False, reason="no_clean_sibling"))
            print(f"RECOVER {sid}: NO SIBLING", flush=True)
            continue
        jpgs = sorted(node.sweep_dir.glob("*.jpg")) + sorted(node.sweep_dir.glob("*.JPG"))
        prior_rec = dict(theta=prior["theta"], theta_deg=prior["theta"],
                         scale=prior["scale"],
                         x0_img=prior["x0_img"], y0_img=prior["y0_img"])
        try:
            best = spr.recover_config(jpgs, prior_rec, prior["sharp_frame"])
        except Exception as e:
            best = None
            print(f"RECOVER {sid}: exception {e!r}", flush=True)
        if best is None:
            rec_dropped_rows.append(dict(sid=sid, config=cid, session=node.session,
                                         stage="recover", reason="reg_fail"))
            recover_log.append(dict(sid=sid, recovered=False, reason="reg_fail",
                                    family_prior_M=prior["M"]))
            print(f"RECOVER {sid}: FAILED (both fixes)", flush=True)
            continue
        M = best["M"]
        rmse = best["rmse"]
        # SAME plausibility as pass 1: select_registration band + reg_guard object ceiling.
        nomM = nominal_M_for(node)
        if select_registration([dict(M=M, rmse=rmse)], nomM) is None:
            rec_dropped_rows.append(dict(sid=sid, config=cid, session=node.session,
                                         stage="recover", reason="reg_implausible_M", M=M, rmse=rmse))
            recover_log.append(dict(sid=sid, recovered=False, reason="reg_implausible_M",
                                    M=M, rmse=rmse, fix=best["fix"], family_prior_M=prior["M"]))
            print(f"RECOVER {sid}: implausible M={M:.3f} (fix {best['fix']})", flush=True)
            continue
        ok, reason = reg_guard(M, rmse, pitch_um=camera_pitch_um(node.camera))
        if not ok:
            rec_dropped_rows.append(dict(sid=sid, config=cid, session=node.session,
                                         stage="recover", reason=reason, M=M, rmse=rmse))
            recover_log.append(dict(sid=sid, recovered=False, reason=reason,
                                    M=M, rmse=rmse, fix=best["fix"], family_prior_M=prior["M"]))
            print(f"RECOVER {sid}: {reason} (fix {best['fix']})", flush=True)
            continue
        # FOLD the recovered config into the SAME per-patch rows the estimator pools
        # (PASS-2 fold): the recovered sibling-prior affine is reg_auto-compatible, so
        # run the shared extraction and tag the shards `recover` — analyse's
        # `*_shard_*.csv` globs pick them up. `reg_fit_rmse_px` carries the recovery
        # residual into meta (the affine stores it as `rmse_px`).
        p = best["affine"]
        p["reg_fit_rmse_px"] = rmse
        extract_config_patches(node, p, M, jpgs, patches, out, rec_accum)
        dM = abs(M - prior["M"])
        recover_log.append(dict(sid=sid, recovered=True, fix=best["fix"], M=M, rmse=rmse,
                                n_int=best["n_int"], family_prior_M=prior["M"], dM_vs_prior=dM))
        print(f"RECOVER {sid}: OK fix={best['fix']} M={M:.3f} "
              f"(prior {prior['M']:.3f}, dM={dM:.3f}) rmse={rmse:.2f}px n_int={best['n_int']}", flush=True)

    # Write the recovered configs as `recover`-tagged per-patch shards (meta + psd +
    # psffoc + fieldtag + padedge + dropped) so relmtf-analyse folds them into the
    # ranking / physical / geometry outputs — not meta-only as before.
    _write_extract_shards(out, "recover", rec_accum, rec_dropped_rows)
    pd.DataFrame(recover_log).to_csv(out / "recover_log.csv", index=False)
    print(f"\nWROTE recover-tagged shards ({len(rec_accum['meta'])} recovered), "
          f"dropped_configs_shard_recover.csv ({len(rec_dropped_rows)}), "
          f"recover_log.csv, reg_family_audit.csv", flush=True)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _io(p):
        p.add_argument("--subset", required=True, help="frozen multi-session subset CSV")
        p.add_argument("--out", required=True, help="output dir for shards + analysis")

    pe = sub.add_parser("extract", help="register + resample + PSD/pad-edge/psffoc/fieldtag (sharded)")
    pe.add_argument("--shard", help="i/N shard selector")
    _io(pe)
    pe.set_defaults(func=cmd_extract)

    pa = sub.add_parser("analyse", help="pool shards; rank + POC 2/3/4; write outputs")
    pa.add_argument("--fpx", type=float, default=X.FPX_DEFAULT,
                    help=f"sensor frequency cy/px (window {X.FPX_WINDOW}); default "
                         f"{X.FPX_DEFAULT}")
    pa.add_argument("--n-boot", dest="n_boot", type=int, default=120)
    pa.add_argument("--tier", choices=("rail-coverage", "all"), default="rail-coverage",
                    help="which pool is the PRIMARY reported ranking (default: "
                         "rail-coverage headline)")
    _io(pa)
    pa.set_defaults(func=cmd_analyse)

    pr = sub.add_parser("relmtf-recover",
                        help="PASS 2: sibling-prior recovery of reg failures + class-A "
                             "family-consistency audit (does NOT touch pass-1 clean regs)")
    pr.add_argument("--in", dest="in_dir",
                    help="pass-1 output dir to read meta/dropped shards from "
                         "(default: --out)")
    _io(pr)
    pr.set_defaults(func=cmd_relmtf_recover)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
