"""World and entities.

Coordinates: x, y are the CENTER of the entity's AABB; z is kept for the future
top-down projection (world plane x/z, side view ignores z). z is always 0 in the
MVP but every entity carries it so the core never needs changes later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from slg.core.events import EventBus


@dataclass
class Entity:
    id: int
    x: float
    y: float
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    width: float = 24.0
    height: float = 24.0
    facing: int = 1          # 1 = right, -1 = left
    hp: int = 1
    max_hp: int = 1
    alive: bool = True
    on_ground: bool = False
    kind: str = "entity"

    @property
    def half_w(self) -> float:
        return self.width / 2.0

    @property
    def half_h(self) -> float:
        return self.height / 2.0

    @property
    def left(self) -> float:
        return self.x - self.half_w

    @property
    def right(self) -> float:
        return self.x + self.half_w

    @property
    def top(self) -> float:
        return self.y - self.half_h

    @property
    def bottom(self) -> float:
        return self.y + self.half_h

    def aabb(self) -> tuple[float, float, float, float]:
        """(left, top, width, height)"""
        return (self.left, self.top, self.width, self.height)

    def distance_to(self, other: "Entity") -> float:
        return abs(self.x - other.x)


@dataclass(frozen=True)
class Platform:
    """Solid AABB obstacle. x, y = top-left corner."""

    x: float
    y: float
    width: float
    height: float
    organic: bool = True

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class KillZone:
    """Falling here kills the player (abyss)."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class Checkpoint:
    x: float
    y: float
    radius: float = 70.0
    name: str = "checkpoint"


@dataclass(frozen=True)
class Trigger:
    x: float
    y: float
    width: float
    height: float
    name: str = "trigger"


@dataclass
class World:
    """Container of everything simulated. Render reads it, never writes."""

    bus: EventBus = field(default_factory=EventBus)
    entities: list[Entity] = field(default_factory=list)
    platforms: list[Platform] = field(default_factory=list)
    kill_zones: list[KillZone] = field(default_factory=list)
    checkpoints: list[Checkpoint] = field(default_factory=list)
    time: float = 0.0
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 4000.0, 720.0)
    _next_id: int = 1

    def spawn(self, entity: Entity | None = None, **kwargs) -> Entity:
        if entity is None:
            entity = Entity(id=self._next_id, **kwargs)
        else:
            entity.id = self._next_id
        self._next_id += 1
        self.entities.append(entity)
        return entity

    def despawn(self, entity: Entity) -> None:
        if entity in self.entities:
            self.entities.remove(entity)

    def by_kind(self, kind: str) -> list[Entity]:
        return [e for e in self.entities if e.kind == kind and e.alive]

    def step_time(self, dt: float) -> None:
        self.time += dt
