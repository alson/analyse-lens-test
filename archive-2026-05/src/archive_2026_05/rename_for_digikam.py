"""Step 3 — rename JPEGs into the existing Digikam pipe-separated
convention.

Reads the magnification manifest produced by step 2 (after vision
review has populated ``vision_measured_mag`` for low-confidence
rows, leaving the algorithmic ``algo_measured_mag`` for high-
confidence ones), then walks each lens-config directory in
``2026-05-13`` and renames every captured JPEG to:

  NNNNN|<slug>|<mag>|<focal> mm|F<n>|<orig>.jpg

where:

- ``NNNNN`` is a 5-digit sequence number per lens-config, ordered
  by ``rail_position_mm`` ascending (rail-zero = #1). For merged
  configs, this naturally orders across all source sessions
  because the merge tool unifies rail_position_mm.
- ``<slug>`` is the lens-config slug exactly as the runner stored
  it (underscore-quoted, e.g. ``f_4`` not ``f/4``).
- ``<mag>`` is the verified magnification rendered in the Digikam
  format: ``1_1``, ``1.3_1``, ``1_2.47``, ``2_1``.
- ``<focal> mm`` comes from EXIF ``Exif.Photo.FocalLength``, read
  once per lens-config (constant within a config). Format: one
  decimal + trailing ` mm`, e.g. ``105.0 mm``.
- ``F<n>`` is the aperture from ``shots.csv.aperture``, mapped to
  ``F<n>`` form (``f/5.6`` → ``F5.6``, ``f/11`` → ``F11``).
- ``<orig>`` is the original capture filename (e.g.
  ``step_0127.jpg`` or ``prev_step_0150.jpg`` from a merge).

Matching cropped JPEGs under each F-aperture's ``cropped/<region>/``
get the same new name. ``shots.csv``'s ``filename`` column updates
to match. The original session-grouping in ``2026-05-13/`` is
preserved by this step; step 4 (``sort_to_lens_tree.py``) is the
one that adds ``<mag>/<focal>/F<n>/`` subdirs.

Usage:

  python -m archive_2026_05.rename_for_digikam \\
      --root ~/shared/files/pics/digikam/test-raw-data/2026-05-13 \\
      --manifest /tmp/wafer-manifest.csv

  # Dry-run (recommended first pass):
  python -m archive_2026_05.rename_for_digikam ... --dry-run
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterable


# ---- Manifest reading ------------------------------------------------------


@dataclass(frozen=True)
class ManifestRow:
    slug: str
    mag_label: str
    claimed_mag: float
    image_path: str
    measured_mag: float | None   # the verified value to use


def _select_measured_mag(row: dict) -> float | None:
    """Choose the magnification value to use for the filename.

    Priority:
    1. ``vision_measured_mag`` — vision-verified, authoritative when present
    2. ``algo_measured_mag`` if ``algo_confidence`` == 'high'
    3. ``claimed_mag`` — fallback to path-encoded GT (or the user's
       claimed value from session.json)
    """
    vision = row.get("vision_measured_mag", "").strip()
    if vision:
        try:
            return float(vision)
        except ValueError:
            pass
    algo = row.get("algo_measured_mag", "").strip()
    conf = row.get("algo_confidence", "").strip()
    if algo and conf == "high":
        try:
            return float(algo)
        except ValueError:
            pass
    claimed = row.get("claimed_mag", "").strip()
    if claimed:
        try:
            return float(claimed)
        except ValueError:
            return None
    return None


def load_manifest(manifest_path: Path) -> dict[tuple[str, str], ManifestRow]:
    """Return ``{(slug, mag_label): ManifestRow}``."""
    rows: dict[tuple[str, str], ManifestRow] = {}
    with manifest_path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            slug = r["slug"]
            mag_label = r["mag_label"]
            mag = _select_measured_mag(r)
            try:
                claimed = float(r["claimed_mag"]) if r["claimed_mag"] else float("nan")
            except ValueError:
                claimed = float("nan")
            rows[(slug, mag_label)] = ManifestRow(
                slug=slug, mag_label=mag_label, claimed_mag=claimed,
                image_path=r.get("image_path", ""), measured_mag=mag,
            )
    return rows


# ---- Format helpers --------------------------------------------------------


def format_magnification(mag: float) -> str:
    """Render a magnification ratio in the Digikam ``<a>_<b>`` shape.

    Convention seen in existing 2026-01-29 / 2026-02-18 archives:
    - 1.0  → ``1_1``
    - 1.3  → ``1.3_1``
    - 0.4048... → ``1_2.47``     (sub-1:1 mag → ``1_<recip>``)
    - 2.0  → ``2_1``

    We pick whichever of ``mag_a/1`` or ``1/mag_a`` rounds cleaner —
    the smaller side gets the ``1``, the larger gets the actual
    number. Round the non-unity side to 2 decimals, then strip
    trailing zeros for cleanliness.
    """
    if mag <= 0 or mag != mag:                       # NaN / non-positive
        raise ValueError(f"invalid magnification: {mag!r}")
    if mag >= 1.0:
        numerator = mag
        denominator = 1.0
    else:
        numerator = 1.0
        denominator = 1.0 / mag

    def _fmt(x: float) -> str:
        # 2-decimal precision, strip trailing zeros, then trailing dot.
        s = f"{x:.2f}".rstrip("0").rstrip(".")
        return s or "0"

    return f"{_fmt(numerator)}_{_fmt(denominator)}"


_APERTURE_RE = re.compile(r"^f/(\d+(?:\.\d+)?)$", re.IGNORECASE)


def format_aperture(aperture_str: str) -> str:
    """``"f/5.6"`` → ``"F5.6"``; ``"f/11"`` → ``"F11"``."""
    m = _APERTURE_RE.match(aperture_str.strip())
    if not m:
        raise ValueError(f"unrecognised aperture: {aperture_str!r}")
    n = m.group(1)
    # Strip ".0" suffix for whole stops
    if n.endswith(".0"):
        n = n[:-2]
    return f"F{n}"


def format_focal_length(focal_mm: float) -> str:
    """``150.0`` → ``"150.0 mm"`` (one-decimal, trailing ' mm')."""
    return f"{focal_mm:.1f} mm"


_FILENAME_INVALID_RE = re.compile(r"[/\\<>:\"\|?*\x00-\x1f]")


def sanitise_filename_component(s: str) -> str:
    """Replace characters that are illegal in filenames on common
    filesystems with underscores. The slug already uses underscores
    where slashes would otherwise appear (``f_4`` for ``f/4``), so
    in practice this is a defensive no-op for typical inputs."""
    return _FILENAME_INVALID_RE.sub("_", s)


def build_digikam_name(
    seq: int, slug: str, mag_label: str, focal_mm: float,
    aperture: str, original_filename: str,
) -> str:
    """Compose the pipe-separated filename. The slug and original
    are sanitised in case any forbidden character sneaks in."""
    return "|".join([
        f"{seq:05d}",
        sanitise_filename_component(slug),
        mag_label,
        format_focal_length(focal_mm),
        format_aperture(aperture),
        sanitise_filename_component(original_filename),
    ])


# ---- EXIF + shots.csv helpers ---------------------------------------------


def read_focal_length_mm(jpeg_path: Path) -> float | None:
    """Read ``Exif.Photo.FocalLength`` via ``exiftool`` (subprocess).
    Returns the float value in mm, or None if not present."""
    try:
        out = subprocess.run(
            ["exiftool", "-FocalLength", "-n", str(jpeg_path)],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    # Format: "Focal Length                    : 150.0"
    m = re.search(r":\s*([\d.]+)", out.stdout)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


_SHOTS_COLUMNS_REQUIRED = ("rail_position_mm", "aperture", "filename")


def load_shots_csv(path: Path) -> tuple[list[dict], list[str]]:
    """Return (rows, fieldnames)."""
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    for col in _SHOTS_COLUMNS_REQUIRED:
        if col not in fieldnames:
            raise RuntimeError(
                f"{path}: missing required column {col!r}; have {fieldnames}"
            )
    return rows, fieldnames


def write_shots_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


# ---- Per-config renaming --------------------------------------------------


def _iter_lens_config_dirs(date_root: Path) -> Iterable[Path]:
    """Yield each ``<slug>/`` directory under ``date_root``."""
    for p in sorted(date_root.iterdir()):
        if p.is_dir() and not p.name.startswith(".") and not p.name.endswith("-resized"):
            yield p


def _iter_jpegs_in_aperture(ap_dir: Path) -> Iterable[Path]:
    """Yield all .jpg files in an aperture dir (NOT recursive — crops
    are handled separately to avoid double-renaming)."""
    for p in sorted(ap_dir.iterdir()):
        if p.is_file() and p.suffix.lower() == ".jpg":
            yield p


def _matching_cropped_paths(jpeg: Path, aperture_dir: Path) -> list[Path]:
    """For a top-level JPEG at ``aperture_dir/<filename>``, return all
    cropped/<region>/<filename> siblings that exist."""
    cropped_root = aperture_dir / "cropped"
    if not cropped_root.is_dir():
        return []
    matches: list[Path] = []
    for region in sorted(cropped_root.iterdir()):
        if region.is_dir():
            candidate = region / jpeg.name
            if candidate.is_file() or candidate.is_symlink():
                matches.append(candidate)
    return matches


def rename_lens_config(
    config_root: Path, slug: str, mag_label: str, focal_mm: float,
    shots_csv: Path, *, dry_run: bool = False, start_seq: int = 1,
) -> int:
    """Rename every JPEG under ``<config_root>/F<n>/`` (and matching
    ``cropped/<region>/`` siblings) to the Digikam convention.
    ``shots.csv``'s ``filename`` column is updated.

    Returns the next ``seq`` value (one past the last assigned).
    """
    rows, fieldnames = load_shots_csv(shots_csv)
    # Sort rows by rail_position_mm ascending (Q4 resolution). Stable
    # secondary key on aperture so the same rail position gives a
    # consistent intra-step order.
    def _sort_key(r: dict) -> tuple[float, str, str]:
        try:
            pos = float(r["rail_position_mm"])
        except ValueError:
            pos = float("inf")
        return (pos, r.get("aperture", ""), r.get("filename", ""))

    rows.sort(key=_sort_key)

    # Build the old→new filename mapping. Sequence number resets per
    # lens-config and increments across all (rail_position, aperture)
    # rows in sort order.
    rename_map: dict[Path, tuple[Path, str]] = {}   # old_full → (new_full, new_name)
    new_filename_per_row: list[tuple[dict, str]] = []
    seq = start_seq
    for row in rows:
        old_name = row.get("filename", "")
        if not old_name:
            new_filename_per_row.append((row, ""))
            continue
        aperture = row.get("aperture", "")
        if not aperture:
            new_filename_per_row.append((row, ""))
            continue
        # filename in shots.csv is the source-side path like
        # "f_11/step_0127.jpg" — split out the aperture-relative tail.
        old_path_rel = Path(old_name)
        ap_subdir = old_path_rel.parent.name           # e.g. "f_11"
        orig_basename = old_path_rel.name              # e.g. "step_0127.jpg"
        old_full = config_root / ap_subdir / orig_basename
        if not old_full.is_file():
            # File missing — could be archived elsewhere. Note in row
            # but leave seq untouched.
            new_filename_per_row.append((row, ""))
            continue
        new_basename = build_digikam_name(
            seq=seq, slug=slug, mag_label=mag_label,
            focal_mm=focal_mm, aperture=aperture,
            original_filename=orig_basename,
        )
        new_full = old_full.with_name(new_basename)
        rename_map[old_full] = (new_full, new_basename)
        new_path_rel = old_path_rel.with_name(new_basename)
        new_filename_per_row.append((row, str(new_path_rel)))
        seq += 1

    if dry_run:
        sample = list(rename_map.items())[:3]
        print(f"  [{slug} / {mag_label}] would rename {len(rename_map)} JPEGs "
              f"(seq {start_seq}..{seq - 1})")
        for old, (_, new_name) in sample:
            print(f"    {old.name}\n      → {new_name}")
        return seq

    # Apply renames. Also rename matching cropped/<region>/<orig> siblings.
    rename_failures = 0
    for old_full, (new_full, new_basename) in rename_map.items():
        ap_dir = old_full.parent
        # Move top-level file first.
        try:
            old_full.rename(new_full)
        except OSError as e:
            print(f"  WARN: rename failed for {old_full}: {e}", file=sys.stderr)
            rename_failures += 1
            continue
        # Then matching cropped siblings.
        for crop_old in _matching_cropped_paths(
            new_full.with_name(old_full.name), ap_dir,
        ):
            crop_new = crop_old.with_name(new_basename)
            try:
                crop_old.rename(crop_new)
            except OSError as e:
                print(f"  WARN: cropped rename failed for {crop_old}: {e}", file=sys.stderr)

    # Write back the shots.csv with updated filenames.
    for row, new_name in new_filename_per_row:
        if new_name:
            row["filename"] = new_name
    write_shots_csv(shots_csv, [r for r, _ in new_filename_per_row], fieldnames)

    print(f"  [{slug} / {mag_label}] renamed {len(rename_map)} JPEGs"
          f" (seq {start_seq}..{seq - 1})"
          + (f", {rename_failures} failures" if rename_failures else ""))
    return seq


def _matching_cropped_paths_for_oldname(
    aperture_dir: Path, old_basename: str,
) -> list[Path]:
    """Look for cropped/<region>/<old_basename> siblings BEFORE the
    top-level rename. Used because we need the matches list before
    the rename happens, but compute paths from the original basename.
    """
    cropped_root = aperture_dir / "cropped"
    if not cropped_root.is_dir():
        return []
    matches: list[Path] = []
    for region in sorted(cropped_root.iterdir()):
        if region.is_dir():
            candidate = region / old_basename
            if candidate.is_file() or candidate.is_symlink():
                matches.append(candidate)
    return matches


# ---- CLI ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rename_for_digikam",
        description="Rename JPEGs into the Digikam pipe-separated convention.",
    )
    parser.add_argument("--root", type=Path, required=True,
                        help="Date dir, e.g. .../test-raw-data/2026-05-13/")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="CSV from measure_wafer_squares with the verified mag column populated.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    print(f"Loaded {len(manifest)} manifest rows")

    next_seq = 1
    for slug_dir in _iter_lens_config_dirs(args.root):
        slug = slug_dir.name
        # The manifest may have multiple mag entries for the same slug
        # (e.g., during validation against 2026-01-29). In the
        # 2026-05-13 production tree we expect ONE mag per slug after
        # step 4. For step 3 (this script), the per-config dir comes
        # without a mag subdir, so we look up by slug only.
        candidates = [
            row for (k_slug, _), row in manifest.items() if k_slug == slug
        ]
        if not candidates:
            print(f"  [{slug}] no manifest row; skipping")
            continue
        if len(candidates) > 1:
            print(f"  [{slug}] WARN: {len(candidates)} manifest rows; "
                  f"using first ({candidates[0].mag_label})")
        row = candidates[0]
        if row.measured_mag is None:
            print(f"  [{slug}] no measured magnification; skipping")
            continue
        mag_label = format_magnification(row.measured_mag)
        # EXIF focal length — read from any one JPEG (constant per config).
        focal_mm: float | None = None
        for jpg in slug_dir.rglob("*.jpg"):
            focal_mm = read_focal_length_mm(jpg)
            if focal_mm:
                break
        if focal_mm is None:
            print(f"  [{slug}] couldn't read focal length from any JPEG; skipping")
            continue

        shots_csv = slug_dir / "shots.csv"
        if not shots_csv.is_file():
            print(f"  [{slug}] no shots.csv; skipping")
            continue

        next_seq = rename_lens_config(
            config_root=slug_dir, slug=slug, mag_label=mag_label,
            focal_mm=focal_mm, shots_csv=shots_csv,
            dry_run=args.dry_run, start_seq=1,        # reset seq per config
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
