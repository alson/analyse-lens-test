# Bellows-factor calibration for Z-mount + extension tubes

Empirical bellows-factor calibration for the extension-tube
configurations used in the 2026-02-18 and 2026-05-13 lens-test
datasets. The point of this work: the camera-reported f-number
on Z-mount lenses **does not include** the bellows contribution
from external extension tubes — so cross-config comparisons by
reported aperture mix different effective f-numbers. This package
measures the true effective f-number for each configuration so the
test-raw-data trees can be renamed to use effective f-numbers.

## Contents

| Path | What |
|---|---|
| `data/per_shot.csv` | EXIF + linear-light center brightness for every validation JPG. Skips the abandoned cloud-with-tube shots. |
| `data/tube_assignments.csv` | Per-group manual mapping `(lens, focal, group_first_file) → tube_mm`, derived from shot sequencing. |
| `data/per_config.csv` | Per-(lens, focal, tube) bellows multiplier and effective-f for every reported aperture. Generated. |
| `data/rename_plan_2026-01-29.csv` | F-dir rename mapping for the 2026-01-29 tree (no on-disk renames — bare 100-400 correction below half-stop quantization). |
| `data/rename_plan_2026-02-18.csv` | F-dir rename mapping for the 2026-02-18 tree (canonical). |
| `data/rename_plan_2026-05-13.csv` | F-dir rename mapping for the 2026-05-13 tree (canonical, with 100-400/Viltrox corrections folded in). |
| `data/rename_plan_*_v1.csv` | Historical first-generation plans archived for provenance. |
| `data/delta_plan_2026-05-13.csv` | Secondary rename plan applied after the v1 rename to correct 100-400 + ext and Viltrox + ext F-dirs whose corrected half-stop snap differed. |
| `data/rename_manifest_*.csv` | Per-row status manifests written by `apply_rename_plan.py` at execute time. |
| `scripts/measure_brightness.py` | Extracts EXIF + Y_linear_center from a directory of JPGs. |
| `scripts/build_calibration.py` | Aggregates per_shot.csv + tube_assignments.csv into per_config.csv. |
| `scripts/build_rename_plan.py` | Walks an existing data tree and outputs the F-dir rename plan. |
| `scripts/recompute_plan.py` | Recomputes a rename plan's new_path / new_F_dir using updated multipliers from per_config.csv, keeping the original orig_path. Used when the multipliers improve after a plan was already applied. |
| `scripts/build_delta_plan.py` | Diffs an applied plan against a recomputed plan and emits a (applied_new → corrected_new) delta rename for rows whose half-stop snap differs. |
| `scripts/apply_rename_plan.py` | Applies a rename plan via two-pass-through-temp-suffix, rewrites the F-component embedded in filenames, writes an in-tree `.bellows-rename-applied.csv` for idempotency. |
| `scripts/build_effective_apertures.py` | Generates a per-tree `effective_apertures.csv` with the **un-rounded** effective f-number for every F-dir. Downstream code (diffraction limits, step-size estimation, etc.) reads this rather than re-interpreting the snapped F-dir name. |
| `docs/PROCEDURE.md` | How the validation shoot was conducted. |
| `docs/FINDINGS.md` | Analysis, per-lens behaviour, and the empirical calibration table. |

### In-tree outputs

After running the rename + effective-apertures scripts on a test-raw-data tree, the tree contains:

- `.bellows-rename-applied.csv` — provenance log of dir renames applied (idempotency marker)
- `effective_apertures.csv` — canonical lookup of every F-dir's *exact* effective f-number. Use this for any computation where precision matters; the F-dir name itself is only the snapped half-stop label.

## How to use

```sh
# Regenerate per_config.csv from per_shot.csv:
python3 scripts/build_calibration.py \
    --per-shot data/per_shot.csv \
    --tube-assignments data/tube_assignments.csv \
    --out data/per_config.csv

# Build/refresh rename plans:
python3 scripts/build_rename_plan.py \
    --calibration data/per_config.csv \
    --tree ~/shared/files/pics/digikam/test-raw-data/2026-05-13 \
    --out data/rename_plan_2026-05-13.csv

# Apply the rename. Default is dry-run; pass --execute to actually move.
python3 scripts/apply_rename_plan.py \
    --plan data/rename_plan_2026-05-13.csv \
    --tree ~/shared/files/pics/digikam/test-raw-data/2026-05-13 \
    --manifest data/rename_manifest_2026-05-13.csv
python3 scripts/apply_rename_plan.py \
    --plan data/rename_plan_2026-05-13.csv \
    --tree ~/shared/files/pics/digikam/test-raw-data/2026-05-13 \
    --manifest data/rename_manifest_2026-05-13.csv \
    --execute
```

The applier:

- Never deletes or overwrites data.
- Two-pass through a temporary suffix to handle within-slug chain
  renames like F4 → F5.6 → F7.1 where the intermediate name is also
  a source.
- Refuses any operation that would overwrite an existing file or dir.
- Writes a `.bellows-rename-applied.csv` in the tree root for
  idempotency: a re-run classifies previously-applied rows as
  `already_done`.
- Rewrites the embedded `|F<n>|` component in filenames inside each
  renamed F-dir for `.nef`, `.jpg`, `.xmp` and any other extension
  (the 2026-02-18 layout has this; the 2026-05-13 layout has
  `step_NNNN.jpg`-style filenames with no F-component, so only the
  directory is renamed there).

## Why no JPEGs are stored

The JPEG content is not needed once `y_lin_center_*` columns are
populated in `per_shot.csv`. Those values are gamma-decoded linear
luminance averages over the centre region, which fully characterise
the brightness of each shot for ratio-based bellows analysis. The
original NEFs live on the camera and will be wiped — this is fine,
the JPG-derived Y is sufficient.

## Caveats

* Brightness was measured on the JPG, not the raw NEF. Camera
  picture-control / D-Lighting effects are baked in, but they apply
  identically across all shots in a single session (constant settings
  in M-mode), so they cancel out of any brightness *ratio*.
* Manual flash power is not recorded in EXIF. We infer "same flash
  power" within a continuous lens block from constant bare-reference
  brightness; flash-power steps between blocks were normalised by
  using each block's own bare reference.
* The empirical multipliers below are valid for the **same body
  + same flash bounce geometry + same MFD focusing approach** used in
  the validation shoot. They are not strict optical first-principle
  values; they are best treated as practical calibration coefficients
  for these lenses on this rig.
