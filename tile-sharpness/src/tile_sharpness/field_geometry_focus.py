"""POC 4 — FIELD CURVATURE from the through-focus best-focus surface (tilt removed).

Each wafer patch has a best-focus axial position ``mu_mm`` (where it is sharpest
through the focus stack, from POC 3) and a field position ``(px, py)`` in sensor
pixels (from POC 1's ``field_geometry``). Mapping ``mu_mm`` over ``(px, py)``
gives a SURFACE.

The PLANE TILT of that surface is rig / sensor-vs-subject-plane alignment (and
from a SINGLE config is degenerate with any lens-induced tilt), so it is NOT a
lens property — we REGRESS IT OUT and never report it. Everything downstream is
computed on the tilt-REMOVED surface so the tilt cannot contaminate it:

* **Field curvature** — a curved (bowl/dome) residual after removing the plane:
  centre focuses at a different depth than the corners. Primary metric is the
  DoF-normalised centre-to-corner sag (dimensionless, step-calibration-free).
* **Decentering** — the curvature-vertex offset from frame centre (the ``(x0,y0)``
  that minimises the residual of ``mu ≈ c + k·((x−x0)²+(y−y0)²)``), a
  tilt-INDEPENDENT indicator, reported only when robustly estimable.

Model (all fits are on the SAME surface, plane + curvature FIT JOINTLY):

    mu_mm ≈ c + a·x + b·y + k·(x² + y²)

The linear ``a·x + b·y`` (the plane tilt) and the intercept are fit SIMULTANEOUSLY
with the quadratic ``k``; the curvature sag is derived from ``k``, never from a
raw corner-minus-centre of the un-detrended surface (which would carry the tilt).
Expanding a vertex-shifted paraboloid ``c' + k·((x−x0)²+(y−y0)²)`` shows the
linear coefficients ARE ``−2k·x0, −2k·y0`` — algebraically identical to a plane
tilt. So from a SINGLE config a plane tilt is INDISTINGUISHABLE from a
vertex-shifted bowl: the vertex ``(x0,y0) = (−a/2k, −b/2k)`` read off the joint
fit is only a meaningful decentering indicator when it is geometrically sane
(strong enough curvature AND the vertex landing inside/near the frame). When the
apparent vertex flies outside the frame it is really the rig tilt in disguise,
and :func:`fit_vertex_offset` reports ``estimable=False``. Clean tilt-independent
decentering needs cross-config or the per-orientation sag/tan extract.

Pure helpers only — no I/O, no image work. The driver in
``scripts/poc_field_geometry.py`` joins the POC 3 physical table to the POC 1
field-geometry shards and calls these.

Coordinate convention (matches ``cross_m_relative_mtf.field_geometry``):

* ``px``/``py`` are sensor pixels; image-y grows DOWNWARD.
* ``field_height`` is ``dist_px`` / frame half-diagonal (0 = centre, 1 = corner).
* Sign of the physical sag: +ve ⇒ corners focus FARTHER (larger ``mu_mm``) than
  the centre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .methods.maze_fft import SENSOR_PITCH_UM_Z7


@dataclass
class CurvatureFit:
    """Joint plane+quadratic fit of the best-focus surface, tilt removed."""

    # joint model: mu ≈ c + a·x + b·y + k·(x²+y²)
    c_mm: float
    a_mm_per_px: float          # linear tilt term (regressed out, NOT reported)
    b_mm_per_px: float          # linear tilt term (regressed out, NOT reported)
    k_mm_per_px2: float         # quadratic curvature coefficient
    # curvature products (from k, on the tilt-removed surface)
    sag_um: float               # signed centre→corner focus shift, µm (+ = corners farther)
    sag_dof: float              # PRIMARY: sag / median through-focus FWHM (dimensionless)
    radius_mm: float            # best-focus-surface radius of curvature, mm (signed);
    #                             lateral axis in SENSOR mm (r_px·pitch), R=1/(2k')
    rms_residual_um: float      # RMS about the FULL plane+quadratic fit, µm (field irregularity)
    # geometry used
    fh_max: float               # max field height in the patch set
    px_corner: float            # pixel radius at fh_max (for the sag lever arm)
    n: int


@dataclass
class VertexOffset:
    """Tilt-independent decentering: the paraboloid-vertex offset from frame centre."""

    estimable: bool
    x0_px: float                # vertex x in image px (frame centre = cx)
    y0_px: float                # vertex y in image px
    dx0_px: float               # x0 − cx  (offset from frame centre)
    dy0_px: float               # y0 − cy
    offset_px: float            # hypot(dx0, dy0)
    offset_field_frac: float    # offset_px / frame half-diagonal
    rms_vertex_um: float        # RMS of the vertex-only (no free tilt) fit, µm
    rms_freetilt_um: float      # RMS of the free-tilt joint fit, µm (lower bound)
    note: str = ""


@dataclass
class Astigmatism:
    """Sagittal vs tangential best-focus split — needs a per-orientation extract."""

    available: bool
    delta_mm: float
    note: str = ""


@dataclass
class FieldGeometryResult:
    curvature: CurvatureFit
    vertex: VertexOffset
    astigmatism: Astigmatism
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Joint plane + quadratic fit (tilt regressed out simultaneously with curvature)
# --------------------------------------------------------------------------- #
def fit_curvature_detrended(
    px: np.ndarray, py: np.ndarray, mu_mm: np.ndarray,
    fwhm_mm_median: float,
    *, cx: float, cy: float,
    half_diag_px: float,
    sensor_pitch_um: float = SENSOR_PITCH_UM_Z7,
) -> CurvatureFit:
    """Fit ``mu ≈ c + a·x + b·y + k·(x²+y²)`` and derive curvature from ``k`` alone.

    The linear plane (a,b,c) is fit SIMULTANEOUSLY with the quadratic k, so the
    curvature coefficient k is orthogonalised against the tilt. All downstream
    numbers come from k / from the residual of this full fit — never from a raw
    corner-minus-centre of the un-detrended surface.

    x,y are taken RELATIVE to the frame centre (cx,cy) so k·(x²+y²) is a paraboloid
    about the frame centre; a genuine vertex offset then shows up in a,b (handled
    separately by :func:`fit_vertex_offset`). The sag is the change in the
    quadratic part from centre (fh=0) to the corner (max field height):
    ``sag = k · px_corner²`` where ``px_corner = fh_max · half_diag_px``.
    """
    px = np.asarray(px, float) - float(cx)
    py = np.asarray(py, float) - float(cy)
    mu = np.asarray(mu_mm, float)
    n = int(px.size)
    r2 = px * px + py * py
    fh_max = float(np.sqrt(r2.max()) / half_diag_px) if half_diag_px > 0 else float("nan")
    px_corner = float(np.sqrt(r2.max()))
    bad = CurvatureFit(*( [float("nan")] * 4 ), float("nan"), float("nan"),
                       float("nan"), float("nan"), fh_max, px_corner, n)
    if n < 4 or not np.isfinite(mu).all():
        return bad
    # design: [1, x, y, x²+y²]
    A = np.column_stack([np.ones_like(px), px, py, r2])
    coef, *_ = np.linalg.lstsq(A, mu, rcond=None)
    c, a, b, k = (float(coef[0]), float(coef[1]), float(coef[2]), float(coef[3]))
    fit = A @ coef
    rms_um = float(np.sqrt(np.mean((mu - fit) ** 2)) * 1000.0)
    # sag from k on the tilt-removed surface: quadratic part centre→corner
    sag_mm = k * px_corner * px_corner
    sag_um = sag_mm * 1000.0
    sag_dof = (sag_mm / fwhm_mm_median
               if math.isfinite(fwhm_mm_median) and fwhm_mm_median > 0 else float("nan"))
    # Radius of the best-focus surface in a consistent length frame: express the
    # lateral coordinate in SENSOR mm (r_mm = r_px · pitch) so mu[mm] = k'·r_mm²
    # with k' = k / pitch_mm²; paraboloid apex radius R = 1/(2k').
    pitch_mm = sensor_pitch_um / 1000.0
    k_per_mm2 = k / (pitch_mm * pitch_mm)
    radius_mm = (1.0 / (2.0 * k_per_mm2)) if k_per_mm2 != 0.0 else float("inf")
    return CurvatureFit(
        c_mm=c, a_mm_per_px=a, b_mm_per_px=b, k_mm_per_px2=k,
        sag_um=sag_um, sag_dof=sag_dof, radius_mm=radius_mm,
        rms_residual_um=rms_um, fh_max=fh_max, px_corner=px_corner, n=n,
    )


# --------------------------------------------------------------------------- #
# Tilt-independent decentering: vertex offset of a NO-free-tilt paraboloid
# --------------------------------------------------------------------------- #
def fit_vertex_offset(
    px: np.ndarray, py: np.ndarray, mu_mm: np.ndarray,
    *, cx: float, cy: float, half_diag_px: float,
    freetilt_rms_um: float,
    min_sag_um: float = 20.0,
    max_offset_frac: float = 0.60,
) -> VertexOffset:
    """Vertex ``(x0,y0)`` of the best-focus paraboloid → decentering indicator.

    A shifted paraboloid ``c + k·((x−x0)²+(y−y0)²)`` expands to
    ``(c+k r0²) + (−2k x0)·x + (−2k y0)·y + k·(x²+y²)`` — the SAME
    ``{1,x,y,x²+y²}`` basis as the joint plane+quadratic fit. So the vertex is
    just ``x0 = −a/(2k), y0 = −b/(2k)`` read off the joint fit coefficients; the
    vertex-only and free-tilt fits are ALGEBRAICALLY IDENTICAL (same design
    matrix), hence ``rms_vertex == rms_freetilt``.

    **This is the crux of the degeneracy the coordinator flagged: from ONE config
    a plane tilt is INDISTINGUISHABLE from a vertex-shifted bowl.** A pure tilt
    ``t·x`` reads as a vertex at ``x0 = −t/(2k)``, which flies far outside the
    frame for realistic (small k, non-trivial t). We therefore treat the vertex
    as a decentering indicator ONLY when it is geometrically sane:

    * curvature strong enough to define a vertex (``|sag| ≥ min_sag_um``), and
    * the vertex lands INSIDE / near the frame
      (``offset / half_diagonal ≤ max_offset_frac``).

    Otherwise the "vertex" is really the rig tilt in disguise and we report
    ``estimable=False`` with an explanatory note — i.e. clean tilt-independent
    decentering needs cross-config or the per-orientation sag/tan extract.
    """
    pxr = np.asarray(px, float) - float(cx)
    pyr = np.asarray(py, float) - float(cy)
    mu = np.asarray(mu_mm, float)
    n = int(pxr.size)
    nan = float("nan")
    if n < 6 or not np.isfinite(mu).all():
        return VertexOffset(False, nan, nan, nan, nan, nan, nan, nan,
                            freetilt_rms_um, note="too few patches for vertex fit")
    A = np.column_stack([np.ones_like(pxr), pxr, pyr, pxr * pxr + pyr * pyr])
    coef, *_ = np.linalg.lstsq(A, mu, rcond=None)
    _c, a, b, k = (float(coef[0]), float(coef[1]), float(coef[2]), float(coef[3]))
    fit = A @ coef
    rms_vertex_um = float(np.sqrt(np.mean((mu - fit) ** 2)) * 1000.0)
    px_corner2 = float((pxr * pxr + pyr * pyr).max())
    sag_um = abs(k * px_corner2) * 1000.0
    if k == 0.0 or sag_um < min_sag_um:
        return VertexOffset(False, nan, nan, nan, nan, nan, nan,
                            rms_vertex_um, freetilt_rms_um,
                            note=f"curvature too weak (|sag| {sag_um:.0f}µm < "
                                 f"{min_sag_um:.0f}µm) — vertex not estimable")
    dx0 = -a / (2.0 * k)
    dy0 = -b / (2.0 * k)
    x0 = dx0 + float(cx)
    y0 = dy0 + float(cy)
    offset_px = math.hypot(dx0, dy0)
    offset_frac = offset_px / half_diag_px if half_diag_px > 0 else float("nan")
    estimable = True
    note = ""
    if not math.isfinite(offset_frac) or offset_frac > max_offset_frac:
        estimable = False
        note = (f"vertex offset {offset_frac:.2f}×half-diag lands outside the "
                f"sane region (>{max_offset_frac:.2f}) → dominated by plane tilt; "
                "decentering NOT separable from tilt with one config")
    return VertexOffset(
        estimable=estimable, x0_px=x0, y0_px=y0, dx0_px=dx0, dy0_px=dy0,
        offset_px=offset_px, offset_field_frac=offset_frac,
        rms_vertex_um=rms_vertex_um, rms_freetilt_um=freetilt_rms_um, note=note,
    )


def analyse_field_geometry(
    px: np.ndarray, py: np.ndarray, mu_mm: np.ndarray,
    fwhm_mm_median: float,
    *, cx: float, cy: float, half_diag_px: float,
    edge_orient_available: bool = False,
) -> FieldGeometryResult:
    """Run the tilt-removed curvature + vertex-offset geometry on one config."""
    curv = fit_curvature_detrended(
        px, py, mu_mm, fwhm_mm_median,
        cx=cx, cy=cy, half_diag_px=half_diag_px,
    )
    vtx = fit_vertex_offset(
        px, py, mu_mm, cx=cx, cy=cy, half_diag_px=half_diag_px,
        freetilt_rms_um=curv.rms_residual_um,
    )
    ast = Astigmatism(
        False, float("nan"),
        note=("needs the per-orientation (sagittal/tangential) best-focus extract; "
              "POC 3 collapses the stack to one mu_mm per patch"),
    ) if not edge_orient_available else Astigmatism(True, float("nan"), note="")
    return FieldGeometryResult(
        curvature=curv, vertex=vtx, astigmatism=ast,
        extra={"cx": cx, "cy": cy, "half_diag_px": half_diag_px},
    )


# frame half-diagonal for the Z7 full frame (px), matches field_geometry
Z7_FRAME_W = 8256
Z7_FRAME_H = 5504
Z7_HALF_DIAG_PX = 0.5 * math.hypot(Z7_FRAME_W, Z7_FRAME_H)
Z7_CENTRE = (Z7_FRAME_W / 2.0, Z7_FRAME_H / 2.0)
