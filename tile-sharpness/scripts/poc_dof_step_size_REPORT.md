# POC 2 — depth-of-field-based rail step-size estimator

A physics-first alternative to the scribe-blur calibrator
(`tile_sharpness.rail_calibration.calibrate_sweep`) for back-deriving the
StackShot rail step (mm per frame) on the older "manual-tier" sweeps that record
no per-shot `rail_position_mm` — only an ordered sequence of JPGs.

**Code:** `scripts/poc_dof_step_size.py` (CLI: `validate`, `apply`, `all`);
physics helper `tile_sharpness.optics.object_dof_predictor`. Run on **nufan**
(NFS data); compute placement note below. Tests:
`tests/test_optics.py`, `tests/test_poc_dof_step_size.py` (22 pass).

> **Lead with caveats** (per MEMORY): the headline accuracy below is *under the
> conditions tested* — a clean bare-lens set spanning M=0.385–1.0 and f/4–f/16 on
> the 2026-05 rig. It is **not** validated above M=1 (no bare lens reaches it
> here) nor on the predictor's behaviour for accessory/tube configs (those enter
> only via the empirical effective-aperture CSV). See "Not yet tested".

---

## 1. Physics & predictor

An object displaced axially by `δz` from best focus makes a geometric defocus
blur of object-space diameter `b ≈ δz·M / N_eff`, with `N_eff` the **working**
(bellows-corrected) f-number. The through-focus sharpness response (Laplacian
variance vs frame) therefore has a characteristic **object-space** width set by
an acceptable-blur tolerance `c`. Candidate scalings for that width:

| form | predictor | rationale |
|---|---|---|
| `neff_over_m` | `N_eff / M` | object-space geometric DoF half-width |
| `n_over_m` | `N / M` | marked f, ignores bellows |
| `neff_1pm_over_m2` | `N_eff·(1+M) / M²` | image-space focus depth `N_eff(1+M)` ÷ axial mag `M²` |
| `neff` | `N_eff` | no M term (control) |

Model: `FWHM_frames × step_mm = FWHM_object_mm ≈ k · predictor(N_eff, M)`. On
2026-05 the step is documented → fit `k`, compare forms by R². Invert on
pre-2026-05: `step_mm = k · predictor / FWHM_frames`.

The through-focus curve is a plain Laplacian-variance over a fixed central ROI
(40 %) of one JPG per rail position (base `step_NNNN.jpg`, replicas excluded),
decoded at 1/4 resolution (`IMREAD_REDUCED_GRAYSCALE_4`) for speed — the FWHM
*shape* is preserved and the same decode path is used for calibration and
application, so `k` transfers. FWHM is the Gaussian-of-defocus fit
(`gaussian_defocus_fwhm`, imported read-only; inlined equivalent for tests).

## 2. Working f-number (N_working) — the load-bearing correction

The DoF model needs the **true working f-number at the focal plane**, used
**once**. The directory/folder f-number in this dataset is already the effective
aperture for every lens (the tree was curated so folder = f_eff, folding in the
lens's own helicoid extension and any external tube), so:

* **`csv_exact` / `csv_mult`** — `effective_f_exact` from the bellows-calibration
  `effective_apertures.csv` (photometric: `bellows_multiplier = sqrt(brightness
  ratio)`, *not* DoF-derived → no circularity). Preferred for the
  100-400 / 24-120 / MC 105 / Viltrox + their tube/diopter combos.
* **`folder_direct`** — otherwise the folder f-number, used directly.
* **Never** the analytical `N·(1+M/p)` formula (focal-length-at-MFD and pupil
  magnification are unpublished/unreliable for IF lenses — the reason the rig
  went photometric). Configs with neither a CSV match nor a folder value are
  dropped, not synthesised.

This avoids the two failure modes of the first cut: (a) reading a snapped-
*effective* F-dir label and re-multiplying by `(1+M)` (double-count), and
(b) applying `(1+M)` to a folder that was already effective (over-count) — the
latter caused a spurious M-dependent bias (M<0.6→0.88, M~1→1.86 ratio) that the
fix removed.

### Per-lens N_working classification (clean bare calibration set)

Guardrail: widest native folder f vs `marked_max × (1+M)` — they should match if
folder = effective.

| lens | M | marked max | widest folder | marked×(1+M) | guardrail | N_source |
|---|---:|---:|---:|---:|---|---|
| NIKKOR Z 100-400 f/4.5-5.6 VR S | 0.385 | 4.5 | 5.6 | 6.23 | EFF-ok | csv_exact |
| NIKKOR Z 24-120 f/4 S | 0.385 | 4.0 | 4.0 | 5.54 | (mult≈1) | csv_exact |
| Nikon AF 70-180 f/4.5-5.6D ED | 0.752 | 4.5 | 5.6 | 7.88 | borderline | folder_direct |
| Nikon Micro-Nikkor 55mm f/2.8 AI-S | 1.0 | 2.8 | 4.0 | 5.60 | **FLAG** | folder_direct |
| Sigma APO Macro 150mm F2.8 | 1.0 | 2.8 | 5.6 | 5.60 | EFF-ok | folder_direct |

**Caveat — 55mm AI-S guardrail flag:** its widest *available* sweep dir is f/4
(it was not shot wide-open), so the widest-folder test is inconclusive for it
(f/4 sits between marked-max 2.8 and 2.8×(1+M)=5.6). The Auto-55 sibling shoots
F7 = 3.5×2 wide-open (clean effective signature), so the folder-effective
convention is taken to hold for the AI-S 55mm too; flagged here for honesty.

**How M was obtained (newer rig):** `metadata.json` →
`lens_config.magnification` (the planned/target magnification). The
`magnification_indicated` column in `shots.csv` is empty/None for these sessions
(confirmed across the extension and Viltrox sessions), so it is NOT used.
Reliability: planned value, not per-frame wafer-measured; for the bare set the
values (0.385, 0.752, 1.0) are the rig's nominal setpoints.

## 3. Predictor comparison + calibration (2026-05 clean bare set, n=22)

FWHM fit: **22/22 sweeps usable (0 % nan / out-of-range)** on the clean bare set
(see §6 on the nan diagnostic).

| predictor | k | R² |
|---|---:|---:|
| **`neff_1pm_over_m2` (N·(1+M)/M²)** | **0.04255** | **0.8712** |
| `neff_over_m` (N/M) | 0.13826 | 0.7418 |
| `n_over_m` | 0.14048 | 0.7316 |
| `neff` (no M) | 0.21068 | 0.0177 |

**Winner: `N_eff·(1+M)/M²`, R²=0.871, k=0.0426.** Physically this is the
image-space depth-of-focus `N_eff(1+M)` divided by the axial (longitudinal)
magnification `M²` to map back to object space — a steeper-than-`1/M` dependence
that the data prefer over the plain object-space `N_eff/M` (R²=0.74). The `neff`
control (no M term) is essentially uncorrelated (R²≈0), confirming the M
dependence is real and necessary.

## 4. Leave-one-out validation (predicted / documented step)

Fit k on all-but-one, predict the held-out sweep's step, ratio vs documented.

* **Overall: median 1.053, IQR [0.905, 1.303], n=22.**

By aperture:

| f | median | IQR | n |
|---|---:|---|---:|
| 4.0 | 0.548 | [0.485,0.610] | 2 |
| 5.6 | 0.828 | [0.727,0.996] | 4 |
| 6.3 | 1.064 | — | 1 |
| 8.0 | 1.030 | [0.995,1.240] | 5 |
| 11.0 | 1.183 | [1.014,1.359] | 4 |
| 13.0 | 1.182 | — | 1 |
| 16.0 | 1.201 | [1.173,1.408] | 5 |

By magnification bucket:

| M | median | IQR | n |
|---|---:|---|---:|
| <0.6 | 0.995 | [0.781,1.021] | 9 |
| 0.6–1.05 | 1.240 | [1.064,1.359] | 13 |

The residual structure: the estimator **under**-predicts at the widest apertures
(f/4–f/5.6, ratio ~0.5–0.8) and slightly **over**-predicts when stopped down
(f/11–f/16, ~1.2). This is the expected breakdown of the pure-geometric blur
model at large apertures, where diffraction and aberrations broaden the
through-focus response beyond the geometric cone — a known limitation, not a bug.

## 5. Comparison vs the scribe-blur calibrator

Ran `rail_calibration.calibrate_sweep` (the existing scribe-blur calibrator) on
the same 2026-05 sweeps, via phase1 wafer/scribe detection, fed the **same**
N_working as the DoF estimator. phase1 is expensive over NFS (and stalls on the
55mm AI-S framing), so each sweep was capped to a contiguous centred window of
≤41 frames (preserves consecutive-frame spacing → documented step unchanged) and
results were written incrementally; **n=10 sweeps completed** (100-400, 24-120,
70-180, Sigma 150, 55mm — spanning f/5.6–f/16, M=0.38–1.0). Head-to-head on those
identical 10 sweeps (ratio = estimated / documented step):

| estimator | ratio median | IQR | |log ratio| median |
|---|---:|---|---:|
| **DoF (this POC, LOO)** | **1.262** | [1.175, 1.388] | **0.294** |
| scribe-blur `calibrate_sweep` | 0.669 | [0.578, 0.749] | 0.403 |

* **The DoF estimator is closer to documented truth** (symmetric |log-ratio|
  0.294 vs 0.403).
* The two miss in **opposite directions**: scribe-blur systematically
  **under**-reads the step (median 0.67×), DoF slightly **over**-reads (1.26× on
  this Sigma/55mm-heavy M≈1 subset; 1.05× on the full bare set, §4). All scribe
  sweeps came back with `wide`/`unusable` verdicts (its own spread-based
  confidence), consistent with the module's documented caveat that its verdict is
  precision, not accuracy.
* This **explains the 2026-01-29 DoF/v1≈2.3× gap** (§7): scribe under-reads,
  DoF reads ~truth, so DoF/scribe ≈ 1/0.67 and larger where the scribe bias is
  worse. Where truth is known (2026-05), DoF wins.

_See `out_poc_dof_step/newer_scribe.csv`._

## 6. nan-rate diagnostic on the clean bare set

0/22 sweeps were dropped (0 % nan / out-of-range). The earlier high nan rate seen
on the *contaminated* full run came from accessory-config sweeps with very few
distinct rail positions and from multi-modal / plateau curves; on the clean bare
set every sweep has ≥9 distinct positions and a single clean through-focus peak,
so the Gaussian-of-defocus fit (>=25 %-of-peak selection, downward-parabola
requirement) succeeds for all. FWHMs ranged 5.2–17.3 frames (well inside the
[2, 60] validity window).

## 7. Application to 2026-01-29 (pre-rename) vs scribe-blur v1/v2

Applied the validated calibration (`neff_1pm_over_m2`, k=0.04255, fit on the
clean bare set) to 27 bare-lens sweeps from the 2026-01-29 manual-tier tree
(`<lens>/1_1/F<n>/`, all at M=1.0). N_working = folder f (already effective).
v1/v2 are the scribe-blur `rail_step_lookup_v1/_v2` from the prebuilt phase1
`per_shot_per_tile.csv` (`out_apertures_for_calibration/`), matched by normalised
`<lens>__<mag>__<F>` key. Full table: `out_poc_dof_step/older_estimates.csv`.

* **25/27 sweeps produced a DoF estimate** (2 nan: AF200 f/5.6 — 95-frame
  runaway FWHM; AF60 f/11 — 242-frame, no clean single peak).
* **DoF / v1 step ratio: median 2.35, IQR [1.95, 2.68].**
* **DoF / v2 step ratio: median 2.48.**

The DoF estimator gives **~2.3–2.5× larger** step-mm than the scribe-blur
calibrators on 2026-01-29. Example (Sigma 150, 1:1, f/11): DoF 0.0389 mm/frame vs
v1 0.0224, v2 0.0190. There is **no documented truth** for 2026-01-29, so this is
a disagreement, not an error on either side — but note (a) on 2026-05, where truth
exists, the DoF estimator is well-calibrated (LOO median 1.05) whereas (b) the
scribe-blur module's own docs warn its verdicts measure *spread, not accuracy* and
it "can be tightly clustered while systematically biased". If the DoF estimator's
2026-05 calibration transfers, it implies the scribe-blur calibrator
**under**-estimates the 2026-01-29 step by ~2.4× — consistent with the scribe
calibrator's known low-bias regime at high M / fine steps. This warrants a
documented-truth check on a 2026-01-29-style sweep before trusting either in
absolute terms (logged as the key open item).

## 8. Not yet tested / limitations

* **M > 1 with a bare lens** — none exists in this set; the steeper `1/M²`
  behaviour is fit only over M∈[0.385, 1.0]. Extrapolation to high-M tube
  configs is untested for the *bare* form (accessory configs would enter via the
  CSV N_working, a separate validation).
* **Wide-aperture underprediction** (f/4–f/5.6, ratio ~0.5–0.8) — geometric
  model breaks down where diffraction/aberration dominate the through-focus
  width. A diffraction-aware correction term is a follow-up.
* **55mm AI-S folder semantics** — guardrail-flagged (see §2); treated as
  effective per the dataset convention, but its widest sweep wasn't wide-open so
  this is assumed, not verified, for that lens.
* **ROI/decode choices** (central 40 %, 1/4-res decode) absorbed into k; k is not
  portable to a different ROI/decode. Same path used end-to-end here.

## Compute placement

Validation DATA (2026-05 sessions with documented `rail_position_mm`) lives on
NFS at `/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-{12,13}/`
(accessible from nufan; the 2026-05-12 tree is unrenamed = marked F-dirs, the
2026-05-13 tree is bellows-renamed and carries `effective_apertures.csv`). Runs
were executed on **nufan** via `ssh nufan 'direnv exec . uv run …'`. The
per-sweep FWHM is process-pooled and cached to `out_poc_dof_step/
newer_fwhm_cache.json` (keyed by session/slug/f_dir/n_frames) so N_working-only
re-runs are instant.
