# NEF distance audit — 2025-09-11

Per (lens_dir, focal_length) summary of EXIF FocusDistance.
**inferred (m)**: for non-encoder lenses (no D/G/E aperture suffix,
no Z-mount, manual focus, etc.), the temporally-nearest encoder-
equipped frame's distance is used. NEFs adjacent in time were
shot at the same physical subject distance (tripod not moved).

**Distance class** (Reikan Focal two-tier rule by subject
distance / focal length ratio):
- Minimum is **20× FL for ≥ 300 mm FL** lenses (the curve stabilises
  earlier for long teles per Focal docs), **50× FL for < 300 mm FL**.
- `below Focal min`: under the per-FL minimum — fine for closer-distance
  testing but not directly cross-comparable to infinity readings.
- `meets Focal min, < 100× FL`: above minimum but below the comfortable
  infinity range.
- `infinity-class (100–300× FL)`: comfortable infinity testing.
- `well past infinity (> 300× FL)`: redundant headroom.

Closer-distance readings of the same lens aren't less valid; they
measure the lens at a different distance regime. Cross-day same-
lens comparisons need matched distance class for fairness.

*Reikan Focal recommends macro lenses be calibrated at their
intended use-distance rather than pushed to infinity — but the
'inf' folders in this dataset are infinity tests, so the standard
FL-ratio rule applies.*

| Lens dir | FL (mm) | n NEFs | n w/ dist | min (m) | median (m) | max (m) | inferred (m) | Effective | dist/FL | Validity |
|---|---|---|---|---|---|---|---|---|---|---|
| Nikon AF Nikkor 35mm f_2 | 35.0 | 21 | 21 | 0.06 | **0.06** | 0.06 | 6.31 | 6.31 (inferred) | 180× | infinity-class (100–300× FL) |
| Nikon AF Nikkor 50mm f_1.8 | 50.0 | 21 | 21 | 0.06 | **0.06** | 0.06 | 6.31 | 6.31 (inferred) | 126× | infinity-class (100–300× FL) |
| Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 24.0 | 34 | 34 | 10.59 | **10.59** | 10.59 | — | 10.59 (encoder) | 441× | well past infinity (> 300× FL) |
| Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 28.0 | 18 | 18 | 10.59 | **10.59** | 10.59 | — | 10.59 (encoder) | 378× | well past infinity (> 300× FL) |
| Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 35.0 | 18 | 18 | 10.59 | **10.59** | 10.59 | — | 10.59 (encoder) | 303× | well past infinity (> 300× FL) |
| Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 50.0 | 18 | 18 | 10.59 | **10.59** | 10.59 | — | 10.59 (encoder) | 212× | infinity-class (100–300× FL) |
| Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 55.0 | 18 | 18 | 10.59 | **10.59** | 10.59 | — | 10.59 (encoder) | 193× | infinity-class (100–300× FL) |
| Nikon AF-S DX Nikkor 35mm f_1.8G | 35.0 | 24 | 24 | 0.79 | **0.79** | 0.79 | — | 0.79 (encoder) | 23× | **below Focal min (50× FL)** |
| Nikon AF-S DX VR Zoom-Nikkor 16-85mm f_3.5-5.6G ED | 24.0 | 30 | 30 | 2.82 | **2.82** | 2.82 | — | 2.82 (encoder) | 118× | infinity-class (100–300× FL) |
| Nikon AF-S DX VR Zoom-Nikkor 16-85mm f_3.5-5.6G ED | 28.0 | 30 | 30 | 3.55 | **3.55** | 3.55 | — | 3.55 (encoder) | 127× | infinity-class (100–300× FL) |
| Nikon AF-S DX VR Zoom-Nikkor 16-85mm f_3.5-5.6G ED | 35.0 | 30 | 30 | 5.01 | **5.01** | 5.01 | — | 5.01 (encoder) | 143× | infinity-class (100–300× FL) |
| Nikon AF-S DX VR Zoom-Nikkor 16-85mm f_3.5-5.6G ED | 50.0 | 30 | 30 | 10.59 | **10.59** | 10.59 | — | 10.59 (encoder) | 212× | infinity-class (100–300× FL) |
| Nikon AF-S DX VR Zoom-Nikkor 16-85mm f_3.5-5.6G ED | 55.0 | 30 | 30 | 10.59 | **10.59** | 10.59 | — | 10.59 (encoder) | 193× | infinity-class (100–300× FL) |
| Nikon AF-S DX Zoom-Nikkor 17-55mm f_2.8G IF-ED | 24.0 | 18 | 18 | 10.59 | **10.59** | 10.59 | — | 10.59 (encoder) | 441× | well past infinity (> 300× FL) |
| Nikon AF-S DX Zoom-Nikkor 17-55mm f_2.8G IF-ED | 28.0 | 18 | 18 | 2.99 | **2.99** | 2.99 | — | 2.99 (encoder) | 107× | infinity-class (100–300× FL) |
| Nikon AF-S DX Zoom-Nikkor 17-55mm f_2.8G IF-ED | 35.0 | 18 | 18 | 10.59 | **10.59** | 10.59 | — | 10.59 (encoder) | 303× | well past infinity (> 300× FL) |
| Nikon AF-S DX Zoom-Nikkor 17-55mm f_2.8G IF-ED | 50.0 | 37 | 37 | 7.50 | **7.50** | 10.59 | — | 7.50 (encoder) | 150× | infinity-class (100–300× FL) |
| Nikon AF-S DX Zoom-Nikkor 17-55mm f_2.8G IF-ED | 55.0 | 18 | 18 | 7.50 | **7.50** | 7.50 | — | 7.50 (encoder) | 136× | infinity-class (100–300× FL) |
| Nikon AF-S DX Zoom-Nikkor 18-70mm f_3.5-4.5G IF-ED | 24.0 | 36 | 36 | 1.00 | **1.00** | 1.00 | — | 1.00 (encoder) | 42× | **below Focal min (50× FL)** |
| Nikon AF-S DX Zoom-Nikkor 18-70mm f_3.5-4.5G IF-ED | 27.0 | 36 | 36 | 1.41 | **1.41** | 1.41 | — | 1.41 (encoder) | 52× | meets Focal min, < 100× FL |
| Nikon AF-S DX Zoom-Nikkor 18-70mm f_3.5-4.5G IF-ED | 35.0 | 30 | 30 | 1.68 | **1.68** | 1.68 | — | 1.68 (encoder) | 48× | **below Focal min (50× FL)** |
| Nikon AF-S DX Zoom-Nikkor 18-70mm f_3.5-4.5G IF-ED | 50.0 | 30 | 30 | 1.68 | **1.68** | 1.68 | — | 1.68 (encoder) | 34× | **below Focal min (50× FL)** |
| Nikon AF-S DX Zoom-Nikkor 18-70mm f_3.5-4.5G IF-ED | 55.0 | 30 | 30 | 2.37 | **2.37** | 2.37 | — | 2.37 (encoder) | 43× | **below Focal min (50× FL)** |
| Nikon AF-S Nikkor 50mm f_1.8G | 50.0 | 24 | 24 | 6.31 | **6.31** | 6.31 | — | 6.31 (encoder) | 126× | infinity-class (100–300× FL) |
| Nikon Micro-Nikkor 55mm f_2.8 AIS 287318 | 55.0 | 18 | 18 | 0.01 | **0.01** | 0.01 | 6.31 | 6.31 (inferred) | 115× | infinity-class (100–300× FL) |
| Nikon Micro-Nikkor 55mm f_2.8 AIS 537016 | 55.0 | 18 | 18 | 0.01 | **0.01** | 0.01 | 6.31 | 6.31 (inferred) | 115× | infinity-class (100–300× FL) |
| Nikon Nikkor-N.C Auto 24mm f_2.8 | 24.0 | 18 | 18 | 0.01 | **0.01** | 0.01 | 12.59 | 12.59 (inferred) | 525× | well past infinity (> 300× FL) |
| Nikon PC-Nikkor 35mm f_2.8 | 35.0 | 18 | 18 | 0.01 | **0.01** | 0.01 | 12.59 | 12.59 (inferred) | 360× | well past infinity (> 300× FL) |
| Sigma 18-35mm F1.8 DC HSM | 24.0 | 24 | 24 | 4.22 | **4.22** | 4.22 | — | 4.22 (encoder) | 176× | infinity-class (100–300× FL) |
| Sigma 18-35mm F1.8 DC HSM | 28.0 | 25 | 25 | 4.22 | **4.22** | 4.22 | — | 4.22 (encoder) | 151× | infinity-class (100–300× FL) |
| Sigma 18-35mm F1.8 DC HSM | 35.0 | 24 | 24 | 4.22 | **4.22** | 4.22 | — | 4.22 (encoder) | 121× | infinity-class (100–300× FL) |
| Sigma 24mm F2.8 Super Wide II Macro | 24.0 | 19 | 19 | 0.01 | **0.01** | 0.01 | 12.59 | 12.59 (inferred) | 525× | well past infinity (> 300× FL) |
| Sigma 50-100mm F1.8 DC HSM A | 50.0 | 25 | 25 | 12.59 | **12.59** | 12.59 | — | 12.59 (encoder) | 252× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM A | 55.0 | 24 | 24 | 12.59 | **12.59** | 12.59 | — | 12.59 (encoder) | 229× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 EX APO DC HSM I | 50.0 | 18 | 18 | 8.91 | **8.91** | 8.91 | — | 8.91 (encoder) | 178× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 EX APO DC HSM I | 56.0 | 18 | 18 | 8.91 | **8.91** | 8.91 | — | 8.91 (encoder) | 159× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 EX APO DC HSM II 1001387 | 50.0 | 18 | 18 | 14.13 | **14.13** | 14.13 | — | 14.13 (encoder) | 283× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 EX APO DC HSM II 1001387 | 55.0 | 18 | 18 | 14.13 | **14.13** | 14.13 | — | 14.13 (encoder) | 257× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 EX APO DC HSM II 1012221 | 50.0 | 18 | 18 | 14.13 | **14.13** | 14.13 | — | 14.13 (encoder) | 283× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 EX APO DC HSM II 1012221 | 55.0 | 18 | 18 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 407× | well past infinity (> 300× FL) |

## Sessions (gap = 5 min)

- **Session 0** 2025-09-11 18:09:52 → 2025-09-11 19:38:32 (89 min): encoded distances 0.8m, 1.0m, 1.4m, 1.7m, 2.4m, 2.8m, 3.0m, 3.5m, 4.2m, 5.0m, 6.3m, 7.5m, 8.9m, 10.6m, 12.6m, 14.1m, 22.4m; lenses: Nikon AF Nikkor 35mm f_2, Nikon AF Nikkor 50mm f_1.8, Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR, Nikon AF-S DX Nikkor 35mm f_1.8G, Nikon AF-S DX VR Zoom-Nikkor 16-85mm f_3.5-5.6G ED, Nikon AF-S DX Zoom-Nikkor 17-55mm f_2.8G IF-ED, Nikon AF-S DX Zoom-Nikkor 18-70mm f_3.5-4.5G IF-ED, Nikon AF-S Nikkor 50mm f_1.8G, Nikon Micro-Nikkor 55mm f_2.8 AIS 287318, Nikon Micro-Nikkor 55mm f_2.8 AIS 537016, Nikon Nikkor-N.C Auto 24mm f_2.8, Nikon PC-Nikkor 35mm f_2.8, Sigma 18-35mm F1.8 DC HSM, Sigma 24mm F2.8 Super Wide II Macro, Sigma 50-100mm F1.8 DC HSM A, Sigma 50-150mm F2.8 EX APO DC HSM I, Sigma 50-150mm F2.8 EX APO DC HSM II 1001387, Sigma 50-150mm F2.8 EX APO DC HSM II 1012221

## Per-lens-dir collapsed view

| Lens dir | min FL | max FL | dist range (m) |
|---|---|---|---|
| Nikon AF Nikkor 35mm f_2 | 35 | 35 | 0.1..0.1 |
| Nikon AF Nikkor 50mm f_1.8 | 50 | 50 | 0.1..0.1 |
| Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 24 | 55 | 10.6..10.6 |
| Nikon AF-S DX Nikkor 35mm f_1.8G | 35 | 35 | 0.8..0.8 |
| Nikon AF-S DX VR Zoom-Nikkor 16-85mm f_3.5-5.6G ED | 24 | 55 | 2.8..10.6 |
| Nikon AF-S DX Zoom-Nikkor 17-55mm f_2.8G IF-ED | 24 | 55 | 3.0..10.6 |
| Nikon AF-S DX Zoom-Nikkor 18-70mm f_3.5-4.5G IF-ED | 24 | 55 | 1.0..2.4 |
| Nikon AF-S Nikkor 50mm f_1.8G | 50 | 50 | 6.3..6.3 |
| Nikon Micro-Nikkor 55mm f_2.8 AIS 287318 | 55 | 55 | 0.0..0.0 |
| Nikon Micro-Nikkor 55mm f_2.8 AIS 537016 | 55 | 55 | 0.0..0.0 |
| Nikon Nikkor-N.C Auto 24mm f_2.8 | 24 | 24 | 0.0..0.0 |
| Nikon PC-Nikkor 35mm f_2.8 | 35 | 35 | 0.0..0.0 |
| Sigma 18-35mm F1.8 DC HSM | 24 | 35 | 4.2..4.2 |
| Sigma 24mm F2.8 Super Wide II Macro | 24 | 24 | 0.0..0.0 |
| Sigma 50-100mm F1.8 DC HSM A | 50 | 55 | 12.6..12.6 |
| Sigma 50-150mm F2.8 EX APO DC HSM I | 50 | 56 | 8.9..8.9 |
| Sigma 50-150mm F2.8 EX APO DC HSM II 1001387 | 50 | 55 | 14.1..14.1 |
| Sigma 50-150mm F2.8 EX APO DC HSM II 1012221 | 50 | 55 | 14.1..22.4 |
