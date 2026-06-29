"""Bounded periodic-FFT contrast — a ceiling-valid MTF read at a structure's
fundamental spatial frequency.

Motivation (see ``MTF_TARGET_ACQUISITION.md`` and ``REPORT_taskAD_2026-06-28.md``
§E/§F): slanted-edge / LSF MTF50 *over-reads* the diffraction ceiling on the wafer
because the scribe is a lit-vs-shadow groove, not a clean reflectance step. A
*periodic* target sidesteps this entirely: it measures contrast **at its own
fundamental frequency**, the contrast is bounded in ``[0,1]`` by construction, and it
*under*-reads to 0 past the optical cutoff — so it physically cannot over-read the
diffraction ceiling. ``maze_fft.maze_amp`` already did this for the universal 13 µm
maze; here we generalise it to read a *normalised* (Michelson-style) contrast at an
*atlas-known* structure pitch, so configs compare at a common subject-space frequency.

The output is a Michelson-like contrast:

    C = 2 · |F(f0)| / |F(0)|

where ``F`` is the 2-D FFT of the Hann-windowed (but **not** mean-subtracted) ROI,
``F(0)`` is the DC term (windowed mean × area) and ``|F(f0)|`` is the amplitude at the
fundamental. For an ideal sinusoid ``m + a·cos(2π f0 x)`` this equals ``a/m`` — the
Michelson contrast — and it is bounded in ``[0,1]`` for any non-negative modulation.
Read at the structure fundamental and compared against ``optics.diffraction_mtf_*``
at the same frequency, ``C`` is a ceiling-valid relative MTF.
"""

from __future__ import annotations

import numpy as np

from tile_sharpness.methods.maze_fft import (
    maze_freq_cy_per_px,
    MAZE_PITCH_UM,
    SENSOR_PITCH_UM_Z7,
)

try:  # cv2 only needed for de-rotation; degrade gracefully without it
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None

# Subject↔sensor frequency conversion (M=1): f_subj(lp/mm) = f_px(cy/px) · LPMM_PER_CYPX · M.
LPMM_PER_CYPX = 1000.0 / SENSOR_PITCH_UM_Z7   # ≈229.9 lp/mm per cy/px at M=1
NYQUIST = 0.5


def _hann2d(h: int, w: int) -> np.ndarray:
    return np.outer(np.hanning(h), np.hanning(w))


def maze_band_cy_per_px(
    M: float, half_bw_frac: float = 0.10
) -> tuple[float, float, float] | None:
    """The universal 13 µm maze's exclusion band ``(f_maze, lo, hi)`` in cy/px for this
    magnification ``M``, or ``None`` if the maze aliases past Nyquist.

    The maze frequency is M-dependent (``f_px = 4.35/(13·M)`` cy/px: ~0.335 @ M=1 but
    ~0.167 @ M=2), so at high M it slides DOWN into the static discovery band and a
    static exclusion misses it. The exclusion half-width is a fraction of the maze
    frequency so the window tracks the maze as it moves with M."""
    fz = maze_freq_cy_per_px(M)
    if fz <= 0 or fz + half_bw_frac * fz > NYQUIST:
        return None
    hw = half_bw_frac * fz
    return fz, max(0.0, fz - hw), min(NYQUIST, fz + hw)


STATIC_BAND: tuple[float, float] = (0.06, 0.30)


def resolvable_band_cy_per_px(
    M: float,
    pad_f1_subj_lpmm: float = 18.0,
    static_band: tuple[float, float] = STATIC_BAND,
    f1_margin: float = 0.8,
) -> tuple[float, float]:
    """M-aware resolvable discovery band ``(lo, hi)`` in cy/px.

    The static 0.06 cy/px floor is M-naive: the pad fundamental's pixel frequency is
    ``f_px = f_subj/(229.9·M)``, so at high M (e.g. M≈2) an ~18 lp/mm pad fundamental
    drops to ~0.039 cy/px — *below* the static 0.06 floor — and would be clipped. The
    floor is therefore lowered **only when the static floor would actually clip the pad
    fundamental** (``f1_px < static_lo``); until then it stays *exactly* at the static
    0.06, so the whole low-M regime (the pad fundamental sits at ≥0.06 for M ≲ 1.16)
    reproduces the static band unchanged — the regression invariant. Once the static
    floor would clip f1, the floor drops to ``f1_margin·f1_px`` (a small margin below the
    pad fundamental). The ceiling is the static 0.30: the pad comb lives below it at every
    M, and the maze line (when it slides in at high M) is removed by the M-aware
    ``exclude`` band, not by the ceiling."""
    f1_px = pad_f1_subj_lpmm / (LPMM_PER_CYPX * M)
    lo = static_band[0] if f1_px >= static_band[0] else f1_margin * f1_px
    hi = static_band[1]
    lo = min(lo, 0.8 * hi)           # never let the floor exceed the ceiling
    return float(lo), float(hi)


def derotate(roi: np.ndarray, theta_deg: float, trim_frac: float = 0.08) -> np.ndarray:
    """Rotate ``roi`` by ``-theta_deg`` so the wafer's u/v axes become image-aligned,
    then trim the rotation seam. Requires cv2; returns the ROI unchanged if cv2 is
    missing or theta is ~0."""
    if cv2 is None or abs(theta_deg) < 1e-3:
        return roi
    h, w = roi.shape
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), theta_deg, 1.0)
    der = cv2.warpAffine(roi.astype(np.float32), M, (w, h),
                         flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    t = max(2, int(trim_frac * min(h, w)))
    der = der[t:h - t, t:w - t]
    return der


def _resolve_band_exclude(
    band: tuple[float, float],
    exclude: tuple[float, float] | None,
    M: float | None,
) -> tuple[tuple[float, float], tuple[float, float] | None]:
    """Apply the M-aware band/exclude defaults (A5) when ``M`` is given and the caller
    left ``band``/``exclude`` at their static defaults. Factored out so every entry
    point (single-axis and 2-D) resolves the band identically — i.e. ``M=None`` always
    means "use the static defaults exactly as passed"."""
    if M is None:
        return band, exclude
    if band == (0.06, 0.30):
        band = resolvable_band_cy_per_px(M)
    if exclude == (0.31, 0.36):
        mb = maze_band_cy_per_px(M)
        exclude = (mb[1], mb[2]) if mb is not None else None
    return band, exclude


def _axis_peak(
    prof: np.ndarray,
    band: tuple[float, float],
    exclude: tuple[float, float] | None,
    *,
    min_prom: float = 2.0,
) -> dict | None:
    """Strongest in-band, non-excluded periodic peak of a 1-D collapsed profile.

    Returns ``dict(pitch_px, f0_cy_per_px, amp, snr)`` or ``None``. ``snr`` is the peak
    amplitude over the in-band median (a peak-prominence measure); a real peak must
    exceed ``min_prom × in-band median`` and a tiny absolute floor (else it is just the
    in-band noise of a flat / pure-noise field). This is the exact selection logic the
    original ``discover_fundamental`` used inline, lifted verbatim so both the single-axis
    and the 2-D entry points share one peak finder (byte-identical picks)."""
    n = prof.size
    if n < 32:
        return None
    prof = prof - prof.mean()
    amp = np.abs(np.fft.rfft(prof * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=1.0)
    m = (freqs >= band[0]) & (freqs <= band[1])
    if exclude is not None:
        m &= ~((freqs >= exclude[0]) & (freqs <= exclude[1]))
    idx = np.where(m)[0]
    if idx.size == 0:
        return None
    k = idx[int(np.argmax(amp[idx]))]
    in_band_med = float(np.median(amp[idx]))
    if amp[k] <= max(1e-9, min_prom * in_band_med):
        return None
    snr = float(amp[k] / in_band_med) if in_band_med > 0 else float("inf")
    return dict(pitch_px=float(1.0 / freqs[k]), f0_cy_per_px=float(freqs[k]),
                amp=float(amp[k]), snr=snr)


def discover_fundamental(
    roi: np.ndarray,
    *,
    axis: str = "auto",
    band: tuple[float, float] = (0.06, 0.30),
    exclude: tuple[float, float] | None = (0.31, 0.36),
    M: float | None = None,
) -> dict | None:
    """Find the dominant periodic fundamental of ``roi`` inside a discriminating
    frequency ``band`` (cy/px), avoiding DC bleed and (optionally) the universal
    13 µm maze line near 0.33 cy/px (``exclude``).

    The atlas super-element pitch (~100-230 px) sits far below the optical cutoff and
    carries no MTF information; the *measurable* fundamental is the structure's
    sub-element periodicity (the caveat's "FFT may lock onto sub-element periodicity"
    — which for MTF is exactly the high-frequency target we want). Returns a dict with
    ``pitch_px``, ``f0_cy_per_px``, ``axis`` and the peak amplitude, or ``None``.

    ``axis="auto"`` collapses a 2-D lattice to a SINGLE axis (the higher-amplitude one)
    and discards the other — for a genuinely 2-D grating with different u/v pitches this
    is lossy (it can lock the weaker axis and miss the dominant grid). When you need both
    axes of a 2-D lattice, call :func:`discover_fundamental_2d` instead; this single-value
    entry point is preserved unchanged for backward compatibility.

    ``M`` (optional magnification): when ``None`` (the default) the static ``band`` and
    ``exclude`` are used exactly as passed — fully backward-compatible. When ``M`` is
    given, the band and maze exclusion become M-aware (``resolvable_band_cy_per_px`` and
    ``maze_band_cy_per_px``), which is what keeps the discovery off the maze at high M
    where the maze frequency slides DOWN into the static band. By construction the
    M-aware band/exclusion reproduce the static (0.06,0.30)/(0.31,0.36) picks across the
    whole low-M regime (the floor only drops once the static 0.06 would clip the pad
    fundamental, ~M≳1.2, and the maze near 0.32 cy/px stays excluded), so low-M reads do
    not change — the only intended behaviour change is at high M. An explicitly passed
    ``band``/``exclude`` still wins over the M-derived defaults if a caller overrides
    them (i.e. M only supplies the defaults)."""
    if roi.ndim != 2 or roi.size == 0:
        return None
    band, exclude = _resolve_band_exclude(band, exclude, M)
    if band[0] >= band[1]:
        return None
    axes = ("u", "v") if axis == "auto" else (axis,)
    best = None
    for ax in axes:
        prof = roi.mean(axis=0) if ax == "u" else roi.mean(axis=1)
        rec = _axis_peak(prof, band, exclude)
        if rec is None:
            continue
        # Preserve the historical output shape exactly: pitch_px/f0_cy_per_px/axis/amp,
        # and pick across axes by raw amplitude (NOT snr) — byte-identical to the
        # pre-refactor inline implementation.
        rec = dict(pitch_px=rec["pitch_px"], f0_cy_per_px=rec["f0_cy_per_px"],
                   axis=ax, amp=rec["amp"])
        if best is None or rec["amp"] > best["amp"]:
            best = rec
    return best


# Diagnostic low floor: period ~250 px (0.004 cy/px). Coarse 2-D pad-grid super-pitches
# (atlas 11.6-192.5 px → f_px 0.005-0.086) sit AT or BELOW the discovery floor and are
# clipped by it. discover_fundamental_2d searches each axis down to this floor purely to
# REPORT the true dominant grid line per axis and FLAG when it lies below the usable
# discovery band — it never silently changes what the discovery band returns.
DIAG_FLOOR_CY_PER_PX: float = 0.004


def discover_fundamental_2d(
    roi: np.ndarray,
    *,
    band: tuple[float, float] = (0.06, 0.30),
    exclude: tuple[float, float] | None = (0.31, 0.36),
    M: float | None = None,
    diag_floor: float = DIAG_FLOOR_CY_PER_PX,
    aniso_ratio: float = 1.2,
) -> dict | None:
    """2-D-lattice-aware, **per-axis** fundamental discovery.

    A wafer pad array is a 2-D lattice with (often anisotropic) u and v pitches. The
    single-value :func:`discover_fundamental` ``axis="auto"`` argmax collapses that to one
    axis and discards the other — so it can lock the weaker axis and miss the dominant
    grid (audited: 5/6 magenta regions; the dropped axis was a ~30 px v-grid with SNR up
    to 254). This entry point keeps both axes and never collapses them.

    For each axis (``u`` = vary across columns, ``v`` = vary across rows) it reports:

    * the **in-band fundamental** — the same band-limited / maze-excluded pick the
      production discovery uses (so the resolvable, MTF-bearing sub-feature is preserved
      for MTF-probing callers), or ``None`` if no real in-band peak exists on that axis;
    * the **dominant (true-grid) line** — the strongest periodic peak searched from a very
      low diagnostic floor (``diag_floor``, period ~250 px), so the coarse pad-grid
      super-pitch is *visible*. This is the real lattice line a human sees.
    * ``true_below_floor`` — ``True`` when that dominant line sits below the usable
      discovery floor (``band[0]``), i.e. the in-band pick is NOT the dominant structure.

    Returns a dict::

        {"u": {<in-band rec> | None, with extra keys
                  true_pitch_px, true_f0_cy_per_px, true_snr, true_below_floor},
         "v": {... same ...},
         "dominant_axis": "u"|"v"|None,   # axis with the higher in-band amplitude
         "anisotropic": bool,             # true u/v pitches differ by > aniso_ratio
         "band": band, "exclude": exclude}

    or ``None`` if ``roi`` is not a non-empty 2-D array.

    **No silent mislock.** The dominant grid line is *reported*, not substituted: a caller
    that wants the resolvable MTF feature still reads the in-band fundamental, but it can
    now see (via ``true_below_floor`` / the per-axis ``true_*`` fields) when the dominant
    real structure was below the usable floor and on which axis — so it never silently
    gets the wrong axis. ``M=None`` keeps the static band/exclude exactly as passed.
    """
    if roi.ndim != 2 or roi.size == 0:
        return None
    band, exclude = _resolve_band_exclude(band, exclude, M)
    out: dict = {"band": band, "exclude": exclude}
    in_band: dict[str, dict | None] = {}
    true_f: dict[str, float | None] = {}
    for ax in ("u", "v"):
        prof = roi.mean(axis=0) if ax == "u" else roi.mean(axis=1)
        # In-band (resolvable) pick — same logic/selection as discover_fundamental.
        rec = None
        if band[0] < band[1]:
            r = _axis_peak(prof, band, exclude)
            if r is not None:
                rec = dict(pitch_px=r["pitch_px"], f0_cy_per_px=r["f0_cy_per_px"],
                           axis=ax, amp=r["amp"], snr=r["snr"])
        # Dominant true-grid line — searched from the diagnostic low floor so the coarse
        # super-pitch is visible. Reuse the same maze exclusion (never lock the maze).
        lo = max(1e-6, min(diag_floor, 0.8 * band[1]))
        diag = _axis_peak(prof, (lo, band[1]), exclude)
        if rec is not None:
            rec["true_pitch_px"] = diag["pitch_px"] if diag else rec["pitch_px"]
            rec["true_f0_cy_per_px"] = diag["f0_cy_per_px"] if diag else rec["f0_cy_per_px"]
            rec["true_snr"] = diag["snr"] if diag else rec["snr"]
            rec["true_below_floor"] = bool(diag is not None
                                           and diag["f0_cy_per_px"] < band[0] - 1e-9)
        in_band[ax] = rec
        true_f[ax] = diag["f0_cy_per_px"] if diag is not None else None
    out["u"], out["v"] = in_band["u"], in_band["v"]
    # Dominant axis = the in-band axis with the larger amplitude (matches the single-value
    # auto pick), so existing auto-pick callers reading dominant_axis see no change.
    cand = [(ax, in_band[ax]["amp"]) for ax in ("u", "v") if in_band[ax] is not None]
    out["dominant_axis"] = max(cand, key=lambda t: t[1])[0] if cand else None
    # Anisotropy on the TRUE per-axis grid pitch (the lattice property, not the clipped
    # in-band pick): u/v fundamentals differing by more than aniso_ratio.
    fu, fv = true_f["u"], true_f["v"]
    out["anisotropic"] = bool(
        fu is not None and fv is not None and fu > 0 and fv > 0
        and max(fu / fv, fv / fu) > aniso_ratio
    )
    return out


def periodic_contrast(
    roi: np.ndarray,
    pitch_px: float,
    *,
    axis: str = "auto",
    half_bw_frac: float = 0.25,
    min_periods: float = 3.0,
) -> dict | None:
    """Bounded Michelson-style periodic contrast at the fundamental ``f0 = 1/pitch_px``.

    ``axis`` selects which 1-D profile to FFT:
      * ``"u"``  — average rows, FFT along columns (horizontal periodicity / vertical
        stripes); pitch_px is the column (u) pitch.
      * ``"v"``  — average columns, FFT along rows (vertical periodicity); pitch_px is
        the row (v) pitch.
      * ``"auto"`` — try both and return the higher-contrast one (the ROI may only
        carry one clean axis).

    The 1-D collapse (averaging the orthogonal axis) is the matched filter for a
    1-D grating and rejects the orthogonal-axis structure + noise; this is what makes
    the contrast clean enough to compare across configs. Returns ``None`` if the pitch
    aliases (``f0`` ≥ Nyquist), the ROI holds < ``min_periods`` periods, or the ROI is
    degenerate. Otherwise a dict with ``contrast`` (in [0,1]), ``f0_cy_per_px``,
    ``axis`` chosen, ``n_periods``, and ``snr`` (fundamental / local sideband median).
    """
    if roi.ndim != 2 or roi.size == 0:
        return None
    if pitch_px is None or pitch_px < 2.5:
        return None
    f0 = 1.0 / pitch_px
    if f0 >= 0.5 - 1e-6:            # aliases at/above Nyquist
        return None

    axes = ("u", "v") if axis == "auto" else (axis,)
    best = None
    for ax in axes:
        prof = roi.mean(axis=0) if ax == "u" else roi.mean(axis=1)
        n = prof.size
        if n < 8 or n * f0 < min_periods:
            continue
        win = np.hanning(n)
        wmean = float((prof * win).sum())
        if wmean <= 0:
            continue
        spec = np.fft.rfft((prof - 0.0) * win)   # keep DC: F(0) = sum(prof*win)
        amp = np.abs(spec)
        freqs = np.fft.rfftfreq(n, d=1.0)
        dc = amp[0]
        if dc <= 0:
            continue
        # locate the fundamental bin, allow +-half_bw_frac*f0 search to absorb
        # small pitch/scale error; take the local max as the fundamental amplitude.
        bw = max(1, int(round(half_bw_frac * f0 * n)))
        idx0 = int(np.argmin(np.abs(freqs - f0)))
        lo, hi = max(1, idx0 - bw), min(len(amp), idx0 + bw + 1)
        if hi <= lo:
            continue
        kpk = lo + int(np.argmax(amp[lo:hi]))
        fund = amp[kpk]
        # local sideband median for SNR (exclude the fundamental neighbourhood)
        side_lo, side_hi = max(1, kpk - 4 * bw), min(len(amp), kpk + 4 * bw + 1)
        side = np.concatenate([amp[side_lo:max(side_lo, kpk - bw)],
                               amp[min(side_hi, kpk + bw + 1):side_hi]])
        side_med = float(np.median(side)) if side.size else 0.0
        contrast = float(min(1.0, 2.0 * fund / dc))
        snr = float(fund / side_med) if side_med > 0 else float("inf")
        rec = dict(contrast=contrast, f0_cy_per_px=float(freqs[kpk]),
                   axis=ax, n_periods=float(n * f0), snr=snr,
                   pitch_px=float(pitch_px))
        if best is None or rec["contrast"] > best["contrast"]:
            best = rec
    return best
