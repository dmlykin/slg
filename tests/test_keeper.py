"""Blind keeper of the well: noise, hearing, patterns, falling orbs and phase 2."""

from __future__ import annotations

import pytest

from slg.core.keeper import KeeperBoss, OrbDrop, ShockZone
from slg.core.level import LevelSpec
from slg.core.player import InputIntents
from slg.core.session import Session

FLOOR = 400.0


def _make_session() -> Session:
    data = {
        "name": "keeper-test",
        "bounds": [0, 0, 2000, 800],
        "player_spawn": [200, 372],
        "platforms": [{"x": 0, "y": FLOOR, "w": 2000, "h": 400}],
        "enemies": [],
        "bosses": [{"type": "keeper", "x": 1000, "y": 332}],
        "boss_trigger": {"x": 0, "y": 340, "w": 2000, "h": 60, "name": "arena"},
    }
    return Session(spec=LevelSpec.from_dict(data))


def _settle(session: Session) -> None:
    dt = session.cfg.physics.fixed_dt
    for _ in range(3):
        session.player.update(dt, InputIntents(), session.world)


def _nop(*_args, **_kwargs) -> None:
    return None


def test_running_makes_noise_and_standing_is_silent():
    session = _make_session()
    p = session.player
    dt = session.cfg.physics.fixed_dt
    start_x = p.entity.x
    for _ in range(12):
        p.update(dt, InputIntents(move=1), session.world)
    assert p.noise_timer == 0.0
    assert p.noise_pulse > 0.0
    assert p.last_noise_pos[0] > start_x

    for _ in range(40):
        p.update(dt, InputIntents(), session.world)
    assert p.noise_timer > 0.5
    assert p.noise_pulse == 0.0


def test_falling_without_input_is_silent():
    session = _make_session()
    p = session.player
    p.entity.y = 250.0
    p.entity.vy = 120.0
    p.entity.on_ground = False
    p.state = "jump"
    p.noise_timer = 0.0
    p.update(session.cfg.physics.fixed_dt, InputIntents(), session.world)
    assert p.noise_timer > 0.0


def test_jumping_and_attacking_make_noise():
    session = _make_session()
    p = session.player
    dt = session.cfg.physics.fixed_dt
    p.update(dt, InputIntents(jump_pressed=True, jump_held=True), session.world)
    assert p.noise_timer == 0.0


def test_keeper_aims_at_the_last_noise_not_the_current_position():
    session = _make_session()
    p = session.player
    boss = session.boss
    assert isinstance(boss, KeeperBoss)
    boss.activate()
    boss.state, boss.state_timer = "idle", 0.0

    p.respawn_at(500.0, 372.0)
    p.update(session.cfg.physics.fixed_dt, InputIntents(move=1), session.world)
    heard_x = p.last_noise_pos[0]

    p.entity.x = 900.0  # slip away silently
    boss.update(session.cfg.physics.fixed_dt, p, session.world, _nop)
    assert boss.target_pos == pytest.approx(heard_x)
    assert boss.target_pos != pytest.approx(900.0)


def test_silence_makes_the_keeper_probe():
    session = _make_session()
    p = session.player
    boss = session.boss
    boss.activate()
    boss.state, boss.state_timer = "idle", 0.0
    p.noise_timer = 100.0
    boss.state_timer = boss.b.idle_between_patterns
    boss.update(session.cfg.physics.fixed_dt, p, session.world, _nop)
    assert boss.pattern in ("echo_wave", "call_orbs")
    assert boss.silent


def _force_pattern(session: Session, pattern: str, target: float) -> KeeperBoss:
    boss = session.boss
    boss.activate()
    boss.state, boss.state_timer = "active", 0.0
    boss.pattern = pattern
    boss.attack_target = target
    boss._struck = False
    boss._orbs_spawned = False
    boss.echo_radius = 0.0
    boss.echo_hit = False
    boss.drop_targets = []
    return boss


def test_lantern_slam_hits_inside_the_circle():
    session = _make_session()
    p = session.player
    p.respawn_at(500.0, 372.0)
    _settle(session)
    boss = _force_pattern(session, "lantern_slam", 500.0)
    hp = p.entity.hp
    for _ in range(30):
        boss.update(session.cfg.physics.fixed_dt, p, session.world, _nop)
        if p.entity.hp < hp:
            break
    assert p.entity.hp == hp - boss.b.slam_damage


def test_lantern_slam_misses_outside_the_circle():
    session = _make_session()
    p = session.player
    p.respawn_at(900.0, 372.0)
    _settle(session)
    boss = _force_pattern(session, "lantern_slam", 400.0)
    hp = p.entity.hp
    for _ in range(40):
        boss.update(session.cfg.physics.fixed_dt, p, session.world, _nop)
    assert p.entity.hp == hp


def test_echo_wave_hits_a_grounded_player():
    session = _make_session()
    p = session.player
    p.respawn_at(700.0, 372.0)
    _settle(session)
    boss = _force_pattern(session, "echo_wave", 700.0)
    hp = p.entity.hp
    for _ in range(120):
        boss.update(session.cfg.physics.fixed_dt, p, session.world, _nop)
        if p.entity.hp < hp:
            break
    assert p.entity.hp == hp - boss.b.sweep_damage


def test_echo_wave_misses_an_airborne_player():
    session = _make_session()
    p = session.player
    p.respawn_at(700.0, 250.0)
    p.entity.on_ground = False
    boss = _force_pattern(session, "echo_wave", 700.0)
    hp = p.entity.hp
    for _ in range(120):
        boss.update(session.cfg.physics.fixed_dt, p, session.world, _nop)
    assert p.entity.hp == hp


def test_call_orbs_fall_turn_into_zones_and_expire():
    session = _make_session()
    p = session.player
    boss = _force_pattern(session, "call_orbs", 700.0)
    boss.drop_targets = boss._make_drop_targets()
    assert len(boss.drop_targets) == 2

    boss.update(session.cfg.physics.fixed_dt, p, session.world, _nop)
    assert len(boss.orb_drops) == 2

    dt = session.cfg.physics.fixed_dt
    for _ in range(int(1.0 / dt)):
        boss.update(dt, p, session.world, _nop)
        if boss.shock_zones:
            break
    assert boss.shock_zones
    assert not boss.orb_drops

    for _ in range(int(2.0 / dt)):
        boss.update(dt, p, session.world, _nop)
    assert not boss.shock_zones


def test_shock_zone_hurts_with_a_cooldown():
    session = _make_session()
    p = session.player
    p.respawn_at(700.0, 372.0)
    _settle(session)
    boss = _force_pattern(session, "call_orbs", 700.0)
    boss.shock_zones.append(ShockZone(
        x=700.0, y=FLOOR, radius=boss.b.orb_zone_radius,
        life=boss.b.orb_zone_life, max_life=boss.b.orb_zone_life,
    ))
    hp = p.entity.hp
    dt = session.cfg.physics.fixed_dt
    boss._update_hazards(dt, p, session.world)
    assert p.entity.hp == hp - boss.b.volley_damage
    hp2 = p.entity.hp
    boss._update_hazards(dt, p, session.world)
    assert p.entity.hp == hp2  # still cooling down


def test_phase_two_adds_an_extra_drop():
    session = _make_session()
    boss = session.boss
    boss.activate()
    boss.entity.hp = int(boss.entity.max_hp * boss.b.phase2_at) + 1
    boss.take_hit(2, 0.0, 0.0)
    assert boss.phase == 2
    assert boss.state == "roar"

    boss.silent = False
    boss.target_pos = 700.0
    boss._pattern_cycle = 2  # next non-silent pick is call_orbs
    pattern = boss._pick_pattern(200.0)
    assert pattern == "call_orbs"
    assert len(boss.drop_targets) == boss.b.volley_count + 1


def test_death_clears_hazards():
    session = _make_session()
    boss = session.boss
    boss.activate()
    boss.orb_drops.append(OrbDrop(x=700.0, y=300.0, vy=800.0, target_y=FLOOR))
    boss.shock_zones.append(ShockZone(x=700.0, y=FLOOR, radius=70.0,
                                      life=1.0, max_life=1.0))
    boss.entity.hp = 1
    boss.take_hit(50, 0.0, 0.0)
    assert boss.state == "dead"
    assert not boss.orb_drops
    assert not boss.shock_zones


def test_shipped_well_spawns_a_keeper_and_can_be_beaten():
    from tests.conftest import run_frames

    data_path = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "src" / "slg" / "data" / "level_03.json"
    )
    session = Session(spec=LevelSpec.load(data_path))
    boss = session.boss
    assert isinstance(boss, KeeperBoss)
    session.player.respawn_at(1000.0, 4622.0)
    run_frames(session, 0.2)
    assert boss.state != "dormant"
    boss.entity.hp = 1
    boss.take_hit(50, 0.0, 0.0)
    run_frames(session, 0.1)
    assert session.victory
    assert not boss.orb_drops and not boss.shock_zones
