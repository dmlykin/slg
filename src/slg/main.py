"""Bootstrap: window, fixed-timestep loop (60 Hz sim + per-frame render), input."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pygame

from slg.audio import AudioSystem
from slg.core.level import LevelSpec
from slg.core.player import InputIntents
from slg.core.progress import Progress
from slg.core.session import Session
from slg.render.camera import SCREEN_H, SCREEN_W
from slg.render.renderer import Renderer

DATA_DIR = Path(__file__).resolve().parent / "data"
LEVEL_KEYS = ["hub", "swamp", "glass", "well"]
LEVELS = {key: DATA_DIR / f"level_0{i}.json" for i, key in enumerate(LEVEL_KEYS)}

VICTORY_TEXT = {
    "swamp": ("СЕРДЦЕ УМОЛКЛО", "Мир дышит. Пока что."),
    "glass": ("СТЕКЛО МОЛЧИТ", "Пустыня остыла. Близнецы разбиты."),
    "well": ("КОЛОДЕЦ УМОЛК", "Спуск окончен. Демо пройдено."),
}
VICTORY_HINT = "E — вернуться"
HUB_FINALE_TEXT = ("СНЯТИЕ ТЯГОТ", "Все тяготы сняты. КОНЕЦ ДЕМО.",
                   "E — остаться в мире")
HUB_KEY = "hub"


def _new_intents() -> InputIntents:
    return InputIntents()


def _consume_one_shots(intents: InputIntents) -> None:
    intents.jump_pressed = False
    intents.roll_pressed = False
    intents.light_pressed = False
    intents.heavy_pressed = False
    intents.heal_pressed = False
    intents.interact_pressed = False


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="slg", description="Gibnushchiy mir")
    parser.add_argument("--level", type=int, default=0, metavar="N",
                        help=f"start at level N (0..{len(LEVEL_KEYS) - 1}); 0 is the hub")
    parser.add_argument("--debug", action="store_true",
                        help="PageDown/PageUp switch levels at any time")
    parser.add_argument("--edit", action="store_true",
                        help="open the in-game level editor for the chosen level")
    return parser.parse_args(argv)


def _clamp_level(index: int) -> int:
    return max(0, min(len(LEVEL_KEYS) - 1, index))


def load_level(index: int, progress: Progress) -> tuple[Session, Renderer, AudioSystem]:
    index = _clamp_level(index)
    key = LEVEL_KEYS[index]
    spec = LevelSpec.load(LEVELS[key])
    session = Session(spec=spec, progress=progress)
    if key == HUB_KEY:
        title, subtitle, hint = HUB_FINALE_TEXT
    else:
        title, subtitle = VICTORY_TEXT[key]
        hint = VICTORY_HINT
    renderer = Renderer(session, victory_title=title, victory_subtitle=subtitle,
                        victory_hint=hint, finale_title=HUB_FINALE_TEXT[0],
                        finale_subtitle=HUB_FINALE_TEXT[1],
                        finale_hint=HUB_FINALE_TEXT[2])
    audio = AudioSystem(session.bus, theme=spec.theme)
    pygame.display.set_caption(f"Гибнущий мир — {spec.name}")
    return session, renderer, audio


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    level_index = _clamp_level(args.level)
    if args.edit:
        from slg.editor import run_editor

        return run_editor(LEVELS[LEVEL_KEYS[level_index]])
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    progress = Progress.load()
    travel_requests: list[str] = []

    def wire(session: Session, key: str) -> None:
        """Each Session owns a fresh EventBus — subscribe after every load."""
        session.bus.subscribe("travel",
                              lambda target: travel_requests.append(target))

        def on_victory() -> None:
            nonlocal progress
            progress = (progress.mark_defeated(key)
                        .with_substance(session.player.substance))
            progress.save()

        session.bus.subscribe("victory", on_victory)

        def on_substance_relieved(amount: float) -> None:
            nonlocal progress
            progress = progress.with_deposit(amount)
            progress.save()

        session.bus.subscribe("substance_relieved", on_substance_relieved)

    session, renderer, audio = load_level(level_index, progress)
    wire(session, LEVEL_KEYS[level_index])
    audio.set_ambient(True)
    ambient_on = True

    intents = _new_intents()
    paused = False
    accumulator = 0.0

    running = True
    while running:
        frame_time = clock.tick(60) / 1000.0
        _consume_one_shots(intents)

        switch_to: int | None = None
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    paused = not paused
                elif event.key == pygame.K_m:
                    ambient_on = not ambient_on
                    audio.set_ambient(ambient_on)
                elif args.debug and event.key in (pygame.K_PAGEDOWN, pygame.K_PAGEUP):
                    step = 1 if event.key == pygame.K_PAGEDOWN else -1
                    switch_to = _clamp_level(level_index + step)
                elif session.victory and event.key == pygame.K_e:
                    switch_to = LEVEL_KEYS.index(HUB_KEY)
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

        if switch_to is None and travel_requests:
            target = travel_requests.pop(0)
            if target in LEVELS:
                switch_to = LEVEL_KEYS.index(target)
            else:
                print(f"unknown travel target: {target}", file=sys.stderr)
        travel_requests.clear()

        if switch_to is not None and switch_to != level_index:
            # the anchor carries over: portal, defeat and post-victory travel
            progress = progress.with_substance(session.player.substance)
            progress.save()
            level_index = switch_to
            session, renderer, audio = load_level(level_index, progress)
            wire(session, LEVEL_KEYS[level_index])
            audio.set_ambient(ambient_on)
            intents = _new_intents()
            accumulator = 0.0
            paused = False

        fixed_dt = session.cfg.physics.fixed_dt
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
