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
    assert paths.packaged({"STICKLER_PACKAGED": "windows", "HOME": HOME}) is None
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
    ],
    ids=["checkout", "appimage", "flatpak"],
)
def test_linux_keeps_its_folders(env, expected):
    assert {k: str(v) for k, v in _where(env).items()} == expected


def test_removing_the_mac_apps_models_takes_its_analyses_too():
    assert removal.targets(MAC, everything=False) == [
        SUPPORT / "adapters",
        SUPPORT / "python",
        CACHES,
        SUPPORT / "results",
    ]
    assert removal.targets(MAC, everything=True) == [SUPPORT, CACHES]
