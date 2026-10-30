"""Level traversal: a held jump at each gap must clear it (no softlocks)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slg.core.level import LevelSpec
from slg.core.player import InputIntents
from slg.core.session import Session
from slg.core.physics import aabb_overlap

DATA_LEVEL = Path(__file__).resolve().parents[1] / "src" / "slg" / "data" / "level_01.json"


def _traversal_spec() -> LevelSpec:
    """Shipped level without enemies/boss — pure geometry check."""
    data = json.loads(DATA_LEVEL.read_text(encoding="utf-8"))
    data["enemies"] = []
    data.pop("boss")
    data.pop("boss_trigger")
    data.pop("boss_gate")
    return LevelSpec.from_dict(data)


def _ground_ahead(session, x, y, half_w, half_h, dist=40):
    probe_x = x + half_w + dist
    probe_y = y + half_h + 12
    return any(
        aabb_overlap(probe_x - 1, probe_y - 1, 2, 2, pl.x, pl.y, pl.width, pl.height)
        for pl in session.world.platforms
    )


def test_level_is_traversable_left_to_right():
    session = Session(spec=_traversal_spec())
    dt = session.cfg.physics.fixed_dt
    p = session.player
    jump_hold = 0.0
    max_x = 0.0
    for _ in range(int(60 / dt)):
        e = p.entity
        assert p.state != "dead", f"died at x={e.x:.0f}"
        jump = False
        if jump_hold > 0:
            jump_hold -= dt
        if e.on_ground and not _ground_ahead(session, e.x, e.y, e.half_w, e.half_h):
            jump = True
            jump_hold = 0.45
        session.update(dt, InputIntents(move=1, jump_pressed=jump,
                                        jump_held=jump or jump_hold > 0))
        max_x = max(max_x, e.x)
    # reached the far end of the boss arena
    assert max_x > 3900, f"stuck at x={max_x:.0f}"


def test_level_can_be_traversed_after_checkpoint_too():
    """From the checkpoint onward the same traversal works (respawn path)."""
    session = Session(spec=_traversal_spec())
    dt = session.cfg.physics.fixed_dt
    p = session.player
    p.entity.x = 2450
    p.entity.y = 520
    jump_hold = 0.0
    max_x = 0.0
    for _ in range(int(60 / dt)):
        e = p.entity
        assert p.state != "dead", f"died at x={e.x:.0f}"
        jump = False
        if jump_hold > 0:
            jump_hold -= dt
        if e.on_ground and not _ground_ahead(session, e.x, e.y, e.half_w, e.half_h):
            jump = True
            jump_hold = 0.45
        session.update(dt, InputIntents(move=1, jump_pressed=jump,
                                        jump_held=jump or jump_hold > 0))
        max_x = max(max_x, e.x)
    assert max_x > 3900, f"stuck at x={max_x:.0f}"
