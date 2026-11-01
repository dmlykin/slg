# AGENTS.md — «Гибнущий мир» (slg)

## Проект
2D souls-like на pygame-ce: Python 3.12, src-layout, фиксированный шаг 60 Гц.
Вся графика и звук процедурные — файлов ассетов нет. Три уровня: `swamp`,
`glass`, `well`; боссы, редактор уровней, headless-тесты.

## Команды
| Задача | Команда |
|---|---|
| Игра | `.venv/bin/slg` |
| Уровень / отладка | `.venv/bin/slg --level 2 --debug` |
| Редактор | `.venv/bin/slg --edit --level 1` |
| Все тесты | `.venv/bin/python -m pytest -q` |
| Один файл / тест | `.venv/bin/python -m pytest tests/test_keeper.py -q` |
| Проверка синтаксиса | `.venv/bin/python -m compileall -q src tests` |
| Переустановка | `uv sync` или `.venv/bin/pip install -e . pytest` |

Линтера в проекте нет (`ruff` не установлен). Стиль: PEP 8,
`from __future__ import annotations`, docstring-и на английском, UI-текст на
русском.

## Железные правила
1. `slg.core.*` — headless. Никаких `import pygame`, рендера и звука. Любое
   правило игры должно работать в pytest без окна.
2. `slg.render.*` и `slg.audio` только читают `Session`/`World` и подписываются
   на `EventBus`. Они не меняют состояние симуляции.
3. Core общается с render/audio только событиями (`slg/core/events.py`).
4. Все числа, тайминги и урон — в `src/slg/core/config.py` (frozen dataclass).
   Не хардкодь баланс в логике; в тестах используй `cfg.with_overrides(...)`.
5. Координаты: `Entity.x/y` — центр AABB; `Platform.x/y`, `KillZone`,
   `Trigger` — левый верхний угол; `Checkpoint` и спавны — центр. `bounds` —
   это `(left, top, width, height)`, а не правый/нижний край. `z` зарезервирован
   и всегда равен 0.
6. Симуляция детерминирована: только `session.update(fixed_dt, intents)`.
   Никаких `time.sleep`, реального времени и pygame в тестах ядра.
7. Новый контент — данные в `src/slg/data/*.json`; код меняется только для
   новых механик.
8. Не коммить без явной просьбы. Не трогай `.venv/`, `uv.lock`,
   `.kilo/agent-manager.json`.

## Карта кода
| Файл | Ответственность |
|---|---|
| `src/slg/main.py` | окно, ввод, fixed-timestep цикл, `--level/--debug/--edit` |
| `src/slg/core/session.py` | оркестратор: спавн, респавн, победа, связывание систем |
| `src/slg/core/player.py` | FSM игрока, шум, ресурсы |
| `src/slg/core/enemies.py` | crawler/spitter/shard/orb, снаряды |
| `src/slg/core/boss.py` | базовый босс: slam/sweep/volley, фазы, poise |
| `src/slg/core/keeper.py` | Слепой смотритель: слух, эхо, падающие молнии |
| `src/slg/core/physics.py` | гравитация, AABB-коллизии, sharp-грани |
| `src/slg/core/combat.py` | stamina, attack-фазы, hitbox, poise, i-frames |
| `src/slg/core/level.py` | JSON -> `LevelSpec` |
| `src/slg/core/world.py` | `Entity`, `World`, платформы, чекпоинты |
| `src/slg/core/config.py` | весь баланс и тайминги |
| `src/slg/render/*` | камера, фон, террейн, персонажи, частицы, HUD, палитры |
| `src/slg/editor.py` | редактор: `EditorState` (данные) + `run_editor` (pygame) |
| `src/slg/data/level_0N.json` | уровни |
| `tests/` | pytest; `conftest.py` — фикстуры и `run_frames` |

## Как работать
- Перед правкой ядра прочитай `docs/ARCHITECTURE.md`.
- Новый уровень, враг, босс или тема — `docs/CONTENT.md`.
- Тесты и проверки — `docs/TESTING.md`.
- После изменений обязательно: `.venv/bin/python -m pytest -q`. Для рендера и
  аудио дополнительно проверь smoke-тесты под SDL dummy
  (`tests/test_smoke_render.py`, `tests/test_audio.py`).
- Сначала ищи существующий паттерн (`grep`), потом добавляй код. Не вводи новые
  зависимости без необходимости.
