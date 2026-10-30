"""Level loading, checkpoints, death -> respawn."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slg.core.level import LevelSpec
from slg.core.player import InputIntents
from tests.conftest import run_frames

DATA_LEVEL = Path(__file__).resolve().parents[1] / "src" / "slg" / "data" / "level_01.json"


def test_shipped_level_loads():
    spec = LevelSpec.load(DATA_LEVEL)
    assert spec.name
    assert len(spec.platforms) >= 5
    assert spec.player_spawn[1] > 0
    assert spec.boss is not None
    assert spec.boss_trigger is not None
    assert spec.boss_gate is not None
    assert any(c.name for c in spec.checkpoints)
    types = {e.type for e in spec.enemies}
    assert types == {"crawler", "spitter"}


def test_shipped_level_spawns_are_above_platforms():
    spec = LevelSpec.load(DATA_LEVEL)
    tops = [(p.x, p.x + p.width, p.y) for p in spec.platforms]
    def on_ground(x, y, half_h):
        for left, right, top in tops:
            if left - 5 <= x <= right + 5 and abs((top - half_h) - y) < 30:
                return True
        return False
    assert on_ground(*spec.player_spawn, 28)
    for e in spec.enemies:
        assert on_ground(e.x, e.y, 15 if e.type == "crawler" else 20), e
    assert on_ground(spec.boss.x, spec.boss.y, 60)


def test_level_from_dict_roundtrip(tmp_path):
    path = tmp_path / "lvl.json"
    path.write_text(json.dumps({
        "name": "test", "bounds": [0, -400, 2000, 1000],
        "player_spawn": [100, 100],
        "platforms": [{"x": 0, "y": 200, "w": 600, "h": 200}],
        "enemies": [{"type": "crawler", "x": 400, "y": 185}],
    }), encoding="utf-8")
    loaded = LevelSpec.load(path)
    assert loaded.name == "test"
    assert len(loaded.platforms) == 1
    assert loaded.enemies[0].type == "crawler"
    assert loaded.boss is None


def test_unknown_enemy_type_rejected(session):
    with pytest.raises(ValueError):
        session._spawn_enemy("banshee", 0, 0)


def test_checkpoint_activation_with_e(session):
    run_frames(session, 0.5)
    p = session.player
    p.entity.x = 900
    p.entity.y = 172
    p.entity.hp = 10
    p.heal_charges = 0
    events = []
    session.bus.subscribe("checkpoint", lambda checkpoint: events.append(checkpoint))
    run_frames(session, 0.05, InputIntents(interact_pressed=True))
    assert events
    assert "cp1" in session.activated_checkpoints
    assert p.entity.hp == p.entity.max_hp
    assert p.heal_charges == p.cfg.player.heal_charges
    assert session.current_checkpoint == (900, 160)


def test_checkpoint_requires_proximity(session):
    run_frames(session, 0.5)
    run_frames(session, 0.05, InputIntents(interact_pressed=True))
    assert session.activated_checkpoints == set()


def test_death_respawns_at_checkpoint_with_reset(session):
    run_frames(session, 0.5)
    p = session.player
    # activate the checkpoint
    p.entity.x = 900
    p.entity.y = 172
    run_frames(session, 0.05, InputIntents(interact_pressed=True))
    assert session.activated_checkpoints

    # damage the player, kill an enemy, then die
    p.entity.hp = 5
    crawler = session.enemies[0]
    crawler.entity.hp = 1
    crawler.take_hit(10, 0.0, 0.0)
    assert not crawler.entity.alive
    p.take_hit(999, 0.0)
    assert p.state == "dead"

    respawns = []
    session.bus.subscribe("respawn", lambda: respawns.append(True))
    run_frames(session, 2.0)
    assert respawns
    assert p.state == "idle"
    assert p.entity.hp == p.entity.max_hp
    assert p.entity.x == pytest.approx(900, abs=0.1)
    # enemies revived
    alive = [e for e in session.enemies if e.entity.alive]
    assert len(alive) == len(session.spec.enemies)


def test_respawn_resets_undead_boss_and_gate(session):
    run_frames(session, 0.5)
    boss = session.boss
    session.player.entity.x = 1280
    session.player.entity.y = 150
    run_frames(session, 0.1)
    assert session.boss_gate_active
    # hurt the boss, then die
    boss.activate()
    boss.entity.hp = 100
    session.player.take_hit(999, 0.0)
    run_frames(session, 2.0)
    assert session.player.state == "idle"
    assert not session.boss_gate_active
    assert session.boss.entity.hp == session.boss.entity.max_hp
    assert session.boss.state == "dormant"


def test_victory_keeps_boss_dead_on_respawn_path(session):
    run_frames(session, 0.5)
    boss = session.boss
    boss.activate()
    boss.entity.hp = 1
    boss.take_hit(50, 0.0, 0.0)
    run_frames(session, 0.05)
    assert session.victory
    assert session.boss_defeated
    session.respawn_everything()
    assert session.boss.entity.hp == 0 or session.boss is None or not session.boss.entity.alive
