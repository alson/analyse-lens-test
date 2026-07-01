"""POC 2 — depth-of-field-based rail step-size estimator.

A physics-first alternative to the scribe-blur calibrator
(``tile_sharpness.rail_calibration.calibrate_sweep``) for back-deriving the
StackShot rail step (mm per frame) on the older "manual-tier" sweeps that record
NO rail position — only an ordered sequence of JPGs.

Idea
----
As the OBJECT moves axially by ``δz`` from best focus, the geometric defocus blur
diameter in object space grows as ``b(δz) ≈ δz · M / N_eff`` (``N_eff`` the
effective/working f-number, ``M`` the magnification). The through-focus sharpness
response (Laplacian variance vs frame) therefore has a characteristic OBJECT-space
width set by an acceptable-blur tolerance ``c``; object-space DoF scales as
``N_eff / M`` (with image-space focus depth ``∝ N_eff·(1+M)``). So:

    measured FWHM_frames × step_mm  =  FWHM in object mm  ≈  k · predictor(N_eff, M)

On the 2026-05 "newer-rig" sweeps the step is DOCUMENTED (``rail_position_mm`` in
``shots.csv`` and ``sample_plan.rail_step_mm`` in ``metadata.json``), so we fit the
constant ``k`` and validate. On the pre-2026-05 sweeps we invert:

    step_mm = k · predictor(N_eff, M) / FWHM_frames

We sanity-check WHICH DoF scaling actually fits (``N_eff/M`` vs ``N_eff·(1+M)/M²``
vs ``N/M`` vs ``N_eff``) by comparing the linear (through-origin) R² of each
predictor against measured object-space FWHM, then use the winner.

Self-contained
--------------
The through-focus curve is a plain Laplacian-variance over a fixed central ROI of
each JPG (one frame per rail position). The Gaussian-of-defocus FWHM fit is
imported READ-ONLY from ``cross_m_relative_mtf.gaussian_defocus_fwhm`` when
available; an inlined equivalent (``_fit_gaussian_fwhm``) is used as a fallback so
the unit tests do not depend on that module. ``optics.object_dof_predictor`` holds
the physics.

CLI
---
    # 2026-05 calibrate + leave-one-out validation (run on nufan, NFS data):
    uv run python scripts/poc_dof_step_size.py validate
    # apply to 2026-01-29 + compare to scribe-blur v1/v2:
    uv run python scripts/poc_dof_step_size.py apply
    # both, writing the report:
    uv run python scripts/poc_dof_step_size.py all
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tile_sharpness.optics import DOF_PREDICTOR_FORMS, object_dof_predictor

try:  # read-only import of the shared Gaussian-FWHM fitter
    from tile_sharpness.cross_m_relative_mtf import gaussian_defocus_fwhm as _shared_fwhm
except Exception:  # pragma: no cover - fallback path
    _shared_fwhm = None


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
# Two newer-rig session trees, with DIFFERENT F-dir semantics (verified via
# .bellows-rename-applied.csv presence + EXIF spot-checks, 2026-06):
#
#   * 2026-05-12: NOT bellows-renamed. F-dir name == MARKED (camera-reported /
#     ring-set) f-number, matching shots.csv ``aperture``. The clean source for
#     extension/tube/diopter CONFIGS, because the marked f-number keys the
#     effective_apertures.csv (by reported_f) to get the empirical N_working.
#   * 2026-05-13: bellows-RENAMED. F-dir names for tube configs are
#     SNAPPED-EFFECTIVE labels (e.g. "100-400 + 35mm" dir ``f_11`` has
#     reported_f=8.0, effective_f_exact=10.68). It carries the canonical
#     effective_apertures.csv. Used here only for the BARE lenses (Sigma 150,
#     70-180 AF-D, 55mm AI-S, bare Z 24-120 / 100-400), whose F-dir == marked
#     (they were not bellows-shifted: bare bellows_multiplier ≈ 1).
#
# N_working (true working f-number at the focal plane) is resolved per config:
#   - In effective_apertures.csv (by slug, reported_f): use effective_f_exact
#     DIRECTLY — it is the empirical working f, already folding in BOTH the
#     magnification and any external-tube bellows. NEVER re-apply (1+M/p) on top.
#   - Bare lens NOT in the CSV: the folder f-number is ALREADY effective — the
#     tree was curated so folder = f_eff, folding in the lens's own helicoid
#     extension (and, for the manual macros, the external tube used to reach the
#     stated magnification). So N_working = folder f DIRECTLY. We never multiply
#     by (1+M/p). Verified at 1:1: 55mm AI-S marked max f/2.8 -> widest native
#     folder F5.6 = 2.8×2; Auto 55mm f/3.5 -> F7 = 3.5×2; Sigma 150 f/2.8 ->
#     f/5.6 = 2.8×2.
#
# GUARDRAIL: for each lens we check the widest native folder f-number against
# marked_max × (1+M). They should match (folder is effective). A lens whose
# widest folder ≈ marked_max instead would be a MARKED-labelled folder needing
# correction — per the evidence there are none, but we flag any that appear.
_MARKED_MAX_OVERRIDES: dict[str, float] = {
    # Lens nominal marked maximum aperture (widest), from the lens model, where
    # it cannot be parsed unambiguously from the slug. Zooms list the long-end max.
    "Nikon Micro-Nikkor 55mm f_2.8 AIS": 2.8,
    "Nikon Micro-Nikkor Auto 55mm f_3.5": 3.5,
}


def _marked_max_aperture(slug: str) -> float | None:
    """Parse the lens's nominal MARKED maximum (widest) f-number from its name.

    Picks the smallest f-number token (<= 40, to exclude focal lengths in mm).
    Returns None if none is parseable. Used only for the folder=effective
    guardrail, not for any N_working computation."""
    for prefix, val in _MARKED_MAX_OVERRIDES.items():
        if slug.startswith(prefix):
            return val
    vals: list[float] = []
    for a, b in re.findall(r"[Ff]_?(\d+(?:[._]\d+)?)(?:-(\d+(?:[._]\d+)?))?", slug):
        for t in (a, b):
            if t:
                try:
                    v = float(t.replace("_", "."))
                except ValueError:
                    continue
                if v <= 40:
                    vals.append(v)
    return min(vals) if vals else None
NEWER_TREES = [
    (Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-12"), "marked"),
    (Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13"), "effective"),
]
NEWER_ROOTS = [t for t, _ in NEWER_TREES]
EFF_AP_CSV = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/effective_apertures.csv"
)
OLDER_ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
OUT_DIR = Path(__file__).resolve().parent.parent / "out_poc_dof_step"

# Tokens that mark a config as NOT a truly-bare prime/macro (extension tube,
# teleconverter, close-up diopter). Used to keep the calibration set clean:
# truly-bare = none of these tokens AND not present in effective_apertures.csv
# with a bellows_multiplier != 1.
_ACCESSORY_TOKENS = (
    "extension", "tube", "+", " tc", "tc-", "teleconverter", "raynox",
    "mcon", "500d", "5t", "6t", "diopter", "close-up", "closeup", "kenko",
)


def _looks_bare(slug: str) -> bool:
    """True only for a truly-bare prime/macro (no extension/TC/diopter token)."""
    s = slug.lower()
    return not any(tok in s for tok in _ACCESSORY_TOKENS)


@dataclass(frozen=True)
class EffApertureCSV:
    """``(slug, reported_f_rounded) -> (effective_f_exact, bellows_multiplier)``.

    Built from the bellows-calibration ``effective_apertures.csv`` (the
    2026-05-13 tree root). ``effective_f_exact`` already IS the empirical working
    f-number at the focal plane — it folds in BOTH the magnification and the
    external-tube bellows — so for configs present here the DoF model uses it
    DIRECTLY as ``N_working`` (no extra ``(1+M/p)`` factor). Also exposes the
    per-config ``bellows_multiplier`` (constant across apertures) so a marked
    f-number with no exact row can still be corrected as marked × multiplier.
    """
    exact: dict[tuple[str, float], float]
    mult: dict[str, float]

    @classmethod
    def load(cls, path: Path) -> "EffApertureCSV":
        import csv
        exact: dict[tuple[str, float], float] = {}
        mult: dict[str, float] = {}
        if not path.exists():
            return cls(exact={}, mult={})
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                slug = r["slug"]
                try:
                    rep = round(float(r["reported_f"]), 2)
                    eff = float(r["effective_f_exact"])
                    m = float(r["bellows_multiplier"])
                except (ValueError, TypeError, KeyError):
                    continue
                exact[(slug, rep)] = eff
                mult[slug] = m
        return cls(exact=exact, mult=mult)

    def n_working(self, slug: str, folder_f: float, m_total: float,
                  *, pupil_mag: float = 1.0) -> tuple[float, str]:
        """Resolve the working f-number for one (slug, FOLDER f-number, M).

        The directory/folder f-number in THIS dataset is ALREADY the effective
        working f-number for every lens — the tree was curated so folder = f_eff,
        folding in the lens's own helicoid extension and any external tube/diopter
        (verified at 1:1: e.g. 55mm AI-S marked max f/2.8 -> widest native folder
        F5.6 = 2.8×2; Sigma 150 likewise). So we NEVER multiply by (1+M/p).

        Priority:
          1. exact (slug, reported_f) row in the bellows CSV -> effective_f_exact
             [source "csv_exact"] — the un-snapped empirical working f (preferred
             for 100-400 / 24-120 / MC 105 / Viltrox + their tube/diopter combos).
          2. slug bellows_multiplier in the CSV -> folder × mult [source "csv_mult"].
          3. else: the folder f-number, used DIRECTLY [source "folder_direct"].
        """
        key = (slug, round(folder_f, 2))
        if key in self.exact:
            return self.exact[key], "csv_exact"
        if slug in self.mult:
            return folder_f * self.mult[slug], "csv_mult"
        return folder_f, "folder_direct"

# Central ROI fraction (fraction of width/height kept, centred) for the
# Laplacian-variance curve. The wafer target fills the frame; a central crop
# avoids vignetting / frame-edge artefacts while keeping plenty of structure.
ROI_FRAC = 0.4
# Minimum distinct rail positions (frames) to attempt a peak fit.
MIN_FRAMES = 9
# Drop FWHM fits wider than this many frames (degenerate / no real peak).
MAX_VALID_FWHM_FRAMES = 60.0


# --------------------------------------------------------------------------- #
# Through-focus sharpness curve + FWHM fit
# --------------------------------------------------------------------------- #
def _laplacian_variance(img_gray: np.ndarray) -> float:
    """Variance of the 4-neighbour Laplacian — a standard focus measure."""
    f = img_gray.astype(np.float64)
    lap = (
        -4.0 * f
        + np.roll(f, 1, 0) + np.roll(f, -1, 0)
        + np.roll(f, 1, 1) + np.roll(f, -1, 1)
    )
    # Trim the 1-px border that the wrap-around roll corrupts.
    lap = lap[1:-1, 1:-1]
    return float(lap.var())


def lapvar_curve(jpg_paths: list[Path], *, roi_frac: float = ROI_FRAC) -> np.ndarray:
    """Per-frame Laplacian variance over a fixed central ROI, in path order.

    Reads each JPG as greyscale (luminance), crops the centred ``roi_frac`` box,
    and returns the focus-measure curve. Frames that fail to decode contribute a
    NaN (later dropped). Uses OpenCV if available, else Pillow.
    """
    try:
        import cv2  # noqa: F401
        _have_cv2 = True
    except Exception:  # pragma: no cover
        _have_cv2 = False
    vals: list[float] = []
    for p in jpg_paths:
        try:
            if _have_cv2:
                import cv2
                # Decode at 1/4 resolution: the through-focus lapvar *shape*
                # (hence FWHM-in-frames) is preserved while decode is ~16x cheaper,
                # which matters for full-res (~30 MB) JPGs read over NFS.
                im = cv2.imread(str(p), cv2.IMREAD_REDUCED_GRAYSCALE_4)
                if im is None:
                    raise OSError("decode failed")
                g = im
            else:  # pragma: no cover
                from PIL import Image
                img = Image.open(p).convert("L")
                img.draft("L", (img.width // 4, img.height // 4))
                g = np.asarray(img)
            h, w = g.shape[:2]
            ch, cw = int(h * roi_frac), int(w * roi_frac)
            y0, x0 = (h - ch) // 2, (w - cw) // 2
            roi = g[y0:y0 + ch, x0:x0 + cw]
            vals.append(_laplacian_variance(roi))
        except Exception:
            vals.append(float("nan"))
    return np.asarray(vals, dtype=float)


def _fit_gaussian_fwhm(seqs: np.ndarray, vals: np.ndarray) -> float:
    """Inlined Gaussian-of-defocus FWHM (frames). Mirror of the shared fitter.

    Subtracts a 10th-percentile baseline, selects the >=25%-of-peak region, and
    fits ``log(y)`` to a weighted quadratic in ``z`` (a Gaussian). Returns
    ``2.3548 * sigma`` in frames, or NaN if there is no clean downward parabola.
    Kept so the unit tests need not import the cross_m module.
    """
    seqs = np.asarray(seqs, float)
    vals = np.asarray(vals, float)
    if len(vals) < 7:
        return float("nan")
    base = np.percentile(vals, 10)
    v0 = np.clip(vals - base, 0, None)
    pk = int(np.argmax(v0))
    peak = v0[pk]
    if peak <= 0:
        return float("nan")
    sel = v0 >= 0.25 * peak
    z = seqs[sel]
    y = v0[sel]
    if len(z) < 5 or np.ptp(z) < 2:
        return float("nan")
    w = y / y.max()
    A = np.column_stack([np.ones_like(z), z, z * z])
    coef, *_ = np.linalg.lstsq(A * w[:, None], np.log(np.clip(y, 1e-9, None)) * w, rcond=None)
    _, _c1, c2 = coef
    if c2 >= 0:
        return float("nan")
    sigma_z = float(np.sqrt(-1.0 / (2 * c2)))
    return 2.3548 * sigma_z


def fwhm_frames(vals: np.ndarray) -> float:
    """FWHM (frames) of the through-focus curve. Uses the shared fitter if present."""
    finite = np.isfinite(vals)
    if finite.sum() < 7:
        return float("nan")
    seqs = np.arange(len(vals), dtype=float)[finite]
    v = vals[finite]
    if _shared_fwhm is not None:
        _s, fw, _mu = _shared_fwhm(seqs, v)
        return float(fw)
    return _fit_gaussian_fwhm(seqs, v)


# --------------------------------------------------------------------------- #
# Newer-rig (2026-05) discovery + ground truth
# --------------------------------------------------------------------------- #
_BASE_STEP_RE = re.compile(r"^step_(\d+)\.jpg$", re.IGNORECASE)
# F-dirs come in two shapes: ``f_5_6`` / ``f_8`` (CPU lenses) and bare-number
# ``6_3`` / ``8`` (manual AI-S lenses, e.g. the 55mm). Underscore = decimal point.
_AP_DIR_RE = re.compile(r"^(?:f_)?(\d+)(?:_(\d+))?$", re.IGNORECASE)


def _aperture_from_f_dir(name: str) -> float | None:
    m = _AP_DIR_RE.match(name)
    if not m:
        return None
    whole, frac = m.group(1), m.group(2)
    return float(f"{whole}.{frac}") if frac else float(whole)


@dataclass
class NewerSweep:
    session: str
    slug: str
    is_bare: bool
    m: float
    marked_f: float              # camera-reported (MARKED) f-number from the F-dir
    n_working: float             # working f-number at the focal plane (bellows-correct)
    n_source: str                # how n_working was resolved
    f_dir: str
    true_step_mm: float          # documented step (median diff of distinct rail pos)
    plan_step_mm: float | None   # sample_plan.rail_step_mm cross-check
    base_jpgs: list[Path]        # one per distinct rail position, in rail order

    @property
    def aperture_f(self) -> float:  # back-compat alias for the marked f-number
        return self.marked_f


def discover_newer_sweeps(eff_csv: "EffApertureCSV | None" = None) -> list[NewerSweep]:
    if eff_csv is None:
        eff_csv = EffApertureCSV.load(EFF_AP_CSV)
    out: list[NewerSweep] = []
    for root, fdir_kind in NEWER_TREES:
        if not root.is_dir():
            continue
        for sess_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            mp = sess_dir / "metadata.json"
            sp = sess_dir / "shots.csv"
            if not (mp.exists() and sp.exists()):
                continue
            try:
                meta = json.loads(mp.read_text())
            except Exception:
                continue
            cfg = meta.get("lens_config", {}) or {}
            slug = cfg.get("slug") or sess_dir.name
            m = cfg.get("magnification")
            if m is None or not (isinstance(m, (int, float)) and m > 0):
                continue
            plan = (cfg.get("sample_plan") or {})
            plan_step = plan.get("rail_step_mm")
            is_bare = _looks_bare(slug)
            # F-dir semantics per tree: in the bellows-RENAMED ("effective")
            # tree the tube-config F-dirs are effective-snapped and cannot be
            # keyed back to a marked f-number, so we take ONLY bare lenses from
            # it (their F-dir == marked). Tube/diopter configs come from the
            # unrenamed ("marked") tree, where the F-dir keys the CSV by
            # reported_f. This split avoids both double-counting and the
            # snapped-label ambiguity.
            if fdir_kind == "effective" and not is_bare:
                continue
            # Parse shots.csv (sweep rows) for per-aperture rail positions.
            import csv
            with open(sp, newline="") as f:
                rows = [r for r in csv.DictReader(f) if r.get("phase") == "sweep"]
            # Group sweep rows by their parsed aperture float (handles both
            # "f/5.6" and bare "6.3" aperture strings in shots.csv).
            def _ap_str_to_f(s: str) -> float | None:
                s = s.strip().lower().removeprefix("f/")
                try:
                    return float(s)
                except ValueError:
                    return None
            by_ap: dict[float, list[dict]] = {}
            for r in rows:
                apv = _ap_str_to_f(str(r.get("aperture", "")))
                if apv is not None:
                    by_ap.setdefault(round(apv, 2), []).append(r)
            for f_dir in sorted(p for p in sess_dir.iterdir() if p.is_dir()):
                ap_f = _aperture_from_f_dir(f_dir.name)
                if ap_f is None:
                    continue
                # base files on disk (step_NNNN.jpg, no replica suffix)
                base = []
                for jpg in f_dir.glob("step_*.jpg"):
                    mm = _BASE_STEP_RE.match(jpg.name)
                    if mm:
                        base.append((int(mm.group(1)), jpg))
                base.sort()
                if len(base) < MIN_FRAMES:
                    continue
                # documented step: match shots.csv rows by parsed aperture float
                arows = by_ap.get(round(ap_f, 2), [])
                try:
                    pos = sorted({float(r["rail_position_mm"]) for r in arows})
                except Exception:
                    pos = []
                if len(pos) < 2:
                    continue
                diffs = np.diff(pos)
                true_step = float(np.median(diffs))
                if not (math.isfinite(true_step) and true_step > 0):
                    continue
                n_work, n_src = eff_csv.n_working(slug, ap_f, float(m))
                out.append(NewerSweep(
                    session=sess_dir.name, slug=slug, is_bare=is_bare, m=float(m),
                    marked_f=ap_f, n_working=n_work, n_source=n_src,
                    f_dir=f_dir.name, true_step_mm=true_step,
                    plan_step_mm=float(plan_step) if plan_step else None,
                    base_jpgs=[p for _, p in base],
                ))
    return out


# --------------------------------------------------------------------------- #
# Calibration + validation
# --------------------------------------------------------------------------- #
@dataclass
class FitResult:
    form: str
    k: float
    r2: float
    n: int


def fit_through_origin(predictor: np.ndarray, fwhm_mm: np.ndarray) -> tuple[float, float]:
    """Fit fwhm_mm = k * predictor (through origin). Returns (k, R²).

    R² is computed against the through-origin model (1 - SS_res/SS_tot, SS_tot
    about the mean of fwhm_mm) so it is comparable across predictor forms.
    """
    x = np.asarray(predictor, float)
    y = np.asarray(fwhm_mm, float)
    k = float((x @ y) / (x @ x))
    resid = y - k * x
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) @ (y - y.mean())))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return k, r2


def _sweep_fwhm_worker(sw: "NewerSweep") -> float:
    """Process-pool worker: compute the through-focus FWHM (frames) for one sweep."""
    return fwhm_frames(lapvar_curve(sw.base_jpgs))


_FWHM_CACHE = OUT_DIR / "newer_fwhm_cache.json"


def _fwhm_cache_key(sw: "NewerSweep") -> str:
    return f"{sw.session}||{sw.slug}||{sw.f_dir}||{len(sw.base_jpgs)}"


def build_measurement_table(sweeps: list[NewerSweep], *, log=print,
                            workers: int = 8, use_cache: bool = True) -> list[dict]:
    """Per-sweep: measured FWHM_frames, object-space FWHM_mm, predictors.

    The per-frame Laplacian-variance curve is the bottleneck (NFS reads of ~30 MB
    JPGs), so the per-sweep FWHM is computed across a process pool AND cached to
    JSON keyed by (session, slug, f_dir, n_frames). The FWHM depends only on the
    pixels, so re-runs that change only N_working resolution reuse the cache and
    are instant. Delete ``newer_fwhm_cache.json`` to force recomputation.
    """
    from concurrent.futures import ProcessPoolExecutor
    cache: dict[str, float] = {}
    if use_cache and _FWHM_CACHE.exists():
        try:
            cache = json.loads(_FWHM_CACHE.read_text())
        except Exception:
            cache = {}
    to_compute = [sw for sw in sweeps if _fwhm_cache_key(sw) not in cache]
    if to_compute:
        log(f"  computing FWHM for {len(to_compute)}/{len(sweeps)} sweeps "
            f"({len(sweeps) - len(to_compute)} cached)", flush=True)
        if workers > 1 and len(to_compute) > 1:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                new_fwhms = list(ex.map(_sweep_fwhm_worker, to_compute))
        else:
            new_fwhms = [_sweep_fwhm_worker(sw) for sw in to_compute]
        for sw, fw in zip(to_compute, new_fwhms):
            cache[_fwhm_cache_key(sw)] = fw
        if use_cache:
            OUT_DIR.mkdir(exist_ok=True)
            _FWHM_CACHE.write_text(json.dumps(cache))
    fwhms = [cache[_fwhm_cache_key(sw)] for sw in sweeps]
    rows: list[dict] = []
    for i, (sw, fw) in enumerate(zip(sweeps, fwhms), 1):
        log(f"[{i}/{len(sweeps)}] {sw.session} {sw.f_dir} "
            f"M={sw.m:.3f} N={sw.aperture_f} step={sw.true_step_mm:.5f} "
            f"frames={len(sw.base_jpgs)} FWHM_frames={fw:.2f}", flush=True)
        if not (math.isfinite(fw) and 2.0 <= fw <= MAX_VALID_FWHM_FRAMES):
            continue
        row = {
            "session": sw.session, "slug": sw.slug, "is_bare": sw.is_bare,
            "f_dir": sw.f_dir, "marked_f": sw.marked_f, "m": sw.m,
            "n_working": sw.n_working, "n_source": sw.n_source,
            "true_step_mm": sw.true_step_mm,
            "plan_step_mm": sw.plan_step_mm, "n_frames": len(sw.base_jpgs),
            "fwhm_frames": fw, "fwhm_obj_mm": fw * sw.true_step_mm,
        }
        # All predictor forms use the bellows-correct working f-number ONCE
        # (n_working), so no (1+M/p) is re-applied on top of an already-effective
        # value. The marked f-number feeds only the n_over_m control.
        for form in DOF_PREDICTOR_FORMS:
            row[f"pred_{form}"] = object_dof_predictor(
                sw.marked_f, sw.m, form=form, n_working=sw.n_working)
        rows.append(row)
    return rows


def compare_predictors(rows: list[dict]) -> list[FitResult]:
    """Fit each candidate predictor form; return sorted by R² desc."""
    fwhm_mm = np.array([r["fwhm_obj_mm"] for r in rows])
    results = []
    for form in DOF_PREDICTOR_FORMS:
        pred = np.array([r[f"pred_{form}"] for r in rows])
        k, r2 = fit_through_origin(pred, fwhm_mm)
        results.append(FitResult(form=form, k=k, r2=r2, n=len(rows)))
    return sorted(results, key=lambda r: (-(r.r2 if math.isfinite(r.r2) else -1)))


def leave_one_out(rows: list[dict], form: str) -> list[dict]:
    """LOO: fit k on all-but-one, predict that one's step, compare to truth."""
    fwhm_mm = np.array([r["fwhm_obj_mm"] for r in rows])
    pred = np.array([r[f"pred_{form}"] for r in rows])
    out = []
    n = len(rows)
    for i in range(n):
        mask = np.arange(n) != i
        k, _ = fit_through_origin(pred[mask], fwhm_mm[mask])
        # invert: step = k * predictor / FWHM_frames
        est_step = k * pred[i] / rows[i]["fwhm_frames"]
        out.append({
            **{key: rows[i][key] for key in
               ("session", "f_dir", "marked_f", "n_working", "m", "is_bare",
                "true_step_mm", "fwhm_frames")},
            "aperture_f": rows[i]["marked_f"],  # for grouping by aperture
            "k_loo": k,
            "est_step_mm": est_step,
            "ratio": est_step / rows[i]["true_step_mm"],
        })
    return out


# --------------------------------------------------------------------------- #
# Scribe-blur calibrator comparison (run phase1 on the same newer sweeps)
# --------------------------------------------------------------------------- #
def scribe_blur_ratios(sweeps: list[NewerSweep], *, log=print,
                       max_frames: int = 41) -> list[dict]:
    """Run the existing scribe-blur calibrator on the same newer-rig sweeps.

    Builds a Sweep of base-replica Shots per (session, aperture), runs phase1
    (with M injected from metadata), then calibrate_sweep, and reports
    derived/documented step ratio. Returns [] if phase1 can't be run.

    ``max_frames`` caps each sweep to a CONTIGUOUS centred window of that many
    frames before running phase1 (wafer detection on full-res JPGs is expensive
    over NFS). A contiguous window preserves the consecutive-frame spacing — so
    the documented per-frame step is unchanged — and keeps the in-focus peak
    (focus sits mid-sweep), which is all the blur-vs-defocus calibrator needs.
    """
    try:
        import pandas as pd
        import tile_sharpness.phase1 as phase1_mod
        from tile_sharpness.m_lookup import MagLookup, MLookup
        from tile_sharpness.rail_calibration import calibrate_sweep
        from tile_sharpness.sweeps import Shot, Sweep
    except Exception as e:  # pragma: no cover
        log(f"scribe-blur comparison unavailable: {e}")
        return []

    label_to_m: dict[str, float] = {}
    sweep_objs: list[tuple[Sweep, NewerSweep]] = []
    for sw in sweeps:
        jpgs = sw.base_jpgs
        if max_frames and len(jpgs) > max_frames:
            mid = len(jpgs) // 2
            half = max_frames // 2
            jpgs = jpgs[max(0, mid - half): max(0, mid - half) + max_frames]
        shots = [Shot(path=p, rail_step=k, rail_position_mm=None)
                 for k, p in enumerate(jpgs)]
        label = f"{sw.session}__{sw.slug}__{sw.f_dir}"
        sweep = Sweep(label=label, family="poc-dof-newer", lens=sw.slug,
                      aperture=sw.f_dir, shots=shots)
        label_to_m[label] = sw.m
        sweep_objs.append((sweep, sw))

    # Run smaller sweeps first so a slow/killed phase1 (wafer detection on a
    # manual-lens framing can stall) still yields the most comparisons; the
    # incremental CSV write preserves whatever completed.
    sweep_objs.sort(key=lambda t: len(t[0].shots))

    original_resolve = phase1_mod.resolve

    def patched_resolve(sweep, mlookup):
        m = label_to_m.get(sweep.label)
        if m is not None and m > 0:
            return MagLookup(measured=m, source="metadata_json", confidence="planned")
        return original_resolve(sweep, mlookup)

    phase1_mod.resolve = patched_resolve
    mlookup = MLookup()
    all_rows: list[dict] = []
    incremental_csv = OUT_DIR / "newer_scribe.csv"
    try:
        for i, (sweep, sw) in enumerate(sweep_objs, 1):
            log(f"  scribe[{i}/{len(sweep_objs)}] {sweep.label}", flush=True)
            try:
                rows, _peaks = phase1_mod.analyse_sweep_phase1(sweep, mlookup, workers=16)
            except Exception as e:
                log(f"    phase1 failed: {e}")
                continue
            df = pd.DataFrame(rows)
            if df.empty:
                continue
            # Give the scribe calibrator the SAME bellows-correct working
            # f-number the DoF estimator uses, so the comparison is apples-to-
            # apples (the calibrator's blur formula expects total-effective N).
            res = calibrate_sweep(df, effective_aperture=sw.n_working)
            if math.isfinite(res.rail_step_mm):
                all_rows.append({
                    "session": sw.session, "f_dir": sw.f_dir,
                    "aperture_f": sw.aperture_f, "m": sw.m, "is_bare": sw.is_bare,
                    "true_step_mm": sw.true_step_mm,
                    "scribe_step_mm": res.rail_step_mm,
                    "scribe_ratio": res.rail_step_mm / sw.true_step_mm,
                    "verdict": res.verdict, "n_estimates": res.n_estimates,
                })
                # write incrementally so a slow/killed phase1 still leaves results
                try:
                    pd.DataFrame(all_rows).to_csv(incremental_csv, index=False)
                except Exception:
                    pass
    finally:
        phase1_mod.resolve = original_resolve
    return all_rows


# --------------------------------------------------------------------------- #
# Older-rig (2026-01-29) application
# --------------------------------------------------------------------------- #
_OLDER_MAG_RE = re.compile(r"^(\d+)_([\d.]+)")  # 1_1, 1_2.60, 2_1
_OLDER_F_RE = re.compile(r"^F([\d.]+)$", re.IGNORECASE)
# bare lenses: no '+', no TC token
_OLDER_BARE_LENSES = [
    "Nikon AF Micro-Nikkor 200mm f_4D IF-ED",
    "Sigma APO Macro 150mm F2.8 EX DG OS HSM",
    "Sigma Macro 105mm F2.8 EX DG OS HSM",
    "NIKKOR Z MC 105mm f_2.8 VR S",
    "Nikon AF Micro-Nikkor 60mm f_2.8D",
    "Nikon Micro-Nikkor 55mm f_2.8 AIS 287318",
]


def _older_m_from_dir(name: str) -> float | None:
    m = _OLDER_MAG_RE.match(name)
    if not m:
        return None
    a, b = float(m.group(1)), float(m.group(2))
    if b == 0:
        return None
    return a / b  # 1_1 -> 1.0, 1_2.60 -> 0.385, 2_1 -> 2.0


@dataclass
class OlderSweep:
    lens: str
    mag_dir: str
    m: float
    aperture_f: float
    f_dir: str
    jpgs: list[Path]
    sweep_id: str   # for matching scribe-blur lookups


def _seq_num(p: Path) -> int:
    head = p.name.split("|", 1)[0]
    try:
        return int(head)
    except ValueError:
        return 0


def discover_older_sweeps(lenses: list[str]) -> list[OlderSweep]:
    out: list[OlderSweep] = []
    for lens in lenses:
        ldir = OLDER_ROOT / lens
        if not ldir.is_dir():
            continue
        for mag_dir in sorted(p for p in ldir.iterdir() if p.is_dir()):
            if mag_dir.name.endswith("-resized"):
                continue
            m = _older_m_from_dir(mag_dir.name)
            if m is None:
                continue
            for f_dir in sorted(p for p in mag_dir.iterdir() if p.is_dir()):
                fm = _OLDER_F_RE.match(f_dir.name)
                if not fm:
                    continue
                ap_f = float(fm.group(1))
                jpgs = sorted(
                    (p for p in f_dir.glob("*.jpg") if "|" in p.name),
                    key=_seq_num,
                )
                if len(jpgs) < MIN_FRAMES:
                    continue
                sweep_id = f"{lens}__{mag_dir.name}__{f_dir.name}"
                out.append(OlderSweep(
                    lens=lens, mag_dir=mag_dir.name, m=m, aperture_f=ap_f,
                    f_dir=f_dir.name, jpgs=jpgs, sweep_id=sweep_id,
                ))
    return out


_OLDER_EFF_CSV = OLDER_ROOT / "effective_apertures.csv"


def _older_fwhm_worker(sw: "OlderSweep") -> float:
    return fwhm_frames(lapvar_curve(sw.jpgs))


def apply_older(sweeps: list[OlderSweep], k: float, form: str, *, log=print,
                workers: int = 8) -> list[dict]:
    # 2026-01-29 F-dirs are MARKED (the bare-prime tree was not bellows-renamed;
    # README: "no on-disk renames"). The bare AF-D / AI-S macros here are not in
    # the CSV, so N_working = marked × (1+M/p); any covered config uses csv_exact.
    eff_csv = EffApertureCSV.load(_OLDER_EFF_CSV)
    from concurrent.futures import ProcessPoolExecutor
    if workers > 1 and len(sweeps) > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            fwhms = list(ex.map(_older_fwhm_worker, sweeps))
    else:
        fwhms = [_older_fwhm_worker(sw) for sw in sweeps]
    rows: list[dict] = []
    for i, (sw, fw) in enumerate(zip(sweeps, fwhms), 1):
        n_work, n_src = eff_csv.n_working(sw.lens, sw.aperture_f, sw.m)
        log(f"[older {i}/{len(sweeps)}] {sw.sweep_id} M={sw.m:.3f} marked={sw.aperture_f} "
            f"Nwork={n_work:.2f} frames={len(sw.jpgs)} FWHM_frames={fw:.2f}", flush=True)
        base = {"sweep_id": sw.sweep_id, "lens": sw.lens, "mag_dir": sw.mag_dir,
                "m": sw.m, "marked_f": sw.aperture_f, "n_working": n_work,
                "n_source": n_src, "n_frames": len(sw.jpgs), "fwhm_frames": fw}
        if not (math.isfinite(fw) and 2.0 <= fw <= MAX_VALID_FWHM_FRAMES):
            rows.append({**base, "dof_step_mm": float("nan")})
            continue
        pred = object_dof_predictor(sw.aperture_f, sw.m, form=form, n_working=n_work)
        rows.append({**base, "predictor": pred, "dof_step_mm": k * pred / fw})
    return rows


# --------------------------------------------------------------------------- #
# Reporting helpers
# --------------------------------------------------------------------------- #
def _iqr(a: np.ndarray) -> tuple[float, float, float]:
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return (float("nan"),) * 3
    return float(np.median(a)), float(np.percentile(a, 25)), float(np.percentile(a, 75))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["validate", "apply", "all"], default="all", nargs="?")
    ap.add_argument("--all-configs", action="store_true",
                    help="calibrate on ALL newer-rig configs (bare + tube/diopter), "
                         "not just the clean truly-bare set (the default).")
    ap.add_argument("--scribe", action="store_true",
                    help="also run the scribe-blur calibrator for comparison (slow; "
                         "needs phase1 wafer detection)")
    args = ap.parse_args()
    OUT_DIR.mkdir(exist_ok=True)

    import pandas as pd

    rows = None
    fits = None
    best = None
    if args.mode in ("validate", "all"):
        all_sweeps = discover_newer_sweeps()
        n_bare = sum(1 for s in all_sweeps if s.is_bare)
        print(f"Discovered {len(all_sweeps)} newer-rig sweeps (>= {MIN_FRAMES} frames); "
              f"{n_bare} truly-bare, {len(all_sweeps) - n_bare} accessory configs")
        from collections import Counter
        print(f"  N_working source breakdown: "
              f"{dict(Counter(s.n_source for s in all_sweeps))}")
        sweeps = all_sweeps if args.all_configs else [s for s in all_sweeps if s.is_bare]
        print(f"Calibration set: {len(sweeps)} sweeps "
              f"({'all configs' if args.all_configs else 'clean bare only'})")
        # Per-lens N_working classification + folder=effective guardrail.
        print("  per-lens N_working + guardrail (widest folder vs marked_max×(1+M)):")
        print(f"    {'lens':<44} {'M':>5} {'mkMax':>5} {'wFold':>5} "
              f"{'mk*(1+M)':>8} {'guard':>9}  N_source")
        seen_lens = {}
        for s in sweeps:
            seen_lens.setdefault(s.slug, s)
        for slug, s in sorted(seen_lens.items()):
            wfold = min(x.marked_f for x in sweeps if x.slug == slug)
            mk = _marked_max_aperture(slug)
            if mk is not None:
                eff = mk * (1.0 + s.m)
                # folder==effective if wfold closer to mk*(1+M) than to mk
                guard = "EFF-ok" if abs(wfold - eff) <= abs(wfold - mk) else "FLAG:marked?"
                mk_s, eff_s = f"{mk:.2f}", f"{eff:.2f}"
            else:
                guard, mk_s, eff_s = "n/a", "?", "?"
            print(f"    {slug[:44]:<44} {s.m:>5.2f} {mk_s:>5} {wfold:>5} "
                  f"{eff_s:>8} {guard:>9}  {s.n_source}")

        # FWHM nan-rate diagnostic on the calibration set.
        all_rows_dbg = build_measurement_table(sweeps)
        rows = all_rows_dbg
        n_attempt = len(sweeps)
        n_usable = len(rows)
        print(f"\nFWHM fit: {n_usable}/{n_attempt} sweeps usable "
              f"({100*(n_attempt-n_usable)/max(n_attempt,1):.1f}% dropped as nan / "
              f"out-of-range [2,{MAX_VALID_FWHM_FRAMES:.0f}] frames)")
        pd.DataFrame(rows).to_csv(OUT_DIR / "newer_measurements.csv", index=False)
        if not rows:
            print("No usable sweeps — aborting validation.")
            return

        fits = compare_predictors(rows)
        print("\n=== Predictor R² comparison (fwhm_obj_mm = k * predictor) ===")
        for fr in fits:
            print(f"  {fr.form:20s}  k={fr.k:10.5f}  R²={fr.r2:.4f}  n={fr.n}")
        best = fits[0]
        print(f"\nBest predictor: {best.form}  k={best.k:.5f}  R²={best.r2:.4f}")

        loo = leave_one_out(rows, best.form)
        pd.DataFrame(loo).to_csv(OUT_DIR / "newer_loo.csv", index=False)
        ratios = np.array([r["ratio"] for r in loo])
        med, q1, q3 = _iqr(ratios)
        print(f"\n=== LOO validation (predicted/documented step) — {best.form} ===")
        print(f"  overall: median={med:.3f}  IQR=[{q1:.3f}, {q3:.3f}]  n={len(ratios)}")
        # by aperture
        print("  by aperture:")
        ldf = pd.DataFrame(loo)
        for apf, g in ldf.groupby("aperture_f"):
            m_, q1_, q3_ = _iqr(g["ratio"].to_numpy())
            print(f"    f/{apf:<5}: median={m_:.3f}  IQR=[{q1_:.3f},{q3_:.3f}]  n={len(g)}")
        print("  by M bucket:")
        ldf["m_bucket"] = pd.cut(ldf["m"], [0, 0.6, 1.05, 1.6, 10],
                                 labels=["<0.6", "0.6-1.05", "1.05-1.6", ">1.6"])
        for mb, g in ldf.groupby("m_bucket", observed=True):
            m_, q1_, q3_ = _iqr(g["ratio"].to_numpy())
            print(f"    M {str(mb):<9}: median={m_:.3f}  IQR=[{q1_:.3f},{q3_:.3f}]  n={len(g)}")

        if args.scribe:
            print("\n=== Scribe-blur calibrator on the same sweeps ===")
            scribe = scribe_blur_ratios(sweeps)
            if scribe:
                pd.DataFrame(scribe).to_csv(OUT_DIR / "newer_scribe.csv", index=False)
                sr = np.array([r["scribe_ratio"] for r in scribe])
                sm, sq1, sq3 = _iqr(sr)
                print(f"  scribe ratio: median={sm:.3f}  IQR=[{sq1:.3f},{sq3:.3f}]  n={len(sr)}")
                print(f"  |log ratio| DoF-LOO median: {np.median(np.abs(np.log(ratios[ratios>0]))):.4f}")
                print(f"  |log ratio| scribe   median: {np.median(np.abs(np.log(sr[sr>0]))):.4f}")

    if args.mode in ("apply", "all"):
        # need k/form; if validate didn't run, fit on the CLEAN BARE set (the
        # same set the predictor/k were validated on) so apply uses the validated
        # calibration, not a different one.
        if best is None:
            bare = [s for s in discover_newer_sweeps() if s.is_bare]
            rows = build_measurement_table(bare, log=lambda *a, **k: None)
            fits = compare_predictors(rows)
            best = fits[0]
            print(f"(fit on clean bare set, n={len(rows)}) best={best.form} "
                  f"k={best.k:.5f} R²={best.r2:.4f}")
        older = discover_older_sweeps(_OLDER_BARE_LENSES)
        print(f"\nDiscovered {len(older)} older (2026-01-29) bare-lens sweeps")
        orows = apply_older(older, best.k, best.form)
        odf = pd.DataFrame(orows)

        # scribe-blub v1/v2 comparison via the prebuilt per_shot_per_tile if present
        v1v2 = _older_v1v2_lookup()
        if v1v2 is not None:
            odf["v1_step_mm"] = odf["sweep_id"].map(lambda s: v1v2[0].get(_older_norm_key(s)))
            odf["v2_step_mm"] = odf["sweep_id"].map(lambda s: v1v2[1].get(_older_norm_key(s)))
            odf["dof_over_v1"] = odf["dof_step_mm"] / odf["v1_step_mm"]
            odf["dof_over_v2"] = odf["dof_step_mm"] / odf["v2_step_mm"]
        odf.to_csv(OUT_DIR / "older_estimates.csv", index=False)
        print("\n=== 2026-01-29 estimates (DoF) ===")
        cols = [c for c in ["sweep_id", "m", "aperture_f", "fwhm_frames", "dof_step_mm",
                            "v1_step_mm", "v2_step_mm"] if c in odf.columns]
        print(odf[cols].to_string(index=False))
        if "dof_over_v1" in odf.columns:
            r1 = odf["dof_over_v1"].to_numpy(float)
            r2 = odf["dof_over_v2"].to_numpy(float)
            print(f"\n  DoF/v1 ratio: median={np.nanmedian(r1):.3f}  IQR="
                  f"[{np.nanpercentile(r1[np.isfinite(r1)],25):.3f},"
                  f"{np.nanpercentile(r1[np.isfinite(r1)],75):.3f}]")
            print(f"  DoF/v2 ratio: median={np.nanmedian(r2):.3f}")

    print(f"\nOutputs in {OUT_DIR}")


def _older_norm_key(s: str) -> str:
    """Normalise a sweep id to ``<lens-slug>__<mag>__<F>`` for cross-source match.

    Accepts both our older sweep_id (``<raw lens> <spaces>__<mag_dir>__<F_dir>``)
    and the phase1 sweep id
    (``older-2026-01-29/2026-01-29__<slug lens>__<mag>__<F>``). Strips any family/
    date prefix and slugifies spaces so the two line up.
    """
    s = s.split("/")[-1]
    # drop a leading date segment like 2026-01-29__
    s = re.sub(r"^\d{4}-\d{2}-\d{2}__", "", s)
    return s.replace(" ", "_")


def _older_v1v2_lookup():
    """Build v1/v2 scribe-blur lookups for the 2026-01-29 sweeps, keyed by the
    normalised ``<lens-slug>__<mag>__<F>`` so the apply step can join them to the
    DoF estimates.

    Uses a prebuilt phase1 ``per_shot_per_tile.csv`` covering 2026-01-29 (the
    scribe-blur calibrator needs phase1's wafer/scribe detections, which we do
    not recompute here). Returns ``None`` if none is found."""
    from tile_sharpness.rail_calibration import rail_step_lookup_v1, rail_step_lookup_v2
    candidates = [
        OUT_DIR / "older_per_shot_per_tile.csv",
        Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/"
             "tile-sharpness/out_apertures_for_calibration/per_shot_per_tile.csv"),
    ]
    csv_path = next((c for c in candidates if c.exists()), None)
    if csv_path is None:
        return None
    try:
        v1 = rail_step_lookup_v1(csv_path)
        v2 = rail_step_lookup_v2(csv_path)
    except Exception as e:  # pragma: no cover
        print(f"  v1/v2 lookup failed: {e}")
        return None

    def remap(d: dict[str, float]) -> dict[str, float]:
        return {_older_norm_key(sid): val for sid, val in d.items()}
    return remap(v1), remap(v2)


if __name__ == "__main__":
    main()
