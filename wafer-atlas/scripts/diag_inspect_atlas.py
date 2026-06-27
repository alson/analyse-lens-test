"""Diagnostic: dump atlas.json structure + per-type feature inventory."""
import json
from collections import Counter
from pathlib import Path

A = Path(__file__).parent.parent
a = json.load(open(A / "atlas.json"))
print("TOP KEYS:", list(a.keys()))
for k, v in a.items():
    if k == "die_types":
        continue
    print(f"\n## {k}")
    print(json.dumps(v, indent=1)[:1500])

print("\n## die_types:", len(a["die_types"]), "types")
fc = Counter()
for name, dt in a["die_types"].items():
    for ftype, lst in dt.get("feature_inventory", {}).items():
        fc[ftype] += len(lst)
print("feature totals across types:", dict(fc))

print("\n## die_types['(0, 3)'] full:")
print(json.dumps(a["die_types"]["(0, 3)"], indent=1)[:2500])

print("\n## per-type feature counts:")
for name, dt in a["die_types"].items():
    inv = dt.get("feature_inventory", {})
    counts = {k: len(v) for k, v in inv.items()}
    print(f"  {name}: keys={list(dt.keys())} feat={counts}")
