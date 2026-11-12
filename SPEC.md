# Spec: Stickler

> Benchmark für automatische Schlagzeug-Transkription (Audio → Noten) mit ausschließlich Open-Source-Modellen.
> Stand: 2026-11-11 · Status: **freigegeben** (mit Ergänzungen GPU + spätere GTK-Oberfläche)

## Annahmen
1. Einziger Nutzer ist der Projektinhaber, Nutzung privat. Gewichte unter NC-Lizenz (ADTOF, MuScriptor) sind erlaubt.
2. Alles läuft lokal: Ryzen AI 5 340, 30 GB RAM, iGPU Radeon 840M (**gfx1152**, RDNA 3.5, teilt sich den Arbeitsspeicher). **GPU wird genutzt, wo möglich** (PyTorch-ROCm-Wheels von AMD). Jeder Adapter muss aber auch auf der CPU laufen, als Fallback.
3. Laufzeit ist zweitrangig, Genauigkeit zählt. Ein kompletter Benchmark-Lauf darf über Nacht dauern, weil Ergebnisse gecacht werden.
4. Bedienung in v1 über die Kommandozeile. Der Report ist eine lokale HTML-Datei. **Später kommt eine GTK-Oberfläche** (GTK 4 + libadwaita über PyGObject, passend zu GNOME/Bluefin). Deshalb liegt die Logik in einer Bibliotheks-API, und die CLI ist nur eine dünne Schicht darüber.
5. Erst nur Schlagzeug. Andere Instrumente kommen später als neue Adapter dazu, ohne den Kern umzubauen.

## Objective
Herausfinden, **welche Kombination aus Drum-Stem-Trennung und Transkriptionsmodell die besten Schlagzeug-Noten liefert**, und zwar auf öffentlichen Testdaten und auf den eigenen Songs (Metal/Elektro, z. B. Electric Callboy). Die beste Pipeline erzeugt am Ende MusicXML bzw. PDF-Noten.

User Stories:
- Als Schlagzeuger will ich einen Song hineingeben und Noten bekommen, die ich in MuseScore nur noch korrigieren muss.
- Als Entwickler will ich ein neues Modell mit einem Adapter-Ordner und einem Config-Eintrag in den Vergleich aufnehmen.
- Als Entwickler will ich in einer Tabelle sehen, welche Pipeline pro Instrumentenklasse (Kick, Snare, Toms, Hi-Hat, Becken) am besten abschneidet.

### Kandidaten
| Stufe | ID | Projekt | Lizenz |
|---|---|---|---|
| Trennung | `none` | Original-Mix | – |
| Trennung | `demucs` | adefossez/demucs (gepflegter Fork), `htdemucs_ft` | MIT |
| Trennung | `roformer` | nomadkaraoke/python-audio-separator + BS-/Mel-RoFormer-Checkpoint mit Drum-Stem | MIT, Checkpoint prüfen |
| Transkription | `adtof` | ADTOF-pytorch (Zehren), 5 Klassen | CC BY-NC-SA |
| Transkription | `adt_str` | pier-maker92/ADT_STR (2026), `setting-tau-0.8`, 26 Klassen | CC BY-SA |
| Transkription | `muscriptor_s`, `muscriptor_m` | muscriptor/muscriptor (2026), small/medium | MIT / Gewichte CC BY-NC |
| Transkription | `yourmt3` | mimbres/YourMT3 (YourMT3+ YPTF.MoE+Multi) | GPL-3.0 |
| Transkription | `drumsep_onset` | DrumSep MDX23C 6-Stem + librosa-Onsets pro Stem | Community |
| Beats | `beat_this` | CPJKU/beat_this | MIT |

## Tech Stack
- Python **3.12** und `uv` ≥ 0.13 (Homebrew). Jede Umgebung wird mit `uv` verwaltet.
- Harness: `mir_eval`, `pretty_midi`, `music21`, `librosa`, `pandas`, `pyyaml`, `jinja2`, `typer`.
- Dev: `pytest`, `ruff`.
- Jeder Adapter hat sein **eigenes** `pyproject.toml` mit eigener Umgebung (Torch-CPU-Wheels). Der Harness importiert nie Modellcode, er ruft Adapter als Subprozess auf.
- Optional: MuseScore 4 (Flatpak) für den PDF-Export.

### GPU (AMD ROCm)
- PyTorch-Wheels von AMD für `gfx1152` mit gebündelter ROCm-Runtime, kein System-ROCm nötig: Index `https://repo.amd.com/rocm/whl-multi-arch/` (ROCm 7.14.x) oder `https://stable.repo.amd.com/rocm/whl-next/` (ROCm 10.x), Paket `torch[device-gfx1152]`. Welcher Kanal stabil läuft, wird per ADR entschieden.
- `/dev/kfd` und `/dev/dri/renderD128` sind vorhanden und für den User zugänglich, der Kernel ist 7.2 (amdgpu).
- Jeder Adapter-Env gibt es in zwei Varianten: `cpu` (Standard-Torch-CPU-Wheels) und `rocm`. Sie wird per `stickler setup --device rocm` gewählt.
- Adapter bekommen `--device auto|cpu|gpu`. `auto` nimmt die GPU, wenn `torch.cuda.is_available()`, sonst die CPU. Das tatsächlich genutzte Gerät steht in `meta.json`.
- Nicht-Torch-Modelle (z. B. ONNX) laufen auf der CPU, solange es keinen funktionierenden ROCm/MIGraphX-Provider gibt.

### Später: GTK-Oberfläche (nicht Teil von v1)
- GTK 4 + libadwaita via PyGObject, eigenes Paket `stickler-gtk`, das nur `stickler.api` nutzt.
- Damit das klappt, braucht v1: eine öffentliche API in `stickler/api.py` (`run_benchmark`, `evaluate`, `transcribe_song`, `notate`) mit Fortschritts-Callbacks und Abbruchmöglichkeit, keine `print`s in der Logik (Logging stattdessen) und Ergebnisse als Datenobjekte, nicht nur als Dateien.

## Commands
```bash
uv sync                                         # Harness-Umgebung
uv run pytest -q                                # Tests
uv run ruff check --fix . && uv run ruff format .   # Lint/Format
uv run stickler setup --adapter adt_str --device rocm   # Adapter-Env (cpu|rocm) bauen + Gewichte laden; ohne --adapter: alle
uv run stickler doctor                          # prüft GPU, Envs, Gewichte, HF-Login, MuseScore
uv run stickler fetch mdb                       # MDB Drums nach data/mdb/
uv run stickler run   --config config/benchmark.yaml --device auto   # Matrix rechnen (gecacht)
uv run stickler eval  --config config/benchmark.yaml        # Metriken → results/metrics.csv
uv run stickler report                                       # → results/report.html
uv run stickler align [song]                                 # eigene Referenzen abgleichen, prüfen + click.wav
uv run stickler notate --audio song.mp3 --pipeline roformer+adt_str   # → MusicXML (+ PDF, falls MuseScore da)
```

## Project Structure
```
SPEC.md, CONSTRAINTS.md, README.md
pyproject.toml                 # Harness-Paket "stickler"
src/stickler/
  api.py                       # öffentliche API (für CLI und spätere GTK-App)
  cli.py                       # dünne typer-CLI über api.py
  adapters.py                  # Subprozess-Aufruf + Adapter-Vertrag
  classes.py                   # GM-Pitch → Klassen-Mapping (5er/3er)
  datasets/mdb.py, own.py      # Loader → einheitliche Referenz (Onsets je Klasse)
  align.py                     # Partitur-Beats → Audio-Beats
  evaluate.py                  # mir_eval-Metriken
  report.py                    # CSV + HTML
  notation.py                  # Quantisierung + MusicXML
config/benchmark.yaml          # aktive Separatoren/Transkriber/Datensätze
config/classes.yaml            # Mapping-Tabelle
adapters/separators/<id>/      # pyproject.toml + run.py + README.md (Quelle, Lizenz, Version)
adapters/transcribers/<id>/
adapters/beats/beat_this/
adapters/_common/             # gemeinsame Helfer: device-Wahl, meta.json, Zeitmessung
references/own/<song>.yaml                 # Titel, Pfad zur Aufnahme, manuelle Ausschlüsse
data/own/<song>/score.mid, aligned.json, click.wav   # Partitur (musescore.com) und Abgleich, nicht im Repo
tests/                         # pytest, spiegelt src/stickler/
docs/adr/                      # Architecture Decision Records
data/ cache/ results/          # gitignored
```

**Adapter-Vertrag** (verbindlich):
```bash
uv run --project adapters/<stufe>/<id> python adapters/<stufe>/<id>/run.py --in <audio> --out <dir>
```
- Separator → `<dir>/drums.wav`
- Transkriber → `<dir>/drums.mid` (GM-Drum-Pitches, Kanal 10)
- Beats → `<dir>/beats.json` (`{"beats": [...], "downbeats": [...]}`)
- alle → `<dir>/meta.json` (`{"adapter", "version", "device", "seconds", "peak_rss_mb"}`)
- Optionen: `--device auto|cpu|gpu`
- Exit-Code ≠ 0 heißt Fehler. Der Harness protokolliert ihn und rechnet weiter.
- Optional im Adapter-`pyproject.toml`:
  - `[tool.stickler] input = "stem"`: Der Transkriber verträgt nur getrennte Drum-Stems und wird nicht mit `none` kombiniert (z. B. ADT_STR).
  - `[tool.stickler.rocm]`: GPU-Variante (ADR 0003).
- `config/benchmark.yaml` → `timeout`: Zeitlimit je Adapter-Aufruf. Eine Überschreitung zählt als Fehler „Zeitlimit“.
  Je Stufe entweder feste Sekunden (`separators: 1800`) oder relativ zur Audiodauer
  (`transcribers: {factor: 10, min: 120}` = 10 × Songlänge, mindestens 120 s; Dauer per `ffprobe`).

**Eigene Songs (Referenz und Gütekriterien):**
- Partitur als MIDI von musescore.com (Wiederholungen ausgeschrieben); `stickler align` legt sie über Beat This! und Rhythmusmuster des Demucs-Stems per DTW auf die Aufnahme (`src/stickler/align.py`).
- Nicht bewertet werden: Audio ohne Gegenstück in den Noten, Notenlücken mit Spiel im Audio (≥ 1 Takt), manuelle Ausschlüsse aus der YAML. Noten in diesen Bereichen zählen weder für die Referenz noch für die Modelle.
- Ein Song geht nur in den Benchmark ein, wenn er alle Kriterien erfüllt (Vorgabe des Users: nur mindestens gute Referenzen). Geprüft ohne Transkriptionsmodell, mit Onsets aus dem spektralen Fluss des Demucs-Stems (Detektor-Vorlauf 11 ms an MDB gemessen und korrigiert):

| Kriterium | Schwelle | Kalibrierung an MDB (korrekte Referenzen, Demucs-Stem) |
|---|---|---|
| Notenschläge, deren Beat gepaart ist und ±70 ms auf einem Beat-This!-Beat sitzt | ≥ 95 % | – |
| Notenschläge mit Onset im Stem (±50 ms) | ≥ 85 % | Median 98 %, schlechtester 88,5 % |
| deutliche Onsets (stärkste 20 %) mit Notenschlag (±50 ms) | ≥ 90 % | Median 100 %, schlechtester 92 % |
| deutliche Onsets in ausgeklammerten Bereichen | ≤ 20 % | – |

## Code Style
ruff mit Standardregeln und Zeilenlänge 100. Durchgehend Type Hints, `dataclass`es statt Dicts für Domänenobjekte, keine globalen Zustände. Kommentare und Docstrings auf Deutsch, Bezeichner auf Englisch.
```python
@dataclass(frozen=True)
class Onsets:
    """Onset-Zeiten in Sekunden je Instrumentenklasse."""

    by_class: dict[str, np.ndarray]


def score(ref: Onsets, est: Onsets, window: float = 0.05) -> dict[str, PRF]:
    """Precision/Recall/F1 je Klasse nach mir_eval.onset (Standard: ±50 ms)."""
    return {
        cls: PRF(
            *mir_eval.onset.f_measure(ref.by_class[cls], est.by_class.get(cls, EMPTY), window)
        )[::-1]
        for cls in ref.by_class
    }
```

## Testing Strategy
- **pytest**, Tests unter `tests/`, Test zuerst (red → green → refactor).
- Unit-Tests ohne Modelle und Netz: `classes`, `evaluate`, `align`, `notation`, Dataset-Loader (mit Mini-Fixtures in `tests/fixtures/`).
- Adapter-Smoke-Tests (`pytest -m adapters`, nicht im Standardlauf): 10 s Testaudio, geprüft wird gültiges MIDI und `meta.json`.
- Abdeckung ≥ 95 % für `src/stickler/` außer `cli.py`.

## Boundaries
- **Always:** Releases fortlaufend nummerieren (1, 2, 3 …, Tag `vN`, ADR 0006); Tests vor jedem Commit; ein Commit pro Task; die Quelle (offizielle README/Paper, Version/Commit-Hash) im Adapter-README; Lizenz jedes Modells dokumentieren.
- **Ask first:** neue Harness-Abhängigkeiten; einen neuen Modellkandidaten aufnehmen oder einen streichen; Bewertungsparameter ändern (Toleranzfenster, Klassen-Mapping); größere Downloads (> 2 GB).
- **Never:** Audio, Datensätze oder Modellgewichte committen; proprietäre oder Closed-Source-Dienste nutzen; Tests abschwächen oder überspringen, um grün zu werden; das archivierte facebookresearch/demucs verwenden.

## Success Criteria
1. `evaluate`: Referenz gegen sich selbst ergibt F1 = 1,0. Ein um 60 ms verschobener Onset zählt als Fehler, einer um 40 ms als Treffer.
2. Für alle 23 MDB-Drums-Tracks liefert jede aktive Kombination Separator × Transkriber ein MIDI oder einen protokollierten Fehler mit Ursache.
3. `results/metrics.csv` und `results/report.html` enthalten pro Kombination und Datensatz: P/R/F1 je Klasse (5er und 3er), Micro- und Macro-F1, Laufzeit, RTF und Peak-RAM, dazu ein Ranking.
4. Mindestens ein eigener Song besteht die Gütekriterien (Click-Check-WAV vorhanden, vom User abgehört) und ist im Report enthalten.
5. `stickler notate` erzeugt für einen eigenen Song MusicXML, das sich in MuseScore 4 fehlerfrei öffnen lässt und Taktart sowie Drum-Notation enthält.
6. Ein Dummy-Adapter lässt sich mit einem neuen Ordner und einem Config-Eintrag ohne Änderung an `src/` einbinden (per Test geprüft).
7. Ein zweiter `run` ohne Änderungen rechnet nichts neu (Cache-Treffer).
8. `stickler doctor` erkennt die Radeon 840M. Mindestens die Torch-Adapter (Demucs, RoFormer, ADT_STR, MuScriptor) laufen mit `--device gpu`. Die Ergebnisse weichen von CPU-Läufen um höchstens 0,01 F1 ab. Laufzeiten CPU vs. GPU stehen im Report.
9. Die CLI enthält keine Logik außer Argument-Parsing und Ausgabe. Alles läuft über `stickler.api` (per Test geprüft), damit die GTK-Oberfläche später darauf aufsetzen kann.

## Entscheidungen (ADRs)
- [0001 Demucs über den Fork adefossez/demucs](docs/adr/0001-demucs-fork.md)
- [0002 NC-Lizenzen erlaubt](docs/adr/0002-nc-lizenzen.md)
- [0003 GPU über AMD-ROCm-Wheels](docs/adr/0003-rocm-kanal.md)
- [0004 RoFormer-Checkpoint BS-Roformer-SW](docs/adr/0004-roformer-checkpoint.md)
- [0005 YourMT3+-Variante PS](docs/adr/0005-yourmt3-variante.md)
- [0006 Fortlaufende Versionsnummern](docs/adr/0006-versionierung.md)

## Geklärte Fragen
1. MuScriptor: Der User akzeptiert die Lizenz auf Hugging Face und loggt sich per `uvx hf auth login` ein.
2. ENST-Drums: Ich formuliere den Antrag vor, der User stellt ihn. Bis die Daten da sind, laufen MDB und die eigenen Songs.
3. RoFormer-Checkpoint: Auswahl beim Bau des Adapters, festgehalten als ADR.
4. Report: lokale HTML-Datei.

## Open Questions
- keine
