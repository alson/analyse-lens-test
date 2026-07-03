# POC — native-resolution from-RAW PSD-to-Nyquist cross-camera bridge (Sigma 150)

Script: `poc_crosscam_sigma150_native.py`. Question: can a native-pixel (un-resampled) PSD
from the raw NEFs rescue the Sigma-150 Z7↔D7200 sensor+OLPF bridge that the atlas-resampled
prototype (`poc_crosscam_sigma150.py`, 97d9b30) could not — chiefly by reaching the near-Nyquist
band the atlas 700-samples/unit grid throws away (it caps at ~0.27 cy/px ≈ 54% of Nyquist)?

## VERDICT: cannot run — a DATA WALL, not a method failure.

**The Z7 Sigma 150 was saved JPG-only in every session; there are no Z7 Sigma-150 raws to
decode.** Native-res-from-RAW needs NEFs on *both* cameras.

Raw (NEF) availability audit (Sigma 150):

| camera | session | Sigma-150 NEFs |
|---|---|---|
| Z7 | 2025-10-17 | 0 |
| Z7 | 2026-01-29 | 0 |
| Z7 | 2026-05-13 | 0 |
| D7200 | 2025-08-19 | 132 |

Broader: Z7 NEFs exist only in 2026-01-29 (~20k) and 2026-02-18 (~9k), and **not for the shared
macros** — Z7 **AF200 is also 0 NEFs** in all sessions. The Z7↔D7200 shared anchor lenses
(Sigma 150, AF200) have no Z7 raw at all. So native-res cross-camera is not runnable for the
clean anchor (Sigma 150) nor its obvious substitute (AF200).

**Z7-JPG vs D7200-RAW is not a valid fallback:** in-camera JPG processing (sharpening, tone
curve, 8-bit quantization, noise reduction) alters exactly the near-Nyquist band we are trying
to measure, and does so asymmetrically vs a linear raw — the ratio would conflate the OLPF
question with JPG-vs-raw processing. Uninterpretable.

**Unfixable:** the D7200 is sold (no re-shoot), and the Z7 Sigma-150 raws were never kept.

## The method itself is sound where raws exist (D7200-side demonstration)

Decoding a best-focus D7200 Sigma-150 F8 frame from raw (dcraw `-4 -q 0` linear green),
registering `reg_auto` directly on the raw green (scale 1.80, fit RMSE 4.49 px), and taking a
central native-pixel radial PSD yields signal **to 0.49 cy/px — i.e. to the sensor Nyquist**,
where the atlas-resampled PSD stops at ~0.27. (Near 0.49 the PSD approaches the estimated noise
floor ~1.8e10, as expected — the band is *reachable*, then noise-limited.) So had the Z7 raws
existed, the native-res path could have been attempted; the blocker is purely missing input.

## Where this leaves the two routes to confirm the "sensor/OLPF-dominated" prior

- **Atlas-resampled ratio (97d9b30):** ran, but failed 4 checks — aperture-dependent,
  rises-with-freq, low-f cancellation scatter, and the OLPF region out of band (54% Nyquist cap).
- **Native-res from raw (this POC):** would reach the OLPF band, but **cannot run** — no Z7
  Sigma-150 (or AF200) raws.

Both routes are exhausted for the shared modern macros. **The optics argument that the
Z7↔D7200 modern-macro difference is sensor/OLPF-dominated (not lens) therefore stands as a
well-founded PRIOR that cannot be empirically confirmed with the data we have.**

## Caveats (had it run)
First-order only; ~6% Sigma-150 M-offset (Z7 ~1.03 vs D7200 ~1.09) is modelable but unremovable;
bilinear-green decode mildly attenuates the top ~10–20% of the band; one lens. None of these
mattered in the end — the raw data doesn't exist.
