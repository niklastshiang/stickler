"""Where the app keeps its files: the XDG folders on Linux (unchanged, also tested in
test_setup, test_recent, test_corrections and test_settings), Apple's folders in the Mac app
(SPEC.md, module `core-bridge`, scope 4)."""

from pathlib import Path

import pytest

from stickler import api
from stickler_app import corrections, paths, recent, removal, settings

HOME = "/Users/me"
MAC = {"STICKLER_PACKAGED": "macos", "HOME": HOME}
SUPPORT = Path(HOME) / "Library" / "Application Support" / "Stickler"
CACHES = Path(HOME) / "Library" / "Caches" / "Stickler"


def _where(env) -> dict[str, Path]:
    return {
        "data": paths.data_home(env),
        "cache": paths.cache_home(env),
        "adapters": paths.adapters_root(env),
        "results": paths.results_cache(env),
        "score": paths.score_path(Path("/m/song.flac"), env).parent,
        "hits": paths.hits_path(Path("/m/song.flac"), env).parent,
        "settings": settings.store_path(env),
        "recent": recent.store_path(env),
        "corrections": corrections.store_path(env),
    }


def test_the_mac_app_is_packaged_only_when_its_launcher_says_so():
    assert paths.packaged(MAC) == "macos"
    assert paths.packaged({"STICKLER_PACKAGED": "plan9", "HOME": HOME}) is None
    assert paths.packaged({"HOME": HOME}) is None
    assert paths.packaged({**MAC, "FLATPAK_ID": "ng.tshia.Stickler"}) == "flatpak"


def test_the_mac_app_keeps_models_results_and_settings_in_application_support():
    assert _where(MAC) == {
        "data": SUPPORT,
        "cache": CACHES,
        "adapters": SUPPORT / "adapters",
        "results": SUPPORT / "results",  # macOS may empty Caches; a result takes minutes
        "score": CACHES / "scores",
        "hits": CACHES / "hits",
        "settings": SUPPORT / "settings.json",
        "recent": SUPPORT / "recent.json",
        "corrections": SUPPORT / "corrections.json",
    }


def test_xdg_variables_still_win_in_the_mac_app():
    env = {**MAC, "XDG_DATA_HOME": "/d", "XDG_CACHE_HOME": "/c", "XDG_CONFIG_HOME": "/s"}
    where = _where(env)
    assert where["data"] == Path("/d/stickler") and where["cache"] == Path("/c/stickler")
    assert where["results"] == Path("/c/stickler/results")
    assert where["settings"] == Path("/s/stickler/settings.json")
    assert where["recent"] == Path("/d/stickler/recent.json")
    assert paths.adapters_root({**MAC, "STICKLER_ADAPTERS": "/try"}) == Path("/try")
    assert paths.results_cache({**MAC, "STICKLER_RESULTS_CACHE": "/r"}) == Path("/r")


LINUX_HOME = "/home/me"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (
            {"HOME": LINUX_HOME},
            {
                "data": "/home/me/.local/share/stickler",
                "cache": "/home/me/.cache/stickler",
                "adapters": str(api.ADAPTERS_ROOT),
                "results": str(api.CACHE_DIR),
                "score": "/home/me/.cache/stickler/scores",
                "hits": "/home/me/.cache/stickler/hits",
                "settings": "/home/me/.config/stickler/settings.json",
                "recent": "/home/me/.local/share/stickler/recent.json",
                "corrections": "/home/me/.local/share/stickler/corrections.json",
            },
        ),
        (
            {
                "APPIMAGE": "/x/Stickler.AppImage",
                "SHARUN_DIR": "/tmp/.mount_x",
                "HOME": LINUX_HOME,
            },
            {
                "data": "/home/me/.local/share/stickler",
                "cache": "/home/me/.cache/stickler",
                "adapters": "/home/me/.local/share/stickler/adapters",
                "results": "/home/me/.cache/stickler/results",
                "score": "/home/me/.cache/stickler/scores",
                "hits": "/home/me/.cache/stickler/hits",
                "settings": "/home/me/.config/stickler/settings.json",
                "recent": "/home/me/.local/share/stickler/recent.json",
                "corrections": "/home/me/.local/share/stickler/corrections.json",
            },
        ),
        (
            {
                "FLATPAK_ID": "ng.tshia.Stickler",
                "HOME": LINUX_HOME,
                "XDG_DATA_HOME": "/v/data",
                "XDG_CACHE_HOME": "/v/cache",
                "XDG_CONFIG_HOME": "/v/config",
            },
            {
                "data": "/v/data/stickler",
                "cache": "/v/cache/stickler",
                "adapters": "/v/data/stickler/adapters",
                "results": "/v/cache/stickler/results",
                "score": "/v/cache/stickler/scores",
                "hits": "/v/cache/stickler/hits",
                "settings": "/v/config/stickler/settings.json",
                "recent": "/v/data/stickler/recent.json",
                "corrections": "/v/data/stickler/corrections.json",
            },
        ),
        (
            {"STICKLER_PACKAGED": "system", "HOME": LINUX_HOME},
            {
                "data": "/home/me/.local/share/stickler",
                "cache": "/home/me/.cache/stickler",
                "adapters": "/home/me/.local/share/stickler/adapters",
                "results": "/home/me/.cache/stickler/results",
                "score": "/home/me/.cache/stickler/scores",
                "hits": "/home/me/.cache/stickler/hits",
                "settings": "/home/me/.config/stickler/settings.json",
                "recent": "/home/me/.local/share/stickler/recent.json",
                "corrections": "/home/me/.local/share/stickler/corrections.json",
            },
        ),
    ],
    ids=["checkout", "appimage", "flatpak", "deb-rpm"],
)
def test_linux_keeps_its_folders(env, expected):
    # Compared as paths: Windows spells them with backslashes, the folders are the same
    assert _where(env) == {k: Path(v) for k, v in expected.items()}


def test_removing_the_mac_apps_models_takes_its_analyses_too():
    assert removal.targets(MAC, everything=False) == [
        SUPPORT / "adapters",
        SUPPORT / "python",
        CACHES,
        SUPPORT / "results",
    ]
    assert removal.targets(MAC, everything=True) == [SUPPORT, CACHES]


def test_the_mac_app_with_its_own_core_gives_uv_folders_of_its_own(tmp_path, monkeypatch):
    """SPEC.md, module `mac-package`, scope 3: as the AppImage, the bundled core finds its
    adapters next to itself and keeps uv's Python and downloads in Stickler's folders."""
    import stickler_app

    shipped = tmp_path / "share" / "stickler" / "adapters"
    shipped.mkdir(parents=True)
    monkeypatch.setattr(stickler_app, "prefix", lambda env=None: tmp_path)
    env = {**MAC, "UV_PYTHON_PREFERENCE": "system", "UV_CACHE_DIR": "/elsewhere"}
    assert paths.packaged_env(env) == {
        "STICKLER_ADAPTER_SOURCES": str(shipped),
        "UV_PYTHON_PREFERENCE": "only-managed",  # forced: never a Python found on the Mac
        "UV_PYTHON_DOWNLOADS": "automatic",
        "UV_PYTHON_INSTALL_DIR": str(SUPPORT / "python"),
        "UV_SYSTEM_CERTS": "1",
    }  # a UV_CACHE_DIR already set stays
    assert paths.packaged_env(MAC)["UV_CACHE_DIR"] == str(CACHES / "uv")


def test_the_mac_app_run_from_a_checkout_keeps_uv_as_it_is(tmp_path, monkeypatch):
    """Until `mac-package` the Mac app runs `uv run stickler-bridge` in a checkout: nothing
    ships next to the core there, and its models' environments stay as they were set up."""
    import stickler_app

    monkeypatch.setattr(stickler_app, "prefix", lambda env=None: tmp_path)
    assert paths.packaged_env(MAC) == {}


def _windows(tmp_path) -> dict[str, str]:
    return {"STICKLER_PACKAGED": "windows", "LOCALAPPDATA": str(tmp_path / "AppData" / "Local")}


def test_the_windows_app_is_packaged_when_its_launcher_says_so():
    assert paths.packaged({"STICKLER_PACKAGED": "windows"}) == "windows"
    flatpak = {"STICKLER_PACKAGED": "windows", "FLATPAK_ID": "ng.tshia.Stickler"}
    assert paths.packaged(flatpak) == "flatpak"


def test_the_windows_app_keeps_everything_below_local_app_data(tmp_path):
    root = tmp_path / "AppData" / "Local" / "Stickler"
    assert _where(_windows(tmp_path)) == {
        "data": root / "data",
        "cache": root / "cache",
        "adapters": root / "data" / "adapters",
        "results": root / "cache" / "results",  # the generic rule, not the Mac's
        "score": root / "cache" / "scores",
        "hits": root / "cache" / "hits",
        "settings": root / "config" / "settings.json",
        "recent": root / "data" / "recent.json",
        "corrections": root / "data" / "corrections.json",
    }
    assert paths.config_home(_windows(tmp_path)) == root / "config"


@pytest.mark.parametrize("missing", [{}, {"LOCALAPPDATA": ""}])
def test_the_windows_app_without_local_app_data_uses_the_home_folder(missing):
    env = {"STICKLER_PACKAGED": "windows", "HOME": "/Users/me", **missing}
    assert paths.data_home(env) == Path("/Users/me/AppData/Local/Stickler/data")
    assert paths.cache_home(env) == Path("/Users/me/AppData/Local/Stickler/cache")
    assert paths.config_home(env) == Path("/Users/me/AppData/Local/Stickler/config")


def test_xdg_variables_still_win_in_the_windows_app(tmp_path):
    env = {**_windows(tmp_path), "XDG_DATA_HOME": "/d", "XDG_CACHE_HOME": "/c"}
    env["XDG_CONFIG_HOME"] = "/s"
    where = _where(env)
    assert where["data"] == Path("/d/stickler") and where["cache"] == Path("/c/stickler")
    assert where["settings"] == Path("/s/stickler/settings.json")
    assert paths.adapters_root({**env, "STICKLER_ADAPTERS": "/try"}) == Path("/try")


def test_the_windows_app_with_its_own_core_gives_uv_folders_of_its_own(tmp_path, monkeypatch):
    import stickler_app

    monkeypatch.setattr(stickler_app, "prefix", lambda env=None: tmp_path / "app")
    root = tmp_path / "AppData" / "Local" / "Stickler"
    env = {**_windows(tmp_path), "UV_PYTHON_PREFERENCE": "system", "UV_CACHE_DIR": "/elsewhere"}
    assert paths.packaged_env(env) == {
        "STICKLER_ADAPTER_SOURCES": str(tmp_path / "app" / "share/stickler/adapters"),
        "UV_PYTHON_PREFERENCE": "only-managed",
        "UV_PYTHON_DOWNLOADS": "automatic",
        "UV_PYTHON_INSTALL_DIR": str(root / "data" / "python"),
        "UV_SYSTEM_CERTS": "1",
    }
    assert paths.packaged_env(_windows(tmp_path))["UV_CACHE_DIR"] == str(root / "cache" / "uv")


def test_every_packaged_app_lets_uv_trust_the_systems_certificates(tmp_path, monkeypatch):
    """A company network that inspects TLS stopped the setup on the owner's Windows PC
    (2026-11-25, task 179): uv only trusts its own roots unless told to use the system's.
    A value the user set stays, as for the other uv settings that are not requirements."""
    import stickler_app

    monkeypatch.setattr(stickler_app, "prefix", lambda env=None: tmp_path)
    (tmp_path / "share" / "stickler" / "adapters").mkdir(parents=True)
    for env in (_windows(tmp_path), MAC, {"STICKLER_PACKAGED": "system", "HOME": "/home/me"}):
        assert paths.packaged_env(env)["UV_SYSTEM_CERTS"] == "1"
        assert "UV_SYSTEM_CERTS" not in paths.packaged_env({**env, "UV_SYSTEM_CERTS": "0"})
    assert paths.packaged_env({}) == {}  # from a checkout uv is left as the user set it up
