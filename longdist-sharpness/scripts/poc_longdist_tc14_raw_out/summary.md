# TC-1.4x retention — LINEAR RAW (f/8, brick mortar edges)

rawpy demosaic-only, gamma(1,1), no sharpening / no lens corrections. MTF measured in linear light (correct domain). Best-focus per edge.

| config | f_eff | n edges | median MTF50 | sub-Nyq | median MTF@Nyq | max MTF@Nyq |
|---|---|---|---|---|---|---|
| bare | 400 | 175 | 0.459 | 91/175 | 0.731 | 2.33 |
| tc14 | 560 | 581 | 0.352 | 341/581 | 0.713 | 2.44 |

## Retention (tc14 / bare)

- **MTF@Nyquist: 0.98**  (break-even 0.714, FOM +37%) → PASS
- MTF50: 0.77
- physical ordering (MTF@Nyq): bare 0.731 >= tc14 0.713
- sharpening halo (median MTF@Nyq <=1?): GONE (<=1.0)