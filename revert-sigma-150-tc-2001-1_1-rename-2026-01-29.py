#!/usr/bin/env python3
"""Revert the over-correction in fixup-sigma-tc-mislabels-2026-01-29:
``Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001 / 1_1`` was
renamed to ``/1.5_1`` based on the wafer-square algorithm's F11
measurement of 1.45×. Subsequent cross-checks:

  * The user's lens-focus-scale reading: fd 0.501 m on Sigma 150
    corresponds to lens-magnification 1:2 (= 0.5×); with TC-2001
    that gives **1.0× on sensor**, not 1.5×.
  * User GIMP measurement of 5 horizontal die pitches on a sharp
    F11 frame in this dir: 6172 px / 5 = 1234 px per die, vs the
    anchor's 1202 px. Ratio 1.027× = within rounding of 1:1.
  * F16 frame of the same dir already measured ~0.98× (HIGH conf);
    the F11's 1.45× turned out to be a sub-feature harmonic. The
    multi-aperture warning correctly flagged the disagreement but
    the F11-first picking policy reported the wrong number.
  * User's stated shoot-targets for 150+TC-2001: 1:1, 1.4:1, 2:1
    — original ``1_1`` label matched intent.

This script reverts just that one whole-folder rename. Other fixup
renames (Sigma 105 + TC-1401 swap, Sigma 105 + TC-2001 / 2_1 partial
split) stand — their fd readings remain consistent with the
post-fixup labels.

Structure mirrors fixup-sigma-tc-mislabels-2026-01-29.py: dry-run
by default, `--apply` to execute.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")

SLUG = "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001"
OLD_MAG = "1.5_1"
NEW_MAG = "1_1"

_PIPE_RE = re.compile(r"^(\d{5})\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|(.+)$")


def swap_mag_in_name(name: str, new_mag: str) -> str:
    parts = name.split("|", 5)
    if len(parts) != 6:
        raise ValueError(f"unexpected name shape: {name!r}")
    parts[2] = new_mag
    return "|".join(parts)


def plan_whole_folder(slug: str, old_mag: str, new_mag: str):
    renames: list[tuple[Path, Path]] = []
    stale_picks: list[Path] = []
    # Root-level NEFs (+ XMPs if any — none expected for this slug).
    for ext in ("nef", "jpg.xmp"):
        for p in ROOT.iterdir():
            if not p.is_file() or not p.name.endswith("." + ext):
                continue
            m = _PIPE_RE.match(p.name)
            if not m:
                continue
            _seq, p_slug, p_mag, _focal, _ap, _orig = m.groups()
            if p_slug == slug and p_mag == old_mag:
                renames.append((p, p.with_name(swap_mag_in_name(p.name, new_mag))))
    # Sorted-tree: parent rename + per-JPG basename renames.
    old_dir = ROOT / slug / old_mag
    new_dir = ROOT / slug / new_mag
    if old_dir.is_dir():
        renames.append((old_dir, new_dir))
        for jpg in old_dir.rglob("*.jpg"):
            if jpg.name == "pick.jpg":
                stale_picks.append(new_dir / jpg.relative_to(old_dir))
                continue
            rel = jpg.relative_to(old_dir)
            new_jpg_dir = new_dir / rel.parent
            new_basename = swap_mag_in_name(jpg.name, new_mag)
            renames.append((new_jpg_dir / jpg.name, new_jpg_dir / new_basename))
    return renames, stale_picks


def apply_renames(ops):
    n = 0
    for old, new in ops:
        if old == new:
            continue
        if new.exists():
            print(f"  SKIP (dest exists): {new}", file=sys.stderr)
            continue
        if not old.exists():
            print(f"  SKIP (src missing): {old}", file=sys.stderr)
            continue
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)
        n += 1
    return n


def delete_stale_picks(picks):
    n = 0
    for p in picks:
        if p.exists():
            p.unlink()
            n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(f"Revert: {SLUG} / {OLD_MAG} -> {NEW_MAG}")
    print(f"Root: {ROOT}")
    ops, picks = plan_whole_folder(SLUG, OLD_MAG, NEW_MAG)
    print(f"\nPlanned: {len(ops)} rename/move ops, {len(picks)} stale pick.jpg")
    for old, new in ops[:3]:
        old_disp = str(old.relative_to(ROOT) if ROOT in old.parents else old.name)
        new_disp = str(new.relative_to(ROOT) if ROOT in new.parents else new.name)
        print(f"  {old_disp}\n    -> {new_disp}")
    if not args.apply:
        print("\nDry-run. Re-run with --apply to execute.")
        return 0
    print("\nApplying...")
    n_done = apply_renames(ops)
    n_pick = delete_stale_picks(picks)
    print(f"Done. {n_done} renames, {n_pick} stale pick.jpg removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
