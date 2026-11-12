# ADR 0006: Fortlaufende Versionsnummern statt SemVer

- Status: angenommen
- Datum: 2026-11-12

## Kontext
Stickler ist ein privates Werkzeug ohne fremde Nutzer, die sich auf API-Kompatibilität verlassen.
Die Unterscheidung von Major, Minor und Patch bringt hier keinen Nutzen. Der Projektinhaber wünscht
schlichte Release-Nummern, die bei jedem Release um eins steigen, ähnlich wie bei Firefox.

## Entscheidung
- **Format:** Die Version ist eine Ganzzahl. `0` steht für den Stand vor dem ersten Release, danach folgen `1`, `2`, `3` und so weiter.
- **Release-Schritte:**
  1. Version in `pyproject.toml` und `src/stickler/__init__.py` um eins erhöhen.
  2. Commit „Release N“ anlegen.
  3. Git-Tag `vN` setzen und mit `git push --tags` hochladen.
- **Kompatibilität:** Eine einzelne Ganzzahl ist PEP-440-konform, `uv` und `importlib.metadata` kommen damit zurecht.
- **Adapter:** Die Versionen in den Adapter-`pyproject.toml` (`package = false`) werden nicht veröffentlicht und bleiben unberührt. Maßgeblich ist das jeweilige Modell (Version oder Commit), dokumentiert in `meta.json` und im README des Adapters.

## Konsequenzen
- Am Versionssprung lässt sich nicht ablesen, ob ein Release inkompatibel ist. Was sich geändert hat, steht in der Release-Beschreibung.
- Ein Test prüft, dass die Version eine Ganzzahl ist und Paket und `pyproject.toml` übereinstimmen.
