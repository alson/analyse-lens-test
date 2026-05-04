#!/bin/bash
old_lens_name="$1"
new_lens_name="$2"

if [ -z "$old_lens_name" ] || [ -z "$new_lens_name" ]; then
    echo "Usage: $0 <old_lens_name> <new_lens_name>"
    exit 1
fi

ls *\|"$old_lens_name"* | while read fn; do 
    mv "$fn" "${fn/\|$old_lens_name\|/\|$new_lens_name\|}"
done
