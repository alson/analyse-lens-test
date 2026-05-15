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
  identically on both hosts.
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

## Empirical findings (POC 2026-05-15)

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
