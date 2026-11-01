"""Well descent: the alternating ledges must be passable without softlocks."""

from __future__ import annotations

import json
from pathlib import Path

from slg.core.level import LevelSpec
from slg.core.physics import aabb_overlap
from slg.core.player import InputIntents
from slg.core.session import Session

DATA_LEVEL = Path(__file__).resolve().parents[1] / "src" / "slg" / "data" / "level_03.json"


def _descent_spec() -> LevelSpec:
    """Shipped well without enemies/boss/arena trigger — pure geometry check."""
    data = json.loads(DATA_LEVEL.read_text(encoding="utf-8"))
    data["enemies"] = []
    data["bosses"] = []
    data.pop("boss_trigger", None)
    data.pop("boss_gate", None)
    return LevelSpec.from_dict(data)


def _ground_ahead(session, x, y, half_w, half_h, direction, dist=40):
    probe_x = x + direction * (half_w + dist)
    probe_y = y + half_h + 12
    return any(
        aabb_overlap(probe_x - 1, probe_y - 1, 2, 2, pl.x, pl.y, pl.width, pl.height)
        for pl in session.world.platforms
    )


def test_level_03_can_descend():
    session = Session(spec=_descent_spec())
    dt = session.cfg.physics.fixed_dt
    p = session.player
    direction = 1
    last_ground_y: float | None = None
    jump_hold = 0.0
    reached = False
    for _ in range(int(60.0 / dt)):
        e = p.entity
        assert p.state != "dead", f"died descending at x={e.x:.0f} y={e.y:.0f}"
        if e.on_ground:
            if last_ground_y is not None and abs(e.y - last_ground_y) > 50.0:
                direction *= -1
            last_ground_y = e.y
        if jump_hold > 0.0:
            jump_hold -= dt
        jump = False
        if e.on_ground and not _ground_ahead(
                session, e.x, e.y, e.half_w, e.half_h, direction):
            jump = True
            jump_hold = 0.45
        session.update(dt, InputIntents(
            move=direction,
            jump_pressed=jump,
            jump_held=jump or jump_hold > 0.0,
        ))
        if p.entity.on_ground and p.entity.y > 4600.0:
            reached = True
            break
    assert reached, f"stuck at x={p.entity.x:.0f} y={p.entity.y:.0f}"
