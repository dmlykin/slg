"""Parallax background: fBm-noise silhouettes of growths, pre-rendered once.

Numpy noise is expensive per frame, so every layer is baked into a Surface at
level load; per-frame work is only a couple of blits.
"""

from __future__ import annotations

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

    LAYERS = (
        # (parallax factor, color key, threshold, base_freq, ridge, bottom_bias)
        (0.08, "layer_far", 0.56, 90, False, 0.55),
        (0.20, "layer_mid", 0.58, 70, True, 0.35),
        (0.38, "layer_near", 0.60, 55, True, 0.20),
        (0.62, "layer_nearest", 0.62, 40, False, 0.10),
    )

    def __init__(self, bounds: tuple[float, float, float, float],
                 rng_seed: int = 1337) -> None:
        rng = np.random.default_rng(rng_seed)
        left, _top, width, _h = bounds
        self._sky = self._bake_sky()
        self._layers: list[tuple[float, pygame.Surface, int]] = []
        for factor, color_key, threshold, freq, ridge, bias in self.LAYERS:
            # wide enough to cover the whole camera range at this parallax
            layer_w = int(factor * (width - SCREEN_W / 2.0)) + SCREEN_W + 64
            surf = _bake_layer(layer_w, SCREEN_H, PALETTE[color_key], rng,
                               threshold, freq, ridge, bias)
            self._layers.append((factor, surf, layer_w))

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
        for factor, layer, layer_w in self._layers:
            offset = -projection.parallax_offset(factor)
            # tile horizontally if a layer is narrower than the screen
            x = offset % layer_w if layer_w < SCREEN_W else offset
            surface.blit(layer, (x, 0))
            if layer_w < SCREEN_W:
                surface.blit(layer, (x - layer_w, 0))
            elif x + layer_w < SCREEN_W:
                surface.blit(layer, (x + layer_w, 0))
