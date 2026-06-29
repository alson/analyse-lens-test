"""List exact accessory sweep IDs (lens contains ' + ') at F8/F11 for the
pipeline-discoverable older-rig dates, to feed `tile-sharpness analyse`.
Prints one sweep.label per line; usage: pass these as analyse args.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tile_sharpness.sweeps import discover_all

APS = {"F8", "F8.0", "F11", "F11.0"}
DATES = ("older-2026-01-29", "older-2026-02-18")


def main():
    sweeps = [s for s in discover_all()
              if " + " in s.lens and s.aperture in APS and s.family in DATES]
    # de-dup by label, sort
    for s in sorted({s.label for s in sweeps}):
        print(s)
    print(f"# {len(sweeps)} accessory F8/F11 sweeps", file=sys.stderr)


if __name__ == "__main__":
    main()
