# Reshoot / new-lens plan — 2026-05

Source: rail-coverage/output/reshoot.html (49 of 545 scenarios across 23 of 65 lenses).

- **23** existing lens-attachment combinations to reshoot
- **10** new combinations to add (down from 17 after dropping closely-spaced extension tubes)
- **33** total entries (down from 40)

Order within each group: shortest subject distance first (heuristic by focal length × magnification). Magnifications are observed where the lens has been shot before; otherwise estimated from focal length + extension-tube length, marked `(est.)`.

Status legend: `reshoot` = present in current report and flagged as truncated; `reshoot (F16-only)` = only F16 is truncated, optional to skip if you accept an incomplete F16 sweep; `NEW` = new combination to test.

**Magnification estimate notes.** The `(est.)` values use a thin-lens magnification model corrected per lens for two real-world effects:

1. **Native magnification at MFD.** Total magnification with an extension tube is `m_native + L_tube / F_eff`, *not* `1 + L_tube / F_nominal`. The "+1" form only holds when the lens already reaches 1:1 internally; sub-1:1 lenses (24-120 max ≈ 0.39, Viltrox 85 max ≈ 0.13) need the per-lens native value substituted.

2. **F_eff at close focus.** Internal-focus macro designs shorten their focal length substantially at close focus. The Nikkor Z MC 105 mm f/2.8 VR S drops to ~49 mm at 1:1 (per photomacrography.net optical-bench measurements). General-purpose lenses with "suppressed breathing" stay near nominal — the Z 24-120 measured at 3% breathing through its full focus range stays close to its zoom-position focal length; the Viltrox 85 mm f/2 EVO is described as "comparatively low" focus breathing and is treated similarly.

Per-lens parameters used here:

| Lens | F_eff at close focus | m_native at MFD |
|---|---|---|
| Z MC 105 mm f/2.8 VR S | ~49 mm at 1:1 | 1.0 |
| Z 24-120 mm f/4 S (at 120 mm) | ~120 mm | 0.39 |
| Viltrox 85 mm f/2 EVO | ~85 mm | 0.13 |

**24-120 estimates use observation-fit, not thin-lens.** Past shots
of this lens at 120 mm + 10/16 mm tubes (`2026-02-18` test set)
landed at 0.54 and 0.63 magnification respectively — substantially
higher than the thin-lens model `m_native + L_tube / F_eff` would
predict. The empirical slope at 120 mm is ≈ 0.015 per mm of tube
(roughly 1.8× the thin-lens slope), most likely because the tube
lets the lens focus past its own MFD, compounding both effects.
The 35 / 45 / 61 mm + 120 mm entries above are extrapolated from
that two-point fit and should be treated as upper-bound estimates;
revise to observed values once each combo has actually been shot.

The live SamplePlan computes rail step from whatever magnification
you enter at the prompt; over-estimating m → over-sampling the
bell, which is the safe error direction.

---

## Group 1 — body L-bracket (Z lenses, except 100-400)

| # | Lens + attachment | Mag | Status |
|---|---|---|---|
| 1 | NIKKOR Z MC 105mm f/2.8 VR S + 61mm extension | 2.25:1 (est., F_eff=49) | NEW |
| 2 | NIKKOR Z MC 105mm f/2.8 VR S + 6T + 5T | 1.6:1 | reshoot |
| 3 | NIKKOR Z MC 105mm f/2.8 VR S + 5T + 6T | 1.6:1 | reshoot |
| 4 | NIKKOR Z MC 105mm f/2.8 VR S + 45mm extension | 1.92:1 (est., F_eff=49) | NEW |
| 5 | NIKKOR Z MC 105mm f/2.8 VR S + 6T | 1.4:1 | reshoot (F16-only) |
| 6 | NIKKOR Z MC 105mm f/2.8 VR S + 35mm extension | 1.71:1 (est., F_eff=49) | NEW |
| 7 | NIKKOR Z 24-120mm f/4 S + 61mm extension | 1.31:1 (est., 120mm extrap.) | NEW |
| 8 | Viltrox 85mm f/2 EVO + 61mm extension | 1:1.18 (est.) | NEW |
| 9 | NIKKOR Z 24-120mm f/4 S + 45mm extension | 1.07:1 (est., 120mm extrap.) | NEW |
| 10 | NIKKOR Z 24-120mm f/4 S + 35mm extension | 1:1.09 (est., 120mm extrap.) | NEW |
| 11 | Viltrox 85mm f/2 EVO + 45mm extension | 1:1.51 (est.) | NEW |
| 12 | NIKKOR Z 24-120mm f/4 S + 10mm extension | 1:1.84 | reshoot |
| 13 | Viltrox 85mm f/2 EVO + 26mm extension | 1:2.27 (est.) | NEW |
| 14 | NIKKOR Z 24-120mm f/4 S | 1:2.6 | reshoot |

L-bracket subtotal: **14 entries** (5 reshoot, 9 new)

## Group 2 — separate tripod foot (F-mount via FTZ + 100-400)

| # | Lens + attachment | Mag | Status |
|---|---|---|---|
| 15 | Nikon Micro-Nikkor 55mm f/2.8 AIS — serial 287318 | 1:1 | reshoot |
| 16 | Nikon Micro-Nikkor 55mm f/2.8 AIS — serial 537016 | 1:1 | reshoot (F16-only) |
| 17 | Sigma Macro 105mm F2.8 EX DG OS HSM + 6T + 5T | 1.7:1 | reshoot (F16-only) |
| 18 | Sigma Macro 105mm F2.8 EX DG OS HSM + 5T + 6T | 1.7:1 | reshoot |
| 19 | Sigma APO Macro 150mm F2.8 EX DG OS HSM + 6T + 5T | 1.8:1 | reshoot |
| 20 | Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T + 6T | 1.8:1 | reshoot |
| 21 | Sigma APO Macro 150mm F2.8 EX DG OS HSM + 6T | 1.6:1 | reshoot |
| 22 | Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T | 1.3:1 | reshoot |
| 23 | Sigma APO Macro 150mm F2.8 EX DG OS HSM | 1:1 | reshoot (F16-only) |
| 24 | Nikon AF Micro-Nikkor 200mm f/4D IF-ED + 6T + 5T | 2:1 | reshoot |
| 25 | Nikon AF Zoom-Micro Nikkor 70-180mm f/4.5-5.6D ED + 5T + 6T | 1.14:1 | reshoot |
| 26 | Nikon AF Zoom-Micro Nikkor 70-180mm f/4.5-5.6D ED | 1:1.33 | reshoot |
| 27 | NIKKOR Z 100-400mm f/4.5-5.6 VR S + Nikon 5T | 1.27:1 | reshoot (F16-only) |
| 28 | NIKKOR Z 100-400mm f/4.5-5.6 VR S + Canon 500D | 1.07:1 | reshoot |
| 29 | NIKKOR Z 100-400mm f/4.5-5.6 VR S + Nikon 6T | 1:1.19 | reshoot |
| 30 | NIKKOR Z 100-400mm f/4.5-5.6 VR S + 61mm extension | 1:1.9 (est.) | NEW |
| 31 | NIKKOR Z 100-400mm f/4.5-5.6 VR S + 35mm extension | 1:2.1 (est.) | NEW |
| 32 | NIKKOR Z 100-400mm f/4.5-5.6 VR S | 1:2.6 | reshoot |
| 33 | NIKKOR Z 100-400mm f/4.5-5.6 VR S Z TC-2.0x | 1:1.29 | reshoot (F16-only) |

Separate-mount subtotal: **19 entries** (17 reshoot, 2 new)

## What was dropped from the 40-entry version

| Dropped | Reason |
|---|---|
| MC 105 + 51mm extension | Sits between 45mm and 61mm; magnification gap is small. The kept MC 105 + 6T+5T at 1.6:1 already covers the 1.5–1.6 zone. |
| Viltrox 85 + 35mm | Between 26mm (1:3.27) and 45mm (1:1.89); interpolation. |
| Viltrox 85 + 51mm | Between 45mm (1:1.89) and 61mm (1:1.39); interpolation. |
| 24-120 + 51mm | Between 45mm and 61mm; close to existing close-up filter coverage at 1.3:1. |
| 100-400 + 45mm extension | Between 35mm and 61mm; on a 400mm focal length the magnification difference is barely measurable. |
| 100-400 + 51mm extension | Same reason. |
| 70-180 + 5T+6T (norm) | Norm-vs-reversed analysis showed sub-2 % corner-sharpness difference; the no-norm variant has 4 truncated apertures (worth reshooting), the norm variant has 1 (good enough as-is). |

## F16-only entries (6 of 23 reshoots) — optional to skip

For these six configurations, F16 is the **only** truncated aperture
in the rail-coverage analysis; F4-F11 sweeps are all complete with
on-target peaks. If you accept an incomplete F16 (which the user has
called the least important aperture), these can be dropped from the
reshoot session, taking the plan from 33 to **27 entries**:

- #5  MC 105 + 6T (1.4:1)
- #16 55 AIS 537016 (1:1)
- #17 Sigma Macro 105 + 6T+5T (1.7:1)
- #23 Sigma 150 (native, 1:1)
- #27 100-400 + Nikon 5T (1.27:1)
- #33 100-400 + TC-2.0x (1:1.29)

## Stacking-order (5T+6T vs 6T+5T) — kept both intentionally

The data shows the corner-sharpness ratio differs by lens (3-7% on Sigma 150 favouring 5T-toward-lens; 1-3.5% on Nikon Z MC 105 / AF 70-180 / AF 200 favouring 6T-toward-lens). Both orderings are kept for these lenses so the reshoot session can validate the same effect with the new equipment / setup.

## Notes on the magnification estimates

- **Observed** values come from the 2026-01-29 / 2026-02-18 sessions and are exact for the configuration that was tested.
- **Estimated** values for extension-tube combinations use `M ≈ M_native + ext/focal`, calibrated against the 24-120 + 10mm and + 26mm observed points. The 24-120 estimates extrapolate linearly from those two observations; Viltrox 85 estimates assume `M ≈ ext / 85` (its native MFD is far enough that the native contribution is negligible).
- **The 100-400 + extension-tube** estimates assume the user shoots toward MFD (where the lens already does ~1:2.6 native). At infinity focus, magnification with these tubes would be 6-10× lower.
