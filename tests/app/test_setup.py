"""The setup assistant's decisions without GTK (SPEC.md, module `setup-assistant`)."""

from pathlib import Path

import pytest

from stickler import api
from stickler_app import paths, settings, setup


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


def test_the_model_download_counts_its_own_files_not_the_free_space(tmp_path):
    """The free space also counted Python's first bytecode (21 MB), so Beat This! showed
    "78 of 78 MB" while its checkpoint was half-way (owner, 2026-11-15)."""
    adapter = tmp_path / "beats" / "beat_this"
    checkpoints = adapter / "weights" / "hub" / "checkpoints"
    grown = setup.meter("weights:beat_this", tmp_path, adapter)
    assert grown() == 0  # no weights folder yet
    checkpoints.mkdir(parents=True)
    (checkpoints / "beat_this-final0.ckpt.partial").write_bytes(b"x" * 3000)
    (adapter / ".venv" / "lib").mkdir(parents=True)
    (adapter / ".venv" / "lib" / "torch.pyc").write_bytes(b"y" * 5000)  # not the model
    assert grown() == 3000
    environment = setup.meter("environment:beat_this", tmp_path, adapter)
    assert environment() == pytest.approx(0, abs=10_000_000)  # the free space it took


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
    appimage = {
        "APPIMAGE": "/x/Stickler.AppImage",
        "SHARUN_DIR": "/tmp/.mount_x",
        "XDG_DATA_HOME": "/d",
        "XDG_CACHE_HOME": "/c",
    }
    assert paths.packaged(flatpak) == "flatpak" and paths.packaged(appimage) == "appimage"
    assert paths.packaged({"FLATPAK_ID": "org.other.App"}) is None and paths.packaged({}) is None
    for env in (flatpak, appimage):
        assert paths.adapters_root(env) == Path("/d/stickler/adapters")
        assert paths.results_cache(env) == Path("/c/stickler/results")
    assert paths.adapters_root({**flatpak, "STICKLER_ADAPTERS": "/try"}) == Path("/try")
    assert paths.results_cache({}) == api.CACHE_DIR  # from the checkout: as before
    assert paths.results_cache({**flatpak, "STICKLER_RESULTS_CACHE": "/r"}) == Path("/r")
    assert paths.results_cache({"STICKLER_RESULTS_CACHE": "/r"}) == Path("/r")
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


def test_an_appimage_sets_where_its_files_are_and_keeps_uv_off_its_own_python():
    """Inside an AppImage the data lie in its folder ($SHARUN_DIR) and its Python's path changes
    with every mount, so uv must use a Python of its own (SPEC.md, module `packaging`)."""
    import stickler_app

    env = {
        "APPIMAGE": "/x/Stickler.AppImage",
        "SHARUN_DIR": "/tmp/.mount_x",
        "XDG_DATA_HOME": "/d",
        "XDG_CACHE_HOME": "/c",
    }
    assert stickler_app.prefix(env=env) == Path("/tmp/.mount_x")
    added = paths.packaged_env(env)
    assert added == {
        "STICKLER_ADAPTER_SOURCES": "/tmp/.mount_x/share/stickler/adapters",
        "UV_PYTHON_PREFERENCE": "only-managed",
        "UV_PYTHON_DOWNLOADS": "automatic",
        # uv's downloads and its Python inside Stickler's own folders, so removing those three
        # folders removes everything (owner, 2026-11-15)
        "UV_CACHE_DIR": "/c/stickler/uv",
        "UV_PYTHON_INSTALL_DIR": "/d/stickler/python",
    }
    # requirements, not preferences: a user's own setting would let uv take the AppImage's Python
    chosen = {**env, "UV_PYTHON_PREFERENCE": "system", "UV_CACHE_DIR": "/mine/uv"}
    forced = paths.packaged_env(chosen)
    assert forced["UV_PYTHON_PREFERENCE"] == "only-managed"
    assert "UV_CACHE_DIR" not in forced  # where uv keeps its downloads is the user's to choose
    assert paths.packaged({"APPIMAGE": "/x/Other.AppImage"}) is None  # another AppImage's terminal
    assert paths.packaged_env({"FLATPAK_ID": "ng.tshia.Stickler"}) == {}  # set by the manifest
    assert paths.packaged_env({}) == {}


def test_a_deb_or_rpm_keeps_uv_and_its_python_in_sticklers_folders():
    """Installed by the system's package manager (SPEC.md, module `linux-packages`): the
    launcher says so; the adapters' sources lie under the system's prefix, and uv brings its
    own Python 3.14 into Stickler's folders, so the system's Python never runs the models."""
    import sys

    import stickler_app

    env = {"STICKLER_PACKAGED": "system", "XDG_DATA_HOME": "/d", "XDG_CACHE_HOME": "/c"}
    assert paths.packaged(env) == "system"
    assert stickler_app.prefix(env=env) == Path(sys.prefix)  # /usr for the system's Python
    assert paths.packaged_env(env) == {
        "STICKLER_ADAPTER_SOURCES": str(Path(sys.prefix) / "share/stickler/adapters"),
        "UV_PYTHON_PREFERENCE": "only-managed",
        "UV_PYTHON_DOWNLOADS": "automatic",
        "UV_CACHE_DIR": "/c/stickler/uv",
        "UV_PYTHON_INSTALL_DIR": "/d/stickler/python",
    }


def test_new_weight_downloads_drop_the_finished_mark_so_setup_runs_again(tmp_path):
    """An update that changes where a model's weights come from must download them again
    (code review before release 5)."""
    shipped, models = tmp_path / "app", tmp_path / "data"
    code = shipped / "beats" / "beat_this"
    code.mkdir(parents=True)
    for name, text in (("run.py", "run 1"), ("download.py", "sha 1"), ("setup.py", "setup")):
        (code / name).write_text(text)
    setup.sync_adapters(shipped, models)
    marker = models / "beats" / "beat_this" / "weights" / ".setup-complete"
    marker.parent.mkdir(parents=True)
    marker.write_text("")
    (code / "run.py").write_text("run 2")  # code only: the weights stay valid
    assert setup.sync_adapters(shipped, models) == 1 and marker.exists()
    (code / "download.py").write_text("sha 2")  # another checkpoint
    assert setup.sync_adapters(shipped, models) == 1 and not marker.exists()
    assert not list(models.rglob("*.part"))
