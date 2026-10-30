"""Physics: gravity, AABB collisions, landing, walls, kill zones."""

from __future__ import annotations

import pytest

from slg.core.physics import aabb_overlap, apply_gravity, move_and_collide
from slg.core.world import Entity, Platform
from tests.conftest import run_frames


def test_aabb_overlap_basics():
    assert aabb_overlap(0, 0, 10, 10, 5, 5, 10, 10)
    assert not aabb_overlap(0, 0, 10, 10, 11, 0, 10, 10)
    assert not aabb_overlap(0, 0, 10, 10, 0, 11, 10, 10)


def test_gravity_pulls_and_lands(session):
    e = session.player.entity
    assert not e.on_ground
    run_frames(session, 1.0)
    # platform top is y=200, entity half-height 28 -> rests at 172
    assert e.on_ground
    assert e.y == pytest.approx(200 - 28, abs=1.0)
    assert e.vy == 0.0


def test_horizontal_collision_blocks(session):
    session.world.platforms.append(Platform(60, 100, 40, 200))
    e = session.world.spawn(x=10, y=172, vx=200.0, width=26, height=56)
    for _ in range(60):
        e.vx = 200.0
        move_and_collide(e, session.world, session.cfg.physics.fixed_dt)
    assert e.right <= 60.0 + 0.5


def test_head_bump(session):
    e = session.player.entity
    run_frames(session, 0.1)
    e.vy = -600.0
    session.world.platforms.append(Platform(0, 0, 600, 100))
    for _ in range(30):
        apply_gravity(e, session.cfg.physics, session.cfg.physics.fixed_dt)
        move_and_collide(e, session.world, session.cfg.physics.fixed_dt)
        if e.vy == 0.0 and not e.on_ground:
            break
    assert e.top >= 100.0 - 0.5


def test_kill_zone_kills(session):
    e = session.player.entity
    e.y = 900  # inside the abyss kill zone
    run_frames(session, 0.05)
    assert session.player.state == "dead"


def test_entity_carries_z():
    e = Entity(id=1, x=0.0, y=0.0, z=0.0)
    assert e.z == 0.0
    e.z = 5.0
    assert e.z == 5.0  # stored for the future top-down projection
