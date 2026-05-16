# Sharpness assessment POC — session handover

State as of 2026-05-16. Picks up after the cross-cohort tile-sharpness
runs landed in commit `f869d78` (analyse-lens-test) and the empirical
findings were folded into `analyse-lens-test/SHARPNESS_METRICS.md`.

## TL;DR

A POC has compared 8 sharpness metrics against the wafer dataset on
four cohorts. The slanted-edge "gold standard" recommendation from
`SHARPNESS_METRICS.md §1` did not survive — `mtfmapper` is unusable
on this rig. `filesize` is more robust than the doc previously
credited it with; `wavelet_ratio` and `dct_kurtosis` (added during
the POC) are the best new cross-frame supplements. Doc updates are
in place. **The one pending human action is an eyeball review of the
cross-lens disagreement crops from the three new cohorts** — see "What's
pending" below.

## Key documents (read in this order)

1. **`analyse-lens-test/SHARPNESS_METRICS.md`** — start at the
   **"Empirical results — POC 2026-05-15"** section near the bottom.
   That's the canonical write-up: cohort summaries, the
   "Recommended setup for cross-lens / cross-frame work" matrix, and
   per-method conclusions. The §1 caveat at the top of the file
   points back to that section.
2. **`analyse-lens-test/tile-sharpness/README.md`** — eight-method
   registry with orientations, per-method caveats, the SSH-to-nufan
   setup for `mtfmapper`, the `compare` / `cross-lens-crops`
   subcommand reference, and a recommended-combinations table.
3. **`analyse-lens-test/CLAUDE.md`** — project conventions index
   (git author email, uv/pytest tooling, analysis style, rig
   semantics, dataset layout, subproject pointers).
4. **`analyse-lens-test/ANALYSIS_NOTES.md`** §2 — bell-curve
   detection thresholds plus the rig-semantics paragraph (off-target
   crops are geometric; reshoot direction is not actionable).
5. **`run-lens-test/DESIGN_NOTES.md`** §6.31 — aperture convention,
   manual-aperture mode mechanics, and the brute-force
   `target_for_next_aperture` solver rationale.

## What's pending

### 1. Manual eyeball review of cross-lens disagreement crops *(headline TODO)*

The three cross-cohort runs produced side-by-side per-method peak
tiles. The numbers say wavelet_ratio and filesize agree closely with
each other and with the consensus on cohorts with wide quality
spreads; they disagree on narrow ones. Whether the methods' picks
*look* sharper to a human is the open question. Three directories,
listed in priority order:

- **`analyse-lens-test/tile-sharpness/out_bare1to1/cross_lens_crops/tile_+0_+0/`** (31 JPEGs, 4 lenses × 8 methods)
  - Concrete pairs to compare:
    - `filesize__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED__shot_029.jpg` (filesize's #1) vs `wavelet_ratio__NIKKOR_Z_MC_105mm_f_2.8_VR_S__shot_040.jpg` (wavelet's #1) — same scene at 1:1, three methods disagree about which lens is sharpest at the centre.
    - `mtfmapper__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM__shot_035.jpg` (mtfmapper's #1) — does Sigma 150 actually deserve mtfmapper's nod?
- **`analyse-lens-test/tile-sharpness/out_resized1to1/cross_lens_crops/tile_+0_+0/`** (49 JPEGs, 6 lens configs)
  - Compare `wavelet_ratio__NIKKOR_Z_MC_105mm_f_2.8_VR_S_+_5T__*.jpg` (consensus best) against `wavelet_ratio__NIKKOR_Z_24-120mm_f_4_S_+_Raynox_M-150__*.jpg` (consensus worst). Visual gap should be obvious — that's the sanity check.
  - Compare `radial_fft__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED_+_5T__*.jpg` (rank 1 by radial_fft) against `filesize__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED_+_5T__*.jpg` (rank 4 by filesize) — same lens, 3-rank disagreement. Who's right?
- **`analyse-lens-test/tile-sharpness/out_55mm/cross_lens_crops/tile_+0_+0/`** (40 JPEGs, 5 sweeps × 8 methods)
  - The two AIS copies (s/n 287318 vs 537016) should look near-identical at `filesize__*.jpg` — if they don't, one is decentered.
  - The three Auto copies (209088 vs 258263 vs 262711) — `258263` ranks consistently better by mean-rank-across-tiles; does its centre tile actually look sharper or is it framed differently?
  - **Filesize artefact worth seeing**: at the centre tile, filesize picks Auto 209088 first (peak 318k bytes), but across all 35 tiles the AIS copies win. That's filesize being content-fooled at one position. Open `filesize__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_209088__shot_030.jpg` and compare to either AIS centre crop.

Each tile dir also has a `README.txt` listing every method's pick
with peak metric value and shot index.

Also worth looking at the off-axis dirs in each cohort if the centre
read is ambiguous: `tile_+3_+0`, `tile_-3_+0`, `tile_+0_+2`,
`tile_+0_-2`.

### 2. Decide whether to drop methods from the registry

- **`mtfmapper`** scored 1/5 on the earlier within-sweep eyeball
  review (the Raynox M-250 sweep, results in `SHARPNESS_METRICS.md`
  empirical section). On the resized cohort it can't discriminate
  at all (all six lenses rank ~3.3). Its CV across same-model copies
  is 0.54, 3-25× the next-worst method.
  - **Open question**: would it perform better on a sweep that has
    clear isolated slanted-edge targets (a real chart card, or
    higher-magnification crops where individual bond pads are
    isolated dark blobs)? The default component-finder needs that
    input shape; `--single-roi` is a fallback. Try once on a chart
    card before deciding to drop the method entirely.
- **`edge_decay`** peak quantises to integer pixels and produces
  ties; useful only for *argmax* (which rail step within a sweep).
  Recommended action: keep it but exclude its `peak_value` from
  cross-tile / cross-lens ranking; let the cross_lens routines
  filter to argmax-only for this method.
- **`radial_fft`** argmax is unreliable (picks heavily-defocused
  end-of-sweep shots due to near-Nyquist noise). Its peak ranking
  is fine. Recommended action: same as `edge_decay` — keep `peak`,
  drop `argmax` from cross-method consumers.

### 3. Integration into rail-coverage?

The empirical section's "Recommended setup" matrix is the candidate
for codifying. The simplest move would be to add
`wavelet_ratio` as a second column alongside the existing
file-size proxy in `analyse-lens-test/rail-coverage/`, and flag
scenarios where filesize and wavelet_ratio rank a lens / scenario
more than ~2 ranks apart. The eyeball review (TODO 1) gates this —
don't integrate until visual confirmation lands.

### 4. mtf_mapper available only on nufan

The local Arch host had its `mtf_mapper` binary deleted during a
failed rebuild attempt earlier in this session, and `cmake` isn't
installed locally so a rebuild is blocked. The rebuilt binary now
lives on nufan (Ubuntu 25.10, OpenCV 4.10) at the in-tree workspace
path — same shared-mount path as before, so callers don't change.
The `score_mtfmapper` scorer in `methods.py` routes via SSH with a
`ControlMaster` to keep one connection warm. To get `mtf_mapper`
working locally again, install `cmake` and rebuild the same way (see
`tile-sharpness/README.md` "SSH setup" for the apt package list and
build steps).

## Repository state

`analyse-lens-test/` repo, recent commits:

```
f869d78 sharpness POC empirical findings + project-conventions doc
cdf1c67 tile-sharpness POC + long-distance metrics doc
```

`lens-test-detect-core/` repo: clean, last commit `75cdc54`. (The
local box now has `/home/alson/shared/projects/personal/fotografie/lens-test-detect-core`
on the git `safe.directory` allowlist; you'll need to do the same
on nufan if you haven't already — same command.)

`run-lens-test/` repo: untouched in this session.

## How to resume

The cohort runs are cached. Tile JPEGs live at
`~/shared/projects/personal/fotografie/.tile-sharpness-cache/` on the
shared mount, so nufan sees the same cache. A re-run of any of the
three cohorts is near-instant for the cropping and ~20-30 min for
mtfmapper-via-SSH plus the four other scoring methods.

```sh
cd analyse-lens-test/tile-sharpness

# List candidate sweeps:
uv run tile-sharpness list-sweeps

# Re-run a cohort (uses cached tiles, re-scores):
uv run tile-sharpness analyse <substring-of-label> ... --out out_<name>/

# Cross-cohort aggregation + crop export:
uv run tile-sharpness compare out_<name>/peaks.csv
uv run tile-sharpness cross-lens-crops out_<name>/peaks.csv \
    --out out_<name>/cross_lens_crops \
    --tile 0,0 --tile -3,0 --tile 3,0 --tile 0,-2 --tile 0,2

# All three driven from one place:
./scripts/finalize_cohorts.sh                          # compare + crops
uv run python scripts/cross_cohort_summary.py          # mean-rank tables + CV
```

The three cohorts that produced the current findings:

```sh
# Bare native macros at 1:1, F8 (4 lenses, same scene)
uv run tile-sharpness analyse \
    "2026-01-29__NIKKOR_Z_MC_105mm_f_2.8_VR_S__1_1__F8" \
    "2026-01-29__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED__1_1__F8" \
    "2026-01-29__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM__1_1__F8" \
    "2026-01-29__Sigma_Macro_105mm_F2.8_EX_DG_OS_HSM__1_1__F8" \
    --out out_bare1to1 --workers 8

# Resized 1:1 cross-config (6 mixed configs)
uv run tile-sharpness analyse \
    "2026-01-29__NIKKOR_Z_MC_105mm_f_2.8_VR_S_+_5T__1_1-resized__F8" \
    "2026-01-29__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED_+_5T__1_1-resized__F8" \
    "2026-01-29__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM_+_5T__1_1-resized__F8" \
    "2026-01-29__Nikon_AF_Zoom-Micro_Nikkor_70-180mm_f_4.5-5.6D_ED_+_5T__1_1-resized__F8" \
    "2026-01-29__NIKKOR_Z_100-400mm_f_4.5-5.6_VR_S_+_Nikon_5T__1_1-resized__F8" \
    "2026-02-18__NIKKOR_Z_24-120mm_f_4_S_+_Raynox_M-150__1_1-resized__120.0_mm__F8" \
    --out out_resized1to1 --workers 8

# Multi-copy 55mm primes (2× AIS + 3× Auto)
uv run tile-sharpness analyse \
    "2026-01-29__Nikon_Micro-Nikkor_55mm_f_2.8_AIS_287318__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_55mm_f_2.8_AIS_537016__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_209088__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_258263__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_262711__1_1__F8" \
    --out out_55mm --workers 8
```

All three are committed under `out_*` glob in `.gitignore` so the
generated trees stay out of git. The peaks.csv / agreement.csv /
disagreement directory layout is documented in
`tile-sharpness/README.md`.

## What changed in this session, in one paragraph

POC validated. Four new methods added to the registry
(`laplacian_var`, `tenengrad`, `dct_kurtosis`, `wavelet_ratio`).
Sweep discovery extended to handle bare-prime 3-level layouts and
`*-resized` cohort directories. `compare` and `cross-lens-crops`
CLI subcommands added for cross-sweep aggregation. `mtf_mapper`
moved from local to nufan over SSH (ControlMaster-multiplexed); tile
cache moved from `~/.cache` to the shared mount so nufan reads
tiles by path. Docs updated to reflect empirical findings; memory
files reduced to pointers since the canonical content now lives in
the shared docs. Three cross-lens cohorts run (bare 1:1, resized
1:1, multi-copy 55mm) but the manual eyeball verification step has
not been done yet.
