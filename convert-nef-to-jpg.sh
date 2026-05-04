#!/bin/sh

find . -type f -name "*.nef" | while read file; do
    exiftool -b -JpgFromRaw -w .jpg "$file"
done