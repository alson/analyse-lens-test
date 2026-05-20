"""Develop 2025-07-05 NEFs to high-quality JPEGs via darktable-cli.

The 2025-07-05 dataset has only flat NEFs at the lens-dir level
(no FL/aperture hierarchy). An earlier version of this script tried
to use the NEF-embedded ``JpgFromRaw`` preview, but that turned out to
be Nikon's "basic"-quality JPEG (~113 kB/MP) which crushes
high-frequency content. The sharpness analysis ran on it but every
measurement collapsed to the metric's lower-bound FFT bin (0.20 cy/px)
— no signal.

This version uses darktable-cli to demosaic the NEFs at full quality.
Output JPEGs are 6016 × 4016, ~9 MB (≈370 kB/MP, well above basic).
Default darktable modules (white balance, sharpening, base curve)
applied; user XMP presets ignored.

Walks lens dirs ending in 'inf' (skipping macro '1_1' / '1_3' subdirs
per user). Reads FocalLength and FNumber from each NEF, writes the
developed JPEG to ``<lens-dir>/<focal_length> mm/F<aperture>/<original-stem>.jpg``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2025-07-05")


def exif_get(nef: Path, *tags: str) -> dict[str, str]:
    cmd = ["exiftool", "-s", "-s", "-s"] + [f"-{t}" for t in tags] + [str(nef)]
    out = subprocess.check_output(cmd, text=True).strip().splitlines()
    if len(out) != len(tags):
        return {}
    return dict(zip(tags, out))


def extract(nef: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # darktable-cli demosaics the NEF and exports a JPEG. --apply-custom-presets
    # false ignores any sidecar XMPs the user may have created.
    subprocess.run(
        [
            "darktable-cli", str(nef), str(out_path),
            "--apply-custom-presets", "false",
            "--core", "--conf", "plugins/imageio/format/jpeg/quality=92",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    if not ROOT.is_dir():
        print(f"missing {ROOT}", file=sys.stderr)
        return 1
    n_extracted = 0
    n_skipped = 0
    for lens_dir in sorted(ROOT.iterdir()):
        if not lens_dir.is_dir():
            continue
        # Only infinity-class folders (skip 1_1 / 1_3 macro magnifications)
        if lens_dir.name.endswith(" 1_1") or lens_dir.name.endswith(" 1_3"):
            continue
        if not lens_dir.name.endswith(" inf"):
            print(f"  skipping (no inf suffix): {lens_dir.name}", file=sys.stderr)
            continue
        nefs = sorted(lens_dir.glob("*.nef"))
        if not nefs:
            continue
        print(f"== {lens_dir.name} ({len(nefs)} NEFs)")
        for nef in nefs:
            md = exif_get(nef, "FocalLength", "FNumber")
            if not md:
                print(f"  no metadata: {nef.name}")
                n_skipped += 1
                continue
            fl_raw = md.get("FocalLength", "").strip()
            fn_raw = md.get("FNumber", "").strip()
            # Parse "300.0 mm" / "5.6"
            try:
                fl_mm = float(fl_raw.split()[0])
                fnumber = float(fn_raw)
            except (ValueError, IndexError):
                print(f"  unparseable: {nef.name} FL={fl_raw!r} F={fn_raw!r}")
                n_skipped += 1
                continue
            # Format directory names to match other days' conventions:
            # "300.0 mm", "F8" (no decimal if integer), "F5.6"
            fl_dir = f"{fl_mm:.1f} mm"
            if fnumber == int(fnumber):
                f_dir = f"F{int(fnumber)}"
            else:
                # one decimal place for fractional f-stops
                f_dir = f"F{fnumber:.1f}".rstrip("0").rstrip(".")
            out = lens_dir / fl_dir / f_dir / (nef.stem + ".jpg")
            if out.exists():
                n_skipped += 1
                continue
            try:
                extract(nef, out)
                n_extracted += 1
            except subprocess.CalledProcessError as e:
                print(f"  extract failed: {nef.name}: {e}")
                n_skipped += 1
    print(f"\nExtracted {n_extracted} JPEGs, skipped {n_skipped}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
