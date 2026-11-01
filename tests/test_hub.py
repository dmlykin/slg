"""Hub: the Three-Faced figure, return portals, travel events and the finale."""

from __future__ import annotations

import json
from pathlib import Path

from slg.core.level import LevelSpec
from slg.core.player import InputIntents
from slg.core.progress import Progress
from slg.core.session import Session
from tests.conftest import run_frames

DATA = Path(__file__).resolve().parents[1] / "src" / "slg" / "data"
HUB = DATA / "level_00.json"

ALL_BURDENS = ("swamp", "glass", "well")


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


def _travel_targets(session: Session) -> list[str]:
    targets: list[str] = []
    session.bus.subscribe("travel", lambda target: targets.append(target))
    return targets


def test_hub_level_loads_with_three_faces():
    spec = LevelSpec.load(HUB)
    assert spec.name == "Снятие Тягот"
    assert spec.theme == "sanctum"
    assert spec.figure is not None
    assert [f.target for f in spec.figure.faces] == list(ALL_BURDENS)
    assert [f.requires for f in spec.figure.faces] == [None, "swamp", "glass"]
    assert spec.enemies == []
    assert spec.bosses == []
    assert spec.kill_zones == []


def test_default_session_has_empty_progress():
    session = _hub_session()
    assert session.progress == Progress()
    assert session.face_state(session.spec.figure.faces[0]) == "available"
    for face in session.spec.figure.faces[1:]:
        assert session.face_state(face) == "locked"


def test_available_face_travels_to_swamp():
    session = _hub_session()
    targets = _travel_targets(session)
    turner = session.spec.figure.faces[0]
    _stand_at(session, turner.x, session.player.entity.y)
    _press_e(session)
    assert targets == ["swamp"]


def test_locked_face_does_nothing():
    session = _hub_session()
    targets = _travel_targets(session)
    warden = session.spec.figure.faces[1]
    _stand_at(session, warden.x, session.player.entity.y)
    _press_e(session)
    assert targets == []
    assert session.face_state(warden) == "locked"


def test_face_opens_after_prerequisite_is_defeated():
    progress = Progress().mark_defeated("swamp")
    session = _hub_session(progress)
    warden = session.spec.figure.faces[1]
    assert session.face_state(warden) == "available"
    targets = _travel_targets(session)
    _stand_at(session, warden.x, session.player.entity.y)
    _press_e(session)
    assert targets == ["glass"]


def test_portal_returns_to_hub_and_restores_resources():
    session = Session(spec=LevelSpec.load(DATA / "level_01.json"))
    portal = session.spec.portals[0]
    assert portal.target == "hub"
    p = session.player
    p.entity.hp = 7
    p.heal_charges = 0
    p.stamina.value = 0.0
    targets = _travel_targets(session)
    _stand_at(session, portal.x, p.entity.y)
    _press_e(session)
    assert targets == ["hub"]
    assert p.entity.hp == p.entity.max_hp
    assert p.heal_charges == p.cfg.player.heal_charges
    assert p.stamina.value == p.stamina.max


def test_portal_only_works_in_reach():
    session = Session(spec=LevelSpec.load(DATA / "level_01.json"))
    targets = _travel_targets(session)
    _press_e(session)
    assert targets == []


def test_hub_finale_requires_all_burdens():
    session = _hub_session(Progress().mark_defeated("swamp").mark_defeated("glass"))
    assert session.hub_finale is False
    session = _hub_session(
        Progress().mark_defeated("swamp").mark_defeated("glass").mark_defeated("well")
    )
    assert session.hub_finale is True


def test_finale_press_dismisses_and_does_not_travel():
    session = _hub_session(
        Progress().mark_defeated("swamp").mark_defeated("glass").mark_defeated("well")
    )
    turner = session.spec.figure.faces[0]
    _stand_at(session, turner.x, session.player.entity.y)
    targets = _travel_targets(session)
    _press_e(session)
    assert session.finale_dismissed is True
    assert targets == []
    _press_e(session)
    assert targets == ["swamp"]
