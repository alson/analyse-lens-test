# tile-sharpness

POC: tile-grid sharpness analysis across a focus sweep, comparing
four metrics per tile-position and surfacing tiles where the metrics
disagree on which shot is sharpest. Sibling of `rail-coverage/` and
`resize-bulk/`; reuses `lens-test-detect-core` for MCU alignment and
smoothing.

## What it does

For one focus sweep (constant lens/diopter/aperture, varying rail
position), and for each of N=35 (default) tiles on the 8256×5504
frame:

1. Lossless-crop the tile from every shot in the sweep
   (`TurboJPEG.crop_multiple`, MCU-aligned, zero re-encode loss).
2. Label the tile position as on/off-target via a peak-file-size
   cross-compare plus a content tiebreaker (mean / std-dev luminance).
3. For each method in `{filesize, mtfmapper, radial_fft, edge_decay}`,
   compute the metric per shot, smooth across the sweep, and record
   `(peak, argmax_rail_step)` for that tile.
4. Compare methods pairwise on
   - peak Spearman ρ (do they rank tile positions the same way?),
   - argmax Spearman ρ (do they pick the same shot order across tiles?),
   - argmax-within-±1 fraction (do they pick the same shot, exactly?).
5. Export the top-K tile positions where methods most disagree, as
   side-by-side per-method tile JPEGs in a per-tile directory with a
   README.

## Methods implemented

* **filesize** — `os.path.getsize(tile.jpg)`. Higher = sharper.
* **mtfmapper** — wraps the locally built `mtf_mapper` (slanted-edge
  MTF50 in cycles/pixel). Activates once the binary is rebuilt against
  the current OpenCV.
* **radial_fft** — Hann-windowed 2D FFT, radial average, **high/low PSD
  band ratio** (`E[0.30, 0.45 cy/px] / E[0.10, 0.20 cy/px]`). Higher =
  sharper.
  *Deviation from* `SHARPNESS_METRICS.md §2`: the original four-parameter
  `P(f) = A · f^(-α) · |MTF(f)|² + N₀` fit was tried first but σ
  saturated at the physical lower bound on most in-focus tiles, leaving
  the fitted MTF50 identical across the frame and useless for ranking.
  The band-ratio is the same essential idea (more high-band energy =
  sharper) without the unstable curve fit. Note that it is biased
  upward by **near-Nyquist noise on heavily defocused tiles**, so its
  argmax across a sweep is unreliable when the sweep includes very
  out-of-focus shots (see the Raynox M-250 run for a clear example).
* **edge_decay** — Canny + Marziliano per-edge perpendicular width.
  Lower = sharper.
  *Known bias*: dense edge regions saturate the per-edge walk early
  (a neighbouring edge looks like a local extremum), making
  detail-dense centre tiles appear *wider* than sparse-edge corner
  tiles. The per-tile *argmax* across a sweep is still meaningful;
  the per-tile *peak* is not directly comparable across tile
  positions.

The `MethodSpec.orientation` field tells aggregation/plots which sense
each metric uses, so adding a new method is one entry in
`METHODS`.

## Usage

```sh
uv run tile-sharpness list-sweeps                 # all available sweeps
uv run tile-sharpness list-sweeps --family newer  # only newer-rig

uv run tile-sharpness analyse <substring-of-label> \
    --out out/ \
    [--tile 1024] [--methods filesize,radial_fft,edge_decay] \
    [--workers 6] [--top-disagreement 8]
```

`<substring-of-label>` must uniquely identify one sweep. Multiple
sweeps can be analysed in one run by passing several substrings.

Outputs in `out/`:

* `peaks.csv` — one row per (sweep, method, tile)
* `agreement.csv` — one row per (sweep, method-pair)
* `plots/<sweep>.png` — 2-row × N-method heatmaps (peak + argmax)
* `plots/agreement_summary.png` — scatter of agreement scores across sweeps
* `disagreement/<sweep>/tile_<ix>_<iy>/shot_*.jpg` — manual-review crops
* `disagreement/<sweep>/tile_<ix>_<iy>/README.txt` — per-method picks

## Caveats

* `mtf_mapper` is currently un-runnable on this host
  (`libopencv_imgcodecs.so.410` missing; system has 4.13). The method
  is fully implemented and will start producing results once the
  binary is rebuilt; until then it's silently skipped with a startup
  warning.
* Absolute metric values are not comparable between dataset families
  (`newer-rig` is FINE-quality JPEGs from the rig; `older-*` is
  slightly lower JPEG quality). Per-sweep peak / argmax comparisons
  remain valid.
* Tile cache lives in `~/.cache/tile-sharpness/` keyed by source path
  + mtime + size. Safe to delete; will be regenerated.
