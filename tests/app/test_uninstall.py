"""What "Uninstall Stickler…" removes, per package, without GTK (SPEC.md "Release 10 (proposed):
keep and remove", scope B)."""

import hashlib
from pathlib import Path

from stickler_app import corrections, paths, recent, settings, uninstall


def _appimage(home: Path, where: Path) -> dict[str, str]:
    return {"HOME": str(home), "APPIMAGE": str(where), "SHARUN_DIR": "/tmp/.mount_x"}


def _stored(env) -> None:
    for path in (settings.store_path(env), recent.store_path(env), corrections.store_path(env)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    weights = paths.data_home(env) / "adapters" / "beats" / "beat_this" / "weights"
    weights.mkdir(parents=True)
    (weights / "m.ckpt").write_bytes(b"x" * 100)
    (paths.cache_home(env) / "results").mkdir(parents=True)


def test_by_default_the_settings_recent_songs_and_corrections_stay(tmp_path):
    env = _appimage(tmp_path, tmp_path / "Apps" / "Stickler.AppImage")
    _stored(env)
    plan = uninstall.plan(env, keep_settings=True)
    removed = set(plan.folders)
    assert paths.data_home(env) / "adapters" in removed and paths.cache_home(env) in removed
    for kept in (settings.store_path(env), recent.store_path(env), corrections.store_path(env)):
        assert not any(kept.is_relative_to(f) for f in removed)
    assert plan.size >= 100


def test_with_the_box_ticked_all_of_stickler_goes(tmp_path):
    env = _appimage(tmp_path, tmp_path / "Apps" / "Stickler.AppImage")
    _stored(env)
    plan = uninstall.plan(env, keep_settings=False)
    for gone in (settings.store_path(env), recent.store_path(env), corrections.store_path(env)):
        assert any(gone.is_relative_to(f) for f in plan.folders)


def test_an_appimage_removes_the_menu_entries_and_icons_made_for_this_file_only(tmp_path):
    image = tmp_path / "AppImages" / "Stickler-9-x86_64.AppImage"
    env = _appimage(tmp_path, image)
    apps = tmp_path / ".local" / "share" / "applications"
    apps.mkdir(parents=True)
    md5 = hashlib.md5(f"file://{image}".encode()).hexdigest()
    hicolor = tmp_path / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    hicolor.mkdir(parents=True)
    (hicolor / f"appimagekit_{md5}_ng.tshia.Stickler.png").write_bytes(b"icon")
    (apps / f"appimagekit_{md5}-Stickler.desktop").write_text(
        "[Desktop Entry]\nName=Stickler\nExec=/elsewhere/AppRun %F\n"
        f"Icon=appimagekit_{md5}_ng.tshia.Stickler\nX-AppImage-Identifier={md5}\n"
    )
    gear_icon = tmp_path / "AppImages" / ".icons" / "stickler"
    gear_icon.parent.mkdir(parents=True)
    gear_icon.write_bytes(b"icon")
    (apps / "stickler.desktop").write_text(
        f"[Desktop Entry]\nName=Stickler\nExec={image} %F\nTryExec={image}\nIcon={gear_icon}\n"
    )
    other = apps / "other.desktop"
    other.write_text("[Desktop Entry]\nName=Other\nExec=/opt/other\nIcon=other\n")
    elsewhere = apps / "older-stickler.desktop"  # another copy of Stickler: not this file
    elsewhere.write_text("[Desktop Entry]\nExec=/old/Stickler-8.AppImage\n")

    plan = uninstall.plan(env, keep_settings=True)

    assert plan.kind == "appimage" and plan.program == str(image)
    assert set(plan.files) == {
        apps / f"appimagekit_{md5}-Stickler.desktop",
        hicolor / f"appimagekit_{md5}_ng.tshia.Stickler.png",
        apps / "stickler.desktop",
        gear_icon,
    }


def test_each_package_names_what_removes_the_program(tmp_path):
    home = str(tmp_path)
    assert uninstall.plan({"HOME": home, "STICKLER_PACKAGED": "system"}).program == "stickler"
    flatpak = uninstall.plan({"HOME": home, "FLATPAK_ID": "ng.tshia.Stickler"})
    assert (flatpak.kind, flatpak.program) == ("flatpak", "ng.tshia.Stickler")
    assert uninstall.plan({"HOME": home, "STICKLER_PACKAGED": "macos"}).kind == "macos"


def test_from_the_checkout_nothing_is_removed(tmp_path):
    plan = uninstall.plan({"HOME": str(tmp_path)})
    assert plan.kind is None and plan.folders == [] and plan.files == []


def test_the_flatpak_command_to_copy_where_no_software_app_opens_its_page():
    assert uninstall.flatpak_command() == "flatpak uninstall --user ng.tshia.Stickler"


def test_removing_deletes_folders_and_files_and_tolerates_what_is_gone(tmp_path):
    folder = tmp_path / "f"
    (folder / "x").mkdir(parents=True)
    file = tmp_path / "a.desktop"
    file.write_text("x")
    uninstall.remove(uninstall.Plan("appimage", [folder, tmp_path / "gone"], [file], "", 0))
    assert not folder.exists() and not file.exists()


def test_the_package_name_is_the_packages():
    import yaml

    root = Path(__file__).resolve().parents[2]
    nfpm = yaml.safe_load((root / "packaging" / "nfpm.yaml").read_text(encoding="utf-8"))
    assert nfpm["name"] == uninstall.PACKAGE
