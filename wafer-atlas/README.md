# wafer-atlas

A coordinate system + feature catalogue for the test wafer used in
`analyse-lens-test`. Built 2026-05-18.

## What this is

The test wafer is a fragment with a **4×4 super-cell** repeat — 16
distinct die types tiling the wafer. Within a super-cell, one column
type is wider (~542 px vs ~454 px in the overview photo) and one row
type is taller (~546 px vs ~452 px). See
[`MEMORY.md`](../../run-lens-test/.claude/memory) under
`wafer_4x4_supercell_irregular_pitch.md` for the implications of this
on metrology.

The atlas knows:

1. **The wafer's geometric structure** — per-`(col mod 4, row mod 4)`
   die pitches in pixels-of-the-overview-photo, plus the rotation +
   origin needed to map atlas-coords ↔ overview-photo pixels.
2. **What each die type looks like** — user-provided descriptions
   + CV-derived bounding boxes of bond-pad regions, isolated bars,
   and "experimental" structures.
3. **Per-feature FFT pitch signatures** for the pad-grid features
   (so a sharpness measurement at low M can target a known pad
   periodicity instead of guessing).
4. **The fragment outline** (`fragment_outline`, schema v2) — per
   physical die cell (col 0..10 × row A..F) wafer coverage: 1 = whole,
   0 = absent (off-wafer), in between = jagged/partial. This is the
   "whole-vs-jagged" inventory, used to disambiguate the absolute
   column offset in autonomous registration. Built by
   `scripts/build_fragment_map.py` from the whole-fragment sweep1.

The atlas's primary use: **register any test sweep against the wafer
once** (i.e. solve a per-sweep affine `(θ, x0, y0, scale)`), then
look up atlas features in that sweep's pixel coordinates for
measurement-time CV.

## Coordinate system

- **Columns** `c0..c10` left-to-right (c0/c10 are jagged wafer edges
  with partial dies; c1-c9 are full-die columns).
- **Rows** `rA..rF` bottom-to-top in the photo (rA/rF jagged).
- Each die referenced as `<col><row>`, e.g. `4D`, `3B`, `5E`.
- **Within-die `(u, v)`** ∈ [0, 1]² with `(0, 0)` = die bottom-left,
  `(1, 1)` = die top-right (wafer-native orientation, with text
  reading "up").
- **Super-cell type** indexed as `(col mod 4, row mod 4)`. Each of
  the 16 types appears at multiple positions on the wafer.

## Pipeline (one-time atlas build)

```sh
# 1. Solve the die grid on the f/8 overview photo from 3+ user anchors.
direnv exec . uv run python scripts/grid_supercell_refined.py
#   → out/grid_supercell_refined.png  (overlay for sign-off)

# 2. Register the higher-mag f/8 + 35mm extension photo (step_0129_b).
direnv exec . uv run python scripts/register_0129.py
#   → out/0129/grid_overlay.png + grid_params.json

# 3. User paints features on 0129 photo as 0129_painted2.png:
#      magenta = bond-pad regions
#      yellow  = slanted-edge candidates (e.g. 4D bar)
#      cyan    = experimental "try this" regions

# 4. Parse painted regions into per-feature bboxes + FFT pitches.
direnv exec . uv run python scripts/parse_painted.py
#   → out/0129/atlas_0129_painted.json

# 5. Consolidate into canonical atlas.json.
direnv exec . uv run python scripts/consolidate_atlas.py
#   → atlas.json
```

## Pipeline (per-sweep registration)

### Anchor-based (production — accurate)

```sh
# User provides 3+ scribe-intersection anchors via GIMP for each sweep.
# Script edits anchors list in anchor_fit_sweep.py, then:
direnv exec . uv run python scripts/anchor_fit_sweep.py
#   → out/sweep_anchors/<sweep_label>.png (overlay)
#   → out/sweep_anchors/anchor_fit_params.json
```

RMSE 2-8 px across 4 test sweeps spanning M=0.385 to M=2.0. The
required 3 anchors take ~30 sec of GIMP work per sweep.

### Autonomous (work-in-progress — TODO #14)

Two methods attempted:

- `scripts/register_method_template.py` — multi-scale template
  matching of whole-die templates (4B, 2B, 4C). Works on sweep 1
  (RMSE 13 px) but degrades at high M due to score thresholds.
- `scripts/register_method_morphological.py` — Sobel + long-line
  morphological opening (ported from `archive-2026-05/
  measure_wafer_squares`) + super-cell phase match. Recovers
  scale, rotation, super-cell pattern correctly, but has up-to-3-way
  absolute-label ambiguity for partial-wafer sweeps. Needs
  whole-vs-jagged die identification (per type, count visible
  whole instances and match to wafer's known partial-die positions)
  to disambiguate.

## Pipeline (atlas-anchored measurement)

```sh
# Atlas-anchored 4D-bar slanted-edge MTF50 (Task 15) — strongest demo.
direnv exec . uv run python scripts/task15_4d_bar_lsf_all_sweeps.py
#   → out/task15/all_sweeps_4d_bar_lsf.png
```

Result: for sweeps where a 4D-type instance is in the field of view,
the atlas-anchored slanted-edge MTF50 argmax matches the LSF-pipeline
focus reference within **±1 shot** on 2 of 3 testable sweeps (M=0.385
and M=2.0). The 4D bar is a wide isolated dark rectangle (~62 × 98 px
subject) that the LSF code in `tile-sharpness/methods/lsf.py` handles
cleanly as a "thick scribe".

## Sweep test set

| # | Sweep | M | Anchored | 4D-bar argmax | LSF ref | Gap |
|---|---|---|---|---|---|---|
| 1 | 100-400 @ 0.385× F11 (Task 2) | 0.385 | ✓ | shot 136 | 137 | **−1** |
| 2 | AF 200/4D @ 1:1 F11 (Task 3) | 1.0 | ✓ | shot 28 | 41 | −13 |
| 3 | Sigma + TC-2001 @ 2:1 F11 (Task 4) | 2.0 | ✓ | shot 46 | 47 | **−1** |
| 4 | Z 24-120 + 61mm @ f/11 (newer-rig) | ~1.29 | ✓ | shot 1 | unknown | n/a |

Sweep 2's −13 gap and sweep 4's monotonic-decrease oddity are open;
likely the bar's ROI register slightly shifts under defocus, or the
4D-type instance chosen by `pick_best_4d_instance` isn't visually
clean at that pose.

## Files

| Path | Content |
|---|---|
| `atlas.json` | Canonical atlas data (16 die types + grid + structural metadata + `fragment_outline`, schema v2). |
| `scripts/` | Build pipeline + measurement scripts. Numbered/dated by iteration. |
| `in/0129_painted2.png` | User-painted feature regions on the 0129 photo (50 MB, not in git). |
| `out/0129/grid_params.json` | Per-photo grid solve for the atlas-build 0129 photo. |
| `out/sweep_anchors/anchor_fit_params.json` | Per-sweep affine fits (4 sweeps). |
| `out/task15/all_sweeps_4d_bar_lsf.json` | Per-sweep, per-shot MTF50 from atlas-anchored 4D-bar LSF. |

## Status

Atlas build, anchor-based registration, and atlas-anchored measurement
are all working end-to-end. Autonomous registration and a few specific
measurement quirks remain as follow-ups — see HANDOVER.md.
