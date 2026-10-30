"""Bootstrap: window, fixed-timestep loop (60 Hz sim + per-frame render), input."""

from __future__ import annotations

import sys
from pathlib import Path

import pygame

from slg.core.level import LevelSpec
from slg.core.player import InputIntents
from slg.core.session import Session
from slg.audio import AudioSystem
from slg.render.camera import SCREEN_H, SCREEN_W
from slg.render.renderer import Renderer

LEVEL_FILE = Path(__file__).resolve().parent / "data" / "level_01.json"


def _new_intents() -> InputIntents:
    return InputIntents()


def _consume_one_shots(intents: InputIntents) -> None:
    intents.jump_pressed = False
    intents.roll_pressed = False
    intents.light_pressed = False
    intents.heavy_pressed = False
    intents.heal_pressed = False
    intents.interact_pressed = False


def main() -> int:
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Гибнущий мир")
    clock = pygame.time.Clock()

    spec = LevelSpec.load(LEVEL_FILE)
    session = Session(spec=spec)
    renderer = Renderer(session)
    AudioSystem(session.bus)

    intents = _new_intents()
    paused = False
    accumulator = 0.0
    fixed_dt = session.cfg.physics.fixed_dt

    running = True
    while running:
        frame_time = clock.tick(60) / 1000.0
        _consume_one_shots(intents)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    paused = not paused
                elif not paused and not session.victory:
                    if event.key == pygame.K_SPACE:
                        intents.jump_pressed = True
                    elif event.key == pygame.K_j:
                        intents.light_pressed = True
                    elif event.key == pygame.K_k:
                        intents.heavy_pressed = True
                    elif event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_l):
                        intents.roll_pressed = True
                    elif event.key == pygame.K_q:
                        intents.heal_pressed = True
                    elif event.key == pygame.K_e:
                        intents.interact_pressed = True

        if not paused and not session.victory:
            keys = pygame.key.get_pressed()
            intents.move = (1 if keys[pygame.K_d] else 0) - (1 if keys[pygame.K_a] else 0)
            intents.jump_held = bool(keys[pygame.K_SPACE])

            accumulator += min(frame_time, 0.25)
            first_tick = True
            while accumulator >= fixed_dt:
                session.update(fixed_dt, intents)
                if first_tick:
                    _consume_one_shots(intents)
                    first_tick = False
                accumulator -= fixed_dt
            renderer.update(frame_time)

        renderer.draw(screen, paused)
        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
