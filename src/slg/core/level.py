"""Level layout: JSON data -> platforms, spawns, checkpoints, boss arena trigger."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from slg.core.world import Checkpoint, FaceSpawn, Figure, KillZone, Platform, Portal, Trigger


@dataclass(frozen=True)
class EnemySpawn:
    type: str          # "crawler" | "spitter" | "shard"
    x: float
    y: float


@dataclass(frozen=True)
class BossSpawn:
    x: float
    y: float
    type: str = "boss"   # "boss" | "blade" | "prism" | "keeper"


def _rect(d: dict) -> dict:
    """Normalize w/h <-> width/height keys in rect-ish JSON nodes."""
    out = dict(d)
    if "w" in out:
        out["width"] = out.pop("w")
    if "h" in out:
        out["height"] = out.pop("h")
    return out


@dataclass
class LevelSpec:
    name: str
    bounds: tuple[float, float, float, float]
    player_spawn: tuple[float, float]
    theme: str = "swamp"
    vertical: bool = False
    platforms: list[Platform] = field(default_factory=list)
    kill_zones: list[KillZone] = field(default_factory=list)
    checkpoints: list[Checkpoint] = field(default_factory=list)
    enemies: list[EnemySpawn] = field(default_factory=list)
    boss: BossSpawn | None = None
    bosses: list[BossSpawn] = field(default_factory=list)
    boss_trigger: Trigger | None = None
    boss_gate: Platform | None = None
    portals: list[Portal] = field(default_factory=list)
    figure: Figure | None = None

    @staticmethod
    def from_dict(data: dict) -> LevelSpec:
        bounds = tuple(data.get("bounds", (0.0, -600.0, 4200.0, 1600.0)))
        return LevelSpec(
            name=data.get("name", "unnamed"),
            bounds=(bounds[0], bounds[1], bounds[2], bounds[3]),
            player_spawn=tuple(data["player_spawn"]),
            theme=data.get("theme", "swamp"),
            vertical=bool(data.get("vertical", False)),
            platforms=[
                Platform(**_rect(p)) for p in data.get("platforms", [])
            ],
            kill_zones=[
                KillZone(**_rect(z)) for z in data.get("kill_zones", [])
            ],
            checkpoints=[
                Checkpoint(c["x"], c["y"], c.get("radius", 70.0), c.get("name", "checkpoint"))
                for c in data.get("checkpoints", [])
            ],
            enemies=[
                EnemySpawn(e["type"], e["x"], e["y"])
                for e in data.get("enemies", [])
            ],
            boss=BossSpawn(**data["boss"]) if "boss" in data else None,
            bosses=[BossSpawn(**b) for b in data.get("bosses", [])],
            boss_trigger=Trigger(**_rect(data["boss_trigger"])) if "boss_trigger" in data else None,
            boss_gate=Platform(**_rect(data["boss_gate"])) if "boss_gate" in data else None,
            portals=[
                Portal(p["x"], p["y"], p.get("radius", 70.0),
                       p.get("name", "portal"), p.get("target", "hub"))
                for p in data.get("portals", [])
            ],
            figure=Figure(
                data["figure"]["x"], data["figure"]["y"],
                [
                    FaceSpawn(f["type"], f["x"], f["y"], f["target"], f.get("requires"))
                    for f in data["figure"].get("faces", [])
                ],
            ) if "figure" in data else None,
        )

    @staticmethod
    def load(path: str | Path) -> LevelSpec:
        with open(path, encoding="utf-8") as f:
            return LevelSpec.from_dict(json.load(f))
