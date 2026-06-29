"""(3, robust) Bare-vs-TC from the EXISTING broad periodic-FFT magenta coverage.

The serpent-only bare-vs-TC read (study_bare_vs_tc.py) is fragile: configs frame
DIFFERENT serpent instances (bare 105 lands on die 9F, the macros+TC on 6B/6D), the
serpent SNR is low (1-3), and Sigma105+TC-2001 does not register. So for the controlled
ranking we use the established spanning metric — the periodic-FFT magenta bond-pad
arrays (REPORT §G.1, ~50 reads/config, broad field coverage) — at a COMMON subject
frequency.

This is still "k-normalised at a common feature/frequency" in spirit: the magenta pad
arrays are the same physical feature class across configs, so the Michelson contrast C
is directly comparable at a fixed subject frequency (k cancels for a shared feature
class; REPORT §G.1 explicitly compares configs at a common subject frequency).

We read the pre-computed rank_all.csv (out_periodic_fft), keep SNR>=3 magenta reads,
and average C in a +-band around the target subject frequency per config. Output: the
bare ranking + the bare->+TC drop ratios (TC-tolerance) + honest coverage notes.
"""
from __future__ import annotations
import csv
from pathlib import Path
import numpy as np

RANK_ALL = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test"
                "/tile-sharpness/out_periodic_fft/rank_all.csv")
TARGET_LPMM = 18.0
BAND = 5.0
SNR_MIN = 3.0

LENSES = [
    ("105 bare", "bare", "Sigma Macro 105mm F2.8 EX DG OS HSM"),
    ("150 bare", "bare", "Sigma APO Macro 150mm F2.8 EX DG OS HSM"),
    ("200 bare", "bare", "Nikon AF Micro-Nikkor 200mm f_4D IF-ED"),
    ("105+TC14", "TC-1401", "Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401"),
    ("150+TC14", "TC-1401", "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-1401"),
    ("105+TC20", "TC-2001", "Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001"),
    ("150+TC20", "TC-2001", "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001"),
]


def read():
    if not RANK_ALL.exists():
        raise SystemExit(f"missing {RANK_ALL}")
    return list(csv.DictReader(open(RANK_ALL)))


def c_at_common(rows, lens):
    sub = [r for r in rows if r["lens"] == lens and r["cls"] == "magenta"
           and float(r["snr"]) >= SNR_MIN]
    pts = sorted((float(r["f_subj_lpmm"]), float(r["contrast"]),
                  float(r["ceiling"])) for r in sub)
    if not pts:
        return None
    fs = np.array([p[0] for p in pts]); cs = np.array([p[1] for p in pts])
    ce = np.array([p[2] for p in pts])
    m = (fs >= TARGET_LPMM - BAND) & (fs <= TARGET_LPMM + BAND)
    if m.sum() >= 2:
        return dict(C=float(np.mean(cs[m])), ceil=float(np.mean(ce[m])),
                    n=int(m.sum()), span=(float(fs.min()), float(fs.max())), npad=len(pts))
    if len(fs) >= 2 and fs.min() <= TARGET_LPMM <= fs.max():
        return dict(C=float(np.interp(TARGET_LPMM, fs, cs)),
                    ceil=float(np.interp(TARGET_LPMM, fs, ce)),
                    n=0, span=(float(fs.min()), float(fs.max())), npad=len(pts))
    return dict(C=None, ceil=None, n=0, span=(float(fs.min()), float(fs.max())), npad=len(pts))


def main():
    rows = read()
    res = {}
    print(f"=== Periodic-FFT magenta bond-pads, C @ {TARGET_LPMM:.0f} lp/mm subject "
          f"(avg +-{BAND:.0f}, SNR>={SNR_MIN:.0f}) ===")
    for short, grp, lens in LENSES:
        d = c_at_common(rows, lens)
        if d is None:
            print(f"  {short:10s} [{grp:8s}]  NO DATA (not in rank_all)")
            res[short] = (grp, None)
            continue
        c = d["C"]
        flag = "" if d["n"] >= 2 else (" (no pads near target; extrapolated/none)" if c else " MISSING")
        print(f"  {short:10s} [{grp:8s}]  C={c if c is not None else 'MISSING':<8} "
              f"npad={d['npad']:2d} near={d['n']:2d} f_subj=[{d['span'][0]:.0f},{d['span'][1]:.0f}]{flag}")
        res[short] = (grp, c if d["n"] >= 2 else None)

    print("\n--- bare ranking (C @ common f; higher=sharper) ---")
    bare = [(s, v) for s, (g, v) in res.items() if g == "bare" and v]
    for s, v in sorted(bare, key=lambda x: -x[1]):
        print(f"  {s:10s} {v:.4f}")

    print("\n--- TC-tolerance (drop bare -> +TC; ratio = TC/bare, lower = bigger drop) ---")
    pairs = {"105": ("105 bare", "105+TC14", "105+TC20"),
             "150": ("150 bare", "150+TC14", "150+TC20")}
    for lens, (b, t14, t20) in pairs.items():
        bv = res[b][1]; v14 = res[t14][1]; v20 = res[t20][1]
        def rr(x):
            return f"x{x/bv:.2f}" if (x and bv) else ("MISSING" if x is None else "-")
        print(f"  Sigma {lens}: bare={bv if bv else '-'}  +TC14={v14 if v14 else '-'} ({rr(v14)})  "
              f"+TC20={v20 if v20 else '-'} ({rr(v20)})")
    print("\nNote: 105+TC-2001 does not register (REPORT §I) -> MISSING, never guessed. "
          "150+TC-2001 at M=2 has no magenta pad near 18 lp/mm (all alias to the ~76 cap) "
          "-> its common-f cell is unreliable.")


if __name__ == "__main__":
    main()
