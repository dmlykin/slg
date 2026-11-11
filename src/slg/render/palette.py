"""Decay palette shared by all render modules.

`PALETTE` is the live theme dictionary. Importers hold the same dict object,
so `set_theme()` mutates it in place and every module sees the new colors.
"""

from __future__ import annotations

# Dying world: ash, rot, rust, bone. No man-made colors.
SWAMP = {
    "sky_top": (24, 30, 24),
    "sky_bottom": (44, 38, 26),
    "fog": (52, 56, 40),
    "layer_far": (40, 46, 34),
    "layer_mid": (32, 37, 27),
    "layer_near": (23, 27, 20),
    "layer_nearest": (16, 19, 14),
    "terrain": (19, 22, 16),
    "terrain_rim": (122, 128, 92),
    "rust": (94, 56, 36),
    "moss": (58, 74, 44),
    "rot": (74, 82, 46),
    "bone": (196, 189, 160),
    "spore": (159, 179, 90),
    "spore_dim": (96, 110, 56),
    "blood": (120, 34, 30),
    "stamina": (110, 130, 70),
    "flesh_dark": (13, 15, 11),
    "silhouette": (10, 12, 9),
    "rim": (64, 72, 52),
    "eyes": (216, 232, 150),
    "eyes_boss": (210, 90, 60),
    "telegraph": (220, 170, 80),
    "danger": (190, 60, 40),
    "heal_glow": (170, 220, 140),
    "density": (198, 158, 96),
    "ui_dim": (30, 34, 26),
    "ui_text": (196, 189, 160),
}

# Vitrified desert: white-hot sky over an orange horizon, near-black cold
# shard silhouettes, blinding glints on cut glass.
GLASS = {
    "sky_top": (232, 238, 246),
    "sky_bottom": (250, 148, 66),
    "fog": (238, 178, 120),
    "layer_far": (62, 56, 68),
    "layer_mid": (44, 41, 54),
    "layer_near": (30, 29, 40),
    "layer_nearest": (18, 18, 27),
    "terrain": (24, 26, 38),
    "terrain_rim": (238, 248, 255),
    "rust": (146, 88, 52),
    "moss": (46, 82, 96),
    "rot": (52, 68, 92),
    "bone": (220, 236, 248),
    "spore": (168, 232, 244),
    "spore_dim": (96, 148, 164),
    "blood": (142, 40, 44),
    "stamina": (138, 206, 214),
    "flesh_dark": (12, 14, 21),
    "silhouette": (8, 10, 15),
    "rim": (128, 160, 182),
    "eyes": (198, 242, 255),
    "eyes_boss": (255, 104, 84),
    "telegraph": (255, 232, 158),
    "danger": (252, 78, 58),
    "heal_glow": (162, 232, 230),
    "density": (224, 190, 128),
    "ui_dim": (32, 36, 48),
    "ui_text": (220, 236, 246),
}

# Drowned shaft: wet stone swallowing the light, a bone-pale lip, dim teal
# spores and a nearly black bottom.
WELL = {
    "sky_top": (6, 8, 10),
    "sky_bottom": (18, 24, 26),
    "fog": (24, 32, 32),
    "layer_far": (26, 34, 34),
    "layer_mid": (18, 25, 26),
    "layer_near": (12, 18, 19),
    "layer_nearest": (6, 9, 10),
    "terrain": (14, 18, 18),
    "terrain_rim": (104, 126, 118),
    "rust": (92, 58, 42),
    "moss": (42, 68, 56),
    "rot": (58, 70, 54),
    "bone": (190, 202, 188),
    "spore": (116, 176, 162),
    "spore_dim": (68, 108, 102),
    "blood": (104, 30, 30),
    "stamina": (108, 144, 128),
    "flesh_dark": (8, 10, 11),
    "silhouette": (4, 6, 7),
    "rim": (56, 72, 68),
    "eyes": (190, 226, 206),
    "eyes_boss": (224, 96, 68),
    "telegraph": (226, 180, 100),
    "danger": (198, 64, 48),
    "heal_glow": (150, 218, 194),
    "density": (176, 152, 104),
    "ui_dim": (22, 28, 30),
    "ui_text": (192, 208, 200),
}

# The sanctum hub: pale stone in candle-warm light, air that waits. Faces of
# the Three-Faced glow like banked embers; nothing here is hostile.
SANCTUM = {
    "sky_top": (26, 24, 30),
    "sky_bottom": (60, 50, 40),
    "fog": (66, 58, 48),
    "layer_far": (54, 47, 42),
    "layer_mid": (43, 38, 34),
    "layer_near": (32, 28, 25),
    "layer_nearest": (22, 19, 17),
    "terrain": (27, 23, 20),
    "terrain_rim": (206, 180, 138),
    "rust": (122, 80, 48),
    "moss": (88, 84, 56),
    "rot": (98, 88, 58),
    "bone": (216, 202, 170),
    "spore": (236, 198, 128),
    "spore_dim": (142, 120, 84),
    "blood": (130, 42, 34),
    "stamina": (172, 150, 94),
    "flesh_dark": (17, 14, 12),
    "silhouette": (12, 10, 9),
    "rim": (124, 105, 78),
    "eyes": (242, 216, 152),
    "eyes_boss": (222, 122, 70),
    "telegraph": (230, 192, 112),
    "danger": (198, 72, 48),
    "heal_glow": (202, 228, 172),
    "density": (214, 176, 112),
    "ui_dim": (38, 32, 27),
    "ui_text": (216, 202, 170),
}

THEMES = {"swamp": SWAMP, "glass": GLASS, "well": WELL, "sanctum": SANCTUM}

_current = "swamp"
PALETTE = dict(SWAMP)


def set_theme(name: str) -> None:
    """Switch the live palette in place (all importers see the change)."""
    global _current
    PALETTE.update(THEMES.get(name, SWAMP))
    _current = name if name in THEMES else "swamp"


def current_theme() -> str:
    return _current
