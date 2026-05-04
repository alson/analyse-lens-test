#!/bin/bash

for fn in *\|*\|*.*; do
    # Split filename by pipe character
    IFS='|' read -ra parts <<< "$fn"
    
    # Remove trailing 0 from lens name (second component, index 1)
    lens="${parts[1]}"
    if [[ "$lens" == *0 ]]; then
        parts[1]="${lens%0}"
    fi
    
    # Reconstruct filename
    new_fn=$(IFS='|'; echo "${parts[*]}")
    
    # Rename if different
    if [ "$fn" != "$new_fn" ]; then
        mv "$fn" "$new_fn"
    fi
done