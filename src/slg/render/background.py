"""Parallax background: fBm-noise silhouettes of growths, pre-rendered once.

Numpy noise is expensive per frame, so every layer is baked into a Surface at
level load; per-frame work is only a couple of blits.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pygame

from slg.render.camera import SCREEN_H, SCREEN_W, SideProjection
from slg.render.palette import PALETTE


def _smoothstep(t: np.ndarray) -> np.ndarray:
    return t * t * (3.0 - 2.0 * t)


def value_noise(width: int, height: int, freq: int, rng: np.random.Generator) -> np.ndarray:
    """Tileable-in-feel value noise via bilinear interpolation of a random grid."""
    gw = int(np.ceil(width / freq)) + 2
    gh = int(np.ceil(height / freq)) + 2
    grid = rng.random((gh, gw), dtype=np.float32)
    ys = np.arange(height, dtype=np.float32) / freq
    xs = np.arange(width, dtype=np.float32) / freq
    yi = ys.astype(np.int32)
    xi = xs.astype(np.int32)
    yf = _smoothstep(ys - yi)
    xf = _smoothstep(xs - xi)
    g00 = grid[np.ix_(yi, xi)]
    g10 = grid[np.ix_(yi, xi + 1)]
    g01 = grid[np.ix_(yi + 1, xi)]
    g11 = grid[np.ix_(yi + 1, xi + 1)]
    top = g00 + (g10 - g00) * xf[None, :]
    bottom = g01 + (g11 - g01) * xf[None, :]
    return top + (bottom - top) * yf[:, None]


def fbm(width: int, height: int, base_freq: int, octaves: int,
        rng: np.random.Generator, ridge: bool = False) -> np.ndarray:
    """Fractal Brownian motion; optionally ridged for spiky organic growths."""
    total = np.zeros((height, width), dtype=np.float32)
    amp = 1.0
    freq = base_freq
    norm = 0.0
    for _ in range(octaves):
        n = value_noise(width, height, freq, rng)
        if ridge:
            n = 1.0 - np.abs(n * 2.0 - 1.0)
        total += n * amp
        norm += amp
        amp *= 0.5
        freq *= 2
    return total / norm


def _bake_layer(width: int, height: int, color: tuple[int, int, int],
                rng: np.random.Generator, threshold: float, base_freq: int,
                ridge: bool, bottom_bias: float) -> pygame.Surface:
    """One silhouette layer: fbm field -> alpha mask -> colored Surface."""
    field = fbm(width, height, base_freq, 5, rng, ridge=ridge)
    ys = np.arange(height, dtype=np.float32) / height
    # bias: growths denser toward the bottom (roots) or top (hanging mass)
    field = field + (ys[:, None] - 0.5) * bottom_bias
    mask = (field > threshold).astype(np.uint8) * 255
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[:, :, 0] = color[0]
    arr[:, :, 1] = color[1]
    arr[:, :, 2] = color[2]
    arr[:, :, 3] = mask
    surf = pygame.image.frombuffer(arr.tobytes(), (width, height), "RGBA")
    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass  # no display yet — raw surface still works
    return surf


class Background:
    """3-4 baked parallax layers + a vertical sky gradient + drifting fog band."""

    LAYERS: ClassVar[tuple] = (
        # (parallax factor, color key, threshold, base_freq, ridge, bottom_bias)
        (0.08, "layer_far", 0.56, 90, False, 0.55),
        (0.20, "layer_mid", 0.58, 70, True, 0.35),
        (0.38, "layer_near", 0.60, 55, True, 0.20),
        (0.62, "layer_nearest", 0.62, 40, False, 0.10),
    )

    # Glass: ridged noise everywhere turns the growths into thin shard peaks.
    THEME_LAYERS: ClassVar[dict] = {
        "glass": (
            (0.08, "layer_far", 0.66, 120, True, 0.60),
            (0.20, "layer_mid", 0.68, 96, True, 0.52),
            (0.38, "layer_near", 0.70, 76, True, 0.46),
            (0.62, "layer_nearest", 0.71, 58, True, 0.40),
        ),
        # The sanctum: calm, hanging veil-like masses drifting toward the top.
        "sanctum": (
            (0.08, "layer_far", 0.62, 70, False, -0.22),
            (0.20, "layer_mid", 0.64, 55, True, -0.12),
            (0.38, "layer_near", 0.66, 44, True, -0.05),
            (0.62, "layer_nearest", 0.68, 34, False, 0.06),
        ),
    }

    # Vertical levels (a well shaft): horizontal rock strata instead of
    # horizon silhouettes; each is tiled vertically with its own parallax.
    VERTICAL_LAYERS: ClassVar[tuple] = (
        (0.10, "layer_far"),
        (0.22, "layer_mid"),
        (0.40, "layer_near"),
        (0.62, "layer_nearest"),
    )

    def __init__(self, bounds: tuple[float, float, float, float],
                 rng_seed: int = 1337, theme: str = "swamp",
                 vertical: bool = False) -> None:
        rng = np.random.default_rng(rng_seed)
        _left, _top, width, _h = bounds
        self.vertical = vertical
        self._sky = self._bake_sky()
        self._layers: list[tuple[float, pygame.Surface, int]] = []
        self._vertical_layers: list[tuple[float, pygame.Surface]] = []
        if vertical:
            # Do not bake the whole shaft: a single screen-sized strata tile
            # per layer is tiled vertically with parallax.
            for factor, color_key in self.VERTICAL_LAYERS:
                surf = self._bake_vertical_layer(PALETTE[color_key], rng)
                self._vertical_layers.append((factor, surf))
            return
        layers = self.THEME_LAYERS.get(theme, self.LAYERS)
        for factor, color_key, threshold, freq, ridge, bias in layers:
            # wide enough to cover the whole camera range at this parallax
            layer_w = int(factor * (width - SCREEN_W / 2.0)) + SCREEN_W + 64
            surf = _bake_layer(layer_w, SCREEN_H, PALETTE[color_key], rng,
                               threshold, freq, ridge, bias)
            self._layers.append((factor, surf, layer_w))

    @staticmethod
    def _bake_vertical_layer(color: tuple[int, int, int],
                             rng: np.random.Generator) -> pygame.Surface:
        """One tile of horizontal rock strata, seamless top-to-bottom."""
        surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        bands: list[tuple[int, int]] = []
        y = 0
        while y < SCREEN_H:
            h = int(rng.integers(18, 110))
            bands.append((y, h))
            y += h + int(rng.integers(10, 70))
        rim = tuple(min(255, int(c * 1.5) + 10) for c in color)
        for y, h in bands:
            alpha = int(rng.integers(150, 220))
            for yy in (y - SCREEN_H, y, y + SCREEN_H):
                pygame.draw.rect(surf, (*color, alpha), (0, yy, SCREEN_W, h))
                pygame.draw.line(surf, (*rim, min(255, alpha + 20)),
                                 (0, yy), (SCREEN_W, yy), 2)
        # ragged vertical cracks that also wrap
        for _ in range(14):
            x = int(rng.integers(0, SCREEN_W))
            y0 = int(rng.integers(0, SCREEN_H))
            ln = int(rng.integers(30, 150))
            dx = int(rng.integers(-16, 16))
            for yy in (y0 - SCREEN_H, y0, y0 + SCREEN_H):
                pygame.draw.line(surf, (*color, 80), (x, yy), (x + dx, yy + ln), 2)
        return surf

    @staticmethod
    def _bake_sky() -> pygame.Surface:
        top = np.array(PALETTE["sky_top"], dtype=np.float32)
        bottom = np.array(PALETTE["sky_bottom"], dtype=np.float32)
        arr = np.zeros((SCREEN_H, SCREEN_W, 3), dtype=np.uint8)
        t = (np.arange(SCREEN_H, dtype=np.float32) / (SCREEN_H - 1))[:, None, None]
        grad = (top[None, None, :] * (1 - t) + bottom[None, None, :] * t)
        arr[:, :] = grad.astype(np.uint8)
        return pygame.image.frombuffer(arr.tobytes(), (SCREEN_W, SCREEN_H), "RGB")

    def draw(self, surface: pygame.Surface, projection: SideProjection) -> None:
        surface.blit(self._sky, (0, 0))
        if self.vertical:
            for factor, layer in self._vertical_layers:
                offset = -projection.parallax_offset_y(factor)
                y = offset % SCREEN_H
                surface.blit(layer, (0, y))
                surface.blit(layer, (0, y - SCREEN_H))
            return
        for factor, layer, layer_w in self._layers:
            offset = -projection.parallax_offset(factor)
            # tile horizontally if a layer is narrower than the screen
            x = offset % layer_w if layer_w < SCREEN_W else offset
            surface.blit(layer, (x, 0))
            if layer_w < SCREEN_W:
                surface.blit(layer, (x - layer_w, 0))
            elif x + layer_w < SCREEN_W:
                surface.blit(layer, (x + layer_w, 0))
