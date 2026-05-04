#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import PosixPath
import argparse

magnifications = {}

def main():
    parser = argparse.ArgumentParser(description="Generate HTML to display crops organized by lens, magnification, and aperture.")
    parser.add_argument("path", type=PosixPath, help="Path to all crops", default=PosixPath("."), nargs="?")
    parser.add_argument("--round", type=float, default=0.0, help="Round magnifications to nearest value")
    args = parser.parse_args()
    path : PosixPath = args.path
    for lens in path.iterdir():
        if lens.name.startswith("results"):
            continue
        if lens.name[0] == lens.name[0].lower() or lens.name[0].isdigit():
            continue
        for magnification in lens.iterdir():
            for focal_length in magnification.iterdir():
                for aperture in focal_length.iterdir():
                    # print(f"Processing {aperture}")
                    if (aperture / "cropped").is_dir():
                        for crop in (aperture / "cropped").iterdir():
                            cropped_file = PosixPath(crop / "pick.jpg")
                            if cropped_file.is_file():
                                parsed_magnification, suffix = parse_magnification(magnification.name)
                                magnifications.setdefault((round_magnification(parsed_magnification, args.round), suffix), {}).setdefault(crop.name, {}).setdefault(aperture.name, {})[f"{lens.name} @ {focal_length.name}"] = cropped_file
    # Call the function after populating crops
    render_crops_html(magnifications)

def render_crops_html(magnifications):
    for magnificiation in sorted(magnifications.keys()):
        crops = magnifications[magnificiation]
        magnification_value, suffix = magnificiation
        print(f"<h2>{format_magnification(magnification_value)} {suffix}</h2>")
        for crop_type, apertures in sorted(crops.items()):
            print(f"<h3>{crop_type}</h3>")
            lens_types = sorted({lens for aperture in apertures.values() for lens in aperture.keys()})
            # Sort apertures numerically (e.g., F2.8, F11)
            def aperture_key(a):
                try:
                    return float(a[1:])  # assumes format "F2.8"
                except Exception:
                    return a
            sorted_apertures = sorted(apertures.keys(), key=aperture_key)
            print("<table>")
            print("<tr><th>Aperture</th>" + "".join(f"<th>{lens}</th>" for lens in lens_types) + "</tr>")
            for aperture in sorted_apertures:
                print(f"<tr><td>{aperture}</td>", end="")
                lens_files = apertures[aperture]
                for lens in lens_types:
                    file = lens_files.get(lens)
                    if file:
                        print(f"<td><img src='{file}' alt='{file.name}' title='{lens} {aperture}'></td>", end="")
                    else:
                        print("<td></td>", end="")
                print("</tr>")
            print("</table>")

def round_magnification(magnification: float, round_by: float) -> float:
    if round_by <= 0.0:
        return magnification
    return round((magnification - (round_by / 2)) / round_by) * round_by

def parse_magnification(magnification_str: str) -> tuple[float, str]:
    # Magnification is expected to be in the format 1_1, 1.4_1, 1_1.4 etc, where _ is the replacing the : symbol, so 1_1 means 1:1, 1.4_1 means 1.4:1, and 1_1.4 means 1:1.4
    # In addition, magnification can have a suffix like 1_1-resized or 2_1-resized. This suffix should be returned in the string part of the tuple.
    suffix = ""
    if "-" in magnification_str:
        magnification_str, suffix = magnification_str.split("-", 1)
    if "_" in magnification_str:
        parts = magnification_str.split("_")
        if len(parts) == 2:
            try:
                num = float(parts[0])
                denom = float(parts[1])
                if denom != 0:
                    return num / denom, suffix
            except ValueError:
                pass
    return 0.0, suffix

def format_magnification(value: float) -> str:
    """Convert numeric magnification to ratio format (e.g., 1.0 → '1:1', 0.5 → '1:2', 2.0 → '2:1')"""
    if value >= 1.0:
        # Format as X:1 (e.g., 1:1, 1.13:1, 2:1)
        # Use :g to remove trailing zeros
        return f"{value:g}:1"
    else:
        # Format as 1:X (e.g., 1:2 for 0.5, 1:1.5 for 0.666...)
        return f"1:{1/value:g}"

if __name__ == "__main__":
    main()
