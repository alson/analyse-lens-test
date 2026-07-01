"""POC 3 — physical, cross-sweep-comparable through-focus quantities.

This is the refinement layer that turns POC 1's per-patch through-focus fits
(centre ``mu`` and ``fwhm`` in FRAMES, plus a POC-1 ``coverage_flag``) into
PHYSICAL axial quantities in millimetres, so downstream geometry (POC 4:
decentering / field curvature from where each patch's best focus lands) can run
on the manual-tier sweeps that carry NO documented rail step.

What this module adds
---------------------
Pure, unit-tested numerics only (numpy; no IO, no image decode). The driver
``scripts/poc_refine_fwhm.py`` wires these to the POC-1 ``psffoc_shard_*.csv``
shards and the POC-2 step calibration.

Per sweep (one config = one focus stack) we resolve a single ``step_mm``:

* ``documented`` — the median diff of ``rail_position_mm`` in the session's
  ``shots.csv`` (the 2026-05 newer-rig sweeps record it). EXACT.
* ``dof_estimated`` — POC 2's DoF inversion ``step_mm = k · predictor / FWHM_frames``
  with the validated ``k = 0.04255`` and ``predictor = N_working·(1+M)/M²``
  (form ``neff_1pm_over_m2``). Used for the pre-2026-05 manual sweeps.

Per patch we then emit (see :func:`patch_physical_row`):

* ``mu_mm``    = ``mu_frames · step_mm``  — best-focus AXIAL position (mm). NOTE
  the POSITION is independent of the DoF model — it is the Gaussian fit centroid,
  so ``mu_mm``'s accuracy is purely the ``step_mm`` accuracy.
* ``fwhm_mm``  = ``fwhm_frames · step_mm`` — physical depth-of-focus width (mm).
* ``coverage_flag`` — carried through from POC 1.
* a fit-quality / imputation flag (see :func:`fwhm_quality`).

CRITICAL — non-circularity
--------------------------
The DoF ``step_mm`` is derived FROM the sweep's through-focus ``FWHM_frames``.
So ``fwhm_mm = FWHM_frames · (k·pred / FWHM_frames) = k·pred`` IDENTICALLY for a
``dof_estimated`` sweep — you must NOT "validate" ``fwhm_mm`` against the DoF
model on those sweeps (it is a tautology). The DoF FWHM is therefore used only as
a ROBUSTNESS PRIOR / SANITY BOUND on ``documented``-step sweeps and on the
truncated patches (see the imputation rule below). The two clean validations live
in the driver: (1) on 2026-05 documented sweeps, estimated-step vs documented-step
discrepancy; (2) internal consistency of the across-field ``mu_mm`` spread vs the
per-patch ``mu`` fit noise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from tile_sharpness.optics import object_dof_predictor

# --------------------------------------------------------------------------- #
# POC 2 calibration constants (the validated winner — see poc_dof_step_size_REPORT)
# --------------------------------------------------------------------------- #

#: Validated DoF predictor form: object-space FWHM(mm) = k · N_working·(1+M)/M².
DOF_FORM = "neff_1pm_over_m2"

#: Validated through-origin calibration constant (R²=0.871; LOO median ratio 1.05).
DOF_K = 0.04255

#: A sweep at M above this is OUTSIDE the POC-2 calibration M-clusters (which top out
#: at the ~1.0 cluster) by more than measured-M noise, so its DoF-estimated step is an
#: EXTRAPOLATION of the weakly-identified M-form and is flagged low-confidence. The
#: 1.10 value puts a ~10% tolerance above nominal 1:1 so that sweeps whose MEASURED
#: magnification scatters just over 1.0 (e.g. 1.00–1.05, still the top calibration
#: cluster) are NOT flagged, while the genuine >1 configs (1.7:1, 2:1, and the +diopter
#: ~1.16) are. See :func:`m_extrapolation_sensitivity`.
M_EXTRAPOLATION_THRESHOLD = 1.10

#: Step-source tags.
STEP_SOURCES = ("documented", "dof_estimated")

# --------------------------------------------------------------------------- #
# FWHM-quality / imputation flags
# --------------------------------------------------------------------------- #
#
# Tie the DoF expectation to POC-1 coverage. The DoF model predicts the
# OBJECT-space FWHM in mm: ``fwhm_dof_mm = k · predictor``. Compare it to the
# MEASURED ``fwhm_mm = fwhm_frames · step_mm``:
#
#   * coverage_flag == "fwhm_truncated": the half-max width was clipped by the
#     stack edge, so the MEASURED FWHM is an UNDER-estimate. We flag it
#     ``fwhm_imputed`` and (optionally) replace the value with the DoF expectation
#     ``fwhm_dof_mm`` (clearly labelled) so POC 4 has a usable width. The mu
#     POSITION is kept as measured (the centroid is still inside the stack).
#   * |log(measured / dof)| > LOG_DISAGREE  (i.e. measured is more than
#     ``exp(LOG_DISAGREE)``× off the DoF expectation, in either direction) AND the
#     patch is otherwise ok: flag ``fwhm_suspect`` — the fit disagrees with the
#     physics by a large factor (degenerate fit, double-peak, contamination). We do
#     NOT impute here; we surface it for review.
#   * else: ``ok``.
#
# Rationale for the threshold: POC 2's per-sweep DoF step is itself good to ~±15-30%
# (LOO IQR), and a single patch's FWHM legitimately varies across the field by a
# similar amount, so a factor of ~2 (|log| > 0.69) is a generous "this is not the
# same physical quantity" gate that catches blown-up degenerate fits without
# flagging honest field variation. On a ``dof_estimated`` sweep the ``ok`` patches
# satisfy this by construction (no information), so the suspect test is only
# MEANINGFUL on ``documented``-step sweeps — the driver records that.

FWHM_QUALITY_FLAGS = ("ok", "fwhm_imputed", "fwhm_suspect")

#: |log(measured/DoF)| above this flags a patch FWHM as suspect (factor ≈ 2.0).
FWHM_LOG_DISAGREE = math.log(2.0)


# --------------------------------------------------------------------------- #
# step resolution
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StepResult:
    """Resolved per-sweep rail step (mm/frame) + provenance + confidence."""

    step_mm: float
    step_source: str          # one of STEP_SOURCES
    k: float                  # the DoF k used (NaN for documented)
    predictor: float          # the DoF predictor value (NaN for documented)
    m: float
    low_confidence: bool      # True iff dof_estimated AND M > extrapolation threshold
    note: str = ""


def dof_step_mm(fwhm_frames: float, m: float, n_working: float,
                marked_f: float, *, k: float = DOF_K, form: str = DOF_FORM
                ) -> tuple[float, float]:
    """DoF-inverted rail step (mm/frame) and the predictor value.

    ``step_mm = k · predictor(N_working, M) / FWHM_frames`` — the POC-2 inversion.
    Returns ``(step_mm, predictor)``; ``step_mm`` is NaN if inputs are unusable.
    """
    if not (np.isfinite(fwhm_frames) and fwhm_frames > 0):
        return float("nan"), float("nan")
    pred = object_dof_predictor(marked_f, m, form=form, n_working=n_working)
    return k * pred / fwhm_frames, pred


def resolve_step(*, m: float, n_working: float, marked_f: float,
                 fwhm_frames: float, documented_step_mm: float | None = None,
                 k: float = DOF_K, form: str = DOF_FORM) -> StepResult:
    """Resolve the per-sweep ``step_mm`` and its source.

    Priority: a finite, positive ``documented_step_mm`` wins (source
    ``documented``); otherwise fall back to the DoF inversion (source
    ``dof_estimated``). A ``dof_estimated`` step at ``M > M_EXTRAPOLATION_THRESHOLD``
    is flagged ``low_confidence`` (the POC-2 M-form is weakly identified, all
    calibration clusters ≤ 1.0, so M>1 is extrapolation).
    """
    if documented_step_mm is not None and (
            np.isfinite(documented_step_mm) and documented_step_mm > 0):
        return StepResult(step_mm=float(documented_step_mm), step_source="documented",
                          k=float("nan"), predictor=float("nan"), m=m,
                          low_confidence=False)
    step, pred = dof_step_mm(fwhm_frames, m, n_working, marked_f, k=k, form=form)
    low_conf = bool(np.isfinite(step) and m > M_EXTRAPOLATION_THRESHOLD)
    note = ("M>%.2g extrapolation of the POC-2 M-form (weakly identified; all "
            "calibration clusters M<=1.0)" % M_EXTRAPOLATION_THRESHOLD
            if low_conf else "")
    return StepResult(step_mm=step, step_source="dof_estimated", k=k, predictor=pred,
                      m=m, low_confidence=low_conf, note=note)


# --------------------------------------------------------------------------- #
# frames -> mm conversion + quality/imputation
# --------------------------------------------------------------------------- #
def frames_to_mm(value_frames: float, step_mm: float) -> float:
    """Convert a frame count to mm: ``value_frames · step_mm`` (NaN-safe)."""
    if not (np.isfinite(value_frames) and np.isfinite(step_mm)):
        return float("nan")
    return float(value_frames) * float(step_mm)


def dof_expected_fwhm_mm(m: float, n_working: float, marked_f: float,
                         *, k: float = DOF_K, form: str = DOF_FORM) -> float:
    """DoF-model expected OBJECT-space FWHM (mm) = ``k · predictor(N_working, M)``.

    This is the physics prior used to (a) impute the FWHM of ``fwhm_truncated``
    patches and (b) flag patches whose measured FWHM disagrees by a large factor.
    On a ``dof_estimated`` sweep it equals ``fwhm_frames · step_mm`` by construction
    (do not use it to "validate" that sweep — see the module docstring).
    """
    pred = object_dof_predictor(marked_f, m, form=form, n_working=n_working)
    return k * pred


def fwhm_quality(measured_fwhm_mm: float, coverage_flag: str,
                 dof_fwhm_mm: float, *, log_disagree: float = FWHM_LOG_DISAGREE
                 ) -> tuple[float, str, bool]:
    """Apply the imputation / suspect rule. Returns ``(fwhm_mm, quality, imputed)``.

    * ``coverage_flag == "fwhm_truncated"`` → the measured width is clipped /
      under-estimated; return the DoF expectation as the value, quality
      ``"fwhm_imputed"``, ``imputed=True`` (if the DoF expectation is finite; else
      keep the measured value but still label ``fwhm_imputed`` to mark it untrusted).
    * otherwise, for an ``ok`` patch, if both values are finite and
      ``|log(measured / dof)| > log_disagree`` → quality ``"fwhm_suspect"``,
      value unchanged, ``imputed=False``.
    * else → ``"ok"`` with the measured value.

    truncated-LOW / truncated-HIGH coverage flags are NOT imputed and NOT
    suspect-tested here (the centroid mu is itself unreliable, so a width is
    meaningless); they pass through with their measured value and quality ``"ok"`` —
    the carried ``coverage_flag`` is the authority for those, and the driver excludes
    them from POC-4 geometry.
    """
    if coverage_flag == "fwhm_truncated":
        if np.isfinite(dof_fwhm_mm) and dof_fwhm_mm > 0:
            return float(dof_fwhm_mm), "fwhm_imputed", True
        return float(measured_fwhm_mm), "fwhm_imputed", False
    # The suspect test is meaningful only for an otherwise-OK patch. truncated_low /
    # truncated_high carry an unreliable centroid (and a meaningless width), so the
    # carried coverage_flag is the authority — do not relabel them suspect.
    if coverage_flag != "ok":
        return float(measured_fwhm_mm), "ok", False
    if (np.isfinite(measured_fwhm_mm) and measured_fwhm_mm > 0
            and np.isfinite(dof_fwhm_mm) and dof_fwhm_mm > 0):
        if abs(math.log(measured_fwhm_mm / dof_fwhm_mm)) > log_disagree:
            return float(measured_fwhm_mm), "fwhm_suspect", False
    return float(measured_fwhm_mm), "ok", False


def patch_physical_row(*, mu_frames: float, fwhm_frames: float, coverage_flag: str,
                       step: StepResult, m: float, n_working: float, marked_f: float,
                       k: float = DOF_K, form: str = DOF_FORM) -> dict:
    """Full per-patch physical record: ``mu_mm``, ``fwhm_mm`` + flags.

    Combines :func:`frames_to_mm`, the DoF expectation and :func:`fwhm_quality`.
    ``step`` is the per-sweep :class:`StepResult`. The returned dict has the
    physical fields plus the carried ``coverage_flag`` and ``step_*`` provenance.
    """
    mu_mm = frames_to_mm(mu_frames, step.step_mm)
    fwhm_mm_measured = frames_to_mm(fwhm_frames, step.step_mm)
    dof_fwhm = dof_expected_fwhm_mm(m, n_working, marked_f, k=k, form=form)
    fwhm_mm, quality, imputed = fwhm_quality(fwhm_mm_measured, coverage_flag, dof_fwhm)
    return dict(
        mu_mm=mu_mm,
        fwhm_mm=fwhm_mm,
        fwhm_mm_measured=fwhm_mm_measured,
        fwhm_dof_mm=dof_fwhm,
        fwhm_quality=quality,
        fwhm_imputed=bool(imputed),
        coverage_flag=coverage_flag,
        step_mm=step.step_mm,
        step_source=step.step_source,
        step_low_confidence=bool(step.low_confidence),
    )


# --------------------------------------------------------------------------- #
# M>1 extrapolation sensitivity (the honoured caveat)
# --------------------------------------------------------------------------- #
def m_extrapolation_sensitivity(m: float, n_working: float, marked_f: float,
                                fwhm_frames: float, *, k: float = DOF_K) -> dict:
    """How much ``step_mm`` / ``mu_mm`` / ``fwhm_mm`` move if the M-exponent is 1 vs 2.

    POC 2's winning predictor is ``N_working·(1+M)/M²`` — an M-exponent of 2. The
    plainer object-space DoF form ``N_working·(1+M)/M`` (the ``neff_over_m`` family
    with the (1+M) image-depth factor) uses exponent 1. They differ by a factor of
    ``M``. Since ``step_mm ∝ predictor`` (at fixed ``k`` and FWHM_frames) and both
    ``mu_mm`` and ``fwhm_mm`` are ``∝ step_mm``, ALL THREE move by the SAME ratio:

        ratio(exp1 / exp2) = predictor_exp1 / predictor_exp2 = M.

    So for an M=2 sweep the DoF-estimated step (and every derived mm) is uncertain
    by a factor of ~2 purely from the unidentified M-exponent — a hard floor on the
    M>1 confidence. Returns the two step estimates, their ratio (== M) and the
    common fractional shift applied to mu_mm / fwhm_mm.
    """
    pred_exp2 = object_dof_predictor(marked_f, m, form="neff_1pm_over_m2",
                                     n_working=n_working)
    # exponent-1 variant: N_working·(1+M)/M  (image-depth factor, /M not /M²)
    pred_exp1 = n_working * (1.0 + m) / m
    if not (np.isfinite(fwhm_frames) and fwhm_frames > 0):
        step2 = step1 = float("nan")
    else:
        step2 = k * pred_exp2 / fwhm_frames
        step1 = k * pred_exp1 / fwhm_frames
    ratio = pred_exp1 / pred_exp2 if pred_exp2 else float("nan")  # == M
    return dict(m=m, step_mm_exp2=step2, step_mm_exp1=step1,
                ratio_exp1_over_exp2=ratio, frac_shift=abs(ratio - 1.0))
