"""Atlas-anchored centre/corner subject-MTF50 for the D7200 (DX, 3.91um, OLPF).

The D7200-camera driver for scripts/atlas_corner_mtf.py: reuses its parameterised
`run()` (atlas reg_auto placement + scribe-LSF MTF50 at centre + 4 corners) with the
DX frame (6000x4000) and pitch (3.91um). Magnification comes from the atlas registration
(reg_auto scale / M anchor), the same source the relmtf run used — no rail step needed,
so this is the "characterise-style" centre/corner + uniformity view MINUS field curvature
(which is rail-dependent and unavailable on the manual-tier D7200).

Aperture = the DX folder value, which is the EFFECTIVE f-number (verified: D7200 folders
are effective). Used directly as N_eff (no 1+M re-application).

CAVEATS (lead with these): OLPF depresses D7200 absolute MTF50 vs an OLPF-less sensor, so
within-D7200 / relative comparisons are trustworthy but absolute cross-camera (Z7<->D7200)
lp/mm is NOT. The scribe-LSF MTF50 over-reads the diffraction ceiling at low contrast, so
trust readings that sit below the ceiling (glass-limited: corners, wider apertures) and use
the physics ceiling for diffraction-limited configs.

Usage:
  atlas_corner_d7200.py --subset data/cross_m_relative_mtf_subset_d7200.csv \
      --out out_atlas_corner_d7200 [--limit N] [--config SUBSTR]
Writes <out>/atlas_corner_d7200.csv and a DONE (or FAILED) marker when run over all.
"""
import argparse
import csv
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas_corner_mtf as ac  # parameterised run(), TARGETS

D7200_W, D7200_H = 6000, 4000
D7200_PITCH_UM = 3.91


def parse_aperture(folder_name):
    """'F5.6' -> 5.6 ; 'F11' -> 11.0. Returns None if unparseable."""
    try:
        return float(folder_name.lstrip("Ff"))
    except (ValueError, AttributeError):
        return None


def discover(subset_path):
    """Yield (label, ap_dir, eff_ap) per D7200 config row of the frozen subset."""
    with open(subset_path, newline="") as fh:
        for row in csv.DictReader(fh):
            if (row.get("camera") or "Z7").strip() != "D7200":
                continue
            sample = (row.get("sample") or "").strip()
            if not sample:
                continue
            ap_dir = Path(os.path.dirname(sample))
            eff_ap = parse_aperture(ap_dir.name)
            lens = (row.get("lens") or ap_dir.parent.name).strip()
            label = f"{lens} | {ap_dir.name}"
            yield label, ap_dir, eff_ap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None,
                    help="process only the first N configs (validation)")
    ap.add_argument("--config", default=None,
                    help="only configs whose label contains this substring (validation)")
    ap.add_argument("--shard", default=None,
                    help="i/N shard selector (round-robin); writes a per-shard CSV")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not args.shard:
        (out / "DONE").unlink(missing_ok=True)
        (out / "FAILED").unlink(missing_ok=True)

    configs = list(discover(args.subset))
    if args.config:
        configs = [c for c in configs if args.config.lower() in c[0].lower()]
    if args.limit:
        configs = configs[:args.limit]
    shard_i = None
    if args.shard:
        shard_i, shard_n = (int(x) for x in args.shard.split("/"))
        configs = configs[shard_i::shard_n]

    rows = []
    try:
        for label, ap_dir, eff_ap in configs:
            r = ac.run(label, ap_dir, image_w=D7200_W, image_h=D7200_H,
                       pitch_um=D7200_PITCH_UM, eff_ap=eff_ap)
            if r is None:
                rows.append(dict(label=label, aperture=eff_ap, registered=False))
                continue
            lp = r["lpmm"]
            cor = [lp.get(k) for k in ("TL", "TR", "BL", "BR") if lp.get(k) is not None]
            cmean = float(np.mean(cor)) if cor else float("nan")
            cen = lp.get("centre")
            rows.append(dict(
                label=label, aperture=eff_ap, registered=True,
                M=round(r["M"], 4), n_eff=round(r["n_eff"], 2),
                centre=(round(cen, 2) if cen else None),
                TL=(round(lp["TL"], 2) if lp.get("TL") else None),
                TR=(round(lp["TR"], 2) if lp.get("TR") else None),
                BL=(round(lp["BL"], 2) if lp.get("BL") else None),
                BR=(round(lp["BR"], 2) if lp.get("BR") else None),
                corner_mean=(round(cmean, 2) if cmean == cmean else None),
                uniformity=(round(cmean / cen, 3) if (cen and cmean == cmean) else None)))
    except Exception as e:  # noqa: BLE001 — record failure for the launcher marker
        (out / "FAILED").write_text(f"{type(e).__name__}: {e}\n")
        raise

    csv_path = (out / f"atlas_corner_d7200_shard_{shard_i}.csv") if args.shard \
        else (out / "atlas_corner_d7200.csv")
    fields = ["label", "aperture", "registered", "M", "n_eff", "centre",
              "TL", "TR", "BL", "BR", "corner_mean", "uniformity"]
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nWROTE {csv_path} ({len(rows)} configs; subject lp/mm, centre+4 corners)")
    # stamp DONE only for a full, unsharded, unfiltered run (the launcher merges shards
    # and stamps DONE itself for the sharded path).
    if not args.limit and not args.config and not args.shard:
        (out / "DONE").write_text("ok\n")


if __name__ == "__main__":
    main()
