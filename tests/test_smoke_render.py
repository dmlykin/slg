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
GLASS_LEVEL_FILE = "src/slg/data/level_02.json"
WELL_LEVEL_FILE = "src/slg/data/level_03.json"
HUB_LEVEL_FILE = "src/slg/data/level_00.json"


def _boot(level_file: str = LEVEL_FILE):
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    spec = LevelSpec.load(level_file)
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


def test_render_hub_figure_portals_and_prompts():
    from slg.core.progress import Progress
    from slg.render.palette import current_theme, set_theme

    screen, session, renderer = _boot(HUB_LEVEL_FILE)
    assert current_theme() == "sanctum"
    assert session.spec.figure is not None
    dt = session.cfg.physics.fixed_dt
    face = session.spec.figure.faces[0]
    # walk to the first face so the available prompt is drawn
    for i in range(150):
        session.update(dt, InputIntents(move=1 if i < 140 else 0))
        renderer.update(dt)
        renderer.draw(screen)
    session.player.entity.x = face.x
    for _ in range(6):
        session.update(dt, InputIntents())
        renderer.update(dt)
        renderer.draw(screen)
    assert renderer._near_face() is not None
    # locked face prompt path
    session.player.entity.x = session.spec.figure.faces[1].x
    renderer.draw(screen)
    pygame.quit()


def test_render_hub_finale_overlay_and_dismissal():
    from slg.core.level import LevelSpec
    from slg.core.progress import Progress
    from slg.render.palette import set_theme

    progress = (Progress().mark_defeated("swamp").mark_defeated("glass")
                .mark_defeated("well"))
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    session = Session(spec=LevelSpec.load(HUB_LEVEL_FILE), progress=progress)
    renderer = Renderer(session, finale_title="СНЯТИЕ ТЯГОТ",
                        finale_subtitle="Все тяготы сняты. КОНЕЦ ДЕМО.",
                        finale_hint="E — остаться в мире")
    assert session.hub_finale
    renderer.draw(screen)  # finale overlay
    session.update(session.cfg.physics.fixed_dt, InputIntents(interact_pressed=True))
    assert session.finale_dismissed
    renderer.draw(screen)  # back to the hub
    set_theme("swamp")
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


def test_render_glass_level_with_shards_and_twins():
    from slg.render.palette import current_theme, set_theme

    screen, session, renderer = _boot(GLASS_LEVEL_FILE)
    assert current_theme() == "glass"
    # exercise the boss variants mid-telegraph (blade slam, prism volley)
    for boss in session.bosses:
        boss.activate()
    blade = next(b for b in session.bosses if b.kind == "blade")
    prism = next(b for b in session.bosses if b.kind == "prism")
    blade.state, blade.pattern, blade.state_timer = "telegraph", "slam", 0.2
    prism.state, prism.pattern, prism.state_timer = "telegraph", "volley", 0.3
    for i in range(60):
        intents = InputIntents(move=1 if i < 30 else 0)
        session.update(session.cfg.physics.fixed_dt, intents)
        renderer.update(session.cfg.physics.fixed_dt)
        renderer.draw(screen)
    # sharp-hit path draws sparks without crashing
    session.bus.publish("sharp_hit", entity=session.player.entity, x=100.0, y=100.0)
    renderer.draw(screen)
    set_theme("swamp")
    pygame.quit()


def test_render_well_level_vertical_camera_and_boss():
    from slg.render.palette import current_theme, set_theme

    screen, session, renderer = _boot(WELL_LEVEL_FILE)
    assert current_theme() == "well"
    assert renderer.background.vertical is True
    assert renderer.projection.vertical_bias == 100.0
    assert [b.kind for b in session.bosses] == ["keeper"]

    # fall down the shaft while drawing: vertical background + camera lead
    p = session.player
    p.respawn_at(1000.0, 200.0)
    dt = session.cfg.physics.fixed_dt
    for _ in range(120):
        session.update(dt, InputIntents())
        renderer.update(dt)
        renderer.draw(screen)
    set_theme("swamp")
    pygame.quit()


def test_render_keeper_telegraphs_echo_orbs_and_zones():
    from slg.render.palette import current_theme, set_theme

    screen, session, renderer = _boot(WELL_LEVEL_FILE)
    assert current_theme() == "well"
    boss = session.boss
    assert boss.kind == "keeper"
    boss.activate()
    boss.attack_target = 1000.0
    boss.drop_targets = [900.0, 1100.0]

    # lantern slam circle + echo ring
    boss.state, boss.state_timer, boss.pattern = "telegraph", 0.3, "lantern_slam"
    renderer.draw(screen)
    boss.state, boss.pattern, boss.state_timer = "active", "echo_wave", 0.2
    boss.echo_radius = 220.0
    renderer.draw(screen)

    # falling orbs turn into shock zones while the player makes noise
    session.player.respawn_at(1000.0, 4622.0)
    boss.state, boss.pattern, boss.state_timer = "active", "call_orbs", 0.0
    boss._orbs_spawned = False
    dt = session.cfg.physics.fixed_dt
    for i in range(120):
        session.update(dt, InputIntents(move=1 if i % 2 == 0 else 0))
        renderer.update(dt)
        renderer.draw(screen)
    session.bus.publish("orb_shattered", x=900.0, y=4650.0)
    renderer.draw(screen)
    set_theme("swamp")
    pygame.quit()
