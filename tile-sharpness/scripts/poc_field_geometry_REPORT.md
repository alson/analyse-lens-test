# POC 4 — FIELD CURVATURE from the best-focus surface (tilt removed)

**Date:** 2026-07-01 · **Cohort:** older-rig 2026-01-29, 10 configs, 724 patches
**Driver:** `scripts/poc_field_geometry.py` · **Helpers:** `src/tile_sharpness/field_geometry_focus.py`
**Outputs:** `out_poc_field_geometry/{per_config_field_geometry.csv, joined_per_patch.csv, map_*.png}`

## Idea & method (tilt is corrected, never reported)

Each wafer patch has a best-focus axial position `mu_mm` (POC 3 Gaussian
peak-centre through the focus stack) at a field position `(px, py)` in sensor
pixels (POC 1 `field_geometry`, frame centre `(4128, 2752)`, half-diagonal
4962 px). Mapping `mu_mm` over `(px, py)` gives a SURFACE.

The **plane TILT** of that surface is rig / sensor-vs-subject-plane alignment
and — from a single config — is degenerate with any lens-induced tilt, so it is
**NOT a lens property**. It is regressed out and never reported. The surface is
fit JOINTLY:

    mu_mm ≈ c + a·x + b·y + k·(x² + y²)

The linear plane `(a, b, c)` (the tilt) is fit SIMULTANEOUSLY with the quadratic
`k`, so `k` is orthogonalised against the tilt. **Every downstream number comes
from `k` or from the residual of this full fit — never from a raw
corner-minus-centre of the un-detrended surface** (which would carry the tilt).
The sag is `k · px_corner²`, derived from the fitted quadratic coefficient.

All results are on the **coverage-CLEAN** subset (`coverage_flag == ok` AND not
`fwhm_imputed`); N_used / N_excluded reported. `step_low_confidence` (DoF step at
M>1.10) makes the ABSOLUTE µm / radius uncertain (step is a global scale) — the
DoF-normalised sag is the step-free primary metric.

## Per-config field curvature (tilt removed, coverage-clean)

Primary = **`sag_dof`** = (tilt-removed centre→corner focus shift) / median
through-focus FWHM (dimensionless, step-calibration-free, M-robust — "the corner
sits N depths-of-field from the centre"). Sign: −ve = corners focus NEARER the
camera (bowl toward camera), +ve = corners farther.

| config | M | step_lowconf | N used/excl | **sag_dof** | sag µm | sign | radius mm | RMS resid µm | vertex est.? | vtx offset (×½-diag) |
|---|---|---|---|---|---|---|---|---|---|---|
| 100-400 + MCON-35 1:1.16 | 1.12 | yes | 47/22 | **−0.34** | −417 | corners nearer | −396 | 91 | yes | 0.56 |
| NIKKOR Z MC 105 | 1.00 | yes | 92/0 | **−0.24** | −332 | corners nearer | −546 | 52 | no | 1.10 |
| 200 +5T+6T 2:1 | 2.06 | yes | 15/1 | **−0.03** | −20 | corners nearer | −5722 | 55 | no | — |
| 200 +6T 1.7:1 | 1.72 | yes | 27/1 | **−0.20** | −173 | corners nearer | −749 | 88 | no | 0.75 |
| 200 IF-ED 1:1 | 1.00 | no | 85/3 | **+0.08** | +110 | corners farther | +1429 | 387 | no | 7.90 |
| 60 f/2.8D | 1.00 | yes | 85/0 | **+0.21** | +285 | corners farther | +592 | 124 | no | 2.06 |
| 55 AIS 287318 | 1.00 | no | 84/1 | **−0.80** | −1086 | corners nearer | −137 | 55 | yes | 0.47 |
| Auto 55 f/3.5 209088 | 0.99 | no | 74/19 | **−0.43** | −588 | corners nearer | −246 | 98 | yes | 0.45 |
| Sigma APO 150 | 1.03 | yes | 83/0 | **+0.20** | +270 | corners farther | +595 | 49 | no | 2.77 |
| Sigma 105 | 1.05 | yes | 85/0 | **−0.06** | −80 | corners nearer | −1920 | 84 | no | 3.18 |

**Readings.** The 55 AIS 287318 has the strongest field curvature (−0.80 DoF; the
corner best-focus sits 0.8 depths-of-field nearer the camera than the centre) —
a clean, tight bowl (RMS 55 µm, radial profile hugs the fitted quadratic). The
native macros (Sigma 150 +0.20, 60mm +0.21, MC 105 −0.24) show mild curvature.
The 200 IF-ED clean sag is now a sane +0.08 DoF (was contaminated 8500 µm before
detrend+coverage — see below); its RMS 387 µm is the largest, i.e. the least
regular field even after cleaning. The 200+5T+6T at 2:1 is essentially flat
(−0.03 DoF) but on only 15 patches.

## Detrend validation — pure tilt yields ~zero curvature

Unit test `test_pure_tilt_yields_zero_curvature_and_residual`: a synthetic PURE
plane (`mu = 3 + 2e-4·x − 1.3e-4·y`, no curvature) fed to
`fit_curvature_detrended` returns `k ≈ 0` (|k| < 1e-12), `sag ≈ 0` (< 1e-4 µm),
`sag_dof ≈ 0`, and RMS residual < 1e-6 µm — the plane is fully absorbed, nothing
leaks into curvature. `test_bowl_plus_tilt_recovers_sag_independent_of_tilt`:
the same known bowl `k_true` is recovered to 1e-6 relative for tilts of
`0, +2e-4, −3.5e-4` — the sag is invariant to the superposed tilt. So tilt
cannot contaminate the curvature.

## Why detrend + coverage exclusion both matter (200 IF-ED)

Before this revision, the 200 IF-ED "all patches" surface reported a nonsense
+8508 µm sag — 3 truncated patches carried an extrapolated `mu_mm` down to
−93 mm. Both fixes now apply: coverage-clean drops those 3 patches, and the sag
comes from the fitted quadratic `k` (tilt removed) rather than corner-minus-
centre. Clean sag is +110 µm (+0.08 DoF). This is the same under-coverage
artifact POC 1 flagged; it is fully contained.

## Decentering — tilt-independent, only where estimable

A shifted paraboloid `c + k·((x−x0)²+(y−y0)²)` expands to linear terms
`−2k·x0, −2k·y0` — **algebraically identical to a plane tilt**. So from ONE
config a plane tilt is INDISTINGUISHABLE from a vertex-shifted bowl: the vertex
`(x0,y0) = (−a/2k, −b/2k)` is a valid decentering indicator ONLY when it is
geometrically sane (curvature strong enough AND the vertex lands inside/near the
frame, offset ≤ 0.60 × half-diagonal). Otherwise the "vertex" is the rig tilt in
disguise and is flagged `estimable=False`.

Under that rule, **4 of 10 configs have an estimable vertex**: 55 AIS 287318
(0.47), Auto 55 209088 (0.45), MCON-35 (0.56) — vertices inside the sane region;
the rest have vertices flung 1.1–7.9 × half-diagonal outside the frame (tilt
dominated). So a robust tilt-independent decentering vector is only readable for
the configs with strong, well-centred curvature. For the others, **clean
decentering (and astigmatism) needs the per-orientation sagittal/tangential
best-focus extract or a cross-config solve, neither of which this dataset
provides** — see below. First-moment L-R/T-B asymmetries were dropped entirely
(they ARE the tilt being removed).

## Astigmatism — NOT available

A focus-position sag-vs-tan split needs a best-focus `mu_mm` per edge
ORIENTATION per patch. POC 3 collapses the stack to ONE `mu_mm` per patch, and
the fieldtag shards carry only sagittal/tangential AMPLITUDE. Reported
`available=False`.

## Maps

Per config, `out_poc_field_geometry/map_<slug>.png` — LEFT: the tilt-removed
best-focus residual over the frame (RdBu about the median, frame centre `+`,
curvature vertex `×` when estimable); RIGHT: the radial best-focus-vs-field-
height profile with the fitted quadratic overlaid, so the curvature is visible
without the plane dominating. Example (55 AIS 287318): the patches trace a clean
bowl hugging the fitted −1086 µm quadratic.

## Limitations

`mu_mm`'s absolute mm scale is DoF-estimated (no documented rail step for any
2026-01-29 sweep); `sag_dof` is chosen precisely because it is step-free. The
2026-05 documented-step sweeps would pin the absolute µm/radius, but POC 1
emitted per-patch `(px,py)` field geometry only for the 2026-01-29 cohort, so
that validation isn't runnable here — producing 2026-05 fieldtags is the natural
next step. Vertex-offset decentering and astigmatism both need inputs this
dataset lacks (cross-config or per-orientation extract).

## Unit tests

`tests/test_field_geometry_focus.py` — 9 tests, all passing: pure-tilt → zero
curvature + zero residual; pure-tilt → vertex not reported; bowl+tilt → sag
recovered independent of tilt; sag sign (bowl/dome); DoF-normalised sag scaling;
radius from k (sensor-mm frame); vertex offset recovered (no tilt); vertex
flagged not-separable when tilt dominates; astigmatism unavailable.
