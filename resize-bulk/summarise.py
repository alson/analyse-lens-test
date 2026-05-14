"""Generate focused comparison tables for native vs resized captures.

For each lens family (24-120, AF Micro-Nikkor 200/4, NIKKOR Z 100-400) we
emit two views:

1. **By-combo native+resized triple** — for every (combo, focal) we show
   one row at native magnification and one row at each `*-resized`
   target, with the aperture columns side-by-side. Sorted by descending
   native magnification.

2. **By-target leaderboard** — at each resized target magnification we
   rank combos by F8 peak centre file size. This is the "which combo
   captured the most detail to fill in the target framing" view.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

CACHE = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/rail-coverage/output/scan-cache.json")

MAG_RE = re.compile(r"^(\d+(?:\.\d+)?)_(\d+(?:\.\d+)?)$")
APERTURE_RE = re.compile(r"^F\d+(?:\.\d+)?$")
FOCAL_RE = re.compile(r"^\d+(?:\.\d+)?\s*mm\.?$")


def parse_mag(name: str) -> tuple[float, bool, str]:
    """Return (numeric_ratio, is_resized, base_name without -resized suffix)."""
    base = name.removesuffix("-resized")
    is_resized = base != name
    m = MAG_RE.match(base)
    if not m:
        return (0.0, is_resized, base)
    n, d = float(m.group(1)), float(m.group(2))
    return (n / d, is_resized, base)


def peak(sc, crop_name: str) -> int | None:
    for c in sc["crops"]:
        if c["name"] == crop_name and c["frames"]:
            return max(s for _, s in c["frames"])
    return None


def parse_path(p: str) -> dict:
    parts = p.split("/")
    # Combo lens: closest non-classifiable ancestor above the magnification
    # In practice: the directory whose name contains the lens model.
    mag_idx = None
    for i, x in enumerate(parts):
        if MAG_RE.match(x.removesuffix("-resized")):
            mag_idx = i
            break
    if mag_idx is None:
        return {}
    combo = parts[mag_idx - 1] if mag_idx > 0 else ""
    mag = parts[mag_idx]
    focal = ""
    aperture = ""
    for x in parts[mag_idx + 1:]:
        if FOCAL_RE.match(x.strip()):
            focal = x
        elif APERTURE_RE.match(x):
            aperture = x
    return {"combo": combo, "mag": mag, "focal": focal, "aperture": aperture}


def collect(scenarios):
    """Return rows[(combo, focal, mag_name)] = {aperture: peak_center_size}."""
    rows: dict[tuple[str, str, str], dict[str, int]] = defaultdict(dict)
    for sc in scenarios:
        info = parse_path(sc["cropped_dir"])
        if not info or not info["aperture"]:
            continue
        pk = peak(sc, "center")
        if pk is None:
            continue
        key = (info["combo"], info["focal"], info["mag"])
        rows[key][info["aperture"]] = pk
    return rows


def native_mag_of(combo: str, focal: str, rows) -> tuple[str, float] | None:
    """Pick the native (non-resized) magnification for this (combo, focal)."""
    best = None
    for (c, f, mag), _ in rows.items():
        if c != combo or f != focal:
            continue
        val, is_resized, _ = parse_mag(mag)
        if is_resized:
            continue
        # Prefer the largest native magnification (closest to the capture goal)
        if best is None or val > best[1]:
            best = (mag, val)
    return best


def fmt_int(v) -> str:
    return f"{v:>7,}" if v is not None else f"{'—':>7}"


def by_combo_table(rows, family: str, family_filter):
    print(f"\n## {family} — native vs resized (peak centre file size)\n")
    # Find all (combo, focal) groups
    groups: dict[tuple[str, str], list[tuple[str, float, dict[str, int]]]] = defaultdict(list)
    for (combo, focal, mag), ap_map in rows.items():
        if not family_filter(combo):
            continue
        val, is_resized, _ = parse_mag(mag)
        groups[(combo, focal)].append((mag, val, ap_map))
    if not groups:
        print("_(no scenarios match)_\n")
        return

    # Sort groups by descending native mag value (best lens first)
    def group_sort_key(item):
        (combo, focal), entries = item
        native = next((v for m, v, _ in entries if "-resized" not in m), 0)
        return (-native, combo, focal)

    # Apertures encountered (sorted numerically)
    aps_seen = sorted(
        {ap for _, ap_map in [(k, v) for k, vs in groups.items() for v in vs] for ap in ap_map[2] if ap},
        key=lambda a: float(a.removeprefix("F")) if a.removeprefix("F").replace(".", "").isdigit() else 999,
    )
    # Compact aperture set — drop dotted duplicates like F8.0
    keep_aps = []
    seen_int = set()
    for ap in aps_seen:
        n = float(ap.removeprefix("F"))
        key = round(n, 1)
        if key in seen_int:
            continue
        seen_int.add(key)
        keep_aps.append(ap)

    head = f"| {'combo':50} | {'focal':9} | {'mag':12} |"
    head += "".join(f" {ap:>7} |" for ap in keep_aps)
    sep = "|" + "-" * 52 + "|" + "-" * 11 + "|" + "-" * 14 + "|" + ("-" * 9 + "|") * len(keep_aps)
    print(head)
    print(sep)
    last_combo = None
    for (combo, focal), entries in sorted(groups.items(), key=group_sort_key):
        # Sort entries: native first, then 1_1-resized, then 2_1-resized
        def entry_sort(e):
            mag, val, _ = e
            is_resized = "-resized" in mag
            base = mag.removesuffix("-resized")
            target_order = {"1_1": 1, "2_1": 2}.get(base, 99) if is_resized else 0
            return (target_order, val)
        for mag, val, ap_map in sorted(entries, key=entry_sort):
            combo_show = combo if combo != last_combo else ""
            last_combo = combo
            line = f"| {combo_show[:50]:50} | {focal[:9]:9} | {mag[:12]:12} |"
            for ap in keep_aps:
                line += f" {fmt_int(ap_map.get(ap))} |"
            print(line)
        # Add a thin separator between groups
        last_combo = None


def by_target_leaderboard(rows, family: str, family_filter, *, target_mag: str = "2_1-resized", target_aperture: str = "F8"):
    print(f"\n## {family} — {target_mag} leaderboard at {target_aperture}\n")
    entries = []
    for (combo, focal, mag), ap_map in rows.items():
        if not family_filter(combo):
            continue
        if mag != target_mag:
            continue
        v = ap_map.get(target_aperture)
        if v is None:
            continue
        # Find native mag for context
        nm = native_mag_of(combo, focal, rows)
        native_mag_name = nm[0] if nm else "?"
        native_value = nm[1] if nm else 0.0
        tgt_val, _, _ = parse_mag(target_mag)
        factor = tgt_val / native_value if native_value else 0
        entries.append((v, combo, focal, native_mag_name, factor))
    if not entries:
        print("_(no data at this combination)_\n")
        return
    entries.sort(key=lambda e: -e[0])
    print(f"| {'rank':4} | {'combo':50} | {'focal':9} | {'native':10} | {'factor':>6} | {'peak F8':>8} |")
    print(f"|{'-'*6}|{'-'*52}|{'-'*11}|{'-'*12}|{'-'*8}|{'-'*10}|")
    for rank, (v, combo, focal, native_mag, factor) in enumerate(entries, 1):
        print(f"| {rank:4} | {combo[:50]:50} | {focal[:9]:9} | {native_mag:10} | {factor:6.2f} | {v:>8,} |")


def family_24120(combo: str) -> bool:
    return "24-120" in combo


def family_200(combo: str) -> bool:
    return "200mm f_4D" in combo


def family_100400(combo: str) -> bool:
    return "100-400" in combo


def main(argv: list[str] | None = None) -> int:
    cache = CACHE
    if argv:
        cache = Path(argv[0])
    d = json.loads(cache.read_text())
    scs = d["scenarios"]
    print(f"# Resampled-comparison report\n\nLoaded {len(scs)} scenarios from `{cache.name}`.\n")

    for label, ff in [
        ("NIKKOR Z 24-120 family", family_24120),
        ("Nikon AF Micro-Nikkor 200/4 family", family_200),
        ("NIKKOR Z 100-400 family", family_100400),
    ]:
        rows = collect(scs)
        by_combo_table(rows, label, ff)
        by_target_leaderboard(rows, label, ff, target_mag="2_1-resized", target_aperture="F8")
        by_target_leaderboard(rows, label, ff, target_mag="2_1-resized", target_aperture="F11")
        by_target_leaderboard(rows, label, ff, target_mag="1_1-resized", target_aperture="F8")
        by_target_leaderboard(rows, label, ff, target_mag="1_1-resized", target_aperture="F11")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
