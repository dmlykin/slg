"""Shard ambusher: dormant until close, telegraph, lunge, vulnerable recovery."""

from __future__ import annotations

from slg.core.session import Session
from tests.conftest import make_spec, run_frames


def _shard_session() -> Session:
    spec = make_spec(
        platforms=[{"x": 0, "y": 200, "w": 1200, "h": 400, "organic": False}],
        enemies=[{"type": "shard", "x": 400, "y": 178}],
        boss=None,
        boss_trigger=None,
        boss_gate=None,
        checkpoints=[],
    )
    return Session(spec=spec)


def _shard(session: Session):
    return session.enemies[0]


def test_shard_stays_dormant_outside_wake_radius():
    session = _shard_session()
    run_frames(session, 1.5)
    shard = _shard(session)
    assert shard.state == "dormant"
    assert shard.entity.kind == "shard"


def test_shard_wakes_and_telegraphs():
    session = _shard_session()
    run_frames(session, 0.3)
    kinds = []
    session.bus.subscribe("telegraph", lambda entity, kind, duration: kinds.append(kind))
    session.player.entity.x = 340  # inside wake radius (60 px)
    session.player.entity.y = 172
    run_frames(session, 0.05)
    shard = _shard(session)
    assert shard.state == "telegraph"
    assert "shard_lunge" in kinds


def test_shard_lunge_damages_player():
    session = _shard_session()
    p = session.player
    run_frames(session, 0.3)
    p.entity.x = 340
    p.entity.y = 172
    hp0 = p.entity.hp
    for _ in range(200):
        run_frames(session, 0.05)
        if p.entity.hp < hp0:
            break
    assert p.entity.hp < hp0
    assert p.entity.hp == hp0 - session.cfg.shard.lunge_damage


def test_shard_is_vulnerable_while_recovering():
    session = _shard_session()
    shard = _shard(session)
    shard.state = "recover"
    shard.state_timer = 0.0
    hp0 = shard.entity.hp
    assert shard.take_hit(10, 0.0, 0.0)
    assert shard.entity.hp == hp0 - 10
    assert shard.state == "recover"


def test_shard_dies_from_player_hits():
    session = _shard_session()
    run_frames(session, 0.3)
    session.player.entity.x = 340
    session.player.entity.y = 172
    run_frames(session, 0.1)
    shard = _shard(session)
    died = []
    session.bus.subscribe("entity_died", lambda entity: died.append(entity.kind))
    shard.take_hit(999, 0.0, 0.0)
    assert not shard.entity.alive
    assert "shard" in died
    # and it stays out of the fight
    run_frames(session, 0.2)
    assert not shard.entity.alive
