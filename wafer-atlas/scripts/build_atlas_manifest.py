"""Task 3: build the characterise manifest from atlas-measured M.

m_lookup keys on (slug, mag_label) and uses vision_measured_mag first, so we write
atlas-M there. Scope = the pipeline-discoverable older-rig dates (2026-01-29,
2026-02-18) which carry a real path mag_label. nominal/gap/residual ride along as
ignored cross-check columns. Confidence is informational (vision always wins):
'high' if residual<3px & n_int>=12, else 'medium', else 'low'.
"""
from __future__ import annotations
import csv
from pathlib import Path

WA = Path(__file__).resolve().parent
IN = WA / "atlas_m_results.csv"
OUT = WA / "atlas_m_manifest.csv"
PIPELINE_DATES = {"2026-01-29", "2026-02-18"}
# atlas-M is trusted (overrides nominal) only when the registration is sound:
# a physically plausible scale AND a moderate fit residual. The M~0 scale-collapse
# overfit (rmse 0.40px, n_int 6) and the rmse~24px misfits are excluded -> those
# fall back to path-parsed nominal. A clean-but-few-point fit (low rmse, low n_int)
# with a SANE M that matches nominal is fine and kept.
M_MIN, M_MAX, RMSE_MAX = 0.15, 3.5, 8.0
FIELDS = ["slug", "mag_label", "vision_measured_mag", "vision_confidence",
          "nominal_M", "atlas_gap_pct", "ref_rmse_px", "n_int", "ap_used", "date"]


def trustworthy(M, rmse, n_int):
    try:
        m, r = float(M), float(rmse)
    except (ValueError, TypeError):
        return False
    return M_MIN < m < M_MAX and r < RMSE_MAX


def confidence(rmse, n_int):
    try:
        r, n = float(rmse), int(n_int)
    except (ValueError, TypeError):
        return "low"
    if r < 3.0 and n >= 12:
        return "high"
    if r < 6.0 and n >= 6:
        return "medium"
    return "low"


def main():
    rows = list(csv.DictReader(open(IN)))
    out_rows, skipped = [], {"not_pipeline_date": 0, "not_ok": 0, "untrustworthy_reg": 0}
    for r in rows:
        if r["date"] not in PIPELINE_DATES:
            skipped["not_pipeline_date"] += 1; continue
        if r["status"] != "ok":
            skipped["not_ok"] += 1; continue
        if not trustworthy(r["atlas_M"], r["ref_rmse_px"], r["n_int"]):
            skipped["untrustworthy_reg"] += 1
            print(f"  [skip:untrustworthy] M={r['atlas_M']} rmse={r['ref_rmse_px']} "
                  f"n_int={r['n_int']}  {r['lens'][:45]} [{r['mag_label']}] -> nominal fallback")
            continue
        out_rows.append(dict(
            slug=r["lens"], mag_label=r["mag_label"],
            vision_measured_mag=r["atlas_M"],
            vision_confidence=confidence(r["ref_rmse_px"], r["n_int"]),
            nominal_M=r["nominal_M"], atlas_gap_pct=r["gap_pct"],
            ref_rmse_px=r["ref_rmse_px"], n_int=r["n_int"],
            ap_used=r["ap_used"], date=r["date"]))
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(out_rows)
    print(f"{len(out_rows)} manifest rows -> {OUT}")
    print(f"skipped: {skipped}")
    from collections import Counter
    print("confidence:", dict(Counter(r["vision_confidence"] for r in out_rows)))
    big = [r for r in out_rows if r["atlas_gap_pct"] and abs(float(r["atlas_gap_pct"])) > 10]
    print(f"\n{len(big)} configs with |atlas-nominal gap| > 10% (label likely wrong):")
    for r in sorted(big, key=lambda r: -abs(float(r["atlas_gap_pct"]))):
        print(f"  {float(r['atlas_gap_pct']):+6.1f}%  nom={r['nominal_M']:>7}  "
              f"atlas={r['vision_measured_mag']:>7}  {r['slug'][:50]} [{r['mag_label']}]")


if __name__ == "__main__":
    main()
