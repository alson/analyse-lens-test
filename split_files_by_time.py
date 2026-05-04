#!/usr/bin/env python3
import os
import re
import shutil
import argparse


def extract_time(filename):
    # Extract the time part (HHMMSS) from the filename
    match = re.search(r"alm-\d{8}-(\d{6})-\d+", filename)
    if match:
        tstr = match.group(1)
        h, m, s = int(tstr[:2]), int(tstr[2:4]), int(tstr[4:6])
        return h * 3600 + m * 60 + s
    return None


def extract_basename(filename):
    # Remove extension(s) for grouping (e.g. .jpg, .nef, .jpg.xmp)
    return re.sub(r"(\.[^.]+)+$", "", filename)


def group_files_by_time(files, max_normal_gap=25):
    # Sort files by time
    files_with_time = []
    for f in files:
        t = extract_time(f)
        if t is not None:
            files_with_time.append((f, t))
    files_with_time.sort(key=lambda x: x[1])

    groups = []
    current_group = []
    last_time = None

    for f, t in files_with_time:
        if last_time is not None and ((t - last_time) % (24 * 3600)) > max_normal_gap:
            if current_group:
                groups.append(current_group)
                current_group = []
        current_group.append(f)
        last_time = t
    if current_group:
        groups.append(current_group)
    return groups


def collect_related_files(files):
    # Group files by their basename (without extension)
    related = {}
    for f in files:
        base = extract_basename(f)
        related.setdefault(base, []).append(f)
    return related


def main():
    parser = argparse.ArgumentParser(
        description='Split files into groups based on time gaps between captures'
    )
    parser.add_argument(
        '--max-normal-gap',
        type=int,
        default=25,
        help='Maximum time gap in seconds between consecutive files in the same group (default: 25)'
    )
    args = parser.parse_args()
    
    files = [f for f in os.listdir(".") if os.path.isfile(f)]
    related = collect_related_files(files)
    # Use one file per group for time grouping
    representative_files = [min(group, key=len) for group in related.values()]
    groups = group_files_by_time(representative_files, max_normal_gap=args.max_normal_gap)

    for idx, group in enumerate(groups, 1):
        dir_name = f"group_{idx:03d}"
        os.makedirs(dir_name, exist_ok=True)
        for rep_file in group:
            base = extract_basename(rep_file)
            for f in related[base]:
                shutil.move(f, os.path.join(dir_name, f))


if __name__ == "__main__":
    main()
