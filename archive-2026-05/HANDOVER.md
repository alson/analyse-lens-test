# 2026-05 archive pipeline — session handover

State as of 2026-05-16. This document points a fresh Claude session
to everything needed to continue the work without re-deriving it.

## TL;DR

A 4-step pipeline archives the 2026-05 lens-test shoots from
`~/macro-lens-test-output/` (~517 GB) to NFS
`~/shared/files/pics/digikam/test-raw-data/` and brings them into
the existing `<lens>/<mag>/<focal>/F<n>/` Digikam layout used by
`2026-01-29/` and `2026-02-18/`. All four scripts exist, are
tested (77 unit tests), and are committed. Only step 1 (the actual
NFS copy) is running live; steps 2-4 are ready to run on nufan
afterwards.

## Key documents (read in this order)

1. **`analyse-lens-test/merge-audit-2026-05.md`** — source-of-truth
   for routing decisions (which session is canonical, which is
   superseded, etc.). All D1-D5 decisions resolved 2026-05-15.
2. **`~/.claude/plans/effervescent-jingling-newt.md`** — current
   pipeline plan with status section, target layout, filename
   convention, the full algorithmic no-go log, and decisions made
   during this session.
3. **`analyse-lens-test/archive-2026-05/README.md`** — package-level
   doc covering the four script roles and usage.
4. **`analyse-lens-test/ANALYSIS_NOTES.md`** §7a.4 — the
   wafer-square automation findings, including the no-go log and
   the GT-label-error discoveries.

## The four scripts

All in `analyse-lens-test/archive-2026-05/src/archive_2026_05/`,
runnable as `python -m archive_2026_05.<script>`:

| step | script | status | runs on |
|---|---|---|---|
| 1 | `archive_to_nfs.py` | committed, **running live** | bumblebee |
| 2 | `measure_wafer_squares.py` | committed | nufan (via SSH) |
| 3 | `rename_for_digikam.py` | committed | nufan |
| 4 | `sort_to_lens_tree.py` | committed | nufan |

Recent commits in `analyse-lens-test/` repo:
```
b7f3c4f archive-2026-05: step-4 sort + ANALYSIS_NOTES §7a.4 algorithm log
f7c972f archive-2026-05: step-4 sort_to_lens_tree
db01090 archive-2026-05: step-2 cross-check + step-3 rename_for_digikam
79d8fe3 archive-2026-05: sub-pixel peak refinement + confidence stratification
8227a4e archive-2026-05: step-2 wafer-square measurement (tilt + morph)
670d842 archive-2026-05: README — step 4 builds <mag>/<focal>/F<n>/ inside each slug
9a7620d archive-2026-05: step-1 copy to NFS with audit-driven routing
```

## Step 1 status — DONE (as of 2026-05-16, ~16:30 local)

Step 1 (`archive_to_nfs.py`) finished cleanly. Final state on NFS:

- **21 dirs** under `2026-05-12/` (matches manifest target)
- **31 dirs** under `2026-05-13/` (matches manifest target)
- Process started 2026-05-15 23:58, restarted 02:00 after a kill,
  finished ~16:30 on 2026-05-16. Wall-clock ~14.5 h, mostly NFS-bound.
  Throughput recovered from ~7 MB/s (Wi-Fi) to ~14-18 MB/s after
  the wired-LAN cable swap mid-run.

**Broken symlinks at end of step 1: 5082.** Two patterns:

1. **~7 `range_check.json` / `calibration.json`** symlinks pointing
   into merge_source sessions that never had those files. Cosmetic.
2. **~5075 `cur_step_NNNN[_X].jpg`** symlinks inside merged-dir
   `f_<n>/` subtrees. The merge-symlink logic creates "current"
   versions for what it expects to be overlapping captures, but
   most of those step files don't exist in the underlying
   merge_source. Example: `Z 24-120 + 61mm extension
   (2026-05-08_201054)/f_8/` contains only `step_0092.jpg` and
   `cropped/`, yet 200+ `cur_step_*` symlinks point into it.

Not blocking step 2 — `sharpest_per_aperture` only walks top-level
`F<n>/` dirs (case-sensitive), not the lowercase `f_<n>/` source
subtrees where the broken `cur_step_*` symlinks live. But these
should be investigated and either fixed in `archive_to_nfs.py`'s
merge logic or pruned before treating the merged trees as drop-in
equivalents of the source sessions.

**To check broken symlinks**:
```sh
find ~/shared/files/pics/digikam/test-raw-data/2026-05-1[23] -xtype l | wc -l
# Expect: 5082 (current state)
# Investigate: head of that list shows the patterns above
```

## Running steps 2-4

These need numpy + scipy + Pillow + scikit-image (in the
`pyproject.toml` deps) plus `exiftool` on the PATH (step 3 reads
EXIF focal lengths).

```sh
# Step 2: build the magnification manifest for 2026-05-13.
# (Default anchor is now Nikon AF 200 f/4D — see §7a.8 in
# ANALYSIS_NOTES for why. You can omit the --anchor flag entirely.)
uv run python -m archive_2026_05.measure_wafer_squares prepare \
    --root ~/shared/files/pics/digikam/test-raw-data/2026-05-13 \
    --out /tmp/wafer-manifest-2026-05-13.csv

# Caveat: 2026-05-13 source-side dirs use lowercase f_<n>/ naming
# (e.g. f_5_6, f_8, f_11, f_16). measure_wafer_squares'
# sharpest_per_aperture only globs `F*` (capital F), so on the
# raw 2026-05-13 tree it'll find no apertures and return None for
# every config. Either run step 4 first (which renames f_<n>/ → F<n>/)
# or temporarily patch sharpest_per_aperture to also accept f_*.
# The 2026-01-29 dataset already has F<n>/ (Digikam-style), so the
# above command works as-is on that one.
```

Manifest columns are listed in
`measure_wafer_squares.MANIFEST_COLUMNS`. **For the 2026-05-13
production tree**, the algorithm picks the magnification
directly; vision review is only needed for rows whose
`algo_confidence` is `medium` or `low`. Fill those rows'
`visual_count` column by hand (one entry == "die count along the
horizontal axis of the centre crop"); then run:

```sh
uv run python -m archive_2026_05.measure_wafer_squares evaluate \
    --manifest /tmp/wafer-manifest-2026-05-13.csv \
    --anchor "Nikon AF Micro-Nikkor 200mm f_4D IF-ED"
```

Each HIGH-confidence row already has `algo_measured_mag` populated;
step 3 uses that. The selection priority in step 3 is:
`vision_measured_mag` > `algo_measured_mag` (if HIGH) >
`claimed_mag`.

```sh
# Step 3: rename to Digikam convention.
uv run python -m archive_2026_05.rename_for_digikam \
    --root ~/shared/files/pics/digikam/test-raw-data/2026-05-13 \
    --manifest /tmp/wafer-manifest-2026-05-13.csv \
    --dry-run        # always dry-run first
uv run python -m archive_2026_05.rename_for_digikam \
    --root ~/shared/files/pics/digikam/test-raw-data/2026-05-13 \
    --manifest /tmp/wafer-manifest-2026-05-13.csv

# Step 4: collapse to <slug>/<mag>/<focal>/F<n>/
uv run python -m archive_2026_05.sort_to_lens_tree \
    --root ~/shared/files/pics/digikam/test-raw-data/2026-05-13 \
    --dry-run
uv run python -m archive_2026_05.sort_to_lens_tree \
    --root ~/shared/files/pics/digikam/test-raw-data/2026-05-13
```

After step 4, the layout matches `2026-02-18/` and the existing
`make-crop-for-every-lens-magnification-focal-length-aperture.sh`
will run cleanly to populate `1_1-resized/` + `2_1-resized/`
sibling trees + crops.

## Known issues & gotchas

* **The runner does not populate magnification metadata in
  shots.csv** (the `magnification_indicated` / `f_ring` /
  `focal_length_mm` columns are empty in every captured session).
  Step 2 gets magnification from session.json's `lens_configs[]`
  entry instead; step 3 gets focal length from EXIF.
* **The 2026-01-29 GT had label issues — mostly fixed.** Fixup
  script `analyse-lens-test/fixup-sigma-tc-mislabels-2026-01-29.py`
  applied (2026-05-16):
  - `Sigma 105 + TC-1401 / 1_1 ↔ 1.4_1` were swapped → relabelled
    as `1.5_1` (achieved mag, the TC-1401's effective factor is
    ~1.5 not the nominal 1.4) and `1_1`.
  - `Sigma 105 + TC-2001 / 2_1` had 232 stray 1:1 captures (seq
    15777-16008) that a per-file Nikon FocusDistance audit
    revealed — moved into `1_1/`.
  - A fourth originally-planned rename
    (`Sigma 150 + TC-2001 / 1_1 → 1.5_1`) was applied then
    **reverted** the same day after a lens-focus-scale check and
    user GIMP measurement both confirmed the dir is at ~1.0×
    (the algo's F11 reading of 1.45× was a sub-feature harmonic).
    Revert script:
    `analyse-lens-test/revert-sigma-150-tc-2001-1_1-rename-2026-01-29.py`.
    The multi-aperture cross-check (added later) would have flagged
    the over-correction up front — F11 disagreed with F16/F8.5 by
    32 %.
  - The 105 + TC-1401 / 1_1 → 1.5_1 step was subsequently
    re-renamed to `1.4_1` for consistency with
    `Sigma 150 + TC-1401 / 1.4_1` (same lens-at-MFD-with-TC-1.4
    setup; same label). Script:
    `analyse-lens-test/rename-sigma-105-tc-1401-1.5to1.4-2026-01-29.py`.

  Caliper measurement of the physical wafer (47.9 mm / 9 dies =
  5.322 mm physical pitch) gives absolute calibration. Sigma 150
  anchor reads 0.982× of true 1:1; Sigma 105 1.015×; Nikon AF 200
  f/4D / 1_1 exactly 1.000× (user GIMP-verified); Nikon Z MC 105,
  60mm f/2.8D and AIS 55mm cluster at 0.96-0.97× (3-4 % under
  true 1:1, likely a shared rig-level framing offset). **The
  Nikon Auto 55mm f/3.5 readings are NOT calibration data** —
  shot with K-series extension tubes (M-tube/PK-13 not usable on
  the FTZ-DSLR-era setup), total length a hair over 27.5 mm, so
  the lens was deliberately focused under 1:2 to match the
  reference framing. Convert algo readings to absolute mag with
  ×0.982. See ANALYSIS_NOTES.md §7a.4 + §7a.7 + §7a.8 for full
  reasoning.

* **Archive step-1 broken-symlink count (2026-05-16): 5082.** The
  `archive_to_nfs.py` merge-symlink logic creates
  `cur_step_NNNN[_X].jpg` symlinks for what it expects to be
  overlapping captures across merged sessions, but most of those
  step files don't exist in the underlying merge_source dirs
  (e.g. `Z 24-120 + 61mm extension (2026-05-08_201054)/f_8/`
  contains only `step_0092.jpg` and `cropped/`, yet 200+
  `cur_step_*` symlinks point into it). Not blocking the
  wafer-measurement work (these are inside `f_<n>/` subtrees,
  which `sharpest_per_aperture` doesn't look at — it only walks
  `F<n>/` top-level dirs). Worth investigating before relying on
  the merged-dir trees as drop-in equivalents to the merge-source
  sessions.
* **Wafer-square algorithm partial-wafer failure mode partly
  addressed.** Sub-1:1 frames (e.g. `100-400 / 1_2.60` where the
  wafer covers ~27 % of frame width) still don't give trustworthy
  numbers; the gap-bridge retry (§7a.6) now produces *some*
  measurement instead of returning None, but for `1_2.60`
  specifically the result is still wrong (sub-feature harmonic).
  Confidence is "low" so downstream code ignores it. Vision review
  remains the safety net for sub-1:1 configs.
* **`-resized` sibling dirs** under each slug (e.g.
  `1_1-resized/`, `2_1-resized/`) are produced by the existing
  `make-crop-*` script AFTER step 4 — not by this pipeline.
* **NFS write speed dominates step-1 wall-clock** (the user noted
  this and switched to wired LAN partway through). Don't expect
  algo-style 1-2 GB/s — NFS over LAN was running ~70-100 GB/h
  before the cable swap.

## Validation status

| script | unit tests | validation |
|---|---|---|
| `archive_to_nfs.py` | 25 | dry-run-verified against real source |
| `measure_wafer_squares.py` | 25 | 55 cases on 2026-01-29 GT post-fixup; HIGH band 2.2 % mean abs dev, HIGH+MEDIUM 3.5 % over 44 rows; 12 cross-aperture-disagreement warnings flag the rest |
| `rename_for_digikam.py` | 26 | helper-function tests only; not end-to-end yet |
| `sort_to_lens_tree.py` | 8 | synthetic-slug end-to-end + dry-run + no-op + refusal |
| **total** | **77** | |

End-to-end run on real 2026-05-13 data hasn't happened yet (waiting
for step 1 to finish). The script-by-script dry-run checks looked
clean against fixture data.

## What the next session needs to do

Step 1 is DONE. Pickup points, in priority order:

### 1. Investigate the 5082 broken symlinks (HIGH priority)

The merged-dir trees have many `cur_step_NNNN[_X].jpg` symlinks
pointing to step files that don't exist in the merge_source. Either
the merge logic is wrong about which step files should be linked
or the merge_source copy is incomplete. To investigate:

```sh
# Categorise:
find ~/shared/files/pics/digikam/test-raw-data/2026-05-1[23] -xtype l > /tmp/broken.txt
wc -l /tmp/broken.txt                                        # 5082 expected
awk -F/ '{print $NF}' /tmp/broken.txt | awk -F. '{print "."$NF}' | sort | uniq -c
# Spot-check one merge-source dir's actual content vs the linked names:
ls "~/shared/files/pics/digikam/test-raw-data/2026-05-12/NIKKOR Z 24-120mm f_4 S + 61mm extension (2026-05-08_201054)/f_8/"
```

The fix probably lives in `archive_to_nfs.py`'s merge-symlink loop
(it should only `ln` to source files that actually exist). Once
fixed, either prune stale symlinks or re-run step 1 (idempotent).

### 2. Path-glob fix in measure_wafer_squares for raw 2026-05-13 layout (REQUIRED before step 2)

`sharpest_per_aperture` globs `F*` (capital F). The raw 2026-05-13
tree uses lowercase `f_<n>/` directory names (e.g. `f_5_6`, `f_8`,
`f_11`, `f_16`). Either:

- (a) Run step 4 (`sort_to_lens_tree`) **before** step 2 — step 4
  renames the F-aperture dirs to the Digikam capital convention.
  But this contradicts the original "step 2 first" order.
- (b) Tweak `sharpest_per_aperture` to also accept `f_*` (in
  addition to `F*`). Lowercase-glob is a one-line change.
- (c) Pre-rename the F-dirs as a quick shell loop before running
  step 2.

(b) is the right long-term move — it lets the algorithm run on
raw, un-sorted trees too. Estimated 5 lines of code + a regression
test that runs `sharpest_per_aperture` against a 2026-05-13 dir.

### 3. Run steps 2-4 on 2026-05-13

After (1) and (2), this is the originally-planned flow:

- Step 2 `prepare` → /tmp/wafer-manifest-2026-05-13.csv
- Eyeball the manifest. Rows with `algo_aperture_warning` set need
  vision review (cross-aperture sub-feature-harmonic suspects).
  Rows with `algo_confidence == low` need vision review too. For
  each such row, view the image at `image_path` and fill
  `visual_count` (= "die count along the horizontal axis of the
  centre crop"). Then run `evaluate`.
- Step 3 `rename_for_digikam` (dry-run, then real).
- Step 4 `sort_to_lens_tree` (dry-run, then real).
- Generate `-resized/` siblings via the existing crop scripts.

### 4. End-to-end spot-check

Pick one merged-dir slug (e.g. `2026-05-13/NIKKOR Z 100-400mm
f_4.5-5.6 VR S + 35mm extension/`), verify the surviving symlinks
still resolve into 2026-05-12 after the sort. Confirm
`shots.csv`'s `filename` column is consistent with on-disk file
locations.

### 5. (Optional) Bake absolute-mag calibration into the algo

Currently `algo_measured_mag` is the algo's relative reading
against the Nikon AF 200 f/4D / 1_1 anchor (median across
apertures). That's defined to be 1.000× of true 1:1 (caliper +
GIMP verified), so `algo_measured_mag` is already absolute-mag
within ±2-3 % algo noise. A future enhancement could:

- Take an optional `--absolute-anchor-mag=<float>` CLI flag (default
  1.0), and bake it as a column conversion (e.g. would let a user
  re-anchor against a different physical reference if needed).
- Or: include the caliper-derived true-1:1 pixel pitch (1224 px
  full-res on Z7 with this wafer) as a calibration constant and
  optionally output an `absolute_mag_via_caliper` column for cross-
  check.

Not blocking — the current Nikon-200 anchor already gives absolute
mags directly.

## What this session changed (2026-05-16 algorithm + dataset)

**Algorithm fixes** (in commit-history order):

- `8cd8f8e` — tilt detector suppresses the 0°-bin downsample-
  aliasing spike (`detect_tilt_via_gradient`)
- `8ae2ed4` — line extractor adds a binary-closing retry to bridge
  dust-broken scribes (`measure()` retries with `gap_bridge_px=15`
  when primary returns < 2 peaks)
- `bfd6f29` — multi-aperture cross-check + disagreement warning
  (`measure_config()`, `ConfigMeasurement` dataclass, new manifest
  columns `algo_apertures_tried` / `algo_best_aperture` /
  `algo_cross_aperture_dev_pct` / `algo_aperture_warning`)
- `c89549d` — default anchor switched to Nikon AF Micro-Nikkor
  200mm f/4D / 1_1; anchor period is now the cross-aperture median
  (robust against the AF 200 / F11 sub-feature-harmonic outlier)

**Dataset fixup** (one-off scripts at `analyse-lens-test/` repo
root):

- `cf3aed4` + `53fc212` — `fixup-sigma-tc-mislabels-2026-01-29.py`
  applied. Final state of the Sigma+TC dirs:
  - `Sigma 105 + TC-1401`: `1_1` ↔ `1.4_1` labels swapped (8342
    file ops, via a `_tmp_swap` intermediate)
  - `Sigma 105 + TC-2001 / 2_1`: 232 stray 1:1 captures (seq
    15777-16008) moved into `1_1/`
- `a2f5733` — `revert-sigma-150-tc-2001-1_1-rename-2026-01-29.py`
  reverted an over-correction the original fixup applied based on
  the algo's F11 reading (which was a sub-feature harmonic).
  150 + TC-2001 / 1_1 dir is correctly back at the original label.

**Lens findings** (ANALYSIS_NOTES §7a.8):

| Lens / TC | Effective vs true 1:1 |
|---|---:|
| Nikon AF Micro 200 f/4D (anchor) | 1.000× (GIMP-verified, hard stop) |
| Nikon Z MC 105 / 60mm / AIS 55mm | within ±1 % of true 1:1 |
| Sigma 150 (indicated 1:1 mark) | ~1.00× |
| Sigma 150 (hard mech stop)     | ~1.04× |
| Sigma 105 bare                 | ~1.05× (focus scale allows past 1:1) |
| Sigma TC-1401                  | 1.443× effective (3 % over nominal) |
| Sigma TC-2001                  | 1.96× effective |
| Kenko Pro 300 DG 1.4x          | 1.395× effective (closest to nominal) |

Calibration anchored on caliper: physical die pitch = 5.322 mm
(47.9 mm / 9 dies) → 1224 px at true 1:1 on Z7's 4.349 µm/px
sensor.

**Important behavioural note**: the Sigma 150's distance encoder
has a broad dead zone covering hard stop → indicated 1:1 mark →
several degrees of slack past the mark. All these positions report
the same EXIF FocusDistance (0.375837 m). Don't trust EXIF
FocusDistance alone to disambiguate within this range.

## Open questions for the next session

- Should `archive_to_nfs.py` only create merge symlinks for source
  files that actually exist? (Currently creating 5075 dangling
  `cur_step_*` symlinks.) Investigate before treating merged-dir
  trees as canonical.
- Should the algorithm's `sharpest_per_aperture` accept `f_*` as
  well as `F*` to work on un-sorted 2026-05-13 trees? Likely yes;
  small change.
- Is the Sigma TC-1401's +3 % over-spec a real optical effect
  (TC barrel built slightly long?) or a measurement artefact?
  Reproduces cleanly on two host lenses (Sigma 150 and 105), so
  probably real; Kenko TC-1.4 in the same dataset reads at
  nominal 1.4, so it's TC-specific not host-lens-specific.

## Failure modes & remediation

* **Step 1 hung/dead**: `kill <pid>; uv run python -m
  archive_2026_05.archive_to_nfs` to resume.
* **Step 2 too many LOW configs**: inspect the `algo_n_lines` and
  `algo_cross_check_period_px` columns. If many configs have
  `n_lines < 5`, the wafer-mask threshold may have moved
  (background brightness changed between shoot sessions). The
  `detect_wafer_mask` percentile is the knob (currently 50.0).
* **Step 3 EXIF reads fail**: confirm `exiftool` is on PATH; check
  one JPEG with `exiftool -FocalLength <file>` manually.
* **Step 4 "mixed (mag, focal)" refusal**: a slug has more than
  one (mag, focal) — shouldn't happen for 2026-05-13 production
  but could indicate a step-3 bug. Inspect the slug's F-dirs;
  rename the malformed file by hand or split the slug.
* **Broken symlinks after step 4**: the merge-source dirs in
  2026-05-12 must still exist with the `<slug> (<sid>)` naming.
  `find 2026-05-1[23] -xtype l` lists broken; manually trace
  back to a missing or renamed source.
