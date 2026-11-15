"""The setup assistant's decisions without GTK (SPEC.md, module `setup-assistant`)."""

from pathlib import Path

import pytest

from stickler import api
from stickler_gtk.logic import paths, settings, setup


@pytest.mark.parametrize(
    ("missing", "agreed", "page"),
    [([], False, "none"), (["adtof"], False, "consent"), (["adtof"], True, "download")],
)
def test_the_start_asks_downloads_or_does_nothing(missing, agreed, page):
    assert setup.start_page(missing, agreed=agreed) == page


def test_the_steps_are_programs_for_each_model_then_their_own_downloads():
    ids = setup.step_ids(["adtof", "beat_this"], has_weights=lambda a: a == "beat_this")
    assert ids == ("environment:adtof", "environment:beat_this", "weights:beat_this")


def test_a_steps_progress_is_what_grew_against_its_size_and_never_full():
    assert setup.fraction("weights:beat_this", 39_000_000) == pytest.approx(0.5)
    assert setup.fraction("environment:adtof", 9_000_000_000) == 0.99
    assert setup.fraction("environment:adtof", -5) == 0.0
    assert setup.fraction("weights:unknown", 10) is None
    assert setup.amount("weights:beat_this", 39_000_000) == "39 MB of 78 MB"
    assert setup.amount("environment:adtof", 650_000_000) == "650 MB of 1.3 GB"
    assert setup.amount("weights:unknown", 10) == ""


def test_a_failed_step_names_its_server():
    assert "cloud.cp.jku.at" in setup.server("weights:beat_this")
    assert "github.com" in setup.server("weights:beat_this")
    assert "pypi.org" in setup.server("environment:adtof")
    assert setup.server("weights:other") == "the model’s server"


def test_the_details_are_the_errors_last_lines():
    text = "\n".join(f"line {k}" for k in range(20))
    assert setup.details(text) == "\n".join(f"line {k}" for k in range(12, 20))
    assert setup.details("  short\n\n") == "short"


def test_what_grew_is_the_free_space_a_step_used(tmp_path):
    """Cheap enough for twice a second, unlike walking uv's cache."""
    free = setup.free_space(tmp_path)
    assert free > 0 and setup.free_space(tmp_path / "not" / "there") == free


def test_the_consent_lists_the_missing_models_with_their_sizes():
    assert setup.model_size("adtof") == "1.3 GB" and setup.model_size("beat_this") == "0.9 GB"
    assert setup.total_size(["adtof", "beat_this"]) == "2.2 GB"
    assert setup.total_size(["beat_this"]) == "0.9 GB"
    assert "detects the hits" in setup.model_text("adtof")[0]
    assert "non-commercial" in setup.model_text("adtof")[1]


def test_uvs_cache_and_the_adapters_folder_follow_the_environment(tmp_path):
    assert setup.uv_cache({"UV_CACHE_DIR": "/c/uv"}) == Path("/c/uv")
    assert setup.uv_cache({"XDG_CACHE_HOME": "/c", "HOME": "/h"}) == Path("/c/uv")
    assert setup.uv_cache({"HOME": "/h"}) == Path("/h/.cache/uv")
    assert paths.adapters_root({"STICKLER_ADAPTERS": str(tmp_path)}) == tmp_path
    assert paths.adapters_root({}) == api.ADAPTERS_ROOT


def test_the_consent_is_remembered(tmp_path):
    store = tmp_path / "settings.json"
    assert settings.load(store).setup_agreed is False
    settings.update(store, setup_agreed=True)
    assert settings.load(store).setup_agreed is True
    store.write_text('{"setup_agreed": "yes"}', encoding="utf-8")
    assert settings.load(store).setup_agreed is False


def test_a_packaged_app_keeps_models_and_results_in_its_own_folders(tmp_path):
    flatpak = {"FLATPAK_ID": "ng.tshia.Stickler", "XDG_DATA_HOME": "/d", "XDG_CACHE_HOME": "/c"}
    appimage = {"APPIMAGE": "/x/Stickler.AppImage", "XDG_DATA_HOME": "/d", "XDG_CACHE_HOME": "/c"}
    assert paths.packaged(flatpak) == "flatpak" and paths.packaged(appimage) == "appimage"
    assert paths.packaged({"FLATPAK_ID": "org.other.App"}) is None and paths.packaged({}) is None
    for env in (flatpak, appimage):
        assert paths.adapters_root(env) == Path("/d/stickler/adapters")
        assert paths.results_cache(env) == Path("/c/stickler/results")
    assert paths.adapters_root({**flatpak, "STICKLER_ADAPTERS": "/try"}) == Path("/try")
    assert paths.results_cache({}) == api.CACHE_DIR  # from the checkout: as before
    assert paths.adapter_sources({"STICKLER_ADAPTER_SOURCES": "/app/a"}) == Path("/app/a")
    assert paths.adapter_sources({}) is None


def test_the_shipped_adapter_sources_are_copied_without_touching_environments(tmp_path):
    shipped, models = tmp_path / "app" / "adapters", tmp_path / "data" / "adapters"
    (shipped / "beats" / "beat_this" / "__pycache__").mkdir(parents=True)
    (shipped / "beats" / "beat_this" / "run.py").write_text("print(1)")
    (shipped / "beats" / "beat_this" / "uv.lock").write_text("lock 1")
    (shipped / "beats" / "beat_this" / "__pycache__" / "x.pyc").write_bytes(b"x")
    assert setup.sync_adapters(shipped, models) == 2
    target = models / "beats" / "beat_this"
    assert (target / "run.py").read_text() == "print(1)" and not (target / "__pycache__").exists()
    (target / ".venv").mkdir()
    (target / "weights").mkdir()
    (target / "weights" / "model.ckpt").write_bytes(b"w")
    assert setup.sync_adapters(shipped, models) == 0  # nothing changed
    (shipped / "beats" / "beat_this" / "uv.lock").write_text("lock 2")  # a new app version
    assert setup.sync_adapters(shipped, models) == 1
    assert (target / "uv.lock").read_text() == "lock 2"
    assert (target / ".venv").is_dir() and (target / "weights" / "model.ckpt").read_bytes() == b"w"
