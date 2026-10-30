"""Enemies: melee «crawler» and ranged «spitter», plus projectiles.

Both share the pattern: patrol -> aggro -> telegraph -> attack -> recover,
with a poise/stagger meter that player hits can fill.
"""

from __future__ import annotations

from dataclasses import dataclass

from slg.core.combat import Damageable, Poise
from slg.core.config import CrawlerConfig, Config, SpitterConfig
from slg.core.events import EventBus
from slg.core.physics import (
    aabb_overlap,
    apply_gravity,
    clamp_to_bounds,
    move_and_collide,
)
from slg.core.world import Entity, World


def _ground_ahead(entity: Entity, world: World, direction: int) -> bool:
    """Is there floor a bit ahead-below? Prevents patrolling off ledges."""
    probe_x = entity.x + direction * (entity.half_w + 6.0)
    probe_y = entity.bottom + 8.0
    return any(
        aabb_overlap(probe_x - 1.0, probe_y - 1.0, 2.0, 2.0,
                     p.left, p.top, p.width, p.height)
        for p in world.platforms
    )


@dataclass
class Projectile:
    x: float
    y: float
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    radius: float = 8.0
    damage: int = 10
    life: float = 4.0
    alive: bool = True
    from_player: bool = False

    def aabb(self) -> tuple[float, float, float, float]:
        r = self.radius
        return (self.x - r, self.y - r, r * 2.0, r * 2.0)


class Enemy:
    """Shared bones: hp, poise, taking hits, gravity, ledge-safe walking."""

    def __init__(self, entity: Entity, cfg: Config, bus: EventBus,
                 poise_max: float, poise_regen: float, stagger_time: float) -> None:
        self.entity = entity
        self.cfg = cfg
        self.bus = bus
        self.state = "patrol"
        self.state_timer = 0.0
        self.attack_cooldown = 0.0
        self.poise = Poise(poise_max, poise_regen, stagger_time)
        self.damageable = Damageable(entity)
        self.spawn_x = entity.x

    @property
    def staggered(self) -> bool:
        return self.poise.staggered

    def take_hit(self, damage: int, stagger_damage: float, knockback: float,
                 source: Entity | None = None) -> bool:
        if not self.entity.alive or self.damageable.invulnerable:
            return False
        if not self.damageable.try_take_hit(damage, knockback, source):
            return False
        self.bus.publish("entity_damaged", entity=self.entity, amount=damage, source=source)
        if not self.entity.alive:
            self.bus.publish("entity_died", entity=self.entity)
            return True
        if self.poise.take_stagger_damage(stagger_damage):
            self.state = "stagger"
            self.state_timer = 0.0
            self.bus.publish("telegraph", entity=self.entity, kind="stagger",
                             duration=self.poise.stagger_time)
        return True

    def _tick(self, dt: float) -> None:
        self.state_timer += dt
        self.poise.update(dt)
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)

    def _physics(self, dt: float, world: World) -> None:
        apply_gravity(self.entity, self.cfg.physics, dt)
        move_and_collide(self.entity, world, dt)
        clamp_to_bounds(self.entity, world)

    def _update_stagger(self, dt: float, world: World) -> None:
        self.entity.vx *= 0.86
        self._physics(dt, world)
        if not self.poise.staggered:
            self.state = "aggro"
            self.state_timer = 0.0


class Crawler(Enemy):
    """Melee: patrols, chases, telegraphs a lunge-bite, strikes, recovers."""

    def __init__(self, entity: Entity, cfg: Config, bus: EventBus) -> None:
        c: CrawlerConfig = cfg.crawler
        entity.hp = entity.max_hp = c.max_hp
        entity.width, entity.height = c.width, c.height
        entity.kind = "crawler"
        super().__init__(entity, cfg, bus, c.poise, c.poise_regen, c.stagger_time)
        self.c = c
        self._struck = False

    def update(self, dt: float, player, world: World) -> None:
        e = self.entity
        c = self.c
        self._tick(dt)

        if self.state == "stagger":
            self._update_stagger(dt, world)
            return
        if not player.entity.alive:
            self._patrol(dt, world)
            return

        px, py = player.entity.x, player.entity.y
        dist = abs(px - e.x)
        dy = abs(py - e.y)

        if self.state == "patrol":
            self._patrol(dt, world)
            if dist < c.aggro_range and dy < c.aggro_vertical:
                self.state = "aggro"
                self.state_timer = 0.0
        elif self.state == "aggro":
            e.facing = 1 if px >= e.x else -1
            if dist <= c.attack_range and self.attack_cooldown <= 0.0:
                self.state = "telegraph"
                self.state_timer = 0.0
                self.bus.publish("telegraph", entity=e, kind="crawler_bite",
                                 duration=c.telegraph)
            elif dist > c.attack_range * 0.7:
                if _ground_ahead(e, world, e.facing):
                    e.vx = e.facing * c.chase_speed
                else:
                    e.vx = 0.0
            else:
                e.vx *= 0.8
            self._physics(dt, world)
        elif self.state == "telegraph":
            e.vx *= 0.85
            e.facing = 1 if px >= e.x else -1
            self._physics(dt, world)
            if self.state_timer >= c.telegraph:
                self.state = "strike"
                self.state_timer = 0.0
                self._struck = False
        elif self.state == "strike":
            e.vx = e.facing * c.chase_speed * 1.4
            if not self._struck and self.state_timer >= c.strike_active * 0.5:
                self._struck = True
                self._try_bite(player)
            if self.state_timer >= c.strike_active:
                self.state = "recover"
                self.state_timer = 0.0
            self._physics(dt, world)
        elif self.state == "recover":
            e.vx *= 0.8
            self._physics(dt, world)
            if self.state_timer >= c.recover:
                self.state = "aggro"
                self.state_timer = 0.0
                self.attack_cooldown = 0.2

    def _try_bite(self, player) -> None:
        c = self.c
        e = self.entity
        left = e.x if e.facing == 1 else e.x - c.attack_range
        top = e.y - c.height * 0.7
        p_left, p_top, p_w, p_h = player.entity.aabb()
        if aabb_overlap(left, top, c.attack_range, c.height * 1.4, p_left, p_top, p_w, p_h):
            player.take_hit(c.damage, c.knockback, e)

    def _patrol(self, dt: float, world: World) -> None:
        e = self.entity
        c = self.c
        if not _ground_ahead(e, world, e.facing) or abs(e.x - self.spawn_x) >= c.patrol_range:
            e.facing *= -1
        if _ground_ahead(e, world, e.facing):
            e.vx = e.facing * c.patrol_speed
        else:
            e.vx = 0.0
        self._physics(dt, world)


class Spitter(Enemy):
    """Ranged: holds a band of distance, telegraphs, lobs a spore projectile."""

    def __init__(self, entity: Entity, cfg: Config, bus: EventBus) -> None:
        s: SpitterConfig = cfg.spitter
        entity.hp = entity.max_hp = s.max_hp
        entity.width, entity.height = s.width, s.height
        entity.kind = "spitter"
        super().__init__(entity, cfg, bus, s.poise, s.poise_regen, s.stagger_time)
        self.s = s

    def update(self, dt: float, player, world: World) -> None:
        e = self.entity
        s = self.s
        self._tick(dt)

        if self.state == "stagger":
            self._update_stagger(dt, world)
            return
        if not player.entity.alive:
            e.vx *= 0.85
            self._physics(dt, world)
            return

        px = player.entity.x
        dist = abs(px - e.x)
        e.facing = 1 if px >= e.x else -1

        if self.state == "patrol":
            e.vx *= 0.85
            self._physics(dt, world)
            if dist < s.aggro_range:
                self.state = "aggro"
                self.state_timer = 0.0
        elif self.state == "aggro":
            if dist < s.keep_min:
                e.vx = -e.facing * s.hop_speed
            elif dist > s.keep_max:
                if _ground_ahead(e, world, e.facing):
                    e.vx = e.facing * s.hop_speed * 0.7
                else:
                    e.vx = 0.0
            else:
                e.vx *= 0.8
                if self.attack_cooldown <= 0.0:
                    self.state = "telegraph"
                    self.state_timer = 0.0
                    self.bus.publish("telegraph", entity=e, kind="spitter_spit",
                                     duration=s.telegraph)
            self._physics(dt, world)
        elif self.state == "telegraph":
            e.vx *= 0.85
            self._physics(dt, world)
            if self.state_timer >= s.telegraph:
                self._spit(player)
                self.state = "recover"
                self.state_timer = 0.0
        elif self.state == "recover":
            e.vx *= 0.85
            self._physics(dt, world)
            if self.state_timer >= s.recover:
                self.state = "aggro"
                self.state_timer = 0.0
                self.attack_cooldown = 0.3

    def _spit(self, player) -> None:
        s = self.s
        e = self.entity
        target = player.entity
        dx = target.x - e.x
        t = max(0.25, abs(dx) / s.projectile_speed)
        vx = dx / t
        vy = s.projectile_arc + 0.5 * self.cfg.physics.gravity * t * 0.55
        self.bus.publish(
            "projectile_spawned",
            projectile=Projectile(
                x=e.x + e.facing * e.half_w, y=e.y - e.half_h * 0.4,
                vx=vx, vy=vy, radius=s.projectile_radius, damage=s.projectile_damage,
            ),
        )
