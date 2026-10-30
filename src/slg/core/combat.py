"""Combat: stamina, attack phases, hitboxes, i-frames, stagger/poise, damage.

All timings come from Config; nothing is hardcoded here.
"""

from __future__ import annotations

from dataclasses import dataclass

from slg.core.config import AttackConfig
from slg.core.events import EventBus
from slg.core.world import Entity
from slg.core.physics import aabb_overlap


@dataclass
class Stamina:
    value: float
    max: float
    regen: float
    regen_delay: float
    _delay_timer: float = 0.0

    def spend(self, amount: float) -> bool:
        if self.value < amount:
            return False
        self.value -= amount
        self._delay_timer = self.regen_delay
        return True

    def update(self, dt: float) -> None:
        if self._delay_timer > 0.0:
            self._delay_timer -= dt
            return
        self.value = min(self.max, self.value + self.regen * dt)


@dataclass
class AttackState:
    """Tracks progression through windup -> active -> recovery."""

    attack: AttackConfig | None = None
    timer: float = 0.0
    phase: str = "idle"          # idle | windup | active | recovery
    has_hit: bool = False

    def start(self, attack: AttackConfig) -> None:
        self.attack = attack
        self.timer = 0.0
        self.phase = "windup"
        self.has_hit = False

    @property
    def busy(self) -> bool:
        return self.phase != "idle"

    def update(self, dt: float) -> None:
        if self.phase == "idle" or self.attack is None:
            return
        self.timer += dt
        a = self.attack
        if self.phase == "windup" and self.timer >= a.windup:
            self.phase = "active"
            self.timer = 0.0
        elif self.phase == "active" and self.timer >= a.active:
            self.phase = "recovery"
            self.timer = 0.0
        elif self.phase == "recovery" and self.timer >= a.recovery:
            self.phase = "idle"
            self.timer = 0.0
            self.attack = None

    def hitbox(self, owner: Entity) -> tuple[float, float, float, float] | None:
        """(left, top, w, h) in front of the owner, or None when not active."""
        if self.phase != "active" or self.attack is None:
            return None
        a = self.attack
        left = owner.x if owner.facing == 1 else owner.x - a.reach
        top = owner.y - a.height / 2.0
        return (left, top, a.reach, a.height)


@dataclass
class Poise:
    """Stagger meter: taking stagger damage fills it; full -> staggered."""

    max: float
    regen: float
    stagger_time: float
    _value: float = 0.0
    staggered_timer: float = 0.0

    @property
    def staggered(self) -> bool:
        return self.staggered_timer > 0.0

    def take_stagger_damage(self, amount: float) -> bool:
        """Returns True if this hit caused a stagger."""
        if self.staggered:
            return False
        self._value += amount
        if self._value >= self.max:
            self._value = 0.0
            self.staggered_timer = self.stagger_time
            return True
        return False

    def update(self, dt: float) -> None:
        if self.staggered_timer > 0.0:
            self.staggered_timer -= dt
        else:
            self._value = max(0.0, self._value - self.regen * dt)


def attack_hitbox_hits(attacker: Entity, attack: AttackState, target: Entity) -> bool:
    box = attack.hitbox(attacker)
    if box is None:
        return False
    left, top, w, h = box
    t_left, t_top, t_w, t_h = target.aabb()
    return aabb_overlap(left, top, w, h, t_left, t_top, t_w, t_h)


@dataclass
class Damageable:
    """HP + i-frame bookkeeping shared by player and enemies."""

    entity: Entity
    iframes_timer: float = 0.0

    @property
    def invulnerable(self) -> bool:
        return self.iframes_timer > 0.0

    def grant_iframes(self, seconds: float) -> None:
        self.iframes_timer = max(self.iframes_timer, seconds)

    def update(self, dt: float) -> None:
        if self.iframes_timer > 0.0:
            self.iframes_timer -= dt

    def try_take_hit(self, damage: int, knockback: float, source: Entity | None = None) -> bool:
        """Apply damage unless invulnerable. Returns True if damage landed."""
        if self.invulnerable or not self.entity.alive:
            return False
        self.entity.hp -= damage
        if source is not None:
            direction = 1 if source.x <= self.entity.x else -1
            self.entity.vx = direction * knockback
        if self.entity.hp <= 0:
            self.entity.hp = 0
            self.entity.alive = False
        return True


def publish_hit(bus: EventBus, attacker: Entity, victim: Entity, attack: AttackConfig) -> None:
    bus.publish(
        "attack_hit",
        attacker=attacker, victim=victim,
        x=(attacker.x + victim.x) / 2.0, y=victim.y,
        damage=attack.damage, heavy=(attack.name == "heavy"),
    )
    bus.publish("entity_damaged", entity=victim, amount=attack.damage, source=attacker)
    if not victim.alive:
        bus.publish("entity_died", entity=victim)
