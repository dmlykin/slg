"""Boss: trigger, patterns, phase 2, gate, victory."""

from __future__ import annotations

import pytest

from tests.conftest import run_frames


def test_boss_dormant_until_trigger(session):
    run_frames(session, 1.0)
    boss = session.boss
    assert boss is not None
    assert boss.state == "dormant"
    assert not session.boss_gate_active


def test_trigger_activates_boss_and_closes_gate(session):
    run_frames(session, 0.5)
    boss = session.boss
    # walk the player into the trigger zone (x 1250..1310, y 60..200)
    session.player.entity.x = 1280
    session.player.entity.y = 150
    run_frames(session, 0.1)
    assert boss.state != "dormant"
    assert session.boss_gate_active
    # gate platform is now in the world
    assert any(p.x == session.spec.boss_gate.x for p in session.world.platforms)


def test_boss_cycles_patterns(session):
    run_frames(session, 0.5)
    boss = session.boss
    session.player.entity.x = 1280
    session.player.entity.y = 150
    run_frames(session, 0.2)
    seen_phases = set()
    for _ in range(600):
        run_frames(session, 0.05)
        seen_phases.add(boss.state)
        if {"telegraph", "active", "recover"}.issubset(seen_phases):
            break
    assert "telegraph" in seen_phases
    assert "active" in seen_phases
    assert boss.pattern in ("slam", "sweep", "volley")


def test_boss_volley_fires_projectiles(session):
    run_frames(session, 0.5)
    boss = session.boss
    session.player.entity.x = 1280
    session.player.entity.y = 150
    spawned = []
    session.bus.subscribe("projectile_spawned",
                          lambda projectile: spawned.append(projectile))
    # force a volley pattern for determinism
    for _ in range(600):
        run_frames(session, 0.05)
        if boss.state == "telegraph":
            boss.pattern = "volley"
        if boss.pattern == "volley" and boss.state == "active":
            break
    assert boss.pattern == "volley"
    run_frames(session, 1.5)
    assert len(spawned) >= boss.b.volley_count


def test_phase2_at_half_hp(session):
    run_frames(session, 0.5)
    boss = session.boss
    boss.activate()
    phases = []
    session.bus.subscribe("boss_phase", lambda phase: phases.append(phase))
    boss.entity.hp = int(boss.entity.max_hp * 0.5) + 1
    boss.take_hit(5, 0.0, 0.0)
    assert boss.phase == 2
    assert boss.state == "roar"
    assert phases == [2]


def test_boss_stagger_from_poise(session):
    run_frames(session, 0.5)
    boss = session.boss
    boss.activate()
    boss.poise._value = boss.b.poise - 1
    boss.take_hit(1, 10.0, 0.0)
    assert boss.state == "stagger"


def test_boss_death_unlocks_gate_and_victory(session):
    run_frames(session, 0.5)
    boss = session.boss
    session.player.entity.x = 1280
    session.player.entity.y = 150
    run_frames(session, 0.1)
    assert session.boss_gate_active
    victories = []
    session.bus.subscribe("victory", lambda: victories.append(True))
    boss.entity.hp = 1
    boss.take_hit(50, 0.0, 0.0)
    assert not boss.entity.alive
    run_frames(session, 0.05)
    assert session.victory
    assert not session.boss_gate_active
    assert victories == [True]


def test_victory_freezes_simulation(session):
    run_frames(session, 0.5)
    boss = session.boss
    boss.activate()
    boss.entity.hp = 1
    boss.take_hit(50, 0.0, 0.0)
    run_frames(session, 0.05)
    assert session.victory
    t = session.world.time
    run_frames(session, 1.0)
    assert session.world.time == pytest.approx(t, abs=0.001)
