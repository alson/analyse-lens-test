# archive-2026-05

Pipeline that archives the 2026-05 lens-test shoots from
`~/macro-lens-test-output/` to the NFS test-raw-data tree
(`~/shared/files/pics/digikam/test-raw-data/`) and brings them into
the existing `<lens>/<mag>/<focal>/<F>/` Digikam layout. Driven by
the per-config classifications in
`../merge-audit-2026-05.md`.

Four steps, in order:

1. **`archive_to_nfs.py`** (bumblebee) — copy step. Routes per the
   audit's ⭐/⛔/merge-source classification. Already runnable.
2. **`measure_wafer_squares.py`** (nufan) — TODO. Vision-based
   per-config magnification verification against the Sigma 150 1:1
   reference, sanity-checked vs `reshoot-plan-2026-05.md`.
3. **`rename_for_digikam.py`** (nufan) — TODO. Applies the
   `NNNNN|<slug>|<mag>|<focal> mm|F<n>|<orig>.jpg` filename
   convention. Sequence by `rail_position_mm` ascending.
4. **`sort_to_lens_tree.py`** (nufan) — TODO. Collapses session
   grouping into the final `<lens>/<mag>/<focal>/F<n>/` tree.

## Usage (step 1)

```sh
cd analyse-lens-test/archive-2026-05
uv sync

# Dry-run (preferred first pass — prints actions, copies nothing):
uv run python -m archive_2026_05.archive_to_nfs --dry-run

# Verify-only (enumerates planned actions + broken-symlink check):
uv run python -m archive_2026_05.archive_to_nfs --verify-only

# Real copy:
uv run python -m archive_2026_05.archive_to_nfs

# Custom roots:
uv run python -m archive_2026_05.archive_to_nfs \
    --source-root /some/where \
    --nfs-root /some/where/else
```

The script is idempotent — destinations that already exist (with
contents) are skipped, so an interrupted run can be resumed by just
re-running it.

## Manifest

`src/archive_2026_05/manifest.py` encodes the audit's decisions as
Python data. **If the audit doc changes, update the manifest to
match and re-run the script.** The audit is the human-readable
source-of-truth; the manifest is the machine-readable view.

Roles:

- `canonical` — ⭐ pick, goes to `2026-05-13/<slug>/` (flat slug-level,
  matching the existing `test-raw-data/2026-01-29/<slug>/...`
  convention).
- `superseded` — ⛔ kept-for-traceability, goes to
  `2026-05-12/<slug> (<sid>)/`. The `(session_id)` suffix
  disambiguates same-slug entries (e.g. four dev-era ⛔ MC 105 + 61mm
  shoots).
- `merge_source` — feeds a `merged_X/` dir; same destination shape
  as `superseded`. The merged dir's relative symlinks get rewritten
  to point at this path.
- `labeled_duplicate` — deliberate-by-design duplicate (e.g.
  `+ Canon 500D (duplicate)`); routed like `canonical`.

Plus `SKIP_SESSIONS` (aborted/empty/test runs) and `MERGED_DIRS`
(the four merged outputs — each lands at
`2026-05-13/<output_slug>/`).

Provenance — which session each archived dir came from — lives in
the per-dir `metadata.json`, not in the path.

## Tests

```sh
uv run pytest
```

Tests cover the pure helpers (CSV slicing, metadata building,
symlink-target parsing + rewriting) and the manifest's
consistency (no entries in the skip list; role-count totals match
the audit).
