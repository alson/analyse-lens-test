#!/bin/sh
exiftool '-filename<00000|${LensModel;tr/\//_/}|$FocalLength|F$FNumber|$FileName' alm*.jpg alm*.nef