# Cross-magnification RELATIVE glass-MTF ranking

> CROSS-MAGNIFICATION RELATIVE GLASS-MTF RANKING
> RELATIVE, FIXED-SENSOR-FREQUENCY ranking: 'which lens has the higher MTF
> at this PIXEL frequency'. It is NOT an absolute MTF and NOT a
> subject-resolution ranking. It deliberately refuses to credit empty
> magnification; for 'resolves more subject detail' use within-M periodic
> ranking + diffraction ceiling + tolerance ratios (the SHARPNESS_METRICS / §L
> references), NOT this.
> Trustworthy ONLY at f_px = 0.08-0.15 cy/px (read here at 0.1). M~2 configs
> are reached via a transitive bridge (validated robust). Scores are relative
> (zero-mean gauge), not tied to the diffraction ceiling.
> Higher score / lower rank = sharper. See cross_m_relative_mtf.py docstring.

## Gates (self-check on this input set)

- f_px = **0.1** cy/px (in trustworthy window (0.08, 0.15): True)
- de-confound corr(M, score) = **-0.677** (want <= 0.1; OK)
- empty-magnification floats: **none** (OK)
- graph: **1 component(s)**, 29679 edges, residual 0.273; under-bridged configs: none
- split-half repeatability: Spearman **+0.547** (n=38)
- M~2 transitive-bridge jackknife worst shift: **0.074** (ROBUST)
- §L known orders (lower rank = sharper): modern-macro 7.0 < vintage55/60 11.0 < diopter-tail 35.5
- ALL GATES PASS: **True**

## f_px window sweep

| f_px | nodes | edges | comp | resid | corr(M,score) | floats | in-window |
|---|---|---|---|---|---|---|---|
| 0.08 | 38 | 29679 | 1 | 0.315 | -0.762 | none | True |
| 0.1 | 38 | 29679 | 1 | 0.273 | -0.677 | none | True |
| 0.12 | 38 | 29679 | 1 | 0.278 | -0.582 | none | True |
| 0.15 | 35 | 28403 | 1 | 0.283 | -0.366 | none | True |
| 0.18 | 32 | 27139 | 1 | 0.312 | +0.231 | S150+TC-1401_1.4_1_F8 | False |
| 0.2 | 30 | 25102 | 1 | 0.368 | -0.022 | none | False |
| 0.25 | 26 | 21429 | 1 | 0.358 | +0.19 | none | False |

## Primary ranking @ f_px=0.1 (higher score = sharper; sigma = bootstrap)

| rank | config | score | M | sigma | n_cells |
|---|---|---|---|---|---|
| 1 | Z105_1_1_F11 | +0.706 | 1.01 | 0.011 | 2170 |
| 2 | S105_1_1_F11 | +0.542 | 1.06 | 0.013 | 2074 |
| 3 | Z105_1_1_F8 | +0.535 | 1.00 | 0.026 | 1805 |
| 4 | S150_1_1_F11 | +0.518 | 1.03 | 0.010 | 1666 |
| 5 | Z105_1_1_F5.6 | +0.512 | 1.00 | 0.012 | 2170 |
| 6 | S150_1_1_F8 | +0.460 | 1.03 | 0.010 | 1666 |
| 7 | AF200_1_1_F11 | +0.442 | 1.00 | 0.024 | 1774 |
| 8 | S105+TC-1401_1_1_F8 | +0.359 | 1.01 | 0.018 | 1868 |
| 9 | AF60_1_1_F8 | +0.345 | 1.00 | 0.018 | 1894 |
| 10 | S105_1_1_F8 | +0.326 | 1.05 | 0.011 | 2074 |
| 11 | V55f28537016_1_1_F8 | +0.314 | 0.99 | 0.019 | 1894 |
| 12 | V55f28287318_1_1_F8 | +0.279 | 1.00 | 0.018 | 1894 |
| 13 | AF200_1_1_F8 | +0.258 | 1.00 | 0.011 | 2141 |
| 14 | Z70180_1_1.33_F8 | +0.181 | 0.75 | 0.054 | 1560 |
| 15 | S105+5T_1.27_1_F8 | +0.094 | 1.26 | 0.026 | 555 |
| 16 | Z105+6T_1.4_1_F8 | +0.086 | 1.37 | 0.016 | 1422 |
| 17 | S105_1_1_F5.6 | +0.084 | 1.05 | 0.014 | 2074 |
| 18 | S150+TC-1401_1_1_F8 | +0.050 | 1.00 | 0.020 | 1933 |
| 19 | Z70180+5T+6T_1.14_1_F8 | +0.022 | 1.13 | 0.027 | 1536 |
| 20 | S150_1_1_F5.6 | +0.021 | 1.02 | 0.015 | 1703 |
| 21 | Z70180+6T_1_1_F8 | +0.004 | 1.00 | 0.024 | 1774 |
| 22 | AF200+Kenko14_1_1_F8 | -0.034 | 1.00 | 0.010 | 2170 |
| 23 | S105+6T_1.5_1_F8 | -0.100 | 1.46 | 0.020 | 1184 |
| 24 | S105+TC-2001_1_1_F8.5 | -0.116 | 0.99 | 0.008 | 2162 |
| 25 | S105+TC-1401_1.4_1_F8 | -0.122 | 1.48 | 0.016 | 1158 |
| 26 | Z105+5T+6T_1.6_1_F8 | -0.123 | 1.54 | 0.022 | 999 |
| 27 | V55f35209088_1_1_F8 | -0.133 | 0.99 | 0.025 | 2179 |
| 28 | V55f35258263_1_1_F8 | -0.153 | 1.00 | 0.014 | 2170 |
| 29 | S150+TC-1401_1.4_1_F8 | -0.157 | 1.45 | 0.014 | 1096 |
| 30 | Z100400+C500D_1.07_1_F8 | -0.159 | 0.90 | 0.014 | 2073 |
| 31 | S105+TC-2001_2_1_F11 | -0.269 | 2.09 | 0.028 | 129 |
| 32 | S150+TC-2001_1_1_F8.5 | -0.339 | 1.00 | 0.009 | 2185 |
| 33 | S150+TC-2001_2_1_F11 | -0.345 | 2.03 | 0.067 | 651 |
| 34 | S105+5T+6T_1.7_1_F8 | -0.457 | 1.64 | 0.035 | 289 |
| 35 | Z100400+MCON-35_1_1.16_F8 | -0.686 | 1.12 | 0.021 | 1680 |
| 36 | S150+5T+6T_1.8_1_F8 | -0.722 | 1.80 | 0.034 | 245 |
| 37 | AF200+6T_1.7_1_F8 | -0.879 | 1.72 | 0.023 | 835 |
| 38 | AF200+5T+6T_2_1_F8 | -1.345 | 2.06 | 0.029 | 506 |

## P2 through-focus corroborator (defocus response)

- de-confound self-check: corr(N_eff, P2) = **-0.081** (want |.| <= 0.3; OK); corr(M, P2) = -0.092 (n=37 configs)
- P2 is a PER-CONFIG defocus-based corroborator on a different physical principle (focus-stack response width, no spectrum): its self-check is corr(N_eff)~0, not the f_px window the spectral estimators fence.

## Cross-estimator agreement (Spearman; higher-aligned = sharper)

| estimator | P1_fpx0.1 | P1_fpx0.12 | P1_fpx0.15 | P31_padedge | P32_decon | P2_psffoc |
|---|---|---|---|---|---|---|
| P1_fpx0.1 | 1.0 | 0.945 | 0.945 | 0.524 | 0.728 | 0.408 |
| P1_fpx0.12 | 0.945 | 1.0 | 0.957 | 0.551 | 0.774 | 0.463 |
| P1_fpx0.15 | 0.945 | 0.957 | 1.0 | 0.787 | 0.845 | 0.547 |
| P31_padedge | 0.524 | 0.551 | 0.787 | 1.0 | 0.819 | 0.515 |
| P32_decon | 0.728 | 0.774 | 0.845 | 0.819 | 1.0 | 0.667 |
| P2_psffoc | 0.408 | 0.463 | 0.547 | 0.515 | 0.667 | 1.0 |

*Independent physical principles (same-patch spectral ratio P1, pad-edge averaged-ESF P3.1, relative deconvolution P3.2, through-focus defocus response P2) mutually positive = the cross-M relative signal is real, not a single-method artifact.*

## Consensus cross-M relative ranking (rank-average; rank_std = disagreement = uncertainty)

| consensus_rank | config | mean_rank | rank_std | n_estimators |
|---|---|---|---|---|
| 1 | Z105_1_1_F5.6 | 3.80 | 0.75 | 5 |
| 2 | Z105_1_1_F8 | 5.20 | 2.32 | 5 |
| 3 | Z105_1_1_F11 | 6.20 | 9.43 | 5 |
| 4 | AF200_1_1_F11 | 7.00 | 3.03 | 5 |
| 5 | S150_1_1_F11 | 9.00 | 6.03 | 5 |
| 6 | S150_1_1_F8 | 9.00 | 2.37 | 5 |
| 7 | S105_1_1_F11 | 9.60 | 10.78 | 5 |
| 8 | S105+TC-1401_1_1_F8 | 10.00 | 2.28 | 5 |
| 9 | S105+5T_1.27_1_F8 | 10.00 | 5.55 | 5 |
| 10 | AF200_1_1_F8 | 10.40 | 5.50 | 5 |
| 11 | S105_1_1_F8 | 11.00 | 3.69 | 5 |
| 12 | AF60_1_1_F8 | 13.20 | 7.28 | 5 |
| 13 | S105_1_1_F5.6 | 15.00 | 1.79 | 5 |
| 14 | AF200+Kenko14_1_1_F8 | 15.00 | 7.29 | 5 |
| 15 | S150_1_1_F5.6 | 15.60 | 6.09 | 5 |
| 16 | V55f28287318_1_1_F8 | 16.80 | 4.49 | 5 |
| 17 | S105+TC-2001_2_1_F11 | 17.00 | 10.51 | 4 |
| 18 | Z105+6T_1.4_1_F8 | 17.25 | 2.28 | 4 |
| 19 | V55f28537016_1_1_F8 | 17.80 | 5.98 | 5 |
| 20 | S150+TC-1401_1.4_1_F8 | 18.25 | 12.19 | 4 |
| 21 | S150+TC-1401_1_1_F8 | 18.60 | 1.96 | 5 |
| 22 | S105+TC-1401_1.4_1_F8 | 19.00 | 6.16 | 4 |
| 23 | Z70180_1_1.33_F8 | 21.00 | 5.55 | 5 |
| 24 | S150+TC-2001_2_1_F11 | 21.25 | 12.89 | 4 |
| 25 | S105+TC-2001_1_1_F8.5 | 22.60 | 3.61 | 5 |
| 26 | Z70180+5T+6T_1.14_1_F8 | 25.00 | 4.60 | 5 |
| 27 | S105+6T_1.5_1_F8 | 25.25 | 6.42 | 4 |
| 28 | Z70180+6T_1_1_F8 | 25.40 | 4.50 | 5 |
| 29 | Z105+5T+6T_1.6_1_F8 | 26.00 | 3.67 | 4 |
| 30 | S150+TC-2001_1_1_F8.5 | 27.20 | 7.93 | 5 |
| 31 | Z100400+C500D_1.07_1_F8 | 28.20 | 4.07 | 5 |
| 32 | Z100400+MCON-35_1_1.16_F8 | 30.00 | 5.97 | 5 |
| 33 | S105+5T+6T_1.7_1_F8 | 30.67 | 6.94 | 3 |
| 34 | V55f35258263_1_1_F8 | 31.40 | 3.88 | 5 |
| 35 | V55f35209088_1_1_F8 | 31.80 | 4.79 | 5 |
| 36 | AF200+5T+6T_2_1_F8 | 32.25 | 5.85 | 4 |
| 37 | S150+5T+6T_1.8_1_F8 | 34.75 | 0.83 | 4 |
| 38 | AF200+6T_1.7_1_F8 | 34.75 | 2.77 | 4 |
