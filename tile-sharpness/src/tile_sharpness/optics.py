"""Diffraction / effective-aperture physics for the cross-config resolution
ranking.

The lens-characteristics ranking (``characterise.py``) reports subject-space
MTF50 (lp/mm on the subject) per config at centre / corner field positions. To
tell whether a config is limited by the GLASS (aberrations / focus — a better
lens or wider aperture would help) or by DIFFRACTION (the physical limit at its
working aperture — adding magnification via tubes/TCs only dims it further), we
compare the measured MTF50 against the diffraction-limited ceiling at the
config's *effective* aperture.

Two effects make the working aperture dimmer than the marked f-number:

* **Focusing magnification.** A lens focused at magnification ``M`` has an
  effective f-number ``N_eff = N * (1 + M / p)`` where ``p`` is the pupil
  magnification (≈1 for the roughly-symmetric macro lenses here; >1 for
  telephotos, which suffer less; <1 for retrofocus wides). Extension tubes raise
  ``M`` and therefore ``N_eff`` — that is the bellows factor.
* **Teleconverters** multiply the marked f-number directly; pass the
  TC-multiplied ``N`` as ``n_marked`` (it is usually what EXIF reports for an
  electronic TC).

Diffraction ceiling: for a perfect incoherent system with a circular aperture
the MTF crosses 0.5 at ``ν/ν_cutoff ≈ 0.404`` where the cutoff is
``ν_cutoff = 1 / (λ · N_eff)`` cycles per unit length at the image plane. So the
sensor-plane MTF50 is ``0.404 / (λ · N_eff)`` and the subject-plane figure is
that times ``M`` (the subject is ``M``× smaller, so the same image-plane
frequency is ``M``× finer on the subject). A real lens can only do WORSE than
this, so ``measured / ceiling`` (the "diffraction headroom") near 1 means
diffraction-limited; well below 1 means glass/focus-limited; above 1 means the
measurement is optimistic (slanted-edge over-read or a mis-stated N_eff).

Defaults: ``λ = 0.55 µm`` (green), ``p = 1`` (symmetric pupil). All MTF50 values
are line-pairs per mm (cy = lp).
"""
from __future__ import annotations

GREEN_WAVELENGTH_UM = 0.55
MTF50_CUTOFF_FRACTION = 0.404   # ν/ν_cutoff where the diffraction MTF = 0.5


def effective_fnumber(n_marked: float, magnification: float, pupil_mag: float = 1.0) -> float:
    """Working f-number of a lens marked ``n_marked`` focused at ``magnification``.

    ``N_eff = N * (1 + M / p)``. For a teleconverter, pass the TC-multiplied
    marked f-number as ``n_marked``."""
    if n_marked <= 0 or magnification < 0 or pupil_mag <= 0:
        raise ValueError("n_marked>0, magnification>=0, pupil_mag>0 required")
    return n_marked * (1.0 + magnification / pupil_mag)


def diffraction_mtf50_sensor_lpmm(n_eff: float, wavelength_um: float = GREEN_WAVELENGTH_UM) -> float:
    """Diffraction-limited MTF50 at the SENSOR/image plane (lp/mm)."""
    if n_eff <= 0 or wavelength_um <= 0:
        raise ValueError("n_eff>0, wavelength_um>0 required")
    wavelength_mm = wavelength_um / 1000.0
    cutoff_lpmm = 1.0 / (wavelength_mm * n_eff)
    return MTF50_CUTOFF_FRACTION * cutoff_lpmm


def diffraction_mtf50_subject_lpmm(n_marked: float, magnification: float,
                                   pupil_mag: float = 1.0,
                                   wavelength_um: float = GREEN_WAVELENGTH_UM) -> float:
    """Diffraction-limited MTF50 in SUBJECT space (lp/mm on the subject), at the
    effective aperture for ``magnification``. This is the ceiling a real lens
    cannot exceed; compare measured subject-space MTF50 against it.

    Note the ``M / (1 + M)`` behaviour (for p=1): as magnification grows the
    subject-space ceiling saturates toward ``0.404 / (λ · N)`` — i.e. adding
    magnification via tubes buys ever less subject resolution, the quantitative
    'empty magnification' limit."""
    n_eff = effective_fnumber(n_marked, magnification, pupil_mag)
    return diffraction_mtf50_sensor_lpmm(n_eff, wavelength_um) * magnification
