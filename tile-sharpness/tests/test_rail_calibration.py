"""Tests for the through-focus rail-step-mm calibration."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from tile_sharpness.methods.maze_fft import SENSOR_PITCH_UM_Z7
from tile_sharpness.phase1 import SCRIBE_WIDTH_UM
from tile_sharpness.rail_calibration import (
    CalibrationResult,
    EffectiveApertureLookup,
    PooledCalibrationResult,
    analytical_diopter_effective_f,
    blur_um_from_widening,
    calibrate_group,
    calibrate_sweep,
    defocus_um_from_blur,
    fwhm_object_um,
    group_key,
    parse_aperture,
    resolve_effective_aperture,
)


# --- pure-function unit tests ---


def test_parse_aperture_simple():
    assert parse_aperture("2026-01-29__Some_Lens__1_1__F8") == 8.0
    assert parse_aperture("foo__F5.6") == 5.6
    assert parse_aperture("foo__bar__F11") == 11.0


def test_parse_aperture_newer_rig_lowercase_format():
    assert parse_aperture("newer-rig/2026-05-13__Sigma__f_5.6") == 5.6
    assert parse_aperture("newer-rig/foo__f_11") == 11.0


def test_parse_aperture_post_rename_underscore_decimal():
    """The aperture-convention rewrite renamed dirs to underscore-as-decimal
    for filesystem safety: ``f_5_6`` is f/5.6, ``f_2_8`` is f/2.8 etc."""
    assert parse_aperture("archive-2026-05/foo__f_5_6") == 5.6
    assert parse_aperture("archive-2026-05/foo__f_2_8") == 2.8
    assert parse_aperture("archive-2026-05/foo__f_5_3") == 5.3
    # Mixed: lens-name has dots/underscores too — still match suffix only.
    assert parse_aperture(
        "archive-2026-05/2026-05-13__NIKKOR Z MC 105mm f_2.8 VR S + 5T + 6T__f_5_6"
    ) == 5.6


def test_parse_aperture_ignores_lens_name_fspec():
    """A lens name like 'Sigma_F2.8_HSM' must NOT be mistaken for the aperture."""
    assert parse_aperture(
        "2026-01-29__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM__1_1__F11"
    ) == 11.0
    assert parse_aperture(
        "newer-rig/2026-05-13_230021__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM_+_6T__f_5.6"
    ) == 5.6


def test_parse_aperture_missing():
    assert parse_aperture("nope") is None
    assert parse_aperture("foo__bar") is None


def test_analytical_diopter_100_400_canon_500d_at_m_1():
    """100-400 + Canon 500D at M=1.0, slug f/5.6 — value computed in the
    2026-05-17 validation pass: ~4.51."""
    n_eff = analytical_diopter_effective_f(
        "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D",
        m_total=1.0, slug_f=5.6,
    )
    assert n_eff is not None
    assert math.isclose(n_eff, 4.51, rel_tol=0.01)


def test_analytical_diopter_sigma_150_5t_at_m_1_3():
    """Sigma 150 + 5T (1.5D) at M=1.3, slug f/11. n_ring = 11/2 = 5.5 (lens
    at native MFD m=1.0). f_d = 1000/1.5 = 666.7 mm. f_c = 150*666.7 /
    816.7 = 122.4. D = 150/5.5 = 27.27. n_inf_c = 122.4/27.27 = 4.49.
    n_eff = 4.49 × 2.3 = 10.33."""
    n_eff = analytical_diopter_effective_f(
        "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T",
        m_total=1.3, slug_f=11.0,
    )
    assert n_eff is not None
    assert math.isclose(n_eff, 10.33, rel_tol=0.02)


def test_analytical_diopter_stacked_5t_6t_sums_powers():
    """Stacked diopter powers add: + 5T + 6T = 1.5 + 2.9 = 4.4 D, not 1.5 alone."""
    single = analytical_diopter_effective_f(
        "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T",
        m_total=1.5, slug_f=11.0,
    )
    stacked = analytical_diopter_effective_f(
        "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T + 6T",
        m_total=1.5, slug_f=11.0,
    )
    # Stacked diopters have shorter combined focal length → lower n_inf,
    # but the (1 + M_total) factor multiplies. At fixed M, shorter f_c
    # gives lower n_eff. So stacked should be LOWER than single.
    assert stacked is not None and single is not None
    assert stacked < single


def test_analytical_diopter_returns_none_for_bare_lens():
    assert analytical_diopter_effective_f(
        "Sigma APO Macro 150mm F2.8 EX DG OS HSM",
        m_total=1.0, slug_f=11.0,
    ) is None


def test_analytical_diopter_returns_none_for_unknown_lens():
    assert analytical_diopter_effective_f(
        "Unknown Lens + 5T", m_total=1.0, slug_f=5.6,
    ) is None


def test_resolve_effective_aperture_priority():
    """CSV beats analytical beats slug."""
    csv_table = {
        ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T", "f_11"): 99.0,
    }
    csv_lookup = EffectiveApertureLookup(table=csv_table)

    # CSV hit → uses CSV value, source="csv"
    eff, src = resolve_effective_aperture(
        "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T", "f_11",
        m_total=1.3, slug_f=11.0, csv_lookup=csv_lookup,
    )
    assert eff == 99.0 and src == "csv"

    # CSV miss, has diopter → analytical
    eff, src = resolve_effective_aperture(
        "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 6T", "f_11",
        m_total=1.3, slug_f=11.0, csv_lookup=csv_lookup,
    )
    assert src == "analytical_diopter"
    assert eff is not None and 8.0 < eff < 13.0

    # CSV miss, no diopter → slug
    eff, src = resolve_effective_aperture(
        "Sigma APO Macro 150mm F2.8 EX DG OS HSM", "f_11",
        m_total=1.0, slug_f=11.0, csv_lookup=csv_lookup,
    )
    assert eff == 11.0 and src == "slug"

    # No slug_f and no CSV → missing
    eff, src = resolve_effective_aperture(
        "Anything", "f_11", m_total=1.0, slug_f=None,
        csv_lookup=csv_lookup,
    )
    assert eff is None and src == "missing"


def test_resolve_effective_aperture_analytical_can_be_disabled():
    eff, src = resolve_effective_aperture(
        "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 6T", "f_11",
        m_total=1.3, slug_f=11.0,
        use_analytical_diopter=False,
    )
    assert eff == 11.0 and src == "slug"


def test_effective_aperture_override_supersedes_slug():
    """When ``effective_aperture`` is passed, the slug-parsed value is ignored."""
    df = _synth_sweep(
        sweep_label="t__1_1__F8",  # slug says F8
        rail_step_mm=0.10, n_shots=25, peak_shot_idx=12,
        m=1.0, aperture_n_eff=11.0,  # but synth data was built with N_eff=11
    )
    no_override = calibrate_sweep(df)
    with_override = calibrate_sweep(df, effective_aperture=11.0)
    assert with_override.aperture_f == 11.0
    assert math.isclose(with_override.rail_step_mm, 0.10, rel_tol=0.05)
    # Without override, the formula uses N=8 → result is 8/11 of true.
    assert math.isclose(
        no_override.rail_step_mm / with_override.rail_step_mm, 8 / 11, rel_tol=0.05,
    )


def test_blur_um_quadrature_subtraction():
    # sqrt(13² - 5²) = 12
    assert math.isclose(blur_um_from_widening(13.0, 5.0), 12.0, rel_tol=1e-9)


def test_blur_um_no_widening_returns_none():
    assert blur_um_from_widening(5.0, 5.0) is None
    assert blur_um_from_widening(4.0, 5.0) is None


def test_defocus_inverts_blur_formula():
    # blur = δ × M / N_eff   →   δ = blur × N_eff / M
    # blur=10 µm, N_eff=8, M=1.0  →  δ = 80 µm
    assert math.isclose(defocus_um_from_blur(10.0, 8.0, 1.0), 80.0, rel_tol=1e-9)
    # blur=5 µm, N_eff=11, M=0.5  →  δ = 110 µm
    assert math.isclose(defocus_um_from_blur(5.0, 11.0, 0.5), 110.0, rel_tol=1e-9)


def test_fwhm_object_um_round_trip():
    fwhm_px = 20.0
    m = 1.0
    obj = fwhm_object_um(fwhm_px, m)
    # On Z7 (4.35 µm pitch), 20 px at 1:1 → 87 µm object space.
    assert math.isclose(obj, 20.0 * SENSOR_PITCH_UM_Z7 / 1.0, rel_tol=1e-9)


# --- synthetic-sweep integration tests ---


def _synth_sweep(
    *,
    sweep_label: str,
    rail_step_mm: float,
    n_shots: int,
    peak_shot_idx: int,
    m: float,
    aperture_n_eff: float,
    intrinsic_fwhm_um: float = SCRIBE_WIDTH_UM,
    tiles: list[tuple[int, int]] | None = None,
) -> pd.DataFrame:
    """Generate per_shot_per_tile rows for a defocus-only synthetic sweep.

    For each shot k and each tile, compute:
      δ_um = |k − peak| × rail_step_mm × 1000
      blur_um = δ_um × M / N_eff
      fwhm_obs_um = sqrt(intrinsic² + blur²)
      trough_fwhm_px = fwhm_obs_um × M / pitch
      lsf_peak_amp = intrinsic / fwhm_obs (max at peak, drops with defocus)
    """
    if tiles is None:
        tiles = [(0, 0)]
    rows: list[dict] = []
    for ix, iy in tiles:
        for k in range(n_shots):
            delta_um = abs(k - peak_shot_idx) * rail_step_mm * 1000.0
            blur_um = delta_um * m / aperture_n_eff
            fwhm_obs_um = math.sqrt(intrinsic_fwhm_um**2 + blur_um**2)
            trough_fwhm_px = fwhm_obs_um * m / SENSOR_PITCH_UM_Z7
            # lsf_peak_amp peaks at the in-focus shot. Simple inverse
            # model: amp = intrinsic_fwhm / fwhm_obs (= 1 at peak, < 1 elsewhere).
            lsf_amp = intrinsic_fwhm_um / fwhm_obs_um
            rows.append({
                "sweep": sweep_label,
                "tile_ix": ix,
                "tile_iy": iy,
                "shot_idx": k,
                "rail_position_mm": None,
                "tile_x_px": 4128,
                "tile_y_px": 2752,
                "lsf_roi_px": 1024,
                "maze_roi_px": 1024,
                "filesize_bytes": 100000,
                "on_target": True,
                "m": m,
                "m_source": "synth",
                "scribe_detected": True,
                "trough_fwhm_px": trough_fwhm_px,
                "lsf_peak_amp": lsf_amp,
                "lsf_mtf50_cy_per_px": 0.10,
                "maze_resolves": False,
                "maze_fft_amp": None,
            })
    return pd.DataFrame(rows)


def test_recovers_rail_step_at_1to1_f8():
    rail = 0.05  # 50 µm per step
    df = _synth_sweep(
        sweep_label="t__1_1__F8",
        rail_step_mm=rail,
        n_shots=25,
        peak_shot_idx=12,
        m=1.0,
        aperture_n_eff=8.0,
    )
    res = calibrate_sweep(df)
    assert res.confidence in {"publishable", "comparison_ok"}
    assert math.isclose(res.rail_step_mm, rail, rel_tol=0.05)


def test_recovers_rail_step_at_2to1_f11():
    # At 2:1 F11 the per-step blur is small relative to the 87 µm
    # intrinsic scribe; 0.02 mm/step would be below the widening
    # threshold. Use 0.05 mm/step — a plausible wide-bracket manual run.
    rail = 0.05
    df = _synth_sweep(
        sweep_label="t__2_1__F11",
        rail_step_mm=rail,
        n_shots=25,
        peak_shot_idx=12,
        m=2.0,
        aperture_n_eff=11.0,
    )
    res = calibrate_sweep(df)
    assert res.confidence in {"publishable", "comparison_ok"}
    assert math.isclose(res.rail_step_mm, rail, rel_tol=0.05)


def test_aperture_invariance():
    """Same physical rail bracket at different N should yield the same rail step."""
    # Need enough per-step blur at F22 to clear the 1.10 widening threshold —
    # at F22 m=1 this means rail ≳ 0.075 mm.
    rail = 0.10
    args = dict(rail_step_mm=rail, n_shots=25, peak_shot_idx=12, m=1.0)
    f8 = calibrate_sweep(_synth_sweep(sweep_label="t__1_1__F8", aperture_n_eff=8.0, **args))
    f11 = calibrate_sweep(_synth_sweep(sweep_label="t__1_1__F11", aperture_n_eff=11.0, **args))
    f22 = calibrate_sweep(_synth_sweep(sweep_label="t__1_1__F22", aperture_n_eff=22.0, **args))
    assert math.isclose(f8.rail_step_mm, rail, rel_tol=0.05)
    assert math.isclose(f11.rail_step_mm, rail, rel_tol=0.05)
    assert math.isclose(f22.rail_step_mm, rail, rel_tol=0.05)


def test_multi_tile_pooling():
    rail = 0.05
    tiles = [(-3, 0), (0, 0), (3, 0), (0, -2), (0, 2)]
    df = _synth_sweep(
        sweep_label="t__1_1__F8",
        rail_step_mm=rail,
        n_shots=25,
        peak_shot_idx=12,
        m=1.0,
        aperture_n_eff=8.0,
        tiles=tiles,
    )
    res = calibrate_sweep(df)
    assert res.n_tiles_used == len(tiles)
    assert res.n_estimates > 30  # ~6 K-values per side × 2 × 5 tiles ≈ 60
    assert res.confidence == "publishable"  # clean synthetic should be high


def test_insufficient_when_no_defocus():
    # n_shots=3, all near peak — every shot fails the min_dshot filter
    df = _synth_sweep(
        sweep_label="t__1_1__F8",
        rail_step_mm=0.05,
        n_shots=3,
        peak_shot_idx=1,
        m=1.0,
        aperture_n_eff=8.0,
    )
    res = calibrate_sweep(df, min_dshot=3)
    assert res.confidence == "insufficient"
    assert res.n_estimates == 0
    assert math.isnan(res.rail_step_mm)


def test_failed_no_aperture_in_label():
    df = _synth_sweep(
        sweep_label="no_aperture_here",
        rail_step_mm=0.05, n_shots=25, peak_shot_idx=12,
        m=1.0, aperture_n_eff=8.0,
    )
    res = calibrate_sweep(df)
    assert res.confidence == "failed"
    assert "aperture" in res.note


def test_failed_non_unique_m():
    df = _synth_sweep(
        sweep_label="t__F8", rail_step_mm=0.05, n_shots=25,
        peak_shot_idx=12, m=1.0, aperture_n_eff=8.0,
    )
    # Inject a second m value
    df.loc[0, "m"] = 0.5
    res = calibrate_sweep(df)
    assert res.confidence == "failed"
    assert "non-unique m" in res.note


def test_rejects_off_target_tiles():
    df = _synth_sweep(
        sweep_label="t__1_1__F8", rail_step_mm=0.05, n_shots=25,
        peak_shot_idx=12, m=1.0, aperture_n_eff=8.0,
    )
    df["on_target"] = False
    res = calibrate_sweep(df)
    assert res.confidence == "insufficient"
    assert res.n_tiles_used == 0


def test_skips_rows_where_lsf_was_m_aware_filtered():
    """If lsf_peak_amp is NaN (M-aware trough-width gate fired), skip the row."""
    df = _synth_sweep(
        sweep_label="t__1_1__F8", rail_step_mm=0.05, n_shots=25,
        peak_shot_idx=12, m=1.0, aperture_n_eff=8.0,
    )
    # NaN out half the rows — should still work on the rest.
    df.loc[df["shot_idx"] < 13, "lsf_peak_amp"] = float("nan")
    res = calibrate_sweep(df)
    # Defocused shots above peak still qualify (peak_idx will move to 13);
    # estimate is positively biased because the new "intrinsic" baseline
    # (shot 13) carries a small residual blur from the synthetic peak at
    # shot 12 — algorithm under-counts that as scribe width, over-counts
    # the rest as defocus. ~11 % bias at this offset; document with tol.
    assert res.n_estimates > 0
    assert math.isclose(res.rail_step_mm, 0.05, rel_tol=0.15)


def test_returns_dataclass_with_expected_fields():
    df = _synth_sweep(
        sweep_label="t__1_1__F8", rail_step_mm=0.05, n_shots=25,
        peak_shot_idx=12, m=1.0, aperture_n_eff=8.0,
    )
    res = calibrate_sweep(df)
    assert isinstance(res, CalibrationResult)
    assert res.aperture_f == 8.0
    assert res.m == 1.0
    assert res.uncertainty_mm >= 0


# --- v2 pooled calibration ---


def test_group_key_strips_aperture():
    assert group_key("older-2026-01-29/x__AIS_287318__1_1__F8") == \
        "older-2026-01-29/x__AIS_287318__1_1"
    assert group_key("foo__1_2.60__F5.6") == "foo__1_2.60"
    assert group_key("foo__120.0_mm__F11") == "foo__120.0_mm"
    # Newer-rig lowercase / underscore form
    assert group_key("newer-rig/2026-05-13__Sigma__f_5.6") == \
        "newer-rig/2026-05-13__Sigma"
    assert group_key("newer-rig/foo__f_11") == "newer-rig/foo"
    # No-op when no aperture suffix
    assert group_key("no_aperture") == "no_aperture"


def _multi_aperture_group(
    *,
    group_prefix: str,
    rail_step_mm: float,
    n_shots: int,
    peak_shot_idx: int,
    m: float,
    apertures: list[float],
    tiles: list[tuple[int, int]] | None = None,
) -> pd.DataFrame:
    """Generate a per_shot_per_tile DataFrame with multiple aperture sweeps."""
    frames = []
    for ap in apertures:
        label = f"{group_prefix}__F{ap}"
        frames.append(_synth_sweep(
            sweep_label=label,
            rail_step_mm=rail_step_mm,
            n_shots=n_shots,
            peak_shot_idx=peak_shot_idx,
            m=m,
            aperture_n_eff=ap,
            tiles=tiles,
        ))
    return pd.concat(frames, ignore_index=True)


def test_pooled_recovers_rail_step_with_consistent_apertures():
    # rail=0.10 mm — wide enough that all five apertures clear the
    # widening threshold even at F22 (smallest per-step blur).
    rail = 0.10
    df = _multi_aperture_group(
        group_prefix="t__1_1",
        rail_step_mm=rail,
        n_shots=25,
        peak_shot_idx=12,
        m=1.0,
        apertures=[5.6, 8.0, 11.0, 16.0, 22.0],
    )
    res = calibrate_group(df)
    assert isinstance(res, PooledCalibrationResult)
    assert res.n_apertures == 5
    assert res.n_apertures_valid == 5
    assert math.isclose(res.rail_step_mm, rail, rel_tol=0.05)
    # Clean synthetic data → tight inter-aperture agreement → high.
    assert res.confidence in {"publishable", "comparison_ok"}


def test_pooled_flags_inter_aperture_disagreement():
    """Synthesise two apertures with mismatched 'true' rail steps —
    e.g. simulating an uncorrected aperture-convention bump."""
    frame_a = _synth_sweep(
        sweep_label="t__1_1__F8", rail_step_mm=0.05, n_shots=25,
        peak_shot_idx=12, m=1.0, aperture_n_eff=8.0,
    )
    frame_b = _synth_sweep(
        sweep_label="t__1_1__F11", rail_step_mm=0.10, n_shots=25,
        peak_shot_idx=12, m=1.0, aperture_n_eff=11.0,
    )
    df = pd.concat([frame_a, frame_b], ignore_index=True)
    res = calibrate_group(df)
    assert res.n_apertures_valid == 2
    # Inter-aperture spread should be large.
    assert res.inter_aperture_spread > 0.2
    assert res.confidence in {"sanity_only", "unusable"}


def test_pooled_falls_back_to_single_valid_aperture():
    """If only one aperture produces a valid estimate, confidence is low."""
    valid = _synth_sweep(
        sweep_label="t__1_1__F8", rail_step_mm=0.10, n_shots=25,
        peak_shot_idx=12, m=1.0, aperture_n_eff=8.0,
    )
    # F22 with tiny rail step → no widening signal → NaN estimate.
    no_signal = _synth_sweep(
        sweep_label="t__1_1__F22", rail_step_mm=0.10, n_shots=25,
        peak_shot_idx=12, m=1.0, aperture_n_eff=22.0,
    )
    no_signal.loc[:, "trough_fwhm_px"] = 20.0  # flat → no widening
    df = pd.concat([valid, no_signal], ignore_index=True)
    res = calibrate_group(df)
    assert res.n_apertures_valid == 1
    assert res.confidence == "sanity_only"
    assert "only 1" in res.note


def test_suspicious_peak_downgrades_confidence():
    """A noise-minimum fwhm (well below sweep median) should downgrade confidence.

    Synthesizes a sweep where the algorithm's argmin(fwhm) picks an
    anomalous narrow value — simulating the F5.6 false-confidence
    failure mode observed on real newer-rig data. With tight per-shot
    blur the per-estimate clustering would normally read "high"; the
    suspicious-peak guard should drop it to "medium".
    """
    df = _synth_sweep(
        sweep_label="t__1_1__F5.6", rail_step_mm=0.10, n_shots=25,
        peak_shot_idx=12, m=1.0, aperture_n_eff=5.6,
    )
    # Inject an anomalously narrow fwhm at shot 20 (one defocused shot
    # somewhere, much narrower than the synthetic intrinsic of 87 µm).
    # Convert to trough_fwhm_px: 30 µm × 1.0 / 4.35 ≈ 6.9 px.
    df.loc[(df["tile_ix"] == 0) & (df["tile_iy"] == 0) & (df["shot_idx"] == 20),
           "trough_fwhm_px"] = 6.9
    res = calibrate_sweep(df)
    assert "suspicious peak" in res.note
    assert res.confidence in {"comparison_ok", "sanity_only"}


def test_pooled_failed_when_all_apertures_fail():
    df = _synth_sweep(
        sweep_label="t__1_1__F8", rail_step_mm=0.05, n_shots=25,
        peak_shot_idx=12, m=1.0, aperture_n_eff=8.0,
    )
    df.loc[:, "trough_fwhm_px"] = 20.0  # no widening → NaN estimate
    res = calibrate_group(df)
    assert res.confidence == "insufficient"
    assert res.n_apertures_valid == 0
    assert math.isnan(res.rail_step_mm)
