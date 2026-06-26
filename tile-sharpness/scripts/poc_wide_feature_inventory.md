# POC C: wider-feature inventory at low M — verdict

**Date:** 2026-05-17.
**Sweep:** `older-2026-01-29/2026-01-29__NIKKOR_Z_100-400mm_f_4.5-5.6_VR_S__1_2.60__F11`
at shot_idx 137 (peak-MTF50 shot per `out_task2/peaks_v2.csv`).
**M:** 0.385 (claimed). Z7 sensor; scribe FWHM at this M ~ 7-8 px.
**Tiles surveyed:** 7 (centre, 4 mid-edges, 2 corners of the on-target 4x4 region).

## Headline numbers

| Metric | Value |
|---|---|
| Tiles with at least one isolated wider feature (shot 137) | **4 / 7 = 57 %** |
| Tiles with any wider candidate (incl. non-isolated) | 6 / 7 = 86 % |
| Width distribution across 9 features (px) | min 22 / median 49 / max 167 |
| Width distribution across the 4 isolated features (px) | 44, 47, 94, 167 |
| Length distribution across 9 features (px) | min 220 / median 360 / max 1055 |
| Run-to-run determinism on the same input | NO — `cv2.LSD` segment-ordering causes tile (-2,-1) to flip between scribe-detected (0 candidates) and no-scribe (3 candidates). |
| Centre-tile shot-to-shot stability (3 shots; same scene) | 167-px feature in 1 of 3 shots; 44-px feature in 2 of 3; common feature found across all 3: 0 |

## Per-tile findings (shot 137)

```
tile     scribe  scribe_ang  N_wide  N_iso  features
(0,0)       y      94.88       2      1    dark w=44 L=498 iso ; dark w=26 L=342 nonI
(0,-1)      y      94.80       0      0    -
(0,1)       y       4.85       2      1    dark w=167 L=809 iso ; bright w=51 L=1055 nonI
(-1,0)      y       4.88       1      1    dark w=94  L=592 iso
(1,0)       y       4.77       1      1    dark w=48  L=278 iso
(-2,-1)     n/y    nan/5.33   3/0    0/0    bright w=22,54,40 nonI (when scribe-detect misses)
(2,1)       y       4.91       1      0    dark w=59  L=360 nonI
```

(-2,-1) is shown with two outcomes because run-to-run LSD ordering flips
whether the scribe is found at all; both outcomes still yield zero
isolated wider features.

Slant agreement with the scribe (or its perpendicular grid axis) is always
within +/-5 deg, so once an isolated dark band is found the orientation
constraint is not the limiting factor.

## Coverage assessment

- **Tile-content-dependent, not lens-dependent.** Centre + mid-edge tiles
  (which cover the central die area) yield 4 of 5 isolated features.
  Corner tiles (-2,-1) and (2,1) land near the wafer-die boundary; they
  either get a non-isolated feature or none. The on-target 4x4 region
  defined by `_legacy_filesize_and_labels` is mostly inside the central
  die, so most of the field-of-view tiles that the pipeline scores would
  have *some* candidate, but at-or-beyond the on-target boundary
  coverage drops fast.

- **Tile (0,-1) is the worst-case warning.** Scribe detected, scribe
  slant is fine, but the visible content is dense bond-pad blocks +
  text + small traces — no monolithic >= 200 px band aligned with the
  scribe. Eyeballing `/tmp/poc_wide_features_tile_0_-1.png` confirms
  there is no obvious wider feature this tile could fall back to. So at
  least one valid on-target tile produces zero coverage.

## Stability check (centre tile across 3 shots in the same sweep)

```
shot   N_wide  N_iso  widths_px
 125     2      2     167, 33
 137     2      1     44, 26
 141     1      1     32
```

The on-sensor structure is essentially identical across these 3 shots
(rail drift moves the subject by < 1 pixel at this M). Yet the detector
output is wildly different: a 167-px feature shows up at shot 125 but
not at 137 or 141. That is *not* specular noise — the threshold
percentiles (8th / 95th) drift by 2-3 grey-levels between shots and that
moves the connected-component boundary across the
length/width/aspect-ratio gate. **This is a hard reliability red flag.**
A production fallback would need fixed-percentile-of-die thresholds, or
a feature-anchor-track-across-shots step, before it could even be
characterised as repeatable.

## Verdict

**Marginal. Not recommended as a low-M MTF50 fallback in its current
form.** Three concrete reasons:

1. **Coverage gap on valid tiles.** With only 4/7 tiles producing an
   isolated wider feature, 43 % of on-target tiles would fall back to
   "no MTF50 reading" or to the same scribe-LSF that the proposal was
   meant to replace. That defeats the purpose of having a fallback —
   the centre subject MTF50 number for Task 2 is exactly the case where
   this needs to work, and the centre tile (0,0) does find a 44-px
   feature, but adjacent tiles in the same row do not (tile (0,-1)
   yields nothing).

2. **Shot-to-shot instability dominates over real content variation.**
   Same physical structure, three nearby shots, detector reports 2 / 2 / 1
   features with non-overlapping widths. Whichever shot the
   filesize-argmax happens to land on materially changes the result.
   The scribe-LSF path doesn't have this property because it FFTs a
   continuous profile rather than thresholding.

3. **Width distribution is mostly in the borderline range.** Of the 6
   features detected, only 2 are above 60 px width (94 and 167 px). The
   target was "20+ px so each edge is isolated from the other"; this
   *is* met by all 6 detections, but the cushion above the criterion
   is small for half of them. Half-decent specular highlights could
   easily knock the 26-44-48 px ones into a sub-criterion regime under
   slightly different lighting.

**If the user wants to pursue this anyway**, the implementation
prerequisites are: (a) replace percentile thresholds with absolute
intensity anchors taken from a one-time die-template alignment;
(b) track features across all shots in the sweep, not just at argmax,
and require persistence; (c) accept the 43 % no-reading rate as part of
the spec, with the LSF-saturation MTF50 still reported as a lower
bound; (d) decide whether the perpendicular edge of the same wider
feature (i.e. the OTHER side of a 167-px dark band) gets averaged in
or read as a separate measurement. Item (a) alone is a non-trivial
work item — die orientation/offset varies per sweep.

A cleaner path forward is probably one of:
- **Slanted-edge sub-pixel** on the existing scribe with 4x super-
  sampling (the parallel POC the user mentioned). It only reaches
  20.5 lp/mm at M=0.385, but it's deterministic and works on every
  scribe-detected tile.
- **Forward-model fit**: parametrise the scribe shape (width, depth)
  and fit lens-PSF + scribe convolution to the trough cross-section;
  the PSF width is then read off the fit directly without needing a
  step-edge object.

## Files

- Script: `tile-sharpness/scripts/poc_wide_feature_inventory.py`
- Per-feature CSV: `tile-sharpness/scripts/poc_wide_feature_inventory.csv`
- PNGs (all 7 tiles + 3 centre-tile-by-shot): `/tmp/poc_wide_features_*.png`
  Most informative for eyeballing:
  - `/tmp/poc_wide_features_tile_0_1.png` — best case (167-px isolated dark band).
  - `/tmp/poc_wide_features_tile_0_0.png` — centre, finds 44-px dark trace.
  - `/tmp/poc_wide_features_tile_0_-1.png` — failure case, no wider feature.
  - `/tmp/poc_wide_features_centre_shot_125.png` vs `..._137.png` — shot-to-shot instability.
