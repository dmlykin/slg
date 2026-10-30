"""Player: movement, jump, roll i-frames, stamina costs, heal, hurt."""

from __future__ import annotations

import pytest

from slg.core.player import InputIntents
from tests.conftest import run_frames


def test_lands_and_runs_idle(session):
    run_frames(session, 0.5)
    p = session.player
    assert p.state in ("idle", "run")
    assert p.entity.on_ground


def test_move_right(session):
    run_frames(session, 0.5)
    x0 = session.player.entity.x
    run_frames(session, 0.5, InputIntents(move=1))
    assert session.player.entity.x > x0 + 100
    assert session.player.entity.facing == 1


def test_jump_leaves_ground(session):
    run_frames(session, 0.5)
    run_frames(session, 0.05, InputIntents(jump_pressed=True, jump_held=True))
    assert not session.player.entity.on_ground
    assert session.player.entity.vy < 0
    run_frames(session, 1.5, InputIntents(jump_held=True))
    assert session.player.entity.on_ground


def test_roll_costs_stamina_and_moves(session):
    run_frames(session, 0.5)
    p = session.player
    stamina_before = p.stamina.value
    x0 = p.entity.x
    run_frames(session, 0.05, InputIntents(roll_pressed=True))
    assert p.state == "roll"
    assert p.stamina.value < stamina_before
    run_frames(session, 0.5)
    assert p.state != "roll"
    assert p.entity.x > x0 + 100


def test_roll_gives_iframes(session):
    run_frames(session, 0.5)
    p = session.player
    run_frames(session, 0.05, InputIntents(roll_pressed=True))
    # inside the i-frame window (roll just started, iframes_start=0.03)
    run_frames(session, 0.05)
    assert p.state == "roll"
    assert p.invulnerable
    assert not p.take_hit(20, 0.0)
    assert p.entity.hp == p.entity.max_hp


def test_roll_iframes_expire_before_end(session):
    run_frames(session, 0.5)
    p = session.player
    run_frames(session, 0.05, InputIntents(roll_pressed=True))
    # roll duration 0.38, iframes end at 0.30 -> wait past the window
    run_frames(session, 0.31)
    assert p.state == "roll"
    assert not p.invulnerable
    assert p.take_hit(20, 0.0)


def test_no_stamina_no_roll(session):
    run_frames(session, 0.5)
    p = session.player
    p.stamina.value = 5.0
    run_frames(session, 0.05, InputIntents(roll_pressed=True))
    assert p.state != "roll"


def test_stamina_regen_after_delay(session):
    run_frames(session, 0.5)
    p = session.player
    p.stamina.value = 10.0
    p.stamina.spend(5.0)  # triggers regen delay
    run_frames(session, 0.2)
    assert p.stamina.value == pytest.approx(5.0, abs=0.1)  # still delayed
    run_frames(session, 1.0)
    assert p.stamina.value > 5.0


def test_light_attack_phases(session):
    run_frames(session, 0.5)
    p = session.player
    run_frames(session, 0.05, InputIntents(light_pressed=True))
    assert p.state == "attack_l"
    assert p.attack.phase == "windup"
    a = p.attack.attack
    run_frames(session, a.windup + 0.01)
    assert p.attack.phase == "active"
    run_frames(session, a.active + 0.01)
    assert p.attack.phase == "recovery"
    run_frames(session, a.recovery + 0.01)
    assert p.state in ("idle", "run")


def test_heal_restores_hp_and_consumes_charge(session):
    run_frames(session, 0.5)
    p = session.player
    p.entity.hp = 30
    charges = p.heal_charges
    events = []
    session.bus.subscribe("heal", lambda entity, amount: events.append(amount))
    run_frames(session, 0.05, InputIntents(heal_pressed=True))
    assert p.state == "heal"
    assert p.heal_charges == charges - 1
    run_frames(session, session.cfg.combat.heal_duration + 0.1)
    assert p.entity.hp == 30 + p.cfg.player.heal_amount
    assert events == [p.cfg.player.heal_amount]


def test_heal_interrupted_by_damage(session):
    run_frames(session, 0.5)
    p = session.player
    p.entity.hp = 30
    run_frames(session, 0.05, InputIntents(heal_pressed=True))
    assert p.state == "heal"
    assert p.take_hit(10, 0.0)
    assert p.state == "hurt"
    run_frames(session, 1.0)
    assert p.entity.hp == 20  # no heal applied


def test_hurt_stun_then_recover(session):
    run_frames(session, 0.5)
    p = session.player
    assert p.take_hit(10, 0.0)
    assert p.state == "hurt"
    run_frames(session, p.cfg.player.hurt_stun + 0.1)
    assert p.state in ("idle", "run")


def test_post_hit_invulnerability(session):
    run_frames(session, 0.5)
    p = session.player
    assert p.take_hit(10, 0.0)
    assert not p.take_hit(10, 0.0)  # brief invuln after being hit
    run_frames(session, p.cfg.player.invuln_after_hit + 0.05)
    assert p.take_hit(10, 0.0)
