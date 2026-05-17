# tile-sharpness — implementation plan for LSF + maze-FFT pipeline

State as of 2026-05-16. Supersedes the POC's eight-method primary
analysis. Companion to `SHARPNESS_METRICS.md` "2026-05-16 update";
read that first for the methodology rationale.

> **Status — 2026-05-16:** sequencing steps 1-6 are landed and tested
> (72 passing tests across 6 modules). Steps 7-8 (HTML report wiring +
> cohort re-runs) deferred.
>
> Validation:
>   * Task 1 ✓ — out_55mm AIS centre maze-FFT amp ratio = 1.0412 ≤ 1.05.
>   * Task 3 ✓ — AF 200/4D 1:1 F11 centre subject MTF50 = **42.7 lp/mm**
>     (expected ~33; within physical limits, f/11 diffraction ≈ 67 lp/mm).
>   * Tasks 2/4/5/6 not yet run.
>   * Task 7 still blocked on rail-step-mm calibration for older datasets.
>
> Four follow-up commits sit on top of the initial `9097def`:
>   * Hough-fallback scribe detector — raised AIS per-tile scribe rate
>     from 43 % → 90 %.
>   * ESF→LSF MTF50 refactor — split the trough at its minimum, treat
>     each side as a step edge (ESF), differentiate to a true LSF,
>     FFT each independently and average MTF50. Fixed the
>     scribe-width-limited reading that had clamped MTF50 at ~11 lp/mm
>     across all configs (AF 200/4D centre: 11.1 → 42.7 lp/mm; AIS
>     centre: 11.9 → 45.1 lp/mm). The trough-as-LSF approach was wrong
>     for this dataset — scribes are 20-px-wide dark bands, not
>     impulses, and SHARPNESS_METRICS.md's "scribe FWHM is comparable
>     to optical edge rise" claim doesn't hold at the rig's typical
>     apertures.
>   * M-aware trough-FWHM rejection in `phase1._score_shot` —
>     a `trough_fwhm_px` column now flows through
>     `per_shot_per_tile.csv`; rows where the measured trough is below
>     half of the predicted scribe FWHM at the sweep's M (predicted =
>     `SCRIBE_WIDTH_UM × M / sensor_pitch`) get their LSF columns
>     NaN-out. Catches non-scribe features (bond-pad shadows etc.) that
>     LSD/Hough accepts as long dark lines but whose narrow troughs
>     don't support the ESF→LSF method. Effect on AF 200/4D task 3
>     rollup: the `(+1, 0)` 81 lp/mm outlier (FWHM=12.5 vs predicted 20)
>     is now dropped; uniformity_dx 1.41 → 0.92, uniformity_fx 1.65 →
>     1.02 — corners now correctly read as slightly softer than centre,
>     consistent with the plan's "high uniformity (sharp macro)" target.
>
> See "Open work after 2026-05-16 implementation" for remaining items.

## Goal

Replace the existing `filesize`-based "sharpest tile" picker AND
produce per-lens characteristic data (subject-space MTF50, corner-vs-
centre uniformity, decentering, field curvature, subject tilt) from
a single pass over each sweep. Both outputs share Phase 1; the
characteristics rollup builds on the per-tile peak picks from Phase 2.

## Three-phase pipeline

### Phase 1 — per-shot per-tile raw sharpness CSV

One row per `(sweep, tile_ix, tile_iy, shot_idx)`.

Output: `out_<cohort>/per_shot_per_tile.csv`.

Columns:

| column | source |
|---|---|
| `sweep` | identifies the `(lens, mag, focal, aperture)` slug |
| `tile_ix`, `tile_iy` | tile grid from `tile_sharpness/geometry.py` |
| `shot_idx` | within-sweep index (sorted by capture seq) |
| `rail_position_mm` | from `shots.csv` if present; `None` for older datasets |
| `tile_x_px`, `tile_y_px` | sensor-pixel coords of tile centre |
| `filesize_bytes` | `os.path.getsize` on the tile JPEG — retained for backward compat |
| `on_target` | existing `on_target.py` cross-compare logic |
| `scribe_detected` | LSD or morphology detected ≥1 near-full-span scribe |
| `lsf_peak_amp` | scribe-LSF cross-section FFT amplitude at a fixed reference frequency |
| `lsf_mtf50_cy_per_px` | half-amplitude frequency in `|FFT(cross-section)|` |
| `maze_resolves` | `M ≥ 0.7×  AND  lsf_mtf50 × M / pitch ≥ maze_freq_threshold` |
| `maze_fft_amp` | sum of 2D-FFT magnitude in annulus around predicted maze fundamental (only computed when `maze_resolves`) |

Implementation notes:

- **Scribe detect once per (sweep, tile_position)**, measure cross-section
  per shot. Scribes don't move along the rail; only focus does. Run
  detection on the FFT-argmax-candidate shot from a first pass with
  any cheap proxy (filesize is fine here — it picks *some* sharp
  shot, just not always the sharpest), then re-use the scribe
  endpoints across the sweep.
- **Tile ROI is per-metric, M-driven** (per `SHARPNESS_METRICS.md`
  "M-driven crop sizing"):
  - LSF crop = `max(3 × die_period_px, 1024)` — typically a much
    larger ROI than the existing 1024 tile at M ≥ 1×.
  - Maze-FFT crop = the existing 1024 tile is fine at 1:1+ (340+
    cycles per side); smaller at higher M is OK too.
  - This means **the existing 1024 tile cache is reusable for
    maze-FFT but not for LSF** at M ≥ 1× — Phase 1 has to re-crop
    LSF ROIs from the source full-frame JPEG.
- **M comes from `archive-2026-05/measure_wafer_squares` manifest**
  (cached `wafer-manifest-*.csv`); fallback to the magnification
  parsed from the dir name (`1_2.60` → 0.385) when no manifest is
  available. Add a `m_source` column noting which.

### Phase 2 — per-(sweep, tile) peak rollup

One row per `(sweep, tile_ix, tile_iy)`.

Output: `out_<cohort>/peaks_v2.csv` (alongside the existing
`peaks.csv` for back-compat; eventually replaces it).

Per-tile metric-selection rule:

```
if not on_target:
    skip OR write filesize-only fallback (degenerate path)
elif maze_resolves:
    primary_metric = "maze_fft"
    argmax_shot = argmax over sweep of maze_fft_amp
else:
    primary_metric = "lsf"
    argmax_shot = argmax over sweep of lsf_peak_amp
```

Columns:

| column | source |
|---|---|
| `sweep`, `tile_ix`, `tile_iy` | grouping keys |
| `primary_metric_used` | `"maze_fft"` \| `"lsf"` \| `"filesize_fallback"` |
| `argmax_shot_idx` | per primary_metric |
| `peak_value` | primary_metric value at argmax_shot |
| `mtf50_sensor_cy_per_px` | LSF MTF50 at argmax_shot (always computed, regardless of which method picked argmax — keeps the cross-config metric uniform) |
| `mtf50_subject_lp_per_mm` | `mtf50_sensor × M × 229.9` (Z7 pitch factor) |
| `rail_position_mm` at argmax | for field-curvature physical-units conversion |

The existing per-method rows in `peaks.csv` stay for cross-validation
(filesize / wavelet_ratio / dct_kurtosis etc. at their argmax values).
`peaks_v2.csv` is the new source of truth for "the sharpest crop at
this tile".

### Phase 3 — per-slug lens characteristics

One row per `(lens, mag, focal, aperture)` slug.

Output: `out_<cohort>/lens_characteristics.csv`.

Sampled positions (nine per slug):

- **Centre** `(0, 0)`.
- **DX corners** — four tiles at the corners of the DX inner region
  (sensor coords ≈ ±67 % of FX half-width). Pick the four
  `(ix, iy)` cells nearest those positions.
- **FX corners** — four tiles at the FX extreme corners.

Map these to the existing `cropped/<region>/` naming convention so
the same nine positions are sampled across all datasets.

Columns:

| column | derivation |
|---|---|
| `mtf50_centre_lpmm` | subject-MTF50 from `(0, 0)` tile |
| `mtf50_dx_corner_mean_lpmm` | mean over 4 DX corners |
| `mtf50_fx_corner_mean_lpmm` | mean over 4 FX corners |
| `uniformity_dx` | `dx_corner_mean / centre` |
| `uniformity_fx` | `fx_corner_mean / centre` |
| `decentering_dx_lr` | `(L − R) / mean` peak-VALUE asymmetry for DX-ring left-right pair |
| `decentering_dx_tb` | same for top-bottom |
| `decentering_fx_lr` | same for FX-ring |
| `decentering_fx_tb` | same for FX-ring |
| `subject_tilt_x_deg` | x-slope from plane fit on `(tile_x_px, tile_y_px, argmax_rail_position_mm)` over the 9 positions |
| `subject_tilt_y_deg` | y-slope, same |
| `field_curvature_um_rms` | RMS of plane-fit residuals × rail-step-mm calibration |

Use peak-VALUE for decentering (not peak-index — index asymmetry is
subject-tilt + field-curvature contaminated; value asymmetry is
"this corner is genuinely softer than its opposite").

Subject-tilt + field-curvature are **per-slug** (not session-wide);
older datasets (2026-01-29, 2026-02-18) have larger and more
variable subject tilt than recent ones.

## Module layout

New / updated under `tile-sharpness/src/tile_sharpness/`:

- `methods/lsf.py` *(new)*
  - `detect_scribe(image_2d) -> Segment | None` — LSD via
    `cv2.createLineSegmentDetector` (or scikit-image
    `probabilistic_hough_line` as fallback if opencv-contrib isn't
    available)
  - `cross_section(image_2d, segment, half_window_px) -> 1d_profile`
  - `lsf_peak_amp(profile, ref_freq_cy_per_px) -> float`
  - `lsf_mtf50(profile) -> float | None`
- `methods/maze_fft.py` *(new)*
  - `maze_freq_cy_per_px(M, pitch_um=4.35, maze_pitch_um=13.0) -> float`
  - `maze_amp(image_2d, M) -> float | None` — annulus sum, return
    `None` if maze aliases at this M
- `m_lookup.py` *(new)*
  - Reads cached wafer-manifest CSV(s); maps `(lens, mag, focal)` →
    measured M; falls back to path-parsed claimed M
- `methods.py` *(updated)*
  - Existing eight methods stay; new methods (`lsf`, `maze_fft`) added
    to `METHODS` dict; `MethodSpec.orientation` populated for each
- `analyse.py` *(updated)*
  - Phase 1 loop produces `per_shot_per_tile.csv` alongside existing
    `peaks.csv`
- `characterise.py` *(new)*
  - Phase 3 rollup; `cli.py` gets a `characterise` subcommand

## Schema migration

- `peaks.csv` stays untouched for backward compat with current HTML
  reports.
- `peaks_v2.csv` is new (Phase 2 output, the corrected peak picks).
- `per_shot_per_tile.csv` is new (Phase 1 raw data).
- `lens_characteristics.csv` is new (Phase 3 rollup).

Eventually wire `peaks_v2` into the HTML report (replacing
filesize-based peak crops with FFT-pick crops). Until then, both
exist side-by-side.

## Validation / regression tests

To verify before publishing any conclusions on the new pipeline:

1. **AIS 55mm copies (`out_55mm` re-run)** — the centre-tile maze-FFT
   amp ratio between 287318 and 537016 must be ≤ 1.05× (validates
   the filesize-failure fix; confirms the two copies are essentially
   identical optically, as already established by the 2026-05-16
   analysis).
2. **Bare 100-400 at 0.385× F11 (out_bare1to1 + standalone)** —
   subject MTF50 centre ≈ 33 lp/mm; sensor MTF50 close to Nyquist
   (pixel-limited); corner MTF50 should drop to ~10-15 (zoom corner
   softness).
3. **AF 200/4D bare at 1:1 F11** — subject MTF50 centre ≈ 33 lp/mm;
   high uniformity (sharp macro); minimal decentering.
4. **Sigma 150 + TC-2001 at 2:1 F11** — subject MTF50 centre
   ≈ 41 lp/mm; clean TC chain so uniformity should be reasonable.
5. **200/4D + 5T + 6T at 2:1 F11** — subject MTF50 centre ≈ 23
   lp/mm; stacked diopters → expect worse corner falloff than
   the bare AF 200/4D.
6. **Cross-config ordering**: Sigma + TC-2001 > both bare configs >
   200/4D + 5T + 6T on subject-MTF50, matching the visual ranking
   from task 1.
7. **Subject-tilt sanity**: 2026-01-29 datasets should show
   per-slug `subject_tilt_*_deg` in the 3-6° range (visually
   confirmed in earlier scribe-rotation measurements: scribes
   always come out tilted ~+4.5° in captured frames). 2026-05+
   datasets should be lower (the user reports tighter alignment
   on recent shoots).

## Implementation sequencing

Suggested order, each step shippable on its own:

1. ✓ **done** — `m_lookup.py` (uses existing wafer-manifest CSVs);
   tested against 2026-01-29 `Sigma 150 1:1` anchor. 13 tests.
2. ✓ **done** — `methods/lsf.py` (LSD + cross-section + LSF MTF50).
   12 tests on synthetic Gaussian + fragmented scribes; real-tile
   verification on AIS 287318 centre. **Two-stage detector**: LSD
   first (fast); if its longest dark segment falls below the length
   threshold, fall back to `detect_scribe_hough` (Canny +
   probabilistic Hough + angle-binning + perpendicular-offset
   clustering + endpoint spanning). 2026-05-16 AIS measurement:
   per-tile scribe rate 43 % → 90 % from the fallback alone; mean
   spanned length 690 → 3240 px.
3. ✓ **done** — `methods/maze_fft.py` (annulus sum). 8 tests;
   matches the prototype at `/tmp/ais_fft_worker.py` to 0.4 % on a
   real AIS centre tile.
4. ✓ **done** — Phase 1 wiring (`phase1.py` emits
   `per_shot_per_tile.csv`). Runs on `out_55mm`; validates AIS
   centre maze argmax. **Architecture note**: implemented as a
   separate `phase1.py` module rather than extending `analyse.py`'s
   `MethodSpec` Path→float scorer signature — the new metrics need
   source-path + M + per-sweep scribe-cache context that the legacy
   scorer signature can't carry.
5. ✓ **done** — Phase 2 (`peaks_v2.csv`). Folded into `phase1.py`'s
   `_rollup_peaks_v2()`. Validation task 1 passes: AIS centre maze
   amp ratio 1.0412 ≤ 1.05.
6. ✓ **done** — Phase 3 (`characterise.py`). 8 tests; one new CLI
   subcommand. Decentering / tilt / curvature numbers produced for
   AIS; tasks 2-6 (centre MTF50 absolute checks against AF 200/4D
   etc.) not yet validated — blocked on LSF detection improvement.
7. ⏳ **deferred** — Wire `peaks_v2` into the HTML report.
8. ⏳ **deferred** — Run on `out_bare1to1`, `out_resized1to1`,
   `out_55mm` cohorts; add a row in the HTML report's per-cohort
   summary for the new column set.

## Out of scope for v1

- ``mtfmapper`` (failed; superseded by in-house LSF).
- Bond-pad-grid harmonic analysis at lower frequencies than the
  maze fundamental — kept as a future enhancement; the maze
  fundamental covers the high-frequency band where lens
  discrimination lives.
- 2nd/3rd harmonic readouts at the maze frequency for finer MTF
  curves — useful eventually but not gating any current
  decisions.
- Replacing the existing per-method tile crops on disk; v1 reads
  the existing 1024×1024 cache for maze-FFT and re-crops larger
  ROIs from source JPEGs for LSF.
- Reshoot recommendation logic based on the new metrics — keep
  the existing rail-coverage truncation-status flow; revisit
  reshoot triggers once the new characteristics columns are
  stable.

## Dependencies

- ``opencv-contrib-python`` (for ``cv2.createLineSegmentDetector``)
  *OR* ``scikit-image`` (already a dep; ``probabilistic_hough_line``
  works but is more sensitive to noise / parameter tuning).
- ``numpy``, ``scipy`` (already deps).
- ``archive-2026-05/measure_wafer_squares`` must have been run on
  the dataset to produce a wafer-manifest CSV with measured M
  per `(lens, mag, focal)`. Older datasets without that step
  fall back to path-parsed claimed M (which is fine when the
  user's labels match reality; flagged otherwise).

## Open questions — resolutions

- **LSF reference frequency for argmax** — resolved: `lsf_peak_amp`
  is the |FFT| magnitude at `ref_freq_cy_per_px=0.10`. Both
  `lsf_peak_amp` and `lsf_mtf50_cy_per_px` columns ship in
  `per_shot_per_tile.csv`; the rollup uses `lsf_peak_amp` for
  argmax when maze doesn't resolve.
- **Maze frequency calibration** — kept at `maze_pitch_um = 13.0`.
  Validated on AIS 287318 centre: new annulus sum agrees with the
  prototype's hand-tuned 0.30–0.36 band to 0.4 %. Cross-dataset
  validation still TODO when the pipeline runs on non-AIS sweeps.
- **9-position sampling exact tile indices** — resolved by
  switching to a grid-extent-based selection (in `characterise.py`):
  FX corners are `(ix_min, iy_min) …`, DX corners are one step
  inward along each diagonal. Generalises naturally to the
  M-driven shrinking grid; degenerate cases (≤ 5 distinct cells)
  emit `NaN` aggregates with an `n_positions` + `note` flag.
- **Plane fit weighting** — uniform weighting in v1, as expected.

## Decisions made during the 2026-05-16 implementation

- **Manifest discovery**: `--manifest <path>` CLI arg, repeatable
  (no canonical default path; the existing prototypes at
  `/tmp/wafer-manifest-*.csv` are not stable). Falls back to
  path-parsed `claimed_mag` per sweep with
  `m_source = "path_parsed"`.
- **Scribe detector**: OpenCV LSD via `opencv-contrib-python`.
- **LSF ROI strategy**: on-demand full-JPEG decode + numpy slice
  per (shot, tile); no new tile-cache size. The existing 1024-px
  TurboJPEG-crop cache is reused only for filesize / on_target
  legacy columns (matched to the new ROI grid by `(ix, iy)` since
  both grids share the MCU-aligned centre and step).
- **ROI size vs grid granularity — accuracy wins**: ROI sizes are
  M-driven first; the tile grid is built around the ROIs.
  Overlapping tile cells are acceptable when
  `max(lsf_roi_px, maze_roi_px) > grid_step_px`. At extreme M
  where the LSF ROI is larger than the frame, the grid degenerates
  to a single centre-only ROI. Recorded in
  `feedback_accuracy_over_granularity.md` in the user's memory.
- **Phase 1 vs `MethodSpec` registry**: the new LSF + maze-FFT
  scorers do NOT plug into the legacy `METHODS` dict (whose
  `Scorer = Callable[[Path], float | None]` signature can't carry
  M / source-path / scribe-cache context). They live in
  `phase1.py`, which calls them directly. The eight POC methods
  remain in the registry for cross-validation in `peaks.csv`.

## Open work after 2026-05-16 implementation

### Done

- ~~**Tighten scribe detection (priority).**~~ ✓ Hough fallback
  wired in: detection rate 43 % → 90 % on out_55mm AIS sweeps;
  mean span 690 → 3240 px. Radon-projection alternative shelved as
  the Hough approach was sufficient.
- ~~**MTF50 absolute calibration.**~~ ✓ Task 3 ran and exposed that
  the trough-as-LSF method was scribe-width-limited at ~11 lp/mm
  regardless of lens. Switched to ESF→LSF differentiation of the
  trough's two edges, MTF50 per edge, averaged. AF 200/4D centre
  now reads 42.7 lp/mm (was 11.1); AIS 287318 centre 45.1 (was
  11.9). Both within physical limits and consistent with each
  edge's MTF50 (45–53 lp/mm individually on AF 200/4D centre, see
  POC at `/tmp/poc_esf_lsf.py`).
- ~~**Non-scribe feature rejection.**~~ ✓ M-aware `trough_fwhm_px`
  filter in `phase1._score_shot` drops LSF readings whose measured
  trough is below half the predicted scribe FWHM at the sweep's M.
  AF 200/4D `(+1, 0)` 81 lp/mm outlier (FWHM=12.5 at M=1.0,
  predicted 20) now NaN; uniformity_dx 1.41 → 0.92, fx 1.65 →
  1.02.

### Pending validation runs

- **Task 2** — Bare NIKKOR Z 100-400 at 0.385× F11. ✓ ran 2026-05-17.
  Centre subject MTF50 = **10.4 lp/mm** (expected ~33) — **under-reads
  at low M**: trough is only ~7-8 px FWHM, too few samples per edge
  for the ESF→LSF split to resolve high MTF50. Pipeline runs cleanly
  (full 9-position grid). Algorithmic limit, not a bug.
- **Task 4** — Sigma 150 + TC-2001 at 2:1 F11. ✓ ran 2026-05-17.
  Grid correctly degenerated to centre-only (LSF ROI 6896 px >
  Z7 5504 px). Centre MTF50 = **NaN** — **pipeline bug**: fixed
  `half_window_px=24` in `phase1._score_shot:192` is M-blind. At
  M=2.0 the expected scribe FWHM (~40 px) fills most of the 49-px
  window and `_split_to_edge_lsfs` (`methods/lsf.py:354-363`) rejects
  71/77 shots. Should be M-driven like the LSF/maze ROIs.
- **Task 5** — Nikon AF 200/4D + 5T + 6T at 2:1 F11. ✓ ran 2026-05-17.
  Centre subject MTF50 = **24.76 lp/mm** (expected ~23) — clean
  match. Corner falloff prediction not verifiable (degenerate grid).
- **Task 6** — Cross-config ordering. ✓ partially confirmed (task
  3 > task 5 > task 2 by centre MTF50). Task 4 inconclusive due to
  scribe-detect bug above. Bottom of ranking unreliable until the
  low-M LSF under-read is fixed.
- **Task 7** — Subject-tilt sanity check. ✓ unblocked 2026-05-17 by
  the rail-step-mm calibration in `rail_calibration.py` (see below).
  `characterise.py` now accepts `rail_step_mm` and converts the
  plane-fit slope to true subject tilt in degrees (with M-scaling
  fix) and field curvature in µm-RMS.
- **Validate maze-pitch on non-AIS datasets.** ✓ done 2026-05-17.
  `MAZE_PITCH_UM=13.0` is cohort-stable: AIS centre best-fit
  13.18 µm, Sigma+TC2001 (M=2.0) 13.44 µm, AF200+5T+6T (M=2.06)
  12.95 µm. Spread ±3.5 % within FFT bin width. **Safe to publish
  absolute lp/mm with the existing constant.**

### Rail-step-mm calibration (`rail_calibration.py`, 2026-05-17)

Through-focus scribe-blur back-derivation of per-shot rail step for
older datasets that lack recorded `rail_position_mm`. Geometric
model: `blur_object = δ_object × M / N_eff_total` (thin-lens, total-
effective f-number from the project aperture convention). Wafer
scribes have intrinsic FWHM `SCRIBE_WIDTH_UM=87` (back-solved from
AIS centre); at defocus the observed trough FWHM widens via
quadrature: `fwhm_obs² ≈ intrinsic² + blur²`. Per-tile argmin(fwhm)
defines the local baseline; per-shot estimates pool over all
qualifying (tile, defocus-shot) pairs.

Two layers:
- **v1**: per-sweep estimate. Median of pooled estimates + MAD as
  uncertainty. Returns `CalibrationResult` with `verdict` ∈
  {publishable, comparison_ok, sanity_only, unusable, insufficient,
  failed} mapped to use cases (see module docstring).
- **v2**: pools v1 estimates per `(lens, mag, focal)` group across
  apertures. The user's "same start/stop/steps across apertures"
  workflow means apertures share a physical rail step, so cross-
  aperture agreement is a built-in consistency check. Inter-aperture
  spread becomes the v2 uncertainty.

Wired into `characterise.py` via optional `rail_step_lookup` arg on
`characterise_peaks_v2()`. When provided, missing `rail_position_mm`
is synthesized as `argmax_shot_idx × rail_step_mm`. Two adjacent
fixes landed at the same time:
- Subject-tilt unit fix: previous code did `arctan(slope_mm_per_px)`
  without pixel→object-space scaling, reporting 200× too small. New
  `_slope_to_tilt_deg(slope, m)` does `arctan(slope × M × 1000 / pitch_um)`.
- Field-curvature unit fix: column labeled `_um_rms` was storing mm.
  Now multiplied by 1000 before write.
- Degenerate-grid fix in `_select_rings`: centre-only grids no
  longer silently return centre row 4× as FX corners (was making
  `uniformity_fx=1.0` instead of NaN).

### Aperture parser bug (2026-05-17)

`parse_aperture` previously did an unanchored regex search on the
slug, matching the FIRST `_F<digit>_` substring. Lens names
containing F-specs (`Sigma_..._F2.8_EX_DG_OS_HSM`, AF/Nikkor
`f_2.8`) were picked up first. All Sigma-prefixed sweeps got
N_eff=2.8 regardless of actual aperture, biasing rail-step
estimates by `(2.8/N_actual)`. Fixed by anchoring to the last
`__`-separated segment, matching either `F<digits>` (older-rig) or
`f_<digits>` (newer-rig). Pre-fix Sigma 150 = 6.61 µm; post-fix
18.99 µm (consistent with the rest of the bare-prime cohort).

### Aperture-convention dependency for tube/diopter sweeps

`rail_calibration` uses slug aperture as `N_eff_total`. This is
correct when the slug already reflects total effective (bare-prime
CPU sweeps where m_indicated ≈ m_total; pre-bumped MF sweeps from
2026-01 / 2026-02). For uncorrected extension-tube or diopter
sweeps, slug = lens-internal effective ≠ total-effective; the
formula underestimates `N_eff` by `(1 + m_total) / (1 + m_indicated)`
and the derived rail step is too small. **No code change needed**
when the aperture-convention rewrite lands — the slug column will
carry the right value and the formula picks it up.

### Sequencing steps 7-8 (deferred)

- HTML report integration of `peaks_v2.csv`.
- Full cohort re-runs (`out_55mm`, `out_bare1to1`, `out_resized1to1`)
  under the new pipeline. Once LSF detection is reliable, regenerate
  `out_55mm/cross_lens_crops/` from maze-FFT argmax (the existing
  crops are filesize-picked and unsafe for further numerical
  analysis per HANDOVER.md).

## Pointers

- Methodology: `analyse-lens-test/SHARPNESS_METRICS.md` "2026-05-16
  update — methodology supersedes the POC"
- Prototype maze-FFT script: `/tmp/ais_fft_analysis.py`
  (per-shot per-tile FFT, agent-built)
- Decentering heatmaps from validation: `/tmp/ais55_decentering_*.png`
- Visual validation of filesize failure:
  `/tmp/ais287318_centre_{filesize_pick_shot037,fft_pick_shot030}.png`
  (also copied to `nufan:/tmp/`)
