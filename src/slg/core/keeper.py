"""Blind keeper of the well: it hears the player and strikes the last heard spot.

Reuses the base Boss HP/poise/phase/physics loop, but replaces targeting and the
pattern set with hearing-driven attacks:

* ``lantern_slam`` — a delayed circle strike around the heard point;
* ``echo_wave`` — a ground ring that races away from the keeper;
* ``call_orbs`` — falling ball lightning that leaves short electric zones.

Hazards belong to the boss, not the Session: respawning recreates the boss and
the arena is clean again.
"""

from __future__ import annotations

from dataclasses import dataclass

from slg.core.boss import Boss
from slg.core.config import Config, KeeperConfig
from slg.core.events import EventBus
from slg.core.world import Entity, World


@dataclass
class OrbDrop:
    """A lightning bolt falling from above onto the arena floor."""

    x: float
    y: float
    vy: float
    target_y: float


@dataclass
class ShockZone:
    """Short-lived electric pool left where a falling orb hit the floor."""

    x: float
    y: float
    radius: float
    life: float
    max_life: float
    cooldown: float = 0.0


class KeeperBoss(Boss):
    def __init__(self, entity: Entity, cfg: Config, bus: EventBus,
                 boss_cfg: KeeperConfig | None = None, kind: str = "keeper") -> None:
        super().__init__(entity, cfg, bus, boss_cfg or cfg.keeper, kind)
        self.b: KeeperConfig = self.b  # type: ignore[assignment]
        self.target_pos = entity.x
        self.attack_target = entity.x
        self.silent = False
        self.drop_targets: list[float] = []
        self.orb_drops: list[OrbDrop] = []
        self.shock_zones: list[ShockZone] = []
        self.echo_radius = 0.0
        self.echo_hit = False
        self._orbs_spawned = False
        self._pattern_cycle = 0
        self._silent_cycle = 0

    # ------------------------------------------------------------------ damage

    def take_hit(self, damage: int, stagger_damage: float, knockback: float,
                 source: Entity | None = None) -> bool:
        landed = super().take_hit(damage, stagger_damage, knockback, source)
        if self.state == "dead":
            self._clear_hazards()
        return landed

    # ------------------------------------------------------------------ hearing

    def _sense_target(self, player) -> float:
        if self.state in ("telegraph", "active"):
            # keep the target fixed: the player must be able to walk away from the noise
            return self.attack_target
        if player.entity.alive and player.noise_timer <= (
            self.b.hearing_memory * player.hearing_mult
        ):
            self.silent = False
            self.target_pos = player.last_noise_pos[0]
        else:
            self.silent = True
        return self.target_pos

    # ------------------------------------------------------------------ patterns

    def _reset_pattern(self) -> None:
        self._struck = False
        self._volley_fired = 0
        self._orbs_spawned = False
        self.echo_radius = 0.0
        self.echo_hit = False
        self.drop_targets = []

    def _pick_pattern(self, dist: float) -> str:
        b = self.b
        self._reset_pattern()
        self.attack_target = self.target_pos
        if self.silent:
            self._silent_cycle += 1
            pattern = "echo_wave" if self._silent_cycle % 2 == 1 else "call_orbs"
        elif dist > b.slam_range * 1.5:
            pattern = "call_orbs"
        else:
            self._pattern_cycle += 1
            pattern = ("lantern_slam", "echo_wave", "call_orbs")[
                (self._pattern_cycle - 1) % 3
            ]
        if pattern == "call_orbs":
            self.drop_targets = self._make_drop_targets()
        return pattern

    def _pattern_telegraph(self) -> float:
        b = self.b
        m = self._telegraph_mult()
        if self.pattern == "lantern_slam":
            return b.slam_telegraph * m
        if self.pattern == "echo_wave":
            return b.sweep_telegraph * m
        return b.volley_telegraph * m

    def _pattern_recover(self) -> float:
        b = self.b
        if self.pattern == "lantern_slam":
            return b.slam_recover
        if self.pattern == "echo_wave":
            return b.sweep_recover
        return b.volley_recover

    # ------------------------------------------------------------------ update

    def update(self, dt: float, player, world: World, spawn_projectile) -> None:
        if self.state == "dead" or not self.entity.alive:
            self._clear_hazards()
        else:
            self._update_hazards(dt, player, world)
        super().update(dt, player, world, spawn_projectile)

    def _update_active(self, dt: float, player, world: World, spawn_projectile) -> None:
        e = self.entity
        b = self.b
        if self.pattern == "lantern_slam":
            e.vx *= 0.8
            if not self._struck and self.state_timer >= b.slam_active * 0.4:
                self._struck = True
                self._slam_hit(player)
            if self.state_timer >= b.slam_active:
                self._to_recover()
        elif self.pattern == "echo_wave":
            e.vx *= 0.8
            self._update_echo(dt, player)
        elif self.pattern == "call_orbs":
            e.vx = 0.0
            if not self._orbs_spawned:
                self._orbs_spawned = True
                self._spawn_drops(world)
            if not self.orb_drops:
                self._to_recover()
        self._physics(dt, world)

    def _to_recover(self) -> None:
        self.state = "recover"
        self.state_timer = 0.0

    def _slam_hit(self, player) -> None:
        e = player.entity
        if not e.alive or player.state == "dead" or not e.on_ground:
            return
        if abs(e.x - self.attack_target) <= self.b.slam_range:
            player.take_hit(self._mirror_damage(self.b.slam_damage), 360.0,
                            self.entity)

    def _update_echo(self, dt: float, player) -> None:
        b = self.b
        self.echo_radius += b.echo_speed * dt
        if not self.echo_hit:
            e = player.entity
            if (e.alive and player.state != "dead" and e.on_ground
                    and abs(abs(e.x - self.entity.x) - self.echo_radius) <= b.echo_thickness
                    and player.take_hit(self._mirror_damage(b.sweep_damage), 320.0,
                                         self.entity)):
                self.echo_hit = True
        if self.echo_radius >= b.sweep_range:
            self._to_recover()

    # ------------------------------------------------------------------ orbs

    @staticmethod
    def _floor_top(world: World) -> float:
        tops = [p.top for p in world.platforms]
        return max(tops) if tops else 0.0

    def _make_drop_targets(self) -> list[float]:
        b = self.b
        count = b.volley_count + (1 if self.phase == 2 else 0)
        if count <= 1:
            return [self.attack_target]
        step = (b.orb_spread * 2.0) / (count - 1)
        return [self.attack_target - b.orb_spread + i * step for i in range(count)]

    def _spawn_drops(self, world: World) -> None:
        b = self.b
        floor = self._floor_top(world)
        left, _top, width, _height = world.bounds
        fall_speed = b.orb_fall_height / max(0.001, b.orb_fall_time)
        for target in self.drop_targets:
            x = max(left + b.orb_zone_radius, min(left + width - b.orb_zone_radius, target))
            self.orb_drops.append(OrbDrop(
                x=x,
                y=floor - b.orb_fall_height,
                vy=fall_speed,
                target_y=floor,
            ))

    def _update_hazards(self, dt: float, player, world: World) -> None:
        b = self.b
        for drop in list(self.orb_drops):
            drop.y += drop.vy * dt
            if drop.y < drop.target_y:
                continue
            self.orb_drops.remove(drop)
            self.shock_zones.append(ShockZone(
                x=drop.x, y=drop.target_y, radius=b.orb_zone_radius,
                life=b.orb_zone_life, max_life=b.orb_zone_life,
            ))
            self.bus.publish("orb_shattered", x=drop.x, y=drop.target_y)

        for zone in list(self.shock_zones):
            zone.life -= dt
            zone.cooldown = max(0.0, zone.cooldown - dt)
            if zone.life <= 0.0:
                self.shock_zones.remove(zone)
                continue
            if (zone.cooldown <= 0.0 and self._zone_hits(player, zone)
                    and player.take_hit(self._mirror_damage(b.volley_damage),
                                        260.0, self.entity)):
                zone.cooldown = b.zone_hit_cooldown

    @staticmethod
    def _zone_hits(player, zone: ShockZone) -> bool:
        e = player.entity
        if not e.alive or player.state == "dead":
            return False
        if abs(e.x - zone.x) > zone.radius:
            return False
        return e.on_ground and abs(e.bottom - zone.y) <= 40.0

    def _clear_hazards(self) -> None:
        self.orb_drops.clear()
        self.shock_zones.clear()
        self.echo_radius = 0.0
