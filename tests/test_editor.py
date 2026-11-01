"""Level editor: data model, save formatting, camera and headless boot."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slg.core.level import LevelSpec
from slg.editor import (
    EditorCamera,
    EditorState,
    format_level,
    resize_rect,
    snap,
)

DATA = Path(__file__).resolve().parents[1] / "src" / "slg" / "data"


def _load_dict(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _copy_level(name: str, tmp_path: Path) -> Path:
    path = tmp_path / name
    path.write_text((DATA / name).read_text(encoding="utf-8"), encoding="utf-8")
    return path


@pytest.mark.parametrize("name", ["level_00.json", "level_01.json", "level_02.json",
                                  "level_03.json"])
def test_format_level_roundtrip(name):
    data = _load_dict(name)
    text = format_level(data)
    assert json.loads(text) == data
    LevelSpec.from_dict(json.loads(text))  # still a valid level


def test_editor_opens_all_shipped_levels():
    for name in ("level_00.json", "level_01.json", "level_02.json", "level_03.json"):
        state = EditorState.load(DATA / name)
        assert state.rect_targets()
        assert state.point_targets()
        assert state.build_spec().name
        assert state.vertical is (name == "level_03.json")


def test_editor_keeps_hub_figure_and_portals(tmp_path):
    path = _copy_level("level_00.json", tmp_path)
    state = EditorState.load(path)
    assert state.data["figure"]["faces"]
    state.add_platform(700.0, 300.0, w=140.0, h=50.0)
    assert "сохранено" in state.save()

    spec = LevelSpec.load(path)
    assert spec.theme == "sanctum"
    assert spec.figure is not None
    assert [f.target for f in spec.figure.faces] == ["swamp", "glass", "well"]
    assert any(p.width == 140.0 and p.height == 50.0 for p in spec.platforms)



def test_editor_platform_add_move_delete():
    state = EditorState.load(DATA / "level_02.json")
    count = len(state.platforms)
    sel = state.add_platform(123.0, 456.0)
    assert len(state.platforms) == count + 1
    assert state.selection == sel
    assert state.rect_of(sel) == (120.0, 460.0, 120.0, 40.0)
    state.set_rect(sel, 200.0, 300.0, 150.0, 60.0)
    assert state.rect_of(sel) == (200.0, 300.0, 150.0, 60.0)
    assert state.pick(210.0, 310.0) == sel
    assert state.delete_selection()
    assert len(state.platforms) == count
    assert state.selection is None


def test_editor_platform_flags_toggle():
    state = EditorState.load(DATA / "level_02.json")
    sel = state.add_platform(0.0, 0.0)
    plat = state.platforms[sel.index]
    assert plat.get("organic", True) is True
    state.toggle_platform_flag(sel, "organic")
    assert plat["organic"] is False
    state.toggle_platform_flag(sel, "sharp")
    assert plat["sharp"] is True
    state.toggle_platform_flag(sel, "sharp")
    assert "sharp" not in plat


def test_editor_enemy_snaps_to_platform_top():
    state = EditorState.load(DATA / "level_02.json")
    sel = state.add_enemy("shard", 400.0, 560.0)
    enemy = state.enemies[sel.index]
    assert enemy == {"type": "shard", "x": 400.0, "y": 598.0}


def test_editor_checkpoint_gets_unique_name():
    state = EditorState.load(DATA / "level_02.json")
    used_before = {c["name"] for c in state.checkpoints}
    sel = state.add_checkpoint(1700.0, 590.0)
    cp = state.checkpoints[sel.index]
    assert cp["name"] not in used_before
    assert cp["y"] == 620.0


def test_editor_adding_twin_converts_legacy_boss():
    state = EditorState.load(DATA / "level_01.json")
    assert "boss" in state.data
    sel = state.add_boss("prism", 3800.0, 500.0)
    assert "boss" not in state.data
    assert [b["type"] for b in state.bosses] == ["boss", "prism"]
    assert sel.kind == "boss" and sel.index == 1
    LevelSpec.from_dict(json.loads(json.dumps(state.data)))


def test_editor_sets_trigger_gate_and_spawn():
    state = EditorState.load(DATA / "level_02.json")
    state.set_trigger(4100.0, 590.0)
    assert state.data["boss_trigger"]["x"] == 4100.0
    assert state.data["boss_trigger"]["w"] == 120
    state.set_gate(4000.0, 590.0)
    assert state.data["boss_gate"]["y"] == 440.0
    state.set_spawn(150.0, 590.0)
    assert state.data["player_spawn"] == [150.0, 590.0]
    kinds = {t.kind for t in state.rect_targets()}
    assert {"trigger", "gate"} <= kinds


def test_editor_save_and_reload(tmp_path):
    path = _copy_level("level_02.json", tmp_path)
    state = EditorState.load(path)
    state.add_platform(700.0, 300.0, w=140.0, h=50.0)
    state.set_trigger(4200.0, 590.0)
    assert "сохранено" in state.save()
    assert not state.dirty

    spec = LevelSpec.load(path)
    assert spec.theme == "glass"
    assert any(p.width == 140.0 and p.height == 50.0 for p in spec.platforms)
    assert spec.boss_trigger is not None and spec.boss_trigger.x == 4200.0


def test_editor_save_and_reload_well_keeps_vertical(tmp_path):
    path = _copy_level("level_03.json", tmp_path)
    state = EditorState.load(path)
    assert state.vertical is True
    assert state.theme == "well"
    sel = state.add_boss("keeper", 500.0, 4600.0)
    assert state.bosses[sel.index]["y"] == 4582.0
    assert "сохранено" in state.save()

    spec = LevelSpec.load(path)
    assert spec.vertical is True
    assert spec.theme == "well"


def test_editor_save_rejects_broken_data(tmp_path):
    path = _copy_level("level_02.json", tmp_path)
    before = path.read_text(encoding="utf-8")
    state = EditorState.load(path)
    state.data.pop("player_spawn")
    with pytest.raises(KeyError):
        state.save()
    assert path.read_text(encoding="utf-8") == before

def test_camera_world_screen_roundtrip_and_clamp():
    cam = EditorCamera((0, -600, 5400, 1600), screen=(1280, 720))
    cam.snap_to(2500, 400)
    for x, y in ((2500, 400), (0, -600), (5300, 900)):
        sx, sy = cam.world_to_screen(x, y)
        wx, wy = cam.screen_to_world(sx, sy)
        assert abs(wx - x) < 1.0 and abs(wy - y) < 1.0
    cam.snap_to(-9999, -9999)
    assert cam.center_x >= 640.0 - 0.01
    assert cam.center_y >= -600 + 360.0 - 0.01


def test_resize_rect_handles_and_min_size():
    x, y, w, h = 100.0, 100.0, 200.0, 80.0
    assert resize_rect(x, y, w, h, "e", 420.0, 0.0) == (100.0, 100.0, 320.0, 80.0)
    assert resize_rect(x, y, w, h, "nw", 80.0, 60.0) == (80.0, 60.0, 220.0, 120.0)
    left, top, rw, rh = resize_rect(x, y, w, h, "se", 0.0, 0.0)
    assert rw >= 20.0 and rh >= 20.0
    assert snap(123.0) == 120.0
    assert snap(126.0) == 130.0
    assert snap(126.0, 0.0) == 126.0


def test_editor_boots_and_draws_headless(tmp_path, monkeypatch):
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame

    from slg import editor as editor_mod
    from slg.render.palette import set_theme

    path = _copy_level("level_02.json", tmp_path)
    calls = {"n": 0}

    def fake_get():
        calls["n"] += 1
        if calls["n"] >= 4:
            return [pygame.event.Event(pygame.QUIT)]
        return []

    monkeypatch.setattr(editor_mod.pygame.event, "get", fake_get)
    try:
        assert editor_mod.LevelEditor(path).run() == 0
    finally:
        set_theme("swamp")
        pygame.quit()
