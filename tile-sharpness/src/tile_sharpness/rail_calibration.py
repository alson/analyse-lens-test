"""Rail-step-mm calibration via through-focus scribe-blur defocus.

Older 2026-01-29 / 2026-02-18 sweeps were manually jogged on the
StackShot without a computer connection, so per-shot ``rail_position_mm``
is unknown. This module back-derives the rail step from optics using
through-focus scribe widening in ``per_shot_per_tile.csv``.

Geometric model
---------------

For a thin lens at total magnification ``M`` with total-effective
f-number ``N_eff = N_ring × (1 + M)`` — the slug aperture under the
project aperture convention (CLAUDE.md §"Aperture convention") — the
geometric blur disc diameter in object space at defocus distance
``δ_object`` is

    blur_object = δ_object × M / N_eff

A wafer scribe has intrinsic object-space width ``SCRIBE_WIDTH_UM``
(≈87 µm, back-solved from AIS / AF 200/4D centre-tile trough FWHM at
peak focus on Z7 1:1). At defocus the observed trough FWHM widens by
the optical blur via Gaussian-like convolution:

    fwhm_observed² ≈ fwhm_intrinsic² + blur²

We use each tile's own minimum-FWHM shot as the empirical
``fwhm_intrinsic`` (absorbs per-tile residual focus error / per-tile
scribe-width variation), then for each defocused shot back-solve
``δ_object`` and divide by ``|Δshot|`` for one rail-step estimate.
Pool across all qualifying ``(tile, defocus-shot)`` pairs in the sweep;
report median + MAD as the calibration + uncertainty.

Limitations
-----------

* Per-sweep granularity. The user's "same start/stop/steps across
  apertures" lever pools per ``(lens, mag, focal)`` group with
  cross-aperture consistency as a sanity check — that lives in a
  separate v2 module.
* Assumes slug aperture is total-effective f-number. Holds for
  bare-prime cohorts (CPU lenses with ``m_indicated = m_total``; MF
  lenses already script-bumped to total). Fails for uncorrected
  external-tube extensions.
* 5–15 % accuracy is realistic — adequate for the task 7 subject-tilt
  sanity check, not for absolute field-curvature µm-RMS reporting.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .methods.maze_fft import SENSOR_PITCH_UM_Z7
from .phase1 import SCRIBE_WIDTH_UM


# |Δshot| below which the estimate is rejected (optical blur small;
# quadrature-subtraction noise dominates).
DEFAULT_MIN_DSHOT = 3

# Observed FWHM must be ≥ this fraction larger than the tile's intrinsic
# FWHM before the widening is treated as a meaningful blur signal.
# 1.10 sits safely above ±1-px trough_fwhm quantization at M≈1
# (intrinsic ~20 px → 10 % = 2 px). At very low M (e.g. 0.385×, intrinsic
# ~8 px), 1.10 ≈ 1 px and is near the quantization floor — calibration
# at very low M is accordingly less reliable.
DEFAULT_MIN_WIDENING = 1.10

# Cap on observed blur (in units of SCRIBE_WIDTH_UM); beyond this the
# trough cross-section model breaks down (trough merges with background;
# edge detection drifts).
DEFAULT_MAX_BLUR_FACTOR = 5.0

# Use-case-named verdict thresholds on relative MAD.
#
# The verdict tells the consumer what the calibration is good for —
# the labels map to concrete downstream uses, not a generic "quality
# grade." Map of expected behavior:
#
#   publishable      rel < 0.15   safe for absolute lp/mm, µm-RMS,
#                                  field-curvature in real units.
#   comparison_ok    rel < 0.30   relative comparisons across slugs;
#                                  tilt in degrees with cited uncertainty.
#   sanity_only      rel < 0.50   binary checks (is the answer ≈ X or 0?);
#                                  don't quote absolute numbers without caveat.
#   unusable         rel ≥ 0.50   too noisy to act on; treat as no calibration.
#   insufficient                  too few estimates to compute rel at all.
#   failed                        the calibration didn't run (bad input).
PUBLISHABLE_REL_UNCERTAINTY = 0.15
COMPARISON_OK_REL_UNCERTAINTY = 0.30
SANITY_ONLY_REL_UNCERTAINTY = 0.50

# Back-compat aliases (existing call sites may use these names; keep
# them as deprecated synonyms until callers migrate).
HIGH_CONFIDENCE_REL_UNCERTAINTY = PUBLISHABLE_REL_UNCERTAINTY
MEDIUM_CONFIDENCE_REL_UNCERTAINTY = COMPARISON_OK_REL_UNCERTAINTY

# Minimum pooled estimates before any verdict is issued.
MIN_ESTIMATES_FOR_VERDICT = 5


def _verdict_from_rel(
    rel: float, n_estimates: int,
) -> tuple[str, str]:
    """Map ``rel_uncertainty`` + sample count to a use-case verdict + note."""
    if n_estimates < MIN_ESTIMATES_FOR_VERDICT:
        return "sanity_only", f"n_estimates={n_estimates}<{MIN_ESTIMATES_FOR_VERDICT}"
    if not math.isfinite(rel):
        return "sanity_only", "rel_uncertainty undefined"
    if rel < PUBLISHABLE_REL_UNCERTAINTY:
        return "publishable", ""
    if rel < COMPARISON_OK_REL_UNCERTAINTY:
        return "comparison_ok", ""
    if rel < SANITY_ONLY_REL_UNCERTAINTY:
        return "sanity_only", f"rel_uncertainty={rel:.2f}>{COMPARISON_OK_REL_UNCERTAINTY}"
    return "unusable", f"rel_uncertainty={rel:.2f}≥{SANITY_ONLY_REL_UNCERTAINTY}"


@dataclass(frozen=True)
class CalibrationResult:
    """Per-sweep rail-step calibration outcome."""

    rail_step_mm: float
    uncertainty_mm: float          # MAD across pooled estimates
    rel_uncertainty: float         # MAD / median (NaN if median is 0/NaN)
    n_estimates: int               # pooled (tile, defocus-shot) pairs used
    n_tiles_used: int              # distinct tiles contributing
    # ``verdict`` is one of {publishable, comparison_ok, sanity_only,
    # unusable, failed} — see module docstring above and
    # ``_verdict_from_rel`` for thresholds + meaning.
    verdict: str
    aperture_f: float
    m: float
    note: str

    @property
    def confidence(self) -> str:
        """Back-compat alias for the renamed ``verdict`` field.

        Old callers reading ``.confidence`` get the new verdict labels.
        """
        return self.verdict


_APERTURE_SUFFIX_TAIL_RE = re.compile(r"(?:F|f_)([0-9]+(?:\.[0-9]+)?)")


def parse_aperture(sweep_label: str) -> float | None:
    """Extract the slug aperture as a float. Returns ``None`` if no match.

    Aperture is the LAST ``__``-separated segment of the slug:
    ``F<digits>(.<digits>)?`` (older-rig) or ``f_<digits>(.<digits>)?``
    (newer-rig). Anchoring to the suffix is critical because lens names
    can contain F-spec substrings (e.g. ``Sigma_..._F2.8_EX_DG_OS_HSM``)
    that an unanchored search would match first.
    """
    parts = sweep_label.split("__")
    if not parts:
        return None
    m = _APERTURE_SUFFIX_TAIL_RE.fullmatch(parts[-1])
    return float(m.group(1)) if m else None


def fwhm_object_um(trough_fwhm_px: float, m: float) -> float:
    """Convert measured trough FWHM (sensor px) to object-space µm."""
    return trough_fwhm_px * SENSOR_PITCH_UM_Z7 / m


def blur_um_from_widening(
    fwhm_obs_um: float, fwhm_intrinsic_um: float,
) -> float | None:
    """Quadrature-subtract intrinsic FWHM from observed; ``None`` if not widened."""
    diff = fwhm_obs_um * fwhm_obs_um - fwhm_intrinsic_um * fwhm_intrinsic_um
    if diff <= 0:
        return None
    return math.sqrt(diff)


def defocus_um_from_blur(
    blur_um: float, aperture_n_eff: float, m: float,
) -> float:
    """Object-space defocus from geometric blur disc.

    Inverts ``blur = δ × M / N_eff`` (thin-lens, total-effective N).
    """
    return blur_um * aperture_n_eff / m


# Threshold for the "suspicious peak" diagnostic. If the chosen peak's
# fwhm is below this fraction of the per-sweep median fwhm, the
# detector likely latched onto a narrow non-scribe sub-feature rather
# than the actual in-focus scribe. The estimates produced from such a
# peak will agree with each other (low rel_uncertainty) while being
# systematically biased low — a "false high confidence" failure mode.
# This threshold is per-tile; signaling happens at the calibrate_sweep
# level by reducing the confidence verdict.
SUSPICIOUS_PEAK_FRACTION = 0.7


def _tile_estimates(
    tile_rows: pd.DataFrame,
    *,
    aperture_n_eff: float,
    m: float,
    min_dshot: int,
    min_widening: float,
    max_blur_factor: float,
) -> tuple[list[float], bool]:
    """Return ``(estimates, peak_is_suspicious)``.

    The peak shot is the per-tile ``argmin(trough_fwhm_px)``. Suspicious
    peak: the picked fwhm is below ``SUSPICIOUS_PEAK_FRACTION × median(fwhm)``,
    indicating the detector found a sub-feature narrower than the
    scribe at that tile (e.g. bond-pad edge in a defocused frame).
    Estimates are still returned but the suspicion flag bubbles up so
    the sweep's confidence can be reduced.
    """
    valid = tile_rows.dropna(subset=["trough_fwhm_px", "lsf_peak_amp"]).copy()
    if len(valid) < min_dshot + 1:
        return [], False

    valid["_fwhm_um"] = (
        valid["trough_fwhm_px"].astype(float) * SENSOR_PITCH_UM_Z7 / m
    )
    intrinsic_um = float(valid["_fwhm_um"].min())
    if intrinsic_um <= 0:
        return [], False
    peak_idx = int(valid.loc[valid["_fwhm_um"].idxmin(), "shot_idx"])

    median_um = float(valid["_fwhm_um"].median())
    peak_is_suspicious = (
        median_um > 0 and intrinsic_um < SUSPICIOUS_PEAK_FRACTION * median_um
    )

    max_blur_um = max_blur_factor * SCRIBE_WIDTH_UM
    estimates: list[float] = []
    for _, row in valid.iterrows():
        dshot = abs(int(row["shot_idx"]) - peak_idx)
        if dshot < min_dshot:
            continue
        fwhm_um = float(row["_fwhm_um"])
        if fwhm_um < min_widening * intrinsic_um:
            continue
        blur_um = blur_um_from_widening(fwhm_um, intrinsic_um)
        if blur_um is None or blur_um > max_blur_um:
            continue
        defocus_um = defocus_um_from_blur(blur_um, aperture_n_eff, m)
        estimates.append(defocus_um / 1000.0 / dshot)
    return estimates, peak_is_suspicious


def calibrate_sweep(
    sweep_rows: pd.DataFrame,
    *,
    min_dshot: int = DEFAULT_MIN_DSHOT,
    min_widening: float = DEFAULT_MIN_WIDENING,
    max_blur_factor: float = DEFAULT_MAX_BLUR_FACTOR,
) -> CalibrationResult:
    """Calibrate one sweep's rail-step-mm from its per-shot per-tile data.

    ``sweep_rows`` is the subset of ``per_shot_per_tile.csv`` for one
    sweep. Required columns: ``sweep``, ``tile_ix``, ``tile_iy``,
    ``shot_idx``, ``on_target``, ``m``, ``trough_fwhm_px``,
    ``lsf_peak_amp``.
    """
    if sweep_rows.empty:
        return _failed("empty input")

    sweep_label = str(sweep_rows["sweep"].iloc[0])
    aperture = parse_aperture(sweep_label)
    if aperture is None:
        return _failed(f"could not parse aperture from sweep {sweep_label!r}")
    m_vals = sweep_rows["m"].dropna().unique()
    if len(m_vals) != 1:
        return _failed(f"sweep {sweep_label!r} has non-unique m: {m_vals}")
    m = float(m_vals[0])
    if not math.isfinite(m) or m <= 0:
        return _failed(f"sweep {sweep_label!r} has non-positive m: {m}")

    on_target = sweep_rows[sweep_rows["on_target"] == True]  # noqa: E712
    if on_target.empty:
        return CalibrationResult(
            rail_step_mm=float("nan"),
            uncertainty_mm=float("nan"),
            rel_uncertainty=float("nan"),
            n_estimates=0,
            n_tiles_used=0,
            verdict="insufficient",
            aperture_f=aperture,
            m=m,
            note="no on-target tiles",
        )

    all_estimates: list[float] = []
    tiles_used = 0
    tiles_with_suspicious_peak = 0
    for _, tile_rows in on_target.groupby(["tile_ix", "tile_iy"]):
        tile_ests, peak_suspicious = _tile_estimates(
            tile_rows,
            aperture_n_eff=aperture,
            m=m,
            min_dshot=min_dshot,
            min_widening=min_widening,
            max_blur_factor=max_blur_factor,
        )
        if tile_ests:
            tiles_used += 1
            all_estimates.extend(tile_ests)
            if peak_suspicious:
                tiles_with_suspicious_peak += 1

    n = len(all_estimates)
    if n == 0:
        return CalibrationResult(
            rail_step_mm=float("nan"),
            uncertainty_mm=float("nan"),
            rel_uncertainty=float("nan"),
            n_estimates=0,
            n_tiles_used=0,
            verdict="insufficient",
            aperture_f=aperture,
            m=m,
            note="no qualifying defocused shots",
        )

    arr = np.array(all_estimates, dtype=float)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    rel = mad / median if median > 0 else float("nan")

    verdict, note = _verdict_from_rel(rel, n)

    # "Suspicious peak" downgrade: even tightly-clustered estimates are
    # untrustworthy if the peak shot's fwhm is implausibly narrow (the
    # detector likely picked a noise minimum or sub-feature rather than
    # the in-focus scribe). Drop the verdict one notch and annotate so
    # v2 pooling / readers see why.
    if (
        tiles_used > 0
        and tiles_with_suspicious_peak / tiles_used >= 0.5
    ):
        suspicious_note = (
            f"suspicious peak ({tiles_with_suspicious_peak}/{tiles_used} tiles "
            f"have min_fwhm < {SUSPICIOUS_PEAK_FRACTION}×median)"
        )
        note = (note + "; " + suspicious_note) if note else suspicious_note
        if verdict == "publishable":
            verdict = "comparison_ok"
        elif verdict == "comparison_ok":
            verdict = "sanity_only"

    return CalibrationResult(
        rail_step_mm=median,
        uncertainty_mm=mad,
        rel_uncertainty=rel,
        n_estimates=n,
        n_tiles_used=tiles_used,
        verdict=verdict,
        aperture_f=aperture,
        m=m,
        note=note,
    )


def _failed(reason: str) -> CalibrationResult:
    return CalibrationResult(
        rail_step_mm=float("nan"),
        uncertainty_mm=float("nan"),
        rel_uncertainty=float("nan"),
        n_estimates=0,
        n_tiles_used=0,
        verdict="failed",
        aperture_f=float("nan"),
        m=float("nan"),
        note=reason,
    )


def calibrate_csv(per_shot_csv: Path) -> pd.DataFrame:
    """Run ``calibrate_sweep`` per sweep across a ``per_shot_per_tile.csv``."""
    df = pd.read_csv(per_shot_csv)
    rows: list[dict] = []
    for sweep_id, grp in df.groupby("sweep"):
        result = calibrate_sweep(grp)
        rows.append({
            "sweep": sweep_id,
            "rail_step_mm": result.rail_step_mm,
            "uncertainty_mm": result.uncertainty_mm,
            "rel_uncertainty": result.rel_uncertainty,
            "n_estimates": result.n_estimates,
            "n_tiles_used": result.n_tiles_used,
            "confidence": result.confidence,
            "aperture_f": result.aperture_f,
            "m": result.m,
            "note": result.note,
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# v2: multi-aperture pooling per (lens, mag, focal) group.
# ----------------------------------------------------------------------
#
# The user's "same start/stop/steps across apertures" workflow means
# every aperture sweep within one ``(lens, mag, focal)`` group shares a
# physical rail step. Per-aperture v1 estimates should agree; pooling
# them with the median + MAD across apertures yields both a more
# robust estimate and a built-in cross-aperture consistency check —
# disagreement flags a broken assumption (uncorrected bellows, wrong
# aperture-convention bump, partial bracket).


_APERTURE_SUFFIX_RE = re.compile(r"__(?:F|f_)[\d.]+$")


def group_key(sweep_id: str) -> str:
    """Strip trailing ``__F<aperture>`` (older) or ``__f_<aperture>`` (newer)
    to get the (lens, mag, focal) group key for v2 pooling."""
    return _APERTURE_SUFFIX_RE.sub("", sweep_id)


@dataclass(frozen=True)
class PooledCalibrationResult:
    """Per-(lens, mag, focal) pooled rail-step calibration outcome."""

    group_key: str
    rail_step_mm: float                 # median across per-aperture estimates
    inter_aperture_spread: float        # MAD / median across per-aperture estimates
    n_apertures: int                    # total apertures in the group
    n_apertures_valid: int              # apertures yielding a non-NaN v1 estimate
    # ``verdict`` is one of {publishable, comparison_ok, sanity_only,
    # unusable, insufficient, failed} — same meaning as
    # ``CalibrationResult.verdict``.
    verdict: str
    per_aperture: tuple[CalibrationResult, ...]
    note: str

    @property
    def confidence(self) -> str:
        """Back-compat alias for the renamed ``verdict`` field."""
        return self.verdict


def calibrate_group(group_rows: pd.DataFrame) -> PooledCalibrationResult:
    """Pool per-aperture v1 estimates within one (lens, mag, focal) group.

    ``group_rows`` is the subset of per_shot_per_tile rows with the same
    (lens, mag, focal) key (i.e. multiple sweeps differing only in
    aperture). Per-sweep v1 calibration runs, then the median across
    non-NaN per-sweep estimates is the group's rail step.
    """
    if group_rows.empty:
        return _failed_group("", "empty input")
    sweep_ids = list(group_rows["sweep"].unique())
    if not sweep_ids:
        return _failed_group("", "no sweeps")

    gk = group_key(str(sweep_ids[0]))
    per_aperture: list[CalibrationResult] = []
    for _, sweep_rows in group_rows.groupby("sweep"):
        per_aperture.append(calibrate_sweep(sweep_rows))

    valid = [r for r in per_aperture if math.isfinite(r.rail_step_mm)]
    if not valid:
        return PooledCalibrationResult(
            group_key=gk,
            rail_step_mm=float("nan"),
            inter_aperture_spread=float("nan"),
            n_apertures=len(per_aperture),
            n_apertures_valid=0,
            verdict="insufficient",
            per_aperture=tuple(per_aperture),
            note="no aperture sweeps produced a valid estimate",
        )

    rail_steps = np.array([r.rail_step_mm for r in valid], dtype=float)
    median = float(np.median(rail_steps))
    mad = float(np.median(np.abs(rail_steps - median)))
    rel = mad / median if median > 0 else float("nan")

    # Single-aperture pool: no cross-aperture cross-check possible — cap
    # at sanity_only regardless of the single sweep's internal rel.
    if len(valid) < 2:
        verdict = "sanity_only"
        note = f"only {len(valid)} valid aperture estimate; no cross-aperture check"
    elif not math.isfinite(rel):
        verdict = "sanity_only"
        note = "inter_aperture_spread undefined"
    else:
        # Don't reuse ``_verdict_from_rel`` here: its MIN_ESTIMATES_FOR_VERDICT
        # threshold (designed for v1's tile-shot estimate count) would
        # spuriously demote 2-4 aperture groups. Two apertures with
        # consistent estimates IS the cross-aperture check.
        if rel < PUBLISHABLE_REL_UNCERTAINTY:
            verdict, note = "publishable", ""
        elif rel < COMPARISON_OK_REL_UNCERTAINTY:
            verdict, note = "comparison_ok", ""
        elif rel < SANITY_ONLY_REL_UNCERTAINTY:
            verdict = "sanity_only"
            note = (
                f"inter-aperture spread {rel:.2f} — cross-aperture "
                f"consistency marginal"
            )
        else:
            verdict = "unusable"
            note = (
                f"inter-aperture spread {rel:.2f}≥{SANITY_ONLY_REL_UNCERTAINTY} "
                "— cross-aperture consistency check failed"
            )

    return PooledCalibrationResult(
        group_key=gk,
        rail_step_mm=median,
        inter_aperture_spread=rel,
        n_apertures=len(per_aperture),
        n_apertures_valid=len(valid),
        verdict=verdict,
        per_aperture=tuple(per_aperture),
        note=note,
    )


def _failed_group(gk: str, reason: str) -> PooledCalibrationResult:
    return PooledCalibrationResult(
        group_key=gk,
        rail_step_mm=float("nan"),
        inter_aperture_spread=float("nan"),
        n_apertures=0,
        n_apertures_valid=0,
        verdict="failed",
        per_aperture=(),
        note=reason,
    )


def calibrate_pooled_csv(per_shot_csv: Path) -> pd.DataFrame:
    """Run pooled v2 calibration per (lens, mag, focal) across a per_shot_per_tile.csv."""
    df = pd.read_csv(per_shot_csv)
    df["_group_key"] = df["sweep"].map(group_key)
    rows: list[dict] = []
    for gk, grp in df.groupby("_group_key"):
        result = calibrate_group(grp)
        rows.append({
            "group_key": result.group_key,
            "rail_step_mm": result.rail_step_mm,
            "inter_aperture_spread": result.inter_aperture_spread,
            "n_apertures": result.n_apertures,
            "n_apertures_valid": result.n_apertures_valid,
            "confidence": result.confidence,
            "note": result.note,
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Lookup helpers for the characterise.py wire-in.
# ----------------------------------------------------------------------


def rail_step_lookup_v1(per_shot_csv: Path) -> dict[str, float]:
    """Per-sweep ``sweep_id -> rail_step_mm`` from v1 calibration.

    Excludes sweeps whose calibration returned NaN. Callers should
    accept that unmapped sweeps fall back to the existing
    rail-step-unavailable code path in characterise.
    """
    df = pd.read_csv(per_shot_csv)
    lookup: dict[str, float] = {}
    for sweep_id, grp in df.groupby("sweep"):
        result = calibrate_sweep(grp)
        if math.isfinite(result.rail_step_mm):
            lookup[str(sweep_id)] = result.rail_step_mm
    return lookup


def rail_step_lookup_v2(per_shot_csv: Path) -> dict[str, float]:
    """Per-sweep ``sweep_id -> rail_step_mm`` from v2 pooled calibration.

    Every sweep in a (lens, mag, focal) group is mapped to the group's
    pooled rail step. Excludes groups whose pooled estimate is NaN.
    """
    df = pd.read_csv(per_shot_csv)
    df["_group_key"] = df["sweep"].map(group_key)
    lookup: dict[str, float] = {}
    for gk, grp in df.groupby("_group_key"):
        result = calibrate_group(grp)
        if not math.isfinite(result.rail_step_mm):
            continue
        for sweep_id in grp["sweep"].unique():
            lookup[str(sweep_id)] = result.rail_step_mm
    return lookup
