# POC 3 — physical (mm) through-focus FWHM/peak refinement

**Goal.** Turn POC 1's per-patch through-focus fits (`mu`, `fwhm` in FRAMES + a
POC-1 `coverage_flag`) into **physical, cross-sweep-comparable** axial quantities
in mm, so POC 4 (decentering / field curvature from where each patch's best focus
lands) can run on the manual-tier sweeps that record NO rail step.

Per patch we now emit:

| field | meaning |
|---|---|
| `mu_mm` | best-focus axial position (mm) = `mu_frames × step_mm`. The POSITION is a fit centroid, **independent of the DoF model** — its accuracy is purely `step_mm` accuracy. |
| `fwhm_mm` | physical depth-of-focus width (mm) = `fwhm_frames × step_mm` (imputed for truncated patches, see below) |
| `fwhm_mm_measured` | the raw `fwhm_frames × step_mm` before any imputation |
| `fwhm_dof_mm` | DoF-model expectation `k · predictor(N_working, M)` (the physics prior) |
| `coverage_flag` | carried through from POC 1 (`ok` / `truncated_low/high` / `fwhm_truncated`) |
| `fwhm_quality` | `ok` / `fwhm_imputed` / `fwhm_suspect` |
| `fwhm_imputed` | bool — width replaced by the DoF expectation |
| `step_mm`, `step_source` | per-sweep step + `documented` / `dof_estimated` |
| `step_low_confidence` | bool — `dof_estimated` AND M above the extrapolation threshold |

Code: `src/tile_sharpness/focus_physical.py` (pure conversion + flag layer,
fully unit-tested), driver `scripts/poc_refine_fwhm.py`. Calibration reused from
POC 2 verbatim: form `neff_1pm_over_m2` = `N_working·(1+M)/M²`, **k = 0.04255**.
`N_working` and `step_mm` resolution reuse the POC-2 paths exactly.

## Step resolution

`documented` wins where present (median diff of `rail_position_mm` in the
session's `shots.csv`; the 2026-05 sweeps record it). Else the POC-2 DoF inversion
`step_mm = k · predictor / FWHM_frames`, where `FWHM_frames` is the sweep's
central-tendency FWHM (median over the `ok` patches, so a few truncated corners do
not bias the step). One constant `step_mm` per sweep, as POC 4 requires.

## Imputation / suspect rule (tied to POC-1 coverage)

* `coverage_flag == fwhm_truncated` → measured half-max width is clipped → flag
  `fwhm_imputed` and **replace** `fwhm_mm` with the DoF expectation `k·predictor`
  (clearly labelled; `mu_mm` kept as measured — centroid is still inside the stack).
* otherwise, for an `ok` patch, `|log(measured/DoF)| > log(2)` (a factor-of-2 gate)
  → flag `fwhm_suspect`, value unchanged (degenerate fit / double peak / contamination).
* `truncated_low` / `truncated_high` → carried `coverage_flag` is the authority
  (centroid unreliable); not imputed, not suspect-tested. POC 4 excludes these.

The factor-of-2 gate is deliberately generous: the per-sweep DoF step is itself
±15–30% (LOO IQR) and per-patch FWHM legitimately varies across the field by a
similar amount, so 2× cleanly catches blown-up fits without flagging honest field
variation.

## CRITICAL — non-circularity

The DoF step is derived FROM the sweep FWHM_frames, so on a `dof_estimated` sweep
`fwhm_mm ≡ k·predictor` identically — you must NOT "validate" `fwhm_mm` against the
DoF model there. (Unit test `test_dof_estimated_fwhm_mm_is_identically_k_pred`
pins this identity.) Consequently the suspect test on a `dof_estimated` sweep
compares each patch only to the sweep's OWN median — it surfaces within-field FWHM
outliers, not an independent physics check. The two clean, non-circular
validations below run on the 2026-05 DOCUMENTED sweeps.

---

## Validation #1 — conversion (DoF-estimated vs documented step), 2026-05

22 bare documented sweeps, per-patch fit on a 5×5 ROI grid, each patch converted
with BOTH steps. The discrepancy `estimated/documented` is exactly the POC-2 step
error and is identical across a sweep's patches (it is the per-sweep step ratio).

| quantity | median | IQR | n |
|---|---|---|---|
| `mu_mm` estimated/documented | **1.049** | [0.908, 1.338] | 550 patches |
| `fwhm_mm` estimated/documented | **1.059** | [0.908, 1.338] | 545 patches |
| per-sweep step ratio (dof/doc) | 1.049 | [0.911, 1.319] | 22 sweeps |

This is the expected ±15–30% POC-2 step error propagating linearly into both
physical quantities, and matches the POC-2 LOO median (1.05). `mu_mm` and
`fwhm_mm` share the same ratio because both are `frames × step_mm`. The worst
sweeps are the widest apertures of the Z 24-120 (f/4 ratio 0.28, f/5.6 0.46),
where the very wide DoF gives a long, flat lapvar peak the FWHM fit under-resolves
— a known POC-2 wide-aperture weakness, not a conversion bug.

## Validation #2 — internal consistency (the POC-4-relevant quantity)

POC 4 uses the across-FIELD spread of `mu_mm`. It must sit above the per-patch
`mu` fit noise.

* **median `mu` fit stderr = 0.045 frames** (IQR [0.025, 0.056], n=22 sweeps) —
  the Gaussian centroid is pinned to ~0.05 frame, far sub-frame.
* **across-field `mu_mm` spread / `mu` fit-noise (mm) = median 30.5×** (IQR
  [14.5, 64], n=22). The field-to-field best-focus variation POC 4 reads is
  resolvable ~30× above the fit noise → field-curvature / decentering geometry is
  recoverable.

(Two Z 100-400 sweeps show inflated field spread from a couple of degenerate
edge-grid patches with low wafer detail; the median-based conclusion is robust to
them.)

---

## M>1 extrapolation sensitivity (honoured caveat)

POC 2's M-form is weakly identified (3 M clusters, all ≤ 1.0), so a `dof_estimated`
`step_mm` at M>1 is extrapolation. The winning form has M-exponent 2
(`N_working·(1+M)/M²`); the plain object-space form has exponent 1
(`N_working·(1+M)/M`). They differ by a factor of **M**, and since
`step_mm ∝ predictor` and `mu_mm, fwhm_mm ∝ step_mm`, **all three move by the same
ratio = M**:

| sweep (2026-01-29) | M | step(exp2) | step(exp1) | frac shift |
|---|---|---|---|---|
| AF200 1:1 | 0.997 | 0.1805 | 0.1799 | 0.00 |
| Z105 1:1 | 1.004 | 0.1472 | 0.1478 | 0.00 |
| S105 1:1 | 1.054 | 0.1115 | 0.1175 | 0.05 |
| Z100-400 + MCON-35 1:1.16 | 1.117 | 0.0689 | 0.0770 | **0.12** |
| AF200 + 6T 1.7:1 | 1.717 | 0.0327 | 0.0562 | **0.72** |
| AF200 + 5T + 6T 2:1 | 2.059 | 0.0505 | 0.1041 | **1.06** |

So the **2:1 config's DoF step (and every derived mm) is uncertain by a factor of
~2** purely from the unidentified M-exponent — a hard floor on its confidence. The
~1:1 configs are essentially insensitive. Sweeps with M > 1.10 are tagged
`step_low_confidence` in the output.

## Application output — 2026-01-29 cohort (POC-4 input)

Per-patch physical focus table: **724 rows, 10 sweeps**, all `dof_estimated` (no
documented step). Flag tallies:

* `coverage_flag`: ok 677, fwhm_truncated 45, truncated_low 2
* `fwhm_quality`: ok 649, **fwhm_imputed 45**, **fwhm_suspect 30**
* **45 patches imputed** (all the `fwhm_truncated` ones; concentrated in
  V55f35 19 + Z100-400+MCON-35 22, the wide/low-detail sweeps).
* **458 patches low-confidence** (M>1.10), in the 6 above-1:1 sweeps incl. the
  1.7:1 and 2:1 configs.

**Per-patch physical focus table for POC 4:**
`out_poc_refine_fwhm/per_patch_physical_2026-01-29.csv`

Also written: `validate_per_patch_2026-05.csv`, `validate_per_sweep_2026-05.csv`,
`m_extrapolation_sensitivity.csv`.
