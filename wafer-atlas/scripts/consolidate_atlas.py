"""Consolidate parsed painted-feature data into a canonical atlas.json.

Takes atlas_0129_painted.json (raw connected-component output) and
restructures it into a clean atlas indexed by super-cell type (col mod 4,
row mod 4). Adds user-provided structural metadata for cyan regions
(3×3 grids, 5+4 columns etc.) and user descriptions for each die type.

The output atlas.json is the authoritative wafer-atlas data file —
inputs to per-sweep registration and per-feature locate steps.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


WAFER_ATLAS_DIR = Path(__file__).parent.parent
PARSED_JSON = WAFER_ATLAS_DIR / "out" / "0129" / "atlas_0129_painted.json"
OVERVIEW_GRID = WAFER_ATLAS_DIR / "out" / "grid_supercell_refined.png"  # ref only
OUT_PATH = WAFER_ATLAS_DIR / "atlas.json"


# User-provided per-die-type descriptions (free-form, from chat).
# Indexed by (col mod 4, row mod 4) as a tuple-stringified key.
DIE_TYPE_DESCRIPTIONS = {
    "(0, 0)": {
        "label_in_overview": "4E (or 0E, 8E)",
        "user_desc": "bond pads from (0.25, 0)-(1, 0.6), other structures near (0,0) and (0.25, 0.6)-(1, 1)",
    },
    "(0, 1)": {
        "label_in_overview": "4B (or 0B, 8B); 4F partial",
        "user_desc": "3×3 grid of somewhat complicated structures with a couple of bond pads",
    },
    "(0, 2)": {
        "label_in_overview": "4C (or 0C, 8C)",
        "user_desc": "less-dense pad grid (0.6, 0)-(1, 1); column of 5 + column of 4 of same complex element (cyan)",
    },
    "(0, 3)": {
        "label_in_overview": "4D (or 0D, 8D)",
        "user_desc": "strong vertical bar at (u 0.3-0.35, v 0.4-0.6) — primary slanted-edge target",
    },
    "(1, 0)": {
        "label_in_overview": "5E (or 1E, 9E); 1E is jagged",
        "user_desc": "horizontal band of bond pads at top + three columns at bottom (described from 5E)",
    },
    "(1, 1)": {
        "label_in_overview": "1B (or 5B, 9B)",
        "user_desc": "grid of resistors / caps of different sizes — intentionally skipped, not useful",
    },
    "(1, 2)": {
        "label_in_overview": "1C (or 5C, 9C)",
        "user_desc": "3 horizontal bands of silvered bonding pads",
    },
    "(1, 3)": {
        "label_in_overview": "1D (or 5D, 9D)",
        "user_desc": "like 3C: 3 pad columns + irregular row",
    },
    "(2, 0)": {
        "label_in_overview": "2E + 6E both painted (or 10E, 2A, 6A, 10A partials)",
        "user_desc": "coarser pad grid than the others — less-dense grid of rows of bonding pads. Deliberately painted on both 2E (cut-off instance) AND 6E (full-die reference) so the atlas has a complete-die view.",
    },
    "(2, 1)": {
        "label_in_overview": "2B (or 6B, 10B)",
        "user_desc": "bond pads at (0,0)-(1,0.15) bottom + (0,0.7)-(1,0.85) top; middle = horizontal lines + serpent (cyan; possible slanted-edge target)",
    },
    "(2, 2)": {
        "label_in_overview": "2C (or 6C, 10C)",
        "user_desc": "bond pads in three horizontal bands; (0.3,0)-(0.4,1) strip of small R/C; plus a large cyan rectangle",
    },
    "(2, 3)": {
        "label_in_overview": "2D (or 6D, 10D)",
        "user_desc": "mostly like 1B but with a small bond-pad patch at right side — intentionally painted for low-priority FFT target",
    },
    "(3, 0)": {
        "label_in_overview": "3E (or 7E)",
        "user_desc": "bond pads in three horizontal bands across entire die",
    },
    "(3, 1)": {
        "label_in_overview": "3B (or 7B)",
        "user_desc": "three vertical magenta rectangles + one horizontal magenta rectangle spanning the whole die",
    },
    "(3, 2)": {
        "label_in_overview": "3C (or 7C)",
        "user_desc": "two horizontal pad blocks from top spanning entire die width + a small bond-pad square around (u 0.2, v 0.8)",
    },
    "(3, 3)": {
        "label_in_overview": "3D (or 7D)",
        "user_desc": "mostly bond pads except (0.7, 0.5)-(1, 1)",
    },
}


# Structural metadata for cyan regions where the user told us the count.
# Useful at measurement time: known periodicity validates / overrides the
# FFT estimate, especially for small regions where the FFT is unreliable.
CYAN_STRUCTURE = {
    "(0, 1)": {  # 4B
        "type": "regular_grid",
        "n_u": 3, "n_v": 3,
        "element": "complex geometric shape with fine details",
        "use_for_fft": True,
        "fft_caveat": "FFT may lock onto sub-element periodicity",
    },
    "(0, 2)": {  # 4C
        "type": "two_columns",
        "column_counts": [5, 4],
        "element": "complex geometric shape",
        "suggested_subregion": "4×2 grid (drop odd element) for clean FFT",
        "use_for_fft": True,
    },
    "(2, 1)": {  # 2B middle
        "type": "horizontal_lines_plus_serpent",
        "use_for_slanted_edge": True,
        "use_for_fft": True,
        "note": "user-flagged slanted-edge candidate; may have long parallel edges",
    },
    "(2, 2)": {  # 2C
        "type": "large_uniform_region",
        "use_for_fft": True,
    },
}


def main():
    data = json.load(open(PARSED_JSON))
    grid = data["grid_params"]

    atlas = {
        "schema_version": 1,
        "wafer": {
            "super_cell_shape": [4, 4],
            "row_letters": ["A", "B", "C", "D", "E", "F"],
            "n_visible_rows": 6,
            "n_visible_cols": 11,
            "rotation_in_photo_deg_cw": grid["theta_deg"],
            "scale_relative_to_overview": grid["scale"],
            "note": "Wafer has 4×4 super-cell with irregular pitch — one wide col type (cols mod 4 == 0) and one tall row type (rows mod 4 == 1, i.e. B and F).",
        },
        "die_pitch_px_in_0129": {
            "d_col": grid["d_col"],
            "d_row": grid["d_row"],
            "super_cell_width_px": sum(grid["d_col"]),
            "super_cell_height_px": sum(grid["d_row"]),
        },
        "grid_params_per_photo": {
            "step_0129_b.jpg": grid,
            # step_0131_c.jpg grid is in wafer-atlas/out/grid_supercell_refined.py output
        },
        "die_types": {},
    }

    for type_key, desc in DIE_TYPE_DESCRIPTIONS.items():
        components = data["features_by_die_type"].get(type_key, [])
        # Group by kind
        bond_pads, slanted_edge, experimental = [], [], []
        for c in components:
            entry = {
                "source_die": c["die_label"],
                "bbox_uv": c["bbox_uv_in_die"],
                "area_px": c["area_px"],
                "pad_pitch_px": c.get("pad_pitch_px"),
            }
            if c["kind"] == "bond_pads":
                bond_pads.append(entry)
            elif c["kind"] == "slanted_edge":
                slanted_edge.append(entry)
            elif c["kind"] == "experimental":
                experimental.append(entry)
        atlas["die_types"][type_key] = {
            "user_description": desc["user_desc"],
            "instances_label": desc["label_in_overview"],
            "feature_inventory": {
                "bond_pads": bond_pads,
                "slanted_edge": slanted_edge,
                "experimental": experimental,
            },
        }
        if type_key in CYAN_STRUCTURE and experimental:
            atlas["die_types"][type_key]["cyan_structural_metadata"] = CYAN_STRUCTURE[type_key]

    # Quick stats
    n_types = len(atlas["die_types"])
    n_with_bp = sum(1 for t in atlas["die_types"].values()
                    if t["feature_inventory"]["bond_pads"])
    n_with_se = sum(1 for t in atlas["die_types"].values()
                    if t["feature_inventory"]["slanted_edge"])
    n_with_exp = sum(1 for t in atlas["die_types"].values()
                     if t["feature_inventory"]["experimental"])
    total_bp = sum(len(t["feature_inventory"]["bond_pads"])
                   for t in atlas["die_types"].values())
    total_se = sum(len(t["feature_inventory"]["slanted_edge"])
                   for t in atlas["die_types"].values())
    total_exp = sum(len(t["feature_inventory"]["experimental"])
                    for t in atlas["die_types"].values())

    atlas["statistics"] = {
        "n_die_types": n_types,
        "n_types_with_bond_pads": n_with_bp,
        "n_types_with_slanted_edge": n_with_se,
        "n_types_with_experimental": n_with_exp,
        "total_bond_pad_components": total_bp,
        "total_slanted_edge_components": total_se,
        "total_experimental_components": total_exp,
    }

    OUT_PATH.write_text(json.dumps(atlas, indent=2,
                                    default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o)))
    print(f"Saved canonical atlas: {OUT_PATH}")
    print()
    print(f"Coverage: {n_types} die types described")
    print(f"  with bond pads:      {n_with_bp:2d} types ({total_bp} components)")
    print(f"  with slanted edge:   {n_with_se:2d} types ({total_se} components)")
    print(f"  with experimental:   {n_with_exp:2d} types ({total_exp} components)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
