"""Boss of the dying world: slam / sweep / volley patterns, phase 2 at 50% HP."""

from __future__ import annotations

import random

from slg.core.combat import Damageable, Poise
from slg.core.config import BossConfig, Config
from slg.core.events import EventBus
from slg.core.physics import (
    aabb_overlap,
    apply_gravity,
    clamp_to_bounds,
    move_and_collide,
)
from slg.core.world import Entity, World


class Boss:
    def __init__(self, entity: Entity, cfg: Config, bus: EventBus) -> None:
        b: BossConfig = cfg.boss
        entity.hp = entity.max_hp = b.max_hp
        entity.width, entity.height = b.width, b.height
        entity.kind = "boss"
        self.entity = entity
        self.cfg = cfg
        self.bus = bus
        self.b = b
        self.poise = Poise(b.poise, b.poise_regen, b.stagger_time)
        self.damageable = Damageable(entity)
        self.active = False          # wakes when the player enters the arena
        self.state = "dormant"       # dormant|idle|telegraph|active|recover|stagger|roar|dead
        self.state_timer = 0.0
        self.pattern: str | None = None
        self.phase = 1
        self._struck = False
        self._volley_fired = 0
        self._rng = random.Random()

    # ------------------------------------------------------------------ damage

    def take_hit(self, damage: int, stagger_damage: float, knockback: float,
                 source: Entity | None = None) -> bool:
        if not self.entity.alive or self.state == "dormant":
            return False
        # boss doesn't flinch from knockback
        if not self.damageable.try_take_hit(damage, 0.0, source):
            return False
        self.bus.publish("entity_damaged", entity=self.entity, amount=damage, source=source)
        if not self.entity.alive:
            self.state = "dead"
            self.bus.publish("entity_died", entity=self.entity)
            return True
        # phase transition
        if self.phase == 1 and self.entity.hp <= self.entity.max_hp * self.b.phase2_at:
            self.phase = 2
            self.state = "roar"
            self.state_timer = 0.0
            self.bus.publish("boss_phase", phase=2)
            return True
        if self.poise.take_stagger_damage(stagger_damage):
            self.state = "stagger"
            self.state_timer = 0.0
        return True

    def activate(self) -> None:
        if self.state == "dormant":
            self.active = True
            self.state = "roar"
            self.state_timer = 0.0
            self.bus.publish("boss_activated")

    # ------------------------------------------------------------------ helpers

    def _telegraph_mult(self) -> float:
        return self.b.phase2_telegraph_mult if self.phase == 2 else 1.0

    def _speed_mult(self) -> float:
        return self.b.phase2_speed_mult if self.phase == 2 else 1.0

    def _pick_pattern(self, dist: float) -> str:
        b = self.b
        if dist > b.sweep_range:
            return "volley"
        if dist < b.slam_range * 0.6:
            return self._rng.choice(("slam", "sweep"))
        return self._rng.choice(("sweep", "volley", "slam"))

    def _try_hit_player(self, player, left: float, top: float, w: float, h: float,
                        damage: int, knockback: float) -> None:
        p_left, p_top, p_w, p_h = player.entity.aabb()
        if aabb_overlap(left, top, w, h, p_left, p_top, p_w, p_h):
            player.take_hit(damage, knockback, self.entity)

    # ------------------------------------------------------------------ update

    def update(self, dt: float, player, world: World, spawn_projectile) -> None:
        e = self.entity
        b = self.b
        self.state_timer += dt
        self.poise.update(dt)

        if self.state in ("dormant", "dead"):
            e.vx = 0.0
            self._physics(dt, world)
            return

        if not player.entity.alive:
            e.vx = 0.0
            self._physics(dt, world)
            return

        px = player.entity.x
        dist = abs(px - e.x)
        e.facing = 1 if px >= e.x else -1

        if self.state == "roar":
            e.vx = 0.0
            self._physics(dt, world)
            if self.state_timer >= 1.1:
                self.state = "idle"
                self.state_timer = 0.0
        elif self.state == "stagger":
            e.vx *= 0.86
            self._physics(dt, world)
            if not self.poise.staggered:
                self.state = "idle"
                self.state_timer = 0.0
        elif self.state == "idle":
            # drift toward the player between patterns
            if dist > b.slam_range * 0.8:
                e.vx = e.facing * b.move_speed * self._speed_mult()
            else:
                e.vx *= 0.8
            self._physics(dt, world)
            if self.state_timer >= b.idle_between_patterns / self._speed_mult():
                self.pattern = self._pick_pattern(dist)
                self.state = "telegraph"
                self.state_timer = 0.0
                self._struck = False
                self._volley_fired = 0
                self.bus.publish("telegraph", entity=e, kind=f"boss_{self.pattern}",
                                 duration=self._pattern_telegraph())
        elif self.state == "telegraph":
            e.vx *= 0.8
            self._physics(dt, world)
            if self.state_timer >= self._pattern_telegraph():
                self.state = "active"
                self.state_timer = 0.0
        elif self.state == "active":
            self._update_active(dt, player, world, spawn_projectile)
        elif self.state == "recover":
            e.vx *= 0.85
            self._physics(dt, world)
            if self.state_timer >= self._pattern_recover():
                self.state = "idle"
                self.state_timer = 0.0

    def _pattern_telegraph(self) -> float:
        b = self.b
        m = self._telegraph_mult()
        if self.pattern == "slam":
            return b.slam_telegraph * m
        if self.pattern == "sweep":
            return b.sweep_telegraph * m
        return b.volley_telegraph * m

    def _pattern_recover(self) -> float:
        b = self.b
        if self.pattern == "slam":
            return b.slam_recover
        if self.pattern == "sweep":
            return b.sweep_recover
        return b.volley_recover

    def _update_active(self, dt: float, player, world: World, spawn_projectile) -> None:
        e = self.entity
        b = self.b
        if self.pattern == "slam":
            e.vx = e.facing * b.move_speed * 0.6
            if not self._struck and self.state_timer >= b.slam_active * 0.5:
                self._struck = True
                self._try_hit_player(
                    player,
                    e.x - b.slam_range, e.y - b.height * 0.8,
                    b.slam_range * 2.0, b.height * 1.1,
                    b.slam_damage, 420.0,
                )
            if self.state_timer >= b.slam_active:
                self.state = "recover"
                self.state_timer = 0.0
        elif self.pattern == "sweep":
            e.vx = e.facing * b.move_speed * 1.2
            if not self._struck and self.state_timer >= b.sweep_active * 0.5:
                self._struck = True
                left = e.x if e.facing == 1 else e.x - b.sweep_range
                self._try_hit_player(
                    player,
                    left, e.y - b.height * 0.7,
                    b.sweep_range, b.height * 1.0,
                    b.sweep_damage, 340.0,
                )
            if self.state_timer >= b.sweep_active:
                self.state = "recover"
                self.state_timer = 0.0
        elif self.pattern == "volley":
            e.vx = 0.0
            shots = b.volley_count + (2 if self.phase == 2 else 0)
            interval = 0.09
            if self._volley_fired < shots and self.state_timer >= self._volley_fired * interval:
                self._fire_volley_shot(player, spawn_projectile, self._volley_fired, shots)
                self._volley_fired += 1
            if self._volley_fired >= shots and self.state_timer >= shots * interval + 0.1:
                self.state = "recover"
                self.state_timer = 0.0
        self._physics(dt, world)

    def _fire_volley_shot(self, player, spawn_projectile, index: int, total: int) -> None:
        from slg.core.enemies import Projectile

        b = self.b
        e = self.entity
        target = player.entity
        dx = target.x - e.x
        dy = target.y - e.y
        base_t = max(0.3, abs(dx) / b.volley_projectile_speed)
        spread = ((index / max(1, total - 1)) - 0.5) * b.volley_spread if total > 1 else 0.0
        t = base_t * (1.0 + spread)
        vx = dx / t
        vy = dy / t - 0.5 * self.cfg.physics.gravity * t
        spawn_projectile(Projectile(
            x=e.x + e.facing * e.half_w * 0.6, y=e.y - e.half_h * 0.6,
            vx=vx, vy=vy, radius=10.0, damage=b.volley_damage,
        ))

    def _physics(self, dt: float, world: World) -> None:
        apply_gravity(self.entity, self.cfg.physics, dt)
        move_and_collide(self.entity, world, dt)
        clamp_to_bounds(self.entity, world)
