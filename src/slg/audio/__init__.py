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


def make_glass_drone() -> np.ndarray:
    """Cold air over a sleeping glass sea.

    A low, consonant pad (root/fifth/octave) that slowly breathes, a soft wind
    bed, and a handful of distant glass chimes. Deliberately dark and quiet so
    it can sit under a long fight without listener fatigue.
    """
    duration = 16.0
    t = _t(duration)
    rng = np.random.default_rng(14)

    def pad(freq: float, gain: float, phase: float, drift: float) -> np.ndarray:
        inst = freq * (1.0 + drift * np.sin(2 * math.pi * 0.021 * t + phase))
        ph = 2 * math.pi * np.cumsum(inst) / SAMPLE_RATE
        swell = 0.40 + 0.60 * (0.5 + 0.5 * np.sin(2 * math.pi * 0.031 * t + phase * 2.1))
        return gain * np.sin(ph) * swell

    def chord(offset: float) -> np.ndarray:
        return (
            pad(73.42, 0.30, offset, 0.0012)        # D2
            + pad(110.00, 0.13, offset + 1.7, 0.0016)   # A2 (fifth)
            + pad(146.83, 0.08, offset + 3.1, 0.0020)   # D3 (octave)
            + pad(220.00, 0.04, offset + 4.4, 0.0026)   # A3, just a hint of air
        )

    left = chord(0.0)
    right = chord(0.7)

    # low, gusty air: no hiss, no sustained high-frequency content
    for gust_phase, into in ((0.8, "left"), (2.6, "right")):
        noise = _lowpass(rng.random(len(t)).astype(np.float32) - 0.5, 260)
        gust = 0.30 + 0.70 * (0.5 + 0.5 * np.sin(2 * math.pi * 0.013 * t + gust_phase))
        bed = (noise * gust * 0.18).astype(np.float32)
        if into == "left":
            left = left + bed
        else:
            right = right + bed

    # sparse, soft glass chimes with a long decay; none above ~2 kHz
    for start_s, tone, pan in ((3.1, 587.33, -0.35), (7.4, 880.00, 0.30),
                               (11.6, 1174.66, -0.10), (14.1, 659.25, 0.40)):
        i0 = int(SAMPLE_RATE * start_s)
        n = int(SAMPLE_RATE * 1.5)
        if i0 + n > len(t):
            break
        tt = t[:n]
        attack = np.minimum(1.0, tt / 0.025)
        env = attack * np.exp(-tt * 2.4)
        bell = (np.sin(2 * math.pi * tone * tt)
                + 0.22 * np.sin(2 * math.pi * tone * 2.01 * tt)) * env * 0.16
        left[i0:i0 + n] += bell.astype(np.float32) * (1.0 - max(0.0, pan))
        right[i0:i0 + n] += bell.astype(np.float32) * (1.0 + min(0.0, pan))

    # seamless loop: crossfade the ends
    xf = int(SAMPLE_RATE * 0.6)
    fade = np.linspace(0.0, 1.0, xf, dtype=np.float32)[:, None]
    lr = np.stack((left, right), axis=1)
    lr[:xf] = lr[:xf] * fade + lr[-xf:] * (1.0 - fade)
    return lr[: int(SAMPLE_RATE * (duration - 0.6))]


def make_well_drone() -> np.ndarray:
    """The drowned shaft: sub-bass rumble, cave air and sparse low drips.

    Everything sits below ~300 Hz so the mix stays dark and oppressive; the
    drips are resonant thumps rather than bright chimes.
    """
    duration = 16.0
    t = _t(duration)
    rng = np.random.default_rng(21)

    def pad(freq: float, gain: float, phase: float, drift: float) -> np.ndarray:
        inst = freq * (1.0 + drift * np.sin(2 * math.pi * 0.017 * t + phase))
        ph = 2 * math.pi * np.cumsum(inst) / SAMPLE_RATE
        swell = 0.45 + 0.55 * (0.5 + 0.5 * np.sin(2 * math.pi * 0.023 * t + phase * 1.7))
        return gain * np.sin(ph) * swell

    def bed(offset: float) -> np.ndarray:
        return (
            pad(36.71, 0.34, offset, 0.0009)          # D1
            + pad(55.00, 0.16, offset + 1.3, 0.0012)  # A1
            + pad(73.42, 0.08, offset + 2.7, 0.0015)  # D2
            + pad(110.0, 0.03, offset + 4.1, 0.0018)  # A2, a faint sheen
        )

    left = bed(0.0)
    right = bed(0.9)

    # Low, slow cave air.
    for gust_phase, into in ((0.7, "left"), (2.9, "right")):
        noise = _lowpass(rng.random(len(t)).astype(np.float32) - 0.5, 340)
        gust = 0.30 + 0.70 * (0.5 + 0.5 * np.sin(2 * math.pi * 0.011 * t + gust_phase))
        air = (noise * gust * 0.16).astype(np.float32)
        if into == "left":
            left = left + air
        else:
            right = right + air

    # Sparse water drips: pitch-dropping resonant thumps, never bright.
    for start_s, freq, pan in ((2.7, 220.0, -0.40), (6.4, 174.6, 0.35),
                               (10.9, 261.6, -0.15), (13.8, 196.0, 0.50)):
        i0 = int(SAMPLE_RATE * start_s)
        n = int(SAMPLE_RATE * 1.2)
        if i0 + n > len(t):
            break
        tt = t[:n]
        env = np.minimum(1.0, tt / 0.02) * np.exp(-tt * 3.2)
        inst = freq * (1.0 - 0.12 * tt / 1.2)
        ph = 2 * math.pi * np.cumsum(inst) / SAMPLE_RATE
        tone = (np.sin(ph) + 0.25 * np.sin(ph * 2.0)) * env * 0.10
        left[i0:i0 + n] += tone.astype(np.float32) * (1.0 - max(0.0, pan))
        right[i0:i0 + n] += tone.astype(np.float32) * (1.0 + min(0.0, pan))

    # seamless loop: crossfade the ends
    xf = int(SAMPLE_RATE * 0.6)
    fade = np.linspace(0.0, 1.0, xf, dtype=np.float32)[:, None]
    lr = np.stack((left, right), axis=1)
    lr[:xf] = lr[:xf] * fade + lr[-xf:] * (1.0 - fade)
    return lr[: int(SAMPLE_RATE * (duration - 0.6))]


def make_sanctum_drone() -> np.ndarray:
    """The sanctum: a still, consonant hum — candle-warm and almost silent.

    A slow pad with no percussion and nothing bright: the sound of a room that
    waits for the player to choose a burden.
    """
    duration = 16.0
    t = _t(duration)

    def pad(freq: float, gain: float, phase: float, drift: float) -> np.ndarray:
        inst = freq * (1.0 + drift * np.sin(2 * math.pi * 0.013 * t + phase))
        ph = 2 * math.pi * np.cumsum(inst) / SAMPLE_RATE
        swell = 0.45 + 0.55 * (0.5 + 0.5 * np.sin(2 * math.pi * 0.019 * t + phase * 1.3))
        return gain * np.sin(ph) * swell

    def chord(offset: float) -> np.ndarray:
        return (
            pad(65.41, 0.26, offset, 0.0008)            # C2
            + pad(98.00, 0.12, offset + 1.1, 0.0010)    # G2 (fifth)
            + pad(130.81, 0.07, offset + 2.3, 0.0013)   # C3 (octave)
            + pad(196.00, 0.035, offset + 3.4, 0.0016)  # G3, a faint sheen
        )

    left = chord(0.0)
    right = chord(0.8)

    # seamless loop: crossfade the ends
    xf = int(SAMPLE_RATE * 0.6)
    fade = np.linspace(0.0, 1.0, xf, dtype=np.float32)[:, None]
    lr = np.stack((left, right), axis=1)
    lr[:xf] = lr[:xf] * fade + lr[-xf:] * (1.0 - fade)
    return lr[: int(SAMPLE_RATE * (duration - 0.6))]


def make_travel() -> np.ndarray:
    """Soft ascending swell for stepping through a face or a return gate."""
    t = _t(1.2)
    w = np.zeros(len(t), dtype=np.float32)
    for i, f in enumerate((261.6, 392.0, 523.25)):
        start = int(SAMPLE_RATE * 0.15 * i)
        n = len(t) - start
        tone = np.sin(2 * math.pi * f * t[:n]) * np.exp(-t[:n] * 2.2) * 0.35
        w[start:] += tone.astype(np.float32)
    return w * _env(len(t), 0.02, 0.5)


def make_tink() -> np.ndarray:
    """Short glass chime for a cut from a sharp edge."""
    t = _t(0.35)
    f = 2400.0
    w = (np.sin(2 * math.pi * f * t)
         + 0.5 * np.sin(2 * math.pi * f * 2.76 * t)) * np.exp(-t * 16.0)
    return w * _env(len(t), 0.001, 0.1)


DRONE_BUILDERS = {"swamp": make_drone, "glass": make_glass_drone,
                  "well": make_well_drone, "sanctum": make_sanctum_drone}
DRONE_VOLUME = {"swamp": 0.30, "glass": 0.12, "well": 0.16, "sanctum": 0.14}


# -------------------------------------------------------------------- system


class AudioSystem:
    """Builds all sounds up front; plays them in response to core events."""

    def __init__(self, bus: EventBus, theme: str = "swamp") -> None:
        self.enabled = False
        self.theme = theme
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
            except pygame.error:
                return
        try:
            self._build()
        except Exception:
            return
        self.enabled = True
        self.ambient_enabled = True
        self._drone_volume = DRONE_VOLUME.get(self.theme, 0.20)
        self._subscribe(bus)
        self._drone_channel = pygame.mixer.Channel(0)
        if "drone" in self.sounds:
            self._drone_channel.play(self.sounds["drone"], loops=-1, fade_ms=2000)
        self._drone_channel.set_volume(self._drone_volume)

    def _build(self) -> None:
        builders = {
            "drone": DRONE_BUILDERS.get(self.theme, make_drone),
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
            "travel": make_travel,
            "tink": make_tink,
        }
        for name, fn in builders.items():
            self.sounds[name] = pygame.sndarray.make_sound(_stereo(fn()))

    def set_ambient(self, enabled: bool) -> None:
        """Turn the looping drone on/off without touching the effects."""
        self.ambient_enabled = enabled
        if not self.enabled:
            return
        self._drone_channel.set_volume(self._drone_volume if enabled else 0.0)

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
        bus.subscribe("sharp_hit", lambda entity, x, y: self._play("tink", 0.7))
        bus.subscribe("orb_shattered", lambda x, y: self._play("tink", 0.6))
        bus.subscribe("roll", lambda entity: self._play("roll", 0.5))
        bus.subscribe("jump", lambda entity: self._play("jump", 0.35))
        bus.subscribe("heal", lambda entity, amount: self._play("heal", 0.7))
        bus.subscribe("entity_died", self._on_entity_died)
        bus.subscribe("checkpoint", lambda checkpoint: self._play("checkpoint", 0.8))
        bus.subscribe("boss_activated", lambda: self._play("roar", 1.0))
        bus.subscribe("boss_phase", lambda phase: self._play("roar", 0.9))
        bus.subscribe("victory", lambda: self._play("victory", 0.9))
        bus.subscribe("travel", lambda target: self._play("travel", 0.8))

    def _on_entity_died(self, entity) -> None:
        if entity.kind == "player":
            self._play("death", 1.0)
        elif entity.kind in ("boss", "blade", "prism", "keeper"):
            self._play("roar", 1.0)
            self._play("death", 0.8)
