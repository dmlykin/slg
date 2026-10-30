"""Shared pytest fixtures: a tiny hand-built level + session factory."""

from __future__ import annotations

import pytest

from slg.core.config import Config
from slg.core.level import LevelSpec
from slg.core.session import Session


def make_spec(**overrides) -> LevelSpec:
    data = {
        "name": "test",
        "bounds": [0, -400, 2000, 1000],
        "player_spawn": [100, 100],
        "platforms": [
            {"x": 0, "y": 200, "w": 600, "h": 200},
            {"x": 700, "y": 200, "w": 600, "h": 200},
        ],
        "kill_zones": [{"x": 0, "y": 800, "w": 2000, "h": 300}],
        "checkpoints": [{"x": 900, "y": 200, "radius": 80, "name": "cp1"}],
        "enemies": [
            {"type": "crawler", "x": 400, "y": 185},
            {"type": "spitter", "x": 1000, "y": 180},
        ],
        "boss": {"x": 1600, "y": 140},
        "boss_trigger": {"x": 1250, "y": 60, "width": 60, "height": 140, "name": "arena"},
        "boss_gate": {"x": 1240, "y": -50, "width": 30, "height": 250},
    }
    data.update(overrides)
    return LevelSpec.from_dict(data)


@pytest.fixture
def spec() -> LevelSpec:
    return make_spec()


@pytest.fixture
def session(spec) -> Session:
    return Session(spec=spec)


@pytest.fixture
def cfg() -> Config:
    return Config()


def run_frames(session: Session, seconds: float, intents=None):
    """Advance the sim by whole fixed steps."""
    from slg.core.player import InputIntents

    dt = session.cfg.physics.fixed_dt
    intents = intents or InputIntents()
    steps = int(round(seconds / dt))
    for _ in range(steps):
        session.update(dt, intents)
    return intents
