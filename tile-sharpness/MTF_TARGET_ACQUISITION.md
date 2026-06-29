# Acquiring a target for absolute, ceiling-valid MTF

Written 2026-06-28. **Not urgent** — see "Do this first (no shoot needed)" below;
a new capture is the *eventual* path to absolute lp/mm, not a blocker right now.

## Why this exists

The 2026-06-28 work (REPORT_taskAD_2026-06-28.md §E/§F) established that **no clean,
broad-coverage, sharpness-discriminating slanted-edge MTF target exists in the
2026-01/02 wafer dataset**:

- **Groove scribes over-read** the diffraction ceiling 1.5–1.8×. A scribe is a
  *groove*: under oblique light one wall is lit (specular glint → reads sharper than
  diffraction allows), the other is in shadow (soft). It's a lit-edge vs shadow-edge,
  not a clean reflectance step.
- **Bond-pad "edges" over-read worse** and cover few field positions — the atlas
  `bond_pads` regions are dense *periodic arrays* (aliasing → artificially sharp),
  not isolated steps. (They ARE good *periodic-FFT* targets — see below — just not
  edge targets.)
- The one **designed slanted-edge feature** (die 4D vertical bar) reads ≤ ceiling but
  is **intrinsic-width-limited (~0.10 cy/px, non-discriminating)** and **sparse**
  (1 of 16 die types).

The super-resolved edge estimator itself is sound (`methods/slanted_edge.py`,
`mtf50_step_erf`/`mtf50_auto`, 130 tests) — it reads the designed edge ≤ ceiling. It
just has no good *target* to consume. A dedicated knife/slant edge would fix that.

## Do this first (no shoot needed): periodic-FFT on the existing wafer

Before any new acquisition, exhaust the **periodic-FFT** route on the data already in
hand. The wafer's periodic structures (the maze at 13 µm; the `experimental` blocks
4B/4C/2B/2C with pitches 22–192 px; the many pad grids) are what those atlas regions
were *marked for*. A periodic target measures MTF **at its fundamental frequency** —
contrast in [0,1], bounded, and it *under*-reads to 0 past cutoff, so it **cannot
over-read the ceiling**. `methods/maze_fft.py` already does this for the maze and was
historically the primary high-M discriminator. The open task is to atlas-anchor a
periodic-FFT readout at the marked features for the centre/corner cross-config
ranking (see REPORT §G / the periodic-FFT plan). This may make a new shoot
unnecessary for *relative* cross-config ranking.

## If/when you do shoot: the target

Goal: a true, sharp, isolated, slightly-slanted reflectance edge at every field
position you care about, lit to avoid the groove-emboss / specular failure mode.

### Target
- **Best: a razor/knife edge** (cleanroom razor blade) over a uniform matte
  background — the classic ISO-12233 knife-edge. Effectively infinitely sharp, so it
  probes the *lens*, not the target.
- **Alternative: a printed/etched slant-edge chip** (chrome-on-glass photomask offcut
  with a long straight chrome→glass edge) — sharper than any printed chart at these
  magnifications. A glass-photomask test reticle is ideal if available.
- **Slant 3–7° off the sensor axis** (not 0°, not 45°) so the edge is super-resolved
  across rows but stays within one ROI. A single long edge beats a busy chart.

### Lighting (this is what bit the wafer)
- **Diffuse, near-axial / coaxial illumination** to kill the directional specular
  glint and shadow asymmetry that made the groove walls read differently. A diffuser
  dome or coaxial illuminator, not a raking side light.
- The target should be a **reflectance** edge (matte→matte contrast), **not a groove
  / topographic edge** — no walls to catch light.

### Framing & coverage (per magnification)
- The edge must appear at **centre + the four corners** of the frame; either a target
  with edges at multiple positions, or reposition between captures and tile.
- Shoot the **same magnifications** as the lens-test matrix (1:1, the diopter/TC
  combos, 2:1) so it overlays the existing ranking. Magnification can still be read
  from the wafer atlas if the wafer is co-planar in the same session, or from a stage
  micrometer.
- **Through-focus rail sweep** as usual (the analysis picks best focus per position).
- Apertures: at least **F8 and F11** (matching the current ranking); ideally the full
  set so the diffraction ceiling can be traced.

### What it unlocks
Feed each best-focus edge ROI to `methods/slanted_edge.mtf50_auto` (super-resolved
ESF → erf fit, ceiling-validated). Because the edge is a true sharp reflectance step,
the per-wall asymmetry disappears and the reading should sit at/below the diffraction
ceiling — giving **absolute lp/mm** comparable to published lens charts, not just the
relative metric we have now.

### Sanity checks on the new data
- A featureless/defocused frame must read ≈0 (no spurious signal).
- A stopped-down diffraction-limited shot must read **at** the ceiling, not above.
- Left vs right (or the two edge orientations) must now **agree** (the emboss
  asymmetry is gone) — if they don't, the lighting still has a directional component.

## Pointers
- Estimator: `tile-sharpness/src/tile_sharpness/methods/slanted_edge.py`
- Ceiling physics: `tile-sharpness/src/tile_sharpness/optics.py`
- Atlas registration (geometry + M): `wafer-atlas/scripts/reg_auto.py`
- Why the wafer failed, in full: `REPORT_taskAD_2026-06-28.md` §E/§F
- Negative-result branch (estimator + evidence): `padedge-metric`
