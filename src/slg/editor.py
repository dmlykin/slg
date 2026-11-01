"""In-game level editor (--edit).

A small mouse-driven tool for the hand-written JSON levels:
  * pan with WASD/arrows or middle-drag;
  * click a platform to select, drag the body to move, drag a handle to resize;
  * Shift+click empty space adds a platform, right-click deletes;
  * keys place enemies, checkpoints, bosses, trigger and gate;
  * F2 saves the level back to its JSON file, F5 reloads it from disk.

The editing model (`EditorState`) is pure data; only `run_editor` touches pygame.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pygame

from slg.core.level import LevelSpec
from slg.core.world import Platform
from slg.render.background import Background
from slg.render.camera import SCREEN_H, SCREEN_W
from slg.render.palette import set_theme
from slg.render.terrain import TerrainRenderer

SNAP = 10.0
MIN_SIZE = 20.0
PAN_SPEED = 900.0
HANDLE_RADIUS = 9.0
POINT_PICK_PAD = 5.0

ENEMY_HALF_H = {"crawler": 15.0, "spitter": 20.0, "shard": 22.0, "orb": 17.0}
BOSS_HALF_H = {"keeper": 68.0}
BOSS_HALF_H_DEFAULT = 48.0
LEGACY_BOSS_SIZE = (96.0, 120.0)

RECT_KEYS = ("x", "y", "w", "h")
ITEM_ORDER = {
    "platforms": ("x", "y", "w", "h", "organic", "sharp"),
    "kill_zones": ("x", "y", "w", "h"),
    "checkpoints": ("x", "y", "radius", "name"),
    "portals": ("x", "y", "radius", "name", "target"),
    "enemies": ("type", "x", "y"),
    "bosses": ("type", "x", "y"),
    "boss_trigger": ("x", "y", "w", "h", "name"),
    "boss_gate": ("x", "y", "w", "h"),
    "boss": ("type", "x", "y"),
    "figure": ("x", "y", "faces"),
    "faces": ("type", "x", "y", "target", "requires"),
}
TOP_ORDER = ("name", "theme", "vertical", "bounds", "player_spawn", "platforms",
             "kill_zones", "checkpoints", "portals", "figure", "enemies",
             "boss", "bosses", "boss_trigger", "boss_gate")

COL_GRID = (44, 48, 58)
COL_SELECT = (120, 236, 255)
COL_HANDLE = (245, 250, 255)
COL_PLATFORM = (90, 110, 130)
COL_ENEMY = {"crawler": (228, 96, 72), "spitter": (140, 214, 120),
             "shard": (120, 226, 255), "orb": (116, 176, 162)}
COL_CP = (244, 214, 110)
COL_BOSS = (255, 120, 170)
COL_TRIGGER = (250, 210, 80)
COL_GATE = (240, 140, 60)
COL_KILL = (220, 60, 50)
COL_TEXT = (226, 236, 246)
COL_DIM = (150, 164, 180)


# ------------------------------------------------------------------ formatting

def _scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _fmt_value(value) -> str:
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_scalar(v) for v in value) + "]"
    return _scalar(value)


def _fmt_obj(obj: dict, order: tuple[str, ...]) -> str:
    keys = [k for k in order if k in obj]
    keys += [k for k in obj if k not in order]
    body = ", ".join(f'"{k}": {_fmt_value(obj[k])}' for k in keys)
    return "{ " + body + " }"


def format_level(data: dict) -> str:
    """Render level data in the hand-written compact style used by data/*.json."""
    parts: list[str] = []
    keys = [k for k in TOP_ORDER if k in data]
    keys += sorted(k for k in data if k not in TOP_ORDER)
    for key in keys:
        value = data[key]
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            item_order = ITEM_ORDER.get(key, ())
            inner = ",\n".join(f"    {_fmt_obj(item, item_order)}" for item in value)
            parts.append(f'  "{key}": [\n{inner}\n  ]')
        elif isinstance(value, dict):
            parts.append(f'  "{key}": {_fmt_obj(value, ITEM_ORDER.get(key, ()))}')
        else:
            parts.append(f'  "{key}": {_fmt_value(value)}')
    return "{\n" + ",\n".join(parts) + "\n}\n"


def _norm_rects(data: dict) -> dict:
    """Levels may use width/height; the editor works with w/h."""
    out = dict(data)
    for key in ("platforms", "kill_zones"):
        nodes = []
        for node in out.get(key, []) or []:
            node = dict(node)
            if "width" in node:
                node["w"] = node.pop("width")
            if "height" in node:
                node["h"] = node.pop("height")
            nodes.append(node)
        out[key] = nodes
    for key in ("boss_trigger", "boss_gate"):
        node = out.get(key)
        if isinstance(node, dict):
            node = dict(node)
            if "width" in node:
                node["w"] = node.pop("width")
            if "height" in node:
                node["h"] = node.pop("height")
            out[key] = node
    return out


def snap(value: float, step: float = SNAP) -> float:
    if step <= 0.0:
        return value
    return round(value / step) * step


# ------------------------------------------------------------------ selection

@dataclass(frozen=True)
class Selection:
    kind: str      # platform|trigger|gate|enemy|checkpoint|boss|legacy_boss|spawn
    index: int = 0


@dataclass(frozen=True)
class RectTarget:
    kind: str
    index: int
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class PointTarget:
    kind: str
    index: int
    x: float
    y: float
    half_w: float
    half_h: float


RECT_SELECTIONS = ("platform", "trigger", "gate")


def handle_positions(x: float, y: float, w: float, h: float) -> dict[str, tuple[float, float]]:
    cx, cy = x + w / 2.0, y + h / 2.0
    return {
        "nw": (x, y), "n": (cx, y), "ne": (x + w, y),
        "w": (x, cy), "e": (x + w, cy),
        "sw": (x, y + h), "s": (cx, y + h), "se": (x + w, y + h),
    }


def resize_rect(x: float, y: float, w: float, h: float, handle: str,
                wx: float, wy: float, step: float = SNAP) -> tuple[float, float, float, float]:
    left, top, right, bottom = x, y, x + w, y + h
    if "w" in handle:
        left = min(snap(wx, step), right - MIN_SIZE)
    if "e" in handle:
        right = max(snap(wx, step), left + MIN_SIZE)
    if "n" in handle:
        top = min(snap(wy, step), bottom - MIN_SIZE)
    if "s" in handle:
        bottom = max(snap(wy, step), top + MIN_SIZE)
    return left, top, right - left, bottom - top


# ------------------------------------------------------------------ model

class EditorState:
    """Mutable level JSON plus edit operations. No pygame in here."""

    def __init__(self, path: Path, data: dict) -> None:
        self.path = path
        self.data = _norm_rects(data)
        self.dirty = False
        self.selection: Selection | None = None

    @staticmethod
    def load(path: Path) -> "EditorState":
        return EditorState(path, json.loads(Path(path).read_text(encoding="utf-8")))

    # -- views ---------------------------------------------------------
    @property
    def name(self) -> str:
        return str(self.data.get("name", "unnamed"))

    @property
    def theme(self) -> str:
        return str(self.data.get("theme", "swamp"))

    @property
    def vertical(self) -> bool:
        return bool(self.data.get("vertical", False))

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        b = self.data.get("bounds", (0, 0, 4000, 1000))
        return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))

    @property
    def platforms(self) -> list[dict]:
        return self.data.setdefault("platforms", [])

    @property
    def enemies(self) -> list[dict]:
        return self.data.setdefault("enemies", [])

    @property
    def checkpoints(self) -> list[dict]:
        return self.data.setdefault("checkpoints", [])

    @property
    def bosses(self) -> list[dict]:
        return self.data.setdefault("bosses", [])

    @property
    def kill_zones(self) -> list[dict]:
        return self.data.get("kill_zones", [])

    @property
    def player_spawn(self) -> tuple[float, float]:
        s = self.data.get("player_spawn", [0, 0])
        return (float(s[0]), float(s[1]))

    def platform_objects(self) -> list[Platform]:
        return [
            Platform(x=float(p["x"]), y=float(p["y"]), width=float(p["w"]),
                     height=float(p["h"]), organic=bool(p.get("organic", True)),
                     sharp=bool(p.get("sharp", False)))
            for p in self.platforms
        ]

    def build_spec(self) -> LevelSpec:
        """Validate the edited data by loading it as a real level."""
        return LevelSpec.from_dict(json.loads(json.dumps(self.data)))

    # -- targets -------------------------------------------------------
    def rect_targets(self) -> list[RectTarget]:
        out = [
            RectTarget("platform", i, float(p["x"]), float(p["y"]),
                       float(p["w"]), float(p["h"]))
            for i, p in enumerate(self.platforms)
        ]
        for kind, key in (("trigger", "boss_trigger"), ("gate", "boss_gate")):
            node = self.data.get(key)
            if isinstance(node, dict):
                out.append(RectTarget(kind, 0, float(node["x"]), float(node["y"]),
                                      float(node["w"]), float(node["h"])))
        return out

    def point_targets(self) -> list[PointTarget]:
        out: list[PointTarget] = []
        for i, e in enumerate(self.enemies):
            half_h = ENEMY_HALF_H.get(e.get("type", ""), 18.0)
            out.append(PointTarget("enemy", i, float(e["x"]), float(e["y"]), 18.0, half_h))
        for i, c in enumerate(self.checkpoints):
            out.append(PointTarget("checkpoint", i, float(c["x"]), float(c["y"]),
                                   18.0, 18.0))
        for i, b in enumerate(self.bosses):
            half_h = BOSS_HALF_H.get(b.get("type", ""), BOSS_HALF_H_DEFAULT)
            out.append(PointTarget("boss", i, float(b["x"]), float(b["y"]), 34.0, half_h))
        legacy = self.data.get("boss")
        if isinstance(legacy, dict):
            out.append(PointTarget("legacy_boss", 0, float(legacy["x"]), float(legacy["y"]),
                                   LEGACY_BOSS_SIZE[0] / 2.0, LEGACY_BOSS_SIZE[1] / 2.0))
        if "player_spawn" in self.data:
            sx, sy = self.player_spawn
            out.append(PointTarget("spawn", 0, sx, sy, 12.0, 28.0))
        return out

    def pick_rect(self, wx: float, wy: float) -> Selection | None:
        for target in reversed(self.rect_targets()):
            if target.x <= wx <= target.x + target.w and target.y <= wy <= target.y + target.h:
                return Selection(target.kind, target.index)
        return None

    def pick_point(self, wx: float, wy: float) -> Selection | None:
        best: tuple[float, Selection] | None = None
        for target in self.point_targets():
            if (abs(wx - target.x) <= target.half_w + POINT_PICK_PAD
                    and abs(wy - target.y) <= target.half_h + POINT_PICK_PAD):
                dist = abs(wx - target.x) + abs(wy - target.y)
                if best is None or dist < best[0]:
                    best = (dist, Selection(target.kind, target.index))
        return best[1] if best else None

    def pick(self, wx: float, wy: float) -> Selection | None:
        return self.pick_point(wx, wy) or self.pick_rect(wx, wy)

    def rect_of(self, sel: Selection) -> tuple[float, float, float, float] | None:
        if sel.kind == "platform" and 0 <= sel.index < len(self.platforms):
            p = self.platforms[sel.index]
            return (float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"]))
        key = {"trigger": "boss_trigger", "gate": "boss_gate"}.get(sel.kind)
        if key is not None and isinstance(self.data.get(key), dict):
            node = self.data[key]
            return (float(node["x"]), float(node["y"]), float(node["w"]), float(node["h"]))
        return None

    def point_of(self, sel: Selection) -> tuple[float, float] | None:
        if sel.kind == "enemy" and 0 <= sel.index < len(self.enemies):
            e = self.enemies[sel.index]
            return (float(e["x"]), float(e["y"]))
        if sel.kind == "checkpoint" and 0 <= sel.index < len(self.checkpoints):
            c = self.checkpoints[sel.index]
            return (float(c["x"]), float(c["y"]))
        if sel.kind == "boss" and 0 <= sel.index < len(self.bosses):
            b = self.bosses[sel.index]
            return (float(b["x"]), float(b["y"]))
        legacy = self.data.get("boss")
        if sel.kind == "legacy_boss" and isinstance(legacy, dict):
            return (float(legacy["x"]), float(legacy["y"]))
        if sel.kind == "spawn":
            return self.player_spawn
        return None

    # -- geometry edits ------------------------------------------------
    def set_rect(self, sel: Selection, x: float, y: float, w: float, h: float) -> None:
        node = None
        if sel.kind == "platform" and 0 <= sel.index < len(self.platforms):
            node = self.platforms[sel.index]
        elif sel.kind == "trigger":
            node = self.data.get("boss_trigger")
        elif sel.kind == "gate":
            node = self.data.get("boss_gate")
        if not isinstance(node, dict):
            return
        node.update(x=x, y=y, w=max(MIN_SIZE, w), h=max(MIN_SIZE, h))
        self.dirty = True

    def set_point(self, sel: Selection, x: float, y: float) -> None:
        if sel.kind == "enemy" and 0 <= sel.index < len(self.enemies):
            self.enemies[sel.index].update(x=x, y=y)
        elif sel.kind == "checkpoint" and 0 <= sel.index < len(self.checkpoints):
            self.checkpoints[sel.index].update(x=x, y=y)
        elif sel.kind == "boss" and 0 <= sel.index < len(self.bosses):
            self.bosses[sel.index].update(x=x, y=y)
        elif sel.kind == "legacy_boss" and isinstance(self.data.get("boss"), dict):
            self.data["boss"].update(x=x, y=y)
        elif sel.kind == "spawn":
            self.data["player_spawn"] = [x, y]
        else:
            return
        self.dirty = True

    def toggle_platform_flag(self, sel: Selection, flag: str) -> None:
        if sel.kind != "platform" or not (0 <= sel.index < len(self.platforms)):
            return
        p = self.platforms[sel.index]
        if flag == "organic":
            p["organic"] = not bool(p.get("organic", True))
        elif flag == "sharp":
            p["sharp"] = not bool(p.get("sharp", False))
            if not p["sharp"]:
                p.pop("sharp")
        self.dirty = True

    # -- objects -------------------------------------------------------
    def surface_top_at(self, wx: float, wy: float) -> float:
        """Top of the highest platform below (or at) the cursor, else the cursor."""
        best: float | None = None
        for p in self.platforms:
            x0, y0 = float(p["x"]), float(p["y"])
            if x0 <= wx <= x0 + float(p["w"]) and y0 >= wy - 60.0:
                if best is None or y0 < best:
                    best = y0
        return best if best is not None else wy

    def add_platform(self, wx: float, wy: float, w: float = 120.0, h: float = 40.0,
                     step: float = SNAP) -> Selection:
        self.platforms.append({"x": snap(wx, step), "y": snap(wy, step), "w": w, "h": h})
        self.dirty = True
        sel = Selection("platform", len(self.platforms) - 1)
        self.selection = sel
        return sel

    def add_enemy(self, type_: str, wx: float, wy: float, step: float = SNAP) -> Selection:
        feet = self.surface_top_at(wx, wy)
        self.enemies.append({
            "type": type_, "x": snap(wx, step),
            "y": feet - ENEMY_HALF_H[type_],
        })
        self.dirty = True
        sel = Selection("enemy", len(self.enemies) - 1)
        self.selection = sel
        return sel

    def add_checkpoint(self, wx: float, wy: float, step: float = SNAP) -> Selection:
        used = {c.get("name") for c in self.checkpoints}
        n = 1
        while f"cp_{n}" in used:
            n += 1
        self.checkpoints.append({
            "x": snap(wx, step), "y": snap(self.surface_top_at(wx, wy), step),
            "radius": 80, "name": f"cp_{n}",
        })
        self.dirty = True
        sel = Selection("checkpoint", len(self.checkpoints) - 1)
        self.selection = sel
        return sel

    def add_boss(self, kind: str, wx: float, wy: float, step: float = SNAP) -> Selection:
        legacy = self.data.get("boss")
        if isinstance(legacy, dict):
            # the level used the single-boss format: move it into the twins list
            self.data.pop("boss")
            moved = {"type": "boss", "x": legacy["x"], "y": legacy["y"]}
            self.bosses.insert(0, moved)
        feet = self.surface_top_at(wx, wy)
        self.bosses.append({
            "type": kind, "x": snap(wx, step),
            "y": feet - BOSS_HALF_H.get(kind, BOSS_HALF_H_DEFAULT),
        })
        self.dirty = True
        sel = Selection("boss", len(self.bosses) - 1)
        self.selection = sel
        return sel

    def set_trigger(self, wx: float, wy: float, step: float = SNAP) -> Selection:
        self.data["boss_trigger"] = {
            "x": snap(wx, step), "y": snap(wy - 110.0, step),
            "w": 120, "h": 220, "name": "arena",
        }
        self.dirty = True
        sel = Selection("trigger", 0)
        self.selection = sel
        return sel

    def set_gate(self, wx: float, wy: float, step: float = SNAP) -> Selection:
        self.data["boss_gate"] = {
            "x": snap(wx, step), "y": snap(wy - 150.0, step), "w": 36, "h": 300,
        }
        self.dirty = True
        sel = Selection("gate", 0)
        self.selection = sel
        return sel

    def set_spawn(self, wx: float, wy: float, step: float = SNAP) -> Selection:
        self.data["player_spawn"] = [snap(wx, step), snap(wy, step)]
        self.dirty = True
        sel = Selection("spawn", 0)
        self.selection = sel
        return sel

    def delete_selection(self) -> str:
        sel = self.selection
        if sel is None:
            return ""
        label = sel.kind
        if sel.kind == "platform" and 0 <= sel.index < len(self.platforms):
            self.platforms.pop(sel.index)
        elif sel.kind == "enemy" and 0 <= sel.index < len(self.enemies):
            self.enemies.pop(sel.index)
        elif sel.kind == "checkpoint" and 0 <= sel.index < len(self.checkpoints):
            self.checkpoints.pop(sel.index)
        elif sel.kind == "boss" and 0 <= sel.index < len(self.bosses):
            self.bosses.pop(sel.index)
        elif sel.kind == "legacy_boss":
            self.data.pop("boss", None)
        elif sel.kind == "trigger":
            self.data.pop("boss_trigger", None)
        elif sel.kind == "gate":
            self.data.pop("boss_gate", None)
        else:
            return ""
        self.selection = None
        self.dirty = True
        return f"удалено: {label}"

    def save(self) -> str:
        self.build_spec()  # raises on broken data; nothing is written then
        self.path.write_text(format_level(self.data), encoding="utf-8")
        self.dirty = False
        return f"сохранено: {self.path.name}"


# ------------------------------------------------------------------ camera

class EditorCamera:
    def __init__(self, bounds: tuple[float, float, float, float],
                 screen: tuple[int, int] = (SCREEN_W, SCREEN_H)) -> None:
        self.bounds = bounds
        self.screen_w, self.screen_h = screen
        self.center_x = bounds[0] + bounds[2] / 2.0
        self.center_y = bounds[1] + bounds[3] / 2.0
        self.clamp()

    def world_to_screen(self, x: float, y: float, z: float = 0.0) -> tuple[int, int]:
        return (int(round(x - self.center_x + self.screen_w / 2.0)),
                int(round(y - self.center_y + self.screen_h / 2.0)))

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return (sx - self.screen_w / 2.0 + self.center_x,
                sy - self.screen_h / 2.0 + self.center_y)

    def pan(self, dx: float, dy: float) -> None:
        self.center_x += dx
        self.center_y += dy
        self.clamp()

    def snap_to(self, x: float, y: float) -> None:
        self.center_x, self.center_y = x, y
        self.clamp()

    def clamp(self) -> None:
        left, top, width, height = self.bounds
        if width > self.screen_w:
            half = self.screen_w / 2.0
            self.center_x = max(left + half, min(left + width - half, self.center_x))
        else:
            self.center_x = left + width / 2.0
        if height > self.screen_h:
            half = self.screen_h / 2.0
            self.center_y = max(top + half, min(top + height - half, self.center_y))
        else:
            self.center_y = top + height / 2.0

    def parallax_offset(self, factor: float) -> int:
        return int(round(self.center_x * factor))

    def parallax_offset_y(self, factor: float) -> int:
        return int(round(self.center_y * factor))


# ------------------------------------------------------------------ pygame ui

def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.Font(None, size)
    except Exception:
        return pygame.font.SysFont(None, size)


def _bar(surface: pygame.Surface, text: str, font: pygame.font.Font,
         pos: tuple[int, int], color=COL_TEXT) -> None:
    img = font.render(text, True, color)
    pad = 6
    bg = pygame.Surface((img.get_width() + pad * 2, img.get_height() + pad), pygame.SRCALPHA)
    bg.fill((8, 10, 16, 190))
    surface.blit(bg, (pos[0] - pad, pos[1] - pad // 2))
    surface.blit(img, pos)


class LevelEditor:
    HELP = (
        "ЛКМ — выбрать/двигать · Shift+ЛКМ — платформа · ПКМ — удалить   "
        "1/2/3 — crawler/spitter/shard · 4 — чекпоинт · 5/6 — blade/prism · "
        "9 — keeper boss · 0 — orb   "
        "7 — trigger · 8 — gate · E — спавн игрока · N — organic · H — sharp   "
        "WASD/стрелки — камера · F2/Ctrl+S — сохранить · F5 — перезагрузить · Esc — выход"
    )

    def __init__(self, path: Path) -> None:
        pygame.init()  # fonts must exist before the HUD fonts are built
        self.path = path
        self.state = EditorState.load(path)
        self.cam = EditorCamera(self.state.bounds)
        self.cam.snap_to(*self.state.player_spawn)
        self.font = _font(18)
        self.big = _font(26)
        self.small = _font(16)
        set_theme(self.state.theme)  # palette must be live before baking
        self.background = Background(self.state.bounds, theme=self.state.theme,
                                     vertical=self.state.vertical)
        self.terrain = TerrainRenderer(self.state.platform_objects())
        self.message = ""
        self.message_timer = 0.0
        self.show_help = True
        self.drag: dict | None = None
        self.pan_last: tuple[int, int] | None = None
        self._last_bake = 0.0

    # -- helpers -------------------------------------------------------
    def _rebake(self) -> None:
        self.terrain = TerrainRenderer(self.state.platform_objects())
        self._last_bake = pygame.time.get_ticks() / 1000.0

    def _notify(self, text: str) -> None:
        self.message = text
        self.message_timer = 3.5

    def _mouse_world(self) -> tuple[float, float]:
        return self.cam.screen_to_world(*pygame.mouse.get_pos())

    def _step(self) -> float:
        return 0.0 if pygame.key.get_mods() & pygame.KMOD_CTRL else SNAP

    def _selected_handle(self, wx: float, wy: float) -> str | None:
        sel = self.state.selection
        if sel is None or sel.kind not in RECT_SELECTIONS:
            return None
        rect = self.state.rect_of(sel)
        if rect is None:
            return None
        for name, (hx, hy) in handle_positions(*rect).items():
            if abs(wx - hx) <= HANDLE_RADIUS and abs(wy - hy) <= HANDLE_RADIUS:
                return name
        return None

    # -- input ---------------------------------------------------------
    def _on_mouse_down(self, event, wx: float, wy: float) -> None:
        if event.button == 2:
            self.pan_last = pygame.mouse.get_pos()
            return
        if event.button == 3:
            sel = self.state.pick(wx, wy)
            if sel is not None:
                self.state.selection = sel
                self._notify(self.state.delete_selection() or "нечего удалять")
                self._rebake()
            return
        if event.button != 1:
            return

        handle = self._selected_handle(wx, wy)
        if handle is not None and self.state.selection is not None:
            self.drag = {"mode": "resize", "handle": handle, "sel": self.state.selection}
            return

        sel = self.state.pick(wx, wy)
        if sel is not None:
            self.state.selection = sel
            if sel.kind in RECT_SELECTIONS:
                rect = self.state.rect_of(sel)
                grab = (wx - rect[0], wy - rect[1]) if rect else (0.0, 0.0)
            else:
                point = self.state.point_of(sel) or (wx, wy)
                grab = (wx - point[0], wy - point[1])
            self.drag = {"mode": "move", "sel": sel, "grab": grab}
            return

        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
            self.state.add_platform(wx, wy)
            self._notify("платформа добавлена")
            self._rebake()
        else:
            self.state.selection = None

    def _on_mouse_motion(self, event) -> None:
        if self.pan_last is not None:
            dx = event.pos[0] - self.pan_last[0]
            dy = event.pos[1] - self.pan_last[1]
            self.cam.pan(-dx, -dy)
            self.pan_last = event.pos
            return
        if self.drag is None:
            return
        wx, wy = self._mouse_world()
        step = self._step()
        sel = self.drag["sel"]
        if self.drag["mode"] == "move":
            gx, gy = self.drag["grab"]
            nx, ny = snap(wx - gx, step), snap(wy - gy, step)
            if sel.kind in RECT_SELECTIONS:
                rect = self.state.rect_of(sel)
                if rect:
                    self.state.set_rect(sel, nx, ny, rect[2], rect[3])
            else:
                self.state.set_point(sel, nx, ny)
        else:
            rect = self.state.rect_of(sel)
            if rect:
                self.state.set_rect(sel, *resize_rect(
                    rect[0], rect[1], rect[2], rect[3], self.drag["handle"], wx, wy, step))

    def _on_mouse_up(self, event) -> None:
        if event.button == 2:
            self.pan_last = None
        elif event.button == 1 and self.drag is not None:
            self.drag = None
            self._rebake()

    def _on_key(self, event) -> bool:
        """Returns False to leave the editor."""
        pos = self._mouse_world()
        step = self._step()
        if event.key == pygame.K_ESCAPE:
            return False
        if event.key == pygame.K_F1:
            self.show_help = not self.show_help
        elif event.key == pygame.K_F5:
            self.state = EditorState.load(self.path)
            self.cam.bounds = self.state.bounds
            self.background = Background(self.state.bounds, theme=self.state.theme,
                                         vertical=self.state.vertical)
            self._rebake()
            self._notify("перезагружено с диска")
        elif event.key in (pygame.K_F2,) or (
                event.key == pygame.K_s and pygame.key.get_mods() & pygame.KMOD_CTRL):
            try:
                self._notify(self.state.save())
            except Exception as exc:  # noqa: BLE001 - show broken data instead of crashing
                self._notify(f"не сохранено: {exc}")
        elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            text = self.state.delete_selection()
            if text:
                self._notify(text)
                self._rebake()
        elif event.key == pygame.K_n:
            self.state.toggle_platform_flag(self.state.selection, "organic")
            self._rebake()
        elif event.key == pygame.K_h:
            self.state.toggle_platform_flag(self.state.selection, "sharp")
            self._rebake()
        elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
            kind = {pygame.K_1: "crawler", pygame.K_2: "spitter", pygame.K_3: "shard"}[event.key]
            self.state.add_enemy(kind, *pos, step=step)
        elif event.key == pygame.K_4:
            self.state.add_checkpoint(*pos, step=step)
        elif event.key == pygame.K_0:
            self.state.add_enemy("orb", *pos, step=step)
        elif event.key in (pygame.K_5, pygame.K_6):
            kind = "blade" if event.key == pygame.K_5 else "prism"
            self.state.add_boss(kind, *pos, step=step)
        elif event.key == pygame.K_9:
            self.state.add_boss("keeper", *pos, step=step)
        elif event.key == pygame.K_7:
            self.state.set_trigger(*pos, step=step)
        elif event.key == pygame.K_8:
            self.state.set_gate(*pos, step=step)
        elif event.key == pygame.K_e:
            self.state.set_spawn(*pos, step=step)
        return True

    # -- frame ---------------------------------------------------------
    def _draw_marker(self, screen, target: PointTarget) -> None:
        x, y = self.cam.world_to_screen(target.x, target.y)
        if target.kind == "enemy":
            enemy = self.state.enemies[target.index]
            color = COL_ENEMY.get(enemy.get("type", ""), COL_DIM)
            pygame.draw.ellipse(screen, color, (x - 13, y - 9, 26, 18), 2)
            label = str(enemy.get("type", "?"))
            _bar(screen, label, self.small, (x + 16, y - 8), color)
        elif target.kind == "checkpoint":
            pygame.draw.circle(screen, COL_CP, (x, y), 9, 2)
            _bar(screen, "CP", self.small, (x + 13, y - 8), COL_CP)
        elif target.kind in ("boss", "legacy_boss"):
            boss = (self.state.bosses[target.index] if target.kind == "boss"
                    else self.state.data.get("boss", {}))
            pygame.draw.rect(screen, COL_BOSS,
                             (x - int(target.half_w), y - int(target.half_h),
                              int(target.half_w * 2), int(target.half_h * 2)), 2)
            _bar(screen, str(boss.get("type", "boss")), self.small,
                 (x + 36, y - 10), COL_BOSS)
        elif target.kind == "spawn":
            pygame.draw.polygon(screen, (140, 240, 150),
                                [(x, y - 26), (x + 9, y - 10), (x - 9, y - 10)], 2)
            _bar(screen, "spawn", self.small, (x + 12, y - 10), (140, 240, 150))

    def _draw(self, screen) -> None:
        cam = self.cam
        to_screen = cam.world_to_screen
        screen.fill((10, 12, 18))

        self.background.draw(screen, cam)  # type: ignore[arg-type]

        # kill zones
        for zone in self.state.kill_zones:
            x, y = to_screen(zone["x"], zone["y"])
            rect = pygame.Rect(x, y, int(zone["w"]), int(zone["h"]))
            pygame.draw.rect(screen, (*COL_KILL, 40), rect)
            pygame.draw.rect(screen, COL_KILL, rect, 1)

        # grid every 100 px
        left, top, width, height = self.state.bounds
        x0 = int(left // 100) * 100
        while x0 <= left + width:
            sx, _ = to_screen(x0, 0)
            pygame.draw.line(screen, COL_GRID, (sx, 0), (sx, SCREEN_H), 1)
            x0 += 100
        y0 = int(top // 100) * 100
        while y0 <= top + height:
            _, sy = to_screen(0, y0)
            pygame.draw.line(screen, COL_GRID, (0, sy), (SCREEN_W, sy), 1)
            y0 += 100

        # terrain (hide the platform that is being dragged until release)
        skip: set[int] = set()
        sel = self.state.selection
        if self.drag is not None and self.drag["mode"] in ("move", "resize") \
                and sel is not None and sel.kind == "platform" and self.drag["sel"] == sel:
            skip.add(sel.index)
        self.terrain.draw(screen, self.state.platform_objects(), to_screen, skip=skip)

        # rect objects
        for target in self.state.rect_targets():
            if target.kind == "platform":
                continue
            color = COL_TRIGGER if target.kind == "trigger" else COL_GATE
            x, y = to_screen(target.x, target.y)
            rect = pygame.Rect(x, y, int(target.w), int(target.h))
            pygame.draw.rect(screen, color, rect, 2)
            _bar(screen, target.kind.upper(), self.small,
                 (x, y - 16), color)

        # point objects
        for target in self.state.point_targets():
            self._draw_marker(screen, target)

        # raw rect for the platform being dragged
        if skip and sel is not None:
            rect = self.state.rect_of(sel)
            if rect:
                x, y = to_screen(rect[0], rect[1])
                pygame.draw.rect(screen, COL_SELECT,
                                 (x, y, int(rect[2]), int(rect[3])), 2)

        # selection + handles
        if sel is not None:
            rect = self.state.rect_of(sel) if sel.kind in RECT_SELECTIONS else None
            if rect:
                x, y = to_screen(rect[0], rect[1])
                pygame.draw.rect(screen, COL_SELECT,
                                 (x, y, int(rect[2]), int(rect[3])), 2)
                for hx, hy in handle_positions(
                        float(x), float(y), rect[2], rect[3]).values():
                    pygame.draw.rect(screen, COL_HANDLE,
                                     (int(hx) - 4, int(hy) - 4, 8, 8))
            else:
                point = self.state.point_of(sel)
                if point:
                    px, py = to_screen(*point)
                    pygame.draw.circle(screen, COL_SELECT, (px, py), 22, 2)

        # HUD
        st = self.state
        status = (f"{st.path.name}   тема: {st.theme}   платформ: {len(st.platforms)}   "
                  f"врагов: {len(st.enemies)}   чекпоинтов: {len(st.checkpoints)}   "
                  f"боссов: {len(st.bosses) + (1 if 'boss' in st.data else 0)}")
        if st.dirty:
            status += "   *"
        _bar(screen, status, self.font, (14, 16))

        if sel is not None:
            info = f"выбрано: {sel.kind}"
            if sel.kind in RECT_SELECTIONS:
                rect = st.rect_of(sel)
                if rect:
                    info += (f"  x={int(rect[0])} y={int(rect[1])} "
                             f"w={int(rect[2])} h={int(rect[3])}")
                if sel.kind == "platform":
                    plat = st.platforms[sel.index]
                    info += ("  organic" if plat.get("organic", True) else "  glass")
                    if plat.get("sharp"):
                        info += " · sharp"
            _bar(screen, info, self.small, (14, 40), COL_SELECT)

        if self.show_help:
            _bar(screen, self.HELP, self.small, (14, SCREEN_H - 30), COL_DIM)

        mx, my = pygame.mouse.get_pos()
        wx, wy = cam.screen_to_world(mx, my)
        _bar(screen, f"x={int(wx)}  y={int(wy)}", self.small,
             (SCREEN_W - 150, SCREEN_H - 30), COL_DIM)

        if self.message and self.message_timer > 0.0:
            _bar(screen, self.message, self.font, (14, 68), (150, 240, 170))

    def run(self) -> int:
        pygame.init()
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption(f"Редактор — {self.state.name}")
        set_theme(self.state.theme)
        clock = pygame.time.Clock()
        running = True
        while running:
            dt = clock.tick(60) / 1000.0
            keys = pygame.key.get_pressed()
            pan_x = (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - \
                    (1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0)
            pan_y = (1 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0) - \
                    (1 if keys[pygame.K_w] or keys[pygame.K_UP] else 0)
            if pan_x or pan_y:
                self.cam.pan(pan_x * PAN_SPEED * dt, pan_y * PAN_SPEED * dt)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    running = self._on_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._on_mouse_down(event, *self._mouse_world())
                elif event.type == pygame.MOUSEMOTION:
                    self._on_mouse_motion(event)
                elif event.type == pygame.MOUSEBUTTONUP:
                    self._on_mouse_up(event)

            if self.message_timer > 0.0:
                self.message_timer -= dt
            self._draw(screen)
            pygame.display.flip()
        return 0


def run_editor(path: Path) -> int:
    return LevelEditor(Path(path)).run()
