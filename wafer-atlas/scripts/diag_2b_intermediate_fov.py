"""FOV survey for the 1<M<2 (intermediate-magnification) flat-2B-serpent task.

Make-or-break gate BEFORE any MTF work: for each 1<M<2 config that lives under the
2026-01-29 RAW root, register (reg_auto via lib_2b.register_best), then report
whether die type (2,1) (the 2B serpent) is in FOV -- centre-in-frame and coverage --
and the serpent line pitch (~clearance) so we know if the Airy disc is cleared.

Output a CSV row per config so the parent can decide which configs to push through
route2. Runs on nufan (16-core); registration is the only heavy step.
"""
from __future__ import annotations
import csv, sys, os
from pathlib import Path
import numpy as np, cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib_2b as L  # noqa: E402

RAW = L.RAW
IMG_W, IMG_H = L.IMAGE_W, L.IMAGE_H

# (atlas_M, lens, mag_label) for the 1<M<2 configs present under 2026-01-29.
CONFIGS = [
    (1.002, "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-1401", "1_1"),
    (1.003, "Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x", "1_1"),
    (1.005, "Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401", "1_1"),
    (1.010, "Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + 6T norm", "1_1"),
    (1.056, "Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x", "1_1"),
    (1.112, "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Olympus MCON-35", "1_1.16"),
    (1.121, "Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + 6T + 5T", "1.14_1"),
    (1.126, "Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + 5T + 6T", "1.14_1"),
    (1.140, "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T", "1.27_1"),
    (1.196, "NIKKOR Z MC 105mm f_2.8 VR S + 5T", "1.2_1"),
    (1.263, "Sigma Macro 105mm F2.8 EX DG OS HSM + 5T", "1.27_1"),
    (1.294, "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T", "1.3_1"),
    (1.370, "Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 5T", "1.4_1"),
    (1.373, "NIKKOR Z MC 105mm f_2.8 VR S + 6T", "1.4_1"),
    (1.387, "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001", "1.4_1"),
    (1.396, "Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x", "1.4_1"),
    (1.446, "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-1401", "1.4_1"),
    (1.458, "Sigma Macro 105mm F2.8 EX DG OS HSM + 6T", "1.5_1"),
    (1.485, "Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401", "1.4_1"),
    (1.496, "Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001", "1.4_1"),
    (1.540, "NIKKOR Z MC 105mm f_2.8 VR S + 5T + 6T", "1.6_1"),
    (1.547, "NIKKOR Z MC 105mm f_2.8 VR S + 6T + 5T", "1.6_1"),
    (1.557, "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 6T", "1.6_1"),
    (1.653, "Sigma Macro 105mm F2.8 EX DG OS HSM + 6T + 5T", "1.7_1"),
    (1.717, "Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 6T", "1.7_1"),
]

TYPE_NAME = {(2, 1): "2B-SERPENT"}


def all_2b_dies(aff):
    """Every die of type (2,1) with its centre anywhere in/near frame; report
    coverage and whether centre is strictly inside the image."""
    out = []
    for col in range(-1, 12):
        for row in range(-1, 7):
            if (col % 4, row % 4) != (2, 1):
                continue
            bx0, by0, bx1, by1 = L.block_bbox(col, row, aff)
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            ix0, iy0 = max(0, bx0), max(0, by0)
            ix1, iy1 = min(IMG_W, bx1), min(IMG_H, by1)
            full_area = max(1, (bx1 - bx0) * (by1 - by0))
            cov = max(0, ix1 - ix0) * max(0, iy1 - iy0) / full_area
            centre_in = (0 <= cx < IMG_W) and (0 <= cy < IMG_H)
            if cov > 0.05 or centre_in:
                out.append((f"{col}{chr(65 + row)}", round(cov, 2), int(cx), int(cy), centre_in))
    return out


def pick_ap(lens, mag):
    d = RAW / lens / mag
    aps = [p.name for p in d.iterdir() if p.is_dir()]
    for pref in ("F8", "F7.1", "F7", "F7.4", "F9.5", "F5.6"):
        if pref in aps:
            return pref
    return sorted(aps)[0] if aps else None


def main():
    rows = []
    for atlasM, lens, mag in CONFIGS:
        ap = pick_ap(lens, mag)
        tag = f"{lens.split('+')[0].strip()[:14]}|{'+'.join(p.strip() for p in lens.split('+')[1:])}|{mag}"
        if ap is None:
            print(f"{tag}: no aperture dir"); continue
        ap_dir = RAW / lens / mag / ap
        rmse, aff, jp0, jpgs = L.register_best(ap_dir)
        if aff is None:
            print(f"{tag} [{ap}]: REG-FAIL")
            rows.append(dict(lens=lens, mag=mag, ap=ap, atlasM=atlasM, regM="", rmse="",
                             reg="FAIL", best_cov="", best_die="", centre_in="",
                             line_pitch="", clearance="", get_block=""))
            continue
        M = aff["scale"] / L.M_ANCHOR_SCALE
        theta = aff.get("theta_deg", 0.0)
        dies = all_2b_dies(aff)
        # best = highest coverage with centre in frame, else highest coverage
        in_frame = [d for d in dies if d[4]]
        best = max(in_frame, key=lambda d: d[1]) if in_frame else (
            max(dies, key=lambda d: d[1]) if dies else None)

        # Does get_block actually return a (2,1) die? (its FOV gate is 0.85 cov)
        gb = L.get_block(jp0, aff, want_type=(2, 1), derotate=True)
        gb_label = gb["label"] if gb else "None"
        gb_is_2b = ""
        line_pitch = clearance = ""
        if gb is not None:
            col = int("".join(c for c in gb["label"] if c.isdigit()))
            row = "ABCDEF".index(gb["label"][-1])
            gb_is_2b = "yes" if (col % 4, row % 4) == (2, 1) else f"no({gb['label']})"
            if (col % 4, row % 4) == (2, 1):
                # measure serpent line pitch from the de-rotated block row-mean profile
                block = gb["block"]
                Hb, Wb = block.shape
                x0, x1 = int(0.20 * Wb), int(0.80 * Wb)
                prof = block[:, x0:x1].mean(axis=1)
                g = np.gradient(prof)
                from scipy.signal import find_peaks
                mind = max(4, int(8 * M))
                ris, _ = find_peaks(g, distance=mind, prominence=2.0)
                fal, _ = find_peaks(-g, distance=mind, prominence=2.0)
                alle = np.array(sorted(list(ris) + list(fal)))
                if len(alle) > 2:
                    d = np.diff(alle)
                    line_pitch = round(float(np.median(d)), 1)   # edge-to-edge spacing
                    clearance = round(float(np.median(d)), 1)    # half-line/half-gap = clearance to next edge

        bc = best[1] if best else 0
        bd = best[0] if best else "none"
        ci = best[4] if best else False
        print(f"{tag} [{ap}]: M={M:.3f} rmse={rmse:.2f} | 2B best={bd} cov={bc} centre_in={ci} "
              f"| get_block={gb_label} is2b={gb_is_2b} pitch={line_pitch}px")
        rows.append(dict(lens=lens, mag=mag, ap=ap, atlasM=atlasM, regM=round(M, 3),
                         rmse=round(rmse, 2), reg="ok", best_cov=bc, best_die=bd,
                         centre_in=ci, line_pitch=line_pitch, clearance=clearance,
                         get_block=gb_label, get_block_is2b=gb_is_2b,
                         all_2b=str(dies)))

    out = HERE / "diag_2b_intermediate_fov.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out}")
    # summary
    n_2b = sum(1 for r in rows if r.get("get_block_is2b") == "yes")
    n_centre = sum(1 for r in rows if r.get("centre_in") is True)
    print(f"SUMMARY: {len(rows)} configs | get_block returns true 2B: {n_2b} "
          f"| any 2B centre in frame: {n_centre}")


if __name__ == "__main__":
    main()
