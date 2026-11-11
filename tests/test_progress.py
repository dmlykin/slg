"""Progress persistence: round-trip, idempotence, env path, broken file."""

from __future__ import annotations

import json

from slg.core.progress import PROGRESS_ENV, Progress, default_progress_path


def test_roundtrip(tmp_path):
    path = tmp_path / "progress.json"
    progress = Progress().mark_defeated("swamp").mark_defeated("glass")
    progress.save(path)
    loaded = Progress.load(path)
    assert loaded == progress
    assert loaded.is_defeated("swamp")
    assert loaded.is_defeated("glass")
    assert not loaded.is_defeated("well")


def test_mark_defeated_is_idempotent():
    once = Progress().mark_defeated("swamp")
    twice = once.mark_defeated("swamp")
    assert once is twice
    assert once.defeated == {"swamp"}
    assert twice == once


def test_missing_file_is_empty_progress(tmp_path):
    assert Progress.load(tmp_path / "nope.json") == Progress()


def test_broken_file_is_empty_progress(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text("{ this is not json", encoding="utf-8")
    assert Progress.load(path) == Progress()
    path.write_text(json.dumps({"defeated": "swamp"}), encoding="utf-8")
    assert Progress.load(path) == Progress()
    path.write_text(json.dumps({"other": 1}), encoding="utf-8")
    assert Progress.load(path) == Progress()


def test_env_path_override(tmp_path, monkeypatch):
    path = tmp_path / "custom" / "progress.json"
    monkeypatch.setenv(PROGRESS_ENV, str(path))
    assert default_progress_path() == path
    Progress().mark_defeated("well").save()
    assert path.exists()
    assert Progress.load() == Progress().mark_defeated("well")


def test_to_dict_is_sorted_and_from_dict_tolerant():
    progress = Progress.from_dict({"defeated": ["well", "swamp", 42]})
    assert progress.defeated == {"well", "swamp"}
    assert progress.to_dict() == {"defeated": ["swamp", "well"], "substance": 0.0,
                                  "deposited": 0.0}
    assert Progress.from_dict({"defeated": [], "substance": 5.0}).deposited == 0.0
    assert Progress.from_dict({"deposited": "много"}).deposited == 0.0
