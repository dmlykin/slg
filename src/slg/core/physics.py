"""Gravity and AABB collision against platforms.

Entities move horizontally then vertically; each axis is resolved separately
against solid platform AABBs. Simple, deterministic, headless-testable.
"""

from __future__ import annotations

from slg.core.config import PhysicsConfig
from slg.core.world import Entity, KillZone, Platform, World


def aabb_overlap(
    a_left: float, a_top: float, a_w: float, a_h: float,
    b_left: float, b_top: float, b_w: float, b_h: float,
) -> bool:
    return (
        a_left < b_left + b_w
        and a_left + a_w > b_left
        and a_top < b_top + b_h
        and a_top + a_h > b_top
    )


def entity_hits_platform(entity: Entity, platform: Platform) -> bool:
    return aabb_overlap(
        entity.left, entity.top, entity.width, entity.height,
        platform.left, platform.top, platform.width, platform.height,
    )


def in_kill_zone(entity: Entity, zones: list[KillZone]) -> bool:
    return any(
        aabb_overlap(
            entity.left, entity.top, entity.width, entity.height,
            z.x, z.y, z.width, z.height,
        )
        for z in zones
    )


def move_and_collide(entity: Entity, world: World, dt: float) -> None:
    """Integrate one step: horizontal move + resolve, vertical move + resolve."""
    platforms = world.platforms

    # --- horizontal ---
    entity.x += entity.vx * dt
    for p in platforms:
        if not entity_hits_platform(entity, p):
            continue
        if entity.vx > 0:
            entity.x = p.left - entity.half_w
        elif entity.vx < 0:
            entity.x = p.right + entity.half_w
        entity.vx = 0.0

    # --- vertical ---
    entity.y += entity.vy * dt
    entity.on_ground = False
    for p in platforms:
        if not entity_hits_platform(entity, p):
            continue
        if entity.vy > 0:  # falling: land on top
            entity.y = p.top - entity.half_h
            entity.on_ground = True
        elif entity.vy < 0:  # rising: bump head
            entity.y = p.bottom + entity.half_h
        entity.vy = 0.0


def apply_gravity(entity: Entity, cfg: PhysicsConfig, dt: float) -> None:
    entity.vy += cfg.gravity * dt
    if entity.vy > cfg.max_fall_speed:
        entity.vy = cfg.max_fall_speed


def clamp_to_bounds(entity: Entity, world: World) -> None:
    left, _top, right, _bottom = world.bounds
    if entity.left < left:
        entity.x = left + entity.half_w
        entity.vx = 0.0
    elif entity.right > right:
        entity.x = right - entity.half_w
        entity.vx = 0.0
