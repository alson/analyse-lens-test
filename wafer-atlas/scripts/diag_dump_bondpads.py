"""Dump all atlas bond-pad components: die type, bbox_uv, area, pad_pitch."""
import json
from pathlib import Path

a = json.load(open(Path(__file__).parent.parent / "atlas.json"))
n = 0
print(f"{'die_type':10s} {'label':14s} {'bbox_uv':40s} {'area_px':>8s} {'pad_pitch_px':>12s}")
for name, dt in a["die_types"].items():
    bps = dt.get("feature_inventory", {}).get("bond_pads", [])
    for bp in bps:
        n += 1
        bbox = bp.get("bbox_uv")
        print(f"{name:10s} {dt.get('instances_label','?')[:14]:14s} "
              f"{str([round(x,3) for x in bbox]):40s} "
              f"{bp.get('area_px','?'):>8} {str(bp.get('pad_pitch_px')):>12s}")
print(f"\ntotal bond-pad components: {n}")
# also experimental + slanted for completeness
for ftype in ("slanted_edge", "experimental"):
    print(f"\n{ftype}:")
    for name, dt in a["die_types"].items():
        for f in dt.get("feature_inventory", {}).get(ftype, []):
            print(f"  {name}: bbox={[round(x,3) for x in f['bbox_uv']]} "
                  f"pad_pitch={f.get('pad_pitch_px')}")
