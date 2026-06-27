# wafer-atlas — session handover

State as of 2026-05-18 (original), extended 2026-06-27.

---

## Next session — START HERE (2026-06-27)

**Read first:** `REPORT_2026-06-27.md` (full detail of the 2026-06-27 work) and
the two memory files `wafer_atlas_lsf_ref_is_filesize.md` +
`wafer_atlas_autoreg_and_grid_v3.md`. The "Pending" section further down is the
ORIGINAL 2026-05-18 list — items #1, #2, #4 there are now DONE; #3 is untouched.

**What now works (2026-06-27):** autonomous per-sweep registration end-to-end
(`scripts/reg_auto.py`) at ~1–6px true accuracy (better than the manual 3-anchor
method) — tilt-by-scribe-alignment, 4D-bar row anchor, fragment-outline column
disambiguation, gap-aware labelling, full-res refinement with a radial-distortion
term for non-macro lenses. The atlas grid was recalibrated (`atlas.json` schema
v3, `grid_calibration` block). POC C bond-pad measurement works (`task17`).

### Next steps (priority order)

> **Update (2026-06-27, follow-up): steps 1 & 2 below are DONE** (commits
> `336f4c0` hygiene re-run, `ffe8d3f` autonomous switch). Top remaining item is
> now **#3 (validate on an unseen sweep)**.

1. ~~**Re-run `task15` + `task17` under the v3 grid (hygiene).**~~ **DONE**
   (`336f4c0`). Re-ran both with the manual anchors under the v3 atlas: every
   task15 focus argmax and the task17 headline (coverage 100%, lapvar usable 87%,
   median 138) are UNCHANGED — only underlying per-shot values shift ~1% as the
   ROIs move. No regression; outputs refreshed.

2. ~~**Close the loop: make `task15`/`task17` use autonomous registration.**~~
   **DONE** (`ffe8d3f`). Added `reg_auto.register_and_refine(name)` (detect →
   register → `refine_full_res`, returns the refined distortion-aware affine +
   provenance). task15 + task17 now default to autonomous registration; projection
   routed through `reg_auto.grid_xy_distorted` so the radial term applies for
   non-macro lenses (sweep1 k1=+0.015, sweep4 k1=−0.021; macros stay similarity).
   `--manual` restores the hand-clicked anchors for cross-check. **Verified
   identical to baseline**: task15 focus argmaxes match on every instance
   (137/136/134, 30/21, 28, 0); task17 headline identical. Cold-registration fit
   residuals 1.11/2.52/5.87/2.22px. **A new sweep needs zero manual anchoring.**

3. **Validate `reg_auto` on a genuinely unseen sweep.** All four test sweeps were
   used in development (two in the grid recal). Pick an untouched sweep (other
   aperture/lens under `…/test-raw-data/`), run `reg_auto`, confirm it registers.
   *(low–medium)*

4. **Item #3 (deferred): atlas + maze-FFT at high M** — see Pending §3 below.
   Still untouched.

5. **Consolidation.** `reg_auto.py` has grown; ~12 `diag_*.py` are dev artifacts.
   A `/code-review` pass and a small regression test for `reg_auto` (assert the 4
   sweeps' col/row offsets + refined RMSE) would lock behaviour in.

### How to run (both hosts share ~/shared over NFS)

```sh
# Heavy decode/measurement -> run on nufan (Ryzen 5800X, faster). Per-host venv:
ssh nufan
export PATH="$HOME/.local/bin:$PATH"
cd /home/alson/shared/projects/personal/fotografie/analyse-lens-test/wafer-atlas
export UV_PROJECT_ENVIRONMENT="$HOME/.cache/uv-venvs/wafer-atlas"   # NOT the NFS .venv
uv run --no-sync python scripts/reg_auto.py          # autonomous registration, all sweeps
#   reg_auto.py --oracle    # proves geometry with optimal labels
#   reg_auto.py --validate  # mapping/label sanity probe
```

### Gotchas
- **venv is per-host** at `~/.cache/uv-venvs/wafer-atlas` (outside ~/shared); set
  `UV_PROJECT_ENVIRONMENT` or the build fails. `pyproject.toml` is `package=false`.
- **`atlas.json` is schema v3** — pitches recalibrated; old ratios in
  `grid_calibration`. Anything cached against the old grid is stale (that's why
  step 1 exists).
- The old `task15` "lsf_ref_shot" values (137/41/47) were **JPEG-filesize
  argmaxes, not LSF** — already fixed in task15; don't reintroduce.
- MTF50 saturates at M≥1 → use a non-saturating metric (lapvar) for focus argmax.

---

## What landed this session

A new `wafer-atlas/` uv-subproject (sibling to `tile-sharpness/`,
`archive-2026-05/`, `rail-coverage/`, `bellows-calibration/`) that
provides a coordinate system for the test wafer and a feature
catalogue indexed by super-cell type. The atlas's primary delivery
is **atlas-anchored sharpness measurement**: pointing the existing
LSF + MTF50 code at a known wafer feature with sub-pixel-precise
location, instead of relying on per-tile feature detection that has
57% coverage and non-deterministic across-shot behaviour (POC C from
the earlier session).

Headline result: atlas-anchored 4D-bar slanted-edge MTF50 on Task 2
(NIKKOR Z 100-400 @ 0.385× F11) finds focus argmax at **shot 136 vs
LSF-pipeline reference 137 — gap of −1 shot**. Same agreement on
Task 4 (Sigma + TC-2001 @ 2:1, gap −1). See "Status of measurements"
below for the cross-sweep table.

## Read these first

1. **`README.md`** — what the atlas is, coordinate convention,
   pipeline overview, file layout.
2. **`atlas.json`** — the actual atlas data. 16 super-cell types
   with bond_pads / slanted_edge / experimental feature inventories
   and structural metadata.
3. **MEMORY.md** entries in `~/.claude/projects/-home-alson-shared-
   projects-personal-fotografie-run-lens-test/memory/`:
   - `wafer_4x4_supercell_irregular_pitch.md` — why grid fits with
     a uniform-pitch assumption fail.
   - `maze_fft_original_framing.md` — historical context for why
     pad-grid FFT was originally framed as the primary high-M
     measurement.

## Coordinate system (locked)

- f/8 overview photo `step_0131_c.jpg`: rotation **4.66° CW**, origin
  `(1064, 4029)`. Per-(col mod 4) widths `[539, 458, 454, 453]` and
  per-(row mod 4) heights `[456, 544, 453, 452]` in pixels.
- f/8 + 35mm extension overview `prev_step_0129_b.jpg` (atlas-build
  source): rotation **5.07° CW**, origin `(-645, 4663)`, scale
  **1.582×** the f/8 overview. Grid solved from 3 user anchors, RMSE
  1.92 px.

## Anchor-based registration (production path)

`scripts/anchor_fit_sweep.py` solves `(θ, x0, y0, scale)` from 3+
user-supplied scribe-intersection anchors. Verified on 4 test sweeps:

| Sweep | M | Anchors | Rotation | Scale (vs 0129) | RMSE |
|---|---|---|---|---|---|
| sweep1 (100-400 @ 0.385× F11) | 0.385 | 3 | 4.78° | 0.632× | 2.5 px |
| sweep2 (AF 200/4D @ 1:1 F11) | 1.00 | 3 | 4.63° | 1.644× | 3.0 px |
| sweep3 (Sigma+TC-2001 @ 2:1 F11) | 2.0 | 3 | 4.33° | 3.337× | 7.9 px |
| sweep4 (Z 24-120 + 61mm @ f/11) | ~1.29 | 3 | 4.47° | 2.109× | 5.4 px |

Rotation spread across all sweeps is 0.45° — confirms the user's
"wafer mounted at fixed angle on QR plate" theory. The per-sweep
labelled overlays at `out/sweep_anchors/<label>.png` are useful as
references when marking new sweeps' anchors.

## Status of measurements (Task 15)

`scripts/task15_4d_bar_lsf_all_sweeps.py` runs `cross_section +
lsf_mtf50` from `tile_sharpness.methods.lsf` on atlas-targeted ROIs
of the 4D vertical bar across each sweep's full shot list.

| Sweep | Instance used | Argmax | LSF ref | Gap |
|---|---|---|---|---|
| sweep1 (M=0.385) | 4D | 136 | 137 | **−1** ✓ |
| sweep2 (M=1.0) | 8D | 28 | 41 | −13 ✗ |
| sweep3 (M=2.0) | 4D | 46 | 47 | **−1** ✓ |
| sweep4 (~M=1.29) | 4D | 1 | unknown | n/a |

Atlas's primary value is demonstrated on the two M-extreme sweeps.
Sweep 2's −13 gap and sweep 4's "argmax at shot 1, then monotonic
decrease" are open quirks — see "Pending".

The MTF50 magnitude on sweep 1 was 14.75 lp/mm subject — lower than
POC A's slanted-edge subpixel-binning 20.5 lp/mm earlier, presumably
because the 4D bar's intrinsic edges aren't optically perfect (PSF +
bar fabrication geometry). Per-shot **focus discrimination** is what
the atlas-anchored measurement does well; **absolute MTF50** still
benefits from the scribe-based ESF→LSF when scribes are usable.

## Pending

> **Update 2026-06-27:** items #1, #2, #4 below worked in `REPORT_2026-06-27.md`.
> Summary: the sweep 2/4 "anomalies" were not atlas bugs — the hardcoded
> `lsf_ref_shot` values (137/41/47) are **JPEG-filesize argmaxes, not LSF focus
> argmaxes**; corrected, the atlas agrees with the LSF/maze pipeline within ~2
> shots at all M. Autonomous registration's blocking bug (a rotation-sign error,
> anchor-RMSE 6000→~40px) is fixed; absolute labelling re-scoped to
> feature-anchoring (whole-vs-jagged is insufficient for interior FOVs). POC C's
> coverage (57%→100%) and determinism are solved via atlas-anchored bond-pad
> ROIs scored by gradient energy (87% usable focus). See the report for detail;
> item #3 remains untouched.

### 1. Sweep 2 and Sweep 4 anomalies

- Sweep 2 picks 8D (1472 px from image centre) — col 8's row D may
  be near the wafer's right edge in this sweep's FOV. The bar may
  be partly outside the ROI extraction window. Verify by inspecting
  the bar's predicted bbox against the actual sweep image.
- Sweep 4's monotonic decrease (argmax at shot 1, lowest at shot 128)
  suggests the rail starts at focus and walks AWAY through the sweep,
  rather than the usual "sweep through focus" pattern. Check whether
  the sweep is rail-only-back-side. Also inspect a representative
  middle-shot ROI to confirm the 4D bar is in frame.

### 2. Autonomous registration — task #14

The morphological pipeline ported from `archive-2026-05/
measure_wafer_squares` correctly recovers scale + rotation + super-
cell pattern, but has up-to-3-way absolute-label ambiguity for
partial-wafer sweeps. The disambiguation requires whole-vs-jagged
die identification:

For each visible super-cell type, count the whole instances and
match to the wafer's known whole-die inventory per type. E.g.:
- Type (2, 1) = 2B: whole at cols 2 and 6, jagged at col 10.
  If sweep shows 2 whole instances → cols 2 + 6 (left half of wafer).
- Type (0, 1) = 4B: whole at cols 4 and 8, jagged at col 0.
- Type (2, 0) = 2E + 6E: whole at col 6, jagged at cols 2 and 10.

Where the user looked visually at sweep 2 and identified "jagged
edge bottom-right and top-left", a CV pipeline could:

1. Detect chroma silicon boundary (already done in
   `_silicon_mask`).
2. For each super-cell-type instance found via the morphological
   scribe detection, check whether the bounding-box of that
   instance is bounded by the silicon mask edge.
3. Count whole vs jagged instances → uniquely determine which
   wafer region the sweep covers.

Estimated effort: ~half-day to land cleanly.

### 3. Atlas application to high-M maze-FFT measurements

The atlas knows pad-grid pitches per super-cell type. For sweeps at
M ≥ 0.7 (where the existing maze-FFT method applies), atlas-anchored
pad-FFT could replace or augment the maze-FFT amplitude signal — at
known pad pitches matched to each die-type, not the generic 13 µm
maze fundamental. Worth testing if the maze-FFT method ever shows
limitations on a specific lens config.

### 4. Atlas-anchored measurement on POC C's failed tiles

The original session's POC C ("wide-feature inventory") had 57%
coverage and was non-deterministic across shots. An atlas-anchored
re-run targeting only the bond-pad regions the atlas knows about
(36 components across 14 die types) would close both problems.
Not done in this session; the 4D-bar demonstration was the cleaner
demo of atlas value.

## File layout

```
wafer-atlas/
├── README.md
├── HANDOVER.md            (this file)
├── atlas.json             (canonical, committed)
├── .gitignore             (excludes painted PNGs + regenerable overlays)
├── in/                    (painted source PNGs, NOT in git)
│   └── 0129_painted2.png  (50 MB)
├── out/
│   ├── 0129/
│   │   ├── grid_params.json       (per-photo grid solve, committed)
│   │   ├── atlas_0129_painted.json (intermediate, gitignored)
│   │   └── *.png                  (gitignored overlays)
│   ├── sweep_anchors/
│   │   ├── anchor_fit_params.json (per-sweep affines, committed)
│   │   └── *.png                  (gitignored overlays)
│   ├── task15/
│   │   ├── all_sweeps_4d_bar_lsf.json (committed)
│   │   └── *.png                  (gitignored plots)
│   └── registration/      (autonomous registration experiments,
│                           regenerable, gitignored)
└── scripts/               (all committed)
    ├── grid_supercell_refined.py  (overview-photo grid solve)
    ├── register_0129.py           (atlas-build photo grid solve)
    ├── parse_painted.py           (extract painted feature regions)
    ├── consolidate_atlas.py       (build atlas.json)
    ├── anchor_fit_sweep.py        (per-sweep registration from anchors)
    ├── task15_4d_bar_lsf_all_sweeps.py  (atlas-anchored measurement)
    ├── register_method_template.py     (autonomous attempt, partial)
    ├── register_method_morphological.py (autonomous attempt, partial)
    └── (iteration history: recon_grid_v*.py, extract_top3*.py, etc.)
```

## How to resume

```sh
cd analyse-lens-test/wafer-atlas

# Confirm atlas is loadable + complete.
direnv exec . uv run python -c "
import json
a = json.load(open('atlas.json'))
print(f'{len(a[\"die_types\"])} die types')
print(f'super-cell w/h: {a[\"die_pitch_px_in_0129\"][\"super_cell_width_px\"]:.0f} / '
      f'{a[\"die_pitch_px_in_0129\"][\"super_cell_height_px\"]:.0f} px in 0129')
"

# Re-render any overlay (e.g. to validate against a new sweep):
direnv exec . uv run python scripts/anchor_fit_sweep.py

# Re-run the Task 15 measurement (slow — full-frame JPEG decode × n_shots).
direnv exec . uv run python scripts/task15_4d_bar_lsf_all_sweeps.py
```

The atlas data is **committed**, so anyone who clones the repo
can reproduce the measurement results from scripts/. The painted
input PNGs are not (50 MB each); the build pipeline can be re-run
from those when present, or just use `atlas.json` directly.
