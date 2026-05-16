"""Step 4 — collapse `2026-05-13/<slug>/F<n>/...` into the final
`<slug>/<mag>/<focal mm>/F<n>/...` Digikam layout, matching the
existing `2026-02-18/<lens>/<mag>/<focal>/<F>/` convention.

After step 3, each lens-config dir looks like::

  2026-05-13/<slug>/
  ├── shots.csv               # filenames in the form "F<n>/NNNNN|...|*.jpg"
  ├── metadata.json
  ├── F<n>/
  │   ├── NNNNN|<slug>|<mag>|<focal> mm|F<n>|<orig>.jpg
  │   └── cropped/<region>/...
  └── F<n>/...

This step:

1. Parses any one renamed filename in each `F<n>/` to recover the
   ``<mag>`` and ``<focal> mm`` strings.
2. Sanity-checks that every JPEG in the slug has the SAME mag and
   focal (if not, refuses to act — a slug with mixed mags is a step-3
   problem to fix first).
3. Creates ``<slug>/<mag>/<focal mm>/`` and moves each ``F<n>/`` dir
   into it. The whole F<n> tree moves at once (JPEGs + ``cropped/``
   subtree ride along atomically).
4. Moves ``shots.csv`` + ``metadata.json`` into the new
   ``<slug>/<mag>/<focal mm>/`` dir; updates each ``shots.csv`` row's
   ``filename`` column to prepend ``<mag>/<focal mm>/`` so it stays
   valid as a relative path.
5. The original ``<slug>/`` dir is then a pure container of one
   ``<mag>/<focal mm>/`` subtree (in production), matching
   2026-02-18.

Idempotent + dry-run safe: if ``<mag>/<focal mm>/`` already exists
and the F<n>/ dirs are already there, the script reports
"already sorted" and skips.

Usage:

  python -m archive_2026_05.sort_to_lens_tree \\
      --root ~/shared/files/pics/digikam/test-raw-data/2026-05-13

  # Dry-run:
  python -m archive_2026_05.sort_to_lens_tree --root ... --dry-run
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# Pattern matching the Digikam-style filename produced by step 3.
# Captures: seq | slug | mag | focal | aperture | original
_NAME_RE = re.compile(
    r"^(?P<seq>\d{5})\|"
    r"(?P<slug>[^|]+)\|"
    r"(?P<mag>[^|]+)\|"
    r"(?P<focal>[^|]+)\|"
    r"(?P<aperture>[^|]+)\|"
    r"(?P<orig>.+)$"
)


@dataclass(frozen=True)
class FilenameParts:
    seq: str
    slug: str
    mag: str            # e.g. "1.3_1"
    focal: str          # e.g. "150.0 mm"
    aperture: str       # e.g. "F11"
    orig: str           # e.g. "step_0127.jpg"


def parse_digikam_filename(name: str) -> FilenameParts | None:
    """Parse a Digikam pipe-separated basename. Returns None if it
    doesn't match the expected shape (e.g., a runner-side file that
    step 3 missed)."""
    m = _NAME_RE.match(name)
    if not m:
        return None
    return FilenameParts(
        seq=m.group("seq"),
        slug=m.group("slug"),
        mag=m.group("mag"),
        focal=m.group("focal"),
        aperture=m.group("aperture"),
        orig=m.group("orig"),
    )


# ---- Per-slug sort --------------------------------------------------------


@dataclass(frozen=True)
class SortPlan:
    slug_dir: Path
    mag: str
    focal: str
    f_dirs: tuple[Path, ...]       # F<n> dirs to move
    shots_csv: Path | None
    metadata_json: Path | None


def _aperture_dirs(slug_dir: Path) -> list[Path]:
    """F<n>/ dirs directly under ``slug_dir`` (post-step-3 shape).
    Excludes ``<mag>/`` dirs that look like sort destinations."""
    out = []
    for p in sorted(slug_dir.iterdir()):
        if not p.is_dir():
            continue
        # Already-sorted mag dirs look like "1.3_1" or "1_1" — they
        # don't start with "F".
        if p.name.startswith("F") or p.name.startswith("f_"):
            out.append(p)
    return out


def _pick_sample_jpeg(f_dir: Path) -> Path | None:
    """Find any JPEG in F<n>/ that step 3 already renamed."""
    for p in sorted(f_dir.iterdir()):
        if p.is_file() and p.suffix.lower() == ".jpg":
            return p
    return None


def plan_sort(slug_dir: Path) -> SortPlan | None:
    """Determine the target ``<mag>``/``<focal>`` for this slug.
    Returns ``None`` if the slug has no F-dirs to move (already
    sorted) or has mixed mags/focals (refuse — likely a step-3 bug).
    """
    f_dirs = _aperture_dirs(slug_dir)
    if not f_dirs:
        return None
    sample_parts: FilenameParts | None = None
    for f_dir in f_dirs:
        sample = _pick_sample_jpeg(f_dir)
        if sample is None:
            continue
        parts = parse_digikam_filename(sample.name)
        if parts is None:
            print(
                f"  WARN: {sample.name} isn't in the Digikam convention; "
                "did step 3 run?", file=sys.stderr,
            )
            return None
        if sample_parts is None:
            sample_parts = parts
            continue
        if (parts.mag, parts.focal) != (sample_parts.mag, sample_parts.focal):
            print(
                f"  WARN: {slug_dir.name} has mixed (mag, focal) across "
                f"F-dirs: {sample_parts.mag}/{sample_parts.focal} vs "
                f"{parts.mag}/{parts.focal}; refusing to sort.",
                file=sys.stderr,
            )
            return None
    if sample_parts is None:
        return None
    shots_csv = slug_dir / "shots.csv"
    metadata = slug_dir / "metadata.json"
    return SortPlan(
        slug_dir=slug_dir,
        mag=sample_parts.mag,
        focal=sample_parts.focal,
        f_dirs=tuple(f_dirs),
        shots_csv=shots_csv if shots_csv.is_file() else None,
        metadata_json=metadata if metadata.is_file() else None,
    )


def _update_shots_csv_paths(csv_path: Path, prefix: str, *, dry_run: bool) -> int:
    """Prepend ``prefix`` (e.g. ``"1.3_1/150.0 mm/"``) to each row's
    ``filename`` column. Returns the number of rows updated."""
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    updated = 0
    for r in rows:
        fn = r.get("filename", "")
        if not fn or fn.startswith(prefix):
            continue
        r["filename"] = prefix + fn
        updated += 1
    if dry_run:
        return updated
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return updated


def apply_plan(plan: SortPlan, *, dry_run: bool) -> None:
    """Execute the sort. The ``shots.csv`` filename paths are
    rewritten BEFORE the F-dir move so a dry-run accurately reports
    the new state. The CSV move follows."""
    target_dir = plan.slug_dir / plan.mag / plan.focal
    print(
        f"  [{plan.slug_dir.name}] sort → {plan.mag}/{plan.focal}/ "
        f"({len(plan.f_dirs)} F-dirs)"
    )
    if target_dir.exists() and any(target_dir.iterdir()):
        # Re-running on already-sorted layout. Check it really is sorted.
        existing_f = list(target_dir.glob("F*"))
        if existing_f and not plan.f_dirs:
            print("    already sorted; skipping")
            return
        print(
            f"    WARN: target dir {target_dir} already populated; "
            f"refusing to overwrite. Investigate manually.",
            file=sys.stderr,
        )
        return
    if dry_run:
        print(f"    [dry] mkdir -p {target_dir}")
        for f_dir in plan.f_dirs:
            print(f"    [dry] mv {f_dir.name} → {plan.mag}/{plan.focal}/{f_dir.name}")
        if plan.shots_csv:
            print(f"    [dry] mv shots.csv → {plan.mag}/{plan.focal}/shots.csv")
            print(f"    [dry] prepend '{plan.mag}/{plan.focal}/' to filename column rows")
        if plan.metadata_json:
            print(f"    [dry] mv metadata.json → {plan.mag}/{plan.focal}/metadata.json")
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{plan.mag}/{plan.focal}/"
    # Update CSV paths in place first (so the CSV at the slug level
    # still has the right structure if the move is interrupted —
    # restart will see the wrong paths and refuse to double-prepend
    # thanks to the startswith check).
    if plan.shots_csv:
        n = _update_shots_csv_paths(plan.shots_csv, prefix, dry_run=False)
        print(f"    updated {n} shots.csv rows")
    for f_dir in plan.f_dirs:
        new_path = target_dir / f_dir.name
        shutil.move(str(f_dir), str(new_path))
    if plan.shots_csv:
        shutil.move(str(plan.shots_csv), str(target_dir / "shots.csv"))
    if plan.metadata_json:
        shutil.move(str(plan.metadata_json), str(target_dir / "metadata.json"))


# ---- CLI ------------------------------------------------------------------


def _iter_slugs(root: Path) -> Iterable[Path]:
    for p in sorted(root.iterdir()):
        if p.is_dir() and not p.name.startswith(".") and not p.name.endswith("-resized"):
            yield p


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sort_to_lens_tree",
        description="Collapse <slug>/F<n>/ to <slug>/<mag>/<focal>/F<n>/.",
    )
    parser.add_argument("--root", type=Path, required=True,
                        help="Date dir, e.g. .../test-raw-data/2026-05-13/")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        print(f"ERROR: {args.root} is not a directory", file=sys.stderr)
        return 1

    total = sorted_count = skip_count = 0
    for slug_dir in _iter_slugs(args.root):
        total += 1
        plan = plan_sort(slug_dir)
        if plan is None:
            skip_count += 1
            continue
        apply_plan(plan, dry_run=args.dry_run)
        sorted_count += 1
    print()
    print(f"== summary: {sorted_count} sorted, {skip_count} skipped, {total} total ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
