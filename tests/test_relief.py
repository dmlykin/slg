"""Density relief at the Priestess: zone parsing, arm/confirm ritual, deposit."""

from __future__ import annotations

import json
from pathlib import Path

from slg.core.level import LevelSpec, Relief
from slg.core.player import InputIntents
from slg.core.progress import Progress
from slg.core.session import Session
from tests.conftest import make_spec, run_frames

DATA = Path(__file__).resolve().parents[1] / "src" / "slg" / "data"
HUB = DATA / "level_00.json"


def _hub_spec(**overrides) -> LevelSpec:
    data = json.loads(HUB.read_text(encoding="utf-8"))
    data.update(overrides)
    return LevelSpec.from_dict(data)


def _hub_session(progress: Progress | None = None, **overrides) -> Session:
    return Session(spec=_hub_spec(**overrides), progress=progress)


def _stand_at(session: Session, x: float, y: float) -> None:
    session.player.entity.x = x
    session.player.entity.y = y
    run_frames(session, 0.05)


def _press_e(session: Session, steps: int = 1) -> None:
    dt = session.cfg.physics.fixed_dt
    for _ in range(steps):
        session.update(dt, InputIntents(interact_pressed=True))


def _relieved_events(session: Session) -> list[float]:
    events: list[float] = []
    session.bus.subscribe("substance_relieved", lambda amount: events.append(amount))
    return events


def _stand_in_relief(session: Session, substance: float) -> None:
    relief = session.spec.relief
    assert relief is not None
    _stand_at(session, relief.x, session.player.entity.y)
    session.player.set_substance(substance)


# ------------------------------------------------------------------ parsing


def test_hub_relief_parses_and_missing_key_is_none():
    spec = LevelSpec.load(HUB)
    assert spec.relief == Relief(500.0, 620.0, 50.0)
    assert make_spec().relief is None


def test_editor_roundtrip_keeps_relief_key():
    from slg.editor import format_level

    data = json.loads(HUB.read_text(encoding="utf-8"))
    assert "relief" in data
    text = format_level(data)
    assert json.loads(text) == data
    assert LevelSpec.from_dict(json.loads(text)).relief is not None


# ------------------------------------------------------------------ ritual


def test_first_e_arms_without_relieving():
    session = _hub_session()
    events = _relieved_events(session)
    _stand_in_relief(session, 120.0)
    _press_e(session)
    assert session.relief_armed is True
    assert session.player.substance == 120.0
    assert events == []


def test_second_e_relieves_step_and_rescales_hp():
    session = _hub_session()
    events = _relieved_events(session)
    _stand_in_relief(session, 120.0)
    max_hp_before = session.player.entity.max_hp
    _press_e(session, 2)
    assert events == [50.0]
    assert session.player.substance == 70.0
    assert session.relief_armed is False
    assert session.player.entity.max_hp < max_hp_before
    assert session.player.entity.hp <= session.player.entity.max_hp


def test_each_step_requires_a_new_pair_of_presses():
    session = _hub_session()
    events = _relieved_events(session)
    _stand_in_relief(session, 120.0)
    _press_e(session, 4)  # arm+confirm, arm+confirm
    assert events == [50.0, 50.0]
    assert session.player.substance == 20.0


def test_remainder_below_step_is_taken_whole():
    session = _hub_session()
    events = _relieved_events(session)
    _stand_in_relief(session, 37.0)
    _press_e(session, 2)
    assert events == [37.0]
    assert session.player.substance == 0.0


def test_leaving_zone_disarms_without_e():
    session = _hub_session()
    _stand_in_relief(session, 100.0)
    _press_e(session)
    assert session.relief_armed is True
    session.player.entity.x = 200.0
    run_frames(session, session.cfg.physics.fixed_dt)
    assert session.relief_armed is False
    _stand_in_relief(session, 100.0)
    _press_e(session)
    assert session.relief_armed is True  # first E again, not a step
    assert session.player.substance == 100.0


def test_zero_substance_in_zone_is_noop():
    session = _hub_session()
    events = _relieved_events(session)
    _stand_in_relief(session, 0.0)
    _press_e(session, 2)
    assert session.relief_armed is False
    assert session.player.substance == 0.0
    assert events == []


def test_face_zone_wins_travel_over_relief():
    session = _hub_session(relief={"x": 640, "y": 520, "radius": 70})
    targets: list[str] = []
    session.bus.subscribe("travel", lambda target: targets.append(target))
    _stand_in_relief(session, 120.0)
    _press_e(session)
    assert targets == ["swamp"]
    assert session.relief_armed is False
    assert session.player.substance == 120.0


# ------------------------------------------------------------------ deposit


def test_deposit_accumulates_and_never_shrinks():
    progress = Progress().with_deposit(50.0).with_deposit(37.0)
    assert progress.deposited == 87.0
    assert progress.with_deposit(-5.0).deposited == 87.0


def test_deposit_survives_defeat_and_substance_copies():
    progress = Progress().with_deposit(87.0)
    assert progress.mark_defeated("swamp").deposited == 87.0
    assert progress.with_substance(10.0).deposited == 87.0


def test_deposit_roundtrip_and_legacy_file(tmp_path):
    path = tmp_path / "progress.json"
    Progress().with_deposit(50.0).save(path)
    assert Progress.load(path).deposited == 50.0
    path.write_text(json.dumps({"defeated": ["swamp"], "substance": 5.0}),
                    encoding="utf-8")
    assert Progress.load(path).deposited == 0.0


# ------------------------------------------------------------------ render


def test_relief_zone_renders_and_prompts_smoke():
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame

    from slg.render.palette import set_theme
    from slg.render.renderer import RELIEF_CONFIRM_PROMPT, Renderer

    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    try:
        session = Session(spec=LevelSpec.load(HUB))
        renderer = Renderer(session)
        _stand_in_relief(session, 80.0)
        assert renderer._near_relief() is not None
        assert renderer._prompt_text() == "E — оставить 50 у Жрицы"
        dt = session.cfg.physics.fixed_dt
        _press_e(session)  # arm
        assert renderer._prompt_text() == RELIEF_CONFIRM_PROMPT
        for _ in range(3):
            session.update(dt, InputIntents())
            renderer.update(dt)
            renderer.draw(screen)
        _press_e(session)  # confirm
        assert session.player.substance == 30.0
        renderer.draw(screen)
        # empty hands: no prompt, just the bowl
        _press_e(session, 2)
        assert session.player.substance == 0.0
        renderer.draw(screen)
    finally:
        set_theme("swamp")
        pygame.quit()
