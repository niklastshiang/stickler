"""Translations through gettext, domain `stickler` (SPEC.md, module `app-shell`).

Every text the app shows goes through `_()`; `N_()` only marks a string for extraction where
it is translated later (constants). The catalogues are `<localedir>/<lang>/LC_MESSAGES/
stickler.mo`: in development `scripts/gtk.sh` builds them from `po/` into the app environment,
in the Flatpak they are installed under `/app/share/locale`. No GTK here: the app's logic uses
the same functions."""

from __future__ import annotations

import gettext
import sys
from pathlib import Path

DOMAIN = "stickler"

_translation: gettext.NullTranslations = gettext.NullTranslations()


def default_localedir() -> Path:
    return Path(sys.prefix) / "share" / "locale"


def setup(localedir: Path | None = None) -> None:
    """Loads the catalogue for the user's language (LANGUAGE, LC_ALL, LC_MESSAGES, LANG);
    without one, the English source texts stay."""
    global _translation
    _translation = gettext.translation(DOMAIN, localedir or default_localedir(), fallback=True)


def translation() -> gettext.NullTranslations:
    return _translation


def _(message: str) -> str:
    return _translation.gettext(message)


def N_(message: str) -> str:
    return message
