# Bellows-factor validation shoot — procedure

Date: 2026-05-17.
Camera: Nikon Z 7. Card: NIKON Z 7 SD (now wiped — files are off-card).

## Goal

Measure the actual light-loss EV (= "bellows factor") for every
extension-tube configuration used in the 2026-02-18 and 2026-05-13
lens-test trees, so that the F-dir names in those trees can be
renamed to reflect **effective** rather than reported f-number.

## Why the camera-reported f-number isn't enough

* Z-mount lenses have no electrical contact with the body that would
  tell them an extension tube has been mounted between lens and
  body. So the reported f-number in EXIF does **not** include any
  bellows contribution from the tube.
* Internal-focus macros (Z MC 105) report a bellows-corrected
  aperture from their own close focus (e.g. f/2.8 → f/4.5 at 1:1)
  because the lens *does* know about its own focus state. But the
  external-tube contribution is invisible to the camera.
* Non-macro zooms (Z 24-120, Z 100-400, Viltrox 85) report a static
  f-number independent of focus distance, then sometimes
  *partially* compensate internally so actual transmission matches
  the reported value, and sometimes don't.

We measure the actual bellows by comparing center brightness of a
uniformly-lit reference between a bare-lens shot and a
lens-plus-tube shot at the same exposure settings (fixed ISO,
fixed shutter, fixed reported aperture, fixed manual flash power).

## Equipment

* Tripod with the camera fixed throughout the validation block.
* Speedlight SB-5000 in **manual mode** (no TTL). Wide-angle
  diffuser deployed at 14mm setting. Light bounced off ceiling
  (white, fairly uniform).
* Diffuse cloud cover (first series, bare 24-120 only) — no flash.
  Pairs of paired infinity (focus ~17m on a distant cloud) and MFD
  (lens hard stop, ~0.35m) shots at each focal length.

## Settings

* All shots: ISO 64, raw + JPEG basic.
* Lens-by-lens aperture:
  - Z 24-120: f/4 (wide open at all focal lengths)
  - Z MC 105, Z 100-400, Viltrox 85: f/5.6
* Flash output (manual SB-5000 power level):
  - 1/16 for the 24-120 first pass at 120 mm (underexposed —
    abandoned partway as a data source, but the bare/tube sequence
    is visible)
  - 1/8 for the 24-120 second pass and the 24-120 70mm and 50mm
    blocks
  - 1/4 for the MC 105, 100-400, and Viltrox 85 blocks
* The brightness ratio between bare and tube within each block is
  insensitive to flash power as long as the power was held constant
  across the block (which it was).

## Lenses and tube combinations

User owns three discrete extension tubes: **10 mm, 16 mm, 35 mm**.
Stacked: 26 (= 10+16), 36 (= 10+26 — not used), 45 (= 10+35), 51
(= 16+35), 61 (= 10+16+35). The largest achievable extension is
61 mm.

Configurations tested:

| lens | focal lengths | tube lengths tested |
|---|---|---|
| Z 24-120 f/4 | 50, 70, 120 mm | bare; subset of 10/16/26/35/45/51/61 |
| Z MC 105 f/2.8 | 105 mm | bare; **all seven** stacks |
| Z 100-400 f/4.5-5.6 | 200, 400 mm | bare; 35, 61 |
| Viltrox AF 85 f/2 | 85 mm | bare; 26, 35, 45, 61 |

## Workflow per configuration

1. Mount lens (and tube if applicable).
2. Set zoom to the target focal length.
3. Lens auto-resets focus to infinity on tube swap (Z lens
   behaviour). Manually refocus to MFD (hard stop on the close-focus
   end).
4. Shoot 3 frames at MFD (the validation data points).
5. Optionally shoot at infinity (the bare references use this; for
   tube-mounted configs, infinity-focused shots aren't useful and
   were generally skipped).
6. Swap tube and repeat.

## Sequencing (and order within each block)

* 24-120 @ 120 mm: bare → max-tube (first pass at low flash power,
  underexposed at long tubes), then max-tube → bare again at higher
  flash power (second pass; this is the analysis pass).
* 24-120 @ 70 mm: bare → max-tube.
* 24-120 @ 50 mm: max-tube → bare.
* MC 105 @ 105 mm: bare → max-tube. The +35mm tube was shot twice
  (replicate within ~20 s, no tube change between).
* 100-400 @ both focal lengths: max → bare. The user switched
  between 200 mm and 400 mm at each tube setting, so the sequence
  is: (max @ 200) (max @ 400) (medium @ 400) (medium @ 200) (bare
  @ 200) (bare @ 400). The bare @ 400 mm MFD was missed in the first
  pass and reshot after the card was ejected and re-inserted.
* Viltrox @ 85 mm: bare → max-tube.

## Brightness measurement

For each JPG:

1. Open as RGB.
2. Take a centered N×N pixel crop (we record N = 100, 200, 400,
   800, 1600).
3. Decode sRGB gamma to linear-light intensity.
4. Compute Rec.709 luminance per pixel and average.
5. Store as `y_lin_center_<N>`.

For the bellows analysis we use the N = 400 px centre crop —
the smallest size that's still scene-uniform enough to be robust
(at 100 px, individual ceiling texture starts to dominate; at
800+ the corners catch frame-edge variation).

## Bellows-multiplier formula

```
multiplier = sqrt(Y_bare_MFD / Y_with_tube_MFD)
effective_f_number = reported_f × multiplier
EV loss = 2 × log2(multiplier)
```

Both sides of the ratio use the SAME flash power and SAME ISO/
shutter/aperture/focal-length (within block tolerances). Camera
JPG tone curve is the same for both (M-mode, no Active D-Lighting
adjustments visibly affecting clean ceiling/cloud crops), so the
ratio is preserved through the sRGB → linear decode.

## Limitations

* "Same camera + same flash bounce geometry" assumption — multipliers
  are calibration coefficients for this specific test rig.
* JPG-derived. NEFs were on the card and have been wiped; for any
  future re-measurement at higher precision (e.g. with rawpy), the
  scene-uniform reference target would need to be re-captured.
* The 24-120 first pass at 120 mm with FEC −5 / flash 1/16 has
  shadow-clipped frames in the dark end (Y < 0.06). The second pass
  has the same eight tube settings cleanly and is the analysis
  pass.
* Tube identities at each shot were assigned manually based on
  user-confirmed sequencing within each block (bare → max or max →
  bare) and the inter-frame time gaps (replicates: ≤ 20 s + Y
  unchanged; tube swaps: longer gap + clear Y step). The
  assignments live in `data/tube_assignments.csv` and are
  reproducible from `per_shot.csv` plus the order-of-shoot facts in
  this document.
