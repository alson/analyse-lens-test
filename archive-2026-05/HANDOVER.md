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

## What's running right now

A `uv run python -m archive_2026_05.archive_to_nfs` is executing
on bumblebee, started 2026-05-15 23:58 (was killed at some point
and restarted 02:00 next day — design is idempotent so the
restart resumed cleanly via skip-existing). Output goes to
`/tmp/archive_2026_05.log` (Python in `-u` unbuffered mode).

**Check progress:**
```sh
ps -ef | grep archive_to_nfs                                       # is it alive?
du -sh ~/shared/files/pics/digikam/test-raw-data/2026-05-1[23]     # bytes landed
grep -cE '^  \[2026-05-1[23]\]' /tmp/archive_2026_05.log           # new copies
grep -cE '^  \[skip-existing\]' /tmp/archive_2026_05.log           # skips
tail /tmp/archive_2026_05.log                                      # latest activity
```

**Expected final state:** ~21 dirs under 2026-05-12 + ~31 dirs
under 2026-05-13. Manifest in `archive_2026_05.manifest.ENTRIES`
defines exactly what — see `__post_run_verification` below.

**If it fails or hangs**: kill the python process, then re-invoke
the same command. Skip-existing logic re-uses already-landed dirs;
no double-copy. The user mentioned plugging in a wired LAN cable
during the run — NFS hiccup during reconnect is benign.

## Post-step-1 verification

When the copy finishes (it logs an "== Summary ==" block at the
end), run:

```sh
cd analyse-lens-test/archive-2026-05
uv run python -m archive_2026_05.archive_to_nfs --verify-only
# Expect: 0 broken symlinks under 2026-05-13/
find ~/shared/files/pics/digikam/test-raw-data/2026-05-1[23] -xtype l | wc -l
# Expect: 0
```

If verify reports broken symlinks: investigate before running
step 2. The four merged dirs (`merged_24-120_2026-05-08`,
`merged_viltrox-85_2026-05-10`, `merged_100-400-6T_2026-05-14`,
`merged_100-400-35mm_2026-05-15`) end up as symlinks back into
`2026-05-12/<slug> (<src_session>)/` paths; broken links mean a
merge-source dir is missing.

## Running steps 2-4

These need numpy + scipy + Pillow + scikit-image (in the
`pyproject.toml` deps) plus `exiftool` on the PATH (step 3 reads
EXIF focal lengths).

```sh
# Step 2: build the magnification manifest for 2026-05-13.
uv run python -m archive_2026_05.measure_wafer_squares prepare \
    --root ~/shared/files/pics/digikam/test-raw-data/2026-05-13 \
    --out /tmp/wafer-manifest-2026-05-13.csv \
    --anchor "Sigma APO Macro 150mm F2.8 EX DG OS HSM"
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
    --anchor "Sigma APO Macro 150mm F2.8 EX DG OS HSM"
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

  Multi-aperture cross-check (added later) would have flagged the
  over-correction up front — F11 disagreed with F16/F8.5 by 32%.
  See ANALYSIS_NOTES.md §7a.4 + §7a.7 for the full reasoning.
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

1. **Watch for step 1 to finish** (1-3 more hours when this was
   handed over). When done, run `--verify-only` and the
   `find -xtype l` check.
2. **Run step 2** with `prepare`, eyeball the manifest, fill
   `visual_count` for any LOW/MEDIUM-confidence rows by viewing
   the sharpest-f/11 frame (use the Read tool on the image path
   in the manifest), then `evaluate`.
3. **Run step 3** (dry-run first, then real).
4. **Run step 4** (dry-run first, then real).
5. **Generate the resized + cropped siblings** via the existing
   `make-crop-for-every-lens-magnification-focal-length-aperture.sh`
   inside each `2026-05-13/<slug>/` dir.
6. **End-to-end spot-check**: pick one merged-dir slug
   (e.g. `2026-05-13/NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension/`),
   verify the symlinks still resolve back into 2026-05-12 after
   the sort.

## Open questions for the next session

None currently open. The Q3/Q4 plan questions and D1-D5 audit
decisions are all resolved (see plan file). The algorithm
investigation is concluded; further refinements would be
diminishing returns.

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
