#!/usr/bin/env python3
"""Rename + sort a lens-test capture dir into the Digikam pipe-separated
convention, then into the ``<lens>/<focal>/<F>`` folder tree — moving NEF
and JPG together.

Reproduces the digiKam Advanced-Rename token string used for the
2026-01 longdist data::

  #####|[meta:Exif.Photo.LensModel][meta:Exif.NikonLd4.LensIDNumber]{replace:"^0$","",ri} ISO[meta:Exif.Photo.ISOSpeed]|[meta:Exif.Photo.FocalLength]|[meta:Exif.Photo.FNumber]|[file]{lower}

i.e. each file becomes::

  NNNNN|<lens> ISO<iso>|<focal> mm|F<n>|<orig-lowercased>.<ext>

digiKam reads metadata through **Exiv2**, so this script does too (via the
``exiv2`` CLI, ``-Pkt`` = translated values) to match the existing folders
byte-for-byte — exiftool's strings differ (e.g. it lacks the "Nikon "
prefix on adapted-lens names and would emit the raw LensID *number*).

Field semantics, verified against real 2026-01 files:

- ``NNNNN``   5-digit sequence, per *shot* (a capture's JPG+NEF share it),
  in capture-time order (filename-stem sort).
- ``<lens>``  ``Exif.Photo.LensModel`` when present — **native Z** lenses
  populate it and it already encodes the Z teleconverter (e.g.
  ``…VR S Z TC-2.0x``). **FTZ-adapted F-mount** lenses leave LensModel
  blank, so we fall back to the translated ``Exif.NikonLd4.LensIDNumber``
  (the lens *name*, e.g. ``Nikon AF-S Nikkor 300mm f/4E PF ED VR``). ``/``
  → ``_``.
    ⚠ F-mount teleconverters are NOT in EXIF (bare and "+ TC-14e III" read
      identical LensIDNumber, only FocalLength/FNumber change). Only native
      Z TCs self-encode. For an adapted lens + F-mount TC you must append
      the TC to the lens folder by hand afterwards (as the 2026-01 data was).
- `` ISO<iso>``  ``Exif.Photo.ISOSpeedRatings``.
- ``<focal> mm``  ``Exif.Photo.FocalLength`` — **effective** FL incl. the
  TC (lens-at-400 + TC-2.0x → ``800.0 mm``). Taken verbatim from Exiv2.
- ``F<n>``  ``Exif.Photo.FNumber`` (effective), Exiv2-rendered (``F16``,
  ``F5.6``, ``F5``).
- ``<orig>``  original filename, lower-cased, incl. extension.

The sort step moves each renamed file (JPG *and* NEF) into
``<root>/<lens ISO>/<focal>/<F>/`` — the 2026-01 tree shape.

Usage (dry-run by default — inspect, then ``--apply``)::

  python3 rename_and_sort_lens_test.py --root ~/.../test-raw-data/2026-06-28
  python3 rename_and_sort_lens_test.py --root ~/.../2026-06-28 --apply

Only files without ``|`` are touched, so it is safe to re-run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".nef"}

# Exact Exiv2 keys we consume (translated values).
K_LENS_MODEL = "Exif.Photo.LensModel"
K_LENS_ID = "Exif.NikonLd4.LensIDNumber"
K_ISO = "Exif.Photo.ISOSpeedRatings"
K_FOCAL = "Exif.Photo.FocalLength"
K_FNUMBER = "Exif.Photo.FNumber"
_WANTED_KEYS = (K_LENS_MODEL, K_LENS_ID, K_ISO, K_FOCAL, K_FNUMBER)

# Translated LensIDNumber values that mean "no adapted-lens identity".
_NO_LENS_ID = {"", "0", "(0)"}


# ---- Pure formatting helpers (unit-tested) --------------------------------


def format_lens_field(lens_model: str, lens_id_translated: str, iso: str) -> str:
    """Build the ``<lens> ISO<iso>`` field from Exiv2 translated values.

    LensModel wins (native Z, carries the Z TC); else the translated
    LensIDNumber name (adapted F-mount). ``/`` → ``_``. A ``0``/``(0)``
    LensIDNumber means "not an adapted lens" and is ignored.
    """
    model = (lens_model or "").strip()
    if model:
        name = model
    else:
        lid = (lens_id_translated or "").strip()
        if lid in _NO_LENS_ID:
            raise ValueError("no LensModel and no usable LensIDNumber")
        name = lid
    name = name.replace("/", "_")
    return f"{name} ISO{iso.strip()}"


def build_name(seq: int, lens_field: str, focal: str, fnumber: str,
               original_name: str) -> str:
    """Compose the pipe-separated basename. ``focal``/``fnumber`` are the
    Exiv2 translated strings (e.g. ``"400.0 mm"``, ``"F16"``)."""
    return "|".join([
        f"{seq:05d}", lens_field, focal.strip(), fnumber.strip(),
        original_name.lower(),
    ])


# ---- Exiv2 read ------------------------------------------------------------


def _parse_exiv2(text: str) -> dict[str, str]:
    """Parse ``exiv2 -Pkt`` output (``<key><pad><translated value>``) into
    ``{key: value}`` for our wanted keys. Disambiguates key prefixes
    (FocalLength vs FocalLengthIn35mmFilm) by requiring whitespace after
    the key."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        for key in _WANTED_KEYS:
            if line.startswith(key) and line[len(key):len(key) + 1] in (" ", "\t"):
                out[key] = line[len(key):].strip()
                break
    return out


def read_exiv2(path: Path) -> dict[str, str]:
    cmd = ["exiv2", "-Pkt"]
    for k in _WANTED_KEYS:
        cmd += ["-g", k]
    cmd.append(str(path))
    out = subprocess.run(cmd, capture_output=True, text=True)
    # exiv2 returns non-zero when some -g keys don't match; the matched
    # lines are still on stdout, so parse regardless of returncode.
    return _parse_exiv2(out.stdout)


# ---- Phase A: rename -------------------------------------------------------


def _candidate_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and "|" not in p.name
    )


def plan_rename(root: Path) -> list[tuple[Path, Path]]:
    """``[(old, new)]``. A shot's JPG+NEF share a seq + fields (read from
    one representative file, JPG preferred); seq follows stem order."""
    files = _candidate_files(root)
    if not files:
        return []
    by_stem: dict[str, list[Path]] = {}
    for p in files:
        by_stem.setdefault(p.stem.lower(), []).append(p)
    plan: list[tuple[Path, Path]] = []
    for seq, stem in enumerate(sorted(by_stem), start=1):
        group = by_stem[stem]
        rep = next((p for p in group if p.suffix.lower() in (".jpg", ".jpeg")), group[0])
        tags = read_exiv2(rep)
        try:
            lens_field = format_lens_field(
                tags.get(K_LENS_MODEL, ""), tags.get(K_LENS_ID, ""),
                tags.get(K_ISO, ""),
            )
            focal = tags[K_FOCAL]
            fnum = tags[K_FNUMBER]
        except (KeyError, ValueError) as e:
            print(f"  WARN: {rep.name}: {e}; skipping shot", file=sys.stderr)
            continue
        if not tags.get(K_ISO, "").strip():
            print(f"  WARN: {rep.name}: no ISO; skipping shot", file=sys.stderr)
            continue
        for p in group:
            plan.append((p, p.with_name(build_name(seq, lens_field, focal, fnum, p.name))))
    return plan


# ---- Phase B: sort into <lens>/<focal>/<F>/ -------------------------------


def plan_sort(root: Path) -> list[tuple[Path, Path]]:
    plan: list[tuple[Path, Path]] = []
    for p in sorted(root.iterdir()):
        if not (p.is_file() and p.suffix.lower() in IMAGE_EXTS and "|" in p.name):
            continue
        parts = p.name.split("|")
        if len(parts) < 5:
            print(f"  WARN: {p.name} not a 5-field name; skipping", file=sys.stderr)
            continue
        plan.append((p, root / parts[1] / parts[2] / parts[3] / p.name))
    return plan


def apply_moves(moves: list[tuple[Path, Path]], *, dry_run: bool, label: str) -> None:
    if not moves:
        print(f"  [{label}] nothing to do")
        return
    for old, new in moves[:4]:
        shown = new.name if new.parent == old.parent else f"{new.parent.name}/ … /{new.name}"
        print(f"  [{label}] {old.name}\n      → {shown}")
    if len(moves) > 4:
        print(f"  [{label}] … and {len(moves) - 4} more")
    if dry_run:
        print(f"  [{label}] DRY-RUN: {len(moves)} files would move")
        return
    done = 0
    for old, new in moves:
        new.parent.mkdir(parents=True, exist_ok=True)
        if new.exists():
            print(f"  WARN: target exists, skipping: {new}", file=sys.stderr)
            continue
        old.rename(new)
        done += 1
    print(f"  [{label}] moved {done}/{len(moves)} files")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True,
                    help="Capture dir with the un-renamed image files.")
    ap.add_argument("--apply", action="store_true",
                    help="Actually rename/move (default: dry-run).")
    ap.add_argument("--rename-only", action="store_true")
    ap.add_argument("--sort-only", action="store_true")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"ERROR: {args.root} is not a directory", file=sys.stderr)
        return 1
    dry = not args.apply
    print(f"== {args.root}  ({'DRY-RUN' if dry else 'APPLY'}) ==")
    if not args.sort_only:
        print("-- rename --")
        apply_moves(plan_rename(args.root), dry_run=dry, label="rename")
    if not args.rename_only:
        print("-- sort --")
        apply_moves(plan_sort(args.root), dry_run=dry, label="sort")
    if dry:
        print("\nDry-run only. Re-run with --apply to execute.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
