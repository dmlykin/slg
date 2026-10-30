"""Render/audio smoke test under SDL dummy drivers — catches import & draw bugs."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from slg.core.level import LevelSpec  # noqa: E402
from slg.core.player import InputIntents  # noqa: E402
from slg.core.session import Session  # noqa: E402
from slg.render.camera import Projection, SideProjection, TopDownProjection  # noqa: E402
from slg.render.renderer import Renderer  # noqa: E402
from slg.audio import AudioSystem  # noqa: E402

LEVEL_FILE = "src/slg/data/level_01.json"


def _boot():
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    spec = LevelSpec.load(LEVEL_FILE)
    session = Session(spec=spec)
    renderer = Renderer(session)
    return screen, session, renderer


def test_projection_protocol():
    assert isinstance(SideProjection((0, 0, 4000, 1000)), Projection)
    stub = TopDownProjection((0, 0, 4000, 1000))
    try:
        stub.world_to_screen(0, 0, 0)
        raised = False
    except NotImplementedError:
        raised = True
    assert raised


def test_side_projection_maps_origin():
    proj = SideProjection((0, 0, 4000, 1000), screen_size=(100, 100))
    proj.snap_to(500, 360)  # snap_to centers x, offsets y by -60 (look-up bias)
    x, y = proj.world_to_screen(500, 300, 0)
    assert (x, y) == (50, 50)


def test_render_frames_without_crash():
    screen, session, renderer = _boot()
    for i in range(120):
        intents = InputIntents(move=1 if i % 40 < 20 else 0, jump_pressed=i == 30,
                               light_pressed=i == 80)
        session.update(session.cfg.physics.fixed_dt, intents)
        renderer.update(session.cfg.physics.fixed_dt)
        renderer.draw(screen)
    pygame.quit()


def test_render_death_and_victory_paths():
    screen, session, renderer = _boot()
    # death path
    session.player.take_hit(999, 0.0)
    for _ in range(120):
        session.update(session.cfg.physics.fixed_dt, InputIntents())
        renderer.draw(screen)
    assert session.player.state == "idle"  # respawned
    # victory path
    boss = session.boss
    boss.activate()
    boss.entity.hp = 1
    boss.take_hit(50, 0.0, 0.0)
    for _ in range(10):
        session.update(session.cfg.physics.fixed_dt, InputIntents())
        renderer.draw(screen)
    assert session.victory
    pygame.quit()


def test_audio_system_degrades_gracelessly():
    pygame.init()
    try:
        pygame.mixer.init()
    except pygame.error:
        pass
    from slg.core.events import EventBus

    bus = EventBus()
    AudioSystem(bus)  # must not raise even without a real device
    bus.publish("attack_hit", attacker=None, victim=None, x=0, y=0, damage=1, heavy=False)
    bus.publish("telegraph", entity=None, kind="x", duration=0.1)
    pygame.quit()
