# Архитектура

Документ описывает, как устроен движок и где менять код. Правила, которые
нельзя нарушать, кратко перечислены в `AGENTS.md`.

## Принципы

1. **Core headless.** `src/slg/core/*` — чистая симуляция без `pygame`. Любая
   механика должна воспроизводиться в pytest без окна и звука.
2. **Render/audio только читают.** `src/slg/render/*` и `src/slg/audio` получают
   `Session`/`World`, рисуют или проигрывают звук и подписываются на события.
   Они не меняют состояние игры.
3. **Связь через события.** Core публикует факты в `EventBus`; рендер и аудио
   реагируют. Core не импортирует render/audio.
4. **Баланс в конфиге.** Все числа, тайминги, урон и размеры — в
   `src/slg/core/config.py`. В тестах используй `Config().with_overrides(...)`.
5. **Детерминизм.** Один шаг — `session.update(fixed_dt, intents)`, где
   `fixed_dt = 1/60`. Никакого реального времени в ядре.

## Слои и поток кадра

```
pygame (main.py)
  │  события клавиш -> InputIntents
  ▼
Session.update(fixed_dt, intents)          core, headless
  ├─ Player.update
  ├─ Enemy.update (crawler / spitter / shard / orb)
  ├─ Boss.update (boss / blade / prism / keeper)
  ├─ projectiles, sharp edges, kill zones
  └─ EventBus.publish(...)
        │
        ├─ Renderer (частицы, HUD, оверлеи)
        └─ AudioSystem (процедурные звуки)

Renderer.draw(surface)                     render, read-only
  ├─ Background -> Terrain -> checkpoints
  ├─ enemies -> bosses -> projectiles -> player
  ├─ Particles
  └─ HUD (полоски, подсказки, смерть, победа, пауза)
```

### Главный цикл (`src/slg/main.py`)

- `pygame` накапливает время; симуляция идёт целыми шагами `1/60`, рендер —
  каждый кадр.
- Одноразовые нажатия (`jump_pressed`, `attack…`) сбрасываются после первого
  фиксированного шага через `_consume_one_shots`.
- `Esc` — пауза, `M` — эмбиент, `E` — переход после победы.
- `--debug` включает `PageUp/PageDown`; `--edit` уходит в редактор.
- После победы `Session.update` ничего не делает, но рендер продолжается.

### Порядок `Session.update` (`src/slg/core/session.py`)

1. `world.step_time(dt)`.
2. Если игрок мёртв — тикает `death_timer`, через `DEATH_RESPAWN_DELAY = 1.6`
   вызывается `respawn_everything()`, обновляются снаряды, выход.
3. Единый обработчик `E` (`_check_interactions`), строгий приоритет на одно
   нажатие: финал хаба → портал → лик фигуры → чекпоинт; затем `boss_trigger`.
4. `player.update`.
5. Урон от острых граней (`touching_sharp_side`).
6. Враги; упавшие ниже `bounds` помечаются мёртвыми.
7. Боссы (только живые).
8. Удары игрока по врагам и боссам.
9. Снаряды: гравитация, платформы, попадание в игрока.
10. `kill_zones`.
11. Если все боссы мертвы — `boss_defeated`, победа, ворота открываются.

## Координаты и геометрия

| Объект | Где `x/y` |
|---|---|
| `Entity` | центр AABB; `width/height` — полный размер |
| `Platform` | левый верхний угол |
| `KillZone`, `Trigger` | левый верхний угол |
| `Checkpoint`, спавны игрока, врагов и боссов | центр |
| `Portal`, `FaceSpawn`, `Figure` | центр |
| `World.bounds` | `(left, top, width, height)` |

- `Entity.left/right/top/bottom` — края AABB; `aabb()` возвращает
  `(left, top, width, height)`.
- `z` зарезервирован под будущий top-down: всегда `0`, но есть у каждой
  сущности.
- Гравитация и коллизии — `slg/core/physics.py`: сначала горизонталь, затем
  вертикаль, каждая ось разрешается отдельно.
- `SHARP_SIDE_WIDTH`/`SHARP_SIDE_INSET` задают опасную полосу только на
  боковых гранях платформы с `sharp: true`; верх остаётся безопасным.

## Уровни

`slg/core/level.py` превращает JSON в `LevelSpec`. Ключи `w`/`h`
нормализуются в `width`/`height` (можно писать оба варианта).

```json
{
  "name": "Немой колодец",
  "theme": "well",
  "vertical": true,
  "bounds": [0, -300, 2000, 5350],
  "player_spawn": [300, 90],
  "platforms": [{"x": 0, "y": 120, "w": 950, "h": 120, "organic": true, "sharp": false}],
  "kill_zones": [{"x": 950, "y": 4200, "w": 100, "h": 150}],
  "checkpoints": [{"x": 300, "y": 1080, "radius": 80, "name": "well_01"}],
  "portals": [{"x": 480, "y": 92, "radius": 70, "name": "back_03", "target": "hub"}],
  "enemies": [{"type": "crawler", "x": 1500, "y": 635}],
  "bosses": [{"type": "keeper", "x": 1000, "y": 4582}],
  "boss_trigger": {"x": 0, "y": 4300, "w": 2000, "h": 350, "name": "arena"},
  "boss_gate": {"x": 0, "y": 4200, "w": 2000, "h": 40}
}
```

- `theme`: `swamp` | `glass` | `well` | `sanctum`.
- `vertical`: включает вертикальную камеру и фон.
- `portals`: обратные врата в хаб (`target` — ключ уровня) у старта уровней.
- `figure`: Трёхликая в хабе; `faces` — зоны взаимодействия с `target` и
  необязательным `requires` (ключ уровня, который надо снять первым).
- `boss` (legacy, один) и `bosses` (список) поддерживаются одновременно.
- Допустимые типы боссов: `boss`, `blade`, `prism`, `keeper`
  (`_BOSS_KINDS` в `session.py`).
- `boss_gate` добавляется в `world.platforms` при активации арены и снимается
  при победе или респавне.
- Уровни зарегистрированы в `main.LEVEL_KEYS`/`main.LEVELS` (ключи
  `hub`/`swamp`/`glass`/`well`); тексты победы — в `VICTORY_TEXT`.

## Хаб, прогресс и финал

- `level_00.json` — хаб «Снятие Тягот» (`theme: sanctum`), старт игры по
  умолчанию (`--level 0`). Опасностей, врагов и боссов нет.
- В центре — `Figure` с тремя `FaceSpawn` (слева/центр/справа). У лика есть
  `target` (ключ уровня) и `requires` (какой уровень нужно снять раньше).
  `Session.face_state(face)` возвращает `"available"` или `"locked"`.
- Один обработчик `E` в `Session._check_interactions`:
  1. если `hub_finale` и оверлей ещё не закрыт — `finale_dismissed = True`;
  2. портал в радиусе → восстановить HP/флаконы/стамину и
     `publish("travel", target=...)`;
  3. доступный лик в радиусе → `publish("travel", target=...)`; запертый —
     ничего;
  4. иначе — чекпоинт (прежняя логика).
  Поэтому одно нажатие всегда делает не больше одного действия.
- `Session.hub_finale` — истина, когда все `face.target` уже в прогрессе.
  Финал показывает тот же `victory_overlay`; хаб при этом остаётся играбельным
  (победа `victory` тут не выставляется и симуляцию не морозит).
- `Progress` (`core/progress.py`) — frozenset снятых тягот и JSON-IO:
  `SLG_PROGRESS_PATH` → иначе `~/.local/share/slg/progress.json`, запись
  атомарная (tmp + `os.replace`), битый файл читается как пустой.
- `main.py`: `Progress.load()` на старте, подписка на `"victory"` помечает
  текущий ключ и сохраняет; после победы `E` ведёт в хаб. Уровни при повторном
  входе создают врагов и боссов заново.
- `load_level` создаёт новый `Session` со своим `EventBus`, поэтому
  подписки на `"travel"`/`"victory"` делаются после каждой смены уровня.

## Сущности и контроллеры

`Entity` (`world.py`) — только данные: id, позиция, скорость, размер, HP,
facing, состояние на земле. Поведение живёт в контроллерах:

- `Player` — FSM игрока.
- `Crawler`, `Spitter`, `Shard`, `Orb` — враги.
- `Boss`, `KeeperBoss` — боссы.
- `Projectile` — снаряд (данные + AABB).

`World` хранит `entities`, `platforms`, `kill_zones`, `checkpoints`, `time`,
`bounds` и выдаёт id через `spawn()`.

### Игрок

Состояния: `idle`, `run`, `jump`, `roll`, `attack_l`, `attack_h`, `heal`,
`hurt`, `dead`.

- Приоритет действий в `_update_free`: перекат → лечение → быстрый удар →
  тяжёлый удар → прыжок.
- Прыжок с coyote time; отпускание `Space` режет высоту
  (`jump_cut_multiplier`).
- Перекат даёт i-frames в окне `iframes_start..iframes_end`.
- `take_hit` прерывает действие, включает `hurt` и i-frames; при 0 HP — `dead`.
- Шум для Смотрителя: бег, перекат, атаки и взлёт делают игрока слышимым;
  стоять, лечиться и падать без ввода — тихо (`_is_noisy`).
- `respawn_at` сбрасывает ресурсы, шум и состояние.

### Враги

Общая база `Enemy`: HP, `Poise`, i-frames, гравитация, проверка пола впереди
(`_ground_ahead`), чтобы не падать с уступов.

| Враг | Поведение |
|---|---|
| `crawler` | `patrol → aggro → telegraph → strike → recover`; ближний укус |
| `spitter` | держит дистанцию `keep_min..keep_max`, телеграф, lob-снаряд |
| `shard` | `dormant → telegraph → lunge → recover`; рывок сквозь игрока без гравитации |
| `orb` | неуязвимый шар молний: `float` над уступом, преследует, при потере опоры падает; на арене разбивается |

- `Orb.take_hit` всегда `False` — его нельзя убить, только увести.
- Враги публикуют `telegraph` перед атакой; рендер и аудио реагируют.
- `Projectile` живёт в `Session.projectiles`, спавнится через событие
  `projectile_spawned`.

### Боссы

`Boss` (`boss.py`) — общий цикл: `dormant → roar → idle → telegraph → active
→ recover`, плюс `stagger` и `dead`.

- `take_hit` не отбрасывает босса; poise заполняется — босс staggers.
- На `phase2_at` доле HP — `roar`, вторая фаза: скорость и телеграфы меняются
  множителями.
- Паттерны: `slam`, `sweep`, `volley`. `_pick_pattern` зависит от `kind` и
  дистанции; `keep_min/keep_max` задают ranged-дистанцию (близнец `prism`).
- `enrage()` — если один из близнецов погиб, второй сразу уходит во вторую фазу
  (`Session._on_entity_died`).
- `_sense_target(player)` — точка прицеливания; Смотритель переопределяет её.

`KeeperBoss` (`keeper.py`) — Слепой смотритель:

- Слышит последнюю шумную точку в пределах `hearing_memory`, цель фиксируется
  на телеграф, чтобы от шума можно было уйти.
- Тишина → `silent`: босс прощупывает арену, чередуя `echo_wave` и
  `call_orbs`.
- Паттерны: `lantern_slam` (круг по услышанной точке), `echo_wave` (кольцо по
  земле), `call_orbs` (падающие молнии + короткие электрические зоны).
- Опасности (`OrbDrop`, `ShockZone`) принадлежат боссу; респавн создаёт босса
  заново и очищает арену.

## Бой

`slg/core/combat.py`:

- `Stamina` — трата и регенерация с задержкой.
- `AttackState` — фазы `windup → active → recovery`; хитбокс только в
  `active`.
- `hitbox` строится от центра сущности вперёд по `facing` на `reach` и
  `height` из `AttackConfig`.
- `Poise` — накопление stagger-урона; заполнение даёт stagger на
  `stagger_time`.
- `Damageable` — HP и i-frames; `try_take_hit` применяет урон и отбрасывание.
- `Session._swing_hits` не даёт одному замаху ударить цель дважды.

## События

Канонический список — в `slg/core/events.py`:

| Событие | Payload |
|---|---|
| `player_damaged` | `amount, source` |
| `entity_damaged` | `entity, amount, source` |
| `entity_died` | `entity` |
| `telegraph` | `entity, kind, duration` |
| `sharp_hit` | `entity, x, y` |
| `orb_shattered` | `x, y` |
| `attack_hit` | `attacker, victim, x, y, damage, heavy` |
| `attack_missed` | `attacker, x, y` |
| `roll`, `jump` | `entity` |
| `heal` | `entity, amount` |
| `checkpoint` | `checkpoint` |
| `respawn` | — |
| `boss_activated` | — |
| `boss_phase` | `phase` |
| `victory` | — |
| `projectile_spawned` | `projectile` |
| `travel` | `target` |

Добавляя событие, обнови комментарий в `events.py` и подписчиков в
`renderer.py` / `audio/__init__.py`.

## Рендер

`Renderer` (`render/renderer.py`) собирает кадр:

1. `set_theme(spec.theme)` до запекания фона и виньетки.
2. `SideProjection` — камера; для `vertical` уровней `vertical_bias=100`,
   иначе `-60`.
3. `Background` (процедурные слои), `TerrainRenderer` (платформы).
4. Чекпоинты → порталы → фигура хаба → враги → боссы → снаряды → шумовые
   кольца → игрок.
5. `Particles`, виньетка, HUD, оверлеи смерти/победы/финала/паузы.

- Портал и фигура рисуются из `spec` (без `Entity`), как чекпоинты.
  `draw_figure` подсвечивает доступные лики по `Session.face_state`.
- Подсказка взаимодействия одна: `Hud.interact_prompt`; текст выбирает
  `Renderer._prompt_text` по тому же приоритету, что и core.
- Оверлей финала показывается, пока `session.hub_finale and not
  session.finale_dismissed`.

- Камера следует за игроком с look-ahead по `facing` и вертикальным сдвигом по
  `vy`; `parallax_offset`/`parallax_offset_y` — для фона.
- `Projection` — протокол; `SideProjection` реализован, `TopDownProjection` —
  заглушка на будущее.
- Персонажи рисуются функциями из `render/characters.py`; диспетчеризация по
  `entity.kind` — в `draw()`.
- HUD-подписи боссов — `BOSS_LABELS` в `render/hud.py`.
- Тема — живой словарь `PALETTE`: `set_theme()` мутирует его на месте, поэтому
  модули должны импортировать сам `PALETTE`, а не копию.

## Аудио

`slg/audio/__init__.py` синтезирует звуки numpy-волнами и отдаёт их в
`pygame.sndarray`. Файлов нет. Без аудиоустройства система деградирует в
тишину. `AudioSystem` подписывается на `EventBus`, тема влияет на эмбиент
(`DRONE_BUILDERS`/`DRONE_VOLUME`, включая `sanctum`); переход — короткий звук
по событию `"travel"`.

## Редактор

`src/slg/editor.py` разделён на:

- `EditorState` — чистые данные: загрузка/сохранение JSON, добавление,
  удаление, перемещение, `build_spec()`.
- `EditorCamera` — панорама и world↔screen.
- `run_editor(path)` — pygame-цикл, ввод, отрисовка.

Форматирование сохранения (`format_level`) сохраняет порядок ключей и
человекочитаемые отступы; тесты проверяют round-trip всех уровней.

## Инварианты и ловушки

- Никогда не импортируй `pygame` в `core`.
- Не хардкодь урон/тайминги в логике — только `config.py`.
- Не меняй `PALETTE` копированием; импортируй живой словарь.
- Новый тип врага затрагивает: `Config`, класс в `enemies.py`,
  `Session._spawn_enemy`, `Renderer.draw`, `editor.ENEMY_HALF_H`/`COL_ENEMY`,
  функцию в `characters.py`.
- Новый тип босса затрагивает: `Config`, `Session._BOSS_KINDS` и `_boss_cfg`,
  `hud.BOSS_LABELS`, `editor.BOSS_HALF_H`, при необходимости — `characters.py`.
- Новый уровень затрагивает: JSON, `main.LEVEL_KEYS`/`LEVELS`, `VICTORY_TEXT`,
  тесты, параметризацию `tests/test_editor.py`.
- Новая тема затрагивает: `palette.THEMES` (паритет ключей), при желании
  `background.THEME_LAYERS`, `renderer._bake_vignette` и `audio.DRONE_*`.
- Прогресс хаба — `Progress`; не мутируй его на месте, `mark_defeated`
  возвращает новый объект, который нужно сохранить и передать в следующий
  `Session`.
- `respawn_everything()` пересоздаёт врагов и боссов, очищает снаряды и
  снимает ворота.
- Победа фиксируется, когда все боссы мертвы; симуляция после этого стоит.
- Одноразовые вводы сбрасываются после первого фиксированного шага — не
  рассчитывай, что `pressed` проживёт несколько шагов.
