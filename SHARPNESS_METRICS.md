# Cross-Lens Sharpness Metrics — Alternatives to JPEG File Size

> This document covers the **macro / silicon-wafer** test rig (StackShot
> rail, periodic bond-pad target, fixed planar subject). For the
> **long-distance natural-target** rig (sloped stair scene at 14-50mm,
> distant hedge at 300mm) see [`SHARPNESS_METRICS_LONGDIST.md`](SHARPNESS_METRICS_LONGDIST.md).

The current pipeline (`select-crops.sh`, `make-9-crops.sh`) uses JPEG file
size as a sharpness proxy via `ls -S | head -n1`. This works *within* a
replicate set because the framing is fixed and entropy-coded JPEG length
scales with the amount of detail captured. It does **not** generalise
across lenses, because:

- Different lenses / focal lengths frame different parts of the wafer.
- JPEG length is driven by the entropy of the scene content, not by lens
  resolution alone — a coarser piece of wafer with high local contrast
  can produce a larger file than a finer piece resolved with the same
  acuity.

Below are alternatives that handle the "different framing on the same
wafer" case, roughly ordered by robustness for this particular dataset.

The wafer crops contain two features that make scene-invariant sharpness
measurement unusually tractable here:

- Long, straight die-boundary edges (slanted-edge MTF input).
- Regular periodic arrays of bond pads / bumps (built-in sinusoidal MTF
  target).

---

## 1. Slanted-edge MTF (ISO 12233) via MTF Mapper *(recommended first try)*

The gold standard, and the most scene-invariant option. MTF Mapper
auto-detects straight edges in arbitrary photos and reports per-edge
MTF50 in cycles/pixel; the die boundaries visible in many crops are
ideal targets. Cross-lens comparison reduces to "compare MTF50".

- Binary already built locally: `MTF mapper/workspace/mtfmapper/bin/mtf_mapper`.
- AUR alternative: `mtfmapper-git`.
- Caveats:
  - Needs an edge slanted ~5-10°; perfectly axis-aligned edges fail
    the oversampling step.
  - JPEG-compressed input under-reports the absolute MTF tail.
    Rankings between lenses remain consistent if JPEG settings match.
  - For absolute MTF50 numbers (e.g. comparable to a published lens
    chart), feed RAW-extracted TIFFs instead.

## 2. Radial power-spectrum cutoff with a parametric fit

Compute the 2D FFT of each crop, radially average to obtain P(f), then
fit a model that separates scene statistics from the lens response:

    P(f) = A · f^(-α) · |MTF(f)|² + N₀

where `α` is the natural-image spectral slope (scene-dependent) and
`MTF(f)` is a 1- or 2-parameter shape (Gaussian, or
`sinc(f·b)·exp(-(f·c)²)` for diffraction + defocus). Extract the MTF
cutoff frequency or MTF50 from the fitted curve.

This explicitly *separates* the scene's 1/f spectrum from the lens
response — the central problem with cross-framing comparison. Strictly
better than naive "high-band energy" because it doesn't conflate scene
complexity with sharpness.

Tooling: NumPy + SciPy (`scipy.optimize.curve_fit`) is sufficient. No
extra system packages.

## 3. Harmonic analysis of the bump grid *(exploits the specific target)*

The wafer's regular array of bond pads is, in effect, a built-in
sinusoidal MTF target.

Procedure:
1. Locate the two dominant peaks in the 2D FFT (the grid fundamentals
   in x and y).
2. Measure the amplitudes of the 2nd, 3rd, 4th… harmonics.
3. The decay `A_n / A_1` is a direct sample of the lens MTF at known
   spatial frequencies `n · f_fundamental`.

Literature backs the harmonic method as more accurate at high
frequencies than variance-based methods when noise is correlated
(periodic-bar-phantom comparisons in CT imaging).

Only applies to crops where the grid is visible (centre / pad-array
regions, not die-boundary or bond-wire regions). For those, it is
almost free of scene-content bias because the grid period is known.

## 4. Edge-profile decay rate *(no-reference, content-independent)*

Recent literature on no-reference sharpness assessment converges on
metrics that measure the *normalised* gradient decay along detected
edges, designed to be robust against brightness, contrast, exposure,
and image content. Notable variants:

- Normalised gradient-decay (Akamine et al., 2024 — satellite imagery).
- Marziliano edge-width.
- Local kurtosis of DCT coefficients in 8×8 blocks centred on detected
  edge pixels.

These average over many detected edges, so they don't depend on
finding one good slanted edge — useful for crops with no long straight
die boundary in view.

## 5. Imatest-style acutance / SQF

Integrate MTF (from any of §1-§3) against the human contrast-sensitivity
function to get a single perceived-sharpness number per crop. Useful
when you want a scalar ranking rather than full MTF curves.

---

## Lower-priority options

### 6. Wavelet / DCT band-energy ratio

High-band wavelet energy normalised by low-band wavelet energy. Strictly
better than raw JPEG file size as it removes the dependency on absolute
content density at low frequencies. Still scene-dependent at the margin.

### 7. Variance of Laplacian, Tenengrad, Brenner

Classic autofocus metrics. Strongly content-dependent — useful within a
replicate set, bad for cross-lens comparison. (Effectively equivalent
to the current JPEG-size proxy in failure modes.)

### 8. Blind PSF estimation via cepstrum

Recover the effective PSF from a single image. Fragile and
content-dependent; only useful as a sanity cross-check.

### 9. Deep no-reference IQA (BRISQUE, NIQE, MUSIQ, HyperIQA)

Trained on natural photos. Likely fails to generalise to silicon-wafer
microphotography. Use only as a robustness cross-check, not a primary
metric.

---

## JPEG caveat

All FFT- and MTF-based methods are capped by JPEG's high-frequency
quantisation step. For the same JPEG quality setting:
- *Relative rankings* between lenses are preserved → good for "which
  lens is sharper" decisions.
- *Absolute* MTF50 in cycles/pixel is depressed vs the optical truth →
  bad for comparing against published lens charts.

If absolute numbers are needed, re-extract from NEFs to TIFF and run
the metrics on those.

---

## Lossless JPEG cropping eliminates per-crop generation loss

A second round of pipeline tightening, also done while this dataset was
being processed, switched the crop step itself to a lossless JPEG
transform. The crop dimension changed from 500 px to **512 px** (the
smallest 16-multiple at or above 500), so every crop origin lands on a
clean MCU boundary and `TurboJPEG.crop_multiple` can re-pack the
encoded JPEG blocks into the output files without decoding back to RGB
and re-encoding. Crops now inherit the source JPEG's encoded quality
exactly — zero generation loss in the cropping step.

This kills another large source of noise on top of the resampler swap:

- Previously, every `make-N-crops.sh` invocation decoded the camera
  JPEG and re-encoded each sub-crop at GraphicsMagick's defaults. Two
  generations of JPEG compression on every crop before it ever hit the
  rail-coverage analyser.
- Previously, every resize step (`resize_bulk.py`) re-encoded its full
  resized JPEG *and* then re-encoded each of the 9 sub-crops on top of
  that. Three generations of compression on the resized crops.
- After the switch: one generation on lossless-cropped camera JPEGs;
  two generations on resized crops (resize is intrinsically lossy, but
  the 9-crop split itself is lossless).

Origins are computed via
`lens_test_detect_core.compute_crop_origins` (full-frame) and
`compute_dx_origins` (DX inner region); both snap to 16-multiples via
`align_down`. The live runtime cropper, the batch crop scripts and the
resize-bulk 9-crop split all share that source of truth, so the live
and offline analyses can't drift apart on crop geometry.

See `resize-bulk/RESIZED_COMPARISON.md` §0.0 for the file-size
implications.

## Empirical confirmation: resampler choice affects the JPEG-size proxy

While doing the resampled-lens comparisons (see
[`resize-bulk/RESIZED_COMPARISON.md`](resize-bulk/RESIZED_COMPARISON.md))
we accidentally produced a useful side-result on the JPEG-size proxy
itself. The original `resize-from-to.sh` upsampler was Lanczos; we
switched to Catmull-Rom (Catrom) for the second run, holding everything
else constant.

Same combo, same resized target, same aperture:
- 24-120 + Olympus MCON-35, 1_1-resized F8 (Lanczos): **113,917 bytes**
- 24-120 + Olympus MCON-35, 1_1-resized F8 (Catrom): **46,021 bytes**

A 60 % drop in file size from changing only the resample kernel. Almost
all of that delta is Lanczos's Gibbs ringing around edges — high-
frequency halos that have nothing to do with the optical signal but
that JPEG dutifully encodes, inflating file size.

Implications for using JPEG size as a sharpness proxy:

- **It is sensitive to upstream processing in unintuitive ways.** Any
  step in the pipeline that adds or removes high-frequency content
  (sharpening, resize kernel, noise reduction, sensor PDAF stripes,
  fast-readout artefacts) directly perturbs the proxy by amounts that
  can swamp the optical signal you're trying to measure.
- **Catrom is the more honest kernel** for this kind of analysis. It
  has only local overshoot, not the long-range Gibbs ringing of Lanczos.
  The relative rankings between lens combos were preserved across the
  two kernels but the gaps were much wider with Catrom — i.e. the proxy
  is more diagnostic when the noise from synthetic HF content is
  removed.
- The Catrom result also strengthens the case for moving to a real MTF
  metric (§1–§3 above). If a resize-kernel choice can move the proxy by
  60 %, the proxy clearly carries a lot of non-optical signal.

---

## Suggested first experiment

Cheapest validation before committing to a metric:

1. Pick ~10 `pick.jpg` files spanning lenses with strong priors
   (e.g. AF 200 f/4D should beat 24-120 + Raynox at matched mag).
2. Run MTF Mapper on each.
3. Plot MTF50; check the ranking matches visual intuition.

If consistent, codify in `rail-coverage/` as a new column alongside the
file-size proxy. If not, fall back to §2 (radial power-spectrum fit).

---

## Tool availability

Already present:
- `MTF mapper/workspace/mtfmapper/bin/mtf_mapper` (built from source).

May need installing (Arch):
- `python-scipy`, `python-scikit-image`, `python-opencv` for §2-§4
  (likely already available via uv envs).
- `paru -S mtfmapper-git` if the locally built binary is awkward to
  invoke.

---

## References

- Akamine et al., "A Novel No-Reference Image Quality Metric For
  Assessing Sharpness In Satellite Imagery" (2024) —
  <https://arxiv.org/html/2410.10488>
- Imatest, "Sharpness" — <https://www.imatest.com/imaging/sharpness/>
- Ferzli & Karam, "No-reference sharpness metric based on local edge
  kurtosis" (IEEE) — <https://ieeexplore.ieee.org/document/1038901/>
- Image Engineering, "Image Resolution / ISO 12233" —
  <https://www.image-engineering.de/library/image-quality/factors/1055-resolution>
- "Comparative evaluation of uncertainty in MTF estimation using
  periodic bar patterns: variance vs. harmonic methods" (2025) —
  <https://pubmed.ncbi.nlm.nih.gov/40614766/>
- "An Improved Method for Evaluating Image Sharpness Based on Edge
  Information" — <https://www.mdpi.com/2076-3417/12/13/6712>
- "A Simple Model for Sharpness in Digital Cameras" —
  <https://www.strollswithmydog.com/resolution-model-digital-cameras-iii/>
- Wikipedia, "Optical transfer function" —
  <https://en.wikipedia.org/wiki/Optical_transfer_function>
