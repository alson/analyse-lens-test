# 100-400 + TCs vs crop+upsample — 2026-01-28 shrubbery

Distant 3D shrubbery at FocusDistance=84m. Per-config best replicate; the
highest-gradient 256x256 tile in the central 1500x1500 of each frame is used
as the 'sharpest patch the lens delivered'. Radial power spectrum on that
tile, normalised by the mean power in the [0.01, 0.20] cy/mm-subject band
(scene-dominated, lens MTF ~1 there). Reported cutoff is the lowest subject-
frequency where the normalised spectrum drops below 0.05.

Higher cutoff (cy/mm-subject) = lens delivers more useful real-world detail.

## Subject-space cutoff (the answer)

| Config | f_eff | F# | repl | cutoff (cy/mm subject) | diffraction limit (cy/mm subj) | best_jpeg |
|---|---|---|---|---|---|---|
| bare_400_F8 | 400mm | F8 | 3 | **0.20** | 1.08 | 0123|NIKKOR Z 100-400mm f_4.5-5.6 VR S|400.0 mm|F8|alm-20260128-161220-128.jpg |
| bare_400_F11 | 400mm | F11 | 3 | **0.20** | 0.79 | 0127|NIKKOR Z 100-400mm f_4.5-5.6 VR S|400.0 mm|F11|alm-20260128-161225-132.jpg |
| tc14_400_F8 | 560mm | F8 | 6 | **0.24** | 1.52 | 0147|NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x|400.0 mm|F8|alm-20260128-161444-152.jpg |
| tc14_400_F11 | 560mm | F11 | 6 | **0.25** | 1.10 | 0150|NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x|400.0 mm|F11|alm-20260128-161449-155.jpg |
| tc20_400_F11 | 800mm | F11 | 3 | **0.29** | 1.57 | 0208|NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x|400.0 mm|F11|alm-20260128-161953-213.jpg |
| bare_200_F8 | 200mm | F8 | 3 | **0.20** | 0.54 | 0082|NIKKOR Z 100-400mm f_4.5-5.6 VR S|200.0 mm|F8|alm-20260128-161028-087.jpg |
| bare_300_F8 | 300mm | F8 | 3 | **0.20** | 0.81 | 0098|NIKKOR Z 100-400mm f_4.5-5.6 VR S|300.0 mm|F8|alm-20260128-161114-103.jpg |
| bare_cropped_tc14_FOV_F11 | 400mm | F11 | 1 | **0.20** | 0.79 | 0127|NIKKOR Z 100-400mm f_4.5-5.6 VR S|400.0 mm|F11|alm-20260128-161225-132.jpg |
| bare_cropped_tc20_FOV_F11 | 400mm | F11 | 1 | **0.20** | 0.79 | 0127|NIKKOR Z 100-400mm f_4.5-5.6 VR S|400.0 mm|F11|alm-20260128-161225-132.jpg |
| bare_cropped_tc14_FOV_F8 | 400mm | F8 | 1 | **0.20** | 1.08 | 0123|NIKKOR Z 100-400mm f_4.5-5.6 VR S|400.0 mm|F8|alm-20260128-161220-128.jpg |

## Interpretation

- At F11: TC14 gives **1.22x** the bare-frame subject-space cutoff; TC20 gives **1.45x**. Ideal magnification gain would be 1.4x and 2.0x — the gap (~0.18 for TC14, ~0.55 for TC20) is the TC's optical degradation.
- Cropping the bare 400mm frame and upsampling to TC framing **cannot** exceed the bare-frame cutoff (information theory: crop preserves what was there; upsampling adds nothing). So the bare-cropped-and-upsampled ceiling is **0.20 cy/mm-subject** (same as bare full frame). Both TCs beat that ceiling here.
- At F8 (only bare and TC14 available; TC20 wide-open is f/10): TC14 gives **1.19x** the bare cutoff.

## Caveats

- Each config's 'best tile' is chosen independently (highest gradient energy in
  central 1500x1500). The tiles cover different physical scene patches because
  the TC sees a smaller subject area. The normalisation by the low-subject-
  frequency band controls for scene-amplitude differences, but a residual bias
  remains if scene texture statistics differ across the picked tiles.
- Per-config best replicate is by gradient energy; AF or focus jitter between
  the 3-6 replicates is therefore absorbed into the comparison (we're comparing
  the best-focused frame each config achieved in this short shooting session).
- Long-tele atmospheric turbulence + VR/handheld-equivalent settling: the user
  shot tripod-mounted at 1/several-hundred-second shutters, so this should be
  small but is not formally controlled.
- No NEFs are on disk for 2026-01-28 (the usual NEF-at-date-root pattern does
  not apply here); analysis is on the in-camera JPEGs. Camera JPEG processing
  is identical across the three configs since they were shot in the same
  7-minute window with the same body settings — so within-this-day relative
  comparisons are valid even if absolute numbers differ from a NEF-based
  pipeline.
- Cutoff threshold of 0.05 of the low-band reference is somewhat arbitrary;
  the ranking is stable across nearby threshold choices (0.03, 0.07).

## Related

- Diagnostic script: `poc_longdist_diag2.py` (variant that picks different per-
  replicate tiles and plots the raw spectra).
- Visual side-by-side: `visual_fov_matched.png`.
