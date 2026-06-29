# LSF over-read fix — variant comparison

## A. Synthetic (analytic-MTF ground truth)

11 PSF cases x 3 offsets x 24 reps, noise=0.004. **stress** adds a non-flat background (slope+texture) — the over-read driver.


### regime: clean (bg_slope=0.0, bg_texture=0.0)

| variant | median \|bias50\| | signed bias50 | MTF50-overread frac | MTF@Nyq overread frac | med Nyq excess |
|---|---|---|---|---|---|
| baseline_endtaper | 3.5% | -3.5% | 0% | 0% | +0.019 |
| centroid_hann_full | 3.1% | -2.9% | 0% | 0% | +0.010 |
| centroid_tukey_hw8 | 3.1% | -3.0% | 0% | 0% | +0.004 |
| centroid_tukey_hw12 | 3.1% | -3.0% | 0% | 0% | +0.006 |
| centroid_tukey_hw16 | 3.0% | -3.0% | 0% | 0% | +0.008 |
| centroid_tukey_hw24 | 3.0% | -3.0% | 0% | 0% | +0.012 |
| centroid_hamming_hw12 | 4.2% | -1.7% | 0% | 0% | +0.003 |
| centroid_tukey_hw12_dc | 2.9% | -2.7% | 0% | 0% | +0.007 |
| mirror_min | 3.5% | -3.5% | 0% | 0% | +0.019 |
| mirror_mean | 3.5% | -3.5% | 0% | 0% | +0.019 |

### regime: stress (bg_slope=0.1, bg_texture=0.06)

| variant | median \|bias50\| | signed bias50 | MTF50-overread frac | MTF@Nyq overread frac | med Nyq excess |
|---|---|---|---|---|---|
| baseline_endtaper | 11.3% | -11.2% | 0% | 0% | +0.017 |
| centroid_hann_full | 6.9% | -6.1% | 0% | 0% | +0.009 |
| centroid_tukey_hw8 | 8.3% | -2.7% | 11% | 4% | +0.010 |
| centroid_tukey_hw12 | 6.9% | -5.7% | 1% | 0% | +0.007 |
| centroid_tukey_hw16 | 6.7% | -5.6% | 0% | 0% | +0.008 |
| centroid_tukey_hw24 | 6.8% | -6.0% | 0% | 0% | +0.012 |
| centroid_hamming_hw12 | 7.7% | -3.2% | 5% | 0% | +0.005 |
| centroid_tukey_hw12_dc | 6.7% | -5.3% | 1% | 0% | +0.008 |
| mirror_min | 11.3% | -11.2% | 0% | 0% | +0.017 |
| mirror_mean | 11.3% | -11.2% | 0% | 0% | +0.017 |

## B. Real RAW — 2026-06-28 brick wall (in-focus AF frames; per-edge MEDIAN across frames — NO max-over-frames pick)

MTF50 in cy/sensor-px. Ceiling = diffraction MTF50 at the marked f-number (hard upper bound; M~0). At f/16 the lens is diffraction-limited so true MTF50 ~= ceiling and true MTF@Nyq ~= 0. A correct variant: per-edge **median MTF50 distribution centred at/below the ceiling**, low over-ceiling fraction, **MTF@Nyq tail near 0** (p95 << 1, not the max-pick artefact), ordering f/8 > f/11 > f/16.

| config | ceiling | variant | n edges | med50 | p90-50 | over-ceil | med Nyq | p95 Nyq | Nyq>1 |
|---|---|---|---|---|---|---|---|---|---|
| bare f/8 | 0.399 | baseline_endtaper | 95 | 0.217 | 0.402 | 11% | 0.262 | 0.73 | 4% |
| bare f/8 | 0.399 | centroid_hann_full | 228 | 0.201 | 0.293 | 6% | 0.229 | 0.69 | 2% |
| bare f/8 | 0.399 | centroid_tukey_hw8 | 236 | 0.219 | 0.413 | 11% | 0.281 | 0.92 | 4% |
| bare f/8 | 0.399 | centroid_tukey_hw12 | 233 | 0.205 | 0.391 | 9% | 0.239 | 0.87 | 3% |
| bare f/8 | 0.399 | centroid_tukey_hw16 | 224 | 0.209 | 0.406 | 11% | 0.245 | 0.76 | 2% |
| bare f/8 | 0.399 | centroid_tukey_hw24 | 226 | 0.208 | 0.361 | 8% | 0.227 | 0.76 | 2% |
| bare f/8 | 0.399 | centroid_hamming_hw12 | 221 | 0.206 | 0.351 | 5% | 0.212 | 0.86 | 2% |
| bare f/8 | 0.399 | centroid_tukey_hw12_dc | 233 | 0.205 | 0.391 | 9% | 0.245 | 0.89 | 3% |
| bare f/8 | 0.399 | mirror_min | 95 | 0.217 | 0.402 | 11% | 0.262 | 0.73 | 4% |
| bare f/8 | 0.399 | mirror_mean | 95 | 0.217 | 0.402 | 11% | 0.262 | 0.73 | 4% |
| bare f/11 | 0.290 | baseline_endtaper | 248 | 0.207 | 0.393 | 21% | 0.207 | 0.75 | 2% |
| bare f/11 | 0.290 | centroid_hann_full | 763 | 0.190 | 0.301 | 11% | 0.170 | 0.53 | 0% |
| bare f/11 | 0.290 | centroid_tukey_hw8 | 786 | 0.219 | 0.394 | 26% | 0.273 | 0.88 | 3% |
| bare f/11 | 0.290 | centroid_tukey_hw12 | 759 | 0.206 | 0.380 | 24% | 0.241 | 0.84 | 2% |
| bare f/11 | 0.290 | centroid_tukey_hw16 | 758 | 0.207 | 0.416 | 25% | 0.227 | 0.80 | 3% |
| bare f/11 | 0.290 | centroid_tukey_hw24 | 743 | 0.200 | 0.402 | 22% | 0.191 | 0.75 | 2% |
| bare f/11 | 0.290 | centroid_hamming_hw12 | 702 | 0.199 | 0.364 | 22% | 0.175 | 0.75 | 2% |
| bare f/11 | 0.290 | centroid_tukey_hw12_dc | 758 | 0.206 | 0.388 | 24% | 0.246 | 0.86 | 2% |
| bare f/11 | 0.290 | mirror_min | 248 | 0.207 | 0.393 | 21% | 0.207 | 0.75 | 2% |
| bare f/11 | 0.290 | mirror_mean | 248 | 0.207 | 0.393 | 21% | 0.207 | 0.75 | 2% |
| bare f/16 | 0.200 | baseline_endtaper | 249 | 0.225 | 0.300 | 68% | 0.198 | 0.44 | 0% |
| bare f/16 | 0.200 | centroid_hann_full | 820 | 0.194 | 0.267 | 45% | 0.137 | 0.33 | 0% |
| bare f/16 | 0.200 | centroid_tukey_hw8 | 811 | 0.215 | 0.367 | 57% | 0.246 | 0.75 | 2% |
| bare f/16 | 0.200 | centroid_tukey_hw12 | 782 | 0.207 | 0.357 | 53% | 0.194 | 0.70 | 1% |
| bare f/16 | 0.200 | centroid_tukey_hw16 | 762 | 0.201 | 0.327 | 51% | 0.163 | 0.64 | 1% |
| bare f/16 | 0.200 | centroid_tukey_hw24 | 801 | 0.194 | 0.317 | 47% | 0.147 | 0.54 | 0% |
| bare f/16 | 0.200 | centroid_hamming_hw12 | 716 | 0.195 | 0.320 | 48% | 0.137 | 0.57 | 1% |
| bare f/16 | 0.200 | centroid_tukey_hw12_dc | 782 | 0.207 | 0.361 | 53% | 0.199 | 0.71 | 1% |
| bare f/16 | 0.200 | mirror_min | 249 | 0.225 | 0.300 | 68% | 0.198 | 0.44 | 0% |
| bare f/16 | 0.200 | mirror_mean | 249 | 0.225 | 0.300 | 68% | 0.198 | 0.44 | 0% |
| tc14 f/8 | 0.399 | baseline_endtaper | 309 | 0.189 | 0.404 | 10% | 0.223 | 0.72 | 1% |
| tc14 f/8 | 0.399 | centroid_hann_full | 559 | 0.180 | 0.359 | 6% | 0.214 | 0.65 | 1% |
| tc14 f/8 | 0.399 | centroid_tukey_hw8 | 555 | 0.205 | 0.391 | 9% | 0.338 | 0.92 | 4% |
| tc14 f/8 | 0.399 | centroid_tukey_hw12 | 529 | 0.197 | 0.371 | 7% | 0.313 | 0.78 | 1% |
| tc14 f/8 | 0.399 | centroid_tukey_hw16 | 530 | 0.197 | 0.371 | 8% | 0.286 | 0.83 | 2% |
| tc14 f/8 | 0.399 | centroid_tukey_hw24 | 547 | 0.196 | 0.352 | 6% | 0.264 | 0.70 | 1% |
| tc14 f/8 | 0.399 | centroid_hamming_hw12 | 499 | 0.186 | 0.335 | 3% | 0.220 | 0.73 | 1% |
| tc14 f/8 | 0.399 | centroid_tukey_hw12_dc | 528 | 0.198 | 0.370 | 7% | 0.321 | 0.80 | 2% |
| tc14 f/8 | 0.399 | mirror_min | 309 | 0.189 | 0.404 | 10% | 0.223 | 0.72 | 1% |
| tc14 f/8 | 0.399 | mirror_mean | 309 | 0.189 | 0.404 | 10% | 0.223 | 0.72 | 1% |
| tc14 f/11 | 0.290 | baseline_endtaper | 443 | 0.228 | 0.408 | 29% | 0.332 | 0.81 | 2% |
| tc14 f/11 | 0.290 | centroid_hann_full | 812 | 0.209 | 0.363 | 24% | 0.298 | 0.73 | 1% |
| tc14 f/11 | 0.290 | centroid_tukey_hw8 | 844 | 0.209 | 0.450 | 28% | 0.398 | 1.00 | 5% |
| tc14 f/11 | 0.290 | centroid_tukey_hw12 | 828 | 0.209 | 0.390 | 25% | 0.367 | 0.93 | 3% |
| tc14 f/11 | 0.290 | centroid_tukey_hw16 | 818 | 0.211 | 0.385 | 24% | 0.358 | 0.89 | 3% |
| tc14 f/11 | 0.290 | centroid_tukey_hw24 | 824 | 0.213 | 0.380 | 25% | 0.343 | 0.79 | 2% |
| tc14 f/11 | 0.290 | centroid_hamming_hw12 | 774 | 0.197 | 0.338 | 16% | 0.278 | 0.90 | 4% |
| tc14 f/11 | 0.290 | centroid_tukey_hw12_dc | 827 | 0.209 | 0.393 | 26% | 0.377 | 0.96 | 4% |
| tc14 f/11 | 0.290 | mirror_min | 443 | 0.228 | 0.408 | 29% | 0.332 | 0.81 | 2% |
| tc14 f/11 | 0.290 | mirror_mean | 443 | 0.228 | 0.408 | 29% | 0.332 | 0.81 | 2% |
