"""Minimalist HUD: HP/stamina bars, flask charges, boss bar, prompts, overlays."""

from __future__ import annotations

import math

import pygame

from slg.render.palette import PALETTE

FONT_SIZE = 18

BOSS_LABELS = {"boss": "ПОЖИРАТЕЛЬ", "blade": "КЛИНОК", "prism": "ПРИЗМА",
               "keeper": "СЛЕПОЙ СМОТРИТЕЛЬ"}


def _font() -> pygame.font.Font:
    try:
        return pygame.font.Font(None, FONT_SIZE)
    except Exception:
        return pygame.font.SysFont(None, FONT_SIZE)


class Hud:
    def __init__(self) -> None:
        self.font = _font()
        self.big_font = pygame.font.Font(None, 42)

    # ------------------------------------------------------------------ bars

    def _bar(self, surface: pygame.Surface, pos: tuple[int, int], size: tuple[int, int],
             frac: float, color: tuple[int, int, int], bg: tuple[int, int, int]) -> None:
        x, y = pos
        w, h = size
        pygame.draw.rect(surface, bg, (x - 2, y - 2, w + 4, h + 4), border_radius=3)
        pygame.draw.rect(surface, (10, 12, 9), (x, y, w, h), border_radius=2)
        fill = int(max(0.0, min(1.0, frac)) * w)
        if fill > 0:
            pygame.draw.rect(surface, color, (x, y, fill, h), border_radius=2)

    def player_bars(self, surface: pygame.Surface, player) -> None:
        e = player.entity
        self._bar(surface, (24, 24), (300, 14), e.hp / e.max_hp,
                  PALETTE["blood"], PALETTE["ui_dim"])
        self._bar(surface, (24, 44), (240, 10),
                  player.stamina.value / player.stamina.max, PALETTE["stamina"], PALETTE["ui_dim"])
        if player.substance > 0:
            self._bar(surface, (24, 58), (200, 8),
                      player.substance / player.cfg.density.max_substance,
                      PALETTE["density"], PALETTE["ui_dim"])
        # flask charges: small diamonds
        for i in range(player.cfg.player.heal_charges):
            x = 30 + i * 20
            y = 80
            has = i < player.heal_charges
            color = PALETTE["heal_glow"] if has else (40, 44, 34)
            pts = [(x, y - 6), (x + 5, y), (x, y + 6), (x - 5, y)]
            pygame.draw.polygon(surface, color, pts)

    def boss_bars(self, surface: pygame.Surface, bosses) -> None:
        visible = [b for b in bosses if b.entity.alive and b.state != "dormant"]
        if not visible:
            return
        w, h = 620, 12
        x = (1280 - w) // 2
        y = 660
        for boss in visible:
            e = boss.entity
            self._bar(surface, (x, y), (w, h), e.hp / e.max_hp,
                      PALETTE["eyes_boss"] if boss.phase == 2 else PALETTE["blood"],
                      PALETTE["ui_dim"])
            label = self.font.render(BOSS_LABELS.get(boss.kind, "БОСС"), True,
                                     PALETTE["ui_text"])
            surface.blit(label, (x, y - 22))
            y -= 40

    # ------------------------------------------------------------------ prompts

    def interact_prompt(self, surface: pygame.Surface, text: str | None) -> None:
        if not text:
            return
        label = self.font.render(text, True, PALETTE["spore"])
        rect = label.get_rect(midbottom=(640, 640))
        pulse = 0.6 + 0.4 * math.sin(pygame.time.get_ticks() * 0.006)
        glow = pygame.Surface((rect.width + 16, rect.height + 10), pygame.SRCALPHA)
        pygame.draw.rect(glow, (*PALETTE["spore"], int(40 * pulse)),
                         glow.get_rect(), border_radius=6)
        surface.blit(glow, rect.inflate(16, 10))
        surface.blit(label, rect)

    # ------------------------------------------------------------------ overlays

    def death_overlay(self, surface: pygame.Surface, progress: float) -> None:
        """progress 0..1 through the death delay -> fade to black."""
        alpha = int(255 * min(1.0, progress * 1.4))
        if alpha <= 0:
            return
        shade = pygame.Surface((1280, 720), pygame.SRCALPHA)
        shade.fill((6, 7, 5, alpha))
        surface.blit(shade, (0, 0))
        if progress > 0.35:
            text = self.big_font.render("ВЫ ПОГИБЛИ", True, PALETTE["blood"])
            rect = text.get_rect(center=(640, 330))
            surface.blit(text, rect)

    def victory_overlay(self, surface: pygame.Surface, time: float,
                        title: str = "СЕРДЦЕ УМОЛКЛО",
                        subtitle: str = "Мир дышит. Пока что. MVP пройден.",
                        hint: str | None = "E — идти дальше") -> None:
        shade = pygame.Surface((1280, 720), pygame.SRCALPHA)
        shade.fill((6, 7, 5, 140))
        surface.blit(shade, (0, 0))
        text = self.big_font.render(title, True, PALETTE["bone"])
        surface.blit(text, text.get_rect(center=(640, 320)))
        sub = self.font.render(subtitle, True, PALETTE["spore"])
        surface.blit(sub, sub.get_rect(center=(640, 360)))
        if hint:
            pulse = 0.6 + 0.4 * math.sin(time * 3.0)
            color = tuple(int(c * (0.55 + 0.45 * pulse)) for c in PALETTE["ui_text"])
            tip = self.font.render(hint, True, color)
            surface.blit(tip, tip.get_rect(center=(640, 402)))

    def pause_overlay(self, surface: pygame.Surface) -> None:
        shade = pygame.Surface((1280, 720), pygame.SRCALPHA)
        shade.fill((6, 7, 5, 150))
        surface.blit(shade, (0, 0))
        text = self.big_font.render("ПАУЗА", True, PALETTE["ui_text"])
        surface.blit(text, text.get_rect(center=(640, 340)))
        sub = self.font.render(
            "A/D — движение  Space — прыжок  J/K — атака  "
            "Shift — перекат  Q — лечение  E — взаимодействие  M — фон",
            True, PALETTE["ui_text"])
        surface.blit(sub, sub.get_rect(center=(640, 380)))
