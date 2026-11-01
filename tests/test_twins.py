"""Twin bosses: shared trigger, enrage of the survivor, victory only on both."""

from __future__ import annotations

from slg.core.session import Session
from tests.conftest import make_spec, run_frames


def _twins_session() -> Session:
    spec = make_spec(
        enemies=[],
        boss=None,
        bosses=[
            {"type": "blade", "x": 1600, "y": 140},
            {"type": "prism", "x": 1760, "y": 140},
        ],
    )
    return Session(spec=spec)


def _by_kind(session: Session, kind: str):
    return next(b for b in session.bosses if b.kind == kind)


def test_twins_spawn_with_their_own_hp_and_size():
    session = _twins_session()
    blade = _by_kind(session, "blade")
    prism = _by_kind(session, "prism")
    assert blade.entity.max_hp == session.cfg.blade.max_hp
    assert prism.entity.max_hp == session.cfg.prism.max_hp
    assert blade.entity.kind == "blade" and prism.entity.kind == "prism"
    assert blade.entity.width < session.cfg.boss.width


def test_trigger_wakes_both_and_closes_gate():
    session = _twins_session()
    run_frames(session, 0.4)
    assert all(b.state == "dormant" for b in session.bosses)
    session.player.entity.x = 1280
    session.player.entity.y = 150
    run_frames(session, 0.1)
    assert all(b.state != "dormant" for b in session.bosses)
    assert session.boss_gate_active


def test_survivor_enrages_when_its_twin_dies():
    session = _twins_session()
    run_frames(session, 0.4)
    blade = _by_kind(session, "blade")
    prism = _by_kind(session, "prism")
    blade.activate()
    prism.activate()
    run_frames(session, 1.4)  # let the roars finish
    phases = []
    session.bus.subscribe("boss_phase", lambda phase: phases.append(phase))
    blade.entity.hp = 1
    blade.take_hit(50, 0.0, 0.0)
    run_frames(session, 0.05)
    assert not blade.entity.alive
    assert prism.phase == 2
    assert prism.state == "roar"
    assert phases == [2]
    assert not session.victory


def test_victory_requires_both_deaths():
    session = _twins_session()
    run_frames(session, 0.4)
    blade = _by_kind(session, "blade")
    prism = _by_kind(session, "prism")
    blade.activate()
    prism.activate()
    run_frames(session, 0.1)
    victories = []
    session.bus.subscribe("victory", lambda: victories.append(True))
    blade.entity.hp = 1
    blade.take_hit(50, 0.0, 0.0)
    run_frames(session, 0.1)
    assert not session.victory
    assert not victories
    prism.entity.hp = 1
    prism.take_hit(50, 0.0, 0.0)
    run_frames(session, 0.05)
    assert session.victory
    assert session.boss_defeated
    assert victories == [True]
    assert not session.boss_gate_active


def test_dormant_twins_cannot_be_hit():
    session = _twins_session()
    run_frames(session, 0.4)
    for boss in session.bosses:
        hp0 = boss.entity.hp
        assert not boss.take_hit(50, 0.0, 0.0)
        assert boss.entity.hp == hp0
