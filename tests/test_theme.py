"""Theme palette: set_theme mutates the shared PALETTE in place."""

from __future__ import annotations

from slg.render.palette import PALETTE, THEMES, current_theme, set_theme


def test_set_theme_mutates_palette_in_place():
    live = PALETTE
    set_theme("glass")
    try:
        assert current_theme() == "glass"
        assert PALETTE is live
        assert PALETTE["terrain_rim"] == THEMES["glass"]["terrain_rim"]
        assert set(PALETTE) == set(THEMES["swamp"])
    finally:
        set_theme("swamp")
    assert current_theme() == "swamp"
    assert PALETTE["terrain_rim"] == THEMES["swamp"]["terrain_rim"]


def test_well_theme_has_parity_and_mutates_in_place():
    live = PALETTE
    set_theme("well")
    try:
        assert current_theme() == "well"
        assert PALETTE is live
        assert PALETTE["terrain_rim"] == THEMES["well"]["terrain_rim"]
        assert set(PALETTE) == set(THEMES["swamp"])
    finally:
        set_theme("swamp")
    assert current_theme() == "swamp"


def test_sanctum_theme_has_parity_and_mutates_in_place():
    live = PALETTE
    set_theme("sanctum")
    try:
        assert current_theme() == "sanctum"
        assert PALETTE is live
        assert PALETTE["terrain_rim"] == THEMES["sanctum"]["terrain_rim"]
        assert set(PALETTE) == set(THEMES["swamp"])
    finally:
        set_theme("swamp")
    assert current_theme() == "swamp"
