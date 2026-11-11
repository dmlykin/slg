"""Density of being: substance, density scaling, boss mirrors, persistence."""

from __future__ import annotations

import os

import pytest

from slg.core.config import Config
from slg.core.level import LevelSpec
from slg.core.progress import Progress
from slg.core.session import Session
from tests.conftest import make_spec, run_frames


def _kill(controller) -> None:
    controller.entity.hp = 1
    controller.take_hit(50, 0.0, 0.0)
    assert not controller.entity.alive


# ------------------------------------------------------------------ substance


def test_killing_a_crawler_yields_substance_and_event():
    session = Session(spec=make_spec(enemies=[{"type": "crawler", "x": 400, "y": 185}]))
    player = session.player
    gained = []
    session.bus.subscribe(
        "substance_gained",
        lambda amount, substance, density: gained.append((amount, substance, density)),
    )
    _kill(session.enemies[0])
    yield_ = session.cfg.crawler.substance_yield
    assert player.substance == pytest.approx(yield_)
    assert player.density == pytest.approx(1.0 + 0.005 * yield_)
    assert gained and gained[0][0] == pytest.approx(yield_)
    assert gained[0][1] == pytest.approx(player.substance)
    assert gained[0][2] == pytest.approx(player.density)


def test_substance_is_capped():
    cfg = Config().with_overrides(density={"max_substance": 10})
    spec = make_spec(enemies=[
        {"type": "crawler", "x": 400, "y": 185},
        {"type": "crawler", "x": 450, "y": 185},
    ])
    session = Session(spec=spec, cfg=cfg)
    for enemy in session.enemies:
        _kill(enemy)
    assert session.player.substance == pytest.approx(10.0)


def test_full_substance_scales_max_hp():
    session = Session(spec=make_spec())
    player = session.player
    base = session.cfg.player.max_hp
    assert player.entity.max_hp == base
    player.set_substance(session.cfg.density.max_substance)
    assert player.entity.max_hp == round(base * 1.35)
    assert player.entity.hp == player.entity.max_hp  # gained the delta


def test_player_damage_scales_with_density():
    session = Session(spec=make_spec(enemies=[{"type": "crawler", "x": 140, "y": 185}]))
    player = session.player
    crawler = session.enemies[0]
    player.entity.x = crawler.entity.x - 40.0
    player.entity.y = crawler.entity.y
    player.entity.facing = 1
    light = session.cfg.combat.light

    def swing() -> None:
        session._swing_hits.clear()
        player.attack.start(light)
        player.attack.phase = "active"
        session._resolve_player_attacks()

    hp0 = crawler.entity.hp
    swing()
    assert crawler.entity.hp == hp0 - light.damage
    player.gain_substance(session.cfg.density.max_substance)
    boosted = max(1, round(light.damage * player.damage_mult))
    assert boosted > light.damage
    swing()
    assert crawler.entity.hp == hp0 - light.damage - boosted


def test_death_does_not_reset_substance():
    session = Session(spec=make_spec())
    player = session.player
    player.gain_substance(30.0)
    player.entity.y = 850.0  # into the kill zone
    run_frames(session, 2.5)
    assert player.state == "idle"  # respawned
    assert player.substance == pytest.approx(30.0)


# ------------------------------------------------------------------ progress


def test_progress_substance_roundtrip_and_legacy_files():
    p = Progress().with_substance(123.5)
    restored = Progress.from_dict(p.to_dict())
    assert restored.substance == 123.5
    assert restored.defeated == frozenset()
    # old files without the key, or with a broken value, read as 0.0
    assert Progress.from_dict({"defeated": ["swamp"]}).substance == 0.0
    assert Progress.from_dict({"defeated": [], "substance": "x"}).substance == 0.0
    assert Progress.from_dict({}).substance == 0.0
    # mark_defeated keeps the carried substance
    assert Progress(frozenset({"swamp"}), 5.0).mark_defeated("glass").substance == 5.0


def test_session_seeds_substance_from_progress():
    session = Session(spec=make_spec(), progress=Progress(substance=50.0))
    player = session.player
    assert player.substance == pytest.approx(50.0)
    assert player.density_norm == pytest.approx(50.0 / session.cfg.density.max_substance)
    base = session.cfg.player.max_hp
    assert player.entity.max_hp == round(base * (1.0 + 0.35 * 0.25))
    assert player.entity.hp == player.entity.max_hp


# ------------------------------------------------------------------ mirrors


def test_swamp_boss_mirrors_damage():
    session = Session(spec=make_spec())
    boss = session.boss
    boss.apply_mirror(1.0)
    assert boss._mirror_damage(26) == 39  # 26 * (1 + 0.5)
    light = Session(spec=make_spec())
    light.boss.apply_mirror(0.0)
    assert light.boss._mirror_damage(26) == 26


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


def test_twins_mirror_hp_for_the_heavy_player():
    session = _twins_session()
    blade = next(b for b in session.bosses if b.kind == "blade")
    base_hp = blade.entity.max_hp
    blade.apply_mirror(1.0)
    assert blade.entity.max_hp == round(base_hp * 1.35)
    assert blade.entity.hp == blade.entity.max_hp


def test_twins_mirror_speed_for_the_light_player():
    session = _twins_session()
    blade = next(b for b in session.bosses if b.kind == "blade")
    blade.apply_mirror(0.0)
    assert blade._speed_mult() == pytest.approx(1.3)
    assert blade._telegraph_mult() == pytest.approx(0.8)
    # mirrors stack multiplicatively with phase 2
    blade.phase = 2
    assert blade._speed_mult() == pytest.approx(1.3 * blade.b.phase2_speed_mult)


def test_boss_trigger_applies_mirror_before_activation():
    session = _twins_session()
    session.player.gain_substance(session.cfg.density.max_substance)
    session.player.entity.x = 1280
    session.player.entity.y = 150
    run_frames(session, 0.1)
    blade = next(b for b in session.bosses if b.kind == "blade")
    assert blade.state != "dormant"
    assert blade.entity.max_hp == round(session.cfg.blade.max_hp * 1.35)


# ------------------------------------------------------------------ keeper


def _keeper_session() -> Session:
    data = {
        "name": "density-keeper-test",
        "bounds": [0, 0, 2000, 800],
        "player_spawn": [200, 372],
        "platforms": [{"x": 0, "y": 400, "w": 2000, "h": 400}],
        "enemies": [],
        "bosses": [{"type": "keeper", "x": 1000, "y": 332}],
        "boss_trigger": {"x": 0, "y": 340, "w": 2000, "h": 60, "name": "arena"},
    }
    return Session(spec=LevelSpec.from_dict(data))


def _nop(*_args, **_kwargs) -> None:
    return None


def test_hearing_window_scales_with_density():
    session = _keeper_session()
    player = session.player
    boss = session.boss
    assert player.hearing_mult == pytest.approx(
        player.density ** session.cfg.density.hearing_scale)
    boss.activate()
    boss.state, boss.state_timer = "idle", 0.0
    dt = session.cfg.physics.fixed_dt
    memory = boss.b.hearing_memory

    # heavy player: window stretched by density ** 0.5, still heard in between
    player.set_substance(player.cfg.density.max_substance)
    scaled = memory * player.hearing_mult
    assert scaled > memory
    player.noise_timer = memory + (scaled - memory) / 2.0
    boss.update(dt, player, session.world, _nop)
    assert not boss.silent

    # light player: the same silence is beyond the base window
    player.set_substance(0.0)
    player.noise_timer = memory + 0.1
    boss.update(dt, player, session.world, _nop)
    assert boss.silent


# ------------------------------------------------------------------ render


def test_render_frame_with_substance_bar():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame

    from slg.render.renderer import Renderer

    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    session = Session(spec=make_spec())
    session.player.gain_substance(50.0)
    renderer = Renderer(session)
    renderer.update(session.cfg.physics.fixed_dt)
    renderer.draw(screen)
    pygame.quit()
