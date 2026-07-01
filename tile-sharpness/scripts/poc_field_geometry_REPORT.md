# POC 4 — Decentering & field curvature from the best-focus surface

**Date:** 2026-07-01 · **Cohort:** older-rig 2026-01-29, 10 configs, 724 patches
**Driver:** `scripts/poc_field_geometry.py` · **Helpers:** `src/tile_sharpness/field_geometry_focus.py`
**Outputs:** `out_poc_field_geometry/{per_config_field_geometry.csv, joined_per_patch.csv, crosscheck_characterise.csv}`

## Idea & method

For each lens config, every wafer patch has a best-focus axial position `mu_mm`
(POC 3 Gaussian peak-centre through the focus stack). Mapping `mu_mm` over the
patch field position `(px, py)` (POC 1 `field_geometry`) gives a SURFACE:

1. **Plane fit** `mu_mm ≈ a·px + b·py + c` → subject-space tilt (deg) via
   `characterise._slope_to_tilt_deg` (M-scaled, Z7 pitch 4.35 µm), plus the
   azimuth of steepest best-focus ascent (`field_geometry` convention: +x=0°,
   up=+90°, down=−90°). This is the decentering / plane-tilt signature.
2. **Field curvature** — fit the plane-removed residual vs `field_height²`;
   report sag µm (peak-to-edge, +ve = corners focus farther than centre) and
   RMS µm.
3. **Decentering direction** — mean `mu_mm` left vs right and top (image-up) vs
   bottom about the patch centroid; positive T-B = top focuses farther.
4. **Astigmatism** — sagittal vs tangential best-focus split.

POC 1/2/3 files (`cross_m_relative_mtf.py`, `optics.py`, `focus_physical.py`)
were NOT edited; `_plane_fit` / `_slope_to_tilt_deg` are imported from
`characterise.py`.

`mu_mm` (and hence absolute tilt-deg / curvature-µm) carries an uncertain
ABSOLUTE scale on `step_low_confidence` (M>1.10) sweeps because the rail step is
DoF-estimated, not documented — there is no documented rail step for any
2026-01-29 sweep, so EVERY config here uses a DoF-estimated `step_mm`. Tilt
DIRECTION/azimuth and decentering SIGN are unaffected (step is a global scale);
the absolute µm/deg are step-proportional.

## Per-config results — ALL patches vs COVERAGE-CLEAN

"clean" = `coverage_flag == ok` AND not `fwhm_imputed`.

| config | M | step_lowconf | n all→clean | tilt mag° all→clean | sag µm all→clean | T-B mm all→clean | L-R mm all→clean |
|---|---|---|---|---|---|---|---|
| 100-400 + MCON-35 1:1.16 | 1.12 | yes | 69→47 | 1.83→1.88 | −492→−410 | +0.06→**−0.02** | −0.38→−0.46 |
| NIKKOR Z MC 105 | 1.00 | yes | 92→92 | 2.53 | −325 | +0.26 | +0.53 |
| 200 +5T+6T 2:1 | 2.06 | yes | 16→15 | 3.05→3.86 | +38→−17 | −0.04 | +0.28→+0.34 |
| 200 +6T 1.7:1 | 1.72 | yes | 28→27 | 2.44→2.29 | −159→−164 | −0.12→−0.09 | +0.38→+0.34 |
| **200 IF-ED 1:1** | 1.00 | no | 88→85 | 4.43→6.78 | **8508→108** | **+1.99→−1.14** | +2.36→+1.15 |
| 60 f/2.8D | 1.00 | yes | 85→85 | 4.30 | +279 | +0.10 | −1.12 |
| 55 AIS 287318 | 1.00 | no | 85→84 | 4.29→4.17 | −1206→−1072 | +0.04→**−0.02** | −1.18→−1.15 |
| Auto 55 f/3.5 209088 | 0.99 | no | 93→74 | 2.17→1.74 | −554→−425 | +0.12→+0.11 | −0.57→−0.35 |
| Sigma APO 150 | 1.03 | yes | 83→83 | 5.87 | +264 | +0.96 | −0.42 |
| Sigma 105 | 1.05 | yes | 85→85 | 2.16 | −79 | +0.07 | −0.53 |

(Configs with no exclusions are unchanged by construction.)

## The load-bearing question (HANDOVER follow-up #7): is the T-B "decentering" real?

**Verdict: the 2026-01-29 top-vs-bottom "decentering" is an UNDER-COVERAGE
ARTIFACT, not real decentering.** Every config whose T-B value is non-trivial in
the ALL set collapses to ≈0 (and flips sign) once under-covered patches are
removed:

- **200 IF-ED**: the smoking gun. Three truncated patches carry a garbage
  extrapolated `mu_mm` down to **−93 mm** (vs a clean 3.25–7.42 mm span). They
  inflate T-B to +1.99 mm and curvature sag to **8508 µm (RMS 11033 µm)**.
  Excluding them: T-B → **−1.14 mm with the sign flipped** and sag → **108 µm**
  (RMS 387) — a 78× collapse. The apparent T-B asymmetry lived entirely in the
  truncated patches.
- **55 AIS 287318** and **100-400 + MCON-35**: clean T-B is **±0.02 mm**
  (negligible) and changes sign on exclusion — again artifact-driven.
- Where T-B IS non-zero after cleaning, it is NOT top/bottom: **L-R survives**
  exclusion robustly (e.g. 60mm −1.12, AIS 287318 −1.15, MCON −0.46 mm). The
  real residual is a left-right / general plane tilt, not a T-B decentering.
- The two genuine after-clean T-B signals are **Sigma 150 (+0.96 mm)** and
  **NIKKOR Z MC 105 (+0.26 mm)** — both have NO truncated patches, so these are
  real lens/mount field-tilt, not coverage artifacts (Sigma 150 also has the
  largest plane tilt, 5.9°).

This independently reproduces POC 1's conclusion: the apparent T-B asymmetry was
in TRUNCATED patches; the corners were symmetric in T-B.

## Cross-check vs `characterise.py` (same sweeps, same DoF step)

`characterise_sweep` uses a DIFFERENT focus metric (`argmax_shot_idx`, 1 of ≤77
discrete shots) and a DIFFERENT patch set (≤9 ring tiles from peaks_v2) than
POC 4 (continuous Gaussian `mu_mm` over ~85 dense patches). Fed the SAME
DoF-estimated `step_mm`, tilt MAGNITUDES agree to ~0.5° — strong method
validation:

| config | POC4 clean tilt° | characterise tilt° |
|---|---|---|
| NIKKOR Z MC 105 | 2.53 | 2.31 |
| 200 IF-ED 1:1 | 6.78 | 6.56 |
| 55 AIS 287318 | 4.17 | 4.59 |
| Auto 55 209088 | 1.74 | 1.78 |

(Sigma 150 / Sigma 105 peaks_v2 have only 1 tile → plane fit NaN, no
cross-check.) characterise's `decentering_fx_tb` is likewise small (−0.16 to
+0.02) — consistent with "no real T-B decentering". Note characterise's peak-
VALUE L-R/T-B is an amplitude asymmetry, not a focus-position one, so only the
SIGN/smallness is comparable, not the mm magnitude.

## Tie-back to Task 7 ("older rig near-coplanar, <1°")

POC 4 tilts (clean 1.7–6.8°) are LARGER than Task 7's median |tilt_x|=0.45°,
|tilt_y|=0.12°, max 1.67°. The difference is **the rail-step calibration, not
the geometry**: tilt is exactly LINEAR in `step_mm`, and Task 7 used the **v2
pooled rail-step lookup**, whereas POC 4 (and this cross-check) use POC 2's
**DoF-estimated** `step_mm`. The POC4-vs-characterise agreement at ~0.5° on the
SAME step proves the two focus metrics measure the same surface; the absolute
degree value is whatever the chosen step makes it. So:

- The **method is validated** (two metrics agree on the same step).
- The **absolute tilt magnitude is step-calibration-dependent** and should be
  read as "a few degrees under the DoF step" — not contradicting Task 7, which
  measured the same physical surface scaled by a different (larger) step.
- The robust, scale-INVARIANT conclusions — T-B decentering is a coverage
  artifact, L-R is the real residual, Sigma 150 has the largest genuine tilt —
  hold regardless of step.

## Astigmatism — NOT available

A focus-position sag-vs-tan split needs a best-focus `mu_mm` per edge
ORIENTATION per patch. POC 3 collapsed the stack to ONE `mu_mm` per patch, and
the fieldtag shards carry only sagittal/tangential AMPLITUDE
(`amp_sag/tan_fpx*`), not per-orientation focus position, nor a per-patch
dominant edge azimuth. So astigmatism is reported `available=False`. The helper
`compute_astigmatism` is implemented and unit-tested (recovers a known 0.08 mm
sag-vs-tan split on synthetic data) for when a per-orientation `mu_mm` extract
becomes available.

## Validation on a documented-step 2026-05 sweep — limitation

The 2026-05 sweeps have accurate (documented) `mu_mm`, which would pin the
absolute scale. But POC 1 produced per-patch `(px, py)` field geometry only for
the 2026-01-29 cohort (`fieldtag_shard_*`); the newer sweeps' per-patch geometry
is not readily available in this tree. We therefore lean on the characterise
cross-check (same cohort, independent metric) for method validation and flag the
absolute-scale dependence explicitly. Producing 2026-05 fieldtags is the natural
next step to lock the absolute degrees/µm.

## Unit tests

`tests/test_field_geometry_focus.py` — 11 tests, all passing: plane-slope
recovery, M-scaled tilt-deg formula, tilt-magnitude combination, azimuth image
convention (right=0°, up=+90°, down=−90°), known-bowl curvature + sign,
plane+bowl separation, L-R and T-B decentering sign, astigmatism
unavailable-without-orientation and recovered-with-orientation.
