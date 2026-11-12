"""Tests for the device-independent, comment-insensitive cache key and its migration."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from stickler import adapters, cachemigration, runner

FIXTURES = Path(__file__).parent / "fixtures" / "adapters"


@pytest.fixture
def world(tmp_path):
    """Copied fixture adapters, a mix, and a cache with entries under the old (v1) keys."""
    root = tmp_path / "adapters"
    shutil.copytree(FIXTURES, root, ignore=shutil.ignore_patterns(".venv*", "__pycache__"))
    registry = adapters.discover(root)
    mix = tmp_path / "mix.wav"
    mix.write_bytes(b"mix-content")
    cache = tmp_path / "cache"

    def legacy_entry(spec_id, audio, env, output, payload):
        spec = registry[spec_id]
        d = cache / spec_id / cachemigration.legacy_key(spec, _sha1(audio), env)
        d.mkdir(parents=True)
        (d / output).write_bytes(payload)
        (d / "meta.json").write_text(json.dumps({"device": env.split("|")[-1]}))
        return d

    stem_dir = legacy_entry("copysep", mix, "auto", "drums.wav", b"stem-content")
    legacy_entry("dummy", stem_dir / "drums.wav", "auto", "drums.mid", b"midi-from-stem")
    legacy_entry("dummy", mix, "auto", "drums.mid", b"midi-cpu")
    legacy_entry("dummy", mix, "gpu|cuda", "drums.mid", b"midi-gpu")  # duplicate on the GPU
    orphan = cache / "dummy" / "0123456789abcdef"  # e.g. made by an older adapter version
    orphan.mkdir(parents=True)
    return {"registry": registry, "cache": cache, "mix": mix, "stem_bytes": b"stem-content"}


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def test_code_digest_ignores_comments_and_docstrings(tmp_path):
    spec_dir = tmp_path / "a"
    spec_dir.mkdir()
    spec = adapters.AdapterSpec("a", "transcribers", spec_dir)
    (spec_dir / "run.py").write_text('"""Doc."""\nX = 1  # comment\n', encoding="utf-8")
    (spec_dir / "pyproject.toml").write_text('[project]\nname = "a"  # Kommentar\n')
    before = runner.code_digest(spec)
    (spec_dir / "run.py").write_text('"""Translated doc."""\n# new comment\nX = 1\n')
    (spec_dir / "pyproject.toml").write_text('# header\n[project]\nname = "a"\n')
    assert runner.code_digest(spec) == before
    (spec_dir / "run.py").write_text("X = 2\n", encoding="utf-8")
    assert runner.code_digest(spec) != before


def test_migration_moves_entries_to_new_keys(world):
    report = cachemigration.migrate(world["cache"], world["registry"], [world["mix"]])
    reg, cache, mix = world["registry"], world["cache"], world["mix"]
    stem = runner.cache_dir_for(cache, reg["copysep"], mix) / "drums.wav"
    assert stem.read_bytes() == world["stem_bytes"]
    assert (runner.cache_dir_for(cache, reg["dummy"], stem) / "drums.mid").read_bytes() == (
        b"midi-from-stem"
    )
    # CPU result wins over the GPU duplicate; the duplicate is kept aside, not deleted
    assert (runner.cache_dir_for(cache, reg["dummy"], mix) / "drums.mid").read_bytes() == (
        b"midi-cpu"
    )
    assert report.moved == 3 and report.superseded == 1 and report.orphaned == 1
    assert len(list((cache / "_superseded" / "dummy").iterdir())) == 1
    assert (cache / "_orphaned" / "dummy" / "0123456789abcdef").is_dir()


def test_migration_is_idempotent(world):
    cachemigration.migrate(world["cache"], world["registry"], [world["mix"]])
    again = cachemigration.migrate(world["cache"], world["registry"], [world["mix"]])
    assert (again.moved, again.superseded, again.orphaned) == (0, 0, 0)
    assert again.current == 3


def test_dry_run_changes_nothing(world):
    before = sorted(p.relative_to(world["cache"]) for p in world["cache"].rglob("*"))
    report = cachemigration.migrate(world["cache"], world["registry"], [world["mix"]], dry_run=True)
    assert report.moved == 3
    assert sorted(p.relative_to(world["cache"]) for p in world["cache"].rglob("*")) == before


def test_cache_hit_after_migration_on_any_device(world, monkeypatch):
    cachemigration.migrate(world["cache"], world["registry"], [world["mix"]])

    def no_run(*a, **kw):
        raise AssertionError("must be a cache hit")

    monkeypatch.setattr(adapters, "run_adapter", no_run)
    for device in ("cpu", "gpu", "auto"):
        res = runner.cached_or_run(
            world["registry"]["dummy"], world["mix"], world["cache"], device, True
        )
        assert res.ok and res.output.read_bytes() == b"midi-cpu"


def test_rekey_after_a_cosmetic_edit_keeps_results(world):
    reg, cache, mix = world["registry"], world["cache"], world["mix"]
    cachemigration.migrate(cache, reg, [mix])
    before = cachemigration.digests(reg)
    run_py = reg["dummy"].path / "run.py"
    run_py.write_text(run_py.read_text() + '\nMESSAGE = "translated"\n', encoding="utf-8")
    assert cachemigration.digests(reg)["dummy"] != before["dummy"]
    report = cachemigration.migrate(cache, reg, [mix], previous_digests=before)
    assert report.moved == 2 and report.orphaned == 0  # mix and stem transcription
    assert (runner.cache_dir_for(cache, reg["dummy"], mix) / "drums.mid").read_bytes() == (
        b"midi-cpu"
    )


def test_without_rekey_a_code_change_orphans_old_results(world):
    reg, cache, mix = world["registry"], world["cache"], world["mix"]
    cachemigration.migrate(cache, reg, [mix])
    run_py = reg["dummy"].path / "run.py"
    run_py.write_text(run_py.read_text() + "\nX = 2\n", encoding="utf-8")
    report = cachemigration.migrate(cache, reg, [mix])
    assert report.moved == 0 and report.orphaned == 2


def test_digest_snapshot_round_trip(world, tmp_path):
    reg = world["registry"]
    path = tmp_path / "digests.json"
    cachemigration.save_digests(path, reg)
    assert cachemigration.load_digests(path) == cachemigration.digests(reg)
