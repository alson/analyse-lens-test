#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import PosixPath
import argparse

crops = {}

def main():
    parser = argparse.ArgumentParser(description="Generate HTML to display crops organized by crop type and aperture.")
    parser.add_argument("path", type=PosixPath, help="Path to all crops", default=PosixPath("."), nargs="?")
    args = parser.parse_args()
    path = args.path
    for lens in path.iterdir():
        if lens.name.startswith("results"):
            continue
        for aperture in lens.iterdir():
            for crop in (aperture / "cropped").iterdir():
                cropped_file = crop / "pick.jpg"
                if cropped_file.is_file():
                    crops.setdefault(crop.name, {}).setdefault(aperture.name, {})[lens.name] = cropped_file
    # Call the function after populating crops
    render_crops_html(crops)

def render_crops_html(crops):
    for crop_type, apertures in crops.items():
        print(f"<h2>{crop_type}</h2>")
        print("<table>")
        # Collect all lens types for columns
        lens_types = sorted({lens for lens_files in apertures.values() for lens in lens_files.keys()})
        # Sort apertures numerically (e.g., F2.8, F11)
        def aperture_key(a):
            try:
                return float(a[1:])  # assumes format "F2.8"
            except Exception:
                return a
        sorted_apertures = sorted(apertures.keys(), key=aperture_key)
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

if __name__ == "__main__":
    main()
