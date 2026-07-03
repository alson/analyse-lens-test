"""Per-camera sensor parameters for the cross-M relative-MTF pipeline.

The pipeline was built Z7-only (FX, 4.35 µm pixel pitch, no OLPF). Bringing the D7200
wafer-macro data in (DX, 3.91 µm, OLPF) needs the sensor pitch — and an OLPF provenance
flag — to travel per config rather than being hard-coded. Every :class:`ConfigNode`
carries a ``camera`` key; this table maps it to the sensor parameters.

Pitch is the load-bearing scalar: it converts a per-pixel registration residual to
object-space µm (the reg-guard ceiling), a sensor frequency (cy/px) to subject lp/mm, and
sizes atlas ROIs. ``olpf`` is provenance/reporting only in phase 1 — an anti-alias filter
is a common multiplicative factor across every lens on the same body, so it CANCELS in a
within-camera fixed-sensor-frequency RELATIVE ranking; it does NOT cancel across cameras,
which is why the Z7↔D7200 absolute bridge stays deferred (see ``D7200_INTEGRATION_PLAN.md``).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Camera:
    """Sensor parameters for one camera body."""

    name: str
    pitch_um: float
    olpf: bool
    width_px: int
    height_px: int


#: Registry of camera bodies used in the wafer-macro sessions. Keyed by the ``camera``
#: string carried on every :class:`~tile_sharpness.multi_session.ConfigNode`.
CAMERAS: dict[str, Camera] = {
    "Z7": Camera("Z7", pitch_um=4.35, olpf=False, width_px=8256, height_px=5504),
    "D7200": Camera("D7200", pitch_um=3.91, olpf=True, width_px=6000, height_px=4000),
}

#: Default camera for back-compat with any pre-``camera``-column subset row.
DEFAULT_CAMERA = "Z7"


def get_camera(camera: str | None) -> Camera:
    """Look up a :class:`Camera`, falling back to the Z7 default for empty/unknown keys."""
    return CAMERAS.get((camera or "").strip() or DEFAULT_CAMERA, CAMERAS[DEFAULT_CAMERA])


def camera_pitch_um(camera: str | None) -> float:
    """Sensor pixel pitch in µm for ``camera`` (Z7 default). Load-bearing scalar."""
    return get_camera(camera).pitch_um
