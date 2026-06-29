"""Unit tests for the pure helpers in ``rename_and_sort_lens_test``.
No filesystem / exiv2 I/O — values mirror real Exiv2 translated output.

Run: ``pytest test_rename_and_sort_lens_test.py``
"""

import pytest

from rename_and_sort_lens_test import (
    _parse_exiv2,
    build_name,
    format_lens_field,
)


# --- lens field: native (LensModel wins, carries Z TC) ---------------------

def test_lens_field_native_with_tc():
    assert format_lens_field(
        "NIKKOR Z 100-400mm f/4.5-5.6 VR S Z TC-2.0x", "(0)", "8000"
    ) == "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x ISO8000"


def test_lens_field_native_bare():
    assert format_lens_field(
        "NIKKOR Z 100-400mm f/4.5-5.6 VR S", "(0)", "100"
    ) == "NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO100"


# --- lens field: adapted F-mount (LensModel blank → translated LensID) -----

def test_lens_field_adapted_uses_translated_lensid_name():
    # Reproduces the real 2026-01 AF-S 300 PF folder (validated against EXIF).
    assert format_lens_field(
        "", "Nikon AF-S Nikkor 300mm f/4E PF ED VR", "8000"
    ) == "Nikon AF-S Nikkor 300mm f_4E PF ED VR ISO8000"


@pytest.mark.parametrize("lid", ["", "0", "(0)"])
def test_lens_field_raises_when_no_identity(lid):
    with pytest.raises(ValueError):
        format_lens_field("", lid, "100")


# --- build_name ------------------------------------------------------------

def test_build_name_lowercases_original_keeps_ext():
    assert build_name(
        1, "NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO100", "400.0 mm", "F5.6",
        "ALM-20260628-120000-001.NEF",
    ) == (
        "00001|NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO100|400.0 mm|F5.6|"
        "alm-20260628-120000-001.nef"
    )


# --- exiv2 output parsing (prefix disambiguation) --------------------------

def test_parse_exiv2_disambiguates_focal_length_prefix():
    text = (
        "Exif.Photo.FNumber                            F16\n"
        "Exif.Photo.ISOSpeedRatings                    8000\n"
        "Exif.Photo.FocalLength                        400.0 mm\n"
        "Exif.NikonLd4.LensIDNumber                    (0)\n"
        "Exif.Photo.FocalLengthIn35mmFilm              400.0 mm\n"
        "Exif.Photo.LensModel                          NIKKOR Z 100-400mm f/4.5-5.6 VR S Z TC-2.0x\n"
    )
    got = _parse_exiv2(text)
    assert got["Exif.Photo.FocalLength"] == "400.0 mm"   # not the In35mmFilm line
    assert got["Exif.Photo.FNumber"] == "F16"
    assert got["Exif.Photo.LensModel"].endswith("Z TC-2.0x")
    assert got["Exif.NikonLd4.LensIDNumber"] == "(0)"


def test_parse_exiv2_empty_lensmodel_line():
    text = "Exif.Photo.LensModel                          \n"
    assert _parse_exiv2(text)["Exif.Photo.LensModel"] == ""
