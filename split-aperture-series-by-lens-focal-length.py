#!/usr/bin/env python3
import os
import re
from pathlib import Path
from collections import defaultdict

def parse_filename(filename):
    """Parse filename and extract relevant fields."""
    parts = filename.split('|')
    if len(parts) < 5:
        return None
    
    id_num = parts[0]
    lens = parts[1]
    focal_length = parts[2].strip()
    aperture = parts[3].strip()
    
    # Extract aperture value (e.g., F5.6 -> 5.6)
    aperture_match = re.match(r'F(\d+\.?\d*)', aperture)
    if not aperture_match:
        return None
    
    aperture_value = float(aperture_match.group(1))
    
    # Get basename without extension
    basename = '|'.join(parts)
    basename = os.path.splitext(basename)[0]
    
    return {
        'id': id_num,
        'lens': lens,
        'focal_length': focal_length,
        'aperture': aperture,
        'aperture_value': aperture_value,
        'basename': basename,
        'filename': filename
    }

def group_into_series(files_info):
    """Group files into series based on lens, focal length, and aperture progression."""
    # Group by lens and focal length
    groups = defaultdict(list)
    for info in files_info:
        key = (info['lens'], info['focal_length'])
        groups[key].append(info)
    
    # Sort each group by filename to maintain order
    for key in groups:
        groups[key].sort(key=lambda x: x['filename'])
    
    # Split into series based on aperture progression
    series = []
    for key, group in groups.items():
        current_series = []
        prev_aperture = -1
        
        for info in group:
            # If aperture decreased, start new series
            if info['aperture_value'] < prev_aperture:
                if current_series:
                    series.append(current_series)
                current_series = [info]
            else:
                current_series.append(info)
            
            prev_aperture = info['aperture_value']
        
        if current_series:
            series.append(current_series)
    
    return series

def sanitize_folder_name(name):
    """Remove invalid characters from folder name."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)

def main(directory='.'):
    # Get all files and build an index for fast lookup
    path = Path(directory)
    files_by_stem = {}  # Map stem -> list of file paths
    all_files = []
    
    for f in path.iterdir():
        if f.is_file():
            stem = f.stem
            if stem not in files_by_stem:
                files_by_stem[stem] = []
            files_by_stem[stem].append(f)
            
            if '|' in f.name:
                all_files.append(f.name)
    
    # Parse filenames
    files_info = []
    for filename in all_files:
        info = parse_filename(filename)
        if info:
            files_info.append(info)
    
    if not files_info:
        print("No valid files found.")
        return
    
    # Group into series
    series_list = group_into_series(files_info)
    
    # Track series number for each lens+focal_length combination
    series_counter = defaultdict(int)
    
    # Create folders and move files
    for series_files in series_list:
        if not series_files:
            continue
        
        # Get series info from first file
        first = series_files[0]
        lens = first['lens']
        focal_length = first['focal_length']
        
        # Increment series number
        key = (lens, focal_length)
        series_counter[key] += 1
        series_num = series_counter[key]
        
        # Create folder name
        folder_name = f"{sanitize_folder_name(lens)}_{focal_length}_{series_num:03d}"
        folder_path = path / folder_name
        folder_path.mkdir(exist_ok=True)
        
        # Get unique basenames (to handle multiple extensions)
        basenames = set(f['basename'] for f in series_files)
        
        # Move all files with these basenames using the index
        for basename in basenames:
            # Look up files with this stem in our index
            stem = basename  # basename already has extension removed
            matched_files = files_by_stem.get(stem, [])
            
            for file in matched_files:
                # Check if file still exists at this location (not moved yet)
                if file.exists():
                    dest = folder_path / file.name
                    print(f"Moving {file.name} -> {folder_name}/")
                    file.rename(dest)
            
            # Remove from index to avoid processing again
            if stem in files_by_stem:
                del files_by_stem[stem]

if __name__ == '__main__':
    main()