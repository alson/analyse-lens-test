"""Stage AltEst-2 — build the WIDENED config subset for hardening P1/P2 and the variants.

UNTRACKED / exploratory. Emits poc_altest2_subset.csv in the same column format as
poc_comb_chain_subset.csv (date,lens,mag_label,nominal_M,focal,aperture,n_shots,sample)
so every Stage-AltEst driver reads it unchanged (only SUBSET path differs).

Widening rationale (P1 task: widen config coverage; gate coverage):
  * keep all 16 original spanning configs (continuity / the M~2 bridge),
  * add the vintage 55mm primes (f/2.8 AIS x2, f/3.5 Auto x3) + the 60mm AF-D at 1:1 ->
    the "modern macros > vintage 55 primes" gate, and low-M density,
  * add bare modern macros at EXTRA apertures (F5.6, F11) at 1:1 -> stress the f_px window
    against aperture / N_eff at fixed M,
  * add bare 70-180 + the 70-180+diopter rows (§D trustworthy table),
  * add more TC/diopter mid-M configs -> degrade gate + M-range fill (1.2..1.8).

We only emit (lens,mag,aperture) dirs that actually contain jpgs. Sample = first jpg
(any frame works; the drivers re-discover the focus stack from the parent dir).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
HERE = Path(__file__).resolve().parent
OUT = HERE / "poc_altest2_subset.csv"

# (lens dir name, mag_label, aperture) tuples to include. Mag/aperture must be real dirs.
WANT = [
    # --- the 16 original spanning configs (continuity) ---
    ("Sigma Macro 105mm F2.8 EX DG OS HSM", "1_1", "F8"),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "1_1", "F8"),
    ("NIKKOR Z MC 105mm f_2.8 VR S", "1_1", "F8"),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "1_1", "F8"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401", "1_1", "F8"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401", "1.4_1", "F8"),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-1401", "1_1", "F8"),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-1401", "1.4_1", "F8"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001", "1_1", "F8.5"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001", "2_1", "F11"),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001", "1_1", "F8.5"),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001", "2_1", "F11"),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Olympus MCON-35", "1_1.16", "F8"),
    ("NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D", "1.07_1", "F8"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + 5T + 6T", "1.7_1", "F8"),
    ("NIKKOR Z MC 105mm f_2.8 VR S + 5T + 6T", "1.6_1", "F8"),
    # --- vintage 55mm primes + 60mm at 1:1 (vintage gate; low-M density) ---
    ("Nikon Micro-Nikkor 55mm f_2.8 AIS 287318", "1_1", "F8"),
    ("Nikon Micro-Nikkor 55mm f_2.8 AIS 537016", "1_1", "F8"),
    ("Nikon Micro-Nikkor Auto 55mm f_3.5 209088", "1_1", "F8"),
    ("Nikon Micro-Nikkor Auto 55mm f_3.5 258263", "1_1", "F8"),
    ("Nikon AF Micro-Nikkor 60mm f_2.8D", "1_1", "F8"),
    # --- bare modern macros at EXTRA apertures (fixed M=1, vary N) ---
    ("Sigma Macro 105mm F2.8 EX DG OS HSM", "1_1", "F5.6"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM", "1_1", "F11"),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "1_1", "F5.6"),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "1_1", "F11"),
    ("NIKKOR Z MC 105mm f_2.8 VR S", "1_1", "F5.6"),
    ("NIKKOR Z MC 105mm f_2.8 VR S", "1_1", "F11"),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "1_1", "F11"),
    # --- bare 70-180 + 70-180+diopter (the §D trustworthy rows) ---
    ("Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED", "1_1.33", "F8"),
    ("Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + 6T", "1_1", "F8"),
    ("Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + 5T + 6T", "1.14_1", "F8"),
    # --- mid-M TC/diopter fill (degrade gate + M range 1.2..1.8) ---
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + 5T", "1.27_1", "F8"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + 6T", "1.5_1", "F8"),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T + 6T", "1.8_1", "F8"),
    ("NIKKOR Z MC 105mm f_2.8 VR S + 6T", "1.4_1", "F8"),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 6T", "1.7_1", "F8"),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x", "1_1", "F8"),
    ("Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 5T + 6T", "2_1", "F8"),
]


def nominal_from_mag(mag_label):
    # "1.4_1" -> 1.4 ; "1_1.16" -> 1/1.16 ; "1_1" -> 1.0
    a, b = mag_label.split("_")
    return float(a) / float(b)


def find_jpg(d: Path):
    js = sorted(p for p in d.iterdir() if p.suffix.lower() == ".jpg")
    return js[0] if js else None


def main():
    rows = []
    missing = []
    for lens, mag, ap in WANT:
        d = ROOT / lens / mag / ap
        if not d.is_dir():
            missing.append(f"{lens} | {mag} | {ap}  (no dir)")
            continue
        jpgs = [p for p in d.iterdir() if p.suffix.lower() == ".jpg"]
        if not jpgs:
            missing.append(f"{lens} | {mag} | {ap}  (no jpg)")
            continue
        sample = sorted(jpgs)[0]
        # focal: pull "NNN.0 mm" out of the filename if present
        m = re.search(r"\|(\d+(?:\.\d+)?)\s*mm\|", sample.name)
        focal = m.group(1) if m else ""
        rows.append(dict(
            date="2026-01-29", lens=lens, mag_label=mag,
            nominal_M=f"{nominal_from_mag(mag):.4f}", focal=focal,
            aperture=ap, n_shots=len(jpgs), sample=str(sample),
        ))
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "lens", "mag_label", "nominal_M",
                                           "focal", "aperture", "n_shots", "sample"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} configs -> {OUT}")
    if missing:
        print(f"MISSING ({len(missing)}):")
        for m in missing:
            print("  " + m)


if __name__ == "__main__":
    main()
