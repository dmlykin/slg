"""Procedural audio: numpy waveforms -> pygame.sndarray. No audio files.

Gracefully degrades to silence when no audio device is available.
"""

from __future__ import annotations

import math

import numpy as np
import pygame

from slg.core.events import EventBus

SAMPLE_RATE = 22050


def _stereo(samples: np.ndarray) -> np.ndarray:
    """Mono float array -> stereo int16 array for pygame.sndarray."""
    if samples.ndim == 1:
        samples = np.stack((samples, samples), axis=1)
    peak = float(np.max(np.abs(samples))) or 1.0
    scaled = samples / peak * 0.85
    return (scaled * 32767.0).astype(np.int16)


def _t(duration: float) -> np.ndarray:
    return np.arange(int(SAMPLE_RATE * duration), dtype=np.float32) / SAMPLE_RATE


def _env(n: int, attack: float = 0.01, release: float = 0.4) -> np.ndarray:
    """Attack-decay envelope."""
    t = np.ones(n, dtype=np.float32)
    a = max(1, int(SAMPLE_RATE * attack))
    r = max(1, int(SAMPLE_RATE * release))
    if a < n:
        t[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
    if r < n:
        t[-r:] *= np.linspace(1.0, 0.0, r, dtype=np.float32)
    return t


def _lowpass(x: np.ndarray, strength: int = 40) -> np.ndarray:
    kernel = np.ones(strength, dtype=np.float32) / strength
    return np.convolve(x, kernel, mode="same")


# -------------------------------------------------------------------- sounds

def make_drone() -> np.ndarray:
    """Looping ambient hum of a dying world: detuned lows + breathing noise."""
    duration = 8.0
    t = _t(duration)
    rng = np.random.default_rng(11)
    w = (
        0.40 * np.sin(2 * math.pi * 55 * t)
        + 0.30 * np.sin(2 * math.pi * 55.7 * t)
        + 0.22 * np.sin(2 * math.pi * 82.2 * t)
        + 0.12 * np.sin(2 * math.pi * 110.5 * t)
    )
    lfo = 0.5 + 0.5 * np.sin(2 * math.pi * 0.125 * t)
    noise = _lowpass(rng.random(len(t)).astype(np.float32) - 0.5, 220) * 0.5
    w = w * (0.6 + 0.4 * lfo) + noise * (0.35 + 0.3 * lfo)
    # seamless loop: crossfade the ends
    xf = int(SAMPLE_RATE * 0.5)
    fade = np.linspace(0.0, 1.0, xf, dtype=np.float32)
    w[:xf] = w[:xf] * fade + w[-xf:] * (1 - fade)
    return w[: int(SAMPLE_RATE * (duration - 0.5))]


def make_hit(heavy: bool) -> np.ndarray:
    rng = np.random.default_rng()
    if heavy:
        t = _t(0.5)
        body = np.sin(2 * math.pi * 60 * t) * np.exp(-t * 9)
        crunch = _lowpass(rng.random(len(t)).astype(np.float32) - 0.5, 8) * np.exp(-t * 16)
        w = body * 1.2 + crunch * 0.9
    else:
        t = _t(0.24)
        body = np.sin(2 * math.pi * 140 * t) * np.exp(-t * 22)
        crunch = _lowpass(rng.random(len(t)).astype(np.float32) - 0.5, 6) * np.exp(-t * 28)
        w = body + crunch * 0.7
    return w * _env(len(t), 0.002, 0.3)


def make_telegraph() -> np.ndarray:
    """Rising warning tone — must read as 'it's about to hit you'."""
    t = _t(0.45)
    freq = 220 + 480 * (t / 0.45) ** 1.6
    phase = 2 * math.pi * np.cumsum(freq) / SAMPLE_RATE
    w = np.sin(phase) * 0.7 + np.sin(phase * 2) * 0.2
    return w * _env(len(t), 0.01, 0.12)


def make_roll() -> np.ndarray:
    t = _t(0.3)
    rng = np.random.default_rng(3)
    noise = rng.random(len(t)).astype(np.float32) - 0.5
    sweep = _lowpass(noise, 30) * np.exp(-t * 7)
    whoosh = sweep * (0.5 + 0.5 * np.sin(2 * math.pi * 6 * t))
    return whoosh * _env(len(t), 0.02, 0.15)


def make_jump() -> np.ndarray:
    t = _t(0.18)
    freq = 180 + 160 * t / 0.18
    phase = 2 * math.pi * np.cumsum(freq) / SAMPLE_RATE
    return (np.sin(phase) * 0.5) * _env(len(t), 0.005, 0.1)


def make_heal() -> np.ndarray:
    """Soft ascending chime."""
    t = _t(0.7)
    w = np.zeros(len(t), dtype=np.float32)
    for i, f in enumerate((392.0, 523.25, 659.25)):
        start = int(SAMPLE_RATE * 0.12 * i)
        n = len(t) - start
        tone = np.sin(2 * math.pi * f * t[:n]) * np.exp(-t[:n] * 3.5) * 0.4
        w[start:] += tone.astype(np.float32)
    return w * _env(len(t), 0.01, 0.3)


def make_death() -> np.ndarray:
    t = _t(1.4)
    freq = 200 * np.exp(-t * 1.2) + 40
    phase = 2 * math.pi * np.cumsum(freq) / SAMPLE_RATE
    w = np.sin(phase) * 0.8 + np.sin(phase * 0.5) * 0.3
    return w * _env(len(t), 0.01, 0.7)


def make_checkpoint() -> np.ndarray:
    t = _t(0.9)
    w = (
        np.sin(2 * math.pi * 261.6 * t) * np.exp(-t * 2.5) * 0.4
        + np.sin(2 * math.pi * 392.0 * t) * np.exp(-t * 2.0) * 0.3
        + np.sin(2 * math.pi * 523.2 * t) * np.exp(-t * 1.6) * 0.25
    )
    return w * _env(len(t), 0.01, 0.4)


def make_roar() -> np.ndarray:
    t = _t(1.3)
    saw = 2.0 * ((55 * t) % 1.0) - 1.0
    rng = np.random.default_rng(5)
    growl = _lowpass(rng.random(len(t)).astype(np.float32) - 0.5, 60)
    w = (saw * 0.6 + growl * 0.8) * (0.4 + 0.6 * np.sin(math.pi * t / 1.3))
    return w * _env(len(t), 0.05, 0.5)


def make_victory() -> np.ndarray:
    t = _t(2.2)
    w = np.zeros(len(t), dtype=np.float32)
    for i, f in enumerate((261.6, 329.6, 392.0, 523.2)):
        start = int(SAMPLE_RATE * 0.3 * i)
        n = len(t) - start
        tone = np.sin(2 * math.pi * f * t[:n]) * np.exp(-t[:n] * 1.2) * 0.3
        w[start:] += tone.astype(np.float32)
    return w * _env(len(t), 0.02, 0.8)


# -------------------------------------------------------------------- system


class AudioSystem:
    """Builds all sounds up front; plays them in response to core events."""

    def __init__(self, bus: EventBus) -> None:
        self.enabled = False
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        try:
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
        except pygame.error:
            return
        try:
            self._build()
        except Exception:
            return
        self.enabled = True
        self._subscribe(bus)
        self._drone_channel = pygame.mixer.Channel(0)
        if "drone" in self.sounds:
            self._drone_channel.play(self.sounds["drone"], loops=-1, fade_ms=2000)
        self._drone_channel.set_volume(0.35)

    def _build(self) -> None:
        builders = {
            "drone": make_drone,
            "hit_light": lambda: make_hit(False),
            "hit_heavy": lambda: make_hit(True),
            "telegraph": make_telegraph,
            "roll": make_roll,
            "jump": make_jump,
            "heal": make_heal,
            "death": make_death,
            "checkpoint": make_checkpoint,
            "roar": make_roar,
            "victory": make_victory,
        }
        for name, fn in builders.items():
            self.sounds[name] = pygame.sndarray.make_sound(_stereo(fn()))

    def _play(self, name: str, volume: float = 1.0) -> None:
        if not self.enabled:
            return
        snd = self.sounds.get(name)
        if snd is not None:
            ch = pygame.mixer.find_channel(True)
            if ch is not None:
                ch.set_volume(volume)
                ch.play(snd)

    def _subscribe(self, bus: EventBus) -> None:
        bus.subscribe("attack_hit", lambda attacker, victim, x, y, damage, heavy:
                      self._play("hit_heavy" if heavy else "hit_light", 0.9))
        bus.subscribe("telegraph", lambda entity, kind, duration:
                      self._play("telegraph", 0.55))
        bus.subscribe("roll", lambda entity: self._play("roll", 0.5))
        bus.subscribe("jump", lambda entity: self._play("jump", 0.35))
        bus.subscribe("heal", lambda entity, amount: self._play("heal", 0.7))
        bus.subscribe("entity_died", self._on_entity_died)
        bus.subscribe("checkpoint", lambda checkpoint: self._play("checkpoint", 0.8))
        bus.subscribe("boss_activated", lambda: self._play("roar", 1.0))
        bus.subscribe("boss_phase", lambda phase: self._play("roar", 0.9))
        bus.subscribe("victory", lambda: self._play("victory", 0.9))

    def _on_entity_died(self, entity) -> None:
        if entity.kind == "player":
            self._play("death", 1.0)
        elif entity.kind == "boss":
            self._play("roar", 1.0)
            self._play("death", 0.8)
