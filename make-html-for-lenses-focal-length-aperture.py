#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import PosixPath
import argparse

focal_lengths = {}

def main():
    parser = argparse.ArgumentParser(description="Generate HTML to display crops organized by lens, focal length, and aperture.")
    parser.add_argument("path", type=PosixPath, help="Path to all crops", default=PosixPath("."), nargs="?")
    parser.add_argument("--round", type=float, default=0.0, help="Round focal lengths to nearest value")
    args = parser.parse_args()
    path : PosixPath = args.path
    for lens in path.iterdir():
        if lens.name.startswith("results"):
            continue
        if lens.name[0] == lens.name[0].lower() or lens.name[0].isdigit():
            continue
        for focal_length in lens.iterdir():
            for aperture in focal_length.iterdir():
                # print(f"Processing {aperture}")
                for crop in (aperture / "cropped").iterdir():
                    # cropped_file = next(crop.glob("*.jpg"))
                    cropped_file = PosixPath(crop / "pick.jpg")
                    if cropped_file.is_file():
                        focal_lengths.setdefault(round_focal_length(focal_length.name, args.round), {}).setdefault(crop.name, {}).setdefault(aperture.name, {})[lens.name] = cropped_file
    # Call the function after populating crops
    render_crops_html(focal_lengths)

def render_crops_html(focal_lengths):
    for focal_length in sorted(focal_lengths.keys()):
        crops = focal_lengths[focal_length]
        print(f"<h2>{focal_length} mm</h2>")
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

def round_focal_length(focal_length: str, round_by: float) -> float:
    value = float(focal_length.replace("mm", ""))
    if round_by <= 0.0:
        return value
    return int(round(value / round_by) * round_by)

if __name__ == "__main__":
    main()
