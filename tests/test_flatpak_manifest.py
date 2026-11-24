"""The Flatpak's manifest (SPEC.md, module `packaging`)."""

from pathlib import Path

import yaml

MANIFEST = Path(__file__).resolve().parents[1] / "packaging" / "flatpak" / "ng.tshia.Stickler.yml"


def test_the_translations_stay_inside_the_app():
    """flatpak-builder moves share/locale into a separate .Locale extension by default, which a
    single-file bundle (`flatpak build-bundle`, the release's Stickler-<v>.flatpak) does not
    carry: the app then showed its own texts in English and GTK's in German (owner,
    2026-11-22). With separate-locales off, the .mo files ship inside the app."""
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert manifest.get("separate-locales") is False
