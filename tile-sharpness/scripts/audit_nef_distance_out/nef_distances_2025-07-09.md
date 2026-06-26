# NEF distance audit — 2025-07-09

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
| Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 70.0 | 13 | 13 | 14.96 | **14.96** | 14.96 | — | 14.96 (encoder) | 214× | infinity-class (100–300× FL) |
| Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 105.0 | 14 | 14 | 14.96 | **14.96** | 14.96 | — | 14.96 (encoder) | 142× | infinity-class (100–300× FL) |
| Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 135.0 | 13 | 13 | 14.96 | **14.96** | 14.96 | — | 14.96 (encoder) | 111× | infinity-class (100–300× FL) |
| Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 180.0 | 11 | 11 | 14.96 | **14.96** | 14.96 | — | 14.96 (encoder) | 83× | meets Focal min, < 100× FL |
| Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x | 70.0 | 11 | 11 | 14.96 | **14.96** | 14.96 | — | 14.96 (encoder) | 214× | infinity-class (100–300× FL) |
| Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x | 105.0 | 11 | 11 | 14.96 | **14.96** | 14.96 | — | 14.96 (encoder) | 142× | infinity-class (100–300× FL) |
| Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x | 135.0 | 10 | 10 | 14.96 | **14.96** | 14.96 | — | 14.96 (encoder) | 111× | infinity-class (100–300× FL) |
| Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x | 180.0 | 6 | 6 | 14.96 | **14.96** | 14.96 | — | 14.96 (encoder) | 83× | meets Focal min, < 100× FL |
| Nikon AF-S Nikkor 300mm f_4D IF-ED | 300.0 | 13 | 13 | 37.58 | **37.58** | 37.58 | — | 37.58 (encoder) | 125× | infinity-class (100–300× FL) |
| Nikon AF-S Nikkor 300mm f_4D IF-ED + Kenko Pro 300 DG 1.4x | 420.0 | 9 | 9 | 37.58 | **37.58** | 37.58 | — | 37.58 (encoder) | 89× | meets Focal min, < 100× FL |
| Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-14e I | 420.0 | 9 | 9 | 37.58 | **37.58** | 37.58 | — | 37.58 (encoder) | 89× | meets Focal min, < 100× FL |
| Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-14e III | 420.0 | 12 | 12 | 37.58 | **37.58** | 37.58 | — | 37.58 (encoder) | 89× | meets Focal min, < 100× FL |
| Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-17e II | 500.0 | 12 | 12 | 37.58 | **37.58** | 37.58 | — | 37.58 (encoder) | 75× | meets Focal min, < 100× FL |
| Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-20e III | 600.0 | 9 | 9 | 37.58 | **37.58** | 37.58 | — | 37.58 (encoder) | 63× | meets Focal min, < 100× FL |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED | 70.0 | 20 | 20 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 339× | well past infinity (> 300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED | 105.0 | 15 | 15 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 226× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED | 135.0 | 15 | 15 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 176× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED | 200.0 | 15 | 15 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 119× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Kenko Pro 300 DG 1.4x | 100.0 | 13 | 13 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 237× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Kenko Pro 300 DG 1.4x | 150.0 | 14 | 14 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 158× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Kenko Pro 300 DG 1.4x | 195.0 | 13 | 13 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 122× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Kenko Pro 300 DG 1.4x | 280.0 | 12 | 12 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 85× | meets Focal min, < 100× FL |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e I | 100.0 | 12 | 12 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 237× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e I | 150.0 | 25 | 25 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 158× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e I | 195.0 | 13 | 13 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 122× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e I | 280.0 | 14 | 14 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 85× | meets Focal min, < 100× FL |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e III | 100.0 | 13 | 13 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 200× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e III | 150.0 | 13 | 13 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 158× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e III | 195.0 | 12 | 12 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 122× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e III | 280.0 | 12 | 12 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 85× | meets Focal min, < 100× FL |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-17e II | 120.0 | 12 | 12 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 198× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-17e II | 180.0 | 12 | 12 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 132× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-17e II | 230.0 | 13 | 13 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 103× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-17e II | 340.0 | 13 | 13 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 70× | meets Focal min, < 100× FL |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-20e III | 140.0 | 9 | 9 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 169× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-20e III | 210.0 | 10 | 10 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 113× | infinity-class (100–300× FL) |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-20e III | 260.0 | 9 | 9 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 91× | meets Focal min, < 100× FL |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-20e III | 400.0 | 10 | 10 | 23.71 | **23.71** | 23.71 | — | 23.71 (encoder) | 59× | meets Focal min, < 100× FL |
| Sigma 50-100mm F1.8 DC HSM | A | 50.0 | 23 | 23 | 12.59 | **12.59** | 12.59 | — | 12.59 (encoder) | 252× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A | 70.0 | 44 | 44 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 285× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A | 100.0 | 23 | 23 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 200× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Kenko Pro 300 DG 1.4x | 50.0 | 16 | 16 | 12.59 | **12.59** | 12.59 | — | 12.59 (encoder) | 252× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Kenko Pro 300 DG 1.4x | 70.0 | 18 | 18 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 285× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Kenko Pro 300 DG 1.4x | 100.0 | 29 | 29 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 200× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma APO TC 1.4x | 50.0 | 20 | 20 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 399× | well past infinity (> 300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma APO TC 1.4x | 70.0 | 17 | 17 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 285× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma APO TC 1.4x | 100.0 | 16 | 16 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 200× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma TC-1401 | 50.0 | 18 | 18 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 399× | well past infinity (> 300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma TC-1401 | 70.0 | 18 | 18 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 285× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma TC-1401 | 100.0 | 16 | 16 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 200× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma TC-2001 | 50.0 | 14 | 14 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 399× | well past infinity (> 300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma TC-2001 | 70.0 | 15 | 15 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 285× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma TC-2001 | 100.0 | 16 | 16 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 200× | infinity-class (100–300× FL) |
| Sigma 50-100mm F1.8 DC HSM | A ISO400 | 100.0 | 17 | 17 | 19.95 | **19.95** | 19.95 | — | 19.95 (encoder) | 200× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM | 50.0 | 15 | 15 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 448× | well past infinity (> 300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM | 72.0 | 15 | 15 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 311× | well past infinity (> 300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM | 98.0 | 16 | 16 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 228× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM | 150.0 | 16 | 16 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 149× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM + Kenko Pro 300 DG 1.4x | 50.0 | 12 | 12 | 14.13 | **14.13** | 14.13 | — | 14.13 (encoder) | 283× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM + Kenko Pro 300 DG 1.4x | 68.0 | 13 | 13 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 329× | well past infinity (> 300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM + Kenko Pro 300 DG 1.4x | 102.0 | 12 | 12 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 220× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM + Kenko Pro 300 DG 1.4x | 150.0 | 12 | 12 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 149× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM + Sigma APO TC 1.4x | 70.0 | 12 | 12 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 320× | well past infinity (> 300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM + Sigma APO TC 1.4x | 102.0 | 13 | 13 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 220× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM + Sigma APO TC 1.4x | 145.0 | 16 | 16 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 154× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 I EX APO DC HSM + Sigma APO TC 1.4x | 210.0 | 15 | 15 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 107× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM | 50.0 | 15 | 15 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 448× | well past infinity (> 300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM | 75.0 | 17 | 17 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 299× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM | 105.0 | 16 | 16 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 213× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM | 150.0 | 17 | 17 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 149× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Kenko Pro 300 DG 1.4x | 50.0 | 16 | 16 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 448× | well past infinity (> 300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Kenko Pro 300 DG 1.4x | 75.0 | 16 | 16 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 299× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Kenko Pro 300 DG 1.4x | 105.0 | 13 | 13 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 213× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Kenko Pro 300 DG 1.4x | 150.0 | 13 | 13 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 149× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma APO TC 1.4x | 70.0 | 12 | 12 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 320× | well past infinity (> 300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma APO TC 1.4x | 102.0 | 12 | 12 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 220× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma APO TC 1.4x | 145.0 | 13 | 13 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 154× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma APO TC 1.4x | 210.0 | 12 | 12 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 107× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-1401 | 70.0 | 13 | 13 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 320× | well past infinity (> 300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-1401 | 102.0 | 13 | 13 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 220× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-1401 | 145.0 | 12 | 12 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 154× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-1401 | 210.0 | 15 | 15 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 107× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-2001 | 100.0 | 9 | 9 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 224× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-2001 | 145.0 | 9 | 9 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 154× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-2001 | 210.0 | 11 | 11 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 107× | infinity-class (100–300× FL) |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-2001 | 300.0 | 10 | 10 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 75× | meets Focal min, < 100× FL |
| Sigma APO Macro 150mm F2.8 EX DG OS HSM | 150.0 | 19 | 19 | 5.96 | **5.96** | 5.96 | — | 5.96 (encoder) | 40× | **below Focal min (50× FL)** |
| Sigma APO Macro 150mm F2.8 EX DG OS HSM + Kenko Pro 300 DG 1.4x | 150.0 | 17 | 17 | 5.96 | **5.96** | 5.96 | — | 5.96 (encoder) | 40× | **below Focal min (50× FL)** |
| Sigma APO Macro 150mm F2.8 EX DG OS HSM + Sigma APO TC 1.4x | 210.0 | 17 | 17 | 5.96 | **5.96** | 5.96 | — | 5.96 (encoder) | 28× | **below Focal min (50× FL)** |
| Sigma APO Macro 150mm F2.8 EX DG OS HSM + Sigma TC-1401 | 210.0 | 13 | 13 | 5.96 | **5.96** | 5.96 | — | 5.96 (encoder) | 28× | **below Focal min (50× FL)** |
| Sigma APO Macro 150mm F2.8 EX DG OS HSM + Sigma TC-2001 | 300.0 | 12 | 12 | 5.96 | **5.96** | 5.96 | — | 5.96 (encoder) | 20× | **below Focal min (20× FL)** |
| Sigma APO Macro 180mm F3.5 EX DG HSM | 185.0 | 17 | 17 | 13.34 | **13.34** | 13.34 | — | 13.34 (encoder) | 72× | meets Focal min, < 100× FL |
| Sigma APO Macro 180mm F3.5 EX DG HSM + Kenko Pro 300 DG 1.4x | 185.0 | 12 | 12 | 13.34 | **13.34** | 13.34 | — | 13.34 (encoder) | 72× | meets Focal min, < 100× FL |
| Sigma APO Macro 180mm F3.5 EX DG HSM + Sigma APO TC 1.4x | 250.0 | 13 | 13 | 13.34 | **13.34** | 13.34 | — | 13.34 (encoder) | 53× | meets Focal min, < 100× FL |
| Tamron SP 90mm F_2.8 Di VC USD Macro 1:1 | 90.0 | 16 | 16 | 44.67 | **44.67** | 44.67 | — | 44.67 (encoder) | 496× | well past infinity (> 300× FL) |
| Tamron SP 90mm F_2.8 Di VC USD Macro 1:1 + Kenko Pro 300 DG 1.4x | 90.0 | 16 | 16 | 44.67 | **44.67** | 44.67 | — | 44.67 (encoder) | 496× | well past infinity (> 300× FL) |
| results-ignore | 50.0 | 3 | 3 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 448× | well past infinity (> 300× FL) |
| results-ignore | 55.0 | 1 | 1 | 22.39 | **22.39** | 22.39 | — | 22.39 (encoder) | 407× | well past infinity (> 300× FL) |

## Sessions (gap = 5 min)

- **Session 0** 2025-07-09 19:16:42 → 2025-07-09 19:22:42 (6 min): encoded distances 22.4m; lenses: results-ignore
- **Session 1** 2025-07-09 19:28:51 → 2025-07-09 21:51:00 (142 min): encoded distances 6.0m, 12.6m, 13.3m, 14.1m, 15.0m, 19.9m, 22.4m, 23.7m, 37.6m, 44.7m; lenses: Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED, Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x, Nikon AF-S Nikkor 300mm f_4D IF-ED, Nikon AF-S Nikkor 300mm f_4D IF-ED + Kenko Pro 300 DG 1.4x, Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-14e I, Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-14e III, Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-17e II, Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-20e III, Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED, Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Kenko Pro 300 DG 1.4x, Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e I, Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e III, Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-17e II, Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-20e III, Sigma 50-100mm F1.8 DC HSM | A, Sigma 50-100mm F1.8 DC HSM | A + Kenko Pro 300 DG 1.4x, Sigma 50-100mm F1.8 DC HSM | A + Sigma APO TC 1.4x, Sigma 50-100mm F1.8 DC HSM | A + Sigma TC-1401, Sigma 50-100mm F1.8 DC HSM | A + Sigma TC-2001, Sigma 50-100mm F1.8 DC HSM | A ISO400, Sigma 50-150mm F2.8 I EX APO DC HSM, Sigma 50-150mm F2.8 I EX APO DC HSM + Kenko Pro 300 DG 1.4x, Sigma 50-150mm F2.8 I EX APO DC HSM + Sigma APO TC 1.4x, Sigma 50-150mm F2.8 II EX APO DC HSM, Sigma 50-150mm F2.8 II EX APO DC HSM + Kenko Pro 300 DG 1.4x, Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma APO TC 1.4x, Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-1401, Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-2001, Sigma APO Macro 150mm F2.8 EX DG OS HSM, Sigma APO Macro 150mm F2.8 EX DG OS HSM + Kenko Pro 300 DG 1.4x, Sigma APO Macro 150mm F2.8 EX DG OS HSM + Sigma APO TC 1.4x, Sigma APO Macro 150mm F2.8 EX DG OS HSM + Sigma TC-1401, Sigma APO Macro 150mm F2.8 EX DG OS HSM + Sigma TC-2001, Sigma APO Macro 180mm F3.5 EX DG HSM, Sigma APO Macro 180mm F3.5 EX DG HSM + Kenko Pro 300 DG 1.4x, Sigma APO Macro 180mm F3.5 EX DG HSM + Sigma APO TC 1.4x, Tamron SP 90mm F_2.8 Di VC USD Macro 1:1, Tamron SP 90mm F_2.8 Di VC USD Macro 1:1 + Kenko Pro 300 DG 1.4x

## Per-lens-dir collapsed view

| Lens dir | min FL | max FL | dist range (m) |
|---|---|---|---|
| Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 70 | 180 | 15.0..15.0 |
| Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x | 70 | 180 | 15.0..15.0 |
| Nikon AF-S Nikkor 300mm f_4D IF-ED | 300 | 300 | 37.6..37.6 |
| Nikon AF-S Nikkor 300mm f_4D IF-ED + Kenko Pro 300 DG 1.4x | 420 | 420 | 37.6..37.6 |
| Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-14e I | 420 | 420 | 37.6..37.6 |
| Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-14e III | 420 | 420 | 37.6..37.6 |
| Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-17e II | 500 | 500 | 37.6..37.6 |
| Nikon AF-S Nikkor 300mm f_4D IF-ED + Nikon TC-20e III | 600 | 600 | 37.6..37.6 |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED | 70 | 200 | 23.7..23.7 |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Kenko Pro 300 DG 1.4x | 100 | 280 | 23.7..23.7 |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e I | 100 | 280 | 23.7..23.7 |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-14e III | 100 | 280 | 19.9..23.7 |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-17e II | 120 | 340 | 23.7..23.7 |
| Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED + Nikon TC-20e III | 140 | 400 | 23.7..23.7 |
| Sigma 50-100mm F1.8 DC HSM | A | 50 | 100 | 12.6..19.9 |
| Sigma 50-100mm F1.8 DC HSM | A + Kenko Pro 300 DG 1.4x | 50 | 100 | 12.6..19.9 |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma APO TC 1.4x | 50 | 100 | 19.9..19.9 |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma TC-1401 | 50 | 100 | 19.9..19.9 |
| Sigma 50-100mm F1.8 DC HSM | A + Sigma TC-2001 | 50 | 100 | 19.9..19.9 |
| Sigma 50-100mm F1.8 DC HSM | A ISO400 | 100 | 100 | 19.9..19.9 |
| Sigma 50-150mm F2.8 I EX APO DC HSM | 50 | 150 | 22.4..22.4 |
| Sigma 50-150mm F2.8 I EX APO DC HSM + Kenko Pro 300 DG 1.4x | 50 | 150 | 14.1..22.4 |
| Sigma 50-150mm F2.8 I EX APO DC HSM + Sigma APO TC 1.4x | 70 | 210 | 22.4..22.4 |
| Sigma 50-150mm F2.8 II EX APO DC HSM | 50 | 150 | 22.4..22.4 |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Kenko Pro 300 DG 1.4x | 50 | 150 | 22.4..22.4 |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma APO TC 1.4x | 70 | 210 | 22.4..22.4 |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-1401 | 70 | 210 | 22.4..22.4 |
| Sigma 50-150mm F2.8 II EX APO DC HSM + Sigma TC-2001 | 100 | 300 | 22.4..22.4 |
| Sigma APO Macro 150mm F2.8 EX DG OS HSM | 150 | 150 | 6.0..6.0 |
| Sigma APO Macro 150mm F2.8 EX DG OS HSM + Kenko Pro 300 DG 1.4x | 150 | 150 | 6.0..6.0 |
| Sigma APO Macro 150mm F2.8 EX DG OS HSM + Sigma APO TC 1.4x | 210 | 210 | 6.0..6.0 |
| Sigma APO Macro 150mm F2.8 EX DG OS HSM + Sigma TC-1401 | 210 | 210 | 6.0..6.0 |
| Sigma APO Macro 150mm F2.8 EX DG OS HSM + Sigma TC-2001 | 300 | 300 | 6.0..6.0 |
| Sigma APO Macro 180mm F3.5 EX DG HSM | 185 | 185 | 13.3..13.3 |
| Sigma APO Macro 180mm F3.5 EX DG HSM + Kenko Pro 300 DG 1.4x | 185 | 185 | 13.3..13.3 |
| Sigma APO Macro 180mm F3.5 EX DG HSM + Sigma APO TC 1.4x | 250 | 250 | 13.3..13.3 |
| Tamron SP 90mm F_2.8 Di VC USD Macro 1:1 | 90 | 90 | 44.7..44.7 |
| Tamron SP 90mm F_2.8 Di VC USD Macro 1:1 + Kenko Pro 300 DG 1.4x | 90 | 90 | 44.7..44.7 |
| results-ignore | 50 | 55 | 22.4..22.4 |
