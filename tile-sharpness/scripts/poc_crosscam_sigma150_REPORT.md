# POC: Sigma 150 cross-camera PSD ratio (Z7 vs D7200) — VERDICT: method does NOT cleanly carry

Date 2026-07-03. Script: `poc_crosscam_sigma150.py` (run on nufan, reuses existing
`out_relmtf_311` + `out_relmtf_d7200` PSD/meta shards; no re-extract).

## Goal
Measure the D7200 sensor+OLPF MTF penalty by ratioing the two cameras' per-patch PSD for
the SAME wafer patch, SAME lens (Sigma 150), SAME effective aperture, ~same M — so the optics
(lens×diffraction) and target spectrum cancel and `sqrt(PSD_D7200/PSD_Z7) ≈ sensor+OLPF ratio`.

## Result (D7200/Z7, exposure-normalised sensor-MTF-shape ratio)
| ap | shared patches | expo CV (low-f) | ratio@0.10 cy/px | ratio@0.20 cy/px | ratio@band-max(0.27) |
|----|----|----|----|----|----|
| F5.6 | 34 | 0.42 | 1.01 | 1.33 | 0.96 |
| F8   | 43 | 0.33 | 0.93 | 1.30 | 1.14 |
| F11  | 41 | 0.34 | 1.10 | 1.47 | 1.39 |
| F16  | 42 | 0.27 | 1.08 | 1.36 | 1.53 |

## Why it does NOT cleanly carry (4 structural failures, not just noise)
1. **Aperture dependence (fatal).** A sensor+OLPF ratio is a property of the camera and MUST be
   aperture-independent. Instead the band-max ratio swings 0.96 (F5.6) → 1.53 (F16). So the
   ratio is not isolating the sensor.
2. **Rises with frequency.** Ratio climbs to 1.3–1.5 by 0.20 cy/px — the OPPOSITE of an OLPF
   low-pass (which would pull D7200 *below* Z7 at high freq). Consistent with differing
   high-frequency NOISE FLOORS / residual LSF over-read dominating where the optical MTF has
   decayed (and it worsens stopping down, matching the over-read's known aperture behaviour).
3. **High patch-to-patch scatter** in the supposedly-constant low-frequency exposure factor
   (CV 0.27–0.42). The same atlas patch does not give a constant D/Z low-f ratio → optics+target
   are not cancelling cleanly (different FOV framing/sampling/illumination between the bodies).
4. **OLPF region is out of band.** The atlas-resampled grid (700 samples/atlas-unit) band-limits
   the PSD to ~0.27 cy/px = 54% of sensor Nyquist (0.5). The OLPF's strongest attenuation is
   near Nyquist — i.e. exactly where we have NO data.

## Caveats acknowledged up front
First-order only; the ~6% M-offset (Z7 M≈1.03 vs D7200 M≈1.09) is modeled-not-eliminated
(D7200 sold, no re-shoot); exposure normalised via the low-f ratio; one lens (Sigma 150);
OLPF orientation-dependent. Sigma 105 (M-offset ~15%) would be noisier, not a rescue.

## Verdict
**The final dataset does NOT support even a first-order cross-camera sensor+OLPF bridge via
this same-patch PSD ratio.** The one discriminating region (near Nyquist, where the OLPF acts)
is unmeasurable from the atlas-resampled PSD, and within the measurable band the ratio is
aperture-dependent and rises with frequency — dominated by noise-floor/over-read differences,
not the sensor MTF. The only benign read is that at the relmtf operating point (~0.10 cy/px)
the ratio is ≈1, i.e. no large *low-frequency* sensor discrepancy — but that neither isolates
the OLPF nor decomposes lens-vs-sensor.

## What would be needed (not doable with current data)
- **Native-resolution PSD to reach Nyquist**: bespoke extraction from the raw frames at full
  sensor sampling (not the 700/unit atlas grid) so the ratio spans 0→0.5 cy/px and actually
  covers the OLPF roll-off. That is a re-extraction from raw, out of this POC's scope.
- SNR-weighting / noise-floor subtraction to stop the high-f noise floor dominating.
- Matched-M acquisition (impossible — D7200 gone) to remove the residual diffraction/cy-px mismatch.

Net: the "sensor/OLPF-dominated" prior from optics stands as a **prior**; this data cannot
empirically confirm it. The physically-grounded optics argument remains the best available answer.
