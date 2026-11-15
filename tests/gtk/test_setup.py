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


def test_what_grew_counts_files_below_the_folders(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "one").write_bytes(b"x" * 10)
    (tmp_path / "a" / "b" / "two").write_bytes(b"x" * 5)
    (tmp_path / "a" / "link").symlink_to(tmp_path / "a" / "one")
    assert setup.disk_bytes([tmp_path / "a", tmp_path / "missing"]) == 15


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
