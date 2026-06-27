# Wide-angle / standard sharpness — multi-date, multi-camera

Empirical results across Z7 and D7200 wide / standard test sessions.
Companion to [`SHARPNESS_METRICS_LONGDIST.md`](SHARPNESS_METRICS_LONGDIST.md)
(methodology) and [`LONGDIST_TELE_RESULTS.md`](LONGDIST_TELE_RESULTS.md)
(matching telephoto analysis).

Scope: Z7 wide datasets 2026-01-24, 2026-01-26, 2026-02-07/20 mm. D7200
wide datasets 2025-09-10 and 2025-09-11 (the latter is at mixed distance
classes — see §6.5b). Four sharpness algorithms compared on identical tile selections
to assess each algorithm's stability, accuracy, and lighting robustness.
Cross-camera cy/sensor-px values are not directly comparable (D7200 has
3.91 µm pixel pitch vs Z7's 4.35 µm); the D7200 data lives in §6 with
its own ranking.

> **2026-06 — `radial_cutoff` metric definition changed (§5.3).**
> All `cy/sensor-px` numbers in this doc were recorded under the
> original metric: `REF_BAND = (0.01, 0.20)`, first-crossing, no
> smoothing. The metric now uses `REF_BAND = (0.01, 0.10)`,
> last-crossing on a Gaussian-smoothed normalised spectrum (σ=2
> bins). See [`RADIAL_CUTOFF_REFBAND_RESULTS.md`](RADIAL_CUTOFF_REFBAND_RESULTS.md).
> Absolute values are typically **12–15 % lower** for sharp Z7
> measurements and **higher** for previously-floored soft cases
> (D7200 wide). **Rankings within each dataset are preserved** except
> where the old metric was at floor — in which case the new metric
> reveals previously-hidden ordering. Specifically: this doc's
> 0.30–0.35 "centre cluster" note (FFT-bin quantisation, §4e and §7
> limitations) is resolved by the new metric. The per_measurement.csv
> files under `poc_longdist_algorithms_out/wide*/` and
> `mid2025_09_11/` reflect §5.3; the prose in §6 headlines and §4e /
> §7 limitations is updated; the deep per-lens prose tables in
> §4a/b/c/d still cite pre-§5.3 values and would each shift ~12 %
> lower under §5.3, preserving ranking.
>
> **What changed under §5.3 for this dataset:** centre-cluster
> bin compression resolved (38 → 442 distinct values on wide2026_01_24).
> Lenses that previously read identical 0.328 cy/sensor-px at centre
> now have differentiable values. Edge values that previously hit
> the 0.20 floor (F-mount primes wide-open) resolve into 0.13–0.18
> cy/px range — rankings the same, magnitudes more honest. The
> §4a–§4d tables and the §6/§6.5 lens prose are now all refreshed
> with §5.3 values.

## 1. Setup

### Z7 datasets (FX, 4.35 µm pixel pitch)

| Date | Lenses | Notable |
|---|---|---|
| 2026-01-24 | Z 14-24/2.8 S, Z 24-120/4 S, AF Micro 60/2.8D, AF 35/2, AF 50/1.8 N, AF-S DX 35/1.8G, AF-S 50/1.8G, Nikkor-N.C 24/2.8, PC-Nikkor 35/2.8, Sigma 24/2.8, Viltrox 14/4 Z, Viltrox 50/2 Z | 107 configs, ~3 repl each |
| 2026-01-26 | Z 14-24/2.8 S (also `AF for every pic` variant), Z 24-120/4 S, AF Micro 60/2.8D, AF 50/1.8 N, AF-S 50/1.8G, Nikkor-N.C 24/2.8, Sigma 24/2.8, Viltrox 14/4 Z, **Viltrox 16/1.8 Z** (also `AF once` and `AF every pic` variants), Viltrox 50/2 Z | 111 configs, 3–10 repl each |
| 2026-02-07/20 mm | Z 20/1.8 S, Z 14-24/2.8 S, AF Nikkor 20/2.8, Viltrox AF 20/2.8 Z Air — all at 20 mm | 52 configs, 3–6 repl each. ISO 100 / 400 / 800 ladders |

### D7200 datasets (DX, 3.91 µm pixel pitch — §6)

| Date | Lenses | Notable |
|---|---|---|
| 2025-09-10 | AF Fisheye 10.5/2.8G, AF Nikkor 20/2.8, AF-S DX 16-80/2.8-4E, AF-S DX 16-85/3.5-5.6G, AF-S DX 17-55/2.8G, AF-S DX 18-70/3.5-4.5G, Nikkor-N.C 24/2.8, Sigma 10-20/4-5.6, Sigma 18-35/1.8, Sigma 24/2.8, Tokina 11-20/2.8 | 237 configs |
| 2025-09-11 | DX 18-70 + Sigma 50-150/2.8 I/II + AF 35/2 + AF 50/1.8 + others (18 lenses) | 248 configs; **mixed distance classes — per-(lens, FL) audit in §6.5b**. Most is infinity-class; the DX 18-70 + DX 35/1.8G sub-session is close-test (20-50× FL). |

Scene per dataset (validated by sampling sharp shots — see §3):

- **2026-01-24 / 2026-01-26 / 2025-09-10**: concrete stairs + diagonal handrails + grass embankment + sky.
  Same physical scene reused across years.
- **2026-02-07/20 mm**: same location but framed lower → grass-dominated centre, structural content
  pushed into edges. Different sub-position from the other wide-angle dates.
- **2025-09-11**: same physical location as 2025-09-10, multiple sub-sessions
  at different distance classes. The DX 18-70 + DX 35/1.8G sub-session is at
  close-test distance (20-50× FL — Focal-style test minimum). Most other
  lenses at infinity-class. Per-(lens, FL) audit in §6.5b.

Cyclists / pedestrians intermittently in the path — handled by the
consensus tile picker (§2).

### Lens-encoder presence (deriveable from slug)

EXIF FocusDistance is only reliable for lenses with a distance encoder.
Determinable from the lens-slug suffix:

| Has encoder | Slug pattern | Examples |
|---|---|---|
| ✓ | aperture marked `D` | `AF Micro-Nikkor 60mm f_2.8D`, `AF-S Nikkor 300mm f_4D IF-ED` |
| ✓ | aperture marked `G` | `AF-S 50/1.8G`, `AF-S DX Nikkor 18-70/3.5-4.5G` |
| ✓ | aperture marked `E` | `AF-S DX Nikkor 16-80/2.8-4E`, `AF-S 300mm f_4E PF ED VR` |
| ✓ | Z-mount native | `NIKKOR Z 20mm f_1.8 S`, `Viltrox AF 20_2.8 Z` |
| ✗ | `AF Nikkor` with no D / G / E | `AF Nikkor 50/1.8 N`, `AF Nikkor 35/2`, `AF Nikkor 20/2.8` |
| ✗ | manual focus (`AIS`, `Nikkor-N.C Auto`, `PC-Nikkor`) | `Nikon Micro-Nikkor 55mm f_2.8 AIS`, `Nikkor-N.C Auto 24mm f_2.8`, `PC-Nikkor 35mm f_2.8` |

Note: focus drive (`AF`, `AF-S`, `AF-I`, `AF-P`) is independent of encoder
presence. The encoder marker is the **aperture suffix** (D/G/E), not the
focus drive.

For non-encoder lenses, distance is inferred from another encoder-equipped
lens shot at the same FL in the same sub-session (per user: tripod is not
moved within a focal length).

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

**Pre-§5.3 reading: "all lenses cluster at 0.30–0.35 cy/sensor-px at
centre" — was largely FFT-bin quantisation.** Under the §5.3 metric
the centre cluster spreads into ~0.24–0.30 cy/sensor-px (12-15 %
lower in absolute terms, no longer compressed into a few bins —
see `RADIAL_CUTOFF_REFBAND_RESULTS.md`). The edge story below still
holds qualitatively: edges open a much wider spread than centre,
and the F-mount primes wide-open + Viltrox 16/1.8 wide-open were
hitting the §5.2 floor (real values now reveal which is worst).

### 4a. Best aperture per lens — centre + edges (radial_cutoff)

At each lens' centre-best aperture, the corresponding edge cutoffs at
x=0.18 (left) and x=0.82 (right). 2026-01-24 dataset.

Table refreshed under §5.3 metric.

| Lens (FL, best-centre aperture) | centre | x=0.18 (L) | x=0.82 (R) | min edge / centre |
|---|---|---|---|---|
| NIKKOR Z 14-24/2.8 S @ 24, f/4 | **0.326** | 0.220 | 0.251 | 0.67 |
| NIKKOR Z 14-24/2.8 S @ 24, f/5.6 | 0.318 | 0.231 | 0.253 | 0.73 |
| NIKKOR Z 24-120/4 S @ 24, f/4 | 0.314 | 0.256 | 0.249 | 0.79 |
| NIKKOR Z 24-120/4 S @ 24, f/5.6 | 0.314 | 0.251 | 0.197 | 0.63 |
| Viltrox AF 50/2 Z @ 50, f/2.8 | 0.312 | 0.226 | 0.288 | 0.72 |
| NIKKOR Z 14-24/2.8 S @ 24, f/8 | 0.301 | 0.214 | 0.232 | 0.71 |
| Nikon AF Micro 60/2.8D @ 60, f/5.6 | 0.296 | 0.233 | 0.179 | **0.60** |
| Nikon AF Micro 60/2.8D @ 60, f/2.8 | 0.296 | 0.172 | 0.149 | **0.51** |
| Nikon AF-S DX 35/1.8G @ 35, f/5.6 | 0.292 | 0.235 | (NaN) | n/a |
| Nikon AF Micro 60/2.8D @ 60, f/4 | 0.290 | 0.205 | 0.165 | **0.57** |
| Nikon AF Nikkor 50/1.8 N @ 50, f/2.8 | 0.290 | 0.164 | 0.160 | **0.55** |
| NIKKOR Z 24-120/4 S @ 24, f/8 | 0.289 | 0.238 | 0.197 | 0.68 |
| NIKKOR Z 14-24/2.8 S @ 14, f/5.6 | 0.288 | 0.297 | 0.288 | **1.00** |
| Nikon AF-S Nikkor 50/1.8G @ 50, f/2 | 0.288 | 0.212 | 0.136 | **0.47** |
| NIKKOR Z 14-24/2.8 S @ 14, f/4 | 0.287 | 0.296 | 0.257 | 0.90 |

**The pattern still holds under §5.3**: F-mount primes (AF Micro 60/2.8D,
50/1.8 N, AF-S 50/1.8G) drop one edge to 0.13–0.18 — used to read as
the §5.2 metric floor (0.20), now resolves to real values, revealing
which prime corner-collapses worst (50/1.8G at 50 mm f/2 hits 0.136,
min edge / centre ratio 0.47). Z and Viltrox AF lenses hold edges
much closer to centre (ratio ≥ 0.67); Z 14-24 at 14 mm even has
edge ≥ centre, an exceptional flat-field result.

### 4b. Best edge aperture per lens (not the same as centre-best)

If you care about frame-edge sharpness specifically — say a horizon
that spans the whole frame width — stop down past the centre-best
aperture. Best **edge-mean** ((x=0.18 + x=0.82)/2) aperture per lens
where it differs notably from centre-best:

Table refreshed under §5.3 metric:

| Lens | Centre-best | Edge-best | Edge-mean @ best | centre at edge-best |
|---|---|---|---|---|
| AF Nikkor 50/1.8 N @ 50 | f/2.8 (centre 0.290) | **f/11** | 0.275 | 0.247 |
| Viltrox AF 50/2 Z @ 50 | f/2.8 (centre 0.312) | **f/4** | 0.271 | 0.279 |
| NIKKOR Z 24-120/4 S @ 50 | f/4 (centre 0.268) | **f/5.6** | 0.268 | 0.247 |
| AF Nikkor 35/2 @ 35 | f/16 (centre 0.250) | **f/11** | 0.253 | 0.249 |
| NIKKOR Z 24-120/4 S @ 24 | f/5.6 (centre 0.314) | **f/4** | 0.253 | 0.314 |
| AF Micro 60/2.8D @ 60 | f/5.6 (centre 0.296) | **f/11** | 0.246 | 0.257 |
| NIKKOR Z 14-24/2.8 S @ 24 | f/4 (centre 0.326) | **f/5.6** | 0.242 | 0.318 |
| AF-S 50/1.8G @ 50 | f/2 (centre 0.288) | **f/11** | 0.242 | 0.221 |
| Sigma 24/2.8 SWII @ 24 | f/5.6 (centre 0.282) | **f/8** | 0.234 | 0.268 |
| PC-Nikkor 35/2.8 @ 35 | f/4 (centre 0.271) | **f/11** | 0.208 | 0.215 |

The classic rule of thumb "edge optimum is 1–2 stops tighter than
centre optimum" still holds under §5.3 for the F-mount AF-D / G
primes (50/1.8 N centre F2.8 → edge F11, AF Micro 60/2.8D centre
F5.6 → edge F11). The Z and Viltrox AF lenses are tighter — centre
and edge optima are within 1 stop. The §5.2 metric mapped many of
these centre-best apertures onto the same FFT bin, masking which
lens actually peaks where; §5.3 resolves this.

### 4c. Viltrox 16/1.8 Z — strong wide-open asymmetry

The 2026-01-26 dataset includes the Viltrox 16/1.8 in both `AF for every
pic` and `AF once` variants. Edge cutoffs at 16 mm:

Table refreshed under §5.3 metric:

| Aperture | x=0.18 (L) | x=0.82 (R) | L − R asymmetry |
|---|---|---|---|
| f/1.8  | 0.259 | 0.130 | 0.13 |
| f/2    | 0.262 | 0.134 | 0.13 |
| f/2.8  | 0.288 | 0.155 | 0.13 |
| f/4    | 0.290 | 0.243 | 0.05 |
| **f/5.6** | **0.281** | **0.262** | **0.02** |
| f/8    | 0.264 | 0.247 | 0.02 |
| f/11   | 0.244 | 0.245 | 0.00 |

**At f/1.8–f/2.8 the right edge is roughly HALF the left edge
sharpness** — the §5.2 metric showed the right edge stuck at the
0.20 floor; §5.3 reveals it's truly at 0.13–0.16, much worse than
"just below floor" suggested. The asymmetry collapses by f/4 and
the edges are best at f/5.6 (consistent across both `AF every pic`
and `AF once` variants — optical, not an AF issue). Stopping down
the Viltrox 16 for clean corners is a stronger recommendation
under §5.3 than under §5.2.

### 4d. Whose corners hold up wide-open

Wide-open corner cutoff (best of x=0.18 and x=0.82), 2026-01-24:

Table refreshed under §5.3 metric (best of L/R corner per lens at
its widest aperture):

| Lens | Wide-open | Best wide-open corner | Read |
|---|---|---|---|
| Viltrox AF 50/2 Z @ 50 | f/2.8 | 0.288 | **Best wide-open corners** |
| NIKKOR Z 24-120/4 S @ 35–50 | f/4 (wide) | 0.276–0.280 | Solid (wide is f/4 anyway) |
| NIKKOR Z 14-24/2.8 S @ 24 | f/2.8 | 0.265 | Strong, given the f/2.8 wide-open |
| Viltrox AF 14/4 Z @ 14 | f/4 (wide) | 0.257 | Solid (wide is f/4 anyway) |
| Sigma 24/2.8 SWII @ 24 | f/2.8 | 0.238 | Decent |
| NIKKOR Z 14-24/2.8 S @ 14 | f/2.8 | 0.234 | Decent at the wider end |
| AF-S Nikkor 50/1.8G @ 50 | f/1.8 | 0.210 | Useable corners wide-open |
| AF Nikkor 35/2 @ 35 | f/2 | 0.184 | Soft — stop down for corners |
| AF Micro-Nikkor 60/2.8D @ 60 | f/2.8 | 0.172 | Soft — corners need f/5.6 |
| AF Nikkor 50/1.8 N @ 50 | f/1.8 | 0.155 | Very soft corners wide-open |
| PC-Nikkor 35/2.8 @ 35 | f/2.8 | 0.154 | Same, manual prime |
| Nikkor-N.C Auto 24/2.8 @ 24 | f/2.8 | 0.152 | Same, manual prime |
| AF-S DX 35/1.8G @ 35 | f/1.8 | 0.133 | Worst corners wide-open in this group |

Under §5.3 the previously-floored corners (0.20 reading) resolve
into the real 0.13–0.21 range, revealing the ordering: the Z lenses
+ Viltrox 50/2 stay in the 0.25–0.29 range wide-open, the F-mount
AF-D primes sit at 0.15–0.21, and the manual primes are at 0.15.
The "stop down 1 stop for usable corners" rule of thumb holds; the
required stop-down depends on which group your lens is in.

The Z and Viltrox autofocus lenses have noticeably better wide-open
corners than the legacy F-mount Nikon primes. The F-mount primes
genuinely **do** need stopping down (1–2 stops) for usable corners.

### 4e. Honest centre-only summary

At centre (x=0.50) the lens differences are real but small —
~0.24 to 0.30 cy/sensor-px under the §5.3 metric (was 0.30–0.35
under §5.2 where FFT-bin quantisation compressed them further; §5.3
sub-bin interp + smoothing resolves that). The interesting story is
still at the edges.

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

## 4f. 2026-02-07/20 mm — Z 20/1.8 group

This day was specifically a 20 mm shootout: Z 20/1.8 S vs Z 14-24/2.8 S
(at 20 mm) vs AF Nikkor 20/2.8 (F-mount, non-D) vs Viltrox AF 20/2.8 Z
Air. Same physical location as 2026-01-24/26 but with the framing
pushed lower → centre is grass-dominated rather than stairs-dominated
(see §3 scene atlas).

Centre cutoff (radial_cutoff) at f/4, top of each lens / ISO variant:

| Lens (best ISO/aperture for centre) | top centre cy/sensor-px |
|---|---|
| NIKKOR Z 14-24/2.8 S | 0.316 (f/4, ISO 100) |
| Viltrox AF 20/2.8 Z Air | 0.309 (f/4, ISO 100) |
| NIKKOR Z 20mm f/1.8 S | 0.301 (f/4, ISO 400) |
| Nikon AF Nikkor 20/2.8 (F-mount, non-D) | 0.254 (f/4, ISO 100) |

**Original (§5.2 metric) reading**. The grass-dominated centre on
2026-02-07 means the §5.2 consensus tile picker locks onto grass
texture instead of the structural stairs/handrail it finds on
2026-01-24. The visual finding "Z 20/1.8 best" did **not** reproduce
in the centre-only `radial_cutoff` ranking, which had Z 14-24 leading
by a tiny margin (0.316 vs 0.301 — within FFT-bin quantization).

**§5.1 CV-edge MTF50 (mtf50_known_edge) restores the visual ordering.**
Re-running the dataset through the CV-discovered edge picker (which
lands on stair-side diagonals, paver boundaries, and other
structural content rather than grass) gives this median-across-
edges ranking per (lens, FL, best aperture):

| Lens (best aperture) | mtf50_known_edge |
|---|---|
| **NIKKOR Z 20mm f/1.8 S @ f/5.6** | **0.476** |
| NIKKOR Z 14-24/2.8 S @ 20mm f/8 | 0.427 |
| Nikon AF Nikkor 20/2.8 @ f/8 | 0.407 |
| Viltrox AF 20/2.8 Z Air @ f/11 | 0.379 |

The Z 20/1.8 S leads by 12 % MTF50 over the Z 14-24 at the same
focal length — matching the user's visual judgement that the 1.8
prime delivered better corners than the zoom at 20 mm on this scene.
The CV-edge approach works because it doesn't depend on the centre
tile having structural content; it directly measures the long
structural edges wherever they happen to be in the frame.

**AF Nikkor 20/2.8 underperforms by 20 %** vs the Z lenses at centre
under the §5.2 metric. Under the §5.1 CV-edge metric the AF 20/2.8
sits between the Z 20/1.8 S and the Viltrox 20/2.8 Z. Matches the
visual reading "edges very fuzzy until f/5.6".

The mtf50_slanted_edge (§4.1 auto-detect) produced more usable
output on this dataset than on the others (4 % median CV vs 34–38 %
on 2026-01-24/26) — but the §5.1 CV-edge variant is more
discriminating still because it picks the edges deliberately.

## 5. Movement-detection findings

The cross-replicate consensus picker flagged cells where the
per-replicate gradient-max positions disagreed by > 2 search-steps,
indicating moving content (cyclist / pedestrian).

| Date | n cells flagged | Affected lenses | Affected positions |
|---|---|---|---|
| 2026-01-24 | **39** | mostly Z 14-24 @ 14 / 24 mm | concentrated at x = 0.34 and x = 0.50 (the path / stairs band) |
| 2026-01-26 | **5** | scattered (Z 14-24 AF-every-pic, Z 24-120 @ 60 mm, AF 50/1.8 N) | mixed |
| 2026-02-07/20 mm | small (<5) | n/a | n/a |
| 2025-09-10 (D7200) | small | n/a | n/a |
| 2025-09-11 (D7200) | small | n/a | n/a |

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
   fully lighting-invariant. The §5.2 FFT-bin quantisation that
   compressed centre values into a narrow ~0.29–0.35 cy/sensor-px
   band is resolved by the §5.3 changes (sub-bin interp + smoothing
   + lower ref-band); new dynamic range is ~0.24–0.30 at centre with
   real ordering preserved.
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
5. **Best wide-angle / standard lenses on this scene** (centre values
   under §5.3 — all ~12 % lower than pre-§5.3 figures):
   - Best overall: NIKKOR Z 14-24mm f/2.8 S @ 24 mm f/4 (0.326 cy/px;
     was 0.348)
   - Best 24 mm zoom: NIKKOR Z 24-120/4 S @ f/5.6 (0.314 cy/px; this
     moves above Viltrox 50/2 under §5.3, was tied with Z 14-24 before)
   - Best 50 mm: Viltrox AF 50/2 Z @ f/2.8 (0.312 cy/px; was 0.336)
   - Best 60 mm: AF Micro 60/2.8D @ f/5.6 (0.296 cy/px; was 0.324)
   - Best 35 mm: AF-S DX 35/1.8G @ f/5.6 (0.292 cy/px; was 0.324)
6. **Edges open up a wider spread than the centre cluster suggests.**
   Many F-mount primes (50/1.8 N, 50/1.8G, 60/2.8D, PC-Nikkor 35/2.8)
   previously read the right edge as "stuck at 0.20 cy/px floor" at
   their centre-best aperture. Under §5.3 those edges resolve into
   real values 0.13–0.18 cy/px range — the ranking holds (need 1
   stop more for usable corners), but the spread is now genuinely
   measured rather than collapsed onto a floor. The Z 14-24, Viltrox
   AF 50/2 Z, and Viltrox AF 14/4 Z still hold edges close to centre
   (0.25–0.30 cy/px). The Viltrox 16/1.8 right-edge asymmetry
   wide-open through f/2.8 is still visible — clean from f/4 onward,
   best at f/5.6.

## 6.5. D7200 (DX, older, separate section)

**Caveat box.** D7200 data is presented separately because:
1. Different camera (DX, 6000 × 4000, 3.91 µm pixel pitch). Cy/sensor-px
   values are NOT directly comparable to Z7's 4.35 µm pitch.
2. Older test methodology — some lenses lack distance encoders (see slug
   pattern table in §1) and per-session focus may have been less strict.
3. 2025-09-11 has multiple sub-sessions with **different focus distances**.
   The DX 18-70 sub-session was at 1–2 m (below Focal's 50× FL minimum
   for these short FLs) — labelled as such in §6.5b. Sigma 50-150/2.8 II
   was at 22.39 m on the same day. Both are kept in the analysis, just
   labelled by distance class.

### 6.5a. 2025-09-10 — D7200 wide / ultra-wide lineup (237 configs)

Scene: same stairs-and-grass scene as the 2026 Z7 dates (the photographer
re-uses this physical location across years). DX framing → wider FOV per
mm.

Top centre cutoff per lens (radial_cutoff, cy/sensor-px) under §5.3:

| Lens (best FL, aperture) | centre cy/sensor-px |
|---|---|
| Tokina 11-20/2.8 PRO DX @ 18 mm, f/8 | **0.231** |
| Sigma 10-20/4-5.6 EX DC HSM @ 17 mm, f/8 | 0.181 |
| AF-S DX 18-70/3.5-4.5G @ 20 mm, f/11 | 0.173 |
| AF DX Fisheye 10.5/2.8G @ 10.5 mm, f/4 | 0.139 |
| AF-S DX 16-85/3.5-5.6G @ 22 mm, f/5.6 | 0.108 |
| AF-S DX 16-80/2.8-4E @ 20 mm, f/5.6 | 0.106 |
| Sigma 18-35/1.8 DC HSM @ 22 mm, f/2.8 | 0.102 |

Under §5.3 the D7200 wide values are **substantially lower** than
the pre-§5.3 prose stated (which had them at ~0.22–0.30). That prose
was reading the §5.2 metric floor — under §5.3 the D7200 + OLPF +
JPEG-pipeline combo on this stairs scene is genuinely soft, with the
Tokina 11-20 PRO DX clearly leading and the AF-S DX kit zooms +
Sigma 18-35 in a tighter 0.10–0.11 cluster at centre. Cross-camera
ratio (§5.5) of ~1.35× brings these closer to the Z7 readings but
the Sigma 18-35 still trails the Z 14-24 substantially.

Multiply D7200 numbers by ~1.35 (cy/sensor-px) or ~1.21 (cy/mm-sensor)
when bridging to Z7 readings — see
[`CROSS_CAMERA_BRIDGE_RESULTS.md`](CROSS_CAMERA_BRIDGE_RESULTS.md).

(See `per_measurement.csv` for full table.)

**Algorithm-comparison observations on 2025-09-10:**
- `radial_cutoff` 0 % median CV, 3 % p90 — high stability.
- `mtf50_slanted_edge` 15 % median CV, but only 615 / 1185 cells produced
  → 48 % NaN. Same issue as 2026-01-24: lots of grass/sky tiles without
  strong edges.
- `vol`/`brenner` 4 % median CV, normal gradient behaviour.
- Cross-algorithm Spearman: radial ↔ vol only 0.43 (lower than Z7
  datasets) — likely because the D7200 sensor + older lenses produce
  more noise that affects vol/brenner directly but not the spectrum-
  normalised radial_cutoff.

### 6.5b. 2025-09-11 — D7200 midrange, distance-class audit

Per-(lens, FL) audit of EXIF FocusDistance plus temporally-nearest
encoder-equipped frame's distance for non-encoder lenses (the tripod
was not moved between lenses in the same sub-session, so nearest-time
distance is a valid stand-in). Full audit:
`../scripts/audit_nef_distance_out/nef_distances_2025-09-11.md`.

Classification by Reikan Focal's two-tier rule: minimum subject distance
is **20× FL for ≥ 300 mm FL** and **50× FL for < 300 mm FL** (the curve
stabilises earlier for long teles). Closer-distance readings aren't
invalid — they measure the lens at a different distance regime, fine
for that regime but not directly comparable to infinity-class readings
of the same lens on another day.

**Distance-class distribution (40 cells):**

| Class | n cells |
|---|---|
| below Focal min (< 50× FL for these < 300 mm lenses) | 5 |
| meets Focal min, < 100× FL | 1 |
| infinity-class (100–300× FL) | 25 |
| well past infinity (> 300× FL) | 9 |

**Below Focal min (< 50× FL) — close-distance sub-session:**

| Lens | FL | Distance | dist/FL |
|---|---|---|---|
| AF-S DX Nikkor 35mm f/1.8G | 35 mm | 0.79 m | 23× |
| AF-S DX Zoom-Nikkor 18-70/3.5-4.5G | 24 mm | 1.00 m | 42× |
| AF-S DX Zoom-Nikkor 18-70/3.5-4.5G | 35 mm | 1.68 m | 48× |
| AF-S DX Zoom-Nikkor 18-70/3.5-4.5G | 50 mm | 1.68 m | 34× |
| AF-S DX Zoom-Nikkor 18-70/3.5-4.5G | 55 mm | 2.37 m | 43× |

The DX 18-70 (and DX 35/1.8G) were shot at close-distance for their
focal lengths. Below Focal's 50× FL minimum but still legitimate
close-MTF measurements; just not cross-comparable with the same
lenses' infinity-class readings on 2025-09-10.

**Meets Focal min, < 100× FL:**

| Lens | FL | Distance | dist/FL |
|---|---|---|---|
| AF-S DX Zoom-Nikkor 18-70/3.5-4.5G | 27 mm | 1.41 m | 52× |

**Infinity-class and beyond (≥ 100× FL):** 34 cells — almost all
encoder-equipped readings of AF-S DX 16-80, AF-S DX VR 16-85 (24-55mm,
yes including the 24mm at 2.82m = 118× FL), AF-S DX 17-55 (24/35/50/55mm
and 28mm where 2.99m / 28mm = 107×), AF-S Nikkor 50/1.8G, Sigma
18-35/1.8 (4.22m = 121-176× FL across its zoom range), Sigma 50-100/1.8,
Sigma 50-150/2.8 series, plus the time-inferred distances for AIS Micro 55,
Nikkor-N.C 24, PC-Nikkor 35, Sigma 24/2.8 SWM, AF Nikkor 35/2 (non-D),
AF Nikkor 50/1.8 (non-D).

**Practical takeaways:**

- The 2025-09-11 dataset is mostly infinity-class. Only 5 cells (the
  DX 18-70 + DX 35/1.8G close-distance sub-session) sit below Focal's
  50× FL minimum.
- Earlier framing that the Sigma 18-35/1.8 at 4.22 m was invalid was
  wrong: at 24 mm = 176× FL and at 35 mm = 121× FL, both well
  inside infinity-class.
- The Sigma 50-150/2.8 EX APO DC HSM II 1001387 vs 1012221 readings
  14.13 vs 22.39 m at 55 mm (both infinity-class) probably reflect
  per-copy focus variation or a brief tripod nudge between two-copy
  comparison shots.

### 6.5c. D7200 wide-angle summary

The D7200 wide-angle lineup samples both modern S-mount class lenses
(Sigma 18-35/1.8, AF-S DX 16-80) and older F-mount kit zooms.

Under §5.3 the centre cy/sensor-px values land in a 0.10–0.23 range
on the 2025-09-10 wide dataset and 0.13–0.23 on 2025-09-11 midrange
— substantially lower than the pre-§5.3 0.22–0.30 readings, which
were at the §5.2 metric floor. The D7200 sensor + OLPF + JPEG-pipeline
combo is genuinely soft on this stairs scene at these focal lengths,
and **the Tokina 11-20 PRO DX (0.231 at 18 mm f/8) tops the wide
lineup** rather than the Sigma 18-35/1.8 — the Sigma trails because
on 2025-09-10 its best reads are at the wide end (~0.10 at 22 mm
f/2.8) where wide-open softness dominates. The Sigma's mid range
(35 mm f/4 reads 0.191 on 2025-09-11) is more competitive.

The legacy AF non-D primes (AF 35/2 at 0.187, AF 50/1.8 N at 0.159
on 2025-09-11) and the manual focus Nikkor-N.C / Sigma 24/2.8
Super Wide II Macro (0.16 / 0.13) sit below the modern lenses,
consistent with the Z7-side pattern. To compare directly against
the Z7 datasets, apply the **§5.5 cross-camera bridge factor of
~1.35×** (cy/sensor-px) — see
[`CROSS_CAMERA_BRIDGE_RESULTS.md`](CROSS_CAMERA_BRIDGE_RESULTS.md).

## 7. Limitations and follow-ups

- ~~**`radial_cutoff` resolution is FFT-bin-limited.** Three lenses
  reporting identical 0.328 cy/sensor-px may actually differ…~~
  **Resolved 2026-06 by §5.2 + §5.3.** Sub-bin linear interpolation
  at the threshold crossing + smoothing + lower ref-band: see
  `RADIAL_CUTOFF_SUBBIN_RESULTS.md` and `RADIAL_CUTOFF_REFBAND_RESULTS.md`.
  Centre cluster expanded from ~38 distinct values to 442 across the
  wide2026_01_24 sweep with Spearman 0.97 vs the prior ranking.
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
| `../scripts/poc_longdist_algorithms.py` | Algorithm-comparison script (4 algorithms + consensus tile + lighting probe) |
| `../scripts/audit_nef_distance.py` | EXIF FocusDistance audit script (NEFs preferred, JPEG fallback). Used for the §6.5b validity check on 2025-09-11. |
| `../scripts/poc_longdist_algorithms_out/wide2026_01_24/` | Per-measurement CSV + algorithms_summary.md + correlation_matrices.png |
| `../scripts/poc_longdist_algorithms_out/wide2026_01_26/` | Same for 2026-01-26 |
| `../scripts/poc_longdist_algorithms_out/wide2026_02_07/` | Same for 2026-02-07/20 mm |
| `../scripts/poc_longdist_algorithms_out/wide2025_09_10/` | Same for D7200 2025-09-10 |
| `../scripts/poc_longdist_algorithms_out/mid2025_09_11/` | Same for D7200 2025-09-11 (mixed distance classes — see §6.5b) |
| `../scripts/audit_nef_distance_out/nef_distances_2025-09-11.{csv,md}` | Per-(lens, FL) distance audit for the validity check |

Per-measurement CSV columns: date, lens_dir, focal_mm, aperture,
position_frac, algorithm, top, median, min, top_vs_median, range_pct,
n_replicates, consensus_y, consensus_x, movement_flag.
