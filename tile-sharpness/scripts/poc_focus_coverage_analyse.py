"""POC-1 focus-coverage analysis for the 2026-01-29 cohort.

Pools the psffoc shards (now carrying mu / peak_pos_frac / edge_dist_frames /
coverage_flag) with the fieldtag shards (per-patch field_height + pixel position),
bins each patch into a field zone (centre / mid / corner) and into a vertical half
(top / bottom of frame), and reports:

  * per-config coverage summary (ok vs each truncation class, frac_truncated),
  * per-config x per-zone truncation table,
  * a pooled zone table (is corner disproportionately truncated?),
  * a top-vs-bottom truncation split (the handover's "decentering" suspicion).

Usage: PYTHONPATH=src python scripts/poc_focus_coverage_analyse.py <out_dir>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import tile_sharpness.cross_m_relative_mtf as X

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "cross_m_relative_mtf_poc_focus_out")
IMAGE_H = 5504  # frame height (px); used only to split top vs bottom

pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 200)


def _pool(glob):
    fr = [pd.read_csv(f) for f in sorted(OUT.glob(glob))]
    fr = [d for d in fr if not d.empty]
    return pd.concat(fr, ignore_index=True) if fr else pd.DataFrame()


psf = _pool("psffoc_shard_*.csv")
ft = _pool("fieldtag_shard_*.csv")

print(f"psffoc rows: {len(psf)}  cols: {list(psf.columns)}")
assert "coverage_flag" in psf.columns, "psffoc lacks coverage_flag — re-extract needed"
print(f"fieldtag rows: {len(ft)}")

# merge field position (field_height, py) onto each psffoc patch
ft_pos = ft[["sid", "patch", "field_height", "py"]].drop_duplicates(["sid", "patch"])
df = psf.merge(ft_pos, on=["sid", "patch"], how="left")
df["zone"] = df["field_height"].map(lambda h: X.field_zone(h) if np.isfinite(h) else "unknown")
df["vhalf"] = np.where(df["py"] < IMAGE_H / 2.0, "top", "bottom")
df["truncated"] = df["coverage_flag"] != "ok"

# ---- per-config coverage summary --------------------------------------------- #
cov = X.through_focus_coverage_summary(psf)
print("\n=== per-config coverage summary (frac_truncated desc) ===")
print(cov.to_string(index=False))
cov.to_csv(OUT / "poc_focus_coverage_per_config.csv", index=False)

# ---- per-config x per-zone --------------------------------------------------- #
print("\n=== per-config x zone: n_total / n_truncated / frac_truncated ===")
rows = []
for (sid, zone), g in df.groupby(["sid", "zone"]):
    n = len(g)
    nt = int(g["truncated"].sum())
    rows.append(dict(sid=sid, zone=zone, n=n, n_trunc=nt, frac_trunc=nt / n))
pz = pd.DataFrame(rows)
print(pz.pivot_table(index="sid", columns="zone", values="frac_trunc").round(3).to_string())
pz.to_csv(OUT / "poc_focus_coverage_per_config_zone.csv", index=False)

# ---- pooled zone table ------------------------------------------------------- #
print("\n=== pooled across configs, by zone ===")
zrows = []
for zone, g in df.groupby("zone"):
    n = len(g)
    by = {f: int((g["coverage_flag"] == f).sum()) for f in X.COVERAGE_FLAGS}
    zrows.append(dict(zone=zone, n=n, **by,
                      frac_trunc=(n - by["ok"]) / n))
zt = pd.DataFrame(zrows)
print(zt.to_string(index=False))
zt.to_csv(OUT / "poc_focus_coverage_pooled_zone.csv", index=False)

# ---- top vs bottom (the "decentering" suspicion) ----------------------------- #
print("\n=== pooled top vs bottom half (all zones) ===")
vrows = []
for vh, g in df.groupby("vhalf"):
    n = len(g)
    nt = int(g["truncated"].sum())
    vrows.append(dict(vhalf=vh, n=n, n_trunc=nt, frac_trunc=nt / n,
                      mean_peak_pos_frac=float(np.nanmean(g["peak_pos_frac"]))))
print(pd.DataFrame(vrows).to_string(index=False))

print("\n=== top vs bottom, CORNER + MID patches only (the off-axis ones) ===")
off = df[df["zone"].isin(["mid", "corner"])]
vrows2 = []
for vh, g in off.groupby("vhalf"):
    n = len(g)
    nt = int(g["truncated"].sum())
    vrows2.append(dict(vhalf=vh, n=n, n_trunc=nt, frac_trunc=nt / n,
                       mean_peak_pos_frac=float(np.nanmean(g["peak_pos_frac"]))))
print(pd.DataFrame(vrows2).to_string(index=False))

# ---- effect of coverage filtering on P2 scores ------------------------------- #
print("\n=== P2 score with vs without coverage filter ===")
s_cov = X.through_focus_scores(psf, require_coverage_ok=True)
s_raw = X.through_focus_scores(psf, require_coverage_ok=False)
srows = []
for sid in sorted(set(s_cov) | set(s_raw)):
    srows.append(dict(sid=sid, score_cov=s_cov.get(sid, np.nan),
                      score_raw=s_raw.get(sid, np.nan),
                      delta=s_cov.get(sid, np.nan) - s_raw.get(sid, np.nan)))
print(pd.DataFrame(srows).round(3).to_string(index=False))
