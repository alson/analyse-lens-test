# 2026-05 merge audit — pre-archive cleanup

Source: `~/macro-lens-test-output/`. Document generated 2026-05-15
and updated 2026-05-15 with the cleanup-session decisions. Intended
as the source-of-truth input for the archive-to-NFS script described
in `~/.claude/plans/effervescent-jingling-newt.md`.

## TL;DR

- **Actions completed 2026-05-15** (this session):
  - Three abandoned/empty subdirs deleted (D3, see below).
  - `2026-05-14_213530` relabeled `+ 61mm extension` →
    `+ Canon 500D + 61mm extension` after visual evidence that the
    500D was on. The previous chat's relabel of `2026-05-14_222616`
    missed this session because its `session.json` had empty
    `lens_configs`.
- **Decisions made 2026-05-15**:
  - D1 (61mm stowaway): resolved — `15_093455`'s 61mm sub-config is
    the sole `100-400 + 61mm` (without 500D) shoot. No merge needed,
    no duplicate.
  - D2.a (MC 105 + 61mm): pick `2026-05-06_231805` (1866 rows) as
    canonical, supersede the other four.
  - D2.b (`100-400 + Canon 500D` (bare) duplicate): keep both;
    `14_203311` is canonical, `14_222616/...(duplicate)` keeps the
    suffix as-is. No merge.
  - D2.c (`100-400 + Canon 500D + 61mm` duplicate, newly created by
    today's relabel): keep `14_222616 c1` canonical; mark
    `14_213530` superseded. Merge attempt **rejected** — see profile
    analysis under "Merge feasibility" below.
- **Decisions still open**: D2.d (Sigma 150 + 5T canonical pick),
  D4 (pre-cascade-rewrite MC 105 shoots), D5 (archive routing
  model).

## Actions completed today

### Subdirs deleted (D3)

Each had zero sweep rows; calibration JPEGs only.

| Path | Reason |
|---|---|
| `2026-05-14_194528/NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D/` | Aborted 500D shoot; the real bare-500D dataset is `14_203311`. |
| `2026-05-15_112642/NIKKOR Z 100-400mm f_4.5-5.6 VR S/` | Empty (0 B). Bare 100-400 was actually shot later in `15_121418`. |
| `2026-05-13_173213/Sigma APO Macro 150mm F2.8 EX DG OS HSM + 6T + 5T/` | 34 cal rows only; the `+ 5T + 6T` sibling in the same session has the real data. |

### Relabel: `2026-05-14_213530`

Was originally `NIKKOR Z 100-400mm f_4.5-5.6 VR S + 61mm extension`.
The Canon 500D was physically on the lens during this shoot — the
user discovered the mistake around midnight (`2026-05-15T00:08Z`)
and asked the then-current chat to relabel all 500D-mislabeled
shoots; that chat's grep on `session.json` missed this session
because its `lens_configs` array was empty (the slug only existed
in `shots.csv`).

Visual confirmation: the `cal_f_11_00.jpg` framing in `14_213530`
shows a tight crop of a single die region with no wafer edges —
matching `14_222616`'s known `+ Canon 500D + 61mm extension`
framing. The May 15 reshoots (`15_093455 + 61mm`, `15_093455 +
35mm`, `15_112642 + 35mm`) all show the full wafer fragment with
the silver substrate visible, confirming the 500D was off for
those.

Changes:

- Folder renamed `+ 61mm extension` → `+ Canon 500D + 61mm extension`.
- `shots.csv`: 211 rows updated.
- `session.json`: `lens_configs` populated with the new slug,
  `magnification: 1.5`, `widest_aperture: 5.6` (matching the
  paired `14_222616 c1` entry).

## The 2026-05-14/15 100-400 + 500D sequence

User's intended sequence vs. the actually-captured data:

| # | Intended | Session | Original slug | Final slug | Notes |
|---|---|---|---|---|---|
| 1 | 100-400 + 500D | `14_203311` | `... + Canon 500D` | unchanged | deliberate, 156 sweep |
| 2 | 100-400 + 61mm (500D **left on**) | `14_213530` | `... + 61mm extension` | `... + Canon 500D + 61mm extension` | relabeled today; sweep truncated mid-rise |
| 2 | 100-400 + 61mm (500D **left on**) | `14_222616 c1` | `... + 61mm extension` | `... + Canon 500D + 61mm extension` | relabeled by previous chat 2026-05-15T00:10Z; clean bell |
| 3 | 100-400 + 35mm (500D **left on**) | `14_222616 c2` | `... + 35mm extension` | `... + Canon 500D + 35mm extension` | relabeled by previous chat |
| 4 | 100-400 bare (500D **left on**) | `14_222616 c3` | `100-400 ... VR S` | `... + Canon 500D (duplicate)` | relabeled by previous chat |
| — | *midnight: user discovers 500D was on all along* | | | | |
| 5 | 100-400 + 61mm (correct) | `15_093455 c1` | `... + 61mm extension` | unchanged | 147 sweep |
| 6 | 100-400 + 35mm (correct, anchor) | `15_093455 c2` | `... + 35mm extension` | unchanged | 198 sweep; feeds `merged_100-400-35mm_2026-05-15` |
| 6 | 100-400 + 35mm (correct, redo) | `15_112642` | `... + 35mm extension` | unchanged | 243 sweep; feeds same merge |
| 7 | 100-400 bare (correct) | `15_121418` | `100-400 ... VR S` | unchanged | 579 sweep |

After today's relabel, the duplicate situation for the May-14
100-400 cluster is:

- `100-400 + Canon 500D` (bare): `14_203311` canonical, `14_222616 c3` keeps `(duplicate)` suffix. **Keep both.**
- `100-400 + Canon 500D + 61mm extension`: `14_222616 c1` canonical, `14_213530` superseded (truncated). **No merge.**
- `100-400 + Canon 500D + 35mm extension`: only `14_222616 c2`. **No duplicate.**
- `100-400 + 61mm extension` (no 500D): only `15_093455 c1`. **No duplicate, no merge.**
- `100-400 + 35mm extension` (no 500D): `15_093455 c2` + `15_112642`, already in `merged_100-400-35mm_2026-05-15`.
- `100-400` (bare): only `15_121418`. **No duplicate.**

## Merge feasibility — `100-400 + Canon 500D + 61mm extension`

After today's relabel, two sessions share this slug:
`2026-05-14_213530` and `2026-05-14_222616 c1`. They're adjacent
in time (21:38–21:59 then 22:28–22:52, nothing physical between),
so by the audit's adjacency rule they were merge candidates.

Offline center-crop JPEG-size sharpness analysis (the same metric
the live `range_check` uses) on both sessions across f/5.6, f/8,
f/11, f/16:

| Aperture | `14_213530` peak rail | `14_222616` peak rail | shape |
|---|---|---|---|
| f/5.6 | −3.332 mm *(end of range)* | −2.755 mm (parabolic fit) | 213530 monotonic rise 156k→208k; 222616 clean bell 177k→252k→157k |
| f/8 | −3.147 mm *(end of range)* | −2.740 mm | 213530 monotonic; 222616 sharp bell to 292k |
| f/11 | −3.147 mm *(end of range)* | −2.896 mm | 213530 monotonic; 222616 clean bell |
| f/16 | −2.962 mm *(end of range)* | −3.063 mm | 213530 monotonic; 222616 clean bell |

Verdict: **do not merge.** `14_213530` is truncated — its actual
focus peak lies beyond −3.3 mm and was never captured. The data is
entirely pre-peak rising slope. `14_222616` covers the same
pre-peak region (steps 7–14) more completely AND captures the
actual peak AND the post-peak fall. Apparent offsets between the
two sessions are inconsistent across apertures (−0.58, −0.41, −0.25,
+0.10 mm), confirming the curves represent different
rail-zero / framing references rather than the same setup with a
clean offset. The user evidently re-jogged the rail before
starting `14_222616` (it begins at rail −1.296 mm rather than 0).

Disposition: `14_222616 c1` is the canonical `100-400 + Canon 500D
+ 61mm extension`. `14_213530` is a superseded early attempt —
archive for traceability, do not route into the lens layout.

No prior offset analysis found in `~/.claude/projects/.../*.jsonl`
(searched `6c39b25d`, `777e225d`); the analysis above was the
first.

## All 2026-05 sessions classified

### Aborted / empty / test (skip during archive)

Either no `shots.csv` rows, `ended_at` unset, or `lens_config_slug`
populated only with "test"/"test2"/etc. (the early-May calibration
runs while developing the system).

`2026-05-05_125142` (empty), `2026-05-05_132309` (empty),
`2026-05-05_132950` (empty), `2026-05-05_141959` (slug "test"),
`2026-05-05_153748` (slugs "test2", "test3"), `2026-05-05_155939`
(slug "test4"), `2026-05-05_160542` (slug "test4"),
`2026-05-05_161412` (slug "test5"), `2026-05-05_164532` (slug
"test6"), `2026-05-05_171022` (slug "test7"), `2026-05-05_172105`
(slug "test8"), `2026-05-05_181637` (empty), `2026-05-05_181932`
(no sweep; only reshoot/cal, abandoned), `2026-05-05_183757` (no
sweep, abandoned), `2026-05-05_203701` (no sweep), `2026-05-05_210946`
(empty), `2026-05-05_211044` (empty), `2026-05-05_211909` (no
sweep), `2026-05-06_174107` (empty), `2026-05-06_174749` (4 sweep,
abandoned), `2026-05-06_194546` (empty), `2026-05-07_163258`
(empty), `2026-05-12_200117` (empty), `2026-05-13_172557` (empty),
`2026-05-13_172948` (empty), `2026-05-14_114807` (2 reshoot, slug
populated but no sweep — abandoned), `2026-05-14_122853` (same).

### Sessions that fed a merge

| session | feeds | other configs in same session? |
|---|---|---|
| `2026-05-08_175556` | `merged_24-120_2026-05-08` | none |
| `2026-05-08_201054` | `merged_24-120_2026-05-08` | none |
| `2026-05-10_164247` | `merged_viltrox-85_2026-05-10` | none |
| `2026-05-10_205515` | `merged_viltrox-85_2026-05-10` | none |
| `2026-05-10_212105` | `merged_viltrox-85_2026-05-10` (2 slugs) | none |
| `2026-05-14_174547` | `merged_100-400-6T_2026-05-14` | none |
| `2026-05-14_184841` | `merged_100-400-6T_2026-05-14` | none |
| `2026-05-14_194528` | `merged_100-400-6T_2026-05-14` | (abandoned `+ Canon 500D` subdir already deleted) |
| `2026-05-15_093455` | `merged_100-400-35mm_2026-05-15` | **completed `+ 61mm extension` (sole shoot of that config)** |
| `2026-05-15_112642` | `merged_100-400-35mm_2026-05-15` | (abandoned bare `100-400` subdir already deleted) |

### Standalone completed sessions

Lens-config slug → session id → row counts (sweep / reshoot /
extension / probe / cal).  ⭐ = canonical pick; ⛔ = superseded by
canonical, archive for traceability only.

- `NIKKOR Z MC 105mm f_2.8 VR S + 61mm extension`
  - ⛔ `2026-05-05_133416` (50/0/10/10/10) — dev-era, pre-cascade-rewrite
  - ⛔ `2026-05-05_175758` (18/26/0/0/35) — dev-era
  - ⛔ `2026-05-05_205830` (75/0/0/0/16) — dev-era
  - ⛔ `2026-05-06_175727` (782/22/0/0/11) — pre-cascade, and the
    lens was physically swapped to `+ 5T + 6T` between this and the
    23:18 shoot (session `2026-05-06_200150`), so the two big May 6
    runs are *not* a mergeable adjacent pair
  - ⭐ `2026-05-06_231805` (1790/47/0/0/11) — 9-hour overnight
    sweep, the keeper
- `NIKKOR Z MC 105mm f_2.8 VR S + 5T + 6T` / `+ 6T + 5T` —
  `2026-05-06_200150` (two configs, 683 / 919 sweep).
  `2026-05-06_225632` (55 sweep, 24 reshoot — abandoned redo).
- `NIKKOR Z MC 105mm f_2.8 VR S + 45mm extension` —
  `2026-05-07_082105` (2146 sweep)
- `NIKKOR Z MC 105mm f_2.8 VR S + 35mm extension` —
  `2026-05-07_163659` (1764 sweep)
- `NIKKOR Z 24-120mm f_4 S + 61mm extension` (small early shoots) —
  `2026-05-08_170101` (294 sweep), `2026-05-08_173604` (51 sweep —
  probably abandoned), `2026-05-08_174545` (40 sweep — abandoned).
  *These predate the merged 24-120 dataset; the merge supersedes
  them.* **Open: archive for traceability or skip?**
- `NIKKOR Z 24-120mm f_4 S + 45mm extension` —
  `2026-05-11_161129` (1326 sweep)
- `NIKKOR Z 24-120mm f_4 S + 35mm extension` /
  `Viltrox 85mm f_2 EVO + 45mm extension` —
  `2026-05-11_185420` (two configs: 825 / 246 sweep)
- `Viltrox 85mm f_2 EVO + 26mm extension` /
  `NIKKOR Z 24-120mm f_4 S + 10mm extension` —
  `2026-05-11_220431` (two configs: 195 / 318 sweep)
- `NIKKOR Z 24-120mm f_4 S` —
  `2026-05-12_000950` (435 sweep)
- `Nikon Micro-Nikkor 55mm f_2.8 AIS — serial 287318` —
  `2026-05-12_201123` (300 sweep)
- `Sigma Macro 105mm F2.8 EX DG OS HSM + 5T + 6T` —
  `2026-05-12_214838` (450 sweep)
- `Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T + 6T` —
  `2026-05-13_173213` (483 sweep; the empty `+ 6T + 5T` sibling
  subdir was deleted 2026-05-15 — see D3 above)
- `Sigma APO Macro 150mm F2.8 EX DG OS HSM` (bare) / `+ 5T` / `+ 6T` /
  `+ 6T + 5T` — `2026-05-13_230021` (four configs in one session:
  252 / 567 / 504 / 306 sweep). The biggest session at 42 GB.
- `Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T` —
  `2026-05-14_132004` (273 sweep). **Open D2.d:** possibly a redo
  of `13_230021 + 5T` (567 sweep) — pick canonical.
- `Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 6T + 5T` —
  `2026-05-14_135837` (423 sweep)
- `Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + 5T + 6T` /
  `Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED` (bare) —
  `2026-05-14_151018` (two configs: 201 / 177 sweep)
- ⭐ `NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D` —
  `2026-05-14_203311` (156 sweep). Canonical 500D-bare.
- ⛔ `NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D + 61mm extension` —
  `2026-05-14_213530` (192 sweep, **truncated**; relabel done
  today). Superseded by `14_222616 c1`.
- `NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D + 35mm extension` /
  `+ Canon 500D (duplicate)` / `+ Canon 500D + 61mm extension` —
  `2026-05-14_222616` (three configs: 189 / 168 / 168 sweep).
  ⭐ `... + 500D + 61mm extension` is the canonical 500D+61mm.
  ⭐ `... + 500D + 35mm extension` is the only 500D+35mm.
  The `(duplicate)` slug is the keeper-as-duplicate, by design.
- `NIKKOR Z 100-400mm f_4.5-5.6 VR S` (bare) —
  `2026-05-15_121418` (579 sweep, the latest bare 100-400)

## Remaining open decisions

### D2.d. `Sigma 150 + 5T` canonical pick

In both `2026-05-13_230021` (567 sweep) and `2026-05-14_132004`
(273 sweep). The 230021 one has more rows; the 132004 one is
isolated (single-config session, perhaps a deliberate redo).
Decision needed before archive routing.

### D4. Pre-cascade-rewrite shoots (2026-05-06 / 2026-05-07)

The DESIGN_NOTES §6.33 cascade rewrite landed mid-May. The big
2026-05-06 and 2026-05-07 MC 105 shoots (782 / 1790 / 2146 / 1764
sweep rows) predate that fix and may have calibration-drift
artefacts. Default plan: archive them anyway — the data exists
and may be the only record of those configs.

### D5. Routing model for the archive script

Two routing models for the archive step:

- **Session-level routing.** Whole sessions copy to one date dir.
  The 61mm sole-shoot in `2026-05-15_093455` either gets sorted
  alongside everything else in the final lens layout (treating its
  parent session as a multi-config completed shoot), OR stays
  buried in the raw archive only.
- **Lens-config-level routing.** Each `<session>/<lens-config>/`
  subdir is the unit. Same-session multi-configs naturally split.
  `shots.csv` gets sliced per lens-config at archive time. Cleaner
  story, slightly more code.

Lens-config-level routing handles the canonical/superseded
distinctions above cleanly: each config gets a "canonical pick"
decision regardless of which session it lives in.

## Source data references

- All session metadata: `~/macro-lens-test-output/<session>/session.json`
- All capture metadata: `~/macro-lens-test-output/<session>/shots.csv`
- Merge metadata: `~/macro-lens-test-output/merged_*/session.json`
- Merge tool: `~/shared/projects/personal/fotografie/run-lens-test/tools/merge_sessions.py`
- Existing archive layout examples:
  `~/shared/files/pics/digikam/test-raw-data/2026-01-29/` and
  `2026-02-18/`
- Broader plan in flight:
  `~/.claude/plans/effervescent-jingling-newt.md`
