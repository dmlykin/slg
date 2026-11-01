"""Level loading, checkpoints, death -> respawn."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slg.core.level import LevelSpec
from slg.core.player import InputIntents
from tests.conftest import run_frames

DATA_LEVEL = Path(__file__).resolve().parents[1] / "src" / "slg" / "data" / "level_01.json"
DATA_HUB = Path(__file__).resolve().parents[1] / "src" / "slg" / "data" / "level_00.json"


def test_shipped_level_loads():
    spec = LevelSpec.load(DATA_LEVEL)
    assert spec.name
    assert len(spec.platforms) >= 5
    assert spec.player_spawn[1] > 0
    assert spec.boss is not None
    assert spec.boss_trigger is not None
    assert spec.boss_gate is not None
    assert any(c.name for c in spec.checkpoints)
    types = {e.type for e in spec.enemies}
    assert types == {"crawler", "spitter"}


def test_shipped_level_spawns_are_above_platforms():
    spec = LevelSpec.load(DATA_LEVEL)
    tops = [(p.x, p.x + p.width, p.y) for p in spec.platforms]
    def on_ground(x, y, half_h):
        for left, right, top in tops:
            if left - 5 <= x <= right + 5 and abs((top - half_h) - y) < 30:
                return True
        return False
    assert on_ground(*spec.player_spawn, 28)
    for e in spec.enemies:
        assert on_ground(e.x, e.y, 15 if e.type == "crawler" else 20), e
    assert on_ground(spec.boss.x, spec.boss.y, 60)


def test_level_from_dict_roundtrip(tmp_path):
    path = tmp_path / "lvl.json"
    path.write_text(json.dumps({
        "name": "test", "bounds": [0, -400, 2000, 1000],
        "player_spawn": [100, 100],
        "platforms": [{"x": 0, "y": 200, "w": 600, "h": 200}],
        "enemies": [{"type": "crawler", "x": 400, "y": 185}],
    }), encoding="utf-8")
    loaded = LevelSpec.load(path)
    assert loaded.name == "test"
    assert len(loaded.platforms) == 1
    assert loaded.enemies[0].type == "crawler"
    assert loaded.boss is None


def test_unknown_enemy_type_rejected(session):
    with pytest.raises(ValueError):
        session._spawn_enemy("banshee", 0, 0)


def test_hub_level_loads():
    spec = LevelSpec.load(DATA_HUB)
    assert spec.name == "Снятие Тягот"
    assert spec.theme == "sanctum"
    assert spec.figure is not None
    assert [f.target for f in spec.figure.faces] == ["swamp", "glass", "well"]
    assert [f.requires for f in spec.figure.faces] == [None, "swamp", "glass"]
    assert spec.enemies == []
    assert spec.bosses == []
    assert spec.kill_zones == []
    assert spec.checkpoints == []
    assert spec.portals == []


def test_hub_spawn_stands_on_the_floor():
    spec = LevelSpec.load(DATA_HUB)
    x, y = spec.player_spawn
    assert any(p.x <= x <= p.x + p.width and p.y == pytest.approx(y + 28, abs=8)
               for p in spec.platforms)


@pytest.mark.parametrize("name", ["level_01.json", "level_02.json", "level_03.json"])
def test_return_portal_sits_near_spawn(name):
    spec = LevelSpec.load(Path(DATA_LEVEL).parent / name)
    assert len(spec.portals) == 1
    portal = spec.portals[0]
    px, py = spec.player_spawn
    assert portal.target == "hub"
    assert abs(portal.x - px) <= 250
    assert abs(portal.y - py) <= 120



def test_checkpoint_activation_with_e(session):
    run_frames(session, 0.5)
    p = session.player
    p.entity.x = 900
    p.entity.y = 172
    p.entity.hp = 10
    p.heal_charges = 0
    events = []
    session.bus.subscribe("checkpoint", lambda checkpoint: events.append(checkpoint))
    run_frames(session, 0.05, InputIntents(interact_pressed=True))
    assert events
    assert "cp1" in session.activated_checkpoints
    assert p.entity.hp == p.entity.max_hp
    assert p.heal_charges == p.cfg.player.heal_charges
    assert session.current_checkpoint == (900, 160)


def test_checkpoint_requires_proximity(session):
    run_frames(session, 0.5)
    run_frames(session, 0.05, InputIntents(interact_pressed=True))
    assert session.activated_checkpoints == set()


def test_death_respawns_at_checkpoint_with_reset(session):
    run_frames(session, 0.5)
    p = session.player
    # activate the checkpoint
    p.entity.x = 900
    p.entity.y = 172
    run_frames(session, 0.05, InputIntents(interact_pressed=True))
    assert session.activated_checkpoints

    # damage the player, kill an enemy, then die
    p.entity.hp = 5
    crawler = session.enemies[0]
    crawler.entity.hp = 1
    crawler.take_hit(10, 0.0, 0.0)
    assert not crawler.entity.alive
    p.take_hit(999, 0.0)
    assert p.state == "dead"

    respawns = []
    session.bus.subscribe("respawn", lambda: respawns.append(True))
    run_frames(session, 2.0)
    assert respawns
    assert p.state == "idle"
    assert p.entity.hp == p.entity.max_hp
    assert p.entity.x == pytest.approx(900, abs=0.1)
    # enemies revived
    alive = [e for e in session.enemies if e.entity.alive]
    assert len(alive) == len(session.spec.enemies)


def test_respawn_resets_undead_boss_and_gate(session):
    run_frames(session, 0.5)
    boss = session.boss
    session.player.entity.x = 1280
    session.player.entity.y = 150
    run_frames(session, 0.1)
    assert session.boss_gate_active
    # hurt the boss, then die
    boss.activate()
    boss.entity.hp = 100
    session.player.take_hit(999, 0.0)
    run_frames(session, 2.0)
    assert session.player.state == "idle"
    assert not session.boss_gate_active
    assert session.boss.entity.hp == session.boss.entity.max_hp
    assert session.boss.state == "dormant"


def test_victory_keeps_boss_dead_on_respawn_path(session):
    run_frames(session, 0.5)
    boss = session.boss
    boss.activate()
    boss.entity.hp = 1
    boss.take_hit(50, 0.0, 0.0)
    run_frames(session, 0.05)
    assert session.victory
    assert session.boss_defeated
    session.respawn_everything()
    assert session.boss.entity.hp == 0 or session.boss is None or not session.boss.entity.alive


DATA_LEVEL_02 = Path(__file__).resolve().parents[1] / "src" / "slg" / "data" / "level_02.json"


def test_level_01_keeps_swamp_theme_and_single_boss():
    spec = LevelSpec.load(DATA_LEVEL)
    assert spec.theme == "swamp"
    assert spec.boss is not None
    assert spec.bosses == []
    assert not any(p.sharp for p in spec.platforms)
    assert all(p.organic for p in spec.platforms)


def test_level_02_loads():
    spec = LevelSpec.load(DATA_LEVEL_02)
    assert spec.name == "Выжженное стекло"
    assert spec.theme == "glass"
    assert spec.boss is None
    assert [b.type for b in spec.bosses] == ["blade", "prism"]
    assert len(spec.checkpoints) == 2
    assert {c.name for c in spec.checkpoints} == {"glass_01", "glass_02"}
    assert any(p.sharp for p in spec.platforms)
    assert all(not p.organic for p in spec.platforms)
    assert {e.type for e in spec.enemies} == {"crawler", "spitter", "shard"}
    assert sum(1 for e in spec.enemies if e.type == "shard") >= 5
    assert spec.boss_trigger is not None
    assert spec.boss_gate is not None
    assert spec.bounds[2] >= 4600


def test_level_02_spawns_are_above_platforms():
    spec = LevelSpec.load(DATA_LEVEL_02)
    tops = [(p.x, p.x + p.width, p.y) for p in spec.platforms]

    def on_ground(x, y, half_h):
        for left, right, top in tops:
            if left - 5 <= x <= right + 5 and abs((top - half_h) - y) < 30:
                return True
        return False

    assert on_ground(*spec.player_spawn, 28)
    half_h = {"crawler": 15, "spitter": 20, "shard": 22}
    for e in spec.enemies:
        assert on_ground(e.x, e.y, half_h[e.type]), e
    for b in spec.bosses:
        assert on_ground(b.x, b.y, 48), b


def test_level_02_session_spawns_twins_and_shards():
    from slg.core.session import Session

    session = Session(spec=LevelSpec.load(DATA_LEVEL_02))
    assert len(session.bosses) == 2
    assert {b.kind for b in session.bosses} == {"blade", "prism"}
    assert sum(1 for e in session.enemies if e.entity.kind == "shard") >= 5
    assert session.bosses[0].state == "dormant"


def test_level_02_abyss_kills_falling_player():
    from slg.core.player import InputIntents
    from slg.core.session import Session

    spec = LevelSpec.load(DATA_LEVEL_02)
    session = Session(spec=spec)
    p = session.player
    for x, y in ((830.0, 640.0), (2090.0, 500.0), (3210.0, 500.0)):
        p.entity.x, p.entity.y = x, y
        p.entity.hp = p.entity.max_hp
        p.respawn_at(x, y)
        for _ in range(45):
            session.update(session.cfg.physics.fixed_dt, InputIntents())
        assert p.state == "dead", f"did not die falling at x={x}"
        run_frames(session, 2.0)  # let the respawn cycle finish


def test_level_02_boss_zone_is_enemy_free():
    """The pre-boss plain and the arena hold no regular enemies."""
    spec = LevelSpec.load(DATA_LEVEL_02)
    gate_x = spec.boss_gate.x
    assert all(e.x < gate_x - 150 for e in spec.enemies), [
        (e.type, e.x) for e in spec.enemies if e.x >= gate_x - 150
    ]
    # all of them live in the earlier sections
    assert max(e.x for e in spec.enemies) <= 3200


DATA_LEVEL_03 = Path(__file__).resolve().parents[1] / "src" / "slg" / "data" / "level_03.json"


def test_level_03_loads():
    spec = LevelSpec.load(DATA_LEVEL_03)
    assert spec.name == "Немой колодец"
    assert spec.theme == "well"
    assert spec.vertical is True
    assert spec.bounds == (0, -300, 2000, 5350)
    assert spec.boss is None
    assert [b.type for b in spec.bosses] == ["keeper"]
    assert len(spec.checkpoints) == 3
    assert {c.name for c in spec.checkpoints} == {"well_01", "well_02", "well_03"}
    assert spec.boss_trigger is not None
    assert spec.boss_gate is not None
    assert len(spec.kill_zones) == 1
    assert len(spec.platforms) == 10
    assert all(p.organic for p in spec.platforms)
    assert not any(p.sharp for p in spec.platforms)
    assert {e.type for e in spec.enemies} == {"crawler", "spitter", "orb"}
    assert not any(e.type == "shard" for e in spec.enemies)
    assert max(e.y for e in spec.enemies) < 4200


def test_level_03_spawns_are_above_platforms():
    spec = LevelSpec.load(DATA_LEVEL_03)
    tops = [(p.x, p.x + p.width, p.y) for p in spec.platforms]

    def on_ground(x, y, half_h):
        for left, right, top in tops:
            if left - 5 <= x <= right + 5 and abs((top - half_h) - y) < 30:
                return True
        return False

    assert on_ground(*spec.player_spawn, 28)
    half_h = {"crawler": 15, "spitter": 20, "shard": 22, "orb": 17}
    for e in spec.enemies:
        assert on_ground(e.x, e.y, half_h[e.type]), e
    for b in spec.bosses:
        assert on_ground(b.x, b.y, 68), b


def test_level_03_session_spawns_keeper_boss():
    from slg.core.session import Session

    session = Session(spec=LevelSpec.load(DATA_LEVEL_03))
    assert len(session.bosses) == 1
    assert session.bosses[0].kind == "keeper"
    assert session.bosses[0].state == "dormant"
    kinds = [e.entity.kind for e in session.enemies]
    assert kinds.count("orb") == 3
    assert "shard" not in kinds


def test_level_03_abyss_kills_falling_player():
    from slg.core.session import Session

    session = Session(spec=LevelSpec.load(DATA_LEVEL_03))
    p = session.player
    p.respawn_at(1000.0, 200.0)
    dt = session.cfg.physics.fixed_dt
    for _ in range(int(5.0 / dt)):
        session.update(dt, InputIntents())
        if p.state == "dead":
            break
    assert p.state == "dead", "the central shaft must kill a falling player"
    run_frames(session, 2.0)  # let the respawn cycle finish
    assert p.state == "idle"


def _level_03_geometry_spec() -> LevelSpec:
    data = json.loads(DATA_LEVEL_03.read_text(encoding="utf-8"))
    data["enemies"] = []
    data["bosses"] = []
    data.pop("boss_trigger", None)
    data.pop("boss_gate", None)
    return LevelSpec.from_dict(data)


def test_level_03_arena_floor_and_jump_are_safe():
    from slg.core.session import Session

    session = Session(spec=_level_03_geometry_spec())
    p = session.player
    p.respawn_at(1000.0, 4622.0)
    run_frames(session, 0.5)
    assert p.state != "dead", "standing on the arena floor must be safe"
    run_frames(session, 0.05, InputIntents(jump_pressed=True, jump_held=True))
    run_frames(session, 1.5, InputIntents(jump_held=True))
    assert p.state != "dead", "jumping on the arena floor must clear the kill zone"


def test_level_03_boss_gate_closes_and_opens():
    from slg.core.session import Session

    session = Session(spec=LevelSpec.load(DATA_LEVEL_03))
    p = session.player
    p.respawn_at(1500.0, 4622.0)
    run_frames(session, 0.3)
    assert session.boss_gate_active
    assert session.spec.boss_gate in session.world.platforms
    assert session.bosses[0].state != "dormant"

    boss = session.boss
    boss.entity.hp = 1
    boss.take_hit(50, 0.0, 0.0)
    run_frames(session, 0.1)
    assert session.victory
    assert not session.boss_gate_active
    assert session.spec.boss_gate not in session.world.platforms


def test_level_03_checkpoint_respawn():
    from slg.core.session import Session

    session = Session(spec=LevelSpec.load(DATA_LEVEL_03))
    p = session.player
    p.respawn_at(300.0, 4022.0)
    run_frames(session, 0.1, InputIntents(interact_pressed=True))
    assert "well_03" in session.activated_checkpoints
    assert session.current_checkpoint == (300.0, 4010.0)

    p.take_hit(999, 0.0)
    assert p.state == "dead"
    run_frames(session, 2.0)
    assert p.state == "idle"
    assert p.entity.x == pytest.approx(300.0, abs=0.5)
    assert p.entity.y == pytest.approx(4022.0, abs=30.0)
