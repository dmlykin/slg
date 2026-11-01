"""Sharp glass edges: side-face cuts only, gate by i-frames, roll protects."""

from __future__ import annotations

from slg.core.level import LevelSpec
from slg.core.physics import touching_sharp_side
from slg.core.player import InputIntents
from slg.core.session import SHARP_EDGE_DAMAGE, Session
from slg.core.world import Entity, Platform
from tests.conftest import make_spec, run_frames

FLOOR_TOP = 200.0
COLUMN_TOP = 120.0
COLUMN_X = 300.0


def _sharp_spec(*, sharp: bool = True) -> LevelSpec:
    return make_spec(
        platforms=[
            {"x": 0, "y": FLOOR_TOP, "w": 300, "h": 400, "organic": False},
            {"x": COLUMN_X, "y": COLUMN_TOP, "w": 40, "h": 480,
             "organic": False, "sharp": sharp},
            {"x": 340, "y": FLOOR_TOP, "w": 660, "h": 400, "organic": False},
        ],
        enemies=[],
        boss=None,
        boss_trigger=None,
        boss_gate=None,
        checkpoints=[],
    )


def _session_with_events(*, sharp: bool = True):
    session = Session(spec=_sharp_spec(sharp=sharp))
    events = []
    session.bus.subscribe("sharp_hit", lambda entity, x, y: events.append((x, y)))
    return session, events


def _walk_into_wall(session, seconds: float) -> None:
    dt = session.cfg.physics.fixed_dt
    for _ in range(round(seconds / dt)):
        session.update(dt, InputIntents(move=1))


def test_touching_side_face_deals_damage_and_event():
    session, events = _session_with_events()
    run_frames(session, 0.5)
    hp0 = session.player.entity.hp
    _walk_into_wall(session, 1.0)
    assert events, "sharp_hit was not published"
    assert session.player.entity.hp == hp0 - SHARP_EDGE_DAMAGE
    # knocked back away from the wall (to the left)
    assert session.player.entity.vx <= 0.0


def test_damage_not_repeated_inside_iframes():
    session, events = _session_with_events()
    run_frames(session, 0.5)
    _walk_into_wall(session, 0.9)
    assert len(events) == 1
    hp_after_first = session.player.entity.hp
    _walk_into_wall(session, 0.1)
    assert len(events) == 1
    assert session.player.entity.hp == hp_after_first


def test_standing_on_top_is_safe():
    session, events = _session_with_events()
    p = session.player
    p.entity.x = 320
    p.entity.y = COLUMN_TOP - p.entity.half_h
    run_frames(session, 1.0, InputIntents(move=-1))
    # re-centre and walk the other way, still on the column top
    p.entity.x = 320
    p.entity.y = COLUMN_TOP - p.entity.half_h
    run_frames(session, 0.2, InputIntents(move=1))
    assert events == []
    assert p.entity.hp == p.entity.max_hp


def test_roll_iframes_protect_from_the_edge():
    session, events = _session_with_events()
    p = session.player
    p.entity.x = 200.0
    p.entity.y = FLOOR_TOP - p.entity.half_h
    run_frames(session, 0.3)
    # roll right: contact happens ~0.15s in, inside the roll i-frame window
    dt = session.cfg.physics.fixed_dt
    session.update(dt, InputIntents(move=1, roll_pressed=True))
    for _ in range(round(0.2 / dt)):
        session.update(dt, InputIntents())
    assert p.state == "roll"
    assert events == []
    assert p.entity.hp == p.entity.max_hp


def test_blunt_wall_does_not_hurt():
    session, events = _session_with_events(sharp=False)
    run_frames(session, 0.5)
    _walk_into_wall(session, 1.5)
    assert events == []
    assert session.player.entity.hp == session.player.entity.max_hp


def test_helper_ignores_top_edge():
    entity = Entity(id=1, x=100, y=FLOOR_TOP - 28.0, width=26.0, height=56.0)
    platform = Platform(x=COLUMN_X, y=COLUMN_TOP, width=40, height=480,
                        organic=False, sharp=True)
    # standing far away: no contact
    assert touching_sharp_side(entity, [platform]) is None
    # touching the left face while standing on top: only if the body overlaps
    entity.x = COLUMN_X - entity.half_w
    entity.y = COLUMN_TOP - entity.half_h
    assert touching_sharp_side(entity, [platform]) is None  # body sits above the strip
    # body lowered next to the face: contact
    entity.y = COLUMN_TOP + 40.0
    hit = touching_sharp_side(entity, [platform])
    assert hit is not None
    assert hit[1] == -1
