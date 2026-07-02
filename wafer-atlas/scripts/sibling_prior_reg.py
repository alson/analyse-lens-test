"""Sibling-prior recovery registration (class A + class B) for the wafer atlas.

Two validated fixes, productionised from ``tile-sharpness/out_reg_cv`` prototypes
(``approach4b_tiltseed.py`` = class A, ``approach5b_prior.py`` + ``approach5_matched.py``
= class B). Both need a SAME-FAMILY sharp aperture that already registered cleanly
(the "sibling prior"): the user always shoots a full aperture series up to f/11-f/16,
and the sharpest usable aperture registers reliably, so a same-framing / same-M sibling
prior exists for essentially every config.

WHY these fail in the one-pass extract
---------------------------------------
* **Class A (tilt / detection mislock)** — at sharp LOW-M apertures the tilt detector
  locks onto sub-die TEXTURE (theta -> 1-3.9 deg vs the true ~4.5 deg), mixing dense
  ~20-90 ds-px texture lines into the ~63 ds-px scribe grid, so the affine mis-scales /
  collapses. Fix: FORCE the sibling's theta prior + expected die-pitch into de-rotation
  and peak-detection (reject sub-die texture), then choose the labelling matching the
  prior.
* **Class B (wide-open soft)** — the sub-pixel TROUGH refiner in ``refine_full_res``
  returns 0 intersections (the scribe trough is shallower than 1*std). Fix: seed from
  the sibling's sharp-aperture affine (origin shifted by phase correlation), then replace
  the trough refiner with a dark-bar MATCHED FILTER (symmetric blur preserves the scribe
  centroid), with an M-AWARE search band (~pitch/8; a fixed 100 px gave 0 locks at M~=2).

DESIGN CONTRACT
---------------
Nothing here mutates or monkeypatches ``reg_auto``; the one-pass extract path is
untouched. These entry points ONLY engage when a prior is supplied, so importing this
module does not change default registration behaviour.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import rotate as ndi_rotate
from scipy.signal import find_peaks

_HERE = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


reg_auto = _load("reg_auto", _HERE / "reg_auto.py")
af = _load("anchor_fit_sweep", _HERE / "anchor_fit_sweep.py")
ATLAS = json.load(open(_HERE.parent / "atlas.json"))
mm = reg_auto.mm

D_COL = ATLAS["die_pitch_px_in_0129"]["d_col"]
D_ROW = ATLAS["die_pitch_px_in_0129"]["d_row"]
M_ANCHOR_SCALE = reg_auto.M_ANCHOR_SCALE
N_COL_LINES = reg_auto.N_COL_LINES
N_ROW_LINES = reg_auto.N_ROW_LINES
SENSOR_PITCH_UM = 4.35
DOWNSAMPLE_W = 1024  # mm.load_gray_downscaled target width
FULL_W = 8256


# --------------------------------------------------------------------------- #
# central-focus frame ranking (mirrors apf / lib_cv rank_frames)
# --------------------------------------------------------------------------- #
def _central_lapvar(g):
    H, W = g.shape
    c = g[H // 2 - 800:H // 2 + 800, W // 2 - 800:W // 2 + 800]
    return cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var()


def rank_frames(jpgs, k=8):
    """Return the jpgs sorted by central Laplacian variance (sharpest first)."""
    step = max(1, len(jpgs) // 40)
    lv = []
    for jp in jpgs[::step]:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        lv.append((_central_lapvar(g) if g is not None else -1.0, jp))
    lv.sort(reverse=True, key=lambda t: t[0])
    return [jp for _, jp in lv]


# --------------------------------------------------------------------------- #
# sibling-prior resolution
# --------------------------------------------------------------------------- #
def resolve_sibling_prior(target, clean_regs):
    """Pick the best same-family clean registration to seed a failed config.

    ``target`` is a dict with at least ``family`` and ``nominal_M`` (float or NaN).
    ``clean_regs`` is a list of dicts each with ``family``, ``M``, ``rmse`` and any
    payload (e.g. ``sid``, ``sweep_dir``). Same-family candidates are ranked by NEAREST
    magnification to the target's nominal M (so the prior is a true same-framing sibling,
    e.g. an f/8-f/16 of the SAME lens+session+focal+mag) and, as a tie-break, LOWEST
    residual. When the target carries no nominal M (bare zooms), fall back to lowest
    residual alone. Returns the chosen clean-reg dict or ``None`` when the family has no
    clean sibling (the config then cannot be recovered this way -> report, don't crash).
    """
    fam = target.get("family")
    sibs = [r for r in clean_regs if r.get("family") == fam]
    if not sibs:
        return None
    nomM = target.get("nominal_M")
    have_nom = nomM is not None and np.isfinite(nomM) and nomM > 0
    tgtM = nomM if have_nom else None

    def key(r):
        rmse = r.get("rmse")
        rmse = rmse if (rmse is not None and np.isfinite(rmse)) else float("inf")
        if tgtM is not None:
            rM = r.get("M")
            dM = abs(rM - tgtM) if (rM is not None and np.isfinite(rM)) else float("inf")
            return (dM, rmse)
        return (rmse,)

    return sorted(sibs, key=key)[0]


# --------------------------------------------------------------------------- #
# CLASS A: tilt / pitch-gated detection + prior-consistent labelling
# --------------------------------------------------------------------------- #
def detect_at_tilt(path, tilt, exp_pitch_ds):
    """Detect scribes with a FORCED de-rotation angle + a die-pitch prior.

    Forces the sibling's ``tilt`` into de-rotation, extracts long-line peaks at that
    angle, and snaps to the expected single-die pitch (distance prior 0.55*exp_pitch_ds)
    so dense sub-die texture peaks are rejected. Returns a det dict compatible with
    ``reg_auto`` (col_x / row_y sorted, col_unit / row_unit set).
    """
    gray_ds, ds_scale, (H, W) = mm.load_gray_downscaled(path)
    derot = ndi_rotate(gray_ds, tilt, reshape=False, order=1, mode="reflect")
    wafer, _ = reg_auto.wafer_mask(gray_ds)
    mder = ndi_rotate(wafer.astype(np.float32), tilt, reshape=False, order=1) > 0.5
    bp = mm.bandpass_image(derot)
    Hd, Wd = derot.shape

    def peaks(axis, dim):
        sig = reg_auto._long_line_sig(bp, mder, axis)
        if sig.max() <= 0:
            return np.array([], float)
        dist = max(6, int(0.55 * exp_pitch_ds))
        pk = np.sort(find_peaks(sig / sig.max(), distance=dist, prominence=0.05)[0])
        return reg_auto._drop_edge_peaks(pk, dim).astype(float)

    col_x = peaks(0, Wd)
    row_y = peaks(1, Hd)
    det = dict(path=path, gray_ds=gray_ds, ds_scale=ds_scale, HW=(H, W),
               tilt=tilt, derot=derot, col_x=col_x, row_y=row_y)
    det["col_unit"] = reg_auto._robust_unit_pitch(col_x)
    det["row_unit"] = reg_auto._robust_unit_pitch(row_y)
    det["col_x"] = np.sort(reg_auto._clean_scribes(col_x, det["col_unit"])).astype(float)
    det["row_y"] = np.sort(reg_auto._clean_scribes(row_y, det["row_unit"])).astype(float)
    return det


def all_label_fits(det, theta_prior, scale_prior):
    """Try every gap-aware (col_first, row_first) labelling; fit each affine and score
    consistency with the prior (theta + scale). Returns a list of fit dicts."""
    col_x, row_y = det["col_x"], det["row_y"]
    if len(col_x) < 2 or len(row_y) < 2:
        return []
    col_rel = reg_auto._rel_indices(col_x)
    row_rel = reg_auto._rel_indices(row_y)
    col_span, row_span = int(col_rel[-1]), int(row_rel[-1])
    fits = []
    for cf in range(0, N_COL_LINES - col_span):
        cl_list = [int(cf + r) for r in col_rel]
        for rf in range(0, N_ROW_LINES - row_span):
            rl_top = rf + row_span
            rl_list = [rl_top - int(r) for r in row_rel]
            pairs = []
            for ci, xd in enumerate(col_x):
                for ri, yd in enumerate(row_y):
                    xo, yo = reg_auto.derot_to_orig(float(xd), float(yd), det)
                    pairs.append((cl_list[ci], rl_list[ri], xo, yo))
            p = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=det["tilt"],
                                    scale_init=scale_prior)
            dtheta = abs(p["theta_deg"] - theta_prior)
            dscale = abs(p["scale"] / scale_prior - 1.0)
            fits.append(dict(col_first=cf, row_first=rf, theta=p["theta_deg"],
                             scale=p["scale"], M=p["scale"] / M_ANCHOR_SCALE,
                             rmse=p["rmse_px"], dtheta=dtheta, dscale=dscale,
                             affine=p))
    return fits


def best_prior_consistent(fits, dtheta_max=2.0, dscale_max=0.10):
    """Among label fits consistent with the prior (theta + scale), the min-rmse one."""
    ok = [f for f in fits if f["dtheta"] <= dtheta_max and f["dscale"] <= dscale_max]
    if not ok:
        return None
    ok.sort(key=lambda f: f["rmse"])
    return ok[0]


def register_classA(jpgs, prior, *, topk=8, m_bounds=(0.1, 3.6), min_int=4):
    """Class-A recovery: tilt/pitch-gated detect + prior-consistent labelling + refine.

    ``prior`` must carry ``theta`` (deg) and ``scale`` (px per die). GUARDED: this only
    does anything meaningful with a prior; there is no default (prior-free) path. Returns
    the best refined affine dict (with ``reg_fit_rmse_px``, ``n_refine_intersections``,
    ``M`` fields via reg_auto) and a small record, or ``None``.

    Only a REAL full-res refine (``n_int >= min_int``, the 4-DOF affine minimum) counts:
    when ``refine_full_res`` finds < 4 intersections it returns the seed affine UNCHANGED
    with ``n_int == 0`` and the seed's (low-res, deceptively small) ``rmse_px``. Admitting
    that as a fix-A lock is a fake recovery -- the refiner never fit anything -- and it was
    letting soft configs (S150) "recover" at n_int=0 by inheriting the coarse label fit.
    We reject those here so the combiner falls through to class B's matched-filter fit.
    """
    theta_prior = float(prior["theta"])
    scale_prior = float(prior["scale"])
    exp_pitch_ds = float(np.mean(D_COL)) * scale_prior * (DOWNSAMPLE_W / FULL_W)
    best = None
    for jp in rank_frames(jpgs, k=topk)[:topk]:
        try:
            det = detect_at_tilt(str(jp), theta_prior, exp_pitch_ds)
        except Exception:
            continue
        if len(det["col_x"]) < 3 or len(det["row_y"]) < 2:
            continue
        fits = all_label_fits(det, theta_prior, scale_prior)
        bf = best_prior_consistent(fits)
        if bf is None:
            continue
        try:
            pr, n_int, _ = reg_auto.refine_full_res(str(jp), bf["affine"])
        except Exception:
            pr, n_int = bf["affine"], 0
        if n_int < min_int:  # refiner found < 4 intersections -> seed passed through, not a fit
            continue
        rmse = pr.get("rmse_px", bf["rmse"])
        M = pr.get("scale", bf["scale"]) / M_ANCHOR_SCALE
        if not (m_bounds[0] < M < m_bounds[1]):
            continue
        rec = dict(fix="A", frame=Path(jp).name, M=M,
                   theta=pr.get("theta_deg", bf["theta"]),
                   scale=pr.get("scale", bf["scale"]), rmse=float(rmse),
                   n_int=int(n_int), affine=pr,
                   col_first=bf["col_first"], row_first=bf["row_first"])
        if best is None or rmse < best["rmse"]:
            best = rec
    return best


# --------------------------------------------------------------------------- #
# CLASS B: sibling-affine seed + dark-bar matched-filter localization
# --------------------------------------------------------------------------- #
def matched_center(prof, bar_w, search_frac=0.6):
    """Sub-pixel dark-bar center of a 1-D profile via matched filtering.

    ``bar_w`` = expected scribe width (px). The template is a normalized negative box
    (dark bar) of width ``bar_w`` over a ~3*bar_w window; the NCC peak (parabolic-refined)
    is the center. A symmetric blur preserves a symmetric bar's centroid, so the matched
    center is essentially blur-invariant (unlike the gradient/trough refiner, which needs
    a deep trough). Returns ``(center_index, snr)`` or ``(None, 0.0)``.
    """
    n = prof.size
    if n < int(3 * bar_w) or n < 9:
        return None, 0.0
    p = prof.astype(np.float64)
    p = p - p.mean()
    tw = max(5, int(round(3 * bar_w)))
    if tw % 2 == 0:
        tw += 1
    t = np.zeros(tw)
    lo = tw // 2 - int(round(bar_w / 2))
    hi = tw // 2 + int(round(bar_w / 2)) + 1
    t[lo:hi] = -1.0
    t = t - t.mean()
    t = t / (np.linalg.norm(t) + 1e-9)
    corr = np.correlate(p, t, mode="same")
    m = int(n * (1 - search_frac) / 2)
    csearch = corr.copy()
    if m > 0:
        csearch[:m] = -np.inf
        csearch[-m:] = -np.inf
    i = int(np.argmax(csearch))
    if i < 1 or i > n - 2 or not np.isfinite(csearch[i]):
        return None, 0.0
    y0, y1, y2 = corr[i - 1], corr[i], corr[i + 1]
    denom = y0 - 2 * y1 + y2
    off = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-9 else 0.0
    med = np.median(corr)
    mad = np.median(np.abs(corr - med)) + 1e-9
    snr = (y1 - med) / (1.4826 * mad)
    return i + float(np.clip(off, -1, 1)), float(snr)


def matched_band_for_pitch(pitch_px):
    """M-aware half-band (px) for the matched-filter search window.

    The window must span a decent fraction of the die pitch so a wide/blurred high-M
    scribe sits inside it. A fixed 100 px gave 0 locks at M~=2 (pitch~2500 px); ~pitch/8
    fixes it. Clamped to [100, 500]."""
    return int(np.clip(pitch_px / 8.0, 100, 500))


def ensure_theta_rad(affine):
    """Return a copy of an affine seed guaranteed to carry ``theta_rad``.

    ``af.grid_xy`` (the grid-projection used by :func:`refine_matched`) reads
    ``params["theta_rad"]``, NOT ``theta_deg``. A sibling prior reconstructed from the
    pooled meta / a bare ``register_config`` record carries ``theta_deg`` (+ scale, x0/y0)
    but NOT ``theta_rad`` -- so grid_xy KeyError'd on every ROI, ``refine_matched`` raised,
    and ``register_classB`` silently swallowed it and returned None. That was the whole
    reason class B never fired in production (the ``out_reg_cv`` prototype seeded from a
    full ``fit_sweep_affine`` dict that DID carry ``theta_rad``). Derive it from
    ``theta_deg`` (or the ``theta`` alias) when absent. Pure / unit-tested."""
    a = dict(affine)
    if "theta_rad" in a:
        return a
    deg = a.get("theta_deg", a.get("theta"))
    if deg is not None:
        a["theta_rad"] = float(np.radians(float(deg)))
    return a


def refine_matched(path, p, R=None, band=None, bar_frac=0.03):
    """Like ``reg_auto.refine_full_res`` but localize each scribe with a matched filter.

    ``bar_frac`` = scribe width as a fraction of the die pitch (thin, ~2-4%). ``R`` /
    ``band`` default to M-aware sizes from the die pitch in this sweep. Returns
    ``(affine, n_int, pairs, snr_stats)``.
    """
    img = np.asarray(Image.open(path).convert("L")).astype(np.float32)
    H, W = img.shape
    # af.grid_xy projects through theta_rad; a theta_deg-only seed would KeyError. Self-heal
    # so refine_matched works on a reconstructed prior (see ensure_theta_rad).
    p = ensure_theta_rad(p)
    theta = p["theta_deg"]
    pitch_px = float(np.mean(D_COL)) * p["scale"]
    if band is None:
        band = matched_band_for_pitch(pitch_px)
    if R is None:
        R = band + 60
    bar_w = max(2.0, bar_frac * pitch_px)
    Mrot = cv2.getRotationMatrix2D((R, R), theta, 1.0)
    Minv = cv2.invertAffineTransform(Mrot)
    pairs = []
    snrs = []
    for cl in range(N_COL_LINES):
        for rl in range(N_ROW_LINES):
            xp, yp = af.grid_xy(cl, rl, p, ATLAS)
            xi, yi = int(round(xp)), int(round(yp))
            if not (R < xi < W - R and R < yi < H - R):
                continue
            roi = img[yi - R:yi + R, xi - R:xi + R]
            der = cv2.warpAffine(roi, Mrot, (2 * R, 2 * R), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REFLECT)
            cb = der[R - band:R + band, R - band:R + band]
            xt, sx = matched_center(cb.mean(axis=0), bar_w)
            yt, sy = matched_center(cb.mean(axis=1), bar_w)
            if xt is None or yt is None:
                continue
            xd, yd = (R - band) + xt, (R - band) + yt
            xr = Minv[0, 0] * xd + Minv[0, 1] * yd + Minv[0, 2]
            yr = Minv[1, 0] * xd + Minv[1, 1] * yd + Minv[1, 2]
            pairs.append((cl, rl, (xi - R) + xr, (yi - R) + yr))
            snrs.append(min(sx, sy))
    if len(pairs) < 4:
        return p, 0, [], {}
    pr = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=theta, scale_init=p["scale"])
    pr["model"] = "similarity"
    return pr, len(pairs), pairs, {"snr_med": float(np.median(snrs)),
                                   "snr_min": float(np.min(snrs))}


def phase_shift(sharp_gray, soft_gray, theta_deg, ds=8):
    """Coarse (dx, dy) translation of the soft frame relative to the sharp sibling via
    phase correlation on downscaled de-rotated frames. Absorbs a rail-induced origin
    shift between apertures. Returns full-res px."""
    a = cv2.resize(sharp_gray, (sharp_gray.shape[1] // ds, sharp_gray.shape[0] // ds))
    b = cv2.resize(soft_gray, (soft_gray.shape[1] // ds, soft_gray.shape[0] // ds))
    a = _derotate(a.astype(np.float64), theta_deg)
    b = _derotate(b.astype(np.float64), theta_deg)
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    a = a[:h, :w]
    b = b[:h, :w]
    try:
        win = np.outer(np.hanning(h), np.hanning(w))
        (sx, sy), _ = cv2.phaseCorrelate(a * win, b * win)
    except Exception:
        return 0.0, 0.0
    return sx * ds, sy * ds


def _derotate(gray, theta_deg):
    """De-rotate a 2-D array by theta about its center (matches periodic_fft.derotate)."""
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), theta_deg, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REFLECT)


def register_classB(jpgs, prior_affine, sharp_frame_path, *, topk=6,
                    m_bounds=(0.1, 3.6), min_int=4):
    """Class-B recovery: seed from the sibling sharp affine (origin phase-shifted),
    then matched-filter-refine on the soft config's sharpest frames.

    ``prior_affine`` = the sibling's full affine dict (theta_deg, scale, x0_img, y0_img).
    ``sharp_frame_path`` = the sibling frame the prior was fit on (for phase correlation).
    Returns the best refined affine record or ``None``.
    """
    sharp_g = cv2.imread(str(sharp_frame_path), cv2.IMREAD_GRAYSCALE)
    prior_affine = dict(prior_affine)
    # accept a prior carrying only ``theta`` (deg): refine_matched / phase_shift want
    # ``theta_deg``. Both are the tilt in degrees; alias so either key works.
    if "theta_deg" not in prior_affine and "theta" in prior_affine:
        prior_affine["theta_deg"] = prior_affine["theta"]
    # af.grid_xy needs theta_rad; a reconstructed prior may carry only theta_deg. Complete
    # the seed up front (refine_matched also self-heals, belt-and-braces).
    prior_affine = ensure_theta_rad(prior_affine)
    best = None
    for jp in rank_frames(jpgs, k=topk)[:topk]:
        soft_g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if soft_g is None or sharp_g is None:
            continue
        dx, dy = phase_shift(sharp_g, soft_g, prior_affine["theta_deg"])
        seed = dict(prior_affine)
        seed["x0_img"] = prior_affine["x0_img"] + dx
        seed["y0_img"] = prior_affine["y0_img"] + dy
        seed.pop("k1", None)
        seed.pop("k2", None)  # similarity for the re-localize
        try:
            pr, n_int, _pairs, snr = refine_matched(str(jp), seed)
        except Exception:
            continue
        if n_int < min_int:
            continue
        M = pr["scale"] / M_ANCHOR_SCALE
        if not (m_bounds[0] < M < m_bounds[1]):
            continue
        rec = dict(fix="B", frame=Path(jp).name, M=M, theta=pr["theta_deg"],
                   scale=pr["scale"], rmse=float(pr["rmse_px"]), n_int=int(n_int),
                   affine=pr, snr_med=snr.get("snr_med"), dx=float(dx), dy=float(dy))
        if best is None or pr["rmse_px"] < best["rmse"]:
            best = rec
    return best


# --------------------------------------------------------------------------- #
# combined recovery (min-rmse of {trough via classA, matched via classB})
# --------------------------------------------------------------------------- #
def object_rmse_um(rmse_px, M):
    """Object-space residual (um) = rmse_px * sensor-pitch / M.

    This is the metric the recovery decision (and the outer reg_guard 25 um ceiling)
    is expressed in, so the class-A / class-B combiner MUST rank on it, not on raw px:
    a low-M fix and a high-M fix trade px against object um differently (AF200 at M~2 has
    2x fewer object um per px than a M~1 config). Ranking on raw px let a fix-A lock at
    21.5 px / M=2.07 (= 45 um, FAILS the ceiling) hide a real fix-B lock at 5.5 px / M=2.06
    (= 11.5 um, PASSES). Pure / unit-tested."""
    if not (M is not None and np.isfinite(M) and M > 0):
        return float("inf")
    if not (rmse_px is not None and np.isfinite(rmse_px)):
        return float("inf")
    return float(rmse_px) * SENSOR_PITCH_UM / M


def recover_config(jpgs, prior, sharp_frame_path, *, m_bounds=(0.1, 3.6)):
    """Run BOTH fixes for a dropped config and return the min-object-um plausible result.

    ``prior`` is the resolved sibling clean-reg's affine record (needs theta + scale, and
    x0_img / y0_img for class B). Class A (tilt/pitch gating) attacks the sharp-but-
    mislocked detection; class B (matched filter) attacks the wide-open-soft trough
    failure. Both paths only admit a REAL fit (n_int >= 4). We try both and keep the
    candidate with the smallest OBJECT-SPACE rmse (rmse_px * pitch / M), which is what the
    downstream 25 um ceiling gates on -- NOT the raw px rmse (that let a bad high-px fix-A
    win over the real fix-B). Returns a record dict or None (report as genuinely failed;
    do NOT fake-recover by inheriting the sibling wholesale). The caller applies reg_guard
    + select_registration plausibility on the winner.
    """
    cands = []
    try:
        a = register_classA(jpgs, prior, m_bounds=m_bounds)
    except Exception:
        a = None
    if a is not None:
        cands.append(a)
    if sharp_frame_path is not None and "x0_img" in prior:
        try:
            b = register_classB(jpgs, prior, sharp_frame_path, m_bounds=m_bounds)
        except Exception:
            b = None
        if b is not None:
            cands.append(b)
    if not cands:
        return None
    for c in cands:
        c["rmse_um"] = object_rmse_um(c.get("rmse"), c.get("M"))
    return min(cands, key=lambda r: r["rmse_um"])


# --------------------------------------------------------------------------- #
# class-A family-consistency audit
# --------------------------------------------------------------------------- #
def audit_family_consistency(clean_regs, *, theta_tol_deg=1.5, m_frac_tol=0.15,
                             min_family=2):
    """Flag pass-1 CLEAN regs whose theta or M is inconsistent with their family.

    A texture-mislock (class-A) signature is a theta far from the family median (the wafer
    is fixed on the QR plate, so theta is ~constant within a session) or an M far from the
    family/nominal. For each family with >= ``min_family`` clean regs, flag any member with
    ``|theta - median_theta| > theta_tol_deg`` OR (when a family-median M exists)
    ``|M - median_M| / median_M > m_frac_tol``. Returns a list of per-config audit dicts:
    ``sid, family, theta, M, family_median_theta, family_median_M, flagged, flag_reason``.
    Families with a single clean reg are emitted unflagged (no siblings to compare to).
    """
    by_fam = {}
    for r in clean_regs:
        by_fam.setdefault(r.get("family"), []).append(r)
    out = []
    for fam, members in by_fam.items():
        thetas = np.array([m["theta"] for m in members
                           if m.get("theta") is not None and np.isfinite(m["theta"])])
        Ms = np.array([m["M"] for m in members
                       if m.get("M") is not None and np.isfinite(m["M"])])
        med_t = float(np.median(thetas)) if thetas.size else float("nan")
        med_m = float(np.median(Ms)) if Ms.size else float("nan")
        can_flag = len(members) >= min_family
        for m in members:
            th = m.get("theta")
            M = m.get("M")
            reasons = []
            if can_flag and np.isfinite(med_t) and th is not None and np.isfinite(th):
                if abs(th - med_t) > theta_tol_deg:
                    reasons.append(f"theta_off({th:.2f}vs{med_t:.2f})")
            if (can_flag and np.isfinite(med_m) and med_m > 0
                    and M is not None and np.isfinite(M)):
                if abs(M - med_m) / med_m > m_frac_tol:
                    reasons.append(f"M_off({M:.3f}vs{med_m:.3f})")
            out.append(dict(sid=m.get("sid"), family=fam, theta=th, M=M,
                            family_median_theta=med_t, family_median_M=med_m,
                            flagged=bool(reasons), flag_reason=";".join(reasons)))
    return out
