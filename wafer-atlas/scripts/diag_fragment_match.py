"""Prototype: resolve the column/row absolute offset by matching a sweep's
observed per-cell wafer coverage against the fragment-outline prior
(out/fragment_map.json). Row is fixed by the 4D-bar anchor; we score each
column candidate by how well the observed nick pattern matches the map.
"""
from __future__ import annotations

import importlib.util
import json
from itertools import product
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).parent
A = HERE.parent


def _load(m, f):
    s = importlib.util.spec_from_file_location(m, HERE / f)
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x


mm = _load("mm", "register_method_morphological.py")
af = _load("af", "anchor_fit_sweep.py")
ra = _load("ra", "reg_auto.py")
ATLAS = json.load(open(A / "atlas.json"))
FMAP = json.load(open(A / "out" / "fragment_map.json"))["coverage"]


def sweep_wafer_fullres(path):
    img = np.asarray(Image.open(path).convert("L"))
    small = cv2.resize(img, (img.shape[1] // 4, img.shape[0] // 4), interpolation=cv2.INTER_AREA)
    wsmall, _ = ra.wafer_mask(small)
    return cv2.resize(wsmall, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST), img.shape


def observed_cov(wafer, p, col, row, n=5):
    """Coverage over IN-FRAME samples only. Returns None if the cell is mostly
    outside the image (an off-FRAME cell must not be confused with off-WAFER)."""
    H, W = wafer.shape
    hits = infr = 0
    for u in np.linspace(0.15, 0.85, n):
        for v in np.linspace(0.15, 0.85, n):
            x, y = af.grid_xy(col + u, row + v, p, ATLAS)
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < W and 0 <= yi < H:
                infr += 1
                hits += int(wafer[yi, xi])
    if infr < 0.5 * n * n:
        return None
    return hits / infr


def score_candidate(det, wafer, col_x, row_y, cf, rf):
    """Build labelled pairs for offset (cf,rf), fit affine, then compare observed
    vs map coverage over all in-frame cells. Return (score, n_cells, affine)."""
    cl = [cf + i for i in range(len(col_x))]
    rl_top = rf + (len(row_y) - 1)
    pairs = []
    for ci, xd in enumerate(col_x):
        for ri, yd in enumerate(row_y):
            xo, yo = ra.derot_to_orig(float(xd), float(yd), det)
            pairs.append((cl[ci], rl_top - ri, xo, yo))
    p = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=det["tilt"], scale_init=0.5)
    H, W = wafer.shape
    diffs, weights = [], []
    for col in range(11):
        for row in range(6):
            x, y = af.grid_xy(col + 0.5, row + 0.5, p, ATLAS)
            if not (0 < x < W and 0 < y < H):
                continue
            m = FMAP.get(f"{col},{row}")
            if m is None:
                continue
            o = observed_cov(wafer, p, col, row)
            if o is None:                # off-frame cell -> not a wafer-edge signal
                continue
            diffs.append((o - m) ** 2)
            # weight edge/nicked cells more (they carry the discriminating signal)
            weights.append(1.0 + 3.0 * (1.0 - m))
    if not diffs:
        return -1e9, 0, p
    diffs = np.array(diffs); weights = np.array(weights)
    score = -float((diffs * weights).sum() / weights.sum())
    return score, len(diffs), p


def main():
    for name in ["sweep2_M1.0", "sweep3_M2.0", "sweep4_newer_rig"]:
        path, anchors = ra.SWEEPS[name]
        det = ra.detect(path)
        wafer, _ = sweep_wafer_fullres(path)
        col_x, row_y = det["col_x"], det["row_y"]
        # candidate offsets (phase-consistent run-length); fix row via 4D bar
        # Column PHASE. PREFER the wide-column pitch (reliable when a wide column
        # is in view, e.g. sweep2/4). Only when no clear wide pitch exists
        # (sweep3: 3 short pitches) fall back to the 4D-bar (its die-col is =0
        # mod4, so the col-line just left of the bar is =0 mod4).
        sp = np.diff(np.sort(col_x))
        clear_wide = sp.size and (sp.max() / np.median(sp) > 1.12)
        phase = None
        if clear_wide:
            cands = ra.candidate_offsets(col_x, ra.D_COL, ra.WIDE_COL, ra.N_COL_LINES)
            phase = (cands[0] % 4) if cands else None
        if phase is None:
            bars_all = ra.detect_4d_bars(det)
            if bars_all:
                bx = bars_all[0][0]
                left = np.where(col_x < bx)[0]
                k = int(left[-1]) if left.size else -1
                phase = (-k) % 4
        col_cands = ([c for c in range(0, ra.N_COL_LINES - len(col_x) + 1) if c % 4 == phase]
                     if phase is not None else list(range(0, ra.N_COL_LINES - len(col_x) + 1)))
        bars = ra.detect_4d_bars(det)
        row_votes = []
        for (bx, by) in bars:
            below = row_y[row_y > by]
            if below.size and (row_y[row_y < by]).size:
                j = int(np.where(row_y == below.min())[0][0]); row_votes.append(j + 4 - len(row_y))
        rf = int(np.bincount(np.array(row_votes) - min(row_votes)).argmax() + min(row_votes)) if row_votes else None
        row_cands = [rf] if rf is not None else (
            ra.candidate_offsets(np.sort(-row_y.astype(float)), ra.D_ROW, ra.TALL_ROW, ra.N_ROW_LINES)
            or list(range(0, ra.N_ROW_LINES - len(row_y) + 1)))
        print(f"\n=== {name} ===  col_cands={col_cands} row_cands={row_cands} (bar rf={rf})")
        results = []
        for cf, rf2 in product(col_cands, row_cands):
            sc, ncells, p = score_candidate(det, wafer, col_x, row_y, cf, rf2)
            # validate against known anchors
            errs = [np.hypot(*(np.array(af.grid_xy(c, r, p, ATLAS)) - [x, y])) for (c, r, x, y) in anchors]
            arm = float(np.sqrt(np.mean(np.square(errs))))
            results.append((sc, cf, rf2, ncells, arm))
        results.sort(reverse=True)
        margin = (results[0][0] - results[1][0]) if len(results) > 1 else 1.0
        verdict = f"COMMIT col={results[0][1]} row={results[0][2]}" if margin >= 0.02 else "AMBIGUOUS (no distinguishing nicks in view)"
        print(f"   margin={margin:.4f} -> {verdict}")
        for sc, cf, rf2, ncells, arm in results:
            mark = "  <-- BEST" if (sc, cf, rf2, ncells, arm) == results[0] else ""
            print(f"   col_first={cf} row_first={rf2}: score={sc:.4f} ({ncells} cells)  anchorRMSE={arm:.0f}px{mark}")


if __name__ == "__main__":
    main()
