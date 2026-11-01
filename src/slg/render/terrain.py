"""Platforms as organic growths or cut glass — not rectangles.

Each platform is baked once into a Surface. Organic platforms get noisy edges,
rot patches, a pale rim and hanging strands; glass platforms get faceted,
angular silhouettes and blinding glints. Per-frame it's a single blit.
"""

from __future__ import annotations

import numpy as np
import pygame

from slg.core.world import Platform
from slg.render.palette import PALETTE

_PAD = 28


def _edge_noise(count: int, amp: float, rng: np.random.Generator) -> np.ndarray:
    """Smooth random offsets for an edge polyline."""
    raw = rng.random(count + 2).astype(np.float32) * 2.0 - 1.0
    # smooth with a small kernel so edges look grown, not jagged
    kernel = np.array([0.25, 0.5, 0.25], dtype=np.float32)
    smooth = np.convolve(raw, kernel, mode="same")
    return smooth[:count] * amp


class TerrainRenderer:
    def __init__(self, platforms: list[Platform], rng_seed: int = 4242) -> None:
        self._rng = np.random.default_rng(rng_seed)
        self._baked: list[tuple[Platform, pygame.Surface, tuple[int, int]]] = [
            (p, *self._bake_platform(p)) for p in platforms
        ]

    def _bake_platform(self, p: Platform) -> tuple[pygame.Surface, tuple[int, int]]:
        if not p.organic:
            return self._bake_glass(p)
        rng = self._rng
        w = int(p.width) + _PAD * 2
        h = int(p.height) + _PAD
        surf = pygame.Surface((w, h), pygame.SRCALPHA)

        pts_top = max(6, int(p.width // 40) + 4)
        pts_bot = pts_top

        # --- organic outline ---
        top_noise = _edge_noise(pts_top, 7.0, rng)
        bot_noise = _edge_noise(pts_bot, 9.0, rng)
        left_mid = p.height * 0.5 + float(rng.random() * 10 - 5)
        right_mid = p.height * 0.5 + float(rng.random() * 10 - 5)

        outline: list[tuple[float, float]] = []
        for i in range(pts_top):
            t = i / (pts_top - 1)
            x = _PAD + t * p.width
            outline.append((x, _PAD + top_noise[i]))
        outline.append((_PAD + p.width, _PAD + right_mid * 0.4))
        for i in range(pts_bot - 1, -1, -1):
            t = i / (pts_bot - 1)
            x = _PAD + t * p.width
            outline.append((x, _PAD + p.height - 4 + bot_noise[i]))
        outline.append((_PAD, _PAD + left_mid * 0.4))

        body = [(int(x), int(y)) for x, y in outline]
        pygame.draw.polygon(surf, PALETTE["terrain"], body)

        # --- rot / rust / moss patches ---
        patch_count = max(2, int(p.width * p.height / 26000))
        for _ in range(patch_count):
            px = _PAD + float(rng.random()) * p.width
            py = _PAD + 6 + float(rng.random()) * max(8, p.height - 16)
            r = 6 + float(rng.random()) * 16
            color = PALETTE[[key for key in ("rust", "moss", "rot")][int(rng.random() * 3)]]
            patch = pygame.Surface((int(r * 2), int(r * 2)), pygame.SRCALPHA)
            pygame.draw.ellipse(patch, (*color, 110), (0, 0, int(r * 2), int(r * 2)))
            surf.blit(patch, (int(px - r), int(py - r)))

        # --- pale bone rim along the top edge ---
        rim_pts = [(int(x), int(y + 1)) for x, y in outline[:pts_top]]
        if len(rim_pts) >= 2:
            pygame.draw.lines(surf, PALETTE["terrain_rim"], False, rim_pts, 3)

        # --- spore tufts on the rim ---
        tufts = max(2, int(p.width // 90))
        for i in range(tufts):
            t = (i + 0.5) / tufts
            x = _PAD + t * p.width
            y = _PAD + float(np.interp(t, [j / (pts_top - 1) for j in range(pts_top)], top_noise))
            hgt = 5 + float(rng.random()) * 9
            pygame.draw.line(surf, PALETTE["spore_dim"], (x, y - 2), (x - 2, y - 2 - hgt), 2)
            pygame.draw.line(surf, PALETTE["spore_dim"], (x, y - 2), (x + 3, y - 1 - hgt * 0.7), 2)

        # --- hanging strands below ---
        strands = max(2, int(p.width // 130))
        for i in range(strands):
            t = (i + 0.35) / strands
            x = _PAD + t * p.width
            y0 = _PAD + p.height - 4
            length = 10 + float(rng.random()) * 26
            sway = float(rng.random() * 8 - 4)
            pygame.draw.line(surf, PALETTE["moss"], (x, y0),
                             (x + sway, y0 + length), 2)
            pygame.draw.circle(surf, PALETTE["spore_dim"],
                               (int(x + sway), int(y0 + length)), 2)

        return surf, (int(p.x) - _PAD, int(p.y) - _PAD)

    def _bake_glass(self, p: Platform) -> tuple[pygame.Surface, tuple[int, int]]:
        """Faceted, angular slab of fused sand. No moss, no strands."""
        rng = self._rng
        w = int(p.width) + _PAD * 2
        h = int(p.height) + _PAD
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        top = _PAD
        bottom = _PAD + p.height
        left = _PAD
        right = _PAD + p.width

        # --- angular outline: near-flat walkable top, slanted facets below ---
        steps = max(3, int(p.width // 80) + 3)
        top_pts: list[tuple[float, float]] = []
        for i in range(steps):
            t = i / (steps - 1)
            jag = 0.0 if i % 2 == 0 else -2.0
            top_pts.append((left + t * p.width, top + jag))
        outline: list[tuple[float, float]] = list(top_pts)
        facets = 3
        for i in range(1, facets + 1):
            t = i / facets
            x = right - p.width * 0.06 * (facets - i) * 0.4
            y = top + p.height * t
            outline.append((x, y))
        for i in range(facets - 1, 0, -1):
            t = i / facets
            x = left + p.width * 0.05 * (facets - i) * 0.4
            y = top + p.height * t
            outline.append((x, y))

        body = [(int(x), int(y)) for x, y in outline]
        pygame.draw.polygon(surf, PALETTE["terrain"], body)

        # --- internal fracture lines (cold, faint) ---
        cracks = max(1, int(p.width * p.height / 60000))
        for _ in range(cracks):
            x0 = left + float(rng.random()) * p.width
            y0 = top + 8.0 + float(rng.random()) * max(6.0, p.height * 0.6)
            length = 12.0 + float(rng.random()) * 22.0
            pygame.draw.line(surf, PALETTE["layer_mid"],
                             (int(x0), int(y0)),
                             (int(min(right - 2, x0 + length)), int(y0 + length * 0.7)), 1)

        # --- diagonal glints (light caught inside the glass) ---
        glints = max(2, int(p.width // 90))
        for i in range(glints):
            x0 = left + (i + 0.5) / glints * p.width
            y0 = top + 7.0 + float(rng.random()) * max(4.0, p.height * 0.25)
            ln = 8.0 + float(rng.random()) * 10.0
            pygame.draw.line(surf, PALETTE["bone"],
                             (int(x0), int(y0)), (int(x0 + ln * 0.6), int(y0 + ln)), 1)

        # --- blinding crystal rim along the walkable top ---
        rim_pts = [(int(x), int(y + 1)) for x, y in top_pts]
        pygame.draw.lines(surf, PALETTE["terrain_rim"], False, rim_pts, 3)
        pygame.draw.lines(surf, PALETTE["spore"], False, rim_pts, 1)

        # --- sharp faces read as danger: bright vertical cut edges ---
        if p.sharp:
            y0 = top + 6
            y1 = bottom - 6
            pygame.draw.line(surf, PALETTE["spore"], (left + 1, y0), (left + 1, y1), 3)
            pygame.draw.line(surf, PALETTE["spore"], (right - 1, y0), (right - 1, y1), 3)
            pygame.draw.line(surf, PALETTE["terrain_rim"], (left + 3, y0), (left + 3, y1), 1)
            pygame.draw.line(surf, PALETTE["terrain_rim"], (right - 3, y0), (right - 3, y1), 1)

        return surf, (int(p.x) - _PAD, int(p.y) - _PAD)

    def draw(self, surface: pygame.Surface, world_platforms: list[Platform],
             to_screen, skip: set[int] | None = None) -> None:
        """Blit baked platforms; draw any dynamic platform (boss gate) raw.

        `skip` optionally hides baked platforms by index (used by the level
        editor while a platform is being dragged).
        """
        baked_ids = {id(p) for p, _s, _o in self._baked}
        for index, (p, surf, origin) in enumerate(self._baked):
            if skip and index in skip:
                continue
            sx, sy = to_screen(origin[0], origin[1], 0.0)
            surface.blit(surf, (sx, sy))
        for p in world_platforms:
            if id(p) in baked_ids:
                continue
            sx, sy = to_screen(p.x, p.y, 0.0)
            rect = pygame.Rect(sx, sy, int(p.width), int(p.height))
            pygame.draw.rect(surface, PALETTE["terrain"], rect)
            pygame.draw.line(surface, PALETTE["danger"], rect.topleft, rect.topright, 2)
