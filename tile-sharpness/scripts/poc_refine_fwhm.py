#!/usr/bin/env python
"""POC 3 — refine the through-focus FWHM/peak estimator to PHYSICAL mm.

Wires :mod:`tile_sharpness.focus_physical` (the pure conversion + flag layer) to
POC-1's per-patch through-focus fits (``psffoc_shard_*.csv``) and POC-2's step
calibration, and produces:

  * APPLICATION — a per-patch PHYSICAL focus table for the cached 2026-01-29
    cohort (``cross_m_relative_mtf_poc_focus_out/psffoc_shard_*.csv``). These
    sweeps have NO documented rail step, so ``step_mm`` is DoF-estimated. This is
    the table POC 4 (decentering / field curvature) consumes.

  * VALIDATION — on the 2026-05 DOCUMENTED sweeps (which DO record the rail step),
    two clean, NON-CIRCULAR checks:
      (1) per-patch ``mu_mm`` / ``fwhm_mm`` computed with the DoF-ESTIMATED step vs
          the DOCUMENTED step — the discrepancy is exactly the POC-2 step error.
          (``mu`` POSITION is model-independent, so its accuracy is purely the step
          accuracy.)
      (2) internal consistency — the across-FIELD spread of per-patch ``mu_mm``
          (what POC 4 uses) vs the per-patch ``mu`` fit noise (median fit stderr in
          frames). Shows the field spread is resolvable above the fit noise.
    Plus the M>1 extrapolation sensitivity.

Run on nufan (per-host venv, NFS data):
    direnv exec . uv run python scripts/poc_refine_fwhm.py apply
    direnv exec . uv run python scripts/poc_refine_fwhm.py validate
    direnv exec . uv run python scripts/poc_refine_fwhm.py all
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TS = HERE.parent
sys.path.insert(0, str(TS / "src"))

from tile_sharpness import focus_physical as FP  # noqa: E402
from tile_sharpness.cross_m_relative_mtf import gaussian_defocus_fwhm  # noqa: E402

# Load the POC-2 script (lives in scripts/, not the package) for sweep discovery
# + the documented-step ground truth + the cached central-ROI lapvar curves.
_SPEC = importlib.util.spec_from_file_location("poc_dof_step_size",
                                               HERE / "poc_dof_step_size.py")
poc2 = importlib.util.module_from_spec(_SPEC)
sys.modules["poc_dof_step_size"] = poc2
_SPEC.loader.exec_module(poc2)

POC1_OUT = TS / "cross_m_relative_mtf_poc_focus_out"
OUT_DIR = TS / "out_poc_refine_fwhm"


# --------------------------------------------------------------------------- #
# APPLICATION — 2026-01-29 cached per-patch fits -> physical mm
# --------------------------------------------------------------------------- #
def load_psffoc(out_dir: Path) -> pd.DataFrame:
    """Pool the cached POC-1 ``psffoc_shard_*.csv`` per-patch through-focus fits."""
    files = sorted(out_dir.glob("psffoc_shard_*.csv"))
    if not files:
        raise FileNotFoundError(f"no psffoc shards in {out_dir}")
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def apply_cohort(psffoc: pd.DataFrame, *, documented: dict[str, float] | None = None,
                 log=print) -> pd.DataFrame:
    """Per-patch physical focus table from pooled psffoc fits.

    One ``step_mm`` per sweep (sid): ``documented`` if supplied for that sid, else
    the DoF inversion from the sweep's central-tendency FWHM_frames. To keep the
    per-sweep step a SINGLE value (POC 4 needs ``step_mm`` constant within a sweep),
    we feed the DoF inversion the MEDIAN of the per-patch ``fwhm`` (the ``ok`` patches
    only, so a few truncated corners do not bias the step). Then every patch's
    ``mu_frames`` / ``fwhm_frames`` is converted with that one step.
    """
    documented = documented or {}
    rows = []
    for sid, g in psffoc.groupby("sid"):
        m = float(g["M"].iloc[0])
        n_working = float(g["n_eff"].iloc[0])
        marked_f = float(g["n_marked"].iloc[0])
        # per-sweep FWHM_frames central tendency from the OK patches (fall back to all)
        ok = g[g["coverage_flag"] == "ok"]
        base = ok if len(ok) else g
        sweep_fwhm_frames = float(np.nanmedian(base["fwhm"].to_numpy(float)))
        step = FP.resolve_step(m=m, n_working=n_working, marked_f=marked_f,
                               fwhm_frames=sweep_fwhm_frames,
                               documented_step_mm=documented.get(str(sid)))
        for r in g.itertuples():
            phys = FP.patch_physical_row(
                mu_frames=float(r.mu), fwhm_frames=float(r.fwhm),
                coverage_flag=str(r.coverage_flag), step=step,
                m=m, n_working=n_working, marked_f=marked_f)
            rows.append(dict(config=r.config, sid=sid, patch=r.patch, M=m,
                             n_marked=marked_f, n_eff=n_working, nstack=int(r.nstack),
                             mu_frames=float(r.mu), fwhm_frames=float(r.fwhm),
                             peak_pos_frac=float(r.peak_pos_frac),
                             edge_dist_frames=float(r.edge_dist_frames),
                             **phys))
        log(f"  {sid:32s} M={m:5.3f} N_eff={n_working:6.2f} "
            f"step={step.step_mm:.5f}mm ({step.step_source}"
            f"{' LOW-CONF' if step.low_confidence else ''}) "
            f"sweep_fwhm_frames={sweep_fwhm_frames:.2f} npatch={len(g)}", flush=True)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# VALIDATION — 2026-05 documented sweeps, per-patch grid through-focus
# --------------------------------------------------------------------------- #
def _grid_boxes(w: int, h: int, n: int, frac: float):
    """``n×n`` patch boxes over the centred ``frac`` region of a ``w×h`` frame."""
    cw, ch = int(w * frac), int(h * frac)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    bw, bh = cw // n, ch // n
    boxes = []
    for r in range(n):
        for c in range(n):
            bx = x0 + c * bw
            by = y0 + r * bh
            boxes.append((bx, by, bx + bw, by + bh))
    return boxes


def _gaussian_fit_with_stderr(seqs, vals):
    """Per-patch Gaussian-of-defocus fit -> (mu, fwhm, mu_stderr_frames).

    Reuses the shared :func:`gaussian_defocus_fwhm` for (sigma, fwhm, mu), then
    estimates the standard error of the fitted CENTRE mu by propagating the residual
    scatter of the weighted log-quadratic through the curvature term — a cheap,
    closed-form mu-stderr that quantifies the per-patch fit noise (validation #2).
    """
    sigma, fwhm, mu = gaussian_defocus_fwhm(seqs, vals)
    if not np.isfinite(mu):
        return mu, fwhm, float("nan")
    seqs = np.asarray(seqs, float)
    vals = np.asarray(vals, float)
    base = np.percentile(vals, 10)
    v0 = np.clip(vals - base, 0, None)
    pk = v0.max()
    if pk <= 0:
        return mu, fwhm, float("nan")
    sel = v0 >= 0.25 * pk
    z, y = seqs[sel], v0[sel]
    if len(z) < 5:
        return mu, fwhm, float("nan")
    A = np.column_stack([np.ones_like(z), z, z * z])
    ly = np.log(np.clip(y, 1e-9, None))
    coef, *_ = np.linalg.lstsq(A, ly, rcond=None)
    resid = ly - A @ coef
    dof = max(len(z) - 3, 1)
    s2 = float(resid @ resid) / dof
    try:
        cov = s2 * np.linalg.inv(A.T @ A)
    except np.linalg.LinAlgError:
        return mu, fwhm, float("nan")
    b, cc = coef[1], coef[2]              # log y ~ a + b z + c z^2 ; mu = -b/(2c)
    if cc == 0:
        return mu, fwhm, float("nan")
    # var(mu) via the gradient of mu wrt (b, c): d mu/db = -1/(2c); d mu/dc = b/(2c^2)
    gb, gc = -1.0 / (2 * cc), b / (2 * cc * cc)
    var_mu = (gb * gb * cov[1, 1] + gc * gc * cov[2, 2]
              + 2 * gb * gc * cov[1, 2])
    return mu, fwhm, float(np.sqrt(var_mu)) if var_mu > 0 else float("nan")


def _validate_sweep_worker(args):
    sw, n_grid, roi_frac = args
    import cv2
    seqs = {}
    lvs = {}
    boxes = None
    for seq, jp in enumerate(sw.base_jpgs):
        g = cv2.imread(str(jp), cv2.IMREAD_REDUCED_GRAYSCALE_4)
        if g is None:
            continue
        if boxes is None:
            h, w = g.shape[:2]
            boxes = _grid_boxes(w, h, n_grid, roi_frac)
            seqs = {i: [] for i in range(len(boxes))}
            lvs = {i: [] for i in range(len(boxes))}
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            roi = g[y0:y1, x0:x1]
            if roi.size == 0 or min(roi.shape) < 8:
                continue
            f = roi.astype(np.float64)
            lap = (-4 * f + np.roll(f, 1, 0) + np.roll(f, -1, 0)
                   + np.roll(f, 1, 1) + np.roll(f, -1, 1))[1:-1, 1:-1]
            seqs[i].append(seq)
            lvs[i].append(float(lap.var()))
    nstack = len(sw.base_jpgs)
    out = []
    for i in (seqs or {}):
        s = np.asarray(seqs[i], float)
        v = np.asarray(lvs[i], float)
        if len(s) < 7:
            continue
        mu, fwhm, mu_se = _gaussian_fit_with_stderr(s, v)
        out.append(dict(patch=f"g{i:02d}", mu=mu, fwhm=fwhm, mu_stderr_frames=mu_se,
                        nstack=nstack))
    return sw.session, sw.slug, sw.f_dir, sw.m, sw.n_working, sw.marked_f, \
        sw.true_step_mm, out


def validate(*, n_grid: int = 5, roi_frac: float = 0.5, workers: int = 16,
             log=print) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-patch validation on the 2026-05 documented sweeps.

    Returns ``(per_patch_df, per_sweep_df)``. Per patch we fit mu/fwhm on an
    ``n_grid×n_grid`` ROI grid, then convert with BOTH the documented step and the
    DoF-estimated step (the estimated step uses the sweep's central-ROI FWHM_frames,
    exactly as POC 2 derives it). The discrepancy ``estimated/documented`` is the
    POC-2 step error and is identical across a sweep's patches (it is the per-sweep
    step ratio); we report its distribution across sweeps.
    """
    from concurrent.futures import ProcessPoolExecutor
    sweeps = [s for s in poc2.discover_newer_sweeps() if s.is_bare]
    log(f"validate: {len(sweeps)} bare documented sweeps")
    args = [(sw, n_grid, roi_frac) for sw in sweeps]
    if workers > 1 and len(args) > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_validate_sweep_worker, args))
    else:
        results = [_validate_sweep_worker(a) for a in args]

    patch_rows, sweep_rows = [], []
    for session, slug, f_dir, m, n_working, marked_f, doc_step, patches in results:
        # DoF-estimated step from this sweep's central-ROI FWHM_frames (POC-2 way).
        valid_fwhm = [p["fwhm"] for p in patches if np.isfinite(p["fwhm"])]
        sweep_fwhm = float(np.median(valid_fwhm)) if valid_fwhm else float("nan")
        step_dof = FP.resolve_step(m=m, n_working=n_working, marked_f=marked_f,
                                   fwhm_frames=sweep_fwhm, documented_step_mm=None)
        step_doc = FP.resolve_step(m=m, n_working=n_working, marked_f=marked_f,
                                   fwhm_frames=sweep_fwhm,
                                   documented_step_mm=doc_step)
        step_ratio = (step_dof.step_mm / doc_step
                      if np.isfinite(step_dof.step_mm) and doc_step else float("nan"))
        mu_ses = [p["mu_stderr_frames"] for p in patches
                  if np.isfinite(p.get("mu_stderr_frames", float("nan")))]
        mu_mm_doc_list = []
        for p in patches:
            cov = "ok"  # grid patches: trust the fit; coverage handled by stderr/range
            doc_phys = FP.patch_physical_row(
                mu_frames=p["mu"], fwhm_frames=p["fwhm"], coverage_flag=cov,
                step=step_doc, m=m, n_working=n_working, marked_f=marked_f)
            dof_phys = FP.patch_physical_row(
                mu_frames=p["mu"], fwhm_frames=p["fwhm"], coverage_flag=cov,
                step=step_dof, m=m, n_working=n_working, marked_f=marked_f)
            if np.isfinite(doc_phys["mu_mm"]):
                mu_mm_doc_list.append(doc_phys["mu_mm"])
            patch_rows.append(dict(
                session=session, slug=slug, f_dir=f_dir, patch=p["patch"], M=m,
                n_eff=n_working, mu_frames=p["mu"], fwhm_frames=p["fwhm"],
                mu_stderr_frames=p["mu_stderr_frames"],
                mu_mm_doc=doc_phys["mu_mm"], fwhm_mm_doc=doc_phys["fwhm_mm"],
                mu_mm_dof=dof_phys["mu_mm"], fwhm_mm_dof=dof_phys["fwhm_mm"],
                mu_mm_disc=(dof_phys["mu_mm"] / doc_phys["mu_mm"]
                            if doc_phys["mu_mm"] else float("nan")),
                fwhm_mm_disc=(dof_phys["fwhm_mm"] / doc_phys["fwhm_mm"]
                              if doc_phys["fwhm_mm"] else float("nan"))))
        # internal-consistency: across-field mu_mm spread (documented step) vs fit noise
        mu_mm_doc_arr = np.asarray(mu_mm_doc_list, float)
        field_spread_mm = (float(np.nanstd(mu_mm_doc_arr))
                           if mu_mm_doc_arr.size > 1 else float("nan"))
        med_mu_se = float(np.median(mu_ses)) if mu_ses else float("nan")
        sweep_rows.append(dict(
            session=session, slug=slug, f_dir=f_dir, M=m, n_eff=n_working,
            marked_f=marked_f, doc_step_mm=doc_step, dof_step_mm=step_dof.step_mm,
            step_ratio_dof_over_doc=step_ratio, sweep_fwhm_frames=sweep_fwhm,
            n_patch=len(patches), median_mu_stderr_frames=med_mu_se,
            field_mu_mm_spread=field_spread_mm,
            median_mu_stderr_mm=med_mu_se * doc_step if np.isfinite(med_mu_se) else float("nan"),
            low_confidence=step_dof.low_confidence))
        log(f"  {session[:24]:24s} {f_dir:5s} M={m:4.2f} doc={doc_step:.5f} "
            f"dof={step_dof.step_mm:.5f} ratio={step_ratio:.3f} "
            f"mu_se={med_mu_se:.2f}fr fieldspread={field_spread_mm:.4f}mm", flush=True)
    return pd.DataFrame(patch_rows), pd.DataFrame(sweep_rows)


# --------------------------------------------------------------------------- #
# M>1 extrapolation sensitivity
# --------------------------------------------------------------------------- #
def extrapolation_table(phys: pd.DataFrame) -> pd.DataFrame:
    """Per-sweep M-exponent (1 vs 2) sensitivity for the DoF-estimated sweeps."""
    rows = []
    for sid, g in phys.groupby("sid"):
        if str(g["step_source"].iloc[0]) != "dof_estimated":
            continue
        m = float(g["M"].iloc[0])
        n_working = float(g["n_eff"].iloc[0])
        marked_f = float(g["n_marked"].iloc[0])
        fwhm_frames = float(np.nanmedian(g["fwhm_frames"].to_numpy(float)))
        s = FP.m_extrapolation_sensitivity(m, n_working, marked_f, fwhm_frames)
        rows.append(dict(sid=sid, M=m, **s,
                         low_confidence=bool(g["step_low_confidence"].iloc[0])))
    return pd.DataFrame(rows).sort_values("M")


# --------------------------------------------------------------------------- #
def _summary(df, col):
    a = df[col].to_numpy(float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return float("nan"), float("nan"), float("nan"), 0
    return (float(np.median(a)), float(np.percentile(a, 25)),
            float(np.percentile(a, 75)), int(a.size))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["apply", "validate", "all"], default="all",
                    nargs="?")
    ap.add_argument("--n-grid", type=int, default=5)
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(exist_ok=True)

    if args.mode in ("apply", "all"):
        print("=== APPLY: 2026-01-29 cached cohort -> physical mm ===")
        psffoc = load_psffoc(POC1_OUT)
        phys = apply_cohort(psffoc)
        out_csv = OUT_DIR / "per_patch_physical_2026-01-29.csv"
        phys.to_csv(out_csv, index=False)
        print(f"\nWrote {len(phys)} per-patch rows -> {out_csv}")
        # flag tallies
        qc = phys["fwhm_quality"].value_counts().to_dict()
        cc = phys["coverage_flag"].value_counts().to_dict()
        print(f"  fwhm_quality: {qc}")
        print(f"  coverage_flag: {cc}")
        print(f"  imputed patches: {int(phys['fwhm_imputed'].sum())}")
        print(f"  low-confidence (M>1 extrapolation) patches: "
              f"{int(phys['step_low_confidence'].sum())} "
              f"in sweeps {sorted(phys[phys.step_low_confidence].sid.unique())}")
        ext = extrapolation_table(phys)
        ext.to_csv(OUT_DIR / "m_extrapolation_sensitivity.csv", index=False)
        print("\n  M-exponent (1 vs 2) sensitivity (DoF-estimated sweeps):")
        for r in ext.itertuples():
            print(f"    {r.sid:32s} M={r.M:5.3f} step(exp2)={r.step_mm_exp2:.5f} "
                  f"step(exp1)={r.step_mm_exp1:.5f} ratio(=M)={r.ratio_exp1_over_exp2:.3f} "
                  f"frac_shift={r.frac_shift:.2f}{'  LOW-CONF' if r.low_confidence else ''}")

    if args.mode in ("validate", "all"):
        print("\n=== VALIDATE: 2026-05 documented sweeps ===")
        ppatch, psweep = validate(n_grid=args.n_grid, workers=args.workers)
        ppatch.to_csv(OUT_DIR / "validate_per_patch_2026-05.csv", index=False)
        psweep.to_csv(OUT_DIR / "validate_per_sweep_2026-05.csv", index=False)
        print("\n  --- Conversion validation (DoF-estimated vs documented step) ---")
        for label, col in [("mu_mm   estimated/documented", "mu_mm_disc"),
                           ("fwhm_mm estimated/documented", "fwhm_mm_disc")]:
            med, q1, q3, n = _summary(ppatch, col)
            print(f"    {label}: median={med:.3f} IQR=[{q1:.3f},{q3:.3f}] n={n} patches")
        med, q1, q3, n = _summary(psweep, "step_ratio_dof_over_doc")
        print(f"    per-sweep step ratio (dof/doc): median={med:.3f} "
              f"IQR=[{q1:.3f},{q3:.3f}] n={n} sweeps")
        print("\n  --- Internal consistency (validation #2) ---")
        med_se, q1, q3, n = _summary(psweep, "median_mu_stderr_frames")
        print(f"    median mu fit stderr: {med_se:.3f} frames "
              f"(IQR=[{q1:.3f},{q3:.3f}], n={n} sweeps)")
        # field spread (mm) vs mu stderr (mm): is the across-field mu spread resolvable?
        res = psweep.dropna(subset=["field_mu_mm_spread", "median_mu_stderr_mm"]).copy()
        res["spread_over_noise"] = res["field_mu_mm_spread"] / res["median_mu_stderr_mm"]
        med_r, q1r, q3r, nr = _summary(res, "spread_over_noise")
        print(f"    across-field mu_mm spread / mu fit-noise(mm): median={med_r:.2f} "
              f"IQR=[{q1r:.2f},{q3r:.2f}] n={nr} sweeps (>1 == resolvable)")
        print(f"\nWrote validation tables -> {OUT_DIR}")

    print(f"\nOutputs in {OUT_DIR}")


if __name__ == "__main__":
    main()
