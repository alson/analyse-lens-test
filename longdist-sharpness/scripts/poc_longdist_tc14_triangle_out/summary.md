# TC-1.4x — same-feature (green triangle) retention, f/11

Same physical edge (triangle sides) across configs → like-for-like. Best-focus per edge across the focus-shift stack.

| config | f_eff | edge MTF50 (best side) | mean of sides | MTF@Nyq (best) | ref frame |
|---|---|---|---|---|---|
| bare | 400 | 0.493 | 0.493 | 1.369 | 00414|NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO100|400.0 mm|F11|_dsc7492.jpg |
| tc14 | 560 | 0.493 | 0.338 | 1.305 | 01506|NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x ISO100|560.0 mm|F11|_dsc8584.jpg |
| tc20 | 800 | 0.493 | 0.367 | 1.627 | 00775|NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x ISO100|800.0 mm|F11|_dsc7853.jpg |

## Retention vs bare (same triangle edge)

| TC | retention MTF50 | retention Nyq | break-even | FOM gain | verdict |
|---|---|---|---|---|---|
| tc14 | 1.00 | 0.95 | 0.714 | +40% | PASS (adds detail) |
| tc20 | 1.00 | 1.19 | 0.500 | +100% | PASS (adds detail) |

> Expect bare > tc14 > tc20 in cy/sensor-px. Check the triangle_*.jpg overlays — a misdetected/clipped edge invalidates the row.