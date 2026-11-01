# Тесты

## Запуск

```sh
.venv/bin/python -m pytest -q                 # всё, ~5 секунд
.venv/bin/python -m pytest tests/test_keeper.py -q
.venv/bin/python -m pytest tests/test_boss.py::test_boss_volley_fires_projectiles -q
.venv/bin/python -m compileall -q src tests   # быстрая проверка синтаксиса
```

- Зависимости уже стоят в `.venv`; pytest 9.x.
- Линтера нет: `ruff` в проект не входит. Стиль проверяй глазами и по
  соседнему коду.
- Тесты обязаны быть headless и быстрыми. Никаких `time.sleep`, скриншотов и
  реального времени.

## База: `tests/conftest.py`

| Фикстура/функция | Что даёт |
|---|---|
| `make_spec(**overrides)` | маленький уровень: 2 платформы, kill zone, чекпоинт, crawler, spitter, босс, триггер и ворота |
| `spec` | `make_spec()` |
| `session` | `Session(spec=spec)` |
| `cfg` | `Config()` |
| `run_frames(session, seconds, intents=None)` | прогоняет ровно `round(seconds / fixed_dt)` шагов |

`run_frames` — основной способ двигать время. Не вызывай `session.update` в
цикле вручную без причины и не смешивай реальное время с симуляцией.

Пример:

```python
from slg.core.player import InputIntents
from tests.conftest import run_frames

def test_player_walks_right(session):
    run_frames(session, 0.5, InputIntents(move=1))
    assert session.player.entity.x > 100
```

## Детерминизм

- Симуляция идёт только фиксированными шагами `cfg.physics.fixed_dt`.
- Позиции и таймеры сравнивай с `pytest.approx(...)`, а не на точное равенство
  float.
- Босс использует `random.Random()` без сида. Не полагайся на случайный паттерн:
  принудительно задай `boss.pattern`, состояние или проверяй допустимое
  множество значений (как в `test_boss_cycles_patterns`).
- В игре `main.py` одноразовые нажатия (`jump_pressed`, `light_pressed` и т.п.)
  сбрасываются после первого фиксированного шага. А `run_frames` передаёт один
  и тот же `InputIntents` каждый шаг, поэтому в тестах `pressed=True` остаётся
  включённым на весь прогон. Для удержания используй `jump_held` / `move`.

## Рендер и аудио

Перед импортом `pygame` выстави драйверы:

```python
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
```

Шаблон smoke-теста:

```python
def test_render_frames_without_crash():
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    try:
        spec = LevelSpec.load("src/slg/data/level_01.json")
        session = Session(spec=spec)
        renderer = Renderer(session)
        for _ in range(120):
            session.update(session.cfg.physics.fixed_dt, InputIntents())
            renderer.update(session.cfg.physics.fixed_dt)
            renderer.draw(screen)
    finally:
        pygame.quit()
```

- Тема — глобальный мутируемый `PALETTE`. Если тест вызывает `set_theme`,
  верни `set_theme("swamp")` в `finally` (см. `test_theme.py`).
- Для аудио проверяй массивы/буферы, а не реальное воспроизведение.

## Карта тестов

| Файл | Что покрывает |
|---|---|
| `test_physics.py` | гравитация, AABB, приземление, стены, kill zones |
| `test_player.py` | движение, прыжок, перекат/i-frames, stamina, лечение, hurt |
| `test_combat.py` | хитбокс только в active, stagger, события смерти |
| `test_enemies.py` | циклы crawler и spitter |
| `test_shard.py` | dormant → telegraph → lunge → recover |
| `test_orb.py` | неуязвимость, контактный урон, разбивание об арену |
| `test_sharp_edges.py` | урон только от боковых граней, i-frames, перекат |
| `test_boss.py` | триггер, паттерны, фаза 2, ворота, победа |
| `test_keeper.py` | слух, фиксация цели, эхо, молнии, зоны, фаза 2 |
| `test_twins.py` | общий триггер, enrage выжившего, победа только за двоих |
| `test_level.py` | загрузка уровней, спавны, чекпоинты, смерть → респавн |
| `test_traversal.py` | каждый разрыв проходим прыжком |
| `test_well.py` | спуск по уступам колодца без софтлоков |
| `test_editor.py` | модель редактора, round-trip JSON, камера, headless boot |
| `test_theme.py` | `set_theme` мутирует общий `PALETTE` |
| `test_smoke_render.py` | импорт, камера, отрисовка кадров |
| `test_audio.py` | процедурные сэмплы корректны и конечны |

## Рецепты

### Игрок и бой

```python
def test_light_attack_damages_crawler(session):
    run_frames(session, 0.2)
    enemy = session.enemies[0]
    p = session.player
    p.entity.x = enemy.entity.x - 40
    p.entity.facing = 1
    p.entity.on_ground = True
    hp = enemy.entity.hp
    run_frames(session, 0.4, InputIntents(light_pressed=True))
    assert enemy.entity.hp < hp
```

- Поставь участников вручную, дай один кадр на стабилизацию, затем действуй.
- Хитбокс активен только в фазе `active`; ждать нужно полный `windup + active`.

### Враг

```python
def test_crawler_telegraphs(session):
    run_frames(session, 0.5)
    enemy = session.enemies[0]
    session.player.entity.x = enemy.entity.x - 40
    events = []
    session.bus.subscribe("telegraph", lambda entity, kind, duration: events.append(kind))
    run_frames(session, 1.0)
    assert "crawler_bite" in events
```

### Босс

- Для арены: перемести игрока в `spec.boss_trigger` и прогони несколько шагов.
- Для конкретного паттерна выстави `boss.pattern` в состоянии `telegraph`.
- HP/фазу меняй напрямую, но помни: `take_hit` запускает переход фазы.
- Опасности Смотрителя живут в `boss.orb_drops` / `boss.shock_zones`; после
  смерти босса они очищаются.

### Уровень

```python
def test_level_04_loads():
    spec = LevelSpec.load("src/slg/data/level_04.json")
    assert spec.name
    assert spec.player_spawn
    assert spec.platforms
```

Проверяй, что спавны стоят на платформах (см. `test_level_*.py`), а разрывы
проходимы (`test_traversal.py`, `test_well.py`).

### Редактор

- `EditorState` тестируется без pygame: загрузка, `build_spec()`, `save()`,
  round-trip `format_level`.
- `run_editor` не запускай в тестах; проверяй `EditorState` и `EditorCamera`.

## Чек-лист перед завершением

1. `.venv/bin/python -m pytest -q` — всё зелёное.
2. Новый уровень/тип врага/босса — добавлены тесты на загрузку и поведение.
3. Рендер/аудио затронуты — прогнаны `test_smoke_render.py` и `test_audio.py`.
4. Нет `import pygame` в `src/slg/core`.
5. Числа не захардкожены в логике — только `config.py`.
6. `compileall` проходит.
