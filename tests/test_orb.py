"""Well ball lightning: invulnerable, damaging on touch, shatters on the arena."""

from __future__ import annotations

import json
from pathlib import Path

from slg.core.level import LevelSpec
from slg.core.player import InputIntents
from slg.core.session import Session

DATA_LEVEL = Path(__file__).resolve().parents[1] / "src" / "slg" / "data" / "level_03.json"


def _well_spec() -> LevelSpec:
    data = json.loads(DATA_LEVEL.read_text(encoding="utf-8"))
    data.pop("boss_trigger", None)
    data.pop("boss_gate", None)
    data["bosses"] = []
    return LevelSpec.from_dict(data)


def _orb(session: Session):
    return next(e for e in session.enemies if e.entity.kind == "orb")


def test_orb_cannot_be_killed():
    session = Session(spec=_well_spec())
    orb = _orb(session)
    assert orb.take_hit(10_000, 10_000, 10_000) is False
    assert orb.entity.alive


def test_orb_hurts_on_contact():
    session = Session(spec=_well_spec())
    orb = _orb(session)
    p = session.player
    orb.entity.x = 600.0
    orb.entity.y = 1117.0
    orb.base_y = 1133.0
    p.respawn_at(600.0, 1122.0)
    for _ in range(12):
        session.update(session.cfg.physics.fixed_dt, InputIntents())
    assert p.entity.hp < p.entity.max_hp or p.state == "hurt"


def test_orb_falls_when_it_leaves_the_ledge():
    session = Session(spec=_well_spec())
    orb = _orb(session)
    orb.entity.x = 955.0
    session.update(session.cfg.physics.fixed_dt, InputIntents())
    assert orb.state == "fall"


def test_orb_shatters_on_the_boss_arena():
    session = Session(spec=_well_spec())
    orb = _orb(session)
    orb.entity.x = 1000.0
    orb.entity.y = 3000.0
    orb.base_y = 3000.0
    orb.state = "fall"
    dt = session.cfg.physics.fixed_dt
    for _ in range(int(4.0 / dt)):
        session.update(dt, InputIntents())
        if not orb.entity.alive:
            break
    assert not orb.entity.alive
    assert orb.entity.bottom == 4650.0
