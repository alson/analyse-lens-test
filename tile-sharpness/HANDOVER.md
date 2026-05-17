# Sharpness assessment POC — session handover

State as of 2026-05-17.

> **2026-05-17 update — validation runs + rail-step calibration.**
>
> 1. **Tasks 2/4/5 + maze-pitch validation ran.** Task 5 (AF 200/4D
>    + 5T + 6T @ 2:1 F11) centre MTF50 = 24.76 lp/mm vs predicted
>    23 ✓. Task 2 (100-400 @ 0.385× F11) = 10.4 vs predicted 33 —
>    low-M LSF algorithmic limit (narrow trough, too few ESF samples
>    per edge). Task 4 (Sigma + TC-2001 @ 2:1 F11) = NaN — separate
>    pipeline bug at `phase1.py:192` (`cross_section`'s fixed
>    `half_window_px=24` is M-blind; at M=2.0 the predicted scribe
>    FWHM fills the window and `_split_to_edge_lsfs` rejects 71/77
>    shots).
>
> 2. **`MAZE_PITCH_UM=13.0` is cohort-stable** across AIS (M=1.0),
>    Sigma+TC2001 (M=2.0), AF200+5T+6T (M=2.06). Best-fit pitch
>    spread ±3.5 % within FFT bin width. Safe to publish absolute
>    lp/mm with the existing constant.
>
> 3. **Rail-step-mm calibration landed** (`src/tile_sharpness/
>    rail_calibration.py`). Task 7 (subject-tilt sanity check) is
>    now unblocked. Through-focus scribe-blur back-derivation with
>    v1 (per-sweep) + v2 (multi-aperture pooling). See
>    IMPLEMENTATION_PLAN.md "Rail-step-mm calibration" for the
>    physics + use-case-named verdict labels.
>
> 4. **Pre-existing characterise.py bugs found + fixed** during the
>    rail-step wire-in:
>    * `subject_tilt_*_deg` was reporting `arctan(slope)` without
>      pixel→object-space scaling — values were 200× too small.
>      New `_slope_to_tilt_deg` applies M-scaling.
>    * `field_curvature_um_rms` was storing mm in a µm-labelled
>      column. Now multiplied by 1000.
>    * Centre-only grids silently returned the centre row 4× as FX
>      corners, making `uniformity_fx` report 1.0 instead of NaN.
>
> 5. **`parse_aperture` regex bug**: was unanchored, matching the
>    first `_F<digit>_` substring in slugs. Lens names with F-specs
>    (`Sigma_..._F2.8_EX_DG_OS_HSM`) hijacked the result. Fixed by
>    anchoring to the last `__`-separated segment, handling both
>    older-rig (`F8`) and newer-rig (`f_8`) formats. **Old Sigma
>    v2 results are wrong** — Sigma 150 was reading 6.61 µm before
>    fix vs 18.99 µm after (consistent with the rest of the cohort).
>
> Test count: 98 passing.

> **2026-05-16 follow-up — read this before any prior conclusions.**
> A second empirical pass surfaced two findings that supersede parts of
> the POC report below:
>
> 1. **`filesize` argmax fails at sharp configs.** On AIS 55mm at 1:1
>    F8, only 26 % / 46 % of tiles agree between filesize and maze-FFT
>    argmax. Filesize systematically picks 6-10 shots too late. At the
>    centre tile of AIS 287318 it under-reported the lens's true sharpness
>    by 2.13× through pure focus mis-pick. The POC's "filesize 5/5
>    within-sweep" validation was on a *soft* config (24-120 + Raynox
>    M-250) where the bell curve has a sharp peak; on sharp configs it
>    saturates and flattens.
> 2. **The AIS-copy "decentering" was a measurement artifact.** Once
>    each tile is judged at its own FFT-amp peak (not filesize's pick),
>    AIS 287318 and AIS 537016 are within 1 % at every tile and both
>    centred on the sensor. The previously reported 5.8× centre-tile
>    gap and the "287318 top edge 6.3× stronger than its own centre"
>    were both filesize mis-picking on 287318.
>
> **New methodology** (full details in
> `SHARPNESS_METRICS.md` "2026-05-16 update — methodology supersedes
> the POC"): per-tile scribe-LSF MTF50 + maze 2D-FFT amplitude. Both
> sized by measured magnification. Cross-config metric is subject-space
> MTF50. The eight POC methods remain available as cross-validation
> columns but no longer drive primary analysis. Resampled cohorts are
> for human visual comparison only — measurement runs on native frames.
>
> **Status of the `out_55mm/cross_lens_crops/` JPEGs**: these are
> filesize-picked and are not safe for any further numerical analysis.
> Visual review is fine (filesize picks *some* sharp shot, just not
> always the sharpest). Regenerate them via maze-FFT argmax before
> publishing any AIS cross-copy comparisons.
>
> Artefacts from the 2026-05-16 analysis: `/tmp/ais55_decentering_*.png`
> (per-copy maze-FFT amplitude heatmaps); `/tmp/ais_fft_analysis_run2.log`
> (definitive run log); scripts at `/tmp/ais_fft_analysis*.py`. Visual
> validation crops at `/tmp/ais287318_centre_*.png` (also on `nufan:/tmp/`).
>
> **Implementation plan**: see `IMPLEMENTATION_PLAN.md` in this directory
> for the three-phase pipeline (per-shot per-tile CSV → corrected
> peaks_v2.csv → per-slug lens_characteristics.csv) that picks up from
> the 2026-05-16 findings.
>
> **Implementation status (initial commit `9097def`, 2026-05-16):**
> sequencing steps 1-6 of the IMPLEMENTATION_PLAN have landed. New
> modules: `src/tile_sharpness/m_lookup.py` (manifest lookup),
> `methods/lsf.py` (OpenCV LSD scribe detect + cross-section + FFT;
> Hough fallback added in `7cfd5dd`; ESF→LSF math in `17a8d6a`),
> `methods/maze_fft.py` (M-aware annulus sum, matches the prototype to
> 0.4 % on a real AIS centre tile), `phase1.py` (per_shot_per_tile.csv
> + peaks_v2.csv; trough-FWHM filter in `3d3c31c`),
> `characterise.py` (lens_characteristics.csv). CLI gains
> `--manifest <path>` (repeatable), `--no-legacy`, and a
> `characterise` subcommand. 72 tests pass.
>
> Validation status (refreshed 2026-05-17):
>   * **Task 1** ✓ — out_55mm AIS centre maze-FFT amp ratio = 1.0412 (≤ 1.05).
>   * **Task 2** ✓ ran, FAIL — 100-400 @ 0.385× F11 centre = 10.4 vs
>     expected 33. Low-M LSF under-read (algorithmic limit).
>   * **Task 3** ✓ — AF 200/4D 1:1 F11 centre subject MTF50 = 42.7 lp/mm
>     (target ~33; within physical limits, f/11 diffraction ≈ 67 lp/mm).
>     Uniformity_dx = 0.92, uniformity_fx = 1.02 (matches "high uniformity
>     (sharp macro)" prediction).
>   * **Task 4** ⚠ ran, BLOCKED on `phase1.py:192` cross_section
>     window bug — Sigma + TC-2001 @ 2:1 F11 centre = NaN.
>   * **Task 5** ✓ — AF 200/4D + 5T + 6T @ 2:1 F11 centre = 24.76 lp/mm
>     (target ~23). Degenerate-grid path (centre-only) works correctly.
>   * **Task 6** — partial. Top of ranking (task 3 > 5) confirmed;
>     bottom unreliable due to task 2 under-read.
>   * **Task 7** ✓ unblocked — rail-step calibration in
>     `rail_calibration.py` provides per-sweep / per-group rail step
>     for older datasets without recorded `rail_position_mm`.
>   * **Maze-pitch validation** ✓ — `MAZE_PITCH_UM=13.0` stable across
>     three cohorts (±3.5 % spread).
>
> Steps 7-8 of the IMPLEMENTATION_PLAN (HTML report wiring + full
> cohort re-runs) deferred.
>
> **M-aware non-scribe rejection (`trough_fwhm_px` filter).** LSD/Hough
> accepts long dark lines regardless of width; some non-scribe features
> (bond-pad shadows, single dark texture lines) slip through with
> 5-12 px troughs even when real scribes at that M would be 20+ px
> wide. `phase1._score_shot` now records the measured trough FWHM and
> NaN-out the LSF columns when it's below half the predicted scribe
> FWHM at the sweep's M (`SCRIBE_WIDTH_UM × M / sensor_pitch`).
> AF 200/4D task 3 effect: `(+1, 0)` 81 lp/mm outlier (FWHM=12.5,
> predicted 20) → NaN; uniformity_dx 1.41 → 0.92, fx 1.65 → 1.02 —
> corners now correctly read as slightly softer than centre.
>
> **MTF50 method fixed: ESF→LSF differentiation, per-edge averaging.**
> The previous "FFT the whole trough as LSF" reading was
> scribe-width-limited (~11 lp/mm subject across every config tested),
> because wafer scribes are 20-px-wide dark bands, not impulses.
> Replaced with classic slanted-edge mechanics: split the trough at
> its deepest point, treat each side as an ESF, differentiate to an
> LSF, FFT each independently, average MTF50. AF 200/4D 1:1 F11
> centre: 11.1 → 42.7 lp/mm; AIS 287318 centre: 11.9 → 45.1 lp/mm.
> Validation task 1 unchanged (centre maze-FFT amp ratio 1.0412).
>
> **Hough fallback raised scribe-detection rate on the AIS sweeps from
> 43 % → 90 % per-tile.** When LSD's longest dark
> segment falls below the length threshold, `detect_scribe()` now runs
> `skimage.transform.probabilistic_hough_line` on Canny edges, groups
> lines by angle, clusters by perpendicular offset, and spans the
> dominant cluster's endpoints to recover a single long composite line.
> Compute cost: one Hough call (~3 s on a 3456 px ROI) at most once per
> (sweep, tile) — Phase 1 caches scribe detection at the filesize-argmax
> shot, so this is sweep-level overhead, not per-shot. Composite spans
> average 3240 px vs LSD's 690 px — a 4.7× longer cross-section anchor,
> giving more samples for the LSF profile.

## TL;DR

A POC has compared 8 sharpness metrics against the wafer dataset on
four cohorts. The slanted-edge "gold standard" recommendation from
`SHARPNESS_METRICS.md §1` did not survive — `mtfmapper` is unusable
on this rig. `filesize` is more robust than the doc previously
credited it with; `wavelet_ratio` and `dct_kurtosis` (added during
the POC) are the best new cross-frame supplements. Doc updates are
in place. **The one pending human action is an eyeball review of the
cross-lens disagreement crops from the three new cohorts** — see "What's
pending" below.

## Key documents (read in this order)

1. **`analyse-lens-test/SHARPNESS_METRICS.md`** — start at the
   **"Empirical results — POC 2026-05-15"** section near the bottom.
   That's the canonical write-up: cohort summaries, the
   "Recommended setup for cross-lens / cross-frame work" matrix, and
   per-method conclusions. The §1 caveat at the top of the file
   points back to that section.
2. **`analyse-lens-test/tile-sharpness/README.md`** — eight-method
   registry with orientations, per-method caveats, the SSH-to-nufan
   setup for `mtfmapper`, the `compare` / `cross-lens-crops`
   subcommand reference, and a recommended-combinations table.
3. **`analyse-lens-test/CLAUDE.md`** — project conventions index
   (git author email, uv/pytest tooling, analysis style, rig
   semantics, dataset layout, subproject pointers).
4. **`analyse-lens-test/ANALYSIS_NOTES.md`** §2 — bell-curve
   detection thresholds plus the rig-semantics paragraph (off-target
   crops are geometric; reshoot direction is not actionable).
5. **`run-lens-test/DESIGN_NOTES.md`** §6.31 — aperture convention,
   manual-aperture mode mechanics, and the brute-force
   `target_for_next_aperture` solver rationale.

## What's pending

### 1. Manual eyeball review of cross-lens disagreement crops *(partly superseded — see 2026-05-16 update at top)*

**Status as of 2026-05-16**: the disagreement-crops review is *less*
load-bearing now that the path forward is scribe-LSF + maze-FFT subject-
space MTF50 (which makes its own predictions independent of filesize /
wavelet / mtfmapper). The eyeball priorities that remain useful:

* The Sigma 150 + TC-2001 vs AF 200/4D + 5T + 6T comparison at 2:1
  (validated: TC chain looks ~1.8× sharper, matching the metric).
* The 100-400 2:1-resized vs native (to *see* Lanczos halo on
  resampled data — validates "don't measure on resampled").
* Scribes-as-lines confirmation at 400 % zoom on a single die-boundary
  in a 1:1 macro frame.

The original POC-era tasks below are kept for completeness but
deprioritised; only revisit if you specifically want to decide
whether to retain ``radial_fft`` / ``mtfmapper`` as cohort columns.

The three cross-cohort runs produced side-by-side per-method peak
tiles. The numbers say wavelet_ratio and filesize agree closely with
each other and with the consensus on cohorts with wide quality
spreads; they disagree on narrow ones. Whether the methods' picks
*look* sharper to a human is the open question. Three directories,
listed in priority order:

- **`analyse-lens-test/tile-sharpness/out_bare1to1/cross_lens_crops/tile_+0_+0/`** (31 JPEGs, 4 lenses × 8 methods)
  - Concrete pairs to compare:
    - `filesize__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED__shot_029.jpg` (filesize's #1) vs `wavelet_ratio__NIKKOR_Z_MC_105mm_f_2.8_VR_S__shot_040.jpg` (wavelet's #1) — same scene at 1:1, three methods disagree about which lens is sharpest at the centre.
    - `mtfmapper__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM__shot_035.jpg` (mtfmapper's #1) — does Sigma 150 actually deserve mtfmapper's nod?
- **`analyse-lens-test/tile-sharpness/out_resized1to1/cross_lens_crops/tile_+0_+0/`** (49 JPEGs, 6 lens configs)
  - Compare `wavelet_ratio__NIKKOR_Z_MC_105mm_f_2.8_VR_S_+_5T__*.jpg` (consensus best) against `wavelet_ratio__NIKKOR_Z_24-120mm_f_4_S_+_Raynox_M-150__*.jpg` (consensus worst). Visual gap should be obvious — that's the sanity check.
  - Compare `radial_fft__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED_+_5T__*.jpg` (rank 1 by radial_fft) against `filesize__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED_+_5T__*.jpg` (rank 4 by filesize) — same lens, 3-rank disagreement. Who's right?
- **`analyse-lens-test/tile-sharpness/out_55mm/cross_lens_crops/tile_+0_+0/`** (40 JPEGs, 5 sweeps × 8 methods)
  - The two AIS copies (s/n 287318 vs 537016) should look near-identical at `filesize__*.jpg` — if they don't, one is decentered.
  - The three Auto copies (209088 vs 258263 vs 262711) — `258263` ranks consistently better by mean-rank-across-tiles; does its centre tile actually look sharper or is it framed differently?
  - **Filesize artefact worth seeing**: at the centre tile, filesize picks Auto 209088 first (peak 318k bytes), but across all 35 tiles the AIS copies win. That's filesize being content-fooled at one position. Open `filesize__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_209088__shot_030.jpg` and compare to either AIS centre crop.

Each tile dir also has a `README.txt` listing every method's pick
with peak metric value and shot index.

Also worth looking at the off-axis dirs in each cohort if the centre
read is ambiguous: `tile_+3_+0`, `tile_-3_+0`, `tile_+0_+2`,
`tile_+0_-2`.

### 2. Decide whether to drop methods from the registry

- **`mtfmapper`** scored 1/5 on the earlier within-sweep eyeball
  review (the Raynox M-250 sweep, results in `SHARPNESS_METRICS.md`
  empirical section). On the resized cohort it can't discriminate
  at all (all six lenses rank ~3.3). Its CV across same-model copies
  is 0.54, 3-25× the next-worst method.
  - **Open question**: would it perform better on a sweep that has
    clear isolated slanted-edge targets (a real chart card, or
    higher-magnification crops where individual bond pads are
    isolated dark blobs)? The default component-finder needs that
    input shape; `--single-roi` is a fallback. Try once on a chart
    card before deciding to drop the method entirely.
- **`edge_decay`** peak quantises to integer pixels and produces
  ties; useful only for *argmax* (which rail step within a sweep).
  Recommended action: keep it but exclude its `peak_value` from
  cross-tile / cross-lens ranking; let the cross_lens routines
  filter to argmax-only for this method.
- **`radial_fft`** argmax is unreliable (picks heavily-defocused
  end-of-sweep shots due to near-Nyquist noise). Its peak ranking
  is fine. Recommended action: same as `edge_decay` — keep `peak`,
  drop `argmax` from cross-method consumers.

### 3. Integration into rail-coverage?

The empirical section's "Recommended setup" matrix is the candidate
for codifying. The simplest move would be to add
`wavelet_ratio` as a second column alongside the existing
file-size proxy in `analyse-lens-test/rail-coverage/`, and flag
scenarios where filesize and wavelet_ratio rank a lens / scenario
more than ~2 ranks apart. The eyeball review (TODO 1) gates this —
don't integrate until visual confirmation lands.

### 4. mtf_mapper available only on nufan

The local Arch host had its `mtf_mapper` binary deleted during a
failed rebuild attempt earlier in this session, and `cmake` isn't
installed locally so a rebuild is blocked. The rebuilt binary now
lives on nufan (Ubuntu 25.10, OpenCV 4.10) at the in-tree workspace
path — same shared-mount path as before, so callers don't change.
The `score_mtfmapper` scorer in `methods.py` routes via SSH with a
`ControlMaster` to keep one connection warm. To get `mtf_mapper`
working locally again, install `cmake` and rebuild the same way (see
`tile-sharpness/README.md` "SSH setup" for the apt package list and
build steps).

## Repository state

`analyse-lens-test/` repo, recent commits (tile-sharpness only):

```
3d3c31c tile-sharpness: M-aware trough-FWHM filter for non-scribe rejection
17a8d6a tile-sharpness: ESF→LSF MTF50 fixes scribe-width-limited reading
7cfd5dd tile-sharpness: Hough fallback for scribe detection (43 % → 90 %)
9097def tile-sharpness: implement LSF + maze-FFT pipeline (Phases 1-3)
8fecab0 docs: 2026-05-16 methodology supersession + LSF/maze-FFT plan
f869d78 sharpness POC empirical findings + project-conventions doc
cdf1c67 tile-sharpness POC + long-distance metrics doc
```

`lens-test-detect-core/` repo: clean, last commit `75cdc54`. (The
local box now has `/home/alson/shared/projects/personal/fotografie/lens-test-detect-core`
on the git `safe.directory` allowlist; you'll need to do the same
on nufan if you haven't already — same command.)

`run-lens-test/` repo: untouched in this session.

## How to resume

The cohort runs are cached. Tile JPEGs live at
`~/shared/projects/personal/fotografie/.tile-sharpness-cache/` on the
shared mount, so nufan sees the same cache. A re-run of any of the
three cohorts is near-instant for the cropping and ~20-30 min for
mtfmapper-via-SSH plus the four other scoring methods.

```sh
cd analyse-lens-test/tile-sharpness

# List candidate sweeps:
uv run tile-sharpness list-sweeps

# Re-run a cohort (uses cached tiles, re-scores):
uv run tile-sharpness analyse <substring-of-label> ... --out out_<name>/

# Cross-cohort aggregation + crop export:
uv run tile-sharpness compare out_<name>/peaks.csv
uv run tile-sharpness cross-lens-crops out_<name>/peaks.csv \
    --out out_<name>/cross_lens_crops \
    --tile 0,0 --tile -3,0 --tile 3,0 --tile 0,-2 --tile 0,2

# All three driven from one place:
./scripts/finalize_cohorts.sh                          # compare + crops
uv run python scripts/cross_cohort_summary.py          # mean-rank tables + CV
```

The 2026-05-16 LSF + maze-FFT pipeline runs via the same `analyse`
subcommand, with two new flags + a follow-up subcommand:

```sh
# Run Phase 1 + Phase 2 only (per_shot_per_tile.csv + peaks_v2.csv).
# --manifest is repeatable; --no-legacy skips the 8-method pass.
uv run tile-sharpness analyse <sweep> [<sweep>...] \
    --out out_<name>/ \
    --manifest /path/to/wafer-manifest-2026-01-29.csv \
    --no-legacy

# Phase 3 rollup: per-slug centre/DX/FX MTF50 + uniformity +
# peak-value decentering + plane-fit tilt + curvature.
uv run tile-sharpness characterise out_<name>/peaks_v2.csv
# → writes out_<name>/lens_characteristics.csv
```

The new pipeline needs `archive-2026-05/measure_wafer_squares` output
to resolve M per sweep (drives ROI sizing + subject-MTF50 conversion);
falls back to path-parsed `claimed_mag` per sweep if no manifest row
matches, with `m_source = "path_parsed"` flagged in the CSV.

The three cohorts that produced the current findings:

```sh
# Bare native macros at 1:1, F8 (4 lenses, same scene)
uv run tile-sharpness analyse \
    "2026-01-29__NIKKOR_Z_MC_105mm_f_2.8_VR_S__1_1__F8" \
    "2026-01-29__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED__1_1__F8" \
    "2026-01-29__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM__1_1__F8" \
    "2026-01-29__Sigma_Macro_105mm_F2.8_EX_DG_OS_HSM__1_1__F8" \
    --out out_bare1to1 --workers 8

# Resized 1:1 cross-config (6 mixed configs)
uv run tile-sharpness analyse \
    "2026-01-29__NIKKOR_Z_MC_105mm_f_2.8_VR_S_+_5T__1_1-resized__F8" \
    "2026-01-29__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED_+_5T__1_1-resized__F8" \
    "2026-01-29__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM_+_5T__1_1-resized__F8" \
    "2026-01-29__Nikon_AF_Zoom-Micro_Nikkor_70-180mm_f_4.5-5.6D_ED_+_5T__1_1-resized__F8" \
    "2026-01-29__NIKKOR_Z_100-400mm_f_4.5-5.6_VR_S_+_Nikon_5T__1_1-resized__F8" \
    "2026-02-18__NIKKOR_Z_24-120mm_f_4_S_+_Raynox_M-150__1_1-resized__120.0_mm__F8" \
    --out out_resized1to1 --workers 8

# Multi-copy 55mm primes (2× AIS + 3× Auto)
uv run tile-sharpness analyse \
    "2026-01-29__Nikon_Micro-Nikkor_55mm_f_2.8_AIS_287318__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_55mm_f_2.8_AIS_537016__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_209088__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_258263__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_262711__1_1__F8" \
    --out out_55mm --workers 8
```

All three are committed under `out_*` glob in `.gitignore` so the
generated trees stay out of git. The peaks.csv / agreement.csv /
disagreement directory layout is documented in
`tile-sharpness/README.md`.

## What changed in this session, in one paragraph

POC validated. Four new methods added to the registry
(`laplacian_var`, `tenengrad`, `dct_kurtosis`, `wavelet_ratio`).
Sweep discovery extended to handle bare-prime 3-level layouts and
`*-resized` cohort directories. `compare` and `cross-lens-crops`
CLI subcommands added for cross-sweep aggregation. `mtf_mapper`
moved from local to nufan over SSH (ControlMaster-multiplexed); tile
cache moved from `~/.cache` to the shared mount so nufan reads
tiles by path. Docs updated to reflect empirical findings; memory
files reduced to pointers since the canonical content now lives in
the shared docs. Three cross-lens cohorts run (bare 1:1, resized
1:1, multi-copy 55mm) but the manual eyeball verification step has
not been done yet.
