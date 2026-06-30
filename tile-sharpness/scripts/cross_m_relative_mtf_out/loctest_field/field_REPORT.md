# Location-aware (field-position) sharpness — subset

> LOCATION-AWARE (field-position) sharpness — companion to the cross-M relative
> glass-MTF ranking. Per-patch sharpness is the RELATIVE, FIXED-SENSOR-FREQUENCY
> amplitude at f_px=0.1 cy/px (same axis + fence as the ranking; NOT absolute
> MTF, NOT subject resolution). Position is DISTANCE + ANGLE from the FRAME CENTRE;
> field_height = dist / frame half-diagonal (0=centre, 1=corner).
> COVERAGE IS M-DEPENDENT + INCOMPLETE: high-M patches cluster (small field span,
> see field_coverage.field_supported); low-M wafer covers only PART of the frame so
> the true corners may be unsampled. Field maps are meaningful ONLY where patches
> exist — do NOT extrapolate into empty zones; trust configs with the richest
> coverage. Subset only; production-ready for the full reprocess.

## Field coverage (where patches actually exist)

| config | n | fh_min | fh_max | fh_span | az_span° | zones | supported |
|---|---|---|---|---|---|---|---|
| Z105_1_1_F8 | 92 | 0.07 | 0.88 | 0.81 | 343 | centre;mid;corner | True |
| V55f28287318_1_1_F8 | 85 | 0.07 | 0.86 | 0.79 | 340 | centre;mid;corner | True |
| S150_1_1_F8 | 83 | 0.05 | 0.83 | 0.78 | 339 | centre;mid;corner | True |
| AF60_1_1_F8 | 85 | 0.07 | 0.85 | 0.78 | 340 | centre;mid;corner | True |
| Z100400+MCON-35_1_1.16_F8 | 69 | 0.09 | 0.84 | 0.76 | 338 | centre;mid;corner | True |
| V55f35209088_1_1_F8 | 93 | 0.06 | 0.81 | 0.75 | 344 | centre;mid;corner | True |
| S105_1_1_F8 | 85 | 0.06 | 0.81 | 0.75 | 340 | centre;mid;corner | True |
| AF200_1_1_F8 | 92 | 0.07 | 0.82 | 0.75 | 344 | centre;mid;corner | True |
| AF200+6T_1.7_1_F8 | 28 | 0.05 | 0.75 | 0.69 | 317 | centre;mid;corner | True |
| AF200+5T+6T_2_1_F8 | 16 | 0.06 | 0.70 | 0.63 | 302 | centre;mid | True |

## Radial falloff (corner/centre relative-amp ratio; <1 softens to corner)

| config | corner/centre | mid/centre | supported |
|---|---|---|---|
| AF200+5T+6T_2_1_F8 |  | 0.949 | False |
| AF200+6T_1.7_1_F8 | 0.789 | 0.934 | True |
| AF200_1_1_F8 | 1.025 | 1.086 | True |
| AF60_1_1_F8 | 1.036 | 1.052 | True |
| S105_1_1_F8 | 1.043 | 1.041 | True |
| S150_1_1_F8 | 0.884 | 0.940 | True |
| V55f28287318_1_1_F8 | 0.829 | 0.969 | True |
| V55f35209088_1_1_F8 | 0.607 | 0.750 | True |
| Z100400+MCON-35_1_1.16_F8 | 0.841 | 0.888 | True |
| Z105_1_1_F8 | 1.036 | 1.048 | True |

## Azimuthal asymmetry / decentering (lr>0 right sharper; tb>0 top sharper)

| config | n_band | lr | tb | mag | dir° | supported |
|---|---|---|---|---|---|---|
| AF200+5T+6T_2_1_F8 | 10 | -0.025 | -0.005 | 0.026 | -169 | True |
| AF200+6T_1.7_1_F8 | 20 | -0.239 | +0.022 | 0.240 | +175 | True |
| AF200_1_1_F8 | 69 | +0.047 | -0.122 | 0.131 | -69 | True |
| AF60_1_1_F8 | 65 | +0.033 | -0.125 | 0.129 | -75 | True |
| S105_1_1_F8 | 66 | -0.011 | -0.098 | 0.099 | -96 | True |
| S150_1_1_F8 | 59 | +0.026 | -0.105 | 0.108 | -76 | True |
| V55f28287318_1_1_F8 | 63 | +0.110 | -0.069 | 0.130 | -32 | True |
| V55f35209088_1_1_F8 | 68 | +0.113 | -0.164 | 0.199 | -55 | True |
| Z100400+MCON-35_1_1.16_F8 | 51 | -0.010 | -0.098 | 0.098 | -96 | True |
| Z105_1_1_F8 | 71 | +0.002 | -0.141 | 0.141 | -89 | True |

## Astigmatism index (mean log(sag/tan); >0 sagittal sharper)

| config | n_band | astig_index | supported |
|---|---|---|---|
| AF200+5T+6T_2_1_F8 | 10 | -0.128 | True |
| AF200+6T_1.7_1_F8 | 20 | -0.109 | True |
| AF200_1_1_F8 | 69 | +0.049 | True |
| AF60_1_1_F8 | 65 | -0.099 | True |
| S105_1_1_F8 | 66 | -0.073 | True |
| S150_1_1_F8 | 59 | -0.128 | True |
| V55f28287318_1_1_F8 | 63 | -0.151 | True |
| V55f35209088_1_1_F8 | 68 | -0.199 | True |
| Z100400+MCON-35_1_1.16_F8 | 51 | -0.016 | True |
| Z105_1_1_F8 | 71 | -0.016 | True |

## Field-resolved relative ranking (top configs per zone)

- **centre** (10 configs): S150_1_1_F8, Z105_1_1_F8, V55f28287318_1_1_F8, S105_1_1_F8, AF60_1_1_F8
- **mid** (10 configs): Z105_1_1_F8, S150_1_1_F8, AF60_1_1_F8, S105_1_1_F8, AF200_1_1_F8
- **corner** (8 configs): Z105_1_1_F8, AF60_1_1_F8, S105_1_1_F8, AF200_1_1_F8, V55f28287318_1_1_F8
