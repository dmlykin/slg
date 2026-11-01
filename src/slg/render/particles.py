"""Particles: drifting spores and ash (ambient), impact sparks, death bursts.

The only per-frame numpy-free effect layer — everything else is baked.
"""

from __future__ import annotations

import math
import random

import pygame

from slg.render.palette import PALETTE


class Particles:
    MAX_PARTICLES = 420

    def __init__(self) -> None:
        self._parts: list[dict] = []
        self._rng = random.Random(7)
        self._cam_w = 1280
        self._cam_h = 720

    # ------------------------------------------------------------------ spawn

    def _add(self, x, y, vx, vy, life, color, size, gravity=0.0, fade=True) -> None:
        if len(self._parts) >= self.MAX_PARTICLES:
            return
        self._parts.append({
            "x": x, "y": y, "vx": vx, "vy": vy, "life": life, "max": life,
            "color": color, "size": size, "g": gravity, "fade": fade,
        })

    def spawn_ambient(self, cam_x: float, cam_y: float, count: int = 3) -> None:
        """Spores drifting up and ash falling, within the camera view."""
        for _ in range(count):
            x = cam_x + self._rng.uniform(-80, self._cam_w + 80)
            y = cam_y + self._rng.uniform(-80, self._cam_h + 80)
            if self._rng.random() < 0.55:  # spore
                self._add(x, y, self._rng.uniform(-14, 6), self._rng.uniform(-26, -8),
                          self._rng.uniform(3.0, 7.0), PALETTE["spore_dim"],
                          self._rng.randint(1, 3), fade=False)
            else:  # ash
                self._add(x, y, self._rng.uniform(-10, 10), self._rng.uniform(14, 34),
                          self._rng.uniform(3.0, 8.0), (120, 116, 104),
                          self._rng.randint(1, 2), fade=False)

    def impact_burst(self, x: float, y: float, heavy: bool = False) -> None:
        n = 14 if heavy else 8
        for _ in range(n):
            ang = self._rng.uniform(0, math.tau)
            speed = self._rng.uniform(60, 260 if heavy else 170)
            self._add(x, y, math.cos(ang) * speed, math.sin(ang) * speed - 60,
                      self._rng.uniform(0.2, 0.5), PALETTE["bone"],
                      self._rng.randint(1, 3), gravity=500.0)

    def blood_burst(self, x: float, y: float) -> None:
        for _ in range(10):
            ang = self._rng.uniform(0, math.tau)
            speed = self._rng.uniform(40, 200)
            self._add(x, y, math.cos(ang) * speed, math.sin(ang) * speed - 40,
                      self._rng.uniform(0.3, 0.7), PALETTE["blood"],
                      self._rng.randint(2, 3), gravity=600.0)

    def heal_glow(self, x: float, y: float) -> None:
        for _ in range(12):
            ang = self._rng.uniform(0, math.tau)
            self._add(x, y, math.cos(ang) * 30, math.sin(ang) * 30 - 50,
                      self._rng.uniform(0.4, 0.9), PALETTE["heal_glow"],
                      self._rng.randint(1, 2), gravity=-40.0)

    def death_burst(self, x: float, y: float) -> None:
        for _ in range(22):
            ang = self._rng.uniform(0, math.tau)
            speed = self._rng.uniform(50, 300)
            self._add(x, y, math.cos(ang) * speed, math.sin(ang) * speed - 80,
                      self._rng.uniform(0.4, 1.1),
                      self._rng.choice((PALETTE["spore"], PALETTE["rot"], PALETTE["bone"])),
                      self._rng.randint(1, 3), gravity=300.0)

    def telegraph_puff(self, x: float, y: float) -> None:
        for _ in range(6):
            self._add(x + self._rng.uniform(-14, 14), y + self._rng.uniform(-10, 10),
                      self._rng.uniform(-20, 20), self._rng.uniform(-40, -10),
                      self._rng.uniform(0.3, 0.6), PALETTE["telegraph"],
                      self._rng.randint(1, 2))

    def spark_burst(self, x: float, y: float) -> None:
        """Glass splinters flying off a cut edge."""
        for _ in range(12):
            ang = self._rng.uniform(0, math.tau)
            speed = self._rng.uniform(80, 320)
            self._add(x, y, math.cos(ang) * speed, math.sin(ang) * speed - 70,
                      self._rng.uniform(0.15, 0.45), PALETTE["bone"],
                      self._rng.randint(1, 2), gravity=760.0)

    # ------------------------------------------------------------------ update

    def update(self, dt: float, cam_x: float, cam_y: float) -> None:
        self.spawn_ambient(cam_x, cam_y, count=2)
        for p in self._parts:
            p["life"] -= dt
            p["vy"] += p["g"] * dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
        self._parts = [p for p in self._parts if p["life"] > 0]

    def draw(self, surface: pygame.Surface, to_screen) -> None:
        for p in self._parts:
            alpha = 255
            if p["fade"]:
                alpha = int(255 * min(1.0, p["life"] / p["max"] * 2))
            x, y = to_screen(p["x"], p["y"], 0.0)
            if -20 <= x <= 1300 and -20 <= y <= 740:
                pygame.draw.circle(surface, (*p["color"], alpha), (x, y), p["size"])
