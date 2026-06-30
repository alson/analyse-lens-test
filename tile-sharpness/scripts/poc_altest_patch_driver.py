"""Stage AltEst driver — same-physical-patch resampling + per-config patch stats.

Approaches 1 & 2 (and the substrate the rest reuse):
  * register each config once (reg_auto),
  * for each COMMON in-FOV atlas patch, resample BOTH the per-patch best-focus frame
    onto a COMMON subject-space grid (same samples_per_unit for every config -> same
    physical sampling density -> the intrinsic target spectrum is shared),
  * save the resampled patch (.npy) for the pairwise relative-MTF chain (analyse step),
  * record per-config-per-patch radial-PSD samples + non-spectral detail metrics
    (Tenengrad / Laplacian / variance / HF-wavelet) for approach #2.

Sharded: env SHARD="i/N". Common patches are chosen from the COMMON in-FOV rect found
by poc_altest_fov.py; we tile it into PATCH_UNITS-sized sub-patches at several field
positions so repeatability across regions can be checked (gate c).

Usage (nufan):
  SHARD=0/8 PYTHONPATH=.../src python poc_altest_patch_driver.py
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import poc_altest_lib as L

SUBSET = HERE / "poc_comb_chain_subset.csv"
OUT = HERE / "poc_comb_chain_out" / "altest"
PATCH_DIR = OUT / "patches"

# GLOBAL fixed atlas lattice. Each patch is a fixed atlas cell; a patch LABEL therefore
# denotes the SAME physical wafer region in every config (whether or not it is in-FOV).
# We emit whichever cells are in-FOV for a given config; pairwise comparison uses the
# cells two configs SHARE (the M~2 configs sit on a different die region with thin
# overlap — found by poc_altest_fov.py — so the chain rides on the overlapping cells).
PATCH_UNITS = 0.5      # sub-patch size in grid units
SAMPLES_PER_UNIT = 700 # common-grid sampling density (px per grid unit) — fixed for all configs
GLOBAL_CL = (1.5, 11.0)  # span the union of all configs' FOV (low-M reach high cl, M2 low cl)
GLOBAL_RL = (0.5, 6.0)
TOPK = 1


def patch_layout():
    """Fixed GLOBAL atlas lattice of PATCH_UNITS cells; label = atlas (i,j) so the same
    label = same physical patch across configs. Returns (cl0,rl0,cl1,rl1,label)."""
    out = []
    cl = GLOBAL_CL[0]; i = 0
    while cl + PATCH_UNITS <= GLOBAL_CL[1]:
        rl = GLOBAL_RL[0]; j = 0
        while rl + PATCH_UNITS <= GLOBAL_RL[1]:
            out.append((cl, rl, cl + PATCH_UNITS, rl + PATCH_UNITS, f"A{i:02d}{j:02d}"))
            rl += PATCH_UNITS; j += 1
        cl += PATCH_UNITS; i += 1
    return out


def config_id(c):
    return f"{c['lens']} | {c['mag_label']} | {c['aperture']}"


def short_id(c):
    lens = c["lens"]
    base = (lens.split(" + ")[0]
            .replace("NIKKOR Z MC 105mm f_2.8 VR S", "Z105")
            .replace("Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "AF200")
            .replace("Sigma Macro 105mm F2.8 EX DG OS HSM", "S105")
            .replace("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "S150")
            .replace("NIKKOR Z 100-400mm f_4.5-5.6 VR S", "Z100400"))
    acc = ""
    if " + " in lens:
        acc = "+" + lens.split(" + ", 1)[1].replace(" ", "").replace("Olympus", "") \
            .replace("Canon", "C").replace("Nikon", "")
    return f"{base}{acc}_{c['mag_label']}".replace(" ", "").replace("/", "")


def ap_to_n(aperture):
    return float(aperture.replace("F", "").replace("f_", "").replace("f", ""))


def main():
    with SUBSET.open() as fh:
        configs = list(csv.DictReader(fh))
    shard = os.environ.get("SHARD")
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        configs = [c for k, c in enumerate(configs) if k % n == i]
    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    patches = patch_layout()

    psd_rows = []   # config, patch, M, f_grid, psd
    det_rows = []   # config, patch, M, tenengrad, lap_energy, variance, hf_energy, mean, std
    meta_rows = []
    for c in configs:
        cid = config_id(c)
        sid = short_id(c)
        sd = Path(c["sample"]).parent
        p, M, jpgs = L.register_config(sd)
        if p is None:
            print(f"DROP {cid}: reg fail", flush=True); continue
        n_marked = ap_to_n(c["aperture"])
        # empirical image px per atlas grid unit (mean of u and v steps near FOV centre)
        ccl = 0.5 * (GLOBAL_CL[0] + GLOBAL_CL[1]); crl = 0.5 * (GLOBAL_RL[0] + GLOBAL_RL[1])
        x00, y00 = L.reg_auto.grid_xy_distorted(ccl, crl, p)
        xu, yu = L.reg_auto.grid_xy_distorted(ccl + 1.0, crl, p)
        xv, yv = L.reg_auto.grid_xy_distorted(ccl, crl + 1.0, p)
        px_per_unit = 0.5 * (np.hypot(xu - x00, yu - y00) + np.hypot(xv - x00, yv - y00))
        print(f"=== {sid} M={M:.3f} rmse={p['reg_fit_rmse_px']:.1f} px/unit={px_per_unit:.0f} ===", flush=True)
        meta_rows.append(dict(config=cid, sid=sid, M=M, rmse=p["reg_fit_rmse_px"],
                              n_marked=n_marked, px_per_unit=px_per_unit,
                              lens=c["lens"], mag_label=c["mag_label"]))
        # enumerate in-FOV boxes for all patches, then scan ONCE (decode per frame once)
        active = []   # (plab, a,b,a1,b1, box)
        for (a, b, a1, b1, plab) in patches:
            corners = [L.reg_auto.grid_xy_distorted(cc, rr, p)
                       for (cc, rr) in [(a, b), (a, b1), (a1, b), (a1, b1)]]
            xs = [pt[0] for pt in corners]; ys = [pt[1] for pt in corners]
            if (min(xs) < 60 or max(xs) > L.IMAGE_W - 60 or
                    min(ys) < 60 or max(ys) > L.IMAGE_H - 60):
                continue
            active.append((plab, a, b, a1, b1, (min(xs), min(ys), max(xs), max(ys))))
        if not active:
            print("  no in-FOV patches", flush=True); continue
        curves = L.scan_all_boxes(jpgs, [x[5] for x in active])
        # best-focus seq per box; group boxes by their best frame to decode color once
        by_frame = {}
        for bi, (plab, a, b, a1, b1, box) in enumerate(active):
            seqs, lvs = curves[bi]
            if len(seqs) == 0:
                continue
            seq = int(seqs[int(np.argmax(lvs))])
            by_frame.setdefault(seq, []).append((plab, a, b, a1, b1))
        for seq, group in by_frame.items():
            chan = L.decode_channel(jpgs[seq], "sat")
            if chan is None:
                continue
            for (plab, a, b, a1, b1) in group:
                patch = L.atlas_rect_to_common_grid(chan, p, a, b, a1, b1,
                                                    samples_per_unit=SAMPLES_PER_UNIT)
                if patch is None:
                    continue
                np.save(PATCH_DIR / f"{sid}__{plab}.npy", patch.astype(np.float32))
                f_grid, psd = L.radial_psd(patch)
                for fg, ps in zip(f_grid, psd):
                    if np.isfinite(ps):
                        psd_rows.append(dict(config=cid, sid=sid, patch=plab, M=M,
                                             n_marked=n_marked, f_grid=fg, psd=ps))
                det = L.detail_metrics(patch)
                det_rows.append(dict(config=cid, sid=sid, patch=plab, M=M,
                                     n_marked=n_marked, focus_seq=seq,
                                     mean=float(patch.mean()), std=float(patch.std()),
                                     **det))
        print(f"  {len(active)} in-FOV patches, {len(by_frame)} focus frames", flush=True)

    tag = (shard or "0_1").replace("/", "_")
    with (OUT / f"psd_shard_{tag}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["config", "sid", "patch", "M", "n_marked",
                                           "f_grid", "psd"])
        w.writeheader(); w.writerows(psd_rows)
    with (OUT / f"det_shard_{tag}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["config", "sid", "patch", "M", "n_marked",
                                           "focus_seq", "mean", "std", "tenengrad",
                                           "lap_energy", "variance", "hf_energy"])
        w.writeheader(); w.writerows(det_rows)
    with (OUT / f"meta_shard_{tag}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["config", "sid", "M", "rmse", "n_marked",
                                           "px_per_unit", "lens", "mag_label"])
        w.writeheader(); w.writerows(meta_rows)
    print(f"WROTE shard {tag}: {len(psd_rows)} psd, {len(det_rows)} det", flush=True)


if __name__ == "__main__":
    main()
