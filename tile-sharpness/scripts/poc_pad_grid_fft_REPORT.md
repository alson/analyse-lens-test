# POC: pad-grid 2D-FFT amplitude as a low-M sharpness metric (Task 2)

Date: 2026-05-17.  Author: Claude POC session.  Status: results in,
unmerged. Production code untouched.

## TL;DR
- **Chosen pitch**: 18.37 µm (4th harmonic of a ~76 µm pad-grid fundamental
  visible as discrete spots in the 2D FFT of the Task 2 centre crop).
- **Centre pad-FFT argmax**: 119, vs LSF argmax 137 — **MISMATCH (-18 shots)**.
- **Argmax std-dev across 5 tiles**: 6.31 shots (18 µm) / 2.71 shots (70 µm).
- **Practical takeaway**: the LSF argmax shot lands within **0.5–3.3 % of
  the pad-FFT peak** at 18 µm (rank 7–28 out of 142). So the metric is
  picking up the same broad focus region, but argmax is slipped by ~3 % of
  the rail in a direction that's consistent across tiles. Useful as a
  peak-value metric, **not** a drop-in replacement for LSF argmax.

## 1. Pitch discovery

`scripts/poc_pad_grid_fft.py --discover-only` on shot 137 centre tile
(1024 × 1024 crop @ M=0.385).

Radial 1D spectrum (`radial_spectrum.png`) is **monotonically decreasing**
in the 0.02-0.20 cy/px band — there is **no clean radial peak**. The top
five local maxima sit on a 1/f-like decay and are essentially the
broadband texture envelope.

The 2D FFT (`fft2d_zoom.png`, `fft2d_deviation_zoom.png`) tells a
different story: an axis-aligned grid of discrete spots at (fx ≈ ±0.007,
fy ≈ k × 0.022) cy/px and its 90°-rotated copy. Subtracting a running-mean
radial baseline brings out the top peaks:

| fx     | fy     | r (cy/px) | subject pitch @ M=0.385 |
|--------|--------|-----------|--------------------------|
| ±0.007 | ±0.091 | 0.091     | **18.4 µm** (4th harmonic) |
| ±0.006 | ±0.068 | 0.069     | 24.4 µm                 |
| ±0.018 | ±0.205 | 0.206     | 8.1 µm (near maze, ~Nyquist) |
| ±0.008 | ±0.098 | 0.098     | 17.1 µm                 |
| ±0.016 | ±0.192 | 0.193     | 8.7 µm                  |

The grid fundamental is ~76 µm (at ±0.022 cy/px on sensor) — the bright
column near fx≈0 with peaks repeating every ~0.022 in fy. The 18.4 µm
spot is the 4th harmonic and is the **brightest** because the broadband
trend is much lower there (better SNR over local baseline).

Two candidate pitches were taken forward: 18.37 µm (4th harmonic; clean
SNR) and 70.45 µm (fundamental; high amplitude but Talbot-prone — see §3).

## 2. Algorithm summary

`pad_grid_amp(image_2d, M, pitch_um, *, half_bandwidth=0.015)` mirrors
`methods/maze_fft.maze_amp`: mean-subtract → 2-D Hann window → 2-D FFT →
`fftshift` → mean |FFT| amplitude in an annulus of radius
`f = M × sensor_pitch_um / pitch_um` cy/px ± `half_bandwidth`. ROI is
1024 × 1024 px (wider than maze's 256 px because the pad fundamental
has only ~5-cycle support per maze-ROI at M=0.385). Returns `None` if
the band aliases past Nyquist or overlaps DC. Per-pixel mean over the
annulus is divided by ROI area to keep numbers comparable across crop
sizes (same convention as `maze_amp`).

## 3. Per-shot sweep — 5 tiles × 142 shots

Centre + 4 mildly off-axis on-target tiles
(centre 0,0 = (4128, 2752) px; left/right-mid ±1 in x;
above/below-mid ±1 in y).

### Pitch = 18.37 µm
```
tile         (ix,iy)  pad_argmax lsf_argmax  fs_argmax     pad_peak
centre       (0,0)           119        137        137      404.005
left-mid     (-1,0)          129        141        141      403.418
right-mid    (1,0)           124        137        137      342.207
above-mid    (0,-1)          137        139        137      441.237
below-mid    (0,1)           122        141        141      391.587
```
Pad-FFT argmax std-dev: **6.31 shots** across 5 tiles.
Value at LSF argmax shot is **0.5–3.3 % below pad-FFT max**; LSF argmax
shot ranks 7–28 out of 142 in the pad-FFT curve. The pad-FFT curve has
a broad plateau (≥ 99 % of max spans 9–19 consecutive shots) that
includes the LSF argmax.

### Pitch = 70.45 µm (fundamental)
```
tile         (ix,iy)  pad_argmax lsf_argmax  fs_argmax     pad_peak
centre       (0,0)            99        137        137      254.742
left-mid     (-1,0)          101        141        141      263.729
right-mid    (1,0)           101        137        137      245.613
above-mid    (0,-1)          101        139        137      368.056
below-mid    (0,1)            94        141        141      311.336
```
Pad-FFT argmax std-dev: **2.71 shots** — tighter than 18 µm but argmax is
way off from LSF (Δ ~ -38 shots). Curves show heavy oscillation between
shots ~10-80 (likely **Talbot self-imaging**: the periodic 76-µm object
has Talbot length z_T = 2P²/λ ≈ 2 × (76e-6 × 0.385)² / 0.55e-6 ≈ 3.1 mm —
small enough that the rail steps repeatedly cross self-image planes).
At the fundamental, this Talbot ringing dominates and the metric's
argmax should not be trusted.

The 18.37 µm 4th-harmonic has the same Talbot ringing but at much
shorter z_T (~75 µm rail), so it averages out over the rail step into a
smoother curve.

## 4. Verdict

**Viable for peak-value comparison; NOT a drop-in argmax replacement.**

Suggested use cases:
- **Subject MTF50 / decentering peak-value** at low M — pad-FFT amplitude
  at the 18 µm harmonic is a real high-frequency-content signal whose
  peak value rises with focus quality. Useful for cross-tile comparison
  (decentering reads off ratios of peak values, not argmaxes).
- **Sanity gate for "we're in the focus zone"** — when pad-FFT > 0.95 ×
  pad-FFT-max across N consecutive shots, the rail is on the focus
  plateau. The LSF argmax should be inside that window.

Not suitable for:
- **Cross-config / cross-lens absolute MTF50 readout** at low M — argmax
  drifts 3 % of rail vs LSF, and the value depends on local pad-grid
  density which varies across the wafer. Two different on-target tiles
  on the centre die may sit on different pad subgrids.
- **Replacing LSF argmax at the per-tile rollup** — the consistent
  ~18-shot leading-edge bias would degrade `rail_position_mm_at_argmax`.

## 5. Honest remaining issues

1. **Talbot ringing.** At the fundamental (76 µm) and weaker at the 4th
   harmonic (18 µm). A truly low-M sharpness metric should subtract or
   ignore the oscillating component — possibly by integrating across a
   range of pitches rather than locking to one.
2. **Pad-grid is not universal across the wafer.** The maze pattern (per
   `maze_fft.py` docstring) is "universal across every die except inside
   the scribes themselves". The pad-grid only appears on dies that have
   bond pads — at low M with 8000-px-wide subject coverage we may
   straddle pad-less zones. Off-axis tiles likely see varying pad
   density, which is why peak-values vary 342-441 across tiles.
3. **No clean radial peak.** Argues against using a 1-D radial spectrum
   for pitch discovery on future datasets; the 2-D deviation-above-
   baseline approach is necessary and not automatable without manual
   inspection.
4. **18-shot argmax bias** is consistent across tiles (std-dev 6.3), so
   it's a real signal — but its sign and magnitude depend on rail
   direction. Without knowing whether shot 0 is far-focus or near-focus
   we can't say if pad-FFT is "early" or "late" relative to true focus.
5. **Sanity sweep on AF 200 @ M=1.0 not run** — JPEGs are on the same NFS
   mount and copying them locally would add another ~10 min. Skipped per
   the user's "if time-constrained" allowance. The maze gate at M=1.0
   already works for that case; the value of validating pad-FFT there is
   low.

## Files produced

- `scripts/poc_pad_grid_fft.py` — main POC script.
- `scripts/poc_pad_grid_fft_2dview.py` — one-shot 2-D FFT visualisation
  for pitch discovery.
- `scripts/poc_pad_grid_fft_out/radial_spectrum.{csv,png}` — 1-D radial
  spectrum at shot 137.
- `scripts/poc_pad_grid_fft_out/fft2d_{overview,zoom,deviation_zoom}.png`
  — 2-D FFT and deviation-above-baseline plots.
- `scripts/poc_pad_grid_fft_out/pad_fft_per_shot_pitch{18.37,70.45}um.csv`
  + matching `pad_fft_curves_pitch*.png`.

## Notes for the next session

- NFS on bumblebee stalled for ~3 min per JPEG decode on the first run;
  the script now reads from `/tmp/poc_jpegs` when present and only walks
  the NFS tree if that cache is absent. Re-run with
  `direnv exec . uv run python scripts/poc_pad_grid_fft.py --pitch-um=X`.
- The synthetic `_build_sweep_from_cache` skips `discover_all()`. Remove
  if/when this is promoted to a method module.
