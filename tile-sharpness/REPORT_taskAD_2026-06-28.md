# Accessory-config M validation + atlas-anchored resolution ranking

**Date:** 2026-06-28. **Scope:** the two follow-ups carried over from the
2026-06-27 cross-config thread — (A) validate/correct the magnification `M` used
for the accessory configs, and (D) bring the accessory/2:1 configs into the
cross-config resolution ranking. Existing data only (2026-01-29 + 2026-02-18
older-rig sweeps); no new acquisition.

> **TL;DR**
> - **(A) The handover's "reg_auto mislabels cols/rows and scales M 8-29%"
>   hypothesis is REFUTED.** Enumerating every phase-consistent label moves M by
>   ≤1.9%. atlas-M is independently *validated* — it reproduces known nominal M to
>   ~1.6% across M=0.385→2.0 (incl. the 100-400 zoom). So the atlas-vs-nominal gaps
>   are **nominal-label errors**, and atlas-M is the trustworthy M.
> - **The error is concentrated in the 100-400 + close-up-diopter family**:
>   MCON-35 +29% (a ratio inversion — nominal `1_1.16` should be ~`1.16_1`),
>   Canon 500D −16%, 6T −10%, 5T −8%. Macro + TC / extension configs match their
>   nominal labels well (mostly <±6%).
> - **(D) The resolution ranking uses the atlas-anchored 5-position method**, not
>   the blind per-tile pipeline (which collapses to centre-only at high M and
>   costs ~6 min/sweep). Trustworthy in the glass-limited regime; the sharp
>   macro+diopter configs OVER-READ at centre (>diffraction ceiling) — read their
>   corners / the ceiling there, not the centre number.

---

## A. M validation

### A.1 What was claimed vs what is true

The 2026-06-27 handover and the `reg_auto_label_scale_uncertainty` memo recorded
that reg_auto registered the 100-400 + diopter configs at clean 1.6-1.9px residual
yet atlas-M disagreed with the nominal path labels by 8-29%, and *hypothesised*
that a wrong absolute (col,row) **labelling** scales the grid (hence M) while still
fitting. Two probes test that directly:

**`probe_label_ambiguity.py`** — at the lowest-residual frame, enumerate every
phase-consistent (col_first, row_first) label, refit the affine, look at the M
spread:

| config | M_nominal | M_atlas | atlas-vs-nominal | label-family M spread |
|--------|-----------|---------|------------------|------------------------|
| MCON-35 | 0.862 | 1.113 | **+29%** | 1.7% (4 labels) |
| 6T | 1.270 | 1.140 | −10% | 1.9% |
| 5T | 0.840 | 0.771 | −8% | 1.8% |

The whole label family spans ≤1.9% in M — nowhere near the 8-29% gap, and the gaps
have inconsistent sign, so it is **neither labelling nor a constant anchor error**.

**`probe_anchor_validation.py`** — does atlas-M reproduce KNOWN nominal M on the 3
anchor sweeps?

| sweep | M_nominal | M_atlas | gap |
|-------|-----------|---------|-----|
| 100-400 @ 1:2.60 | 0.385 | 0.383 | −0.6% |
| AF200 @ 1:1 (the anchor) | 1.000 | 1.000 | 0% |
| Sigma+TC @ 2:1 | 2.000 | 2.033 | +1.6% |

The method is geometrically sound to ~1.6% across the range — including on the
**same 100-400 zoom** used by the diopter configs. **Conclusion: the diopter gaps
are nominal-label errors; atlas-M is the trustworthy M.**

### A.2 The real reg_auto failure mode: scale collapse, not mislabelling

Registering all 87 accessory combos surfaced the actual risk: one config
(AF200 + 5T/6T @ 2:1) returned atlas M ≈ −0.0003 at a *suspiciously low* 0.40px
residual with only 6 intersections — a **scale-collapse overfit** (few points + a
bad label let the affine shrink scale to ~0 and still fit). A too-low residual on a
few-point fit is a red flag, not reassurance. Guard atlas-M with an absolute sanity
bound (0.15 < M < 3.5) and a residual ceiling (~8px), and select the registration
frame robustly (sharpest-by-lapvar + a spread, keep the min refined residual) —
a quick reduced-res frame picker under-registered several configs (Canon 500D
rmse 18, 24-120+MCON-35 rmse 43) that the robust picker nails at 1-2px.

### A.3 Per-config validation table

`out_accessory_atlas/ranking_validation.csv` (full table). Configs flagged
`LABEL-SUSPECT` (|gap|>10% at a sound fit) are where the directory magnification
label should not be trusted:

| flag | gap | nominal | atlas-M | rmse | config |
|------|-----|---------|---------|------|--------|
| DEGENERATE | — | 2.00 | collapse | 0.3 | AF200 + 5T+6T / 6T+5T [2:1] (both) |
| LABEL-SUSPECT | **+29%** | 0.862 | 1.113 | 1.6 | 100-400 + Olympus MCON-35 [1_1.16] |
| LABEL-SUSPECT | **−16%** | 1.070 | 0.898 | 2.1 | 100-400 + Canon 500D [1.07_1] |
| LABEL-SUSPECT | **−10%** | 1.270 | 1.140 | 1.9 | 100-400 + Nikon 6T [1.27_1] |
| (notable) | −8% | 0.840 | 0.771 | 1.8 | 100-400 + Nikon 5T [1_1.19] |
| reg-failed | — | 1.6–2.0 | — | — | Sigma 150 +5T+6T/+6T/+6T+5T; Sigma 105 +5T+6T/+TC-2001 [2:1] |

**Every other one of the 51 configs matches its nominal label within ±7%
(median |gap| ≈ 1%).** The label error is entirely concentrated in the
**100-400 + close-up-diopter family** (MCON-35 is a clear ratio inversion: atlas
M=1.11 ≈ the 6T's 1.14, not the labelled 0.86). Macro + TC / extension labels are
trustworthy. The high-M Sigma stacked-diopter configs (M 1.6–2.0) and the 2:1
AF200 stacks do not register (sparse/ambiguous wafer fragment at high M) — coverage
gap, not a label issue.

The corrected-M manifest (`wafer-atlas/scripts/atlas_m_manifest.csv`, 47 trusted
rows, m_lookup `vision_measured_mag` schema) lets any future blind-pipeline run
pick up the atlas-measured M via `--manifest`. Untrustworthy registrations are
omitted so they fall back to the path label.

---

## D. Atlas-anchored resolution ranking

### D.1 Method and why not the blind pipeline

The blind per-tile `characterise` pipeline was measured at ~6 min/sweep and
**collapses to centre-only at M≈1.1** (the high-M scribe under-coverage that
`atlas_corner_mtf.py` was built to solve). So the ranking generalises the
atlas-anchored method (`atlas_rank_accessory.py`): register once per (lens, mag)
via reg_auto (reused across that config's apertures — framing is fixed within a
session), then read MTF50 at centre + 4 corners, each at THAT position's own
best-focus shot (field-tilt-aware). Subject lp/mm uses the atlas-measured M; the
diffraction ceiling (`optics.py`, N_eff = N·(1+M)) tags each position's regime.

### D.2 Caveats (carry these with every number)

- **MTF50 over-reads above the diffraction ceiling** (the 2026-06-27 finding,
  also in SHARPNESS_METRICS.md). Trust values comfortably *below* the ceiling
  (`glass-ltd`); a value at/over the ceiling (`OVER-READ`) is a measurement
  artifact — read the ceiling instead. The sharp macro+diopter configs (105/200)
  over-read at centre at F8/F11.
- **Per-position scribe noise ≈ ±5 lp/mm**; fine corner rankings within that band
  are not separable. Relative comparison across configs is robust (shared method).
- 2:1 stacked-diopter AF200 configs do not register (scale collapse) and are
  excluded.

### D.3 Ranking

`out_accessory_atlas/ranking_resolution.csv` (full table, per config × aperture).

**Trustworthy F8 ranking** (rows reading *below* the diffraction ceiling —
glass/focus-limited, so the lp/mm is real; sorted by centre subject lp/mm):

| M | N_eff | ceiling | centre | corner | unif | config |
|---|-------|---------|--------|--------|------|--------|
| 1.26 | 18.1 | 51 | 50.1 | 33.9 | 0.68 | Sigma 105 + 5T [1.27:1] *(at ceiling)* |
| 1.45 | 19.6 | 54 | 47.7 | 41.9 | 0.88 | Sigma 150 + TC-1401 [1.4:1] |
| 1.00 | 16.0 | 46 | 44.8 | 21.0 | 0.47 | Sigma 150 + TC-1401 [1:1] |
| 1.12 | 16.9 | 49 | 42.6 | 22.0 | 0.52 | 70-180 + 5T+6T [1.14:1] |
| 1.46 | 19.7 | 54 | 37.8 | 29.3 | 0.78 | Sigma 105 + 6T [1.5:1] |
| 1.00 | 16.0 | 46 | 35.5 | 23.6 | 0.67 | 70-180 + 6T [1:1] |
| 1.65 | 21.2 | 57 | 33.3 | 31.8 | 0.95 | Sigma 105 + 6T+5T [1.7:1] |
| 1.00 | 16.0 | 46 | 33.0 | 42.7 | 1.29 | AF200 + Kenko 1.4× [1:1] |
| 0.77 | 14.2 | 40 | 30.2 | 20.6 | 0.68 | 100-400 + Nikon 5T [≈0.77×] |
| 1.11 | 16.9 | 48 | **28.9** | 19.4 | 0.67 | 100-400 + Olympus MCON-35 [≈1.11×] |
| 1.14 | 17.1 | 49 | **23.8** | 17.9 | 0.75 | 100-400 + Nikon 6T [≈1.14×] |
| 0.90 | 15.2 | 44 | 20.7 | 20.1 | 0.97 | 100-400 + Canon 500D [≈0.90×] |

(Full table incl. the 24-120 configs in `ranking_resolution.csv`.)

**Headline:** at the 100-400's working magnification, **MCON-35 (28.9) > 6T (23.8)
≈ +21% at centre** — reproduces the 2026-06-27 atlas_corner figure exactly; 5T sits
between. Among trustworthy configs the **Sigma macros + a single TC/diopter** and
the **70-180 + diopter** hold the most real resolution; corner uniformity is
0.3–0.7 for most (corners markedly softer — field-dependent glass/diopter limits,
the same "corners are glass-limited" pattern as the bare lenses).

**Two regimes to respect (do NOT read these as resolution):**
- **Sharp macro + diopter at F8** (105 VR/Sigma, 200 + 5T) report centre 86–94 lp/mm
  against a ~50–56 ceiling — headroom 1.6–1.7, physically impossible. These are
  **LSF over-reads**; their real centre is at/below the ceiling. Use corners
  (glass-limited, trustworthy) to separate them.
- **F11 over-reads almost universally** (headroom 1.0–2.4): at these magnifications
  N_eff is f/17–f/33, so the diffraction ceiling falls to ~22–45 lp/mm-subject and
  the measurement floats above it. Practically, **F11 buys no real resolution over
  F8 for any of these high-M configs** — it is the diffraction/empty-magnification
  regime. F8 is the aperture to compare on.

---

## E. Follow-ups executed 2026-06-28b

### E.1 LSF over-read — diagnosed; the documented hypothesis was wrong

SHARPNESS_METRICS.md / the 2026-06-27 handover attributed the over-read to
`_mtf50_from_lsf` normalising to the spectral **peak** (DC dropped) plus a noise
floor in the differentiated LSF. **Both were tested and neither is the cause:**
- DC-normalisation (+ a peak-centred Hann window) was implemented and measured on
  the real fixtures — it moved AF200 1:1 F11 centre from 0.187 → 0.196 cy/px (the
  *wrong direction*) and was reverted. The ESF is clean and monotonic (no noise
  plateau, no JPEG-sharpening overshoot), so windowing/denoising has nothing to
  bite on.
- The real cause is **left/right trough-wall asymmetry**: on AF200 1:1 F11 the
  LEFT wall reads 0.146 cy/px (≈ the 0.145 ceiling — physical) while the RIGHT
  reads 0.226 (1.6× over); the per-edge **mean** then over-reads at 0.186. (This
  also explains why the earlier sub-pixel-binning POC over-read — same asymmetry.)

### E.2 Mitigation: `combine="min"` (opt-in)

Added a `combine` parameter to `lsf_mtf50` (`methods/lsf.py`). Default stays
`"mean"` so every existing number and all tests are unchanged (117 pass, +1 new).
`combine="min"` takes the lower (cleaner, conservative) per-edge MTF50; the atlas
ranking driver now uses it. Effect on the over-read count (centre headroom ≥ 1.0):

| aperture | mean | → min |
|----------|------|-------|
| F8  | 11/38 | **8/38** |
| F11 | 40/44 | **28/44** |

A real reduction (esp. F11), but **not a full fix**: the sharpest macro+diopter
configs over-read on *both* walls (e.g. 105 VR + 5T+6T still 1.6× over at F8), so
`min` can't rescue them. Those centres remain `OVER-READ` — read corners/ceiling.
Closing the residual needs better edge extraction (symmetric sub-pixel ESF), a
larger effort.

### E.3 Bare macros measured → unified ranking

`enumerate_bare_configs.py` + the same atlas-anchored driver measured the 15 bare
native lens combos (105 VR, Sigma 150/105, AF200, AF 60mm, the five 55mm primes,
70-180, bare zooms) with `combine="min"`, so bare and accessory now sit on **one
axis** (`out_accessory_atlas/unified_ranking.csv`). Trustworthy (glass/diffraction-
limited) **F8** picture, subject lp/mm at centre:

| tier | configs (centre lp/mm) |
|------|------------------------|
| modern bare macros | Sigma 150 **41.6**, Sigma 105 **40.2**, 105 VR **39.5** (unif 0.90), AF 60 38.1, AF200 35.8 (unif 0.88) |
| macro + single TC | Sigma 150 + TC-1401 40.6, Sigma 105 + TC-1401 40.5 |
| 70-180 + diopter | 25–38 |
| vintage 55mm primes | Auto 258263 31.6, AIS 287318 24.0, AIS 537016 21.7, Auto 262711 21.3 |
| 100-400 + diopter | 5T 28.3, MCON-35 26.3, Canon 500D 20.7, 6T 17.7 |

Takeaways: bare modern macros and macro+single-TC lead; the **vintage 55mm primes
and the 100-400 + close-up-diopter combos are the resolution-limited tail**; F11
stays diffraction/over-read across the board (F8 is the aperture to compare on).
Sharp macro+diopter centres still `OVER-READ` (see E.2) — rank those on corners.

### E.4 Root cause CONFIRMED: groove emboss (not the estimator) — true edges read physical

User insight (2026-06-28): a scribe is a **groove**; under oblique lighting one wall
is lit (possibly a specular glint → reads artificially sharp) and the other is in
shadow (soft). So the L/R "asymmetry" is a lit-edge vs shadow-edge — the groove is a
poor MTF target. POC (`wafer-atlas/scripts/poc_true_edge_feature.py`) measured the
atlas's designated **true slanted-edge feature** (die type (0,3), source 4D) vs the
groove scribe at the same field point, against the ceiling:

| config | ceiling | groove scribe | true-edge feature |
|--------|---------|---------------|-------------------|
| AF200 1:1 F11 | 0.145 | 0.148–0.197 OVER | **0.10–0.11 ✓** |
| Sigma150 1:1 F8 | 0.197 | erf 0.260 OVER | **0.10–0.11 ✓** |
| 105VR+6T F8 | 0.168 | 0.272–0.362 OVER | **0.10 ✓** |

The groove over-reads everywhere; the true edge reads ≤ ceiling everywhere —
**confirming the emboss hypothesis**. The `combine="min"` (shadow-wall) mitigation
was on the right track but partial because both groove walls can carry the artifact.

Caveats from the POC: the true-edge reading is ~constant 0.10 cy/px across all three
configs (no sharpness discrimination) → this single designed feature is
intrinsic-width / focus-limited and is **sparse** (1 of 16 die types). So it proves
the mechanism but is not itself a usable metric.

**Path forward (de-risked by this POC):** rebuild the resolution metric on TRUE
reflectance edges with broad field coverage — **bond-pad edges** (catalogued in
14/16 die types, `feature_inventory.bond_pads`) and/or die-surface contrast edges —
using the super-resolved + parametric estimator already built
(`methods/slanted_edge.py`), selecting a sharp in-focus pad edge near each field
target. Validate every reading against the diffraction ceiling. This replaces the
groove-scribe LSF for centre resolution; the groove can stay only as a coarse
fallback where no true edge is in FOV.

## F. Bond-pad-edge metric — built, validated, and REJECTED (2026-06-28c)

The §E.4 "path forward" (build the resolution metric on bond-pad reflectance
edges, 14/16 die types) was implemented and **validated against the diffraction
ceiling on the three known-ceiling configs. It FAILED the validation gate; it is
not shipped.** The negative result is the deliverable for this follow-up.

### F.1 What was built

- **Single-STEP estimator** (`methods/slanted_edge.py`). A groove is a two-wall
  TROUGH (`_split_walls`); a metal→substrate pad edge is one monotone STEP. Added
  `mtf50_step_erf` (crop the super-res ESF to its dominant step, drop a second
  neighbouring-pad step, fit one erf), `mtf50_step_iso` (ISO-12233 cross-check on
  the full window), and `mtf50_auto` (dispatch step vs trough from ESF shape).
  Groove behaviour unchanged. A **step-quality gate** (on the FULL super-res ESF)
  rejects the artefacts the pad regions produce: bright-trace **ridges**
  (rise-then-fall), troughs, low-contrast/noise, and erf fits **railing at the
  σ-floor** (0.30 px → an unresolved/aliased pixel edge). Tests:
  `tests/test_slanted_edge.py`, 13 cases (σ-recovery, sharp>soft, direction
  invariance, erf≈iso, step/trough discrimination, auto-dispatch, second-step
  trim, ridge/noise rejection, groove back-compat). **Full suite 130 passed.**
- **Pad-edge selector** (`methods/pad_edge.py`). Enumerates in-FOV bond-pad
  regions from the atlas (`task17` geometry), and within each returns *ranked*
  slanted contrast-edge candidates (2–15° off axis); the caller takes the longest
  one that **passes the step gate** — so it skips internal pad-array structure and
  only accepts a genuine clean step.
- **Driver + report builder**: `scripts/atlas_rank_padedge.py` (mirrors
  `atlas_rank_accessory.py`: register-once-per-combo, shard/env support) and
  `scripts/build_padedge_report.py`. Built but **not run for ranking** (see F.3).

### F.2 The make-or-break validation (the reason it is rejected)

`wafer-atlas/scripts/diag_padedge_explore.py`, gate ON, best-focus per position,
on the three configs whose ceiling is known. Result — gate-passing pad-edge erf
MTF50 (cy/px) vs ceiling:

| config | ceiling | gate-passing positions (of 5) | pad-edge erf | vs ceiling |
|--------|---------|-------------------------------|--------------|------------|
| AF200 1:1 F11    | 0.145 | **1** (BR) | 0.268 (σ≈0.70 px) | **1.85× OVER** |
| Sigma150 1:1 F8  | 0.197 | **1** (centre) | 0.294 (σ≈0.64 px) | **1.49× OVER** |
| 105 VR + 6T F8   | 0.168 | **0** | — | no coverage |

**Both validation criteria fail.** (a) Every reading that survives the step gate
**over-reads the ceiling 1.5–1.85×** — physically impossible, *worse* than the
groove (which at these same points reads ≤ ceiling). (b) Discrimination is moot:
only **2 of 15** field positions yield any reading at all (105VR+6T yields none),
so there is no broad-coverage signal to discriminate with — the opposite of the
goal. The remaining positions are rejected because their longest slanted edges are
either fine periodic structure / bright-trace ridges or flat noise.

**Why** (root cause, with image proof in `wafer-atlas/scripts/diag_padedge_crops/`
and the raw-pixel/ESF dumps from `diag_padedge_debug.py`): the atlas
`feature_inventory.bond_pads` "regions" are not large isolated metal plates with a
single clean boundary — they are **dense periodic pad/line ARRAYS** (catalogued
pitches 11–173 px in the 0129 frame; the finest are below the lens's resolution at
these magnifications). The longest straight contrast edge inside such a region is a
pad-row/trace edge that is **aliased** (sampled below Nyquist → artificially sharp,
σ≈0.6–0.7 px), so it over-reads exactly like the lit groove wall — the *same*
specular/aliasing failure mode the task warned about, just from periodicity rather
than emboss glint. The pad-FIELD outer boundary (a true array→substrate step) is
lower-contrast than the internal periodicity, so Hough never prefers it.

**The estimator itself is sound** — this is geometry, not a code bug. The same
`mtf50_step_erf` on the atlas's *designed* slanted-edge feature (the POC's
known-good true edge, die (0,3)) reads **≤ ceiling on all three configs**
(`diag_designed_edge_check.py`): AF200 1:1 F11 **0.125** (ceil 0.145), Sigma150 1:1
F8 **0.130** (ceil 0.197), 105VR+6T F8 **0.099** (ceil 0.168) — matching the POC's
0.10–0.13 cy/px. A genuine clean reflectance edge reads physical with this exact
estimator; the pad arrays do not. (As §E.4 noted, that designed feature is itself
non-discriminating and sparse, so it confirms the mechanism but can't be the metric.)

### F.3 Decision — no re-ranking shipped

Per the task's explicit instruction ("Do not silently ship a metric that fails
(a)/(b)"), the production unified re-ranking was **not run**: a metric that
over-reads on 2/15 positions and is blank on 13/15 would be strictly worse than
the existing groove-`min` ranking, not better. There is no
`unified_ranking_padedge.csv`; the groove-`min` `unified_ranking.csv` (§E) remains
the current best, with its documented OVER-READ caveat at sharp macro+diopter
centres. MCON-35 > 6T (centre) therefore stands on the groove ranking as before
(§D.3 / §E.3); the pad-edge metric produced no centre numbers to re-confirm it.

### F.4 Honest assessment / what didn't work

- **Bond-pad edges are not viable broad-coverage MTF targets on this wafer.** They
  are periodic arrays, not isolated reflectance steps. Tried: longest-edge (locks
  onto ridges → 0.25–0.62 over-read, the σ-floor); + step-quality gate (correctly
  rejects ridges/noise, but then 13/15 positions go blank and the 2 survivors are
  aliased array edges that still over-read). Both fail.
- **Die-boundary / non-metal edges**: the die/cell boundary IS the groove scribe,
  already known to over-read (§E.4). The only true-reflectance edge that reads
  physical is the **single designed slanted-edge feature** — but it is sparse
  (1–2 die types in FOV) and intrinsic-width-limited (≈0.10–0.13 cy/px, **does not
  discriminate** sharpness; §E.4). So it proves the mechanism but cannot rank.
- **Conclusion: no clean, broad-coverage, sharpness-discriminating MTF target
  exists in the current 2026-01/02 wafer dataset.** A physically-calibrated
  centre/corner resolution metric needs a *new acquisition* with a proper
  slanted-edge / knife-edge target (a single high-contrast straight metal step,
  several per field position), not a re-mining of the wafer's periodic structures.
  The deliverables left behind (single-step estimator + gate + selector + driver,
  all tested) are the reusable half — they will measure such a target correctly
  the moment one is captured; what is missing is the target, not the tool.

### F.5 Caveats on the validation itself

- Sigma150's registration rmse was 4.1 px (vs 1.5 px for the others); its M=1.028
  and ceiling are still reliable to ~few %, and the conclusion (1.49× over) is far
  outside that band.
- The gate thresholds (`min_contrast=12 DN`, `max_overshoot_frac=0.25`,
  σ-floor×1.05) were set to be *permissive* — they let through the 2 aliased
  survivors rather than over-pruning, so the negative result is not an artefact of
  an over-tight gate. Loosening them only readmits more ridges (larger over-reads);
  tightening them drives coverage to 0/15.
- Tooling note: the worktree's `tile-sharpness/pyproject.toml` pins the sibling
  `lens-test-detect-core` at `../../`, which doesn't resolve from inside a
  `.claude/worktrees/` worktree, so `uv run` re-resolution fails there. Tests/CPU
  jobs were run with the prebuilt host venv + `PYTHONPATH=.../tile-sharpness/src`
  (worktree src wins over the editable install); `pytest` → 130 passed.

## G. Periodic-FFT metric (the WIN) + isolated-edge closure + the metric suite (2026-06-29)

### G.1 Periodic-FFT — a physically-valid SPANNING relative metric
On the atlas's FFT-marked features (cyan `use_for_fft` blocks 4B/4C/2B/2C + magenta
bond-pad arrays — the intent layer no measurement code had consumed), a **bounded
Michelson contrast `C = 2·|F(f₀)|/|F(0)|`** at the feature's *sub-element* pitch:
`methods/periodic_fft.py`, `scripts/atlas_periodic_fft.py`, ceiling at arbitrary
frequency via `optics.diffraction_mtf_at`. Results: **0 / 1664 region-reads over the
diffraction ceiling** (it physically can't exceed 1 and under-reads to 0 past cutoff
— the opposite of the groove-LSF's 1.5–1.8× over-read), focus-tracking, discriminates
sharp/soft (2.6–15×), and **reproduces the groove tiers + MCON-35 > 6T**, now
physically valid. **This is the cross-config metric to use.** Caveats: it is
*relative*; compare configs **at a common subject frequency** (raw C is M-confounded:
higher M samples a lower subject frequency where C is naturally higher); read the
**sub-element pitch**, not the atlas super-pitch (which sits below cutoff → carries no
MTF info). Both magenta (broad coverage) and cyan (cleanest separation) work.

### G.2 The isolated-edge / absolute-lp/mm route is definitively CLOSED on this data
Three honest negatives, all the same root cause — **no clean flat reflectance edge
exists on the wafer**:
- **Bond-pad "edges"** (§F): dense periodic arrays → alias → over-read.
- **Designed 4D bar** (`methods/long_edge.py`, recentred ISO long-edge): the user's
  height hypothesis was tested and **refuted** — MTF50 is flat with edge length
  (~0.10 cy/px floor is intrinsic), and the bar is itself a short lit/shadow emboss
  (over-reads sharp / floors shadow).
- **2B "bright pads"** (`methods/pad_long_edge.py` + `diag_2b_*`): masking the ROI to
  the pad edge **worked** (solved the grating distraction), but the pads are **recessed
  metal plates in a dark trench** — the lit edge carries a specular rim (over-reads
  0.9–2.1× ceiling), the shadow edge floors and ranks INVERTED, and the open field is
  only ~24–36 px wide. The estimators + `isolation_clearance`/specular gate are sound
  (they read the designed edge ≤ ceiling and reject the bad ones); the *target* is the
  problem. **Absolute lp/mm requires a new acquisition** of a flat, open-field
  knife/slant edge (see `MTF_TARGET_ACQUISITION.md`).

### G.3 The metric suite — coverage × reliability, and the calibration plan
| metric | coverage | reliability / interpretability |
|--------|----------|-------------------------------|
| **periodic-FFT contrast** | all configs (broad) | bounded, ceiling-valid; **relative**, common-f₀, sub-element pitch — the spanning backbone |
| diffraction ceiling (`optics`) | all configs | physics-exact **upper bound**, not a measurement |
| maze-FFT | M ≳ 0.7 | independent periodic check (Tier-B cross-validator) |
| groove-LSF `min` | all configs | over-reads — cross-check only |
| masked slant/knife edge → absolute lp/mm | **none yet** (needs new shoot) | most interpretable; will be partial (open-field edge in FOV) |

Design (endorsed): one **spanning** metric (periodic-FFT) carries the full
cross-config ranking; **partial, more-interpretable** metrics validate it over their
overlap and could **calibrate** it. Calibration is physically principled because
`C = k_feature · MTF(f₀)` — k_feature is a *target* constant, so an absolute anchor
(the future knife-edge MTF curve, and/or the parameter-free ceiling at the
diffraction-limited end) pins k_feature in the overlap, after which `C/k_feature` is
absolute MTF(f₀) everywhere that feature appears (multiple features → MTF sampled at
several frequencies → interpolate to absolute MTF50). **From existing data the only
absolute anchor is the ceiling (diffraction-limited end); the glass-limited anchor
awaits the new acquisition.** Flag every config as measured-absolute /
calibrated-absolute / ranked-only.

## Artifacts

- `wafer-atlas/scripts/accessory_configs.csv` — config inventory (282 sweeps).
- `wafer-atlas/scripts/atlas_m_results.csv` — atlas-M for all 87 combos vs nominal.
- `wafer-atlas/scripts/atlas_m_manifest.csv` — corrected-M manifest (m_lookup schema).
- `wafer-atlas/scripts/probe_label_ambiguity.py`, `probe_anchor_validation.py` — the A probes.
- `tile-sharpness/scripts/atlas_rank_accessory.py` — the D ranking driver (combine='min').
- `tile-sharpness/scripts/build_{ranking,unified}_report.py` — table builders.
- `wafer-atlas/scripts/enumerate_bare_configs.py` — bare-config inventory → `bare_configs.csv`.
- `tile-sharpness/out_accessory_atlas/ranking_{validation,resolution}.csv` — accessory tables (mean).
- `tile-sharpness/out_accessory_atlas/{accessory,bare}_ranking_min.csv`, `unified_ranking.csv` — min-method + unified bare+accessory ranking.
- **(F) pad-edge metric (built, validated, rejected):**
  `tile-sharpness/src/tile_sharpness/methods/slanted_edge.py` (single-step path +
  quality gate), `.../methods/pad_edge.py` (gated selector),
  `tile-sharpness/tests/test_slanted_edge.py` (13 tests),
  `tile-sharpness/scripts/atlas_rank_padedge.py` + `build_padedge_report.py`
  (driver/report, unused — no ranking shipped),
  `wafer-atlas/scripts/diag_padedge_explore.py` (the validation),
  `.../diag_padedge_debug.py` (ESF/raw-pixel dump), `.../diag_designed_edge_check.py`
  (estimator-soundness check), `.../diag_padedge_crops/` (image proof the regions
  are periodic pad arrays).

## Follow-ups (remaining)

- **Residual LSF over-read**: `combine="min"` cut over-reads (F11 40→28, F8 11→8)
  but the sharpest macro+diopter centres over-read on *both* trough walls. Closing
  it needs symmetric sub-pixel ESF extraction (ISO-12233 binning across the slant),
  not a normalisation tweak — the DC/noise-floor hypothesis is disproven (§E.1).
- Recover the two **2:1 AF200 stacked-diopter** + high-M Sigma stacked configs
  (registration collapses/fails) via manual anchors / better fragment disambiguation.
- Optionally re-measure the bare cohort at **F8 only** with more scribes per position
  to beat the ±5 lp/mm corner noise (the vintage-55mm ordering is within that band).
- **True-edge metric needs a new capture (§F).** The bond-pad route is exhausted
  (periodic arrays, not isolated steps → over-read or no coverage). To get a
  physically-calibrated, sharpness-discriminating centre/corner metric, capture a
  dedicated slanted-edge / knife-edge target (single high-contrast straight metal
  steps, several per field zone). The single-step estimator + gate + selector are
  ready to consume it.
