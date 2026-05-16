# tile-sharpness

POC: tile-grid sharpness analysis across a focus sweep. Compares
eight sharpness metrics per tile-position and surfaces (a) tiles where
the metrics disagree on which shot is sharpest, and (b) cross-lens
rankings on cohorts of related sweeps. Sibling of `rail-coverage/`
and `resize-bulk/`; reuses `lens-test-detect-core` for MCU alignment
and smoothing.

## What it does

For one focus sweep (constant lens/diopter/aperture, varying rail
position), and for each of N=35 (default) tiles on the 8256×5504
frame:

1. Lossless-crop the tile from every shot in the sweep
   (`TurboJPEG.crop_multiple`, MCU-aligned, zero re-encode loss).
2. Label the tile position as on/off-target via a peak-file-size
   cross-compare plus a content tiebreaker (mean / std-dev luminance).
3. For each registered method, compute the metric per shot, smooth
   across the sweep, and record `(peak, argmax_rail_step)` for that
   tile.
4. Compare methods pairwise on peak Spearman ρ, argmax Spearman ρ, and
   argmax-within-±1 fraction.
5. Export the top-K tile positions where methods most disagree, as
   side-by-side per-method tile JPEGs in a per-tile directory with a
   README.

The `compare` and `cross-lens-crops` subcommands extend this to
cross-sweep aggregation: rank lenses per tile-position, summarise
agreement across methods, and dump per-(method, lens) peak crops
side-by-side for manual evaluation.

## Methods implemented

| key | what it measures | orientation |
|---|---|---|
| `filesize` | `os.path.getsize(tile.jpg)` | higher = sharper |
| `mtfmapper` | slanted-edge MTF50 via `mtf_mapper --single-roi`, run remotely over SSH to nufan (see "SSH setup" below) | higher = sharper |
| `radial_fft` | high/low radial PSD band ratio (`E[0.30, 0.45 cy/px] / E[0.10, 0.20 cy/px]`), Hann-windowed | higher = sharper |
| `edge_decay` | Canny + Marziliano per-edge perpendicular width | lower = sharper |
| `laplacian_var` | variance of Laplacian (classic autofocus) | higher = sharper |
| `tenengrad` | mean Sobel² (classic autofocus, different bias from Laplacian) | higher = sharper |
| `dct_kurtosis` | kurtosis of 8×8 DCT AC coefficients (Ferzli-Karam variant) | lower = sharper |
| `wavelet_ratio` | 3-level db2 detail/approx energy ratio | higher = sharper |

The `MethodSpec.orientation` field tells aggregation/plots which sense
each metric uses, so adding a new method is one entry in `METHODS`.

### Per-method caveats

* **`radial_fft`** is a deviation from `SHARPNESS_METRICS.md §2`. The
  original four-parameter `P(f) = A · f^(-α) · |MTF(f)|² + N₀` fit
  was tried first but σ saturated at the physical lower bound on
  most in-focus tiles, leaving the fitted MTF50 identical across the
  frame. The band-ratio is the same essential idea (more high-band
  energy = sharper) without the unstable curve fit. The argmax
  across a sweep is biased upward by near-Nyquist JPEG quantisation
  noise on heavily defocused frames — use it for ranking tiles
  within a known-good shot, not for picking which shot is in focus.
* **`mtfmapper`** uses `--single-roi` because the default
  component-finding step fails on wafer tiles ("No black objects
  found" — the wafer isn't a chart with isolated dark targets).
  Empirically unreliable on this dataset (see findings below).
* **`edge_decay`** quantises to integer pixels; on these crops
  Marziliano width saturates at 4–5 for most tiles, producing ties.
  Useful only for the *argmax* (which rail step within a sweep), not
  for peak-magnitude ranking across tiles or lenses.

## SSH setup for `mtfmapper`

The locally built `mtf_mapper` binary was linked against an old
OpenCV version that no longer matches the local Arch install. The
working setup is:

* `mtf_mapper` runs on **nufan** (Ubuntu 25.10, OpenCV 4.10). The
  binary was rebuilt there in-tree at `MTF mapper/workspace/mtfmapper/bin/mtf_mapper`.
  Since the workspace is on the shared mount, the path resolves
  identically on both hosts. The previous locally-built (Arch) binary
  no longer exists — it was removed during a failed local rebuild
  attempt; nufan is now the canonical host for this method.
  Apt packages required for the rebuild on Ubuntu 25.10:
  `libopencv-dev libeigen3-dev libtclap-dev qtbase5-dev`
  `libqt5charts5-dev libexiv2-dev gnuplot exiv2 dcraw subversion`.
  Build steps: ``cd "MTF mapper/workspace/mtfmapper" && rm -rf
  CMakeCache.txt CMakeFiles && cmake ../mtfmapper-code && make
  -j$(nproc)``.
* The tile cache lives on the shared mount at
  `~/shared/projects/personal/fotografie/.tile-sharpness-cache/`,
  so nufan can read tile JPEGs by path without copying.
* `subprocess.run(["ssh", "nufan", ...])` with `ControlMaster=auto`
  and `ControlPersist=120s` keeps one SSH connection warm across
  hundreds of calls. Steady-state cost ≈ mtf_mapper compute time + a
  few ms of channel demux per call (~400-500 ms / tile).
* `tile-sharpness analyse` probes for SSH availability at startup;
  if nufan isn't reachable the method is silently skipped with a
  warning.

## Usage

```sh
uv run tile-sharpness list-sweeps                 # all available sweeps
uv run tile-sharpness list-sweeps --family newer  # only newer-rig

uv run tile-sharpness analyse <substring-of-label> \
    --out out/ \
    [--tile 1024] [--methods filesize,wavelet_ratio,...] \
    [--workers 8] [--top-disagreement 8]

# After analyse, secondary aggregations:
uv run tile-sharpness compare <out>/peaks.csv
uv run tile-sharpness cross-lens-crops <out>/peaks.csv \
    --out <out>/cross_lens_crops \
    --tile 0,0 --tile 3,0 --tile -3,0 --tile 0,2 --tile 0,-2
```

`<substring-of-label>` must uniquely identify one sweep. Multiple
sweeps can be analysed in one run by passing several substrings.

Outputs in `out/`:

* `peaks.csv` — one row per `(sweep, method, tile)` with peak value, argmax index, argmax rail position.
* `agreement.csv` — one row per `(sweep, method-pair)` with Spearman ρ and argmax-match fractions.
* `plots/<sweep>.png` — 2-row × N-method heatmaps (peak + argmax).
* `plots/agreement_summary.png` — cross-sweep agreement scatter.
* `disagreement/<sweep>/tile_<ix>_<iy>/shot_*.jpg` + `README.txt` — manual-review crops at the top-K disagreement positions.

After `compare` is run:

* `cross_lens_per_tile.csv` — lens ranks per `(method, ix, iy)`.
* `cross_lens_centre.csv` — pivoted centre-tile ranks for every method.
* `cross_lens_centre_agreement.csv` — Spearman ρ across methods on the centre-tile ranking.
* `cross_lens_ranks.png` — per-sweep × per-method rank heatmaps.
* `symmetric_corner.csv` + `.png` — paired ±(ix, iy) tile-peak asymmetry per (sweep, method), bars away from 0 suggest decentering/tilt.

After `cross-lens-crops`:

* `tile_<ix>_<iy>/<method>__<lens>__shot_<k>.jpg` — peak crops per (method, lens) side-by-side, with `README.txt` listing per-method picks.

## LSF + maze-FFT pipeline (2026-05-16 methodology)

Per `SHARPNESS_METRICS.md` "2026-05-16 update", primary sharpness
analysis runs through the `phase1` + `characterise` modules (the
eight POC methods stay available as cross-validation columns in
`peaks.csv`). The `analyse` subcommand grew two flags + one new
follow-up subcommand:

```sh
# Phase 1 + Phase 2: per_shot_per_tile.csv + peaks_v2.csv
uv run tile-sharpness analyse <sweep> [<sweep>...] \
    --out out/ \
    --manifest /path/to/wafer-manifest-2026-01-29.csv \
    [--manifest /path/to/another.csv ...] \
    [--no-legacy]

# Phase 3: lens_characteristics.csv (one row per sweep)
uv run tile-sharpness characterise out/peaks_v2.csv
```

* `--manifest` is repeatable — supply one or more wafer-manifest CSVs
  produced by `archive-2026-05/measure_wafer_squares`. Without a
  matching manifest row the pipeline falls back to path-parsed
  `claimed_mag` and flags `m_source = "path_parsed"` in the output.
* `--no-legacy` skips the 8-method `peaks.csv` / `agreement.csv` pass
  for fast iteration on the new methodology.

Additional outputs in `out/` when the LSF + maze-FFT pipeline runs:

* `per_shot_per_tile.csv` — one row per `(sweep, tile_ix, tile_iy,
  shot_idx)` with `lsf_peak_amp`, `lsf_mtf50_cy_per_px`, `maze_fft_amp`,
  `maze_resolves`, plus the M-driven per-metric ROI sizes
  (`lsf_roi_px`, `maze_roi_px`) and `filesize_bytes` / `on_target` for
  back-compat.
* `peaks_v2.csv` — one row per `(sweep, tile_ix, tile_iy)`. Picks
  the primary metric per the IMPLEMENTATION_PLAN's rule
  (`maze_fft` when `maze_resolves`, else `lsf`, else
  `filesize_fallback` for off-target tiles). Includes subject-space
  MTF50 (`mtf50_subject_lp_per_mm`).
* `lens_characteristics.csv` (after `characterise`) — per-slug
  centre + DX-ring + FX-ring MTF50, uniformity, peak-value
  decentering (per the IMPLEMENTATION_PLAN: peak-VALUE, not
  peak-INDEX), plane-fit subject-tilt + field-curvature.
  `n_positions` and `note` flag degenerate grids — at extreme M the
  M-driven ROI may not permit all 9 conceptual positions.

ROI sizing is M-driven: `lsf_roi_px = max(3 × die_period_px, 1024)`
and `maze_roi_px = max(64 × maze_period_px, 256)`, then aligned up to
a 16-multiple. Per the accuracy-over-granularity policy in
`CLAUDE.md`, ROIs may overlap with neighbouring tile cells; at extreme
M a sweep may degenerate to a single centre-only ROI.

Scribe detection is a two-stage pipeline:

1. **OpenCV LSD** (`opencv-contrib-python`) finds the longest dark
   line that's at least `min_length_px=200` pixels and sits
   `darkness_margin=15` units below the ROI mean.
2. **Probabilistic Hough fallback** (when LSD returns nothing):
   `skimage.transform.probabilistic_hough_line` over Canny edges,
   then group by angle, cluster by perpendicular offset, span the
   dominant cluster's endpoints to recover a single long composite
   line. The wafer scribes show up in LSD output as 400–700 px
   fragmented segments inside a ~3456 px ROI; Hough's linking step
   joins those fragments into a span that averages ~3240 px (4.7×
   longer cross-section anchor, more samples for the LSF profile).

On `out_55mm` AIS sweeps the two-stage detector achieves 90 %
per-tile scribe detection (LSD-only: 43 %). Cost: Hough adds ~3 s
per ROI but Phase 1 caches scribe detection at the filesize-argmax
shot, so it's sweep-level overhead, not per-shot.

MTF50 is computed via classic slanted-edge mechanics rather than
FFTing the whole trough — wafer scribes are 20-px-wide dark bands,
not impulses, so the trough-FFT path is scribe-width-limited at
~11 lp/mm regardless of lens. The trough is split at its deepest
point, each side treated as an ESF, differentiated to an LSF,
FFTed; MTF50 is the arithmetic mean of the left and right per-edge
values.

Phase 1 also gates out non-scribe features that LSD/Hough accepts
as long dark lines but whose troughs are too narrow to support the
ESF→LSF method (bond-pad shadows, single dark texture artefacts,
etc.). The measured trough FWHM is recorded in
`per_shot_per_tile.csv` as `trough_fwhm_px`; rows where it falls
below half the predicted scribe FWHM at the sweep's M
(`SCRIBE_WIDTH_UM × M / sensor_pitch`) get their LSF columns NaN-out.

### Validation (tasks 1 + 3 from IMPLEMENTATION_PLAN)

* AIS 287318 vs 537016 centre-tile maze-FFT amp ratio = **1.0412**
  (target ≤ 1.05). The POC's reported "5.8× decentering" was a
  filesize mis-pick artifact and is no longer visible under the
  maze-FFT picker.
* AF 200/4D 1:1 F11 centre subject MTF50 = **42.7 lp/mm** (expected
  ~33; well within the f/11 diffraction-limit envelope of ~67 lp/mm).
  AIS 287318 centre: 45.1 lp/mm.

## Empirical findings (POC 2026-05-15) *— partially superseded; see 2026-05-16 update below*

Validated on four cohorts: a within-sweep manual review (24-120 +
Raynox M-250 @ F8), bare native macros at 1:1 F8 (4 lenses), resized
1:1 cross-config at F8 (6 lens combos), and multi-copy 55mm primes at
1:1 F8 (5 sweeps). Full numbers + reasoning are in
`../SHARPNESS_METRICS.md`'s "Empirical results" section. Headlines:

1. **`mtfmapper` is unusable on this rig.** Three independent
   strikes: 1/5 on manual within-sweep review; completely flat on
   the resized cross-config cohort (all lenses rank ≈ 3.3); CV =
   0.54 across same-model copies vs 0.02–0.18 for every other method.
2. **`filesize` is more robust than its reputation.** 5/5 on the
   manual within-sweep check; ρ ≈ 0.94 with `wavelet_ratio` and
   `laplacian_var` on the resized cross-config cohort. Known failure
   mode (content-fooled when framings differ slightly) shows up only
   on narrow cross-frame comparisons.
3. **`wavelet_ratio` is the best new cross-frame supplement.** Picks
   up the consensus ranking on cross-config (ρ ≈ 0.83–0.94 with
   filesize) and gets the AIS-vs-Auto distinction right on
   multi-copy. The LL-approximation normalisation compensates for
   different framings — exactly the property §6 of
   `SHARPNESS_METRICS.md` claims for it.
4. **`dct_kurtosis` is the most stable across same-model copies**
   (CV = 0.032, second only to `edge_decay`'s quantisation-trick
   zero). Useful as a calibration stability check.
5. **`radial_fft` argmax is unreliable** because near-Nyquist noise
   inflates the high-band on defocused frames. Its peak-tile-ranking
   correlates fine with consensus; its picking-the-focus-shot does
   not.
6. **`edge_decay`'s peak** is useless (integer-pixel ties); its
   *argmax* matches filesize ~38% within ±1 step — keep for
   sanity-check on focus shot only.

### Recommended combinations

| use case | primary | sanity check |
|---|---|---|
| within-sweep argmax (which rail step is sharpest) | `filesize` | `edge_decay` argmax |
| cross-lens ranking, similar framing | `filesize` | `wavelet_ratio` |
| cross-config ranking, different framings | `wavelet_ratio` | `dct_kurtosis` |
| same-model copy consistency | `dct_kurtosis` | `filesize` |

Disagreement of more than ~2 ranks between primary and sanity-check
on a 4–6-lens cohort is the threshold for manual inspection via
`cross-lens-crops`.

## 2026-05-16 update — methodology shift

A follow-up empirical pass on the AIS 55mm cohort surfaced a
filesize-argmax failure mode at sharp configs and replaced the
recommended-setup table above. **Read `../SHARPNESS_METRICS.md`
"2026-05-16 update — methodology supersedes the POC" before
running any new cohort.** Short version:

* `filesize` argmax picks 6-10 shots past true peak on sharp configs
  (1:1+ with quality glass, F8-F11), with disagreement rates of
  54-74 % vs maze-FFT argmax on AIS 55mm. Use maze-FFT or scribe-LSF
  argmax for sharp configs; `filesize` is fine on soft chains where
  the bell curve has a steep peak.
* New primary methods: **scribe-LSF MTF50** (universal) and
  **fine-maze 2D-FFT amplitude** (sensitive, requires M ≥ 0.7×).
  Both subsume the eight POC methods.
* Cross-config metric is **subject-space MTF50** (`= MTF50_sensor ×
  M × 229.9` on Z7). Resized cohorts are kept for visual comparison
  only — Lanczos overshoot biases any measurement on them by ~20 %.
* Per-metric ROI sizing depends on measured magnification (from
  `archive-2026-05/measure_wafer_squares`). The fixed 1024-px tile
  works for maze-FFT at 1:1 (340 cycles per side) but is too small
  for scribe LSF (die period ~1100 px at 1:1).
* Cross-lens crop directories under `out_*/cross_lens_crops/` are
  filesize-picked and are **not safe** for further numerical analysis
  at sharp configs. Eyeball review is fine; numerical re-runs should
  regenerate via FFT-argmax picks.

The eight POC scoring methods remain available as cross-validation
columns. Empirical reversal worth noting: the POC's "AIS 287318 looks
5.8× softer than 537016 at the centre tile" finding was a filesize
mis-pick artifact, not a real optical difference; the two AIS copies
are essentially identical when each tile is evaluated at its own
maze-FFT amplitude peak.

## Caveats

* Absolute metric values are not comparable between dataset families
  (`newer-rig` uses FINE-quality JPEGs from the rig; `older-*` uses
  slightly lower JPEG quality). Per-sweep peak/argmax and
  within-cohort cross-lens rankings remain valid.
* Tile cache lives at
  `~/shared/projects/personal/fotografie/.tile-sharpness-cache/`
  keyed by source path + mtime + size. Safe to delete; will be
  regenerated.
* The cache is on the shared mount specifically so nufan can read
  tiles for `mtfmapper` over SSH. If you move it back to a host-local
  path, you'll need to either run `mtfmapper` locally or pipe tile
  bytes over SSH per call.
