"""Session: headless orchestrator wiring player, enemies, boss, level, respawn.

main.py only feeds input intents in and reads state out (for render/audio).
All rules live here so pytest can drive the whole game without pygame.
"""

from __future__ import annotations

from dataclasses import dataclass

from slg.core.boss import Boss
from slg.core.combat import attack_hitbox_hits, publish_hit
from slg.core.config import Config
from slg.core.enemies import Crawler, Enemy, Orb, Projectile, Shard, Spitter
from slg.core.events import EventBus
from slg.core.keeper import KeeperBoss
from slg.core.level import BossSpawn, FaceSpawn, LevelSpec
from slg.core.physics import aabb_overlap, in_kill_zone, touching_sharp_side
from slg.core.player import InputIntents, Player
from slg.core.progress import Progress
from slg.core.world import Entity, World

DEATH_RESPAWN_DELAY = 1.6
SHARP_EDGE_DAMAGE = 14
SHARP_EDGE_KNOCKBACK = 210.0


def within_reach(ex: float, ey: float, x: float, y: float, radius: float) -> bool:
    """Shared proximity test for E-interactions (checkpoints, portals, faces)."""
    return abs(ex - x) <= radius and abs(ey - y) <= radius + 40.0


_BOSS_KINDS = {"boss", "blade", "prism", "keeper"}


@dataclass
class Session:
    spec: LevelSpec
    cfg: Config = None  # type: ignore[assignment]
    bus: EventBus = None  # type: ignore[assignment]
    progress: Progress | None = None

    def __post_init__(self) -> None:
        if self.cfg is None:
            self.cfg = Config()
        if self.bus is None:
            self.bus = EventBus()
        if self.progress is None:
            self.progress = Progress()
        self.world = World(bus=self.bus)
        self.world.bounds = self.spec.bounds
        self.world.platforms = list(self.spec.platforms)
        self.world.kill_zones = list(self.spec.kill_zones)
        self.world.checkpoints = list(self.spec.checkpoints)

        self.player = Player(
            self.world.spawn(x=self.spec.player_spawn[0], y=self.spec.player_spawn[1]),
            self.cfg, self.bus,
        )
        if self.progress.substance > 0:
            self.player.set_substance(self.progress.substance)
        self.enemies: list[Enemy] = []
        self.bosses: list[Boss] = []
        self.projectiles: list[Projectile] = []
        self._swing_hits: set[int] = set()

        self.current_checkpoint: tuple[float, float] = self.spec.player_spawn
        self.activated_checkpoints: set[str] = set()
        self.death_timer = 0.0
        self.victory = False
        self.boss_defeated = False
        self.boss_gate_active = False
        self.finale_dismissed = False
        self.relief_armed = False

        self.bus.subscribe("projectile_spawned", self._on_projectile_spawned)
        self.bus.subscribe("entity_died", self._on_entity_died)
        self._spawn_initial()

    @property
    def boss(self) -> Boss | None:
        """The first boss — keeps single-boss levels convenient."""
        return self.bosses[0] if self.bosses else None

    # ------------------------------------------------------------------ hub

    def face_state(self, face: FaceSpawn) -> str:
        """'available' when the face's requirement is met, else 'locked'."""
        if face.requires is None or self.progress.is_defeated(face.requires):
            return "available"
        return "locked"

    @property
    def hub_finale(self) -> bool:
        """True when every face's target level is defeated (demo finished)."""
        figure = self.spec.figure
        if figure is None or not figure.faces:
            return False
        return all(self.progress.is_defeated(f.target) for f in figure.faces)

    # ------------------------------------------------------------------ spawning

    def _boss_spawns(self) -> list[BossSpawn]:
        spawns = list(self.spec.bosses)
        if self.spec.boss is not None:
            spawns.append(self.spec.boss)
        return spawns

    def _boss_cfg(self, type_: str):
        return {
            "boss": None,
            "blade": self.cfg.blade,
            "prism": self.cfg.prism,
            "keeper": self.cfg.keeper,
        }.get(type_)

    def _spawn_initial(self) -> None:
        self.enemies = []
        for s in self.spec.enemies:
            self._spawn_enemy(s.type, s.x, s.y)
        if self.boss_defeated:
            return
        for boss in self.bosses:
            self.world.despawn(boss.entity)
        self.bosses = []
        for s in self._boss_spawns():
            if s.type not in _BOSS_KINDS:
                raise ValueError(f"unknown boss type: {s.type}")
            boss_cls = KeeperBoss if s.type == "keeper" else Boss
            self.bosses.append(boss_cls(
                self.world.spawn(x=s.x, y=s.y),
                self.cfg, self.bus,
                boss_cfg=self._boss_cfg(s.type),
                kind=s.type,
            ))

    def _spawn_enemy(self, type_: str, x: float, y: float) -> None:
        entity = self.world.spawn(x=x, y=y)
        if type_ == "crawler":
            self.enemies.append(Crawler(entity, self.cfg, self.bus))
        elif type_ == "spitter":
            self.enemies.append(Spitter(entity, self.cfg, self.bus))
        elif type_ == "shard":
            self.enemies.append(Shard(entity, self.cfg, self.bus))
        elif type_ == "orb":
            self.enemies.append(Orb(entity, self.cfg, self.bus))
        else:
            raise ValueError(f"unknown enemy type: {type_}")

    def _on_projectile_spawned(self, projectile: Projectile) -> None:
        self.projectiles.append(projectile)

    def _publish_projectile(self, projectile: Projectile) -> None:
        self.bus.publish("projectile_spawned", projectile=projectile)

    _SUBSTANCE_KINDS = ("crawler", "spitter", "shard")

    def _on_entity_died(self, entity: Entity) -> None:
        """Dead mobs yield substance; when one twin falls, the survivor enrages."""
        if entity.kind in self._SUBSTANCE_KINDS:
            section = {
                "crawler": self.cfg.crawler,
                "spitter": self.cfg.spitter,
                "shard": self.cfg.shard,
            }[entity.kind]
            self.player.gain_substance(section.substance_yield)
            return
        if entity.kind not in ("blade", "prism"):
            return
        for boss in self.bosses:
            if boss.entity is entity or not boss.entity.alive:
                continue
            if boss.phase == 1:
                boss.enrage()

    # ------------------------------------------------------------------ respawn

    def respawn_everything(self) -> None:
        """Respawn player at checkpoint with full resources; revive enemies."""
        for enemy in self.enemies:
            self.world.despawn(enemy.entity)
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
        self._update_relief_state()

        # death sequencing: fade delay handled by render via death_timer
        if self.player.state == "dead":
            self.death_timer += dt
            if self.death_timer >= DEATH_RESPAWN_DELAY:
                self.respawn_everything()
            self._update_projectiles(dt)
            return

        self._check_interactions(intents)
        self._check_boss_trigger()

        self.player.update(dt, intents, self.world)
        self._check_sharp_edges()

        for enemy in list(self.enemies):
            if enemy.entity.alive:
                enemy.update(dt, self.player, self.world)
                if enemy.entity.y > self.world.bounds[1] + self.world.bounds[3]:
                    enemy.entity.alive = False
        for boss in self.bosses:
            if boss.entity.alive:
                boss.update(dt, self.player, self.world, self._publish_projectile)

        self._resolve_player_attacks()
        self._update_projectiles(dt)
        self._check_kill_zones()

        if (self.bosses and not self.boss_defeated
                and all(not b.entity.alive for b in self.bosses)):
            self.boss_defeated = True
            self._set_boss_gate(False)
            self.victory = True
            self.bus.publish("victory")

    def _check_sharp_edges(self) -> None:
        """Sharp glass faces cut: a short knockback away from the wall."""
        e = self.player.entity
        if not e.alive or self.player.state == "dead":
            return
        hit = touching_sharp_side(e, self.world.platforms)
        if hit is None:
            return
        _platform, side = hit
        if self.player.take_hit(SHARP_EDGE_DAMAGE, 0.0, None):
            e.vx = side * SHARP_EDGE_KNOCKBACK
            self.bus.publish("sharp_hit", entity=e, x=e.x, y=e.y)

    # ------------------------------------------------------------------ subsystems

    def _check_interactions(self, intents: InputIntents) -> None:
        """One E press does at most one thing, in a strict priority order:
        finale dismissal -> portal -> figure face -> relief -> checkpoint."""
        if not intents.interact_pressed:
            return
        e = self.player.entity
        if self.hub_finale and not self.finale_dismissed:
            self.finale_dismissed = True
            return
        for portal in self.spec.portals:
            if within_reach(e.x, e.y, portal.x, portal.y, portal.radius):
                self._restore_resources()
                self.bus.publish("travel", target=portal.target)
                return
        if self.spec.figure is not None:
            radius = self.cfg.hub.face_radius
            for face in self.spec.figure.faces:
                if not within_reach(e.x, e.y, face.x, face.y, radius):
                    continue
                if self.face_state(face) == "available":
                    self.bus.publish("travel", target=face.target)
                return
        relief = self.spec.relief
        if (relief is not None
                and within_reach(e.x, e.y, relief.x, relief.y, relief.radius)
                and self.player.substance > 0):
            # first E arms, second E confirms one step; empty hands fall through
            if not self.relief_armed:
                self.relief_armed = True
                return
            step = min(self.cfg.density.relief_step, self.player.substance)
            self.player.set_substance(self.player.substance - step)
            self.bus.publish("substance_relieved", amount=step)
            self.relief_armed = False
            return
        self._check_checkpoint()

    def _update_relief_state(self) -> None:
        """Disarm the pending relief act when the player leaves the zone.

        Runs every tick regardless of input: `_check_interactions` early-exits
        without `interact_pressed`, so a disarm check in there would never fire.
        """
        relief = self.spec.relief
        if relief is None or not self.relief_armed:
            return
        e = self.player.entity
        if not within_reach(e.x, e.y, relief.x, relief.y, relief.radius):
            self.relief_armed = False

    def _restore_resources(self) -> None:
        self.player.entity.hp = self.player.entity.max_hp
        self.player.heal_charges = self.cfg.player.heal_charges
        self.player.stamina.value = self.player.stamina.max

    def _check_checkpoint(self) -> None:
        e = self.player.entity
        for cp in self.spec.checkpoints:
            if cp.name in self.activated_checkpoints:
                continue
            if within_reach(e.x, e.y, cp.x, cp.y, cp.radius):
                self.activated_checkpoints.add(cp.name)
                self.current_checkpoint = (cp.x, cp.y - 40.0)
                self._restore_resources()
                self.bus.publish("checkpoint", checkpoint=cp)
                return

    def _check_boss_trigger(self) -> None:
        if self.boss_defeated or not self.bosses:
            return
        if all(b.state != "dormant" for b in self.bosses):
            return
        trig = self.spec.boss_trigger
        if trig is None:
            return
        e = self.player.entity
        if aabb_overlap(e.left, e.top, e.width, e.height,
                        trig.x, trig.y, trig.width, trig.height):
            for boss in self.bosses:
                boss.apply_mirror(self.player.density_norm)
                boss.activate()
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
        for boss in self.bosses:
            if boss.entity.alive and boss.state != "dormant":
                targets.append((boss.entity, boss))
        for entity, controller in targets:
            if entity.id in self._swing_hits:
                continue
            if attack_hitbox_hits(self.player.entity, attack, entity):
                self._swing_hits.add(entity.id)
                damage = max(1, round(a.damage * self.player.damage_mult))
                landed = controller.take_hit(damage, a.stagger_damage, a.knockback,
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
            e = self.player.entity
            if (self.player.entity.alive and self.player.state != "dead"
                    and aabb_overlap(pl_l, pl_t, pl_w, pl_h,
                                     e.left, e.top, e.width, e.height)
                    and self.player.take_hit(p.damage, 120.0, None)):
                p.alive = False
                self.projectiles.remove(p)

    def _check_kill_zones(self) -> None:
        e = self.player.entity
        if e.alive and in_kill_zone(e, self.world.kill_zones):
            self.player.take_hit(10_000, 0.0, None)
