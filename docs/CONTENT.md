# Добавление контента

Сначала данные, потом код. Если новую механику можно выразить JSON-уровнем и
существующими типами — код менять не нужно.

## Новый уровень

### 1. JSON

Создай `src/slg/data/level_0N.json` (или скопируй соседний и правь в редакторе).
Минимально нужны `name`, `bounds`, `player_spawn`; остальное опционально.

| Поле | Формат | Комментарий |
|---|---|---|
| `name` | строка | показывается в заголовке окна |
| `theme` | `swamp` / `glass` / `well` / `sanctum` | палитра, фон, эмбиент |
| `vertical` | bool | вертикальная камера и фон |
| `bounds` | `[left, top, width, height]` | не правый/нижний край |
| `player_spawn` | `[x, y]` | центр игрока |
| `platforms` | список | `x/y` — левый верхний угол |
| `kill_zones` | список | смерть при пересечении |
| `checkpoints` | список | `x/y` — центр, `name` уникален |
| `portals` | список | обратные врата в хаб, `x/y` — центр |
| `figure` | объект | Трёхликая в хабе и её `faces` |
| `enemies` | список | `type`: `crawler` / `spitter` / `shard` / `orb` |
| `bosses` | список | `type`: `boss` / `blade` / `prism` / `keeper` |
| `boss` | объект | legacy-одиночный босс |
| `boss_trigger` | прямоугольник | арена активируется при входе |
| `boss_gate` | прямоугольник | добавляется в платформы на время боя |

Портал возврата (`portals`):

```json
{"x": 480, "y": 92, "radius": 70, "name": "back_03", "target": "hub"}
```

- `target` — ключ уровня назначения; `E` в радиусе восстанавливает HP,
  флаконы и стамину и публикует `travel`.
- `radius` — горизонтальный радиус, как у чекпоинта.

Фигура хаба (`figure`):

```json
{
  "x": 800, "y": 620,
  "faces": [
    {"type": "turner", "x": 640, "y": 520, "target": "swamp", "requires": null},
    {"type": "warden", "x": 800, "y": 520, "target": "glass", "requires": "swamp"},
    {"type": "herald", "x": 960, "y": 520, "target": "well", "requires": "glass"}
  ]
}
```

- `requires: null` — лик доступен сразу; иначе нужен снятый уровень из
  `requires`.
- `type` выбирает подпись подсказки (`turner`/`warden`/`herald`).
- Зоны ликов слегка перекрываются при большом `radius`; порядок обработки —
  порядок в `faces`.

Платформа:

```json
{"x": 0, "y": 200, "w": 600, "h": 200, "organic": true, "sharp": false}
```

- `w`/`h` и `width`/`height` эквивалентны.
- `sharp: true` — опасны только боковые грани, верх безопасен.
- `organic` влияет только на вид террейна.

### 2. Поставь спавны на платформы

Высота сущностей (половина):

| Сущность | half_h |
|---|---:|
| игрок | 28 |
| crawler | 15 |
| spitter | 20 |
| shard | 22 |
| orb | 17 |
| keeper | 68 |
| остальные боссы | 48 |

`spawn.y = platform.top - half_h`. X — центр сущности. Проще всего расставить всё
в редакторе: `F2` сохраняет корректный JSON.

### 3. Зарегистрируй уровень

- `src/slg/main.py`: ключи в `LEVEL_KEYS`/`LEVELS` (`hub`/`swamp`/`glass`/`well`)
  и запись в `VICTORY_TEXT` по ключу. Уровни теперь ведут в хаб: подсказка
  победы общая — «E — вернуться»; финал демо живёт в хабе.
- Прогресс — `src/slg/core/progress.py`: файл `SLG_PROGRESS_PATH` или
  `~/.local/share/slg/progress.json`; `main` сохраняет его по событию
  `"victory"`. Хаб показывает финал, когда сняты все три тяготы.
- `tests/test_editor.py`: добавь имя файла в `@pytest.mark.parametrize` и в
  цикл `test_editor_opens_all_shipped_levels`.
- `tests/test_level.py`: добавь тест загрузки и, если уровень особый,
  проверку спавнов/геометрии.
- `tests/test_smoke_render.py`: при необходимости добавь константу уровня и
  прогон кадров.

### 4. Проверь

```sh
.venv/bin/python -m pytest -q
.venv/bin/slg --level N --debug
```

Особенно проверь: спавн не в текстуре, разрывы проходимы прыжком, падение в
`kill_zone` убивает, чекпоинты достижимы, арена закрывается и открывается после
победы.

## Новый враг

1. `src/slg/core/config.py`: отдельный frozen dataclass (HP, скорости,
   тайминги, урон, размер, poise) и поле в `Config`.
2. `src/slg/core/enemies.py`: класс-наследник `Enemy`; в `__init__` задай
   `entity.kind`, `hp`, `width/height`, вызови `super().__init__(..., poise...)`.
   В `update(dt, player, world)` используй `self._tick`, `_physics`,
   `_ground_ahead`, публикуй `telegraph` перед атакой.
3. `src/slg/core/session.py`: ветка в `_spawn_enemy`.
4. `src/slg/render/characters.py`: функция `draw_<kind>`.
5. `src/slg/render/renderer.py`: ветка диспетчеризации в `draw`.
6. `src/slg/editor.py`: `ENEMY_HALF_H`, `COL_ENEMY`, клавиша добавления.
7. JSON уровня: `{"type": "<kind>", "x": ..., "y": ...}`.
8. `tests/`: загрузка типа, переходы состояний, урон, смерть.
9. Если враг должен звучать — добавь событие и звук в `audio/__init__.py`.

Неуязвимые опасности (как `orb`) делай через `take_hit → False` и собственное
условие исчезновения.

## Новый босс

### Вариант A: поведение на базе `Boss`

Если достаточно `slam` / `sweep` / `volley` с другими числами:

1. `config.py`: поле `BossConfig` в `Config` (или `KeeperConfig`, если нужен
   новый набор полей).
2. `session.py`: добавь тип в `_BOSS_KINDS` и `_boss_cfg`.
3. `boss.py`: при необходимости ветка в `_pick_pattern` и эффекты в
   `_update_active`.
4. `hud.py`: `BOSS_LABELS[kind] = "ИМЯ"`.
5. `editor.py`: `BOSS_HALF_H[kind]` и клавиша.
6. JSON: `"bosses": [{"type": "<kind>", "x": ..., "y": ...}]`.
7. `characters.py`: свой силуэт или существующий fallback.

### Вариант B: собственный класс

Как `KeeperBoss`:

1. Наследуй `Boss`, переопредели `_sense_target`, `_pick_pattern`,
   `_pattern_telegraph`, `_pattern_recover`, `_update_active`.
2. Свои опасности держи в контроллере босса, а не в `Session`, чтобы респавн
   очищал арену вместе с боссом.
3. В `session._spawn_initial` выбери класс по `type`.
4. Добавь `BOSS_LABELS`, `BOSS_HALF_H`, тесты на каждый паттерн и очистку
   опасностей после смерти.

Боссы не отбрасываются от ударов; урон и stagger идут через `take_hit`.
Фаза 2 включается автоматически на `phase2_at`.

## Новая тема

1. `src/slg/render/palette.py`: новый словарь с **тем же набором ключей**, что
   у `SWAMP`, и запись в `THEMES`. Тест `test_theme.py` проверяет паритет
   ключей (пример — `sanctum`).
2. JSON уровня: `"theme": "<name>"`.
3. `renderer._bake_vignette`: при необходимости отдельная сила/оттенок
   виньетки (сейчас спецкейсы для `glass`, `well` и `sanctum`).
4. `render/background.py`: опционально `THEME_LAYERS` для своей геометрии
   слоёв; иначе используется общий `LAYERS` с ключами палитры.
5. `audio/__init__.py`: опционально `DRONE_BUILDERS` и `DRONE_VOLUME` для
   эмбиента; иначе играет общий `make_drone`.
6. `test_theme.py`: добавь проверку, что тема мутирует общий `PALETTE`.
7. Проверь smoke-рендер и звук под SDL dummy.

Палитра — живой словарь: `set_theme()` меняет его на месте. Импортируй
`PALETTE`, не делай копию.

## Баланс и тайминги

- Все числа — в `src/slg/core/config.py`.
- Для тестов:

```python
cfg = Config().with_overrides(player={"max_hp": 10})
session = Session(spec=spec, cfg=cfg)
```

- Не добавляй поля в логику «на будущее»: сначала поле в конфиг, потом
  использование.
- Не меняй числа в тестах через глобальные мутации — только `with_overrides`
  или локальные ассерты.

## Редактор: кратко

- `F1` — помощь по клавишам.
- `F2` / `Ctrl+S` — сохранить, `F5` — перечитать.
- `Shift` + ЛКМ — добавить платформу, ПКМ — удалить.
- `1/2/3/0` — crawler/spitter/shard/orb, `4` — чекпоинт.
- `5/6/9` — blade/prism/keeper, `7` — триггер, `8` — ворота, `E` — спавн.
- `N` — `organic`, `H` — `sharp`, `Delete` — удалить выбранное.

После ручной правки JSON прогони `pytest`: `format_level` и `LevelSpec`
проверяют, что файл остаётся валидным.
