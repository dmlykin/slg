"""Event bus. The core publishes events; render/audio subscribe and react.

The core never calls render or audio directly.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

EventHandler = Callable[..., None]

# Canonical event names emitted by the core:
#   "player_damaged"      (amount, source)
#   "entity_damaged"      (entity, amount, source)
#   "entity_died"         (entity)
#   "telegraph"           (entity, kind, duration)
#   "attack_hit"          (attacker, victim, x, y)
#   "attack_missed"       (attacker, x, y)
#   "roll"                (entity)
#   "jump"                (entity)
#   "heal"                (entity, amount)
#   "checkpoint"          (checkpoint)
#   "respawn"             ()
#   "boss_activated"      ()
#   "boss_phase"          (phase)
#   "victory"             ()
#   "projectile_spawned"  (projectile)


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event: str, handler: EventHandler) -> None:
        self._handlers[event].append(handler)

    def publish(self, event: str, **payload) -> None:
        for handler in self._handlers[event]:
            handler(**payload)
