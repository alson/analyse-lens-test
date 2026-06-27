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

## Additional metrics (2026-06)

The algorithm now reports three complementary numbers per
measurement, all in cy / original-image-pixel:

- **`mtf50`** — the headline frequency at MTF = 0.5. Capped at sensor
  Nyquist (0.5 cy/sensor-px) so a sharp edge can saturate at ~0.49.
- **`mtf_at_nyquist`** — the actual MTF *value* at exactly
  0.5 cy/sensor-px. Stays in [0, 1] for valid edges and remains
  differentiating in the regime where MTF50 saturates. A typical
  Z7 wide-angle sharp edge reads 0.4 – 0.6; a soft edge reads 0.1 – 0.2.
- **`mtf10_freq`** — frequency where MTF drops to 0.1, capped at
  Nyquist. For very sharp edges this caps at 0.49 too — those edges
  retain > 10 % MTF all the way to Nyquist.

Why three? Sensor-Nyquist is a hard ceiling for unambiguous MTF
readings (the Z7 has no OLPF so above-Nyquist content aliases back
in-band; we cap there rather than mix aliased content into the
metric). Within [0, Nyquist], MTF50 is the canonical sharpness
threshold but it saturates for the best edges. MTF@Nyquist breaks
the saturation; MTF10 captures the tail when MTF50 doesn't reach
the Nyquist cap.

ESF contrast-normalisation (rather than `mtf[0]` from Hann-windowed
LSF) keeps mtf[0] ≈ 1 by construction, so the three metrics share a
coherent normalisation.

## Known limitations

- **Per-(lens, FL) reference**: different lenses at different FLs
  use different edge sets. Cross-(lens, FL) MTF50 comparison is not
  apples-to-apples in the way `radial_cutoff` is.
- **Telephoto / 3D-shrubbery scenes** still don't have usable step
  edges across the entire dataset. The new algorithm is for
  wide-angle / mid stairs-scene datasets by default. See
  "Extending to telephoto" below for scene-by-scene options.
- **Above sensor Nyquist** the slanted-edge oversampling produces
  spectrum values but they mix real lens MTF with aliased content
  (Z7 has no OLPF). The algorithm caps reads at 0.5 cy/sensor-px
  deliberately.

## Extending to telephoto / mid datasets — proposals

The current algorithm requires ≥ 400-px long Hough segments on a
sharp reference, which is plentiful on the wide-angle stairs scene
but sparse on the existing telephoto frames (mostly 3D shrubbery
where the dominant gradients are short twig branches). Three
practical paths, ordered by complexity:

### A. Try the existing algorithm at relaxed length, per-dataset

Lowest-effort first cut. Drop `HOUGH_MIN_LINE_PX` from 400 to ~150
and re-run on each telephoto dataset. If the algorithm finds usable
edges at the lower length and the resulting MTF50 values pass the
reference-MTF floor (≥ 0.20), the dataset is implicitly viable.

Likely viable candidates by visual inspection of one sharp F8 frame:

- **2025-07-09 (D7200)** — the **galvanised sign post** in the scene
  has two long vertical edges (left/right of the pole) of order
  150–300 px. With min-length lowered, Hough should pick these.
  The pole-vs-grass contrast is high and the edge is a true step.
  This is the highest-confidence telephoto candidate.
- **2026-01-28 / 30 (Z7)** — the 300 PF and Z 100-400 family shots
  at 31.62 m / 84 m include a **distant building skyline / chimney
  silhouettes** plus the **horizon-line where the shrubbery meets
  sky**. Lengths are scene-dependent; worth checking with a single
  `discover` run.

Workflow: run `poc_known_edge_mtf50.py discover --reference <sharp_F8>`
with the lowered minimum, view the overlay, and decide per scene.

### B. Sky / hedge boundary as a "soft" structural edge

For shrubbery shots the only inherently long boundary is the
**sky/hedge horizon** — irregular (twigs poking up) but mostly
monotonic. Two ways to extract it:

1. **Brightness-threshold segmentation**: binarise on the sky
   brightness, take the bottom row of the sky region per column,
   smooth with a median filter. The resulting curve is the
   sky/hedge boundary. Sample MTF perpendicular to its local
   tangent in 20–40 short ROIs along the curve.
2. **Hough on the smoothed boundary**: extract the contour as a
   1-D y(x) signal, look for the longest near-horizontal stretch
   where curvature is low, and treat that stretch as a single
   "slanted" edge for ISO-12233-style MTF.

This is the most general approach but takes real engineering
(segmentation tuning, boundary smoothing, MTF on a curved-rather-
than-straight edge). The boundary is also where lens *centre*
isn't always — the metric becomes a "boundary MTF" which may
emphasise different field positions than the wide-angle MTF50.

### C. Hand-pick edge coordinates per dataset

Lowest-tech path: open one sharp F8 reference per dataset in any
image viewer, note the (x, y, angle, length) of 2–6 well-chosen
edges, dump those as JSON into the per-(lens, FL) edges.json the
algorithm normally generates. The measurement step works unchanged
because it's just reading `EdgeSpec` records.

Pros: zero algorithm risk; you pick edges the algorithm already
knows how to measure.
Cons: manual labour per dataset (~5 minutes per scene class), and
the choice is no longer reproducible from code.

For the existing datasets this would be:

- 2025-07-09 sign-post: 2–3 pole edges
- 2026-01-28 / 30 hedge: sky/hedge horizon + any visible
  distant building or roofline
- 2026-02-07 telephoto: shrubbery only — skip; the dataset is
  genuinely edgeless and the bell-curve / radial_cutoff path
  remains the right metric there.

A small CLI to load a `edges.json` you hand-curate and run the
measurement step against the dataset's other apertures /
replicates would be ~30 lines on top of the existing code.

### D. Different metric for true shrubbery

When no usable structural edges exist, fall back to the existing
`radial_cutoff` (§5.3 metric) for ranking. The current per-config
sharpness CSV under `poc_longdist_algorithms_out/tele*/` is already
the right artefact for those datasets — no need to force a
slanted-edge metric onto a scene that doesn't have edges.

### Recommendation

Start with (A) on 2025-07-09 (sign-post) — if it works, that's the
test case for the relaxed-length variant. Then (C) for any specific
telephoto cross-date the user wants quantified. (B) is a research
project rather than a quick fix.

## 2026-06 — Z 20/1.8 ordering on wide2026_02_07 restored

The 2026-02-07/20 mm dataset was an open question (handover §5.4):
the user's visual finding "Z 20/1.8 best at corner" was contradicted
by the §5.2 consensus-tile picker which landed on grass-dominated
centre tiles.

Under §5.1 CV-discovered edges (which land on stair-side diagonals
and paver boundaries regardless of the consensus tile picker's
centre choice), the ranking restores to:

| Lens (best aperture) | mtf50_known_edge |
|---|---|
| **NIKKOR Z 20/1.8 S @ f/5.6** | **0.476** |
| NIKKOR Z 14-24/2.8 S @ 20 mm f/8 | 0.427 |
| Nikon AF Nikkor 20/2.8 @ f/8 | 0.407 |
| Viltrox AF 20/2.8 Z Air @ f/11 | 0.379 |

Z 20/1.8 S leads by 12 % over the Z 14-24 at the same focal length,
matching the user's visual judgement. Closes handover §5.4.

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
