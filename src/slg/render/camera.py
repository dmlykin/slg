"""Projection abstraction.

The core keeps world coordinates (x, y, z). A Projection maps them to screen
pixels. MVP ships SideProjection; TopDownProjection is an architectural stub
for future special locations (world plane x/z) — the core needs no changes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable



SCREEN_W = 1280
SCREEN_H = 720


@runtime_checkable
class Projection(Protocol):
    """How world space becomes screen space."""

    def world_to_screen(self, x: float, y: float, z: float) -> tuple[int, int]:
        ...

    def camera_center(self) -> tuple[float, float]:
        ...


class SideProjection:
    """Side view: camera follows a target, clamped to level bounds."""

    def __init__(self, bounds: tuple[float, float, float, float],
                 screen_size: tuple[int, int] = (SCREEN_W, SCREEN_H),
                 smooth: float = 6.0, vertical_bias: float = -60.0) -> None:
        self.bounds = bounds
        self.screen_w, self.screen_h = screen_size
        self.smooth = smooth
        self.vertical_bias = vertical_bias
        left, top, width, height = bounds
        self._cam_x = left + width / 2.0
        self._cam_y = top + height / 2.0
        self._look_ahead = 0.0

    def update(self, dt: float, target_x: float, target_y: float, facing: int,
               target_vy: float = 0.0) -> None:
        self._look_ahead += (facing * 90.0 - self._look_ahead) * min(1.0, 2.0 * dt)
        desired_x = target_x + self._look_ahead
        lead = max(-80.0, min(160.0, target_vy * 0.10))
        desired_y = target_y + self.vertical_bias + lead
        k = min(1.0, self.smooth * dt)
        self._cam_x += (desired_x - self._cam_x) * k
        self._cam_y += (desired_y - self._cam_y) * k
        self._clamp()

    def snap_to(self, x: float, y: float) -> None:
        self._cam_x = x
        self._cam_y = y + self.vertical_bias
        self._look_ahead = 0.0
        self._clamp()

    def _clamp(self) -> None:
        left, top, width, height = self.bounds
        half_w = self.screen_w / 2.0
        half_h = self.screen_h / 2.0
        if width > self.screen_w:
            self._cam_x = max(left + half_w, min(left + width - half_w, self._cam_x))
        else:
            self._cam_x = left + width / 2.0
        if height > self.screen_h:
            self._cam_y = max(top + half_h, min(top + height - half_h, self._cam_y))
        else:
            self._cam_y = top + height / 2.0

    # -- Projection API --------------------------------------------------

    def world_to_screen(self, x: float, y: float, z: float) -> tuple[int, int]:
        return (
            int(round(x - self._cam_x + self.screen_w / 2.0)),
            int(round(y - self._cam_y + self.screen_h / 2.0)),
        )

    def camera_center(self) -> tuple[float, float]:
        return (self._cam_x, self._cam_y)

    def parallax_offset(self, factor: float) -> int:
        """Pixel offset for a background layer moving at `factor` of camera speed."""
        return int(round(self._cam_x * factor))

    def parallax_offset_y(self, factor: float) -> int:
        """Vertical counterpart for descending levels."""
        return int(round(self._cam_y * factor))


class TopDownProjection:
    """Stub for future top-down locations: projects the (x, z) plane."""

    def __init__(self, bounds: tuple[float, float, float, float],
                 screen_size: tuple[int, int] = (SCREEN_W, SCREEN_H)) -> None:
        self.bounds = bounds
        self.screen_w, self.screen_h = screen_size

    def world_to_screen(self, x: float, y: float, z: float) -> tuple[int, int]:
        raise NotImplementedError(
            "TopDownProjection is planned for special locations; "
            "the MVP renders the side view only (see plan: top-down is architecture-only)."
        )

    def camera_center(self) -> tuple[float, float]:
        raise NotImplementedError
