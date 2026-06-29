"""Enumerate BARE (no-accessory) native lens sweep configs for the atlas-anchored
ranking — the bare-vs-accessory reference. Same layout/filters as
enumerate_accessory_configs.py but lens dir must NOT contain ' + '. Pipeline dates
only (2026-01-29, 2026-02-18); excludes -resized. Emits bare_configs.csv.
"""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path.home() / "shared/files/pics/digikam/test-raw-data"
DATES = ["2026-01-29", "2026-02-18"]
OUT = Path(__file__).resolve().parent / "bare_configs.csv"


def parse_mag(s: str) -> float:
    bare = s.removesuffix("-resized")
    if "_" not in bare:
        return float("nan")
    a, b = bare.split("_", 1)
    try:
        return float(a) / float(b)
    except ValueError:
        return float("nan")


def is_ap(name: str) -> bool:
    return name.startswith("F") or name.startswith("f_")


def main():
    rows = []
    for date in DATES:
        root = ROOT / date
        if not root.exists():
            continue
        for lens_dir in sorted(p for p in root.iterdir()
                               if p.is_dir() and " + " not in p.name and p.name != "resuls_ignore"):
            for mag_dir in sorted(p for p in lens_dir.iterdir() if p.is_dir()):
                if mag_dir.name.endswith("-resized"):
                    continue
                children = sorted(p for p in mag_dir.iterdir() if p.is_dir())
                ap_dirs = ([(None, c) for c in children] if children and all(is_ap(c.name) for c in children)
                           else [(fd.name, ap) for fd in children
                                 for ap in sorted(p for p in fd.iterdir() if p.is_dir()) if is_ap(ap.name)])
                for focal, ap in ap_dirs:
                    jpgs = sorted(ap.glob("*.jpg")) or sorted(ap.glob("*.JPG"))
                    if len(jpgs) < 3:
                        continue
                    rows.append(dict(date=date, lens=lens_dir.name, mag_label=mag_dir.name,
                                     nominal_M=f"{parse_mag(mag_dir.name):.4f}", focal=focal or "",
                                     aperture=ap.name, n_shots=len(jpgs), sample=str(jpgs[len(jpgs)//2])))
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} bare sweep configs -> {OUT}")
    f8 = [r for r in rows if r["aperture"] in ("F8", "F8.0", "f_8")]
    import collections
    print("F8 bare configs:", len(f8))
    print("distinct (lens,mag) at F8/F11:",
          len({(r["lens"], r["mag_label"]) for r in rows if r["aperture"] in ("F8","F8.0","F11","F11.0")}))
    print("lenses:", sorted({r["lens"] for r in rows}))


if __name__ == "__main__":
    main()
