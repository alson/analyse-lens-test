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
> 0.30–0.35 "centre cluster" note (FFT-bin quantisation, §3 and §5.4)
> is now resolved by the new metric. The per_measurement.csv files
> under `poc_longdist_algorithms_out/wide*/` and `mid2025_09_11/`
> reflect §5.3; the prose in this doc still cites pre-§5.3 numbers
> and has not been hand-replaced.

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

**Caveat — different scene content vs 2026-01-24/26**. The grass-
dominated centre on 2026-02-07 means the consensus tile picker locks
onto grass texture instead of the structural stairs/handrail it
finds on 2026-01-24. The visual finding "Z 20/1.8 best, good even
in edges; Z 14-24 slightly less sharp" is **not** reproduced by the
centre-only ranking here, where Z 14-24 leads by a tiny margin
(0.316 vs 0.301 — within FFT-bin quantization). Field-edge data
would be more discriminating (the Z 20/1.8's flat-field reputation
shows in corner sharpness, not centre).

**AF Nikkor 20/2.8 underperforms by 20 %** vs the Z lenses at centre.
Matches the visual reading "edges very fuzzy until f/5.6" — the older
non-D AF lens is consistent with the other legacy F-mount primes in
the 2026-01-24 dataset.

The mtf50_slanted_edge algorithm produced more usable output on this
dataset (4 % median CV vs 34–38 % on 2026-01-24/26 and rank-correlation
with radial_cutoff jumps to 0.55 from 0.10). Even so, the centre
ranking is too compressed for the metric to discriminate confidently.

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

Top centre cutoff per lens (radial_cutoff, cy/sensor-px), all at the
lens's best centre aperture:

| Lens (best FL, aperture) | centre cy/sensor-px |
|---|---|
| Sigma 18-35/1.8 DC HSM @ 24 / 35 mm, f/5.6 | ~0.30 |
| AF-S DX 17-55/2.8G @ 35 mm, f/5.6 | ~0.28–0.30 |
| AF-S DX Nikkor 16-80/2.8-4E @ 24 mm, f/5.6 | ~0.28 |
| Tokina 11-20/2.8 PRO DX @ 14 mm, f/8 | ~0.26–0.28 |
| Sigma 10-20/4-5.6 @ 14-17 mm, f/8 | ~0.24–0.26 |
| AF DX Fisheye 10.5/2.8G @ 10.5 mm, f/8 | ~0.24 |
| AF Nikkor 20/2.8 (non-D) @ 20 mm, f/8 | ~0.24 (no-D — visual edges very fuzzy until f/5.6 per user) |
| AF-S DX 16-85/3.5-5.6G @ 24 mm, f/8 | ~0.24 |
| Nikkor-N.C 24/2.8 (manual focus, no encoder) @ 24 mm, f/8 | ~0.22 |
| Sigma 24/2.8 Super Wide II Macro (non-D, non-AF) @ 24 mm, f/8 | ~0.22 |

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
(Sigma 18-35/1.8, AF-S DX 16-80) and older F-mount kit zooms. The
modern Sigma 18-35 takes the top spot on the D7200 the same way the
Z 14-24 does on the Z7 — modern designs hold edges much better than
the older kit. The AF-S DX 17-55/2.8G is also competitive.

The legacy AF non-D primes (AF 20/2.8, AF 50/1.8 N) and the manual
focus Nikkor-N.C / Sigma 24/2.8 Super Wide II Macro all sit at 0.22–
0.24 cy/sensor-px centre — slightly below the modern lenses, consistent
with the Z7-side pattern.

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
