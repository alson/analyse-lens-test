# Analysis Notes — Macro Lens Sharpness Test Data

This document records the data-driven findings from the rail-coverage
analyser run on the combined 2026-01-29 + 2026-02-18 test sessions
(545 scenarios across 65 distinct lens / magnification / focal /
aperture configurations). It is the empirical companion to
`run-lens-test/DESIGN_NOTES.md` (which covers the live-capture rig)
and `analyse-lens-test/rail-coverage/` (the offline analyser code).

The findings here drive the constants in
`run-lens-test/sharpness/planner.py` and the shape of the reshoot
plan in `reshoot-plan-2026-05.md`.

---

## 1. Source data

Two test sessions captured to NFS at
`~/shared/files/pics/digikam/test-raw-data/`:

- `2026-01-29/` — 216 scenarios, mostly F-mount lenses + close-up
  filter combinations on the Sigma 150 / Nikon AF 200 / Nikon AF
  70-180 / Nikon 55 AIS, plus the NIKKOR Z 100-400 with various
  add-ons.
- `2026-02-18/` — 330 scenarios, primarily NIKKOR Z 24-120 with
  extension tubes and close-up filters at multiple focal lengths
  (also covers some "resized" magnification trees that don't fit
  the lens-name path layout).

Path layouts vary across the two sessions. The analyser supports:

```
.../<lens>/<magnification>/<aperture>/cropped                          # 2026-01-29
.../<lens>/<magnification>/<focal_length>/<aperture>/cropped           # 2026-02-18 normal
.../<date>/<magnification-resized>/<focal_length>/<aperture>/cropped   # 2026-02-18 top-level resized
.../<lens>/.../<f_dirty>/<aperture>/cropped                            # F16.0/F16/cropped sort artefact
```

Each `cropped/` folder has nine 512×512 sub-folders (centre, four
edges, four corners) plus optionally eight `dx-*` sub-folders for
APS-C-equivalent sub-frames; each contains the captured shots'
full-resolution centre crop saved as JPEG. **File size is the
sharpness proxy** (matches `select-crops.sh` in the existing
pipeline) — JPEG entropy-coded length scales with the amount of
detail in the crop, so larger files = sharper.

Sub-crops are now produced losslessly via
`TurboJPEG.crop_multiple` (re-packing the source's encoded MCU
blocks into the output JPEGs without decoding+re-encoding). The
512-pixel side length is the smallest 16-multiple at or above the
historical 500-pixel size, which is what lets the lossless transform
work — see `resize-bulk/RESIZED_COMPARISON.md` §0.0 for the full
rationale. Older trees in this dataset were 500 px and re-encoded;
they are no longer numerically comparable to fresh output and need
re-generation.

---

## 2. Bell-curve detection methodology

For each scenario × crop combination, the rail-coverage analyser
builds a sequence of `(seq, file_size)` tuples sorted by capture
sequence and runs a small set of heuristics:

| Step | Function | Default |
|---|---|---|
| Smooth | 3-shot moving average | window=3 |
| Find peak | argmax of smoothed series, mapped to raw index | — |
| Truncation | peak inside first/last `edge_shots` raw shots | 6 |
| Flat profile | `max/min < ratio_threshold` ⇒ off-target | 1.15 |
| Cross-crop off-target | crop's max < `factor × best_max_in_scenario` | 0.65 |

Source: `lens-test-detect-core/src/lens_test_detect_core/primitives.py`
(shared between this offline analyser and the live `sharpness`
package in `run-lens-test/`).

The thresholds differ between the two consumers because of input
granularity:
- **rail-coverage** sees ~3 raw shots per rail position → `edge_shots = 6`
  (about 2 rail positions of buffer at each end).
- **sharpness/planner** sees one shot per rail step (rail-step-outer,
  aperture-inner architecture) → `edge_steps = 2`.

---

## 3. Resampling experiment — how many samples to find the peak

Question: does the historical 25-position × 3-replica setup find the
sharpness peak well? Could fewer (or more) samples do better?

Method: pick representative bell curves from the cache, fit a
quadratic to the smoothed series for the "ground-truth" peak, then
re-pick using only k of the 25 rail positions (evenly spaced) and
measure the percentage sharpness loss vs the fitted ground-truth.

Six scenarios tested (all from 2026-01-29):
- Sigma 150 at 1:1, F5.6 / F8 / F11 / F16 (sharpness-vs-aperture sweep)
- Sigma 150 at 1.4:1 + TC-1401 / F8 (high-magnification with TC)
- Nikon AF 200 + 5T+6T at 2:1 / F8 (highest magnification tested)

Results (per-scenario rel_loss in % vs fitted peak; negative numbers
mean the sub-sample beat the smoothed fit because the per-position
noise can exceed the curvature signal):

| Scenario | k=3 | k=5 | k=8 | k=10 | k=15 | k=25 |
|---|---|---|---|---|---|---|
| Sigma 150 / 1:1 / F5.6 | 5.3 | 5.3 | -5.0 | -1.7 | -5.0 | -5.0 |
| Sigma 150 / 1:1 / F8 | 3.5 | 3.5 | -3.6 | -3.6 | -3.6 | -4.6 |
| Sigma 150 / 1:1 / F11 | 1.6 | 1.6 | -0.8 | -0.8 | -0.8 | -0.8 |
| Sigma 150 / 1.4:1 + TC F8 | 0.07 | 0.07 | -6.5 | -6.5 | 0.07 | -6.5 |
| **200mm 2:1 + 5T+6T / F8** | **6.5** | **6.5** | **4.0** | **3.8** | -1.2 | -3.0 |

Conclusions used to calibrate `sharpness/planner.py`:
1. **k = 8 across the whole sweep is enough at moderate magnification.**
   Translating sweep size to FWHM, 8 sub-samples / 25 ≈ 5 across FWHM
   → `POSITIONS_ACROSS_FWHM_DEFAULT = 5`.
2. **The high-mag case (200 mm 2:1) needs k=15** to land within 1 %.
   That's ~8 across FWHM at that scenario's bell width →
   `POSITIONS_ACROSS_FWHM_HIGH_MAG = 8`.
3. **k=25 vs k=15 is a wash.** Going beyond 25 positions doesn't help.
4. **Going below k=8 costs ~3-7 %** sharpness in non-high-mag scenarios
   and ~6.5 % in the high-mag case.
5. **Aperture isn't a useful axis for the bump table.** F11 and F16
   tolerate sparser sampling fine (broad bell, plateau-of-best frames
   spans many rail positions); F5.6 needs more density only because
   the peak is genuinely sharper. Both effects are captured by the
   DOF formula already.

The experiment script is preserved at `/tmp/resample_experiment.py`
(transient — recreate from the methodology above if needed).

---

## 4. Sample-density stratification by magnification

Per-scenario classification across the 545 scenarios:

| Bucket | Definition | Count | % |
|---|---|---|---|
| **good** | 2-3 rail positions within 1 % of peak | 224 | 41.1 |
| **wide** | 4-6 positions within 1 % | 154 | 28.3 |
| **very_wide** | 7+ positions within 1 % | 34 | 6.2 |
| **narrow** | ≤1.5 positions within 1 % (sharp peak) | 41 | 7.5 |
| **truncated** | peak inside first/last 6 shots | 49 | 9.0 |
| **all_off_target** | every crop's series is flat (target too small) | 43 | 7.9 |

Plateau-width median: **2.0 rail positions**. FWHM median: **11.3 rail
positions**. So the median scenario has a bell that fills 11 of the
25 rail positions at half-max, and the very top of the peak (within
1 % of max) spans 2 positions.

Stratified by magnification band:

| Band | n | good | wide+vwide | narrow | trunc | plateau | FWHM |
|---|---|---|---|---|---|---|---|
| very_low (<1:2) | 14 | 36 % | **43 %** | 0 % | **21 %** | **3.3** | 13.7 |
| low (1:2 to 1:1.18) | 90 | 41 % | 35 % | 1 % | 11 % | 3.0 | 15.0 |
| near 1:1 | 218 | 41 % | 36 % | 10 % | 6 % | 2.0 | 12.0 |
| **high (1:1 to 1.6:1)** | 64 | **58 %** | **17 %** | 16 % | 6 % | **1.3** | **9.3** |
| very_high (>1.6:1) | 159 | 35 % | 38 % | 5 % | 12 % | 2.0 | 10.0 |

Patterns:

- **Plateau width drops as magnification increases up to 1.6:1, then
  bumps back up.** Lower mag means the rail step is too fine for the
  DOF; higher mag (>1.6:1) sees variable behaviour, partly because
  rail-step sizing was inconsistent.
- **Truncation worst at the magnification extremes** (21 % at <1:2;
  12 % at >1.6:1). At very low mag the rail range is the limit; at
  very high mag the start-position calibration has tighter tolerances.
- **The 1:1-to-1.6:1 band is the sweet spot** — 58 % "good", lowest
  combined oversample (17 %), lowest FWHM (9.3) → most precise peaks.
  Macro lenses are designed for this range and the rail step matches
  it naturally.

---

## 5. Outliers in the >1.6:1 band

The very-high-mag band has the most variable behaviour. A drill-down
(141 scenarios with M ≥ 1.6) shows three patterns:

### 5.1 24-120 zoom — systematic oversampling

The NIKKOR Z 24-120mm zoom appears in this band only because of the
"resized" trees (where the source images are downsampled to simulate
2:1 magnification). The 24-120 + 26mm extension scenarios in
particular average **plateau width 4.0 rail positions** — twice the
overall median. This is structural: the 24-120 is a normal zoom, not
a macro, and its DOF behaves differently from a true macro lens at
the same nominal magnification.

The MC 105 + extensions (a real macro) average plateau **0.9-1.2** —
exactly what you'd expect for thin DOF at >1.6:1.

### 5.2 Sigma 150 + close-ups — truncation cluster

At magnifications ≥ 1.6:1, the Sigma 150 shows a striking truncation
rate when close-up filters are stacked:

| Variant | Truncated / total apertures |
|---|---|
| Sigma 150 + 6T | 3 / 4 |
| Sigma 150 + 5T+6T | 2 / 4 |
| Sigma 150 + 6T+5T | 3 / 3 |

vs the comparable Nikon AF 200 + 6T (0/5 truncated). The Sigma 150
+ stacked close-ups specifically need more rail range — the focus
point shifts further than expected when the diopters are stacked.

### 5.3 F16 broader plateaus across all lenses

At very high magnification the F16 row tends to be wide or very_wide
across all lenses tested (24-120, MC 105, Sigma 150, AF 200,
100-400). This is physics-consistent: F16 quadruples DOF vs F8, so
the bell broadens, plateau widens. The aperture-wise subsample
factors in `sharpness/planner.py` (`floor(N / N_min)`) compensate
for this on the analysis side.

### 5.4 Multi-session concatenation

88 scenarios across all bands have at least one crop folder with
> 30 rail positions (vs the typical 25). Most of these are
deliberately-extended single sweeps; some are partial reshoots
(droop interrupted, resumed later) where two sessions ended up in
the same folder. The `select_primary_chunk` filter in
`rail-coverage/scan.py` splits at seq gaps > 30 and keeps the
longest contiguous chunk; on the rescan that filter changed
**almost no aggregate statistics** — most "long" folders have
single contiguous sweeps with no large gaps.

---

## 6. Stacking-order analysis (5T+6T vs 6T+5T)

Question: does the order of stacked close-up diopters affect corner
sharpness?

Method: for each lens that has both 5T+6T and 6T+5T variants at the
same magnification, compute peak file size at the centre crop and
each of the four corner crops; report `corner_avg / center` ratios
side-by-side at each aperture.

| Lens | Best ordering at small ap | Magnitude |
|---|---|---|
| Sigma 150 (1:1.8) | **5T-toward-lens (5T+6T)** | +3 to +7 % corners F8-F16 |
| Sigma 105 (1:1.7) | no clear winner | sub-1 % either way |
| MC 105 (1:1.6) | **6T-toward-lens (6T+5T)** | +1 to +2 % corners F11-F16 |
| 70-180 (1:1.14) | **6T-toward-lens (6T+5T)** | +1.5 to +3.5 % corners F11-F16 |
| Nikon AF 200 (2:1) | **6T-toward-lens (6T+5T)** | +1.5 to +1.7 % corners F11-F16 |

Conclusions:
- **Stacking order matters.** Effect is real, lens-dependent, 1-7 %
  in corner sharpness at small apertures (where corners would be
  diffraction-limited otherwise).
- **Sigma 150 is the outlier.** Its rear element / close-up filter
  thread geometry behaves differently from the Nikon-style lenses.
- **At wide apertures the difference is sub-1 %** — corners are still
  resolution-limited, so the stacking-order optical-path differences
  don't show up.

For the reshoot plan this means **both stacking orders should be
retained** for any lens that uses stacked diopters.

---

## 7. Orientation analysis (norm vs reversed)

Only the Nikon AF 70-180 has both `norm` and bare-name variants in
the dataset, where "norm" is the factory orientation (hollow side
toward camera) and the bare variant is reversed (bulbous side toward
camera).

Aggregate effect across all four 70-180 close-up variants and four
apertures:
- **Reversed gets +1-3 % center sharpness** vs norm.
- **Corner sharpness is comparable** (within 1-3 %).
- **`corner / center` ratio is slightly worse for reversed** when
  diopters are stacked — by 1-7 % on the 6T+5T variant, up to ~15 %
  on the 5T+6T variant (one F8 outlier likely contaminated by
  partial-reshoot data).

Conclusion: the effect exists but is small and inconsistent. For
single diopters (no stacking) the reversed orientation has a slight
center-sharpness edge. For stacked diopters, normal orientation has
a slight corner-balance edge. **Neither effect is strong enough to
warrant testing both orientations for every lens** — keep one
orientation per lens config (the 70-180 reshoot list has the
no-norm + 5T+6T entry, which has 4 truncated apertures vs 1 for
the norm variant; the no-norm version is the one needing more
data anyway).

---

## 8. How findings flow into the planner

Summary of what each section of this document contributes to
`run-lens-test/sharpness/planner.py`:

| Constant or rule | Source section |
|---|---|
| `DEFAULT_COC_MM = 0.030` | §3 (back-derived from historical FWHM ratios) |
| `POSITIONS_ACROSS_FWHM_DEFAULT = 5` | §3 (k=8 sub-samples sufficient at moderate mag) |
| `POSITIONS_ACROSS_FWHM_HIGH_MAG = 8` | §3 (k=15 needed for 200mm 2:1) |
| `HIGH_MAG_THRESHOLD = 1.5` | §4 (1:1-1.6:1 is the sweet spot; >1.6:1 needs more density) |
| `MIN_RAIL_STEP_MM = 0.005` | StackShot mechanical resolution (~2-5 µm) |
| Aperture subsample factors | §3 + §5.3 (broader bells at small N tolerate sparser analysis) |
| No low-mag / small-N bumps | §3 (broad bells are MORE tolerant, not less) |

Findings that do NOT (yet) flow into the planner:
- **Lens-specific stacking-order preference** (§6) — would require
  per-lens tuning beyond what `(M, N)` alone can capture.
- **Sigma-150-with-close-ups truncation cluster** (§5.2) — the planner
  recommends a step, but the user still chooses the rail range; the
  truncation issue is a range-selection problem, not a step problem.
- **24-120 zoom oversampling at >1.6:1** (§5.1) — same: the bell is
  inherently broad on a non-macro lens at simulated high mag.
