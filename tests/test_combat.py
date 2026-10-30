"""Combat: hitboxes live only in the active phase; stagger; death events."""

from __future__ import annotations

import pytest

from slg.core.combat import AttackState, Poise, Stamina
from slg.core.config import Config
from slg.core.player import InputIntents
from slg.core.world import Entity
from tests.conftest import run_frames

_LIGHT = Config().combat.light


def test_stamina_spend_and_block():
    s = Stamina(100, 100, 30, 0.4)
    assert s.spend(60)
    assert s.value == 40
    assert not s.spend(60)
    assert s.value == 40


def test_poise_stagger_cycle():
    p = Poise(40, 20, 0.5)
    assert not p.take_stagger_damage(30)
    assert not p.staggered
    assert p.take_stagger_damage(15)  # 45 >= 40
    assert p.staggered
    p.update(0.6)
    assert not p.staggered


def test_hitbox_only_during_active():
    owner = Entity(id=1, x=0, y=0, width=26, height=56, facing=1)
    atk = AttackState()
    atk.start(_LIGHT)
    assert atk.hitbox(owner) is None  # windup
    atk.update(atk.attack.windup + 0.01)
    box = atk.hitbox(owner)
    assert box is not None
    assert box[0] == 0.0  # extends to the right of the center
    atk.update(atk.attack.active + 0.01)
    assert atk.hitbox(owner) is None  # recovery


def test_hitbox_respects_facing():
    owner = Entity(id=1, x=100, y=0, width=26, height=56, facing=-1)
    atk = AttackState()
    atk.start(_LIGHT)
    atk.update(atk.attack.windup + 0.01)
    left, top, w, h = atk.hitbox(owner)
    assert left + w == pytest.approx(100.0)  # extends to the left


def test_player_attack_hits_enemy_in_reach(session):
    run_frames(session, 0.5)
    p = session.player
    crawler = session.enemies[0]
    # place the crawler right in front of the player
    crawler.entity.x = p.entity.x + 40
    crawler.entity.y = p.entity.y
    crawler.entity.hp = crawler.entity.max_hp
    hp0 = crawler.entity.hp
    run_frames(session, 0.05, InputIntents(light_pressed=True))
    a = p.attack.attack
    run_frames(session, a.windup + a.active / 2)
    assert crawler.entity.hp < hp0


def test_player_attack_misses_out_of_reach(session):
    run_frames(session, 0.5)
    p = session.player
    crawler = session.enemies[0]
    crawler.entity.x = p.entity.x + 500  # far away
    crawler.entity.y = p.entity.y
    hp0 = crawler.entity.hp
    run_frames(session, 0.05, InputIntents(light_pressed=True))
    a = p.attack.attack
    run_frames(session, a.windup + a.active + a.recovery)
    assert crawler.entity.hp == hp0


def test_single_swing_hits_target_once(session):
    run_frames(session, 0.5)
    p = session.player
    crawler = session.enemies[0]
    crawler.entity.x = p.entity.x + 40
    crawler.entity.y = p.entity.y
    run_frames(session, 0.05, InputIntents(heavy_pressed=True))
    a = p.attack.attack
    run_frames(session, a.windup + a.active / 2)
    hp_mid = crawler.entity.hp
    run_frames(session, a.active)  # still same swing
    assert crawler.entity.hp == hp_mid


def test_stagger_interrupts_enemy_telegraph(session):
    run_frames(session, 0.5)
    p = session.player
    crawler = session.enemies[0]
    crawler.entity.x = p.entity.x + 50
    crawler.entity.y = p.entity.y
    # force the crawler into telegraph
    crawler.state = "telegraph"
    crawler.state_timer = 0.0
    # heavy attack stagger (48) >= crawler poise (40)
    run_frames(session, 0.05, InputIntents(heavy_pressed=True))
    a = p.attack.attack
    run_frames(session, a.windup + a.active / 2)
    assert crawler.state == "stagger"


def test_enemy_death_publishes_events(session):
    run_frames(session, 0.5)
    crawler = session.enemies[0]
    died = []
    session.bus.subscribe("entity_died", lambda entity: died.append(entity))
    crawler.entity.hp = 1
    assert crawler.take_hit(10, 0.0, 0.0)
    assert not crawler.entity.alive
    assert died == [crawler.entity]
