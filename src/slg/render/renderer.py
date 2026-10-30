"""Renderer: composes camera, background, terrain, characters, particles, HUD."""

from __future__ import annotations

import pygame

from slg.core.session import DEATH_RESPAWN_DELAY, Session
from slg.render.background import Background
from slg.render.camera import SCREEN_H, SCREEN_W, Projection, SideProjection
from slg.render.characters import (
    draw_boss,
    draw_checkpoint,
    draw_crawler,
    draw_player,
    draw_projectile,
    draw_spitter,
)
from slg.render.hud import Hud
from slg.render.particles import Particles
from slg.render.terrain import TerrainRenderer


class Renderer:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projection: Projection = SideProjection(session.world.bounds)
        self.background = Background(session.world.bounds)
        self.terrain = TerrainRenderer(session.spec.platforms)
        self.particles = Particles()
        self.hud = Hud()
        self._subscribe(session.bus)
        spawn = session.player.entity
        self.projection.snap_to(spawn.x, spawn.y)  # type: ignore[attr-defined]
        self._checkpoint_near = False
        self._vignette_surf = self._bake_vignette()

    @staticmethod
    def _bake_vignette() -> pygame.Surface:
        vignette = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        steps = 6
        for i in range(steps):
            alpha = 22 + i * 15
            rect = pygame.Rect(0, 0, SCREEN_W - i * 26, SCREEN_H - i * 26)
            rect.center = (SCREEN_W // 2, SCREEN_H // 2)
            pygame.draw.rect(vignette, (8, 10, 7, alpha), rect,
                             width=10 + i * 3, border_radius=20)
        try:
            vignette = vignette.convert_alpha()
        except pygame.error:
            pass
        return vignette

    def _subscribe(self, bus) -> None:
        bus.subscribe("attack_hit", self._on_attack_hit)
        bus.subscribe("player_damaged", self._on_player_damaged)
        bus.subscribe("entity_died", self._on_entity_died)
        bus.subscribe("heal", self._on_heal)
        bus.subscribe("telegraph", self._on_telegraph)

    # ------------------------------------------------------------------ events

    def _on_attack_hit(self, attacker, victim, x, y, damage, heavy) -> None:
        self.particles.impact_burst(x, y, heavy)

    def _on_player_damaged(self, amount, source) -> None:
        e = self.session.player.entity
        self.particles.blood_burst(e.x, e.y)

    def _on_entity_died(self, entity) -> None:
        self.particles.death_burst(entity.x, entity.y)

    def _on_heal(self, entity, amount) -> None:
        self.particles.heal_glow(entity.x, entity.y - 10)

    def _on_telegraph(self, entity, kind, duration) -> None:
        self.particles.telegraph_puff(entity.x, entity.y)

    # ------------------------------------------------------------------ frame

    def update(self, dt: float) -> None:
        e = self.session.player.entity
        self.projection.update(dt, e.x, e.y, e.facing)  # type: ignore[attr-defined]
        cam = self.projection.camera_center()
        self.particles.update(dt, cam[0] - SCREEN_W / 2, cam[1] - SCREEN_H / 2)

    def draw(self, surface: pygame.Surface, paused: bool = False) -> None:
        session = self.session
        to_screen = self.projection.world_to_screen

        self.background.draw(surface, self.projection)  # type: ignore[arg-type]
        self.terrain.draw(surface, session.world.platforms, to_screen)

        for cp in session.spec.checkpoints:
            draw_checkpoint(surface, cp, cp.name in session.activated_checkpoints,
                            to_screen, session.world.time)

        for enemy in session.enemies:
            if enemy.entity.alive:
                if enemy.entity.kind == "crawler":
                    draw_crawler(surface, enemy, to_screen, session.world.time)
                else:
                    draw_spitter(surface, enemy, to_screen, session.world.time)
        if session.boss is not None:
            draw_boss(surface, session.boss, to_screen, session.world.time)
        for projectile in session.projectiles:
            draw_projectile(surface, projectile, to_screen, session.world.time)
        draw_player(surface, session.player, to_screen, session.world.time)

        self.particles.draw(surface, to_screen)

        # vignette: dying world framing (baked once)
        surface.blit(self._vignette_surf, (0, 0))

        # HUD
        self.hud.player_bars(surface, session.player)
        self.hud.boss_bar(surface, session.boss)
        self._checkpoint_near = self._near_checkpoint()
        self.hud.checkpoint_prompt(surface, self._checkpoint_near)
        if session.player.state == "dead":
            self.hud.death_overlay(surface, session.death_timer / DEATH_RESPAWN_DELAY)
        if session.victory:
            self.hud.victory_overlay(surface, session.world.time)
        if paused:
            self.hud.pause_overlay(surface)

    def _near_checkpoint(self) -> bool:
        e = self.session.player.entity
        if self.session.player.state == "dead":
            return False
        for cp in self.session.spec.checkpoints:
            if cp.name not in self.session.activated_checkpoints:
                if abs(e.x - cp.x) <= cp.radius and abs(e.y - cp.y) <= cp.radius + 40.0:
                    return True
        return False
