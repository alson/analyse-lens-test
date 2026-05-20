# Wide-angle sloped-stair sharpness — 2026-01 (24mm and 26mm sessions)

Empirical results from the 2026-01-24 and 2026-01-26 wide-angle test
sessions. Companion to [`SHARPNESS_METRICS_LONGDIST.md`](SHARPNESS_METRICS_LONGDIST.md)
(methodology) and [`LONGDIST_TELE_RESULTS_2026-01.md`](LONGDIST_TELE_RESULTS_2026-01.md)
(the matching telephoto analysis).

Scope: 13 wide / standard / short-tele lenses at 14–60 mm shot against
the sloped-stair + grass-embankment + sky scene from the doc. Four
sharpness algorithms compared on identical tile selections to assess
each algorithm's stability, accuracy, and lighting robustness.

## 1. Setup

| Date | Lenses | Notable |
|---|---|---|
| 2026-01-24 | Z 14-24/2.8 S, Z 24-120/4 S, AF Micro 60/2.8D, AF 35/2, AF 50/1.8 N, AF-S DX 35/1.8G, AF-S 50/1.8G, Nikkor-N.C 24/2.8, PC-Nikkor 35/2.8, Sigma 24/2.8, Viltrox 14/4 Z, Viltrox 50/2 Z | 107 (lens, FL, ap) configs, ~3 repl each |
| 2026-01-26 | Z 14-24/2.8 S (also `AF for every pic` variant), Z 24-120/4 S, AF Micro 60/2.8D, AF 50/1.8 N, AF-S 50/1.8G, Nikkor-N.C 24/2.8, Sigma 24/2.8, Viltrox 14/4 Z, **Viltrox 16/1.8 Z** (also `AF once` and `AF every pic` variants), Viltrox 50/2 Z | 111 configs, 3–10 repl each |

Scene: planar concrete stair / grass slope with structural detail —
wall horizon, asphalt boundary, stair treads, zigzag bike path railing,
lamp posts, fence segments. The `AF for every pic` variants re-trigger
AF between replicates to sample multiple focal-plane positions (per
user clarification: this samples the scene's depth structure, not AF
repeatability per se).

Cyclists / pedestrians intermittently in the path — handled by the
consensus tile picker (§2).

## 2. Methodology

### Field-position sweep

Same 5-position horizontal sweep as the telephoto analysis (x = 0.18,
0.34, 0.50, 0.66, 0.82 of frame width).

### Consensus tile selection (movement rejection)

For each search box at each field position:

1. Per replicate, compute the gradient-energy map across all 256 × 256
   candidate tile positions (step 64 px).
2. Take the **median gradient-energy across replicates** at each
   candidate position.
3. Pick the candidate position with the **highest median**. A static
   high-gradient feature (wall horizon, lamp post) has comparable
   gradient on every replicate; a moving cyclist has high gradient in
   only one frame, so the median demotes those positions.
4. Movement flag: if the per-replicate gradient-max positions disagree
   by > 2 search-steps (~128 px), the cell is flagged as
   movement-corrupted. We still measure but mark for caution.

### Four sharpness algorithms

All four are computed on the **same consensus tile** in each replicate,
so any disagreement reflects algorithmic choice, not scene/position
variation.

| Algorithm | Domain | Returns | Best for |
|---|---|---|---|
| `radial_cutoff` | Frequency (radially-averaged spectrum) | cy/sensor-px | Threshold-free cross-scene comparison |
| `mtf50_slanted_edge` | Edge-based, ISO 12233-style | cy/sensor-px | Physical MTF on real edges (when present) |
| `vol` | Gradient (variance of Laplacian) | Unitless variance | Simple, fast, sensitive to amplitude |
| `brenner` | Gradient (squared-diff at lag 2) | Unitless | Simple, fast, directional |

Per cell we report `top` / `median` / `min` / `top_vs_median` /
`range_pct` for each algorithm — same statistical framing as the
telephoto v2 analysis (top = best replicate, median = typical reading,
top_vs_median > 1.10 = top is a flier).

## 3. Algorithm comparison — headline

### 3a. Stability across replicates (lower CV = more consistent)

Per cell, **CV = (top − min) / median × 100**. Lower is better — the
algorithm gave a consistent reading across the burst.

| Algorithm | median CV | p90 CV | n cells produced | NaN rate |
|---|---|---|---|---|
| **radial_cutoff** | **0.0 %** | 2.9–5.5 % | 535 / 555 | ~0 % |
| `mtf50_slanted_edge` | 34–38 % | 127–171 % | 158–207 (~28–39 %) | ~60–70 % |
| `vol` | 1.6–2.5 % | 10–11 % | 535 / 555 | ~0 % |
| `brenner` | 1.1–1.9 % | 9–10 % | 535 / 555 | ~0 % |

- `radial_cutoff` is hyper-stable (most cells return *identical* values
  across replicates) but possibly because the cutoff lands on the same
  FFT bin for visually-similar tiles. Stability is real but resolution
  is FFT-quantized.
- `mtf50_slanted_edge` is unstable: 34–38 % median CV, p90 ≥ 127 %.
  Plus a 60–70 % NaN rate — the algorithm could not detect a strong
  slanted edge in most tiles. **Not usable as a primary metric on this
  scene without major rework.**
- `vol` and `brenner` are both very stable (≤ 2.5 % CV) and fully
  produced — solid baselines.

### 3b. Cross-algorithm rank agreement (Spearman ρ on `top`)

Do the algorithms rank the (lens, FL, aperture, position) cells the
same way?

**2026-01-24:**

|  | radial | mtf50 | vol | brenner |
|---|---|---|---|---|
| `radial_cutoff` | 1.00 | 0.10 | **0.89** | 0.82 |
| `mtf50_slanted_edge` | 0.10 | 1.00 | 0.11 | 0.13 |
| `vol` | 0.89 | 0.11 | 1.00 | **0.98** |
| `brenner` | 0.82 | 0.13 | 0.98 | 1.00 |

**2026-01-26** (more lenses, more replicate variation including AF-every-pic):

|  | radial | mtf50 | vol | brenner |
|---|---|---|---|---|
| `radial_cutoff` | 1.00 | -0.05 | **0.67** | 0.56 |
| `mtf50_slanted_edge` | -0.05 | 1.00 | 0.20 | 0.14 |
| `vol` | 0.67 | 0.20 | 1.00 | **0.96** |
| `brenner` | 0.56 | 0.14 | 0.96 | 1.00 |

- **`vol` and `brenner` are essentially the same algorithm** (ρ ≥ 0.96
  on both dates). Both are gradient-amplitude metrics; their
  agreement validates the gradient-domain family but doesn't add
  information.
- **`radial_cutoff` agrees well with the gradient family** (ρ = 0.67 to
  0.89) — the three "frequency / gradient" algorithms broadly rank
  lenses the same way.
- **`mtf50_slanted_edge` is uncorrelated** with all other algorithms
  (ρ ≈ ±0.10 in both datasets). Combined with its high NaN rate, this
  means its non-NaN outputs are mostly metric noise rather than signal.

### 3c. Lighting robustness probe

Apply uniform brightness, contrast, and gamma transforms to one
reference sharp tile and re-measure each algorithm. Robust algorithms
should not shift; lighting-amplitude-sensitive ones will track the
transform.

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| brightness −1.0 EV | +0 % | (NaN) | **−75 %** | **−75 %** |
| brightness −0.5 EV | +0 % | (NaN) | **−50 %** | **−50 %** |
| baseline | 0 % | (NaN) | 0 % | 0 % |
| brightness +0.5 EV | +0 % | (NaN) | **+100 %** | **+100 %** |
| brightness +1.0 EV | +0 to +1 % | (NaN) | **+273–284 %** | **+263–276 %** |
| contrast × 0.7 | +0 % | (NaN) | −51 % | −51 % |
| contrast × 1.3 | +0 % | (NaN) | +69 % | +69 % |
| gamma 0.7 | +0 % | (NaN) | −2 to −4 % | −3 % |
| gamma 1.3 | +0 to +1 % | (NaN) | −11 to −13 % | −12 to −13 % |

- **`radial_cutoff` is fully lighting-invariant** — by construction
  (low-band normalisation cancels global amplitude scaling, which is
  what brightness/contrast are).
- **`vol` and `brenner` track brightness quadratically** (since they
  measure squared gradients): −0.5 EV → −50 %, +1.0 EV → +273 %. They
  are useful only when comparing same-lighting frames.
- **`mtf50_slanted_edge` failed to fire on the reference tile** (no
  detectable strong edge in the canonical sharp tile despite having
  high radial_cutoff). That's a tell: the slanted-edge algorithm
  needs an actual dominant edge, and even a "sharp" tile from the
  middle of the bike-path scene didn't have one.

### 3d. Recommended algorithm choice for this dataset

| Use case | Recommended |
|---|---|
| Within-day cross-aperture / cross-position ranking | `radial_cutoff` |
| Within-day cross-lens ranking (same lighting) | `radial_cutoff` ≈ `vol` |
| Across-day or across-lighting comparison | **`radial_cutoff`** (only lighting-invariant option) |
| Edge-MTF physical units | `mtf50_slanted_edge` (NaN where no edge — accept low coverage) |

`vol` and `brenner` are interchangeable; one of them is enough.
`mtf50_slanted_edge` would need a better edge-detector + edge-ROI
selector to be useful here (current ISO-12233-style auto-detection
fires on too few tiles).

## 4. Centre vs frame edges — the cluster splits when you leave centre

**The "all lenses cluster at 0.30–0.35 cy/sensor-px" reading is a
CENTRE-only artifact**. Edge values open up a much wider spread, and
several lenses (especially F-mount primes wide-open and the
Viltrox 16/1.8 wide-open) drop to the metric's floor at 0.20 cy/px.

### 4a. Best aperture per lens — centre + edges (radial_cutoff)

At each lens' centre-best aperture, the corresponding edge cutoffs at
x=0.18 (left) and x=0.82 (right). 2026-01-24 dataset.

| Lens (FL, best-centre aperture) | centre | x=0.18 (L) | x=0.82 (R) | min edge / centre |
|---|---|---|---|---|
| NIKKOR Z 14-24/2.8 S @ 24, f/4 | **0.348** | 0.262 | 0.277 | 0.75 |
| NIKKOR Z 14-24/2.8 S @ 24, f/5.6 | 0.344 | 0.273 | 0.285 | 0.79 |
| Viltrox AF 50/2 Z @ 50, f/2.8 | 0.336 | 0.273 | **0.320** | 0.81 |
| NIKKOR Z 14-24/2.8 S @ 24, f/8 | 0.336 | 0.258 | 0.266 | 0.77 |
| Sigma 24/2.8 Super Wide II Macro @ 24, f/5.6 | 0.328 | 0.223 | 0.254 | **0.68** |
| Viltrox AF 50/2 Z @ 50, f/4 | 0.324 | 0.305 | 0.309 | 0.94 |
| Nikon AF-S DX 35/1.8G @ 35, f/5.6 | 0.324 | 0.281 | **0.203** ⚠ | **0.63** |
| Nikon AF Micro 60/2.8D @ 60, f/5.6 | 0.324 | 0.273 | **0.215** ⚠ | **0.66** |
| Nikon AF Micro 60/2.8D @ 60, f/2.8 | 0.324 | 0.230 | **0.203** ⚠ | **0.63** |
| Nikon AF-S DX 35/1.8G @ 35, f/8 | 0.316 | 0.285 | 0.270 | 0.85 |
| Nikon AF Micro 60/2.8D @ 60, f/4 | 0.316 | 0.238 | **0.203** ⚠ | **0.64** |
| Viltrox AF 50/2 Z @ 50, f/5.6 | 0.313 | 0.289 | 0.316 | 0.93 |
| Nikon AF-S Nikkor 50/1.8G @ 50, f/2 | 0.313 | 0.242 | **0.203** ⚠ | **0.65** |
| Nikon PC-Nikkor 35/2.8 @ 35, f/4 | 0.313 | 0.230 | **0.203** ⚠ | **0.65** |
| Nikon AF Nikkor 50/1.8 N @ 50, f/2.8 | 0.313 | **0.203** | **0.203** | **0.65** |

⚠ = right edge at the metric's floor (0.20 cy/px) — visibly soft at
100 % view.

**The pattern: F-mount primes (AF/AF-S Nikkor 35/2, 50/1.8 N, 50/1.8G,
AF Micro 60/2.8D, PC-Nikkor 35/2.8) all drop the right edge to 0.20**
at the centre-best aperture. Z lenses and the Viltrox primes hold the
edges much closer to centre (ratio ≥ 0.75).

### 4b. Best edge aperture per lens (not the same as centre-best)

If you care about frame-edge sharpness specifically — say a horizon
that spans the whole frame width — stop down past the centre-best
aperture. Best **edge-mean** ((x=0.18 + x=0.82)/2) aperture per lens
where it differs notably from centre-best:

| Lens | Centre-best | Edge-best | Edge-mean @ best |
|---|---|---|---|
| Viltrox AF 14/4 Z @ 14 | f/5.6 (centre 0.30) | **f/5.6** | 0.305 |
| Viltrox AF 50/2 Z @ 50 | f/2.8 (centre 0.336) | **f/4** | 0.307 (with centre 0.324) |
| Nikon AF Micro 60/2.8D @ 60 | f/5.6 (centre 0.324) | **f/8** | 0.282 (with centre still 0.32) |
| Nikon AF-S DX 35/1.8G @ 35 | f/5.6 (centre 0.324) | **f/8** | 0.278 (centre drops only to 0.316) |
| NIKKOR Z 14-24/2.8 S @ 24 | f/4 (centre 0.348) | **f/5.6** | 0.279 |

For most lenses, the edge optimum is **1 stop tighter than the centre
optimum** — confirming the photographer's rule of thumb.

### 4c. Viltrox 16/1.8 Z — strong wide-open asymmetry

The 2026-01-26 dataset includes the Viltrox 16/1.8 in both `AF for every
pic` and `AF once` variants. Edge cutoffs at 16 mm:

| Aperture | x=0.18 (L) | x=0.82 (R) | L − R asymmetry |
|---|---|---|---|
| f/1.8 | 0.281 | **0.203** ⚠ | 0.08 |
| f/2 | 0.281 | **0.203** ⚠ | 0.08 |
| f/2.8 | 0.313 | **0.203** ⚠ | 0.11 |
| f/4 | 0.313 | 0.273 | 0.04 |
| **f/5.6** | **0.320** | **0.301** | 0.02 |
| f/8 | 0.301 | 0.285 | 0.02 |
| f/11 | 0.277 | 0.258 | 0.02 |

**At f/1.8–f/2.8 the right edge is stuck at the 0.20 floor**; the left
edge already works at f/1.8. The asymmetry vanishes by f/4 and the
edges are best at f/5.6 (consistent across both `AF every pic` and
`AF once` variants — so this isn't an AF issue, it's optical).
Confirms your visual impression that the Viltrox 16 needs stopping
down for clean corners.

### 4d. Whose corners hold up wide-open

Wide-open corner cutoff (best of x=0.18 and x=0.82), 2026-01-24:

| Lens | Wide-open | Best wide-open corner | Read |
|---|---|---|---|
| Viltrox AF 50/2 Z @ 50, f/2 | f/2 | 0.290 | Best wide-open corners |
| NIKKOR Z 14-24/2.8 S @ 24, f/2.8 | f/2.8 | 0.262 | Decent |
| Viltrox AF 14/4 Z @ 14, f/4 | f/4 (wide) | 0.305 | Decent (wide is f/4 anyway) |
| Nikon AF Nikkor 50/1.8 N @ 50, f/1.8 | f/1.8 | 0.203 ⚠ | Floor — useless corners wide-open |
| Nikon AF-S Nikkor 50/1.8G @ 50, f/1.8 | f/1.8 | 0.226 ⚠ | Near floor |
| Nikon AF Nikkor 35/2 @ 35, f/2 | f/2 | 0.203 ⚠ | Floor |
| Nikon AF Micro 60/2.8D @ 60, f/2.8 | f/2.8 | 0.230 | Near floor (right edge at 0.20) |

The Z and Viltrox autofocus lenses have noticeably better wide-open
corners than the legacy F-mount Nikon primes. The F-mount primes
genuinely **do** need stopping down (1–2 stops) for usable corners.

### 4e. Honest centre-only summary

At centre (x=0.50) the lens differences are real but small —
0.30 to 0.35 cy/sensor-px — and the metric's FFT-bin quantization
compresses them further. The interesting story is at the edges.

**Lenses that excel both at centre AND edges**:
- NIKKOR Z 14-24/2.8 S (any aperture f/4–f/8)
- Viltrox AF 50/2 Z @ f/4–f/5.6

**Lenses that are centre-sharp but corner-weak at their centre-best
aperture** (stop down ~1 stop for usable corners):
- Sigma 24/2.8 Super Wide II Macro
- AF-S DX 35/1.8G
- AF Micro 60/2.8D
- AF-S Nikkor 50/1.8G
- AF Nikkor 50/1.8 N
- PC-Nikkor 35/2.8
- Viltrox 16/1.8 Z (especially the right edge; needs f/4–f/5.6)

## 5. Movement-detection findings

The cross-replicate consensus picker flagged cells where the
per-replicate gradient-max positions disagreed by > 2 search-steps,
indicating moving content (cyclist / pedestrian).

| Date | n cells flagged | Affected lenses | Affected positions |
|---|---|---|---|
| 2026-01-24 | **39** | mostly Z 14-24 @ 14 / 24 mm | concentrated at x = 0.34 and x = 0.50 (the path / stairs band) |
| 2026-01-26 | **5** | scattered (Z 14-24 AF-every-pic, Z 24-120 @ 60 mm, AF 50/1.8 N) | mixed |

- 2026-01-24 had substantially more moving-subject contamination
  (39 cells vs 5). Either more cyclists were in the scene that day,
  or the search-box positions / aperture choices put them in the
  measurement zone more often.
- The flagged positions concentrate at **x = 0.34 and x = 0.50** —
  exactly where the user said cyclists would be (the central bike
  path and stair area).
- The consensus picker's median-gradient still works on flagged cells —
  it just locks onto the most-static-gradient feature available even
  when one replicate's local content moved. The flag is a "treat with
  caution" marker, not "data discarded."

## 6. Headline findings

1. **`radial_cutoff` is the right primary algorithm for this dataset.**
   Highest stability (0 % median CV), full coverage (~0 % NaN), and
   fully lighting-invariant. The trade-off is FFT-bin quantization that
   produces a narrow dynamic range (~0.29–0.35 cy/sensor-px across the
   13 lenses tested).
2. **`mtf50_slanted_edge` as implemented is not usable on this scene.**
   60–70 % NaN rate, 34–38 % median CV when it does fire, and
   uncorrelated with the other algorithms (suggests noise rather than
   signal). To use it productively, the edge detector and ROI selector
   would need a major rewrite — possibly with hand-specified edge ROIs
   per the doc (wall horizon, asphalt boundary).
3. **`vol` and `brenner` are interchangeable** (Spearman ρ ≥ 0.96) and
   work well within a single lighting environment. They cannot be used
   for cross-day comparisons because they track brightness quadratically.
4. **Consensus tile picker successfully rejects cyclists** without
   discarding cells — flags 39 cells on 2026-01-24 for further
   inspection. Cyclists concentrate at x = 0.34 / 0.50 as the user
   warned.
5. **Best wide-angle / standard lenses on this scene** (centre values):
   - Best overall: NIKKOR Z 14-24mm f/2.8 S @ 24 mm f/4 (0.348 cy/px)
   - Best 50 mm: Viltrox AF 50/2 Z @ f/2.8 (0.336 cy/px)
   - Best 60 mm: AF Micro 60/2.8D @ f/5.6 (0.324 cy/px)
   - Best 35 mm: AF-S DX 35/1.8G @ f/5.6 (0.324 cy/px)
6. **Edges open up a wider spread than the centre cluster suggests.**
   Many F-mount primes (50/1.8 N, 50/1.8G, 60/2.8D, PC-Nikkor 35/2.8)
   drop the right edge to the 0.20 cy/px floor at their centre-best
   aperture and need 1 stop more for usable corners. The Z 14-24,
   Viltrox AF 50/2 Z, and Viltrox AF 14/4 Z hold edges much closer
   to centre. The Viltrox 16/1.8 has strong right-edge asymmetry
   wide-open through f/2.8 (right edge stuck at 0.20 cy/px) — clean
   from f/4 onward, best at f/5.6.

## 7. Limitations and follow-ups

- **`radial_cutoff` resolution is FFT-bin-limited.** Three lenses
  reporting identical 0.328 cy/sensor-px may actually differ; the
  metric just can't see the difference. To resolve this, sub-bin
  interpolation on the spectrum crossing point, or a smaller-bin FFT
  (e.g. 512 × 512 tiles instead of 256 × 256) would help.
- **The slanted-edge algorithm needs a hand-picked edge ROI**, per
  the doc's recommendation. Auto-detection fails on too many tiles
  even when a strong edge is visually present, because:
  - The wall-horizon edge is mostly horizontal — gradient direction
    averaging gets confused by near-horizontal sky gradients.
  - The asphalt boundary is at the bottom of the frame, outside the
    "centre 20 % of vertical" search box used by the consensus picker.
  - Stair-tread edges are short and offset, not a single dominant
    direction in a 256 × 256 tile.
- **Best-cutoff-per-lens table compresses many apertures.** A full
  table with (lens × FL × aperture × position) would be useful for
  someone choosing apertures specifically. The per-measurement CSV
  has all of this.
- **The vertical-axis depth dimension is not exploited**, per the
  long-distance doc's recommendation to fit 1D sharpness-vs-y curves
  on planar slopes for field-curvature measurement. The 5-position
  horizontal sweep used here matches the telephoto method but doesn't
  capture the slope-as-focus-bracket signal.

## 8. Data and code

| File | Content |
|---|---|
| `tile-sharpness/scripts/poc_longdist_algorithms.py` | Algorithm-comparison script (4 algorithms + consensus tile + lighting probe) |
| `tile-sharpness/scripts/poc_longdist_algorithms_out/wide2026_01_24/` | Per-measurement CSV + algorithms_summary.md + correlation_matrices.png for 2026-01-24 |
| `tile-sharpness/scripts/poc_longdist_algorithms_out/wide2026_01_26/` | Same for 2026-01-26 |

Per-measurement CSV columns: date, lens_dir, focal_mm, aperture,
position_frac, algorithm, top, median, min, top_vs_median, range_pct,
n_replicates, consensus_y, consensus_x, movement_flag.
