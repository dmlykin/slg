"""Session: headless orchestrator wiring player, enemies, boss, level, respawn.

main.py only feeds input intents in and reads state out (for render/audio).
All rules live here so pytest can drive the whole game without pygame.
"""

from __future__ import annotations

from dataclasses import dataclass

from slg.core.boss import Boss
from slg.core.combat import attack_hitbox_hits, publish_hit
from slg.core.config import Config
from slg.core.enemies import Crawler, Enemy, Projectile, Spitter
from slg.core.events import EventBus
from slg.core.level import LevelSpec
from slg.core.physics import aabb_overlap, in_kill_zone
from slg.core.player import InputIntents, Player
from slg.core.world import Entity, World

DEATH_RESPAWN_DELAY = 1.6


@dataclass
class Session:
    spec: LevelSpec
    cfg: Config = None  # type: ignore[assignment]
    bus: EventBus = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.cfg is None:
            self.cfg = Config()
        if self.bus is None:
            self.bus = EventBus()
        self.world = World(bus=self.bus)
        self.world.bounds = self.spec.bounds
        self.world.platforms = list(self.spec.platforms)
        self.world.kill_zones = list(self.spec.kill_zones)
        self.world.checkpoints = list(self.spec.checkpoints)

        self.player = Player(
            self.world.spawn(x=self.spec.player_spawn[0], y=self.spec.player_spawn[1]),
            self.cfg, self.bus,
        )
        self.enemies: list[Enemy] = []
        self.boss: Boss | None = None
        self.projectiles: list[Projectile] = []
        self._swing_hits: set[int] = set()

        self.current_checkpoint: tuple[float, float] = self.spec.player_spawn
        self.activated_checkpoints: set[str] = set()
        self.death_timer = 0.0
        self.victory = False
        self.boss_defeated = False
        self.boss_gate_active = False

        self.bus.subscribe("projectile_spawned", self._on_projectile_spawned)
        self._spawn_initial()

    # ------------------------------------------------------------------ spawning

    def _spawn_initial(self) -> None:
        self.enemies = []
        for s in self.spec.enemies:
            self._spawn_enemy(s.type, s.x, s.y)
        if self.spec.boss is not None and not self.boss_defeated:
            self.boss = Boss(
                self.world.spawn(x=self.spec.boss.x, y=self.spec.boss.y),
                self.cfg, self.bus,
            )

    def _spawn_enemy(self, type_: str, x: float, y: float) -> None:
        entity = self.world.spawn(x=x, y=y)
        if type_ == "crawler":
            self.enemies.append(Crawler(entity, self.cfg, self.bus))
        elif type_ == "spitter":
            self.enemies.append(Spitter(entity, self.cfg, self.bus))
        else:
            raise ValueError(f"unknown enemy type: {type_}")

    def _on_projectile_spawned(self, projectile: Projectile) -> None:
        self.projectiles.append(projectile)

    def _publish_projectile(self, projectile: Projectile) -> None:
        self.bus.publish("projectile_spawned", projectile=projectile)

    # ------------------------------------------------------------------ respawn

    def respawn_everything(self) -> None:
        """Respawn player at checkpoint with full resources; revive enemies."""
        for enemy in self.enemies:
            self.world.despawn(enemy.entity)
        if self.boss is not None and not self.boss_defeated:
            self.world.despawn(self.boss.entity)
        self.projectiles.clear()
        self._spawn_initial()
        x, y = self.current_checkpoint
        self.player.respawn_at(x, y)
        self._set_boss_gate(False)
        self.death_timer = 0.0
        self.bus.publish("respawn")

    def _set_boss_gate(self, closed: bool) -> None:
        gate = self.spec.boss_gate
        if gate is None:
            return
        if closed and not self.boss_gate_active:
            self.world.platforms.append(gate)
            self.boss_gate_active = True
        elif not closed and self.boss_gate_active:
            if gate in self.world.platforms:
                self.world.platforms.remove(gate)
            self.boss_gate_active = False

    # ------------------------------------------------------------------ update

    def update(self, dt: float, intents: InputIntents) -> None:
        if self.victory:
            return
        self.world.step_time(dt)

        # death sequencing: fade delay handled by render via death_timer
        if self.player.state == "dead":
            self.death_timer += dt
            if self.death_timer >= DEATH_RESPAWN_DELAY:
                self.respawn_everything()
            self._update_projectiles(dt)
            return

        self._check_checkpoint(intents)
        self._check_boss_trigger()

        self.player.update(dt, intents, self.world)

        for enemy in list(self.enemies):
            if enemy.entity.alive:
                enemy.update(dt, self.player, self.world)
                if enemy.entity.y > self.world.bounds[1] + self.world.bounds[3]:
                    enemy.entity.alive = False
        if self.boss is not None and self.boss.entity.alive:
            self.boss.update(dt, self.player, self.world, self._publish_projectile)

        self._resolve_player_attacks()
        self._update_projectiles(dt)
        self._check_kill_zones()

        if self.boss is not None and not self.boss.entity.alive and not self.boss_defeated:
            self.boss_defeated = True
            self._set_boss_gate(False)
            self.victory = True
            self.bus.publish("victory")

    # ------------------------------------------------------------------ subsystems

    def _check_checkpoint(self, intents: InputIntents) -> None:
        if not intents.interact_pressed:
            return
        e = self.player.entity
        for cp in self.spec.checkpoints:
            if cp.name in self.activated_checkpoints:
                continue
            if abs(e.x - cp.x) <= cp.radius and abs(e.y - cp.y) <= cp.radius + 40.0:
                self.activated_checkpoints.add(cp.name)
                self.current_checkpoint = (cp.x, cp.y - 40.0)
                self.player.entity.hp = self.player.entity.max_hp
                self.player.heal_charges = self.cfg.player.heal_charges
                self.player.stamina.value = self.player.stamina.max
                self.bus.publish("checkpoint", checkpoint=cp)
                return

    def _check_boss_trigger(self) -> None:
        if self.boss is None or self.boss_defeated or self.boss.state != "dormant":
            return
        trig = self.spec.boss_trigger
        if trig is None:
            return
        e = self.player.entity
        if aabb_overlap(e.left, e.top, e.width, e.height,
                        trig.x, trig.y, trig.width, trig.height):
            self.boss.activate()
            self._set_boss_gate(True)

    def _resolve_player_attacks(self) -> None:
        attack = self.player.attack
        if attack.phase != "active" or attack.attack is None:
            self._swing_hits.clear()
            return
        a = attack.attack
        targets: list[tuple[Entity, object]] = [
            (en.entity, en) for en in self.enemies if en.entity.alive
        ]
        if self.boss is not None and self.boss.entity.alive and self.boss.state != "dormant":
            targets.append((self.boss.entity, self.boss))
        for entity, controller in targets:
            if entity.id in self._swing_hits:
                continue
            if attack_hitbox_hits(self.player.entity, attack, entity):
                self._swing_hits.add(entity.id)
                landed = controller.take_hit(a.damage, a.stagger_damage, a.knockback,
                                             self.player.entity)
                if landed:
                    publish_hit(self.bus, self.player.entity, entity, a)

    def _update_projectiles(self, dt: float) -> None:
        cfg = self.cfg.physics
        for p in list(self.projectiles):
            p.vy += cfg.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.life -= dt
            if p.life <= 0:
                p.alive = False
                self.projectiles.remove(p)
                continue
            # platform hit
            pl_l, pl_t, pl_w, pl_h = p.aabb()
            if any(aabb_overlap(pl_l, pl_t, pl_w, pl_h, pl.left, pl.top, pl.width, pl.height)
                   for pl in self.world.platforms):
                p.alive = False
                self.projectiles.remove(p)
                continue
            # player hit
            if self.player.entity.alive and self.player.state != "dead":
                e = self.player.entity
                if aabb_overlap(pl_l, pl_t, pl_w, pl_h, e.left, e.top, e.width, e.height):
                    if self.player.take_hit(p.damage, 120.0, None):
                        p.alive = False
                        self.projectiles.remove(p)

    def _check_kill_zones(self) -> None:
        e = self.player.entity
        if e.alive and in_kill_zone(e, self.world.kill_zones):
            self.player.take_hit(10_000, 0.0, None)
