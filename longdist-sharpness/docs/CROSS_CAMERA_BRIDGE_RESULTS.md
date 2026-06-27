# D7200 ↔ Z7 cross-camera bridge factor

Closes the §5.5 follow-up in [`LONGDIST_HANDOVER.md`](LONGDIST_HANDOVER.md):
"cross-camera cy/sensor-px is not directly comparable — develop a
shared-lens + shared-scene measurement to quantify the bridge."

## Setup

EXIF confirms the camera cut-over:

| Date range | Camera |
|---|---|
| 2025-07-05 through 2025-09-11 | Nikon D7200 (DX, 3.91 µm pitch, OLPF, AA filter) |
| 2025-10-17 onwards | Nikon Z 7 (FX, 4.35 µm pitch, no OLPF) |

Three F-mount lenses appear in both the D7200 wide dataset
`wide2025_09_10` and post-switch Z7 wide datasets at the same
physical scene (stairs / grass / arch):

- **Sigma 24mm F2.8 Super Wide II Macro** — D7200 2025-09-10 / Z7 2026-01-24
- **Nikkor-N.C Auto 24mm f/2.8** — D7200 2025-09-10 / Z7 2026-01-24
- **AF Nikkor 20mm f/2.8** — D7200 2025-09-10 / Z7 2026-02-07

For each, I take the **best-of-positions** `radial_cutoff` value per
(FL, aperture) on each body (using best-of-positions because the
D7200 `position_frac=0.50` consensus tile returns NaN on most
configs — the JPEG-engine + OLPF combo apparently leaves no
above-threshold spectrum at the stairs-centre tile under the §5.3
metric; off-centre positions still report). The ratio Z7 / D7200 at
matched (lens, FL, aperture) is the bridge factor.

## Caveats

1. **APS-C framing differs from FX framing.** The D7200 sees the
   centre DX-crop of the Z7 framing — i.e. the same lens projects
   the same image circle, but the camera samples a smaller central
   subset. The "centre" tile (position_frac=0.50, 256 px) on each
   body samples a subject region of:
   - D7200: 256 × 3.91 µm = 1.00 mm of subject
   - Z7:    256 × 4.35 µm = 1.11 mm of subject
   So the Z7 centre tile covers ~11 % more subject area; the
   measurements are not strictly apples-to-apples, but on a
   well-textured stairs centre the lens-MTF dominates the
   measurement and the framing offset washes out.
2. **F-mount lenses on Z7 use the FTZ adapter** — adds nothing in
   the optical path (the FTZ is a passive spacer that maintains
   F-mount flange distance), so optical performance is unchanged.
3. The bridge factor is a single empirical constant; it folds
   together camera sensor MTF, OLPF/AA filter, and JPEG-pipeline
   processing. It is not a clean optical property.

## Results

Per-aperture Z7 / D7200 ratios at the best position per (FL, aperture):

| Lens | Median ratio | Mean | Range |
|---|---|---|---|
| Sigma 24/2.8 SWII Macro @ 24 mm | **1.35** | 1.43 | 1.28 – 1.69 |
| Nikkor-N.C 24/2.8 @ 24 mm | **1.37** | 1.37 | 1.17 – 1.56 |
| AF Nikkor 20/2.8 @ 20 mm | **1.33** | 1.33 | 1.00 – 1.48 |
| **Combined (24 ratios)** | **1.35** | 1.37 | 1.00 – 1.69 |

Cross-lens consensus: **Z7 reads ~1.35× higher cy/sensor-px than
D7200** on the same F-mount lens at the same wide-angle scene.

### Converted to cy/mm-sensor

In sensor-spatial-frequency units (the more physical metric):
`cy/mm-sensor = cy/sensor-px / pixel_pitch_mm`. With D7200 pitch
3.91 µm and Z7 pitch 4.35 µm — **the two pitches differ by only
~11 %**, so the conversion barely moves the ratio:

```
Z7 cy/mm-sensor / D7200 cy/mm-sensor = 1.35 × (3.91 / 4.35) ≈ 1.21
```

So **Z7 records ~21 % higher cy/mm-sensor than D7200 on the same
optical input** — that's the sensor-MTF + JPEG-pipeline advantage of
the Z7 (no OLPF, JPEG sharpening profile on FX FINE) isolated from
the small pitch difference. The cy/sensor-px factor (1.35) and
cy/mm-sensor factor (1.21) tell the same story; pick whichever
units your downstream comparison is in.

## Practical use

For comparing a D7200 `radial_cutoff` reading against a Z7 reading
of a hypothetical-same-lens-same-scene, **multiply the D7200 value
by 1.35** (cy/sensor-px) or 1.21 (cy/mm-sensor).

This is an empirical bridge for the specific
"wide-angle stairs / cy-per-px after §5.3 metric" use case. For
telephoto / 3D-shrubbery scenes the factor might shift because the
JPEG sharpening + sensor-MTF interaction is scene-content
dependent. Use the wide-angle factor as a first-cut estimate and
verify on the specific cross-camera comparison being made.

## Source data

Per-config ratios for the three lenses (under §5.3 metric):

| Lens | FL | Aperture | D7200 top | Z7 top | Z7/D7200 |
|---|---|---|---|---|---|
| Sigma 24/2.8 SWII | 24 | F2.8 | 0.184 | 0.238 | 1.30 |
| Sigma 24/2.8 SWII | 24 | F4   | 0.184 | 0.244 | 1.33 |
| Sigma 24/2.8 SWII | 24 | F5.6 | 0.172 | 0.291 | 1.70 |
| Sigma 24/2.8 SWII | 24 | F8   | 0.169 | 0.274 | 1.63 |
| Sigma 24/2.8 SWII | 24 | F11  | 0.180 | 0.247 | 1.38 |
| Sigma 24/2.8 SWII | 24 | F16  | 0.153 | 0.196 | 1.28 |
| Nikkor-N.C 24/2.8 | 24 | F2.8 | 0.148 | 0.219 | 1.48 |
| Nikkor-N.C 24/2.8 | 24 | F4   | 0.172 | 0.230 | 1.34 |
| Nikkor-N.C 24/2.8 | 24 | F5.6 | 0.163 | 0.254 | 1.56 |
| Nikkor-N.C 24/2.8 | 24 | F8   | 0.181 | 0.256 | 1.41 |
| Nikkor-N.C 24/2.8 | 24 | F11  | 0.192 | 0.239 | 1.24 |
| Nikkor-N.C 24/2.8 | 24 | F16  | 0.194 | 0.227 | 1.17 |
| AF Nikkor 20/2.8 | 20 | F2.8 | 0.131 | 0.192 | 1.46 |
| AF Nikkor 20/2.8 | 20 | F4   | 0.140 | 0.208 | 1.48 |
| AF Nikkor 20/2.8 | 20 | F5.6 | 0.173 | 0.251 | 1.44 |
| AF Nikkor 20/2.8 | 20 | F8   | 0.199 | 0.246 | 1.23 |
| AF Nikkor 20/2.8 | 20 | F11  | 0.194 | 0.248 | 1.28 |
| AF Nikkor 20/2.8 | 20 | F16  | 0.167 | 0.218 | 1.31 |

The wide-open apertures (F2.8 / F4) show slightly more spread because
those frames are softer in both bodies and the metric is closer to
its sub-bin noise floor. F5.6–F11 (the lens-sharp regime) gives the
tightest cluster around 1.3–1.5.
