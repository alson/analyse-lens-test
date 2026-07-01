"""POC 4 — decentering + field curvature from the through-focus best-focus surface.

Each wafer patch has a best-focus axial position ``mu_mm`` (where it is sharpest
through the focus stack, from POC 3) and a field position ``(px, py)`` in sensor
pixels (from POC 1's ``field_geometry``). Mapping ``mu_mm`` over ``(px, py)`` gives
a SURFACE whose shape is the lens/sensor geometry:

* a TILTED best-focus plane ``mu_mm ≈ a·px + b·py + c`` ⇒ subject-plane tilt /
  decentering (and its azimuth),
* a curved (bowl/dome) residual after removing the plane ⇒ field curvature
  (centre focuses at a different depth than the corners),
* a sagittal-vs-tangential best-focus split ⇒ astigmatism.

This is the FOCUS-POSITION approach, complementary to the amplitude-based field
analysis in ``cross_m_relative_mtf`` (``azimuthal_asymmetry`` etc.).

Pure helpers only — no I/O, no image work. The driver in
``scripts/poc_field_geometry.py`` joins the POC 3 physical table to the POC 1
field-geometry shards and calls these. We reuse :func:`characterise._plane_fit`
and :func:`characterise._slope_to_tilt_deg` so the tilt comes out in degrees in
subject space, consistent with the existing pipeline.

Coordinate convention (matches ``cross_m_relative_mtf.field_geometry``):

* ``px``/``py`` are sensor pixels; image-y grows DOWNWARD.
* The plane-fit slope ``a`` is mm of best-focus per pixel of ``px`` (rightward),
  ``b`` is mm per pixel of ``py`` (downward). ``_slope_to_tilt_deg`` converts a
  per-sensor-pixel mm slope to a subject-space tilt angle; ``px``/``py`` here are
  sensor pixels (Z7 4.35 µm), so ``a``/``b`` feed it directly.
* ``angle_deg`` (azimuth) is math convention with image-y FLIPPED: +x (right) =
  0°, up = +90°, left = 180°, down = −90°.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .characterise import _plane_fit, _slope_to_tilt_deg
from .methods.maze_fft import SENSOR_PITCH_UM_Z7


@dataclass
class PlaneTilt:
    """Plane fit of ``mu_mm`` over ``(px, py)`` → subject-space tilt."""

    a_mm_per_px: float          # d(mu_mm)/d(px), px = rightward
    b_mm_per_px: float          # d(mu_mm)/d(py), py = downward
    c_mm: float                 # intercept (mu_mm at px=py=0)
    rms_residual_mm: float      # RMS of mu_mm about the fitted plane
    tilt_x_deg: float           # subject-space tilt about the px axis
    tilt_y_deg: float           # subject-space tilt about the py axis
    tilt_mag_deg: float         # total tilt magnitude
    tilt_azimuth_deg: float     # azimuth of STEEPEST ASCENT of best-focus,
    #                             field_geometry convention (+x=0, up=+90, down=-90)
    n: int


@dataclass
class FieldCurvature:
    """Radial fit of the plane-removed residual vs field height."""

    curv_coef_mm_per_fh2: float   # k in residual ≈ k·field_height² + d
    sag_um: float                 # peak-to-edge curvature sag (signed: +ve = corners
    #                               focus FARTHER than centre), µm
    rms_residual_um: float        # RMS about the radial fit, µm
    centre_focus_mm: float        # fitted residual at field_height=0
    edge_focus_mm: float          # fitted residual at max field_height
    n: int


@dataclass
class Decentering:
    """Left-right / top-bottom best-focus asymmetry of the field."""

    lr_mm: float        # mean(mu_mm | left) - mean(mu_mm | right)
    tb_mm: float        # mean(mu_mm | top)  - mean(mu_mm | bottom)
    #                     "top" = image-up (angle_deg > 0), "bottom" = image-down
    n_left: int
    n_right: int
    n_top: int
    n_bottom: int


@dataclass
class Astigmatism:
    """Sagittal vs tangential best-focus split, if the edge orientations allow it."""

    available: bool
    mean_sag_mm: float
    mean_tan_mm: float
    delta_mm: float          # sag - tan
    n_sag: int
    n_tan: int
    note: str = ""


@dataclass
class FieldGeometryResult:
    """Full per-config focus-surface geometry."""

    plane: PlaneTilt
    curvature: FieldCurvature
    decentering: Decentering
    astigmatism: Astigmatism
    extra: dict = field(default_factory=dict)


def fit_plane_tilt(
    px: np.ndarray, py: np.ndarray, mu_mm: np.ndarray, m: float,
    *, sensor_pitch_um: float = SENSOR_PITCH_UM_Z7,
) -> PlaneTilt:
    """Fit ``mu_mm ≈ a·px + b·py + c`` and convert slopes to subject-space tilt.

    ``m`` is the sweep magnification (for the pixel→object scaling in
    :func:`_slope_to_tilt_deg`).
    """
    px = np.asarray(px, float)
    py = np.asarray(py, float)
    mu = np.asarray(mu_mm, float)
    n = int(px.size)
    a, b, c, rms = _plane_fit(px.tolist(), py.tolist(), mu.tolist())
    tilt_x = _slope_to_tilt_deg(a, m, sensor_pitch_um=sensor_pitch_um)
    tilt_y = _slope_to_tilt_deg(b, m, sensor_pitch_um=sensor_pitch_um)
    if math.isfinite(tilt_x) and math.isfinite(tilt_y):
        tilt_mag = math.degrees(
            math.atan(math.hypot(math.tan(math.radians(tilt_x)),
                                 math.tan(math.radians(tilt_y))))
        )
    else:
        tilt_mag = float("nan")
    # Azimuth of steepest ASCENT of mu_mm. The gradient in image px is (a, b)
    # with py downward; flip py to the field_geometry math convention (up=+90).
    if math.isfinite(a) and math.isfinite(b) and (a != 0.0 or b != 0.0):
        azimuth = math.degrees(math.atan2(-b, a))
    else:
        azimuth = float("nan")
    return PlaneTilt(
        a_mm_per_px=a, b_mm_per_px=b, c_mm=c, rms_residual_mm=rms,
        tilt_x_deg=tilt_x, tilt_y_deg=tilt_y, tilt_mag_deg=tilt_mag,
        tilt_azimuth_deg=azimuth, n=n,
    )


def fit_field_curvature(
    field_height: np.ndarray, residual_mm: np.ndarray,
) -> FieldCurvature:
    """Fit plane-removed ``residual_mm ≈ k·field_height² + d`` and report the sag.

    ``residual_mm`` is ``mu_mm`` MINUS the fitted plane (so plane tilt is already
    removed). A bowl/dome shows up as a non-zero ``k``: ``sag_um`` is the signed
    peak-to-edge difference (+ve ⇒ corners focus FARTHER from the camera than the
    centre, i.e. ``mu_mm`` larger at the edge).
    """
    fh = np.asarray(field_height, float)
    res = np.asarray(residual_mm, float)
    n = int(fh.size)
    if n < 3 or not np.isfinite(fh).all() or not np.isfinite(res).all():
        return FieldCurvature(float("nan"), float("nan"), float("nan"),
                              float("nan"), float("nan"), n)
    x = fh * fh
    # res = k*x + d  (least squares)
    A = np.column_stack([x, np.ones_like(x)])
    coef, *_ = np.linalg.lstsq(A, res, rcond=None)
    k, d = float(coef[0]), float(coef[1])
    fit = A @ coef
    rms_um = float(np.sqrt(np.mean((res - fit) ** 2)) * 1000.0)
    fh_max = float(fh.max())
    centre = d                       # at fh=0
    edge = k * fh_max * fh_max + d   # at fh_max
    sag_um = (edge - centre) * 1000.0
    return FieldCurvature(
        curv_coef_mm_per_fh2=k, sag_um=sag_um, rms_residual_um=rms_um,
        centre_focus_mm=centre, edge_focus_mm=edge, n=n,
    )


def compute_decentering(
    px: np.ndarray, py: np.ndarray, mu_mm: np.ndarray,
    cx: float, cy: float,
) -> Decentering:
    """Left-right / top-bottom mean best-focus asymmetry about ``(cx, cy)``.

    ``lr_mm`` = mean(mu_mm | px<cx) − mean(mu_mm | px>cx); positive ⇒ the LEFT
    half focuses farther. ``tb_mm`` = mean(mu_mm | image-up) − mean(mu_mm |
    image-down); positive ⇒ the TOP half focuses farther. (Image-up is py<cy.)
    """
    px = np.asarray(px, float)
    py = np.asarray(py, float)
    mu = np.asarray(mu_mm, float)
    left = px < cx
    right = px > cx
    top = py < cy        # image-up
    bottom = py > cy     # image-down

    def _m(mask):
        v = mu[mask]
        return float(np.mean(v)) if v.size else float("nan")

    lr = _m(left) - _m(right)
    tb = _m(top) - _m(bottom)
    return Decentering(
        lr_mm=lr, tb_mm=tb,
        n_left=int(left.sum()), n_right=int(right.sum()),
        n_top=int(top.sum()), n_bottom=int(bottom.sum()),
    )


def compute_astigmatism(
    angle_deg: np.ndarray, edge_orient_deg: np.ndarray | None,
    mu_mm: np.ndarray, field_height: np.ndarray,
    *, min_field_height: float = 0.25, tol_deg: float = 22.5,
) -> Astigmatism:
    """Best-focus split between sagittal- and tangential-oriented edges.

    Astigmatism needs edges of KNOWN orientation relative to the radial vector.
    ``edge_orient_deg`` (per patch) is the dominant edge azimuth; an edge is
    SAGITTAL when it lies along the radial direction (orientation ≈ ``angle_deg``)
    and TANGENTIAL when perpendicular. If ``edge_orient_deg`` is None (the wafer
    pad/patch geometry doesn't carry a clean dominant edge orientation per patch),
    the split is not available and we say so.
    """
    if edge_orient_deg is None:
        return Astigmatism(False, float("nan"), float("nan"), float("nan"),
                          0, 0, note="no per-patch edge orientation available")
    ang = np.asarray(angle_deg, float)
    eo = np.asarray(edge_orient_deg, float)
    mu = np.asarray(mu_mm, float)
    fh = np.asarray(field_height, float)
    # only patches off-axis enough to define a radial direction
    use = fh >= min_field_height
    # angle between edge orientation and radial vector, folded into [0,90]
    d = np.abs(((eo - ang + 90) % 180) - 90)
    sag = use & (d <= tol_deg)              # edge aligned with radius
    tan = use & (d >= 90 - tol_deg)          # edge perpendicular to radius
    n_sag, n_tan = int(sag.sum()), int(tan.sum())
    if n_sag < 3 or n_tan < 3:
        return Astigmatism(False, float("nan"), float("nan"), float("nan"),
                          n_sag, n_tan,
                          note="too few sagittal/tangential patches to separate")
    mean_sag = float(np.mean(mu[sag]))
    mean_tan = float(np.mean(mu[tan]))
    return Astigmatism(True, mean_sag, mean_tan, mean_sag - mean_tan,
                      n_sag, n_tan)


def analyse_field_geometry(
    px: np.ndarray, py: np.ndarray, mu_mm: np.ndarray,
    field_height: np.ndarray, angle_deg: np.ndarray, m: float,
    *, cx: float | None = None, cy: float | None = None,
    edge_orient_deg: np.ndarray | None = None,
    sensor_pitch_um: float = SENSOR_PITCH_UM_Z7,
) -> FieldGeometryResult:
    """Run the full focus-surface geometry on one config's patches.

    ``cx``/``cy`` default to the mean of ``px``/``py`` (the patch centroid). The
    field-height-based curvature does not depend on the centre; the L-R/T-B
    decentering split does.
    """
    px = np.asarray(px, float)
    py = np.asarray(py, float)
    mu = np.asarray(mu_mm, float)
    fh = np.asarray(field_height, float)
    ang = np.asarray(angle_deg, float)
    if cx is None:
        cx = float(np.mean(px))
    if cy is None:
        cy = float(np.mean(py))

    plane = fit_plane_tilt(px, py, mu, m, sensor_pitch_um=sensor_pitch_um)
    # residual after removing the fitted plane
    resid = mu - (plane.a_mm_per_px * px + plane.b_mm_per_px * py + plane.c_mm)
    curv = fit_field_curvature(fh, resid)
    dec = compute_decentering(px, py, mu, cx, cy)
    ast = compute_astigmatism(ang, edge_orient_deg, mu, fh)
    return FieldGeometryResult(
        plane=plane, curvature=curv, decentering=dec, astigmatism=ast,
        extra={"cx": cx, "cy": cy},
    )
