"""What "Remove Downloaded Models…" deletes (SPEC.md, module `polish`): only the installed
app's own folders, never the checkout's models."""

from pathlib import Path

from stickler_app import removal

HOME = "/home/me"
APPIMAGE = {
    "APPIMAGE": "/x/Stickler.AppImage",
    "SHARUN_DIR": "/tmp/.mount_x",
    "HOME": HOME,
    "XDG_DATA_HOME": f"{HOME}/.local/share",
    "XDG_CACHE_HOME": f"{HOME}/.cache",
    "XDG_CONFIG_HOME": f"{HOME}/.config",
}
APP = f"{HOME}/.var/app/ng.tshia.Stickler"
FLATPAK = {
    "FLATPAK_ID": "ng.tshia.Stickler",
    "HOME": HOME,
    "XDG_DATA_HOME": f"{APP}/data",
    "XDG_CACHE_HOME": f"{APP}/cache",
    "XDG_CONFIG_HOME": f"{APP}/config",
}


def test_from_the_checkout_nothing_is_removed():
    assert removal.targets({"HOME": HOME}, everything=False) == []
    assert removal.targets({"HOME": HOME}, everything=True) == []


def test_an_appimage_removes_its_models_python_and_analyses_by_default():
    assert removal.targets(APPIMAGE, everything=False) == [
        Path(f"{HOME}/.local/share/stickler/adapters"),
        Path(f"{HOME}/.local/share/stickler/python"),
        Path(f"{HOME}/.cache/stickler"),
    ]


def test_everything_means_stickler_s_three_folders():
    assert removal.targets(APPIMAGE, everything=True) == [
        Path(f"{HOME}/.local/share/stickler"),
        Path(f"{HOME}/.cache/stickler"),
        Path(f"{HOME}/.config/stickler"),
    ]


def test_the_flatpak_also_removes_the_uv_cache_inside_its_sandbox_folder():
    assert removal.targets(FLATPAK, everything=False) == [
        Path(f"{APP}/data/stickler/adapters"),
        Path(f"{APP}/data/stickler/python"),
        Path(f"{APP}/cache/stickler"),
        Path(f"{APP}/cache/uv"),
    ]
    shared = {**FLATPAK, "XDG_CACHE_HOME": f"{HOME}/.cache"}  # not the sandbox's own folder
    assert Path(f"{HOME}/.cache/uv") not in removal.targets(shared, everything=False)


def test_the_windows_app_removes_its_models_python_and_caches_but_not_its_settings(tmp_path):
    local = tmp_path / "AppData" / "Local" / "Stickler"
    env = {"STICKLER_PACKAGED": "windows", "LOCALAPPDATA": str(tmp_path / "AppData" / "Local")}
    # the analyses sit in the cache folder; config (settings) and data/recent.json stay
    assert removal.targets(env, everything=False) == [
        local / "data" / "adapters",
        local / "data" / "python",
        local / "cache",
    ]
    assert removal.targets(env, everything=True) == [
        local / "data",
        local / "cache",
        local / "config",
    ]


def test_size_and_removal_of_real_folders(tmp_path):
    env = {**APPIMAGE, "XDG_DATA_HOME": str(tmp_path / "d"), "XDG_CACHE_HOME": str(tmp_path / "c")}
    env["XDG_CONFIG_HOME"] = str(tmp_path / "f")
    model = tmp_path / "d" / "stickler" / "adapters" / "beats" / "beat_this" / "weights"
    model.mkdir(parents=True)
    (model / "w.ckpt").write_bytes(b"x" * 1000)
    (tmp_path / "c" / "stickler" / "scores").mkdir(parents=True)
    (tmp_path / "c" / "stickler" / "scores" / "a.musicxml").write_bytes(b"x" * 24)
    recent = tmp_path / "d" / "stickler" / "recent.json"
    recent.write_text("[]")
    chosen = removal.targets(env, everything=False)
    assert removal.size(chosen) == 1024
    removal.remove(chosen)
    assert not (tmp_path / "d" / "stickler" / "adapters").exists()
    assert not (tmp_path / "c" / "stickler").exists() and recent.exists()
    removal.remove(chosen)  # again: nothing left, no error
