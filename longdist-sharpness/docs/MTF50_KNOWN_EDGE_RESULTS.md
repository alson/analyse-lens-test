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
4. Smooth ESF, derive LSF, **window with a Hann centred on the LSF
   centroid and renormalise by the DC bin** (the §5.6e over-read fix,
   2026-06-29 — see "MTF over-read fix" below), FFT, find MTF50 by
   linear interpolation between the bracketing bins. Cap at Nyquist
   (0.5 cy/px). Floor at 0.10 cy/px → NaN below (FFT-bin-noise
   artefact).

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

Normalisation (updated 2026-06-29): the LSF is built by ESF
contrast-normalisation, then windowed with a Hann centred on its
centroid and **renormalised so `mtf[0] = 1`** (the §5.6e fix). The
earlier code skipped the `mtf[0]` renormalisation and tapered only the
ROI ends — that is what let the asymmetric LSF tail over-read; see
below.

## MTF over-read fix (§5.6e, 2026-06-29)

The estimator used to over-read MTF50 at f/11–f/16 — above the
diffraction ceiling — and threw `mtf_at_nyquist` outliers even on
linear, demosaic-only RAW. Root cause: an **asymmetric LSF**. The old
end-of-ROI taper left the longer / noisier LSF tail intact, and that
asymmetry inflates the FFT high-frequency magnitude. (This is the
single-step-edge analogue of the macro scribe-trough wall asymmetry,
but the macro `lsf_mtf50(combine="min")` two-wall trick does not apply
to a single edge.)

Fix: window the LSF with a **Hann centred on its centroid** and
renormalise by the DC bin (`poc_known_edge_mtf50.LSF_PROFILE =
{"window": "centroid_hann"}`). Chosen by `scripts/poc_lsf_overread_fix.py`,
which compared windowing variants on (a) synthetic edges with analytic
ground-truth MTF and (b) 2026-06-28 brick RAW against the diffraction
ceiling (`tile-sharpness/optics.py`), using in-focus AF frames and a
per-edge **median across frames** (the old "best-focus = max over
frames" pick was itself inflating MTF@Nyq — the previously-reported
max ~2.4 was largely that artefact, not the metric).

Aggregate result vs the old end-taper, bare Z 100-400 @ 400 mm
(in-focus AF frames, per-edge median across frames):

| config | ceiling | metric | old (endtaper) | new (centroid_hann) |
|---|---|---|---|---|
| f/16 | 0.200 | median MTF50 | 0.225 (+12 %) | **0.194** (≈ceiling) |
| f/16 | 0.200 | over-ceiling frac | 68 % | **45 %** |
| f/11 | 0.290 | over-ceiling frac | 21 % | **11 %** |
| f/11 | 0.290 | MTF@Nyq p95 | 0.75 | **0.53** |
| f/11 | — | usable edges (lower NaN) | 248 | **763** |

**Read these honestly.** The headline win is **edge yield** (~3× more
edges measured) + a lower MTF@Nyq tail. The aggregate median drop is
**partly a population effect** — the ~500 extra (softer, lower-contrast)
edges centroid_hann measures pull the aggregate down. A *paired,
same-edge* comparison (`poc_lsf_overread_paired.py`) isolates the true
per-edge effect, which is **modest**: f/16 over-ceiling 70 % → 59 %,
ΔMTF50 −0.007; f/11 bare 20 % → 17 %, ΔMTF50 ≈ 0. And a **residual
over-read persists** on sharp diffraction-limited edges (59 % still over
the f/16 ceiling) — likely demosaic aliasing on the no-OLPF Z7, which
LSF windowing cannot remove. The earlier "max MTF@Nyq ~2.4" was largely
a *max-over-frames* picking artefact, not the metric. So the
diffraction-ceiling clamp and the "median across in-focus frames, never
max" rule still apply.

centroid_hann also beat fixed-width Tukey windows (clip the lobe when
narrow), `mirror` (no gain on single edges), and a derivative/sinc
correction (negligible) — and is the simplest. Full variant table:
`scripts/poc_lsf_overread_fix_out/summary.md`; paired check:
`scripts/poc_lsf_overread_fix_out/paired.md`.

**Cached results predate this fix.** The §Results / §2026-06 Z 20/1.8
numbers below were computed under the old metric; rankings are expected
to hold but absolute MTF50 shifts down ~5–12 % and the 0.49-Nyquist
saturation eases. Re-run owed — see LONGDIST_HANDOVER §5.6f.

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

## Extending to telephoto / mid datasets — 2026-06 update

After the 2026-06 follow-up session, the §5.6a "extend to
telephoto" item splits cleanly by **what the user actually
focused on** in each dataset. The slanted-edge approach only
applies where there are long structural edges *at the focus
plane*. Most tele scenes don't qualify; one does.

### Per-dataset disposition

- **2025-07-09 (D7200, `tele2025_07_09`) — VIABLE for path (A),
  but only for the D7200 F-mount telephoto lenses on this date**
  (300/4D + TCs, 70-200 + TCs, Sigma DC zooms at infinity-class
  distance). User focused on the **galvanised pole** itself.
  The pole has two long vertical step edges against the grass
  background and a horizontal bracket near mid-pole. Pole-vs-
  grass contrast is high. Run with `HOUGH_MIN_LINE_PX ≈ 150` and
  the algorithm should find these. The macro lens variants on
  this date (Sigma 150 macro, Tamron 90 macro at close-distance)
  used a different methodology and are not pole-focus — their
  results from path (A) would measure whatever was at their
  individual focus plane, not the pole.
- **2025-09-06 (D7200, `tele2025_09_06`) — BLOCKED.** Focus is on
  the shrubbery embankment, not the road sign. Spot-check at
  bare 300 mm f/4D F8: sign's plate edges are clearly soft;
  shrubbery leaves are crisp. The sign also drifts in and out of
  frame across lens configurations. Use `radial_cutoff`.
- **2026-01-28 / 30 (Z7, hedge) — BLOCKED.** Focus is mid-volume
  in the hedge, between closest twigs and the far horizon. No
  long structural edges exist at that depth. The sky/hedge
  horizon and any distant building silhouettes are at infinity
  — out of focus.
- **2026-02-07 telephoto (Z7) — BLOCKED.** Pure winter shrubbery,
  same methodology as 01-28 / 30.
- **2025-07-05 (D7200, NEF-only) — BLOCKED.** Heath/grass at the
  same scene location as 09-06 (user confirmed), but with no
  man-made objects in frame. Stochastic vegetation only.

### Short-FL coverage

The user notes that one early 70-200 (or similar long-zoom) test
*was* shot at the stairs scene, but it isn't in this directory
tree as a self-contained dataset. All short-FL (≤ 56 mm) data on
the stairs scene is already captured by:

- `mid2025_09_11` (FLs 24, 27, 28, 35, 50, 55, 56 mm) — done by
  §5.1 known-edge.
- The five wide-angle datasets (`wide*`) — done by §5.1
  known-edge.

So the genuine ≤ 100 mm "stairs + man-made objects" zone is
already covered. Everything above ~100 mm in subsequent sessions
has been shrubbery-focus; no slanted-edge coverage is reachable
there.

### What this means for future sessions

- For new telephoto data on shrubbery / heath / hedge:
  `radial_cutoff` (§5.3) is the right metric.
- For new telephoto data **at the stairs scene** (if the user
  ever reshoots), `mtf50_known_edge` could apply — but the per-
  (lens, FL) reference picker is currently tuned for wide-FL
  framings of that scene, and may need a refresh.
- **Path (B) sky/hedge segmentation is permanently shelved.**
  The sky/hedge horizon is at infinity-class distance; the user
  focuses mid-volume. Any future session that revisits this
  should re-read this section before re-proposing it.

### Historical: pre-2026-06 proposals A/B/C

Kept for reference. Path (A) survives, scoped to 2025-07-09;
(B) and (C) are rejected on the same focus-depth grounds as
above.

- **(A) Relaxed `HOUGH_MIN_LINE_PX` ≈ 150** — adopted for
  `tele2025_07_09` (pole focus). Not viable on any other tele
  dataset because the long edges in those scenes are at the
  wrong depth.
- **(B) Sky/hedge boundary segmentation** — rejected. The
  sky/hedge horizon is at infinity-class; user focused
  mid-volume. Measuring at the horizon would report defocused
  MTF, not the lens's behaviour at the user's actual focus
  distance.
- **(C) Hand-pick edges per dataset** — only helpful where path
  (A) is also viable (i.e. where there are structural edges at
  the focus plane). For 2025-07-09 it's redundant with (A); for
  the shrubbery-focus datasets it can't fix the depth mismatch.
- **(D) Stay with `radial_cutoff`** — adopted for everything
  except `tele2025_07_09`.

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
