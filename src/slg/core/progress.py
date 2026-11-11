"""Player progress: the set of lifted burdens, persisted across restarts.

Headless data + JSON file IO, no pygame. main.py loads it on start, marks a
level defeated on "victory" and saves; the hub Session reads it to decide
which faces of the Three-Faced figure are awake.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

PROGRESS_ENV = "SLG_PROGRESS_PATH"


def default_progress_path() -> Path:
    """Progress file location: $SLG_PROGRESS_PATH overrides the default."""
    override = os.environ.get(PROGRESS_ENV)
    if override:
        return Path(override)
    return Path.home() / ".local" / "share" / "slg" / "progress.json"


@dataclass(frozen=True)
class Progress:
    """Defeated level keys ("swamp" / "glass" / "well") + carried substance.

    `deposited` is the substance relieved at the hub figure: it grows
    monotonically and is never given back.
    """

    defeated: frozenset[str] = field(default_factory=frozenset)
    substance: float = 0.0
    deposited: float = 0.0

    def is_defeated(self, key: str) -> bool:
        return key in self.defeated

    def mark_defeated(self, key: str) -> "Progress":
        """Idempotently add a defeated key; returns the new Progress."""
        if key in self.defeated:
            return self
        return Progress(self.defeated | {key}, self.substance, self.deposited)

    def with_substance(self, amount: float) -> "Progress":
        """Return a copy carrying the given substance (clamped >= 0)."""
        return Progress(self.defeated, max(0.0, amount), self.deposited)

    def with_deposit(self, amount: float) -> "Progress":
        """Return a copy with the relieved amount added to the deposit."""
        return Progress(self.defeated, self.substance,
                        self.deposited + max(0.0, amount))

    def to_dict(self) -> dict:
        return {"defeated": sorted(self.defeated), "substance": self.substance,
                "deposited": self.deposited}

    @staticmethod
    def from_dict(data: dict) -> "Progress":
        raw = data.get("defeated") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            raw = []
        substance = data.get("substance", 0.0) if isinstance(data, dict) else 0.0
        if isinstance(substance, bool) or not isinstance(substance, (int, float)):
            substance = 0.0
        deposited = data.get("deposited", 0.0) if isinstance(data, dict) else 0.0
        if isinstance(deposited, bool) or not isinstance(deposited, (int, float)):
            deposited = 0.0
        return Progress(frozenset(k for k in raw if isinstance(k, str)),
                        float(substance), float(deposited))

    @staticmethod
    def load(path: str | Path | None = None) -> "Progress":
        """Read progress; a missing or damaged file means empty progress."""
        path = Path(path) if path is not None else default_progress_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return Progress()
        return Progress.from_dict(data)

    def save(self, path: str | Path | None = None) -> None:
        """Write progress atomically (tmp file + os.replace)."""
        path = Path(path) if path is not None else default_progress_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, path)
