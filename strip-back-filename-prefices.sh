#!/bin/bash
ls *.nef *.jpg|while read f; do mv -i "$f" "${f##*|}";done
