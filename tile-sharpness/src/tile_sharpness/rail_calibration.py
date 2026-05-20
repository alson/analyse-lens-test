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

# Verdict thresholds on relative MAD of pooled estimates.
#
# IMPORTANT — verdict labels describe per-estimate **spread**, not
# accuracy. The 2026-05-18 validation showed that estimates can be
# tightly clustered (low spread → ``tight`` verdict) while being
# systematically biased — "tight cluster" agrees with itself but
# all members can be off in the same direction. Conversely a "wide"
# spread isn't always wrong, just less precise. Treat the verdict as
# a precision indicator, not an accuracy claim. Bias depends on
# regime (M, N_eff, scribe width) and isn't captured by spread alone.
#
#   tight        rel < 0.15   estimates closely clustered (but may be biased!)
#   moderate     rel < 0.30   moderate per-estimate spread
#   wide         rel < 0.50   wide per-estimate spread
#   unusable     rel ≥ 0.50   spread too large to act on
#   insufficient              too few estimates to compute rel at all
#   failed                    the calibration didn't run (bad input)
TIGHT_REL_UNCERTAINTY = 0.15
MODERATE_REL_UNCERTAINTY = 0.30
WIDE_REL_UNCERTAINTY = 0.50

# Back-compat aliases for callers that still use the older names.
PUBLISHABLE_REL_UNCERTAINTY = TIGHT_REL_UNCERTAINTY
COMPARISON_OK_REL_UNCERTAINTY = MODERATE_REL_UNCERTAINTY
SANITY_ONLY_REL_UNCERTAINTY = WIDE_REL_UNCERTAINTY
HIGH_CONFIDENCE_REL_UNCERTAINTY = TIGHT_REL_UNCERTAINTY
MEDIUM_CONFIDENCE_REL_UNCERTAINTY = MODERATE_REL_UNCERTAINTY

# Minimum pooled estimates before any verdict is issued.
MIN_ESTIMATES_FOR_VERDICT = 5


def _verdict_from_rel(
    rel: float, n_estimates: int,
) -> tuple[str, str]:
    """Map ``rel_uncertainty`` + sample count to a spread-level verdict + note.

    Returns one of ``{tight, moderate, wide, unusable, insufficient}``
    based purely on cluster spread — does **not** correct for or
    report bias.
    """
    if n_estimates < MIN_ESTIMATES_FOR_VERDICT:
        return "wide", f"n_estimates={n_estimates}<{MIN_ESTIMATES_FOR_VERDICT}"
    if not math.isfinite(rel):
        return "wide", "rel_uncertainty undefined"
    if rel < TIGHT_REL_UNCERTAINTY:
        return "tight", ""
    if rel < MODERATE_REL_UNCERTAINTY:
        return "moderate", ""
    if rel < WIDE_REL_UNCERTAINTY:
        return "wide", f"rel_uncertainty={rel:.2f}>{MODERATE_REL_UNCERTAINTY}"
    return "unusable", f"rel_uncertainty={rel:.2f}≥{WIDE_REL_UNCERTAINTY}"


@dataclass(frozen=True)
class CalibrationResult:
    """Per-sweep rail-step calibration outcome."""

    rail_step_mm: float
    uncertainty_mm: float          # MAD across pooled estimates
    rel_uncertainty: float         # MAD / median (NaN if median is 0/NaN)
    n_estimates: int               # pooled (tile, defocus-shot) pairs used
    n_tiles_used: int              # distinct tiles contributing
    # ``verdict`` is one of {tight, moderate, wide,
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


# Three aperture suffix shapes encountered in slugs:
#   * older-rig:        F8, F11, F5.6
#   * newer-rig (pre-rename): f_8, f_11, f_5.6 (dot decimal)
#   * post-rename:      f_5_6, f_2_8 (underscore decimal — used by the
#                       aperture-convention rewrite that converted the
#                       on-disk dir names to safer filesystem chars)
_APERTURE_SUFFIX_TAIL_RE = re.compile(
    r"(?:F|f_)("
    r"[0-9]+_[0-9]+"          # underscore decimal: 5_6
    r"|[0-9]+\.[0-9]+"        # dot decimal: 5.6
    r"|[0-9]+"                # integer: 8
    r")"
)


def parse_aperture(sweep_label: str) -> float | None:
    """Extract the slug aperture as a float. Returns ``None`` if no match.

    Aperture is the LAST ``__``-separated segment of the slug. Three
    formats are supported:

    * ``F<digits>(.<digits>)?`` (older-rig: ``F8``, ``F5.6``)
    * ``f_<digits>(.<digits>)?`` (newer-rig pre-rename: ``f_5.6``)
    * ``f_<digits>_<digits>`` (post-rename, underscore decimal:
      ``f_5_6`` = f/5.6)

    Anchoring to the suffix is critical because lens names can contain
    F-spec substrings (e.g. ``Sigma_..._F2.8_EX_DG_OS_HSM``) that an
    unanchored search would match first.

    Note: for tube/diopter chains the slug aperture is the rounded
    *lens-internal* (or post-rename rounded total-effective) value.
    For best precision pass an explicit ``effective_aperture`` to
    ``calibrate_sweep`` — see ``EffectiveApertureLookup`` for building
    one from ``effective_apertures.csv``.
    """
    parts = sweep_label.split("__")
    if not parts:
        return None
    m = _APERTURE_SUFFIX_TAIL_RE.fullmatch(parts[-1])
    if m is None:
        return None
    # Normalise the underscore-decimal form to dot before float().
    return float(m.group(1).replace("_", "."))


@dataclass(frozen=True)
class EffectiveApertureLookup:
    """``(lens, aperture_dir_name) -> effective_f_exact`` from per-dataset CSVs.

    Each ``effective_apertures.csv`` is the source of truth for
    extension-tube chains where the slug aperture (= rounded
    lens-internal effective) differs from the true total-effective N.
    Bare-prime sweeps are absent from the CSVs; for those, fall back
    to the parsed slug aperture (which already equals total-effective
    when the lens reports m_indicated = m_total). Diopter chains are
    also absent from the CSVs — see ``analytical_diopter_effective_f``
    for the thin-lens fallback.

    Key: ``(lens_config_string, F_dir_name)`` exactly as recorded in
    the CSV — e.g. ``("NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension",
    "f_11")``. The lens string matches both the older-rig directory
    name AND the newer-rig ``lens_config_slug`` from ``shots.csv``.
    """

    table: dict[tuple[str, str], float]

    @classmethod
    def from_csvs(cls, paths: list[Path]) -> "EffectiveApertureLookup":
        """Build a lookup that recognises both raw and slugified lens names.

        The CSV stores ``slug`` with spaces (e.g.
        ``"NIKKOR Z 100-400mm f_4.5-5.6 VR S"``); the older-rig sweep
        labels use ``_slug()`` to replace spaces with underscores
        (``"NIKKOR_Z_100-400mm_f_4.5-5.6_VR_S"``). We store both forms
        as keys so the lookup works for either-rig sweep IDs.
        """
        from .sweeps import _slug  # local import to avoid cycle
        table: dict[tuple[str, str], float] = {}
        for path in paths:
            df = pd.read_csv(path)
            for _, row in df.iterrows():
                raw_lens = str(row["slug"])
                F_dir = str(row["F_dir_name"])
                try:
                    eff = float(row["effective_f_exact"])
                except (ValueError, TypeError):
                    continue
                table[(raw_lens, F_dir)] = eff
                slugged = _slug(raw_lens)
                if slugged != raw_lens:
                    table[(slugged, F_dir)] = eff
        return cls(table=table)

    def get(self, lens: str, aperture_dir: str) -> float | None:
        return self.table.get((lens, aperture_dir))


# ----------------------------------------------------------------------
# Analytical diopter effective-N fallback for diopter chains not covered
# by empirical bellows-calibration. Strictly better than slug-only on
# the 2026-05 validation: median ratio for diopter sweeps moved from
# 1.57 (slug) → 1.33 (analytical). Still well off the tube-CSV target
# (0.92) — empirical diopter shoots (cloud / ceiling sessions in
# bellows-calibration/data/) would close the remaining gap. Logged as
# follow-up in HANDOVER.md and IMPLEMENTATION_PLAN.md.
# ----------------------------------------------------------------------

# Nominal diopter power per close-up filter (in diopters = 1/m).
# Manufacturer specs; real values may differ slightly.
DIOPTER_POWER_D: dict[str, float] = {
    "Canon 500D": 2.0,        # 500D = +2 diopters (1/0.5 m)
    "Nikon 5T": 1.5,
    "Nikon 6T": 2.9,
    "5T": 1.5,                # bare short form as written in slugs
    "6T": 2.9,
    "Olympus MCON-35": 2.86,  # 1/0.35 m
    "Raynox M-150": 4.8,
    "Raynox M-250": 8.0,
}

# Lens focal length (mm) and native max magnification per lens prefix.
# Used to back-solve the lens ring aperture from the slug aperture:
# ``n_ring = slug_f / (1 + m_indicated)``. ``m_indicated`` is clamped
# to the lens's native maximum since the lens has no awareness of the
# attached diopter — at M_total beyond native max, the lens is at its
# own MFD and the rest of M comes from the diopter chain.
_LENS_FOCAL_NATIVE_MAX_M: dict[str, tuple[float, float]] = {
    "Sigma APO Macro 150mm F2.8 EX DG OS HSM": (150.0, 1.0),
    "Sigma Macro 105mm F2.8 EX DG OS HSM": (105.0, 1.0),
    "Nikon AF Micro-Nikkor 200mm f_4D IF-ED": (200.0, 1.0),
    "Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED": (180.0, 0.32),
    "NIKKOR Z MC 105mm f_2.8 VR S": (105.0, 1.0),
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S": (400.0, 0.38),
}


def _diopter_power_total(slug: str) -> float | None:
    """Sum the diopter powers of every recognized diopter filter in the slug.

    Iterates from longest filter name to shortest so ``"Nikon 5T"`` is
    matched before plain ``"5T"`` (avoids double-counting). Returns
    ``None`` when no diopter token is found.
    """
    total = 0.0
    found = False
    remaining = slug
    for name, power in sorted(DIOPTER_POWER_D.items(), key=lambda x: -len(x[0])):
        marker = f"+ {name}"
        if marker in remaining:
            remaining = remaining.replace(marker, "+ MATCHED", 1)
            total += power
            found = True
    return total if found else None


def analytical_diopter_effective_f(
    lens_config_slug: str,
    m_total: float,
    slug_f: float,
) -> float | None:
    """Compute analytical total-effective f-number for a diopter chain.

    Thin-lens model: combined focal length
    ``f_c = f_lens × f_d / (f_lens + f_d)``, physical aperture diameter
    ``D = f_lens / n_ring`` with ``n_ring = slug_f / (1 + m_indicated)``,
    ``n_eff = (f_c / D) × (1 + M_total)``. Returns ``None`` when the slug
    lacks a recognized diopter marker, the base lens isn't in the focal-
    length table, or inputs are non-finite/non-positive.

    Limitations: thin-lens approximation (gap to front element = 0),
    nominal diopter powers, ignores pupil-magnification effects. On the
    2026-05-17 validation, analytical correction cut diopter-chain
    median rail-step bias from 1.57× to 1.33×. Empirical diopter
    calibration (extending ``bellows-calibration/`` to cloud shoots
    with diopters attached) would close the rest.
    """
    if (
        not isinstance(slug_f, (int, float))
        or not math.isfinite(slug_f)
        or slug_f <= 0
    ):
        return None
    d_total = _diopter_power_total(lens_config_slug)
    if d_total is None or d_total <= 0:
        return None
    base = next(
        (l for l in _LENS_FOCAL_NATIVE_MAX_M if lens_config_slug.startswith(l)),
        None,
    )
    if base is None:
        return None
    f_lens, native_max_m = _LENS_FOCAL_NATIVE_MAX_M[base]
    f_diopter_mm = 1000.0 / d_total
    f_combined = f_lens * f_diopter_mm / (f_lens + f_diopter_mm)
    m_lens = (
        min(m_total, native_max_m) if math.isfinite(m_total) else native_max_m
    )
    n_ring = slug_f / (1.0 + m_lens)
    if n_ring <= 0:
        return None
    aperture_diameter = f_lens / n_ring
    n_at_inf_combined = f_combined / aperture_diameter
    return n_at_inf_combined * (1.0 + m_total)


def resolve_effective_aperture(
    lens_config_slug: str,
    F_dir: str,
    m_total: float,
    slug_f: float | None,
    *,
    csv_lookup: EffectiveApertureLookup | None = None,
    use_analytical_diopter: bool = True,
) -> tuple[float | None, str]:
    """Resolve effective N for a sweep, with priority CSV → analytical → slug.

    Returns ``(effective_f, source)`` where ``source`` is one of:
      * ``"csv"`` — empirical extension-tube calibration from CSV.
      * ``"analytical_diopter"`` — thin-lens model for diopter chains.
      * ``"slug"`` — fallback (bare lens; slug ≈ total-effective).
      * ``"missing"`` — no resolution available.
    """
    if csv_lookup is not None:
        csv_val = csv_lookup.get(lens_config_slug, F_dir)
        if csv_val is not None:
            return csv_val, "csv"
    if use_analytical_diopter and slug_f is not None:
        analytical = analytical_diopter_effective_f(
            lens_config_slug, m_total, slug_f,
        )
        if analytical is not None:
            return analytical, "analytical_diopter"
    if slug_f is not None:
        return slug_f, "slug"
    return None, "missing"


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
    effective_aperture: float | None = None,
) -> CalibrationResult:
    """Calibrate one sweep's rail-step-mm from its per-shot per-tile data.

    ``sweep_rows`` is the subset of ``per_shot_per_tile.csv`` for one
    sweep. Required columns: ``sweep``, ``tile_ix``, ``tile_iy``,
    ``shot_idx``, ``on_target``, ``m``, ``trough_fwhm_px``,
    ``lsf_peak_amp``.

    ``effective_aperture`` optionally overrides the slug-parsed
    aperture. Use this for tube/diopter chains where the slug carries
    the rounded lens-internal (or rounded total-effective) f-number,
    not the exact total-effective N needed by the blur formula. Build
    via ``EffectiveApertureLookup.from_csvs`` and pass the result of
    ``lookup.get(lens, F_dir_name)`` per sweep.
    """
    if sweep_rows.empty:
        return _failed("empty input")

    sweep_label = str(sweep_rows["sweep"].iloc[0])
    if effective_aperture is not None and math.isfinite(effective_aperture):
        aperture = float(effective_aperture)
    else:
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
        if verdict == "tight":
            verdict = "moderate"
        elif verdict == "moderate":
            verdict = "wide"

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


# Same three formats as parse_aperture; trailing underscore in
# ``[\d._]+`` covers ``f_5_6`` (post-rename) alongside ``f_5.6`` / ``F8``.
_APERTURE_SUFFIX_RE = re.compile(r"__(?:F|f_)[\d._]+$")


def group_key(sweep_id: str) -> str:
    """Strip trailing aperture suffix to get the (lens, mag, focal)
    group key for v2 pooling. Handles ``__F8`` (older-rig), ``__f_5.6``
    (newer-rig dot decimal), and ``__f_5_6`` (post-rename underscore
    decimal)."""
    return _APERTURE_SUFFIX_RE.sub("", sweep_id)


@dataclass(frozen=True)
class PooledCalibrationResult:
    """Per-(lens, mag, focal) pooled rail-step calibration outcome."""

    group_key: str
    rail_step_mm: float                 # median across per-aperture estimates
    inter_aperture_spread: float        # MAD / median across per-aperture estimates
    n_apertures: int                    # total apertures in the group
    n_apertures_valid: int              # apertures yielding a non-NaN v1 estimate
    # ``verdict`` is one of {tight, moderate, wide,
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
    # at "wide" regardless of the single sweep's internal rel.
    if len(valid) < 2:
        verdict = "wide"
        note = f"only {len(valid)} valid aperture estimate; no cross-aperture check"
    elif not math.isfinite(rel):
        verdict = "wide"
        note = "inter_aperture_spread undefined"
    else:
        # Don't reuse ``_verdict_from_rel`` here: its MIN_ESTIMATES_FOR_VERDICT
        # threshold (designed for v1's tile-shot estimate count) would
        # spuriously demote 2-4 aperture groups. Two apertures with
        # consistent estimates IS the cross-aperture check.
        if rel < PUBLISHABLE_REL_UNCERTAINTY:
            verdict, note = "tight", ""
        elif rel < COMPARISON_OK_REL_UNCERTAINTY:
            verdict, note = "moderate", ""
        elif rel < SANITY_ONLY_REL_UNCERTAINTY:
            verdict = "wide"
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


def _resolve_effective_for_sweep_rows(
    sweep_rows: pd.DataFrame,
    csv_lookup: EffectiveApertureLookup | None,
    use_analytical_diopter: bool,
) -> float | None:
    """Helper: resolve effective N for one sweep's rows using the standard
    CSV → analytical → slug priority.

    The per_shot_per_tile.csv doesn't carry lens-config / F_dir
    explicitly — derive from the sweep_id. Two sweep label formats:

    * Newer-rig: ``<family>/<session>__<lens>__<aperture>`` (3 parts
      after stripping family). ``lens`` is at index 1.
    * Older-rig bare prime: ``<family>/<date>__<lens>__<mag>__<aperture>``
      (4 parts). ``lens`` at index 1.
    * Older-rig zoom: ``<family>/<date>__<lens>__<mag>__<focal>__<aperture>``
      (5 parts). ``lens`` at index 1.

    The lens is always ``parts[1]`` (after stripping the family
    prefix). ``EffectiveApertureLookup`` stores both raw-spaces and
    slugified forms so older-rig's slugified lens names also match.
    """
    if sweep_rows.empty:
        return None
    sweep_id = str(sweep_rows["sweep"].iloc[0])
    parts = sweep_id.split("__")
    if len(parts) < 3:
        return None
    F_dir = parts[-1]
    # Strip the family prefix from the first segment.
    first = parts[0]
    if "/" in first:
        first = first.split("/")[-1]
    lens = parts[1]
    slug_f = parse_aperture(sweep_id)
    m_vals = sweep_rows["m"].dropna().unique() if "m" in sweep_rows.columns else []
    m_total = float(m_vals[0]) if len(m_vals) == 1 else float("nan")
    eff, _src = resolve_effective_aperture(
        lens, F_dir, m_total, slug_f,
        csv_lookup=csv_lookup,
        use_analytical_diopter=use_analytical_diopter,
    )
    return eff


def rail_step_lookup_v1(
    per_shot_csv: Path,
    *,
    effective_aperture_lookup: EffectiveApertureLookup | None = None,
    use_analytical_diopter: bool = True,
) -> dict[str, float]:
    """Per-sweep ``sweep_id -> rail_step_mm`` from v1 calibration.

    Excludes sweeps whose calibration returned NaN. Callers should
    accept that unmapped sweeps fall back to the existing
    rail-step-unavailable code path in characterise.

    Per-sweep effective N is resolved via
    ``resolve_effective_aperture`` (CSV → analytical-diopter → slug).
    Pass ``effective_aperture_lookup`` to enable empirical CSV
    overrides for extension-tube chains; the analytical diopter
    fallback can be disabled by setting ``use_analytical_diopter=False``.
    """
    df = pd.read_csv(per_shot_csv)
    lookup: dict[str, float] = {}
    for sweep_id, grp in df.groupby("sweep"):
        eff = _resolve_effective_for_sweep_rows(
            grp, effective_aperture_lookup, use_analytical_diopter,
        )
        result = calibrate_sweep(grp, effective_aperture=eff)
        if math.isfinite(result.rail_step_mm):
            lookup[str(sweep_id)] = result.rail_step_mm
    return lookup


def rail_step_lookup_v2(
    per_shot_csv: Path,
    *,
    effective_aperture_lookup: EffectiveApertureLookup | None = None,
    use_analytical_diopter: bool = True,
) -> dict[str, float]:
    """Per-sweep ``sweep_id -> rail_step_mm`` from v2 pooled calibration.

    Every sweep in a (lens, mag, focal) group is mapped to the group's
    pooled rail step. Excludes groups whose pooled estimate is NaN.

    Per-sweep effective N resolution is delegated to v1's
    ``calibrate_sweep`` call inside ``calibrate_group``; this wrapper
    pre-resolves it per sweep before pooling, so different apertures
    within a group can each use the correct N.
    """
    df = pd.read_csv(per_shot_csv)
    df["_group_key"] = df["sweep"].map(group_key)
    lookup: dict[str, float] = {}
    for gk, grp in df.groupby("_group_key"):
        # calibrate_group internally re-derives per-sweep effective N
        # via calibrate_sweep, but we need to feed the override into
        # each one. Build a pre-resolved per-sweep map and pass it.
        per_sweep_eff: dict[str, float | None] = {}
        for sid, sub in grp.groupby("sweep"):
            per_sweep_eff[str(sid)] = _resolve_effective_for_sweep_rows(
                sub, effective_aperture_lookup, use_analytical_diopter,
            )
        result = _calibrate_group_with_eff(grp, per_sweep_eff)
        if not math.isfinite(result.rail_step_mm):
            continue
        for sweep_id in grp["sweep"].unique():
            lookup[str(sweep_id)] = result.rail_step_mm
    return lookup


def _calibrate_group_with_eff(
    group_rows: pd.DataFrame,
    per_sweep_eff: dict[str, float | None],
) -> PooledCalibrationResult:
    """Variant of ``calibrate_group`` that uses a per-sweep effective-N override.

    Mirrors ``calibrate_group`` but feeds each per-aperture
    ``calibrate_sweep`` call with its resolved effective N.
    """
    if group_rows.empty:
        return _failed_group("", "empty input")
    gk = group_key(str(group_rows["sweep"].iloc[0]))
    per_aperture: list[CalibrationResult] = []
    for sid, sweep_rows in group_rows.groupby("sweep"):
        eff = per_sweep_eff.get(str(sid))
        per_aperture.append(calibrate_sweep(sweep_rows, effective_aperture=eff))

    valid = [r for r in per_aperture if math.isfinite(r.rail_step_mm)]
    if not valid:
        return PooledCalibrationResult(
            group_key=gk, rail_step_mm=float("nan"),
            inter_aperture_spread=float("nan"),
            n_apertures=len(per_aperture), n_apertures_valid=0,
            verdict="insufficient", per_aperture=tuple(per_aperture),
            note="no aperture sweeps produced a valid estimate",
        )

    rail_steps = np.array([r.rail_step_mm for r in valid], dtype=float)
    median = float(np.median(rail_steps))
    mad = float(np.median(np.abs(rail_steps - median)))
    rel = mad / median if median > 0 else float("nan")

    if len(valid) < 2:
        verdict, note = "wide", (
            f"only {len(valid)} valid aperture estimate; no cross-aperture check"
        )
    elif not math.isfinite(rel):
        verdict, note = "wide", "inter_aperture_spread undefined"
    elif rel < PUBLISHABLE_REL_UNCERTAINTY:
        verdict, note = "tight", ""
    elif rel < COMPARISON_OK_REL_UNCERTAINTY:
        verdict, note = "moderate", ""
    elif rel < SANITY_ONLY_REL_UNCERTAINTY:
        verdict = "wide"
        note = f"inter-aperture spread {rel:.2f} — cross-aperture consistency marginal"
    else:
        verdict = "unusable"
        note = (
            f"inter-aperture spread {rel:.2f}≥{SANITY_ONLY_REL_UNCERTAINTY} "
            "— cross-aperture consistency check failed"
        )

    return PooledCalibrationResult(
        group_key=gk, rail_step_mm=median, inter_aperture_spread=rel,
        n_apertures=len(per_aperture), n_apertures_valid=len(valid),
        verdict=verdict, per_aperture=tuple(per_aperture), note=note,
    )
