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
    (common / "pyproject.toml").write_text(
        '[project]\nname = "stickler-adapter"\n', encoding="utf-8"
    )
    (common / "src" / "stickler_adapter" / "__init__.py").write_text(
        "def f():\n    return 1\n", encoding="utf-8"
    )
    path = tmp_path / "transcribers" / "x"
    path.mkdir(parents=True)
    (path / "run.py").write_text("from helper import g\nimport os\n", encoding="utf-8")
    (path / "helper.py").write_text("def g():\n    return 1\n", encoding="utf-8")
    (path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[tool.uv.sources]\n'
        'stickler-adapter = { path = "../../_common", editable = true }\n',
        encoding="utf-8",
    )
    return adapters.AdapterSpec(id="x", stage="transcribers", path=path)


def test_a_helper_module_is_part_of_the_key(adapter):
    before = runner.code_digest(adapter)
    (adapter.path / "helper.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    assert runner.code_digest(adapter) != before


def test_the_shared_adapter_package_is_part_of_the_key(adapter):
    before = runner.code_digest(adapter)
    init = adapter.path.parents[1] / "_common" / "src" / "stickler_adapter" / "__init__.py"
    init.write_text("def f():\n    return 2\n", encoding="utf-8")
    assert runner.code_digest(adapter) != before


def test_comments_and_docstrings_in_helpers_do_not_change_the_key(adapter):
    before = runner.code_digest(adapter)
    (adapter.path / "helper.py").write_text(
        '"""Doc."""\n\n\ndef g():  # note\n    return 1\n', encoding="utf-8"
    )
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


def test_the_equivalence_list_names_real_adapters_and_proper_digests():
    registry = adapters.discover(ROOT / "adapters")
    listed = runner.load_equivalents()
    assert listed, "digests.yaml is empty"
    for spec_id, pairs in listed.items():
        assert spec_id in registry, f"{spec_id} is not an adapter"
        for old, new in pairs:
            assert len(old) == len(new) == 40 and old != new


LISTED = "2aa5362"  # the commit that listed the Task 87 pairs


def _release6_digest(spec: adapters.AdapterSpec, tmp: Path) -> str:
    """The digest definition up to release 6 (run.py, pyproject.toml and setup.py only), on the
    files as they were when the pairs were listed: a later behaviour-neutral edit to one of them
    (Task 97 widened pyproject.toml) must not break the chain this test follows."""
    import hashlib
    import subprocess

    h = hashlib.sha1()
    for name in ("run.py", "pyproject.toml", "setup.py"):
        rel = (spec.path / name).relative_to(ROOT)
        shown = subprocess.run(
            ["git", "show", f"{LISTED}:{rel.as_posix()}"], cwd=ROOT, capture_output=True
        )
        if shown.returncode == 0:
            f = tmp / name
            f.write_bytes(shown.stdout)
            h.update(name.encode() + b"\0" + runner._canonical(f) + b"\0")
    return h.hexdigest()


def test_a_chain_leads_from_each_listed_adapter_s_release_6_digest_to_today_s(tmp_path):
    """Each adapter listed by Task 87 was unchanged since release 6 (checked against b4ca4a5 when
    listed), so its digest of the old definition, on the files of that time, must be reachable.
    drumsep_onset and sad came after release 6; they are listed since Task 96 for a later edit
    only, so they have no release 6 digest to reach."""
    registry = adapters.discover(ROOT / "adapters")
    for spec_id in set(runner.load_equivalents()) - {"drumsep_onset", "sad"}:
        spec = registry[spec_id]
        assert _release6_digest(spec, tmp_path) in runner.equivalent_digests(spec), spec_id


def test_only_a_chain_that_ends_at_the_current_digest_counts(adapter, monkeypatch):
    current = runner.code_digest(adapter)
    pairs = {"x": (("a" * 40, "b" * 40), ("b" * 40, current), ("c" * 40, "d" * 40))}
    monkeypatch.setattr(runner, "load_equivalents", lambda: pairs)
    assert set(runner.equivalent_digests(adapter)) == {"a" * 40, "b" * 40}
    (adapter.path / "helper.py").write_text(
        "def g():\n    return 3\n", encoding="utf-8"
    )  # a real change
    assert runner.equivalent_digests(adapter) == ()


def test_a_file_nothing_imports_is_not_part_of_the_key(adapter):
    before = runner.code_digest(adapter)
    (adapter.path / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    assert runner.code_digest(adapter) == before


def test_a_helper_imported_by_a_helper_is_part_of_the_key(adapter):
    (adapter.path / "helper.py").write_text(
        "import deeper\n\n\ndef g():\n    return 1\n", encoding="utf-8"
    )
    (adapter.path / "deeper.py").write_text("X = 1\n", encoding="utf-8")
    before = runner.code_digest(adapter)
    (adapter.path / "deeper.py").write_text("X = 2\n", encoding="utf-8")
    assert runner.code_digest(adapter) != before


def test_lock_file_and_python_version_are_part_of_the_key(adapter):
    before = runner.code_digest(adapter)
    (adapter.path / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "torch"\n', encoding="utf-8"
    )
    with_lock = runner.code_digest(adapter)
    (adapter.path / ".python-version").write_text("3.14\n", encoding="utf-8")
    assert len({before, with_lock, runner.code_digest(adapter)}) == 3


def test_the_key_does_not_depend_on_where_the_adapters_live(adapter, tmp_path):
    import shutil

    elsewhere = tmp_path / ".venv" / "deep"
    shutil.copytree(adapter.path.parents[1], elsewhere)
    moved = adapters.AdapterSpec(id="x", stage="transcribers", path=elsewhere / "transcribers/x")
    assert runner.code_digest(moved) == runner.code_digest(adapter)


def test_a_list_valued_source_still_finds_the_shared_package(adapter):
    before = runner.code_digest(adapter)
    pyproject = adapter.path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\n\n[tool.uv.sources]\n'
        'stickler-adapter = [{ path = "../../_common", editable = true }]\n',
        encoding="utf-8",
    )
    assert runner._common_dir(adapter) == adapter.path.parents[1] / "_common"
    assert runner.code_digest(adapter) != before  # the pyproject changed, _common still counted


def test_the_equivalence_list_ships_inside_the_package():
    """Installed apps have no repository around the package (see the class table's test)."""
    import stickler

    assert runner.EQUIVALENTS.parent == Path(stickler.__file__).parent
    assert runner.EQUIVALENTS.is_file()
