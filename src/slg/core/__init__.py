"""Core simulation package. MUST NOT import pygame — tested headless."""

from slg.core.config import Config
from slg.core.events import EventBus
from slg.core.world import Entity, World

__all__ = ["Config", "EventBus", "Entity", "World"]
