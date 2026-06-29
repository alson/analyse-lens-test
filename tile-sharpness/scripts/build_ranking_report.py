"""Task 5: turn accessory_ranking.csv into the two deliverable tables.

(1) M-VALIDATION: atlas-M vs nominal per combo (from D's robust per-combo
    registration, which supersedes the quick Task-2 driver). Flags label-suspect
    (|gap|>10% at a sound fit), poor-registration, and degenerate fits.
(2) RESOLUTION RANKING: per (config, aperture) centre + corner-mean subject lp/mm
    with the diffraction ceiling + headroom regime tag (glass-limited = trustworthy;
    >=1 = MTF50 over-read, read the ceiling instead).

Prints both as text and writes ranking_validation.csv + ranking_resolution.csv.
"""
from __future__ import annotations
import csv
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "out_accessory_atlas/accessory_ranking.csv"
OUTDIR = R.parent


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def regime(headroom):
    if headroom is None:
        return "no-data"
    if headroom >= 1.0:
        return "OVER-READ"          # measured > ceiling: untrustworthy (read ceiling)
    if headroom >= 0.85:
        return "diffraction-ltd"
    return "glass-ltd"              # comfortably below ceiling: trustworthy


def main():
    rows = list(csv.DictReader(open(R)))

    # ---- (1) validation: one row per combo ----
    combos = {}
    for r in rows:
        combos.setdefault((r["lens"], r["mag_label"]), r)  # first ap row carries M/reg
    val = []
    for (lens, mag), r in combos.items():
        atlas, nom = fnum(r["atlas_M"]), fnum(r["nominal_M"])
        rmse = fnum(r["reg_rmse_px"])
        gap = (atlas/nom - 1)*100 if (atlas and nom) else None
        if r["status"] == "degenerate_M":
            flag = "DEGENERATE"
        elif rmse is not None and rmse > 8:
            flag = "REG-POOR"
        elif gap is not None and abs(gap) > 10:
            flag = "LABEL-SUSPECT"
        else:
            flag = "ok"
        val.append(dict(lens=lens, mag_label=mag, nominal_M=nom, atlas_M=atlas,
                        gap_pct=gap, reg_rmse_px=rmse, flag=flag))
    val.sort(key=lambda v: (-(abs(v["gap_pct"]) if v["gap_pct"] is not None else -1)))
    with (OUTDIR / "ranking_validation.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(val[0].keys())); w.writeheader(); w.writerows(val)
    print("="*92, "\nM-VALIDATION (atlas vs nominal; sorted by |gap|)\n" + "="*92)
    print(f"{'flag':<14}{'gap%':>7}{'nom':>7}{'atlas':>7}{'rmse':>6}  config")
    for v in val:
        g = f"{v['gap_pct']:+.1f}" if v["gap_pct"] is not None else "-"
        rm = f"{v['reg_rmse_px']:.1f}" if v["reg_rmse_px"] is not None else "-"
        nm = f"{v['nominal_M']:.3f}" if v['nominal_M'] is not None else "-"
        am = f"{v['atlas_M']:.3f}" if v['atlas_M'] is not None else "-"
        print(f"{v['flag']:<14}{g:>7}{nm:>7}{am:>7}{rm:>6}  {v['lens'][:48]} [{v['mag_label']}]")

    # ---- (2) resolution ranking: per (config, aperture) ----
    res = []
    for r in rows:
        if r["status"] != "ok":
            continue
        cen, cmean = fnum(r["centre"]), fnum(r["corner_mean"])
        ceil, head = fnum(r["ceiling_lpmm"]), fnum(r["centre_headroom"])
        res.append(dict(config=f"{r['lens']} [{r['mag_label']}]", ap=r["aperture"],
                        M=fnum(r["atlas_M"]), n_eff=fnum(r["n_eff"]), ceiling=ceil,
                        centre=cen, corner_mean=cmean, uniformity=fnum(r["uniformity"]),
                        headroom=head, regime=regime(head), covered=r["covered"]))
    with (OUTDIR / "ranking_resolution.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)

    for ap in ("F8", "F11"):
        sub = [x for x in res if x["ap"] == ap and x["centre"] is not None]
        sub.sort(key=lambda x: -x["centre"])
        if not sub:
            continue
        print("\n" + "="*92, f"\nRESOLUTION @ {ap} (subject lp/mm; sorted by centre). "
              f"regime: glass-ltd=trust, OVER-READ=read ceiling\n" + "="*92)
        print(f"{'M':>5}{'Neff':>6}{'ceil':>6}{'centre':>7}{'corn':>6}{'unif':>6}"
              f"{'head':>6}  {'regime':<15} config")
        for x in sub:
            u = f"{x['uniformity']:.2f}" if x["uniformity"] is not None else "-"
            cm = f"{x['corner_mean']:.1f}" if x["corner_mean"] is not None else "-"
            h = f"{x['headroom']:.2f}" if x["headroom"] is not None else "-"
            print(f"{x['M']:>5.2f}{x['n_eff']:>6.1f}{x['ceiling']:>6.1f}{x['centre']:>7.1f}"
                  f"{cm:>6}{u:>6}{h:>6}  {x['regime']:<15} {x['config'][:46]}")
    print(f"\n[written] {OUTDIR/'ranking_validation.csv'}, {OUTDIR/'ranking_resolution.csv'}")


if __name__ == "__main__":
    main()
