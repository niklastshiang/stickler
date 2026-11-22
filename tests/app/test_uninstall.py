"""What "Uninstall Stickler…" removes, per package, without GTK (SPEC.md "Release 10 (proposed):
keep and remove", scope B)."""

import hashlib
from pathlib import Path

from stickler_app import corrections, paths, recent, settings, uninstall


def _appimage(home: Path, where: Path) -> dict[str, str]:
    return {"HOME": str(home), "APPIMAGE": str(where), "SHARUN_DIR": "/tmp/.mount_x"}


APPIMAGE_HEAD = b"\x7fELF" + b"\x00" * 4 + b"AI\x02"  # what an AppImage of type 2 starts with


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
    image.parent.mkdir(parents=True)
    image.write_bytes(APPIMAGE_HEAD)
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
    gear_icon.parent.mkdir()
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
    assert uninstall.flatpak_command() == "flatpak uninstall --user --delete-data ng.tshia.Stickler"


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


# The decisions around PackageKit (the D-Bus calls are in stickler_gtk/ui/packagekit.py and run
# against the real PackageKit in packaging/linux/container-test.sh)


def test_only_the_package_of_that_name_is_chosen():
    ids = ["stickler-doc;9;all;installed", "stickler;9;amd64;installed:/tmp/x.deb"]
    assert uninstall.chosen_package("stickler", ids) == "stickler;9;amd64;installed:/tmp/x.deb"
    assert uninstall.chosen_package("stickler", ["other;1;all;installed"]) is None


def test_a_transaction_that_did_not_succeed_says_why():
    assert uninstall.transaction_failed(1, "") is None
    assert uninstall.transaction_failed(1, "") is None and uninstall.SUCCESS == 1
    assert uninstall.transaction_failed(3, "") == "the package was not removed"
    assert uninstall.transaction_failed(1, "Not authorized") == "Not authorized"


def test_where_packagekit_cannot_remove_it_the_terminal_line_for_the_system():
    assert uninstall.terminal_command("/etc/fedora-release") == "sudo dnf remove stickler"
    assert uninstall.terminal_command("/nonexistent") == "sudo apt remove stickler"


def test_keeping_the_settings_still_asks_again_before_the_next_download(tmp_path):
    """As "Remove Downloaded Models…" does (review of 2026-11-22): a reinstall must not start a
    multi-GB download on a consent given before."""
    env = _appimage(tmp_path, tmp_path / "Apps" / "Stickler.AppImage")
    _stored(env)
    settings.save(settings.store_path(env), settings.Settings(zoom=1.25, setup_agreed=True))
    uninstall.remove(uninstall.plan(env, keep_settings=True), env)
    kept = settings.load(settings.store_path(env))
    assert (kept.zoom, kept.setup_agreed) == (1.25, False)


def test_an_icon_outside_the_integrations_folders_is_never_deleted(tmp_path):
    image = tmp_path / "AppImages" / "Stickler.AppImage"
    env = _appimage(tmp_path, image)
    apps = tmp_path / ".local" / "share" / "applications"
    apps.mkdir(parents=True)
    picture = tmp_path / "Pictures" / "drums.png"
    picture.parent.mkdir()
    picture.write_bytes(b"mine")
    (apps / "my-launcher.desktop").write_text(f"[Desktop Entry]\nExec={image}\nIcon={picture}\n")
    plan = uninstall.plan(env)
    assert apps / "my-launcher.desktop" in plan.files and picture not in plan.files


def test_quoted_exec_lines_and_escaped_uris_are_this_files_too(tmp_path):
    image = tmp_path / "My Apps" / "Stickler.AppImage"
    env = _appimage(tmp_path, image)
    apps = tmp_path / ".local" / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / "quoted.desktop").write_text(f'[Desktop Entry]\nExec="{image}" %U\n')
    from urllib.parse import quote

    md5 = hashlib.md5(f"file://{quote(str(image))}".encode()).hexdigest()
    (apps / "escaped.desktop").write_text(f"[Desktop Entry]\nX-AppImage-Identifier={md5}\n")
    assert {apps / "quoted.desktop", apps / "escaped.desktop"} <= set(uninstall.plan(env).files)


# Security (2026-11-22): a destructive path needs its root after resolving, and its proof


def test_an_icon_path_that_climbs_out_of_the_icon_folder_is_never_deleted(tmp_path):
    image = tmp_path / "AppImages" / "Stickler.AppImage"
    env = _appimage(tmp_path, image)
    apps = tmp_path / ".local" / "share" / "applications"
    apps.mkdir(parents=True)
    picture = tmp_path / "Pictures" / "drums.png"
    picture.parent.mkdir()
    picture.write_bytes(b"mine")
    (tmp_path / ".local" / "share" / "icons").mkdir()  # the climb needs a folder that exists
    climbing = (
        tmp_path / ".local" / "share" / "icons" / ".." / ".." / ".." / "Pictures" / "drums.png"
    )
    (apps / "s.desktop").write_text(f"[Desktop Entry]\nExec={image}\nIcon={climbing}\n")
    files = uninstall.plan(env).files
    assert apps / "s.desktop" in files
    assert not any(f.resolve() == picture.resolve() for f in files)


def test_only_a_real_appimage_is_named_as_the_program_to_remove(tmp_path):
    fake = tmp_path / "notes.txt"
    fake.write_text("my notes")
    assert uninstall.plan(_appimage(tmp_path, fake)).program == ""
    real = tmp_path / "Stickler.AppImage"
    real.write_bytes(APPIMAGE_HEAD + b"\x00" * 100)
    assert uninstall.plan(_appimage(tmp_path, real)).program == str(real)


def test_an_unreachable_package_service_is_named_in_words():
    """Owner, 2026-11-22, in a Distrobox (no system bus): the dialog showed D-Bus's own
    "Could not connect: No such file or directory"."""
    reason = uninstall.unreachable()
    assert "PackageKit" in reason and "connect" not in reason


def test_the_flatpak_removes_nothing_itself_the_software_app_asks_about_the_data(tmp_path):
    """Owner, 2026-11-22: the Software app asks whether the data goes when it uninstalls, so
    the Flatpak's own dialog has no box and nothing is removed by the app."""
    env = {"HOME": str(tmp_path), "FLATPAK_ID": "ng.tshia.Stickler"}
    _stored(env)
    for keep in (True, False):
        plan = uninstall.plan(env, keep_settings=keep)
        assert (plan.kind, plan.folders, plan.files, plan.size) == ("flatpak", [], [], 0)
    settings.save(settings.store_path(env), settings.Settings(setup_agreed=True))
    uninstall.remove(uninstall.plan(env), env)
    assert settings.load(settings.store_path(env)).setup_agreed is True  # its data, its choice
    assert uninstall.flatpak_command() == "flatpak uninstall --user --delete-data ng.tshia.Stickler"
