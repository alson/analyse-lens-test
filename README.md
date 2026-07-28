# Lens-test analysis

Offline tooling and research notes for analysing lens-test captures from two
different rigs:

- a **macro focus-rail rig** photographing a patterned silicon wafer; and
- **long-distance natural-target tests** for telephoto, wide-angle, and standard
  lenses.

The repository is an analysis workspace rather than a single application. It
contains Python subprojects, one-off data-preparation scripts, generated result
tables, and the methodology record behind the current conclusions. The image
datasets are stored outside Git.

## Start here

Choose the analysis track that matches the capture:

| Track | Purpose | Entry point |
|---|---|---|
| Macro-wafer sharpness | Through-focus measurement, tile/field analysis, and cross-configuration relative MTF | [`tile-sharpness/README.md`](tile-sharpness/README.md) |
| Long-distance sharpness | Natural-target analysis across lenses, dates, camera bodies, and teleconverters | [`longdist-sharpness/README.md`](longdist-sharpness/README.md) |
| Wafer registration | Coordinate system, feature catalogue, and automatic/anchor-based registration | [`wafer-atlas/README.md`](wafer-atlas/README.md) |
| Bellows calibration | Empirical effective-aperture calibration for extension-tube configurations | [`bellows-calibration/README.md`](bellows-calibration/README.md) |
| Focus-rail coverage | Detect truncated or off-target focus sweeps and render an HTML report | [`rail-coverage/`](rail-coverage/) |
| Crop/resample preparation | Lossless JPEG crops and controlled resizing for visual comparisons | [`resize-bulk/`](resize-bulk/) |

For the current state and open follow-ups, read the relevant handover:

- [`tile-sharpness/HANDOVER.md`](tile-sharpness/HANDOVER.md) for macro-wafer
  analysis;
- [`longdist-sharpness/docs/LONGDIST_HANDOVER.md`](longdist-sharpness/docs/LONGDIST_HANDOVER.md)
  for long-distance analysis; and
- [`wafer-atlas/HANDOVER.md`](wafer-atlas/HANDOVER.md) for wafer registration.

The cross-project conventions in [`CLAUDE.md`](CLAUDE.md) are part of the
methodology. In particular, read
[`LEADING_WITH_CAVEATS.md`](LEADING_WITH_CAVEATS.md) before treating an
exploratory result as a final verdict.

## Repository map

```text
.
├── tile-sharpness/       macro-wafer sharpness package and production pipeline
├── wafer-atlas/          wafer geometry, feature catalogue, and registration
├── longdist-sharpness/   long-distance analysis scripts and result documents
├── bellows-calibration/  effective-aperture measurements and rename plans
├── rail-coverage/        focus-sweep coverage analyser
├── resize-bulk/          lossless crop and resampling utilities
├── archive-2026-05/      provenance-preserving archive pipeline snapshot
├── *.sh / *.py           older preparation, rename, sort, crop, and HTML tools
└── *.md                  cross-cutting methodology and campaign notes
```

The root scripts predate the packaged analysis pipelines. Some remain useful
for capture preparation, but inspect their headers and dry-run support before
using them on a dataset. For example,
[`rename_and_sort_lens_test.py`](rename_and_sort_lens_test.py) is dry-run by
default, while several older shell scripts move or copy files directly.

## Environment

Python subprojects use [uv](https://docs.astral.sh/uv/) and currently require
Python 3.14 or newer. Each subproject has its own `pyproject.toml`, lockfile,
and environment; there is no root Python package.

The macro packages also depend on the sibling checkout
`../../lens-test-detect-core`. Run commands from the subproject directory so
uv resolves the intended project:

```sh
cd tile-sharpness
direnv allow
direnv exec . uv sync
direnv exec . uv run pytest -q
```

The `.envrc` files put virtual environments in a host-local cache. This avoids
sharing compiled wheels between the Arch Linux workstation and Ubuntu compute
host over NFS. See [`COMPUTE.md`](COMPUTE.md) for the shared-data layout and the
canonical `ssh nufan` invocation. CPU-heavy extraction and registration jobs
should run on `nufan`.

Some preparation scripts additionally require system tools such as Exiv2,
ExifTool, GraphicsMagick, darktable, or `mtf_mapper`; requirements are
documented by the script or subproject that invokes them.

## Typical commands

List and analyse a macro-wafer sweep:

```sh
cd tile-sharpness
direnv exec . uv run tile-sharpness list-sweeps
direnv exec . uv run tile-sharpness analyse <unique-sweep-substring> \
  --out out/
```

Run the production multi-session relative-MTF pipeline:

```sh
cd tile-sharpness
direnv exec . uv run tile-sharpness relmtf-extract \
  --subset data/cross_m_relative_mtf_subset_multisession.csv \
  --out out_relmtf_multisession \
  --shard 0/1
direnv exec . uv run tile-sharpness relmtf-analyse \
  --subset data/cross_m_relative_mtf_subset_multisession.csv \
  --out out_relmtf_multisession \
  --tier rail-coverage
```

Run one long-distance dataset analysis:

```sh
cd longdist-sharpness
direnv allow
direnv exec . uv sync
direnv exec . uv run python scripts/poc_longdist_algorithms.py \
  wide2026_01_24
```

Build a focus-coverage report:

```sh
cd rail-coverage
direnv allow
direnv exec . uv sync
direnv exec . uv run rail-coverage --help
```

Most analysis scripts write to `out/` or a sibling `*_out/` directory. Large,
regenerable intermediates are ignored; small reports, summary CSVs, and
methodology notes are retained in Git as evidence.

## Data assumptions and interpretation

The main capture data lives outside this repository:

- newer macro-rig captures: `~/macro-lens-test-output/<session>/` on the local
  capture host;
- mirrored analysis data:
  `~/shared/files/pics/digikam/test-raw-data/<date>/`; and
- older manual sweeps below the same shared `test-raw-data` tree.

Before comparing results, keep these constraints explicit:

- **Do not mix the two rigs.** `tile-sharpness` is for the macro-wafer target;
  `longdist-sharpness` is for distant natural targets.
- **Measure native frames.** Resized cohorts are for visual comparison only;
  resampling alters edge contrast and sharpness metrics.
- **Compare in subject space across magnifications.** Macro cross-configuration
  comparisons use subject-space MTF50 or the documented relative-MTF pipeline,
  not raw sensor-pixel values.
- **Use measured magnification and effective aperture.** Macro analysis depends
  on the measured per-configuration magnification and, where available, the
  exact values in `effective_apertures.csv`. Aperture folder labels are already
  bellows-corrected; do not apply the factor again.
- **JPEG filesize is only a fallback.** It can help within a fixed-framing focus
  sweep, but it is not a valid primary metric across lenses or configurations.
- **Off-target tiles are geometry, not capture failures.** Exclude them from
  focus-peak analysis; do not automatically classify them as reshoots.
- **Camera/dataset families are not automatically comparable.** JPEG settings,
  pixel pitch, scene content, sampling, wind, and focus coverage can change the
  scale or validity of a metric.
- **Lead with tested conditions and gaps.** Report a negative result as negative
  under the tested conditions, with untested assumptions stated alongside it.

The rationale and empirical evidence are in
[`SHARPNESS_METRICS.md`](SHARPNESS_METRICS.md),
[`ANALYSIS_NOTES.md`](ANALYSIS_NOTES.md), and the method-specific documents
linked from each subproject README.

## Validation

Run tests independently per maintained package:

```sh
(cd tile-sharpness && direnv exec . uv run pytest -q)
(cd wafer-atlas && direnv exec . uv run pytest -q)
(cd rail-coverage && direnv exec . uv run pytest -q)
python3 -m pytest -q test_rename_and_sort_lens_test.py
```

Some tests and scripts require the external NFS datasets and will skip or fail
meaningfully when those inputs are unavailable. A successful unit-test run
does not validate a generated report: inspect the output tables, diagnostic
crops, and plots for the analysed cohort.

## Project history

The initial May 2026 import collected existing lens-test preparation scripts.
Subsequent work added focus-rail coverage analysis, lossless crop generation,
macro-wafer MTF methods, empirical bellows calibration, wafer-atlas
registration, and a separate long-distance pipeline. Later commits repeatedly
revised conclusions when sampling, registration, target choice, camera
differences, or weather exposed a hidden assumption. The checked-in handovers,
reports, and small result artifacts are therefore intentional: they record not
only the current method, but why earlier approaches were superseded.
