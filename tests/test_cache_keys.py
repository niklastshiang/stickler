"""Cache keys cover everything that defines an adapter's behaviour, and results stored under an
equivalent earlier digest (src/stickler/digests.yaml) are found and renamed, not recomputed."""

from pathlib import Path

import pytest

from stickler import adapters, runner

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def adapter(tmp_path) -> adapters.AdapterSpec:
    """An adapter with a helper module, pointing at its own copy of _common."""
    common = tmp_path / "_common"
    (common / "src" / "stickler_adapter").mkdir(parents=True)
    (common / "pyproject.toml").write_text('[project]\nname = "stickler-adapter"\n')
    (common / "src" / "stickler_adapter" / "__init__.py").write_text("def f():\n    return 1\n")
    path = tmp_path / "transcribers" / "x"
    path.mkdir(parents=True)
    (path / "run.py").write_text("from helper import g\n")
    (path / "helper.py").write_text("def g():\n    return 1\n")
    (path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[tool.uv.sources]\n'
        'stickler-adapter = { path = "../../_common", editable = true }\n'
    )
    return adapters.AdapterSpec(id="x", stage="transcribers", path=path)


def test_a_helper_module_is_part_of_the_key(adapter):
    before = runner.code_digest(adapter)
    (adapter.path / "helper.py").write_text("def g():\n    return 2\n")
    assert runner.code_digest(adapter) != before


def test_the_shared_adapter_package_is_part_of_the_key(adapter):
    before = runner.code_digest(adapter)
    init = adapter.path.parents[1] / "_common" / "src" / "stickler_adapter" / "__init__.py"
    init.write_text("def f():\n    return 2\n")
    assert runner.code_digest(adapter) != before


def test_comments_and_docstrings_in_helpers_do_not_change_the_key(adapter):
    before = runner.code_digest(adapter)
    (adapter.path / "helper.py").write_text('"""Doc."""\n\n\ndef g():  # note\n    return 1\n')
    assert runner.code_digest(adapter) == before


def test_an_entry_under_an_equivalent_digest_is_renamed_to_the_current_key(
    adapter, tmp_path, monkeypatch
):
    song = tmp_path / "song.wav"
    song.write_bytes(b"audio")
    sha = runner._sha1_file(song)
    old = tmp_path / "cache" / "x" / runner.cache_key(adapter, sha, "0" * 40)
    old.mkdir(parents=True)
    (old / "drums.mid").write_bytes(b"midi")
    monkeypatch.setattr(runner, "equivalent_digests", lambda spec: ["f" * 40, "0" * 40])
    current = runner.cache_dir_for(tmp_path / "cache", adapter, song)
    assert current.name == runner.cache_key(adapter, sha)
    assert (current / "drums.mid").read_bytes() == b"midi" and not old.exists()


def test_an_entry_under_a_digest_that_is_not_listed_is_not_used(adapter, tmp_path, monkeypatch):
    song = tmp_path / "song.wav"
    song.write_bytes(b"audio")
    old = tmp_path / "cache" / "x" / runner.cache_key(adapter, runner._sha1_file(song), "0" * 40)
    old.mkdir(parents=True)
    monkeypatch.setattr(runner, "equivalent_digests", lambda spec: [])
    current = runner.cache_dir_for(tmp_path / "cache", adapter, song)
    assert not current.exists() and old.exists()


def test_the_current_entry_wins_over_an_equivalent_one(adapter, tmp_path, monkeypatch):
    song = tmp_path / "song.wav"
    song.write_bytes(b"audio")
    sha = runner._sha1_file(song)
    old = tmp_path / "cache" / "x" / runner.cache_key(adapter, sha, "0" * 40)
    old.mkdir(parents=True)
    new = tmp_path / "cache" / "x" / runner.cache_key(adapter, sha)
    new.mkdir(parents=True)
    monkeypatch.setattr(runner, "equivalent_digests", lambda spec: ["0" * 40])
    assert runner.cache_dir_for(tmp_path / "cache", adapter, song) == new and old.exists()


def test_the_equivalence_list_names_only_real_adapters_and_never_their_current_digest():
    registry = adapters.discover(ROOT / "adapters")
    listed = runner.load_equivalents()
    assert listed, "digests.yaml is empty"
    for spec_id, old in listed.items():
        assert spec_id in registry, f"{spec_id} is not an adapter"
        assert runner.code_digest(registry[spec_id]) not in old
        assert all(len(d) == 40 for d in old)


def test_the_equivalence_list_ships_inside_the_package():
    """Installed apps have no repository around the package (see the class table's test)."""
    import stickler

    assert runner.EQUIVALENTS.parent == Path(stickler.__file__).parent
    assert runner.EQUIVALENTS.is_file()
