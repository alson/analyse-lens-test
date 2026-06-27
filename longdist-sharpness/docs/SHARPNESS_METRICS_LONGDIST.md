# Cross-Lens Sharpness Metrics — Long-Distance Natural-Target Tests

> Companion to [`SHARPNESS_METRICS.md`](SHARPNESS_METRICS.md), which covers
> the macro / silicon-wafer rig. The long-distance rig uses natural
> targets and *no* focus-bracketing rail — depth variation is built into
> the scene instead.
>
> **2026-06 metric updates** (see [`LONGDIST_HANDOVER.md`](LONGDIST_HANDOVER.md)
> §5.1–§5.5 for the full list):
> - `radial_cutoff` now uses `REF_BAND = (0.01, 0.10)` (was 0.20),
>   smooths the normalised spectrum (σ=2 bins), and locates the
>   *last* threshold crossing with sub-bin linear interpolation. See
>   [`RADIAL_CUTOFF_SUBBIN_RESULTS.md`](RADIAL_CUTOFF_SUBBIN_RESULTS.md)
>   and [`RADIAL_CUTOFF_REFBAND_RESULTS.md`](RADIAL_CUTOFF_REFBAND_RESULTS.md).
> - New algorithm `mtf50_known_edge` reports MTF50, MTF@Nyquist, and
>   MTF10 from CV-discovered Hough edges on a sharp reference. See
>   [`MTF50_KNOWN_EDGE_RESULTS.md`](MTF50_KNOWN_EDGE_RESULTS.md).
> - D7200 ↔ Z7 cross-camera bridge factor measured: ~1.35× in
>   cy/sensor-px. See
>   [`CROSS_CAMERA_BRIDGE_RESULTS.md`](CROSS_CAMERA_BRIDGE_RESULTS.md).

## The two long-distance test designs

| Date(s) | Lenses | Scene | Depth axis |
|---|---|---|---|
| **2026-01-18** | 300mm + TCs | Distant hedge / twigs | (none — planar at infinity) |
| **2026-01-24, 2026-01-26** | 14-50mm primes & zooms | Sloped concrete stairs + grass embankment + sky | Vertical pixel position → subject distance, via slope geometry |

The 14-50mm sloped-scene test is functionally a **45° focus-chart test
in the wild**: by including subjects at a range of distances in one
frame, a single shot at one aperture captures the whole defocus
behaviour of the lens. The 300mm test is closer in spirit to a planar
subject, but with **3D vegetation structure** — branches at different
distances within the same frame band.

`2026-01-26` adds an AF-reproducibility variant: the
`... AF for every pic` folders re-trigger AF between replicates, so
replicate-level variation reflects AF jitter, not just shot noise.

---

## Conceptual shifts from the macro pipeline

### 1. Per-position sharpness, not a single scalar

On a sloped scene, the in-focus band lives at one vertical position in
the crop. A "less sharp" lens may simply have its focus on a different
stair than yours expected, not be optically worse. So the per-crop
output is a **sharpness-vs-position curve**, summarised as:

| Output | Meaning |
|---|---|
| Peak height | Lens resolution at the focal plane (the comparison number) |
| Peak position (vertical px) | Where it focused → focus-accuracy / AF error |
| FWHM along slope | Effective depth-of-field on the slope at that aperture |

This is the canonical 45°-ruler / Datacolor SpyderLensCal protocol
applied to the stairs.

### 2. Replicates measure AF/focus repeatability, not just shot noise

In the macro test, replicates within a rail step share an identical
optical configuration; "pick the sharpest by file size" is exactly
right. In the long-distance tests, especially the `AF for every pic`
folders, **replicates re-trigger AF** and measure whether the lens
lands focus consistently. Per-replicate statistics:

- Variance of **peak position** across replicates → AF repeatability.
- Variance of **peak height** at peak position → severity of AF misses.
- Difference between `AF for every pic` and `AF once at f_1.8` distributions
  → isolates AF jitter from lens + DoF baseline.

### 3. Slice at analysis time, not at capture time

The macro pipeline pre-crops because the rail-coverage analyser only
needs nine fixed positions. For the slope tests, the **slice layout is
the thing under investigation** (field-position effects, field
curvature), so it shouldn't be baked into the pre-processed files.

Keep capture-time crops as they are for manual visual comparison in
`results.html`. For automated analysis, operate on the full-frame
exports and slice in software.

### 4. Vertical position carries depth information

For sloped scenes, **don't sub-crop along the slope axis** (don't
discard the top or bottom of the frame). The depth signal lives there.
Use full sensor height per slice.

---

## Vertical-slice layout

Tall slices, full sensor height, N slices wide:

```
┌──┬──┬──┬──┬──┬──┬──┬──┐
│  │  │  │  │  │  │  │  │   each slice ~1032 px wide (FX)
│  │  │  │  │  │  │  │  │   full sensor height (~5504 px on Z7)
│ 0│ 1│ 2│ 3│ 4│ 5│ 6│ 7│
│  │  │  │  │  │  │  │  │
└──┴──┴──┴──┴──┴──┴──┴──┘
  ←─ field position →
  ↑
  within each slice: vertical pixel position = subject distance
```

- **FX (45 MP Z7, 8256 × 5504): 8 slices.** Each ~1032 px wide.
- **DX crop (5408 × 3600): 5 slices.** Each ~1080 px wide — same
  *physical slice width on the sensor* as FX, so the field-position
  interpretation is consistent across formats. (Rule: ~1000 px slice
  width, regardless of crop mode.)

Across slices, position is the field-position axis (centre vs. corner
of the lens's image circle). Plot against **normalised image height**
(0 at frame centre, 1 at corner) to match Imatest/DXOMark convention.

This layout measures field curvature for free: `peak_position(slice)`
varying systematically across slices = the focal plane is not flat
across the field.

---

## What the slices actually contain (24mm / 35mm / 50mm sloped-scene)

Reviewed F8 frames from `2026-01-24` for each focal length, divided
into 8 vertical slices.

| Slice | 24mm | 35mm | 50mm |
|---|---|---|---|
| **0** (far left) | grass + sky + asphalt | grass + sky + asphalt | left lamp post + handrail diagonal |
| **1** | left lamp post (thin line) | left lamp post (thin line) | grass + handrail diagonal |
| **2** | handrail diagonal | handrail diagonal | handrail diagonal + stair side |
| **3** | stair/grass boundary + handrail | stair/grass boundary + handrail post | stairway side + handrail post |
| **4** | central lamp post + stair edges | central lamp post + stair edges | central lamp post + stair edges |
| **5** | white arch + lamp post | white arch + handrail | arch + lamp post + handrail |
| **6** | right-mid lamp post | handrail vertical post | white arch + stair side |
| **7** (far right) | grass + sky + asphalt | grass + sky + asphalt | grass + slight stair side |

Plus features that span essentially every slice at all three FLs:

- **Wall-top horizon line** — long, slightly slanted (~3-5° off
  horizontal from natural framing). True step-edge, ISO-12233-usable.
- **Asphalt/pavement boundary at bottom of frame** — long, slightly
  slanted. True step-edge.
- **Stair tread edges** (slices 3-6) — many short perspective-slanted
  edges; MTF Mapper processes each independently.

### Thin line vs. true edge

Most dominant "verticals" in the corner slices are **lamp posts and
handrails** — thin lines against sky, not step-edges. Implications:

- Standard ISO 12233 slanted-edge expects an edge between two large
  uniform regions and processes the ESF. A thin line is a *line spread
  function* (LSF) — different code path: FFT of the LSF *is* the MTF
  directly, no derivative step.
- MTF Mapper's auto-detection finds edges, not lines. For thin-line
  targets, either pre-process (subtract sky background, treat the line
  profile as LSF) or run a separate line-MTF tool.
- True step-edge targets — wall horizon, asphalt boundary, stair
  treads, stairway/grass boundary — work in MTF Mapper out of the box.

### Coverage verdict

- **All slices at all three focal lengths have at least one usable
  edge** — but at 24mm and 35mm, the *corner* slices (0 and 7) rely
  on the wall horizon + asphalt boundary (slightly-slanted near-
  horizontal edges) rather than any vertical, and you'd want to confirm
  the algorithm picks those up before committing.
- **Optional capture-side improvement**: tilt the camera 3-5° on the
  tripod for these tests. Converts the "lucky natural slant" of the
  wall horizon and asphalt edge into a guaranteed slant, giving usable
  ISO-12233 edges in every slice without depending on lamp posts.

---

## Per-slice metric — planar vs. 3D content

### Planar slope (14-50mm stair tests): 1D sharpness-vs-y curve

For each slice:

1. Slide a sub-window vertically (e.g. 100-200 px tall, 50% overlap).
2. Compute local sharpness per window — preferred metrics from the
   macro doc that don't depend on edge orientation:
   - Radial power-spectrum cutoff with parametric `α + MTF` fit
     (§2 of macro doc), or
   - Akamine 2024 normalised gradient-decay (§4).
3. Output: a 1D curve `sharpness(y)` per slice.
4. Fit a peak → `(peak_height, peak_y, FWHM_y)`.

Plot peak_height across slices for centre-to-corner sharpness; plot
peak_y across slices for **field curvature**.

### 3D vegetation (300mm hedge tests, plant-on-slope tests): 2D sliding window

3D plant structure intersects the focal plane wherever it happens to —
there's no smooth 1D sharpness-vs-y ridge. Within a single slice, the
in-focus point at one X may be at y=2000, at another X may be at
y=2800. Use a 2D sharpness map and take percentile statistics.

For each slice:

1. Slide a small window (e.g. 128×128 px, 50% overlap) across **both**
   axes.
2. Compute local sharpness per window → 2D map.
3. Output statistics:
   - **95th-percentile sharpness** = "what the lens can resolve when
     it does land focus on a branch in this slice". The
     comparison-across-lenses number.
   - **Median sharpness** = proxy for fraction of slice with in-focus
     content.
   - **Area above threshold** (e.g. above 70% of peak) = DoF coverage
     in pixels — quantifies how much of the 3D plant volume falls
     inside the DoF.

### Decision rule

Automatic fallback: fit the 1D sharpness-vs-y curve. If the fit has
poor R² (multi-modal, flat, or noise-dominated), fall back to the 2D
treatment. The 2D approach also handles the planar case gracefully —
the sharpness map collapses to a horizontal ridge and the 95th
percentile is dominated by the ridge.

So in practice, one 2D analysis path can cover everything, with the
1D curve as an extracted projection where it's clean.

---

## Slanted-edge MTF strategy

Where edges exist (most slices at most FLs — see coverage table above),
MTF Mapper on `pick.jpg` gives per-edge MTF50 values tagged with
`(x, y)` position. Aggregate within each slice:

- Median MTF50 over edges in the slice → comparable across lenses.
- Edges tagged with their y-position give the sharpness-vs-y curve
  directly, no separate windowing step.

This is the **bonus signal where available**; the spectrum-based
metrics (§2/§4 of macro doc) are the **universal fallback** that
applies even on edgeless texture (grass, twigs).

---

## Implementation summary

| Stage | Current | Proposed |
|---|---|---|
| Capture-time crops | 3 positions (centre, left-edge, right-edge) ~ 500×500 | Keep as-is for manual `results.html` browsing |
| Analysis-time slicing | (none — uses the capture crops) | 8 slices on FX, 5 on DX, full sensor height, operating on the full-frame export |
| Per-slice statistic (planar) | JPEG file size of best replicate | `(peak_height, peak_y, FWHM_y)` from 1D sharpness curve |
| Per-slice statistic (3D vegetation) | JPEG file size of best replicate | `(p95, median, area_above_threshold)` from 2D sharpness map |
| Replicate handling | Pick sharpest by file size | Same for `AF once`; for `AF for every pic`, compute peak-y variance across replicates |
| Field curvature | (not measured) | `peak_y(slice_index)` plotted across slices |
| Cross-format consistency | (separate logic for DX) | Same ~1000 px slice width on the sensor for FX and DX |

### Optional capture-side tweak

Tilt the camera 3-5° on the tripod when shooting the sloped-stair
scene. Guarantees ISO-12233-usable slant on the wall horizon and the
asphalt boundary, removing the dependence on lamp posts for edge MTF
in corner slices.

---

## Cross-reference

- [`SHARPNESS_METRICS.md`](SHARPNESS_METRICS.md) — macro / silicon-wafer
  rig. Section numbers (§1-§9) referenced above point there.
- `ANALYSIS_NOTES.md` — empirical findings from the macro test sessions
  (rail-coverage analyser; bell-curve detection).
- `rail-coverage/` — implementation of the macro analyser.

### Results documents

- [`LONGDIST_TELE_RESULTS.md`](LONGDIST_TELE_RESULTS.md) — Z7 telephoto
  cross-date (2026-01-18 / 28 / 30 + 2026-02-07) and D7200 telephoto
  (2025-07-09, 2025-09-06). TC vs cropping analysis, sharpest-of-ISO +
  replicate-spread (top/median/min) reporting, separate D7200 section.
- [`WIDEANGLE_RESULTS.md`](WIDEANGLE_RESULTS.md) — Z7 wide / standard
  (2026-01-24 / 26 / 2026-02-07-20mm) and D7200 wide / midrange
  (2025-09-10, 2025-09-11). Four-algorithm comparison (radial-cutoff,
  slanted-edge MTF50, variance-of-Laplacian, Brenner) with stability,
  agreement, and lighting-robustness assessment; cross-replicate
  consensus tile picker for cyclist / pedestrian rejection. Separate
  D7200 section with camera-pixel-pitch caveat.
