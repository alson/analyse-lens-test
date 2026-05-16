# tile-sharpness — implementation plan for LSF + maze-FFT pipeline

State as of 2026-05-16. Supersedes the POC's eight-method primary
analysis. Companion to `SHARPNESS_METRICS.md` "2026-05-16 update";
read that first for the methodology rationale.

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

1. `m_lookup.py` (uses existing wafer-manifest CSVs); test against
   2026-01-29 `Sigma 150 1:1` anchor.
2. `methods/lsf.py` (LSD + cross-section + LSF MTF50). Unit-test on
   the AF 200/4D 1:1 F11 sharpest frame.
3. `methods/maze_fft.py` (annulus sum). Unit-test against the
   AIS-55mm-tile maze peak from the prototype agent script at
   `/tmp/ais_fft_analysis.py` (known peak at ~0.333 cy/px).
4. Phase 1 wiring (`analyse.py` emits `per_shot_per_tile.csv`).
   Run on `out_55mm` to validate AIS argmax pick.
5. Phase 2 wiring (`peaks_v2.csv`). Validate against the
   `/tmp/ais_fft_analysis_run2.log` numbers.
6. Phase 3 (`characterise.py`). Validate against the planned
   decentering / curvature numbers on a known-clean slug.
7. Wire `peaks_v2` into the HTML report.
8. Run on `out_bare1to1`, `out_resized1to1`, `out_55mm` cohorts;
   add a row in the HTML report's per-cohort summary for the
   new column set.

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

## Open questions to resolve during implementation

- **LSF reference frequency for argmax**: pick a fixed
  spatial frequency (e.g., 0.10 cy/px on sensor) for the
  `lsf_peak_amp` column, or use the per-shot MTF50 itself?
  MTF50 is more interpretable but more noise-prone in low-signal
  shots. Tentative: ship both columns, decide which drives argmax
  empirically.
- **Maze frequency calibration**: ship with `maze_pitch_um = 13.0`
  (back-solved from one AIS 55mm 1:1 tile; period 3 px × 4.35 µm).
  Validate against one frame per dataset family to confirm the
  pitch is stable across captures.
- **9-position sampling exact tile indices**: the current 5×7 grid
  uses `ix ∈ [-3, +3]`, `iy ∈ [-2, +2]`. DX corners would be
  `(±2, ±1)` roughly; FX corners `(±3, ±2)`. Verify against the
  actual DX-region size on Z7.
- **Plane fit weighting**: weight per-tile by inverse-variance of
  the argmax (noisier tiles down-weighted)? Probably overkill for
  v1; uniform weighting is fine.

## Pointers

- Methodology: `analyse-lens-test/SHARPNESS_METRICS.md` "2026-05-16
  update — methodology supersedes the POC"
- Prototype maze-FFT script: `/tmp/ais_fft_analysis.py`
  (per-shot per-tile FFT, agent-built)
- Decentering heatmaps from validation: `/tmp/ais55_decentering_*.png`
- Visual validation of filesize failure:
  `/tmp/ais287318_centre_{filesize_pick_shot037,fft_pick_shot030}.png`
  (also copied to `nufan:/tmp/`)
