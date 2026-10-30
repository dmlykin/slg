"""Player state machine: idle/run/jump/roll/attack_l/attack_h/heal/hurt/dead."""

from __future__ import annotations

from dataclasses import dataclass

from slg.core.combat import AttackState, Damageable, Stamina
from slg.core.config import Config
from slg.core.events import EventBus
from slg.core.physics import apply_gravity, clamp_to_bounds, move_and_collide
from slg.core.world import Entity, World


@dataclass
class InputIntents:
    """What the player pressed this tick (filled by the input layer)."""

    move: int = 0              # -1, 0, 1
    jump_pressed: bool = False
    jump_held: bool = False
    roll_pressed: bool = False
    light_pressed: bool = False
    heavy_pressed: bool = False
    heal_pressed: bool = False
    interact_pressed: bool = False


class Player:
    """Owns one Entity; drives its state machine. No pygame, no rendering."""

    def __init__(self, entity: Entity, cfg: Config, bus: EventBus) -> None:
        self.entity = entity
        self.cfg = cfg
        self.bus = bus
        p = cfg.player
        entity.hp = entity.max_hp = p.max_hp
        entity.width, entity.height = p.width, p.height
        entity.kind = "player"
        self.stamina = Stamina(p.max_stamina, p.max_stamina, p.stamina_regen, p.stamina_regen_delay)
        self.attack = AttackState()
        self.damageable = Damageable(entity)
        self.state = "idle"
        self.state_timer = 0.0
        self.roll_dir = 1
        self.heal_charges = p.heal_charges
        self.heal_timer = 0.0
        self.coyote_timer = 0.0
        self._jump_cut_done = False

    # ------------------------------------------------------------------ helpers

    @property
    def invulnerable(self) -> bool:
        if self.damageable.invulnerable:
            return True
        if self.state == "roll":
            r = self.cfg.roll
            return r.iframes_start <= self.state_timer <= r.iframes_end
        return False

    @property
    def busy(self) -> bool:
        return self.state in ("roll", "attack_l", "attack_h", "heal", "hurt", "dead")

    def _enter(self, state: str) -> None:
        self.state = state
        self.state_timer = 0.0

    # ------------------------------------------------------------------ damage

    def take_hit(self, damage: int, knockback: float, source: Entity | None = None) -> bool:
        """Returns True if the hit landed (not i-framed)."""
        if self.state == "dead" or self.invulnerable:
            return False
        landed = self.damageable.try_take_hit(damage, knockback, source)
        if not landed:
            return False
        self.bus.publish("player_damaged", amount=damage, source=source)
        self.bus.publish(
            "entity_damaged", entity=self.entity, amount=damage, source=source
        )
        if self.entity.hp <= 0:
            self._enter("dead")
            self.entity.vx = 0.0
            self.bus.publish("entity_died", entity=self.entity)
            return True
        # interrupt everything, stagger briefly
        self.attack = AttackState()
        self.heal_timer = 0.0
        self._enter("hurt")
        self.damageable.grant_iframes(self.cfg.player.invuln_after_hit)
        return True

    # ------------------------------------------------------------------ update

    def update(self, dt: float, intents: InputIntents, world: World) -> None:
        p = self.cfg.player
        e = self.entity
        self.state_timer += dt
        self.stamina.update(dt)
        self.damageable.update(dt)

        if self.state == "dead":
            e.vx = 0.0
            apply_gravity(e, self.cfg.physics, dt)
            move_and_collide(e, world, dt)
            return

        if self.state == "hurt":
            if self.state_timer >= p.hurt_stun:
                self._enter("idle")
            # mid-air hurt keeps reduced air control so hits don't dump you into pits
            if not e.on_ground and intents.move != 0:
                target_vx = intents.move * p.run_speed * p.air_control
                accel = p.accel * p.air_control
                if e.vx < target_vx:
                    e.vx = min(target_vx, e.vx + accel * dt)
                elif e.vx > target_vx:
                    e.vx = max(target_vx, e.vx - accel * dt)
            apply_gravity(e, self.cfg.physics, dt)
            move_and_collide(e, world, dt)
            clamp_to_bounds(e, world)
            return

        if self.state == "roll":
            self._update_roll(dt, world)
            return

        if self.state in ("attack_l", "attack_h"):
            self._update_attack(dt, intents, world)
            return

        if self.state == "heal":
            self._update_heal(dt, world)
            return

        self._update_free(dt, intents, world)

    # ------------------------------------------------------------------ states

    def _update_free(self, dt: float, intents: InputIntents, world: World) -> None:
        p = self.cfg.player
        e = self.entity
        grounded = e.on_ground
        self.coyote_timer = p.coyote_time if grounded else max(0.0, self.coyote_timer - dt)

        # --- facing + horizontal movement ---
        if intents.move != 0:
            e.facing = intents.move
        target_vx = intents.move * p.run_speed
        accel = p.accel * (p.air_control if not grounded else 1.0)
        if e.vx < target_vx:
            e.vx = min(target_vx, e.vx + accel * dt)
        elif e.vx > target_vx:
            e.vx = max(target_vx, e.vx - accel * dt)

        # --- actions (priority: roll > attack > heal > jump) ---
        if grounded and intents.roll_pressed and self.stamina.spend(self.cfg.roll.stamina_cost):
            self.roll_dir = intents.move if intents.move != 0 else e.facing
            e.facing = self.roll_dir
            self._enter("roll")
            self.bus.publish("roll", entity=e)
        elif intents.heal_pressed and grounded and self.heal_charges > 0 and e.hp < e.max_hp:
            self.heal_charges -= 1
            self.heal_timer = self.cfg.combat.heal_duration
            self._enter("heal")
        elif intents.light_pressed and self.stamina.spend(self.cfg.combat.light.stamina_cost):
            self.attack.start(self.cfg.combat.light)
            self._enter("attack_l")
        elif intents.heavy_pressed and self.stamina.spend(self.cfg.combat.heavy.stamina_cost):
            self.attack.start(self.cfg.combat.heavy)
            self._enter("attack_h")
        elif intents.jump_pressed and (grounded or self.coyote_timer > 0.0):
            e.vy = p.jump_velocity
            self.coyote_timer = 0.0
            self._jump_cut_done = False
            self._enter("jump")
            self.bus.publish("jump", entity=e)

        # --- variable jump height ---
        if not intents.jump_held and e.vy < 0 and not self._jump_cut_done:
            e.vy *= p.jump_cut_multiplier
            self._jump_cut_done = True

        apply_gravity(e, self.cfg.physics, dt)
        move_and_collide(e, world, dt)
        clamp_to_bounds(e, world)

        # --- settle idle/run/jump label ---
        if self.state in ("idle", "run", "jump"):
            if not e.on_ground:
                self._enter("jump")
            elif abs(e.vx) > 12.0:
                if self.state != "run":
                    self._enter("run")
            else:
                if self.state != "idle":
                    self._enter("idle")

    def _update_roll(self, dt: float, world: World) -> None:
        r = self.cfg.roll
        e = self.entity
        e.vx = self.roll_dir * r.speed
        if self.state_timer >= r.duration:
            e.vx *= 0.3
            self._enter("idle")
        apply_gravity(e, self.cfg.physics, dt)
        move_and_collide(e, world, dt)
        clamp_to_bounds(e, world)

    def _update_attack(self, dt: float, intents: InputIntents, world: World) -> None:
        e = self.entity
        self.attack.update(dt)
        # heavy momentum drift forward during windup
        drift = 40.0 if self.attack.attack and self.attack.attack.name == "heavy" else 0.0
        if self.attack.phase in ("windup", "active"):
            e.vx = e.facing * drift
        else:
            e.vx *= 0.85
        if not self.attack.busy:
            self._enter("idle")
        apply_gravity(e, self.cfg.physics, dt)
        move_and_collide(e, world, dt)
        clamp_to_bounds(e, world)

    def _update_heal(self, dt: float, world: World) -> None:
        p = self.cfg.player
        e = self.entity
        e.vx *= 0.8
        self.heal_timer -= dt
        if self.heal_timer <= 0.0:
            e.hp = min(e.max_hp, e.hp + p.heal_amount)
            self.bus.publish("heal", entity=e, amount=p.heal_amount)
            self._enter("idle")
        apply_gravity(e, self.cfg.physics, dt)
        move_and_collide(e, world, dt)
        clamp_to_bounds(e, world)

    # ------------------------------------------------------------------ respawn

    def respawn_at(self, x: float, y: float) -> None:
        e = self.entity
        e.x, e.y, e.z = x, y, 0.0
        e.vx = e.vy = 0.0
        e.hp = e.max_hp
        e.alive = True
        self.stamina.value = self.stamina.max
        self.heal_charges = self.cfg.player.heal_charges
        self.attack = AttackState()
        self.damageable.iframes_timer = 0.0
        self._enter("idle")
