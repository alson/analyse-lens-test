#!/usr/bin/env python3
import os
import re
from collections import defaultdict

# Regex to extract info from filename
# Assumes: first element is number, last element is alm-datetime-seq
# Makes no assumptions about what's in between
pattern = re.compile(
    r'^(?P<num>\d+)\|(?P<middle>.*)\|alm-(?P<datetime>\d{8}-\d{6})-(?P<seq>\d+)(?P<rest>\..*)?$'
)

# Gather files and group by base (ignoring extension)
files = [f for f in os.listdir('.') if os.path.isfile(f)]
groups = defaultdict(list)

for fname in files:
    m = pattern.match(fname)
    if m:
        base = f"alm-{m.group('datetime')}-{m.group('seq')}"
        groups[base].append(fname)

# Sort groups by date, time, sequence
sorted_groups = sorted(
    groups.items(),
    key=lambda x: tuple(map(int, re.findall(r'(\d{8})-(\d{6})-(\d+)', x[0])[0]))
)

# Renumber and rename
for idx, (base, fnames) in enumerate(sorted_groups, 1):
    new_num = f"{idx:05d}"
    for fname in fnames:
        m = pattern.match(fname)
        if m:
            new_fname = (
                f"{new_num}|{m.group('middle')}|alm-"
                f"{m.group('datetime')}-{m.group('seq')}{m.group('rest') or ''}"
            )
            if fname != new_fname:
                print(f"Renaming: {fname} -> {new_fname}")
                os.rename(fname, new_fname)