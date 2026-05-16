#!/usr/bin/env python3
"""Re-rename the Sigma 105 + TC-1401 high-mag dir from ``/1.5_1`` to
``/1.4_1``.

History: fixup-sigma-tc-mislabels-2026-01-29.py originally renamed
``Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401 / 1_1 -> 1.5_1``
because the wafer-square algo measured this dir at 1.456× (and
``format_magnification(1.456)`` produces "1.5_1"). Subsequent
analysis decomposed the measurement:

  * Sigma TC-1401 effective factor ≈ 1.443 (from Sigma 150 + TC-1401 /
    1.4_1, where the bare Sigma 150 is exactly 1:1 by construction).
  * Sigma 105 bare reads 1.034× at its closest focus (the lens's
    own focus scale allows a little past 1:1; verified algo HIGH
    confidence, no aperture disagreement).
  * Composition: 1.034 × 1.443 ≈ 1.49× — bracketed by algo 1.456×
    and user GIMP 1.536×.

So the *underlying physics* is "TC ≈ 1.44, lens 3 % past 1:1",
giving ~1.49× on sensor — which rounds to 1.5 under 1-decimal
rounding but really is "Sigma TC-1401 at maximum mag", which the
companion Sigma 150 + TC-1401 / 1.4_1 dir is labelled as. For
consistency between the two same-setup dirs (lens at MFD + TC-1.4),
both should carry the 1.4_1 label.

Structure mirrors revert-sigma-150-tc-2001-1_1-rename-2026-01-29.py:
whole-folder rename + per-JPG basename rename + drop stale pick.jpg.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")

SLUG = "Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401"
OLD_MAG = "1.5_1"
NEW_MAG = "1.4_1"

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
    print(f"Rename: {SLUG} / {OLD_MAG} -> {NEW_MAG}")
    ops, picks = plan_whole_folder(SLUG, OLD_MAG, NEW_MAG)
    print(f"Planned: {len(ops)} rename/move ops, {len(picks)} stale pick.jpg")
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
