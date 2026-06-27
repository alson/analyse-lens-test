# `mtf50_known_edge` — §5.1 CV-discovered edge MTF50

Follow-up to the auto-detect `mtf50_slanted_edge` algorithm noted as
the §5.1 priority in [`LONGDIST_HANDOVER.md`](LONGDIST_HANDOVER.md).
That algorithm picks the dominant in-tile gradient direction at
measurement time and fails to fire on 60–70 % of real wide-angle
tiles (the consensus tile lands on grass/asphalt regions where the
single dominant axis is too noisy or too short for ISO-12233 ESF
binning).

The new path: discover the long structural edges *once* per
(lens, FL) via Canny + probabilistic Hough on a sharp F8 reference,
then measure MTF50 on every replicate at the *known* edge positions
and orientations. No per-frame angle estimation; edges that get
occluded (cyclist, pedestrian) are detected via a refinement-stage
gradient-peak threshold and reported as NaN.

## Algorithm

1. Pick a sharp reference frame per (lens, FL) — prefer F8, fall back
   to F5.6 / F11 / F4 in order; within the chosen aperture take the
   largest-file replicate.
2. **Canny + Hough** on the reference; filter segments to
   `length ≥ 400 px` and orientation ≥ 1° off perfectly axis-aligned.
3. **NMS** in (ρ, θ) space (100 px / 5° tolerances) to collapse the
   many parallel sub-edges along the same physical boundary.
4. **Score** each surviving segment by
   `gradient_strength × two-sided_contrast × √length`, sort
   descending.
5. **Reference MTF50 floor**: drop any candidate whose measured
   MTF50 on the reference frame falls below 0.20 cy/px (effectively a
   "is this a true step edge" test — non-step textured regions don't
   pass).
6. **Spatial diversity**: bin frame into 4 × 3 cells; keep at most 2
   candidates per cell; take top-K = 12 overall.
7. Save edge specs as JSON; render an overlay PNG (with the ROI box
   drawn at the saved orientation).

## Per-frame MTF50 measurement

For each test frame (any aperture, any replicate of the same lens/FL):

1. Local refinement: search ±5 px perpendicular to the spec'd edge
   for the gradient-energy peak; sub-pixel-fit. Reject the
   measurement if the peak is below 40 % of the reference peak
   strength (the edge is occluded).
2. Extract an axis-aligned bounding box containing the oriented edge.
3. Project pixel coords onto the **known** gradient-normal direction
   (no auto-detect); bin into 0.25-px bins to recover an oversampled
   ESF.
4. Smooth ESF, derive LSF, Hann-window, FFT, find MTF50 by linear
   interpolation between the bracketing bins. Cap at Nyquist (0.5
   cy/px). Floor at 0.10 cy/px → NaN below (FFT-bin-noise artefact).

## Results

Cross-dataset comparison against the existing auto-detect
`mtf50_slanted_edge`. Auto-detect "range_pct" ≈ 2×CV for n=3
replicates, so the auto column is comparable to ~2× the known-edge
CV-median column.

| Dataset | KE NaN | Auto NaN | KE CV (med) | Auto range_pct | KE vs radial ρ | Auto vs radial ρ |
|---|---|---|---|---|---|---|
| wide2026_01_24 (Z7) | 14.5 % | 61.3 % | 10.8 % | 131 % | 0.52 | −0.01 |
| wide2026_01_26 (Z7) | 10.7 % | 71.5 % | 5.4 %  | 168 % | 0.51 | 0.29 |
| wide2026_02_07 (Z7) | 9.4 %  | 47.7 % | 11.1 % | 73 %  | 0.43 | −0.12 |
| wide2025_09_10 (D7200) | 9.6 % | 48.1 % | 10.2 % | 75 % | 0.37 | 0.09 |
| mid2025_09_11 (D7200) | 19.2 % | 38.1 % | 14.3 % | 121 % | 0.34 | 0.07 |

Three things to read off this table:

1. **NaN rate**: from 38–71 % to 9–19 %. Hits the §5.1 target of
   "≈20 %" across all five datasets — the auto-detect's fundamental
   failure mode (gradient direction undetectable in real
   consensus tiles) is gone because the direction now comes from a
   high-confidence Hough segment on the sharp reference.
2. **Replicate stability**: median CV in single digits (5–14 %) vs
   the auto-detect range_pct of 73–168 % (≈ 35–85 % CV-equivalent).
   The local refinement + reference-peak threshold strips the
   outliers that were inflating cross-replicate spread.
3. **Ranking agreement with `radial_cutoff`**: Spearman ρ 0.34–0.52
   across datasets, all positive. The auto-detect ranged from −0.12
   to 0.29 — essentially uncorrelated. The new metric reproduces the
   workhorse metric's per-aperture-per-lens ordering, so it's a
   meaningful cross-check rather than independent noise.

The remaining 9–19 % NaN are mostly genuine occlusions (cyclists /
pedestrians crossing a long pavement boundary in some replicates)
and the high-aperture wide-open shots where edge contrast in the
ROI doesn't pass the 40 % reference-peak threshold.

## D7200 caveat

The wide2025_09_10 and mid2025_09_11 datasets are D7200 with no
OLPF-less Z7 advantage. Absolute cy/sensor-px values aren't directly
comparable to Z7 numbers; the ranking-agreement metric is the only
cross-camera-meaningful column.

## Known limitations

- **FFT-bin quantisation at Nyquist**: many edges saturate the
  algorithm at the ~0.49 cy/px Nyquist cap on sharp Z7 / F8 frames.
  Cross-aperture discrimination is preserved for edges where the
  lens degradation actually drops MTF below 0.4. For the very best
  edges (high-contrast, near-perfect step) the cap is reached at all
  apertures.
- **Per-(lens, FL) reference**: different lenses at different FLs
  use different edge sets. Cross-(lens, FL) MTF50 comparison is not
  apples-to-apples in the way `radial_cutoff` is.
- **Telephoto / 3D-shrubbery scenes** still don't have usable step
  edges. The new algorithm is for wide-angle / mid stairs-scene
  datasets only.

## Files

- `scripts/poc_known_edge_mtf50.py` — discovery + dataset modes.
- `scripts/poc_known_edge_mtf50_compare.py` — comparison summary
  against `mtf50_slanted_edge` baseline.
- `scripts/poc_known_edge_mtf50_out/<dataset>/<lens-fl>/` — per
  (lens, FL) reference overlay JPEG + edges JSON.
- `scripts/poc_known_edge_mtf50_out/<dataset>/per_measurement.csv` —
  per (lens, FL, aperture, replicate, edge) MTF50 measurements.
- `scripts/poc_known_edge_mtf50_out/comparison_summary.md` — vs
  baseline.
