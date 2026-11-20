"""scripts/site_release.py fills the website's download cards from a release (SPEC.md
"Website"): the HTML holds no version, the published copy names the newest files."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("site_release", ROOT / "scripts" / "site_release.py")
assert _spec and _spec.loader
site_release = importlib.util.module_from_spec(_spec)
sys.modules["site_release"] = site_release
_spec.loader.exec_module(site_release)

DOWNLOAD = "https://github.com/niklastshiang/stickler/releases/download/v8/"
RELEASE = {
    "tagName": "v8",
    "assets": [
        {"name": "Stickler-8.dmg", "size": 412_000_000, "url": DOWNLOAD + "Stickler-8.dmg"},
        {"name": "Stickler-8.flatpak", "size": 32_600_000, "url": DOWNLOAD + "Stickler-8.flatpak"},
        {
            "name": "Stickler-8-x86_64.AppImage",
            "size": 133_800_000,
            "url": DOWNLOAD + "Stickler-8-x86_64.AppImage",
        },
        {"name": "Stickler-8-x86_64.AppImage.zsync", "size": 228_000, "url": DOWNLOAD + "x.zsync"},
        {
            "name": "Stickler-8_amd64.deb",
            "size": 68_700_000,
            "url": DOWNLOAD + "Stickler-8_amd64.deb",
        },
        {
            "name": "Stickler-8.x86_64.rpm",
            "size": 71_700_000,
            "url": DOWNLOAD + "Stickler-8.x86_64.rpm",
        },
    ],
}


@pytest.fixture
def built(tmp_path):
    release = tmp_path / "release.json"
    release.write_text(json.dumps(RELEASE), encoding="utf-8")
    out = tmp_path / "out"
    assert site_release.main([str(release), str(ROOT / "site"), str(out)]) == 0
    return out


def test_sizes_read_as_people_say_them():
    assert site_release.size_text(32_600_000) == "33 MB"
    assert site_release.size_text(133_800_000) == "134 MB"
    assert site_release.size_text(1_240_000_000) == "1.2 GB"
    assert site_release.size_text(1_240_000_000, decimal=",") == "1,2 GB"


def test_each_kind_of_package_is_found_and_the_zsync_is_not():
    found = site_release.packages(RELEASE)
    assert {kind: a["name"] for kind, a in found.items()} == {
        "dmg": "Stickler-8.dmg",
        "flatpak": "Stickler-8.flatpak",
        "appimage": "Stickler-8-x86_64.AppImage",
        "deb": "Stickler-8_amd64.deb",
        "rpm": "Stickler-8.x86_64.rpm",
    }


def test_the_copy_names_the_release_files_in_both_languages(built):
    for page, size in (("index.html", "33 MB"), ("de/index.html", "33 MB")):
        html = (built / page).read_text(encoding="utf-8")
        assert f'data-asset="flatpak"\n              href="{DOWNLOAD}Stickler-8.flatpak"' in html
        assert f'<span data-size="flatpak">{size}</span>' in html
        assert '<span data-name="flatpak">Stickler-8.flatpak</span>' in html
        assert f'href="{DOWNLOAD}Stickler-8.dmg"' in html
        assert "releases/latest" not in html
    for page in ("index.html", "de/index.html"):
        html = (built / page).read_text(encoding="utf-8")
        assert f'data-asset="deb"\n              href="{DOWNLOAD}Stickler-8_amd64.deb"' in html
        assert '<span data-size="deb">69 MB</span>' in html
        assert '<span data-name="deb">Stickler-8_amd64.deb</span>' in html
        assert '<span data-name="rpm">Stickler-8.x86_64.rpm</span>' in html
        assert '<span data-size="rpm">72 MB</span>' in html
    assert '<span data-size="dmg">412 MB</span>' in (built / "index.html").read_text()
    assert '<span data-size="dmg">412 MB</span>' in (built / "de/index.html").read_text()


def test_the_rest_of_the_site_is_copied_unchanged(built):
    for path in (ROOT / "site").rglob("*"):
        if path.is_file() and path.suffix != ".html":
            assert (built / path.relative_to(ROOT / "site")).read_bytes() == path.read_bytes()
    assert not (built / "site").exists()


def test_a_release_without_a_package_keeps_its_card_on_the_release_page(tmp_path, capsys):
    release = dict(RELEASE, assets=[a for a in RELEASE["assets"] if a["name"].endswith("flatpak")])
    path = tmp_path / "release.json"
    path.write_text(json.dumps(release), encoding="utf-8")
    assert site_release.main([str(path), str(ROOT / "site"), str(tmp_path / "out")]) == 0
    html = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert (
        'data-asset="dmg"\n              href="https://github.com/niklastshiang/stickler/releases/latest"'
        in html
    )
    assert "no dmg in v8" in capsys.readouterr().err


def test_an_unreadable_release_stops_the_build(tmp_path):
    bad = tmp_path / "release.json"
    bad.write_text("{", encoding="utf-8")
    shutil.rmtree(tmp_path / "out", ignore_errors=True)
    assert site_release.main([str(bad), str(ROOT / "site"), str(tmp_path / "out")]) == 2
