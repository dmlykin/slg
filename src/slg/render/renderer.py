"""Renderer: composes camera, background, terrain, characters, particles, HUD."""

from __future__ import annotations

import pygame

from slg.core.session import DEATH_RESPAWN_DELAY, Session, within_reach
from slg.render.background import Background
from slg.render.camera import SCREEN_H, SCREEN_W, Projection, SideProjection
from slg.render.characters import (
    draw_boss,
    draw_checkpoint,
    draw_crawler,
    draw_figure,
    draw_noise_ring,
    draw_orb,
    draw_player,
    draw_portal,
    draw_projectile,
    draw_shard,
    draw_spitter,
)
from slg.render.hud import Hud
from slg.render.palette import current_theme, set_theme
from slg.render.particles import Particles
from slg.render.terrain import TerrainRenderer

FACE_PROMPTS = {
    # type -> prompt for an available face
    "turner": "Превратница — E — ступить в топи",
    "warden": "Хранитель — E — пройти по стеклу",
    "herald": "Вдохновитель — E — сойти в колодец",
}
LOCKED_PROMPT = "Лик спит"
PORTAL_PROMPT = "E — вернуться к трёхликой"
CHECKPOINT_PROMPT = "E — коснуться сердца"


class Renderer:
    def __init__(self, session: Session, victory_title: str | None = None,
                 victory_subtitle: str | None = None,
                 victory_hint: str | None = "E — идти дальше",
                 finale_title: str | None = None,
                 finale_subtitle: str | None = None,
                 finale_hint: str | None = None) -> None:
        self.session = session
        # Theme must be live before anything is baked.
        set_theme(session.spec.theme)
        self.projection: Projection = SideProjection(
            session.world.bounds,
            vertical_bias=100.0 if session.spec.vertical else -60.0,
        )
        self.background = Background(session.world.bounds, theme=session.spec.theme,
                                     vertical=session.spec.vertical)
        self.terrain = TerrainRenderer(session.spec.platforms)
        self.particles = Particles()
        self.hud = Hud()
        self.victory_title = victory_title
        self.victory_subtitle = victory_subtitle
        self.victory_hint = victory_hint
        self.finale_title = finale_title
        self.finale_subtitle = finale_subtitle
        self.finale_hint = finale_hint
        self._subscribe(session.bus)
        spawn = session.player.entity
        self.projection.snap_to(spawn.x, spawn.y)  # type: ignore[attr-defined]
        self._checkpoint_near = False
        self._vignette_surf = self._bake_vignette()

    @staticmethod
    def _bake_vignette() -> pygame.Surface:
        theme = current_theme()
        glass = theme == "glass"
        well = theme == "well"
        sanctum = theme == "sanctum"
        mult = 1.8 if well else (1.55 if glass else (0.85 if sanctum else 1.0))
        if well:
            tint = (3, 5, 5)
        elif glass:
            tint = (8, 9, 14)
        elif sanctum:
            tint = (14, 11, 8)
        else:
            tint = (8, 10, 7)
        vignette = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        steps = 6
        for i in range(steps):
            alpha = int(min(255, (22 + i * 15) * mult))
            rect = pygame.Rect(0, 0, SCREEN_W - i * 26, SCREEN_H - i * 26)
            rect.center = (SCREEN_W // 2, SCREEN_H // 2)
            pygame.draw.rect(vignette, (*tint, alpha), rect,
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
        bus.subscribe("sharp_hit", self._on_sharp_hit)
        bus.subscribe("orb_shattered", self._on_orb_shattered)

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

    def _on_sharp_hit(self, entity, x, y) -> None:
        self.particles.spark_burst(x, y)

    def _on_orb_shattered(self, x, y) -> None:
        self.particles.spark_burst(x, y)

    # ------------------------------------------------------------------ frame

    def update(self, dt: float) -> None:
        e = self.session.player.entity
        self.projection.update(dt, e.x, e.y, e.facing, e.vy)  # type: ignore[attr-defined]
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
        for portal in session.spec.portals:
            draw_portal(surface, portal, to_screen, session.world.time)
        if session.spec.figure is not None:
            states = [session.face_state(face) for face in session.spec.figure.faces]
            draw_figure(surface, session.spec.figure, states, to_screen,
                        session.world.time)

        for enemy in session.enemies:
            if enemy.entity.alive:
                if enemy.entity.kind == "crawler":
                    draw_crawler(surface, enemy, to_screen, session.world.time)
                elif enemy.entity.kind == "spitter":
                    draw_spitter(surface, enemy, to_screen, session.world.time)
                elif enemy.entity.kind == "orb":
                    draw_orb(surface, enemy, to_screen, session.world.time)
                else:
                    draw_shard(surface, enemy, to_screen, session.world.time)
        for boss in session.bosses:
            if boss.entity.alive:
                draw_boss(surface, boss, to_screen, session.world.time)
        for projectile in session.projectiles:
            draw_projectile(surface, projectile, to_screen, session.world.time)
        if any(b.kind == "keeper" and b.entity.alive and b.state != "dormant"
               for b in session.bosses):
            draw_noise_ring(surface, session.player, to_screen)
        draw_player(surface, session.player, to_screen, session.world.time)

        self.particles.draw(surface, to_screen)

        # vignette: dying world framing (baked once)
        surface.blit(self._vignette_surf, (0, 0))

        # HUD
        self.hud.player_bars(surface, session.player)
        self.hud.boss_bars(surface, session.bosses)
        self._checkpoint_near = self._near_checkpoint()
        self.hud.interact_prompt(surface, self._prompt_text())
        if session.player.state == "dead":
            self.hud.death_overlay(surface, session.death_timer / DEATH_RESPAWN_DELAY)
        if session.victory:
            self.hud.victory_overlay(
                surface, session.world.time,
                title=self.victory_title or "СЕРДЦЕ УМОЛКЛО",
                subtitle=self.victory_subtitle or "Мир дышит. Пока что. MVP пройден.",
                hint=self.victory_hint,
            )
        elif session.hub_finale and not session.finale_dismissed:
            self.hud.victory_overlay(
                surface, session.world.time,
                title=self.finale_title or "СНЯТИЕ ТЯГОТ",
                subtitle=self.finale_subtitle or "Все тяготы сняты. КОНЕЦ ДЕМО.",
                hint=self.finale_hint,
            )
        if paused:
            self.hud.pause_overlay(surface)

    def _prompt_text(self) -> str | None:
        """One prompt at a time: portal, then figure face, then checkpoint."""
        if self._near_portal():
            return PORTAL_PROMPT
        face = self._near_face()
        if face is not None:
            if self.session.face_state(face) == "available":
                return FACE_PROMPTS.get(face.type, "E — ступить")
            return LOCKED_PROMPT
        if self._checkpoint_near:
            return CHECKPOINT_PROMPT
        return None

    def _near_checkpoint(self) -> bool:
        e = self.session.player.entity
        if self.session.player.state == "dead":
            return False
        for cp in self.session.spec.checkpoints:
            if (cp.name not in self.session.activated_checkpoints
                    and within_reach(e.x, e.y, cp.x, cp.y, cp.radius)):
                return True
        return False

    def _near_portal(self):
        e = self.session.player.entity
        if self.session.player.state == "dead":
            return None
        for portal in self.session.spec.portals:
            if within_reach(e.x, e.y, portal.x, portal.y, portal.radius):
                return portal
        return None

    def _near_face(self):
        figure = self.session.spec.figure
        e = self.session.player.entity
        if figure is None or self.session.player.state == "dead":
            return None
        radius = self.session.cfg.hub.face_radius
        for face in figure.faces:
            if within_reach(e.x, e.y, face.x, face.y, radius):
                return face
        return None
