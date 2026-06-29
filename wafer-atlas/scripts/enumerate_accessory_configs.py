"""Task 1: enumerate every accessory (lens+accessory) sweep config across the
older-rig test-raw-data dates. A config = <lens dir with ' + '>/<mag>/[focal]/<ap>
holding >=3 jpgs. Excludes -resized mag dirs (resampled, visual-only). Emits a CSV.
"""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path.home() / "shared/files/pics/digikam/test-raw-data"
DATES = ["2026-01-29", "2026-02-18", "2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15"]
OUT = Path(__file__).resolve().parent / "accessory_configs.csv"


def parse_mag(mag_str: str) -> float:
    bare = mag_str.removesuffix("-resized")
    if "_" not in bare:
        return float("nan")
    a, b = bare.split("_", 1)
    try:
        return float(a) / float(b)
    except ValueError:
        return float("nan")


def is_aperture(name: str) -> bool:
    return name.startswith("F") or name.startswith("f_")


def main():
    rows = []
    for date in DATES:
        root = ROOT / date
        if not root.exists():
            continue
        for lens_dir in sorted(p for p in root.iterdir() if p.is_dir() and " + " in p.name):
            for mag_dir in sorted(p for p in lens_dir.iterdir() if p.is_dir()):
                if mag_dir.name.endswith("-resized"):
                    continue
                children = sorted(p for p in mag_dir.iterdir() if p.is_dir())
                # bare layout: aperture dirs directly under mag; zoom: focal then ap
                ap_dirs = []  # (focal, ap_dir)
                if children and all(is_aperture(c.name) for c in children):
                    ap_dirs = [(None, c) for c in children]
                else:
                    for focal_dir in children:
                        for ap in sorted(p for p in focal_dir.iterdir() if p.is_dir()):
                            if is_aperture(ap.name):
                                ap_dirs.append((focal_dir.name, ap))
                for focal, ap in ap_dirs:
                    jpgs = sorted(ap.glob("*.jpg")) or sorted(ap.glob("*.JPG"))
                    if len(jpgs) < 3:
                        continue
                    rows.append(dict(
                        date=date, lens=lens_dir.name, mag_label=mag_dir.name,
                        nominal_M=f"{parse_mag(mag_dir.name):.4f}",
                        focal=focal or "", aperture=ap.name, n_shots=len(jpgs),
                        sample=str(jpgs[len(jpgs)//2]),
                    ))
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} accessory sweep configs -> {OUT}")
    # summary by date and aperture
    from collections import Counter
    print("by date:", dict(Counter(r["date"] for r in rows)))
    print("by aperture:", dict(Counter(r["aperture"] for r in rows)))
    f8 = [r for r in rows if r["aperture"] in ("F8", "f_8", "F8.0")]
    print(f"F8-only configs: {len(f8)}")


if __name__ == "__main__":
    main()
