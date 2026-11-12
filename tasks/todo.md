# Aufgaben: Stickler

Jede Aufgabe ist erst erledigt, wenn `scripts/check.sh task` grün ist und ein Commit pro Aufgabe gemacht wurde (siehe CONSTRAINTS.md).

## Phase 0: Doku

- [x] **Task 0: ADRs für getroffene Entscheidungen** (XS)
  - Acceptance: `docs/adr/0001-demucs-fork.md` (adefossez/demucs statt archiviertem Repo) und `0002-nc-lizenzen.md` (NC-Gewichte für private Nutzung erlaubt), jeweils mit Kontext, Entscheidung und Konsequenzen.
  - Verify: Dateien vorhanden, in SPEC.md verlinkt.
  - Dependencies: keine · Files: `docs/adr/*`, `SPEC.md`

## Phase 1: Durchstich (`none` × `adt_str` auf MDB)

- [x] **Task 1: Klassen-Mapping und Bewertung** (M)
  - Acceptance:
    - `Onsets`-Datenklasse.
    - `config/classes.yaml` + `classes.py` bilden GM-Pitches auf das 5er-Schema (KD/SD/TT/HH/CY) und das 3er-Schema (KD/SD/HH) ab.
    - `evaluate.score()` liefert P/R/F1 je Klasse sowie Micro und Macro.
    - Selbstvergleich ergibt F1 = 1,0, ein Versatz von 60 ms zählt als Fehler, einer von 40 ms als Treffer (Success Criterion 1).
  - Verify: `uv run pytest tests/test_evaluate.py tests/test_classes.py`
  - Dependencies: keine · Files: `src/stickler/{classes,evaluate}.py`, `config/classes.yaml`, Tests

- [x] **Task 2: MDB-Drums-Loader und `stickler fetch mdb`** (M)
  - Acceptance:
    - `api.fetch_dataset("mdb")` lädt MDB Drums nach `data/mdb/`, und zwar idempotent.
    - `datasets/mdb.py` liefert pro Track: Mix-Pfad, Drum-Stem-Pfad und Referenz als `Onsets`.
    - Die CLI ruft nur die API auf (Test für Success Criterion 9).
  - Verify:
    - Unit-Test mit Mini-Fixture der Annotationsdatei.
    - `uv run stickler fetch mdb` meldet 23 Tracks.
  - Dependencies: 1 · Files: `src/stickler/{api,cli}.py`, `src/stickler/datasets/mdb.py`, Tests

- [x] **Task 3: Adapter-Vertrag und Dummy-Adapter** (M)
  - Acceptance:
    - `adapters.py` ruft Adapter per `uv run --project` auf, liest `meta.json` und protokolliert Fehler, ohne abzubrechen.
    - `adapters/_common` stellt Geräte-Wahl, Zeitmessung und Peak-RSS bereit.
    - Ein Dummy-Transkriber unter `tests/fixtures/` lässt sich nur per Config einbinden (Success Criterion 6).
  - Verify: `uv run pytest tests/test_adapters.py`
  - Dependencies: 1 · Files: `src/stickler/adapters.py`, `adapters/_common/*`, Tests/Fixtures

- [x] **Task 4: Transkriber-Adapter `adt_str` (CPU)** (M)
  - Acceptance:
    - `stickler setup --adapter adt_str` baut die Umgebung und lädt `setting-tau-0.8`.
    - `run.py` schreibt `drums.mid` mit GM-Pitches und `meta.json`.
    - Das Adapter-README nennt Quelle, Commit und Lizenz.
  - Verify:
    - `uv run pytest -m adapters -k adt_str` (10-s-Clip → gültiges MIDI).
    - Manuell: das MIDI eines MDB-Tracks in MuseScore ansehen.
  - Dependencies: 3 · Files: `adapters/transcribers/adt_str/*`, `src/stickler/api.py` (setup)

- [ ] **Task 5: `stickler run` und `stickler eval` mit Cache** (M)
  - Acceptance:
    - `run` rechnet die in `config/benchmark.yaml` aktiven Kombinationen über einen Datensatz.
    - `eval` schreibt `results/metrics.csv`.
    - Ein zweiter `run` hat nur Cache-Treffer (Success Criterion 7).
  - Verify:
    - Unit-Test mit Dummy-Adapter (Cache, CSV-Spalten).
    - Echter Lauf `none` × `adt_str` über MDB.
  - Dependencies: 2, 3, 4 · Files: `src/stickler/{api,cli,runner,cache}.py`, `config/benchmark.yaml`, Tests

### Checkpoint A
- [ ] Alle Tests grün, `metrics.csv` mit plausiblen F1-Werten für `none` × `adt_str` (KD deutlich > 0,5)
- [ ] Review mit dem User

## Phase 2: GPU (früh, weil riskant)

- [x] **Task 6: ROCm-Spike und `stickler doctor`** (M)
  - Acceptance:
    - `setup --device rocm` installiert `torch[device-gfx1152]` in die Umgebung von `adt_str`.
    - `doctor` meldet GPU, Umgebungen, HF-Login und MuseScore.
    - GPU- und CPU-Ergebnisse weichen um höchstens 0,01 F1 ab, die Laufzeiten werden verglichen.
    - Die Entscheidung über den Kanal (7.14 vs. 10.x) steht in `docs/adr/0003-rocm-kanal.md`.
  - Verify: `uv run stickler doctor`, Vergleichslauf auf 3 MDB-Tracks
  - Dependencies: 5 · Files: `src/stickler/{api,doctor}.py`, `adapters/_common/*`, ADR

## Phase 3: Kandidaten in die Breite

- [x] **Task 7: Separator `demucs` (adefossez-Fork, `htdemucs_ft`)** (S)
  - Acceptance: liefert `drums.wav`, cpu und rocm. README mit Quelle, Commit und Lizenz.
  - Verify: `pytest -m adapters -k demucs`, Lauf `demucs` × `adt_str` auf MDB
  - Dependencies: 5 (6 für rocm) · Files: `adapters/separators/demucs/*`, `config/benchmark.yaml`

- [x] **Task 8: Separator `roformer` (python-audio-separator)** (S)
  - Acceptance: Checkpoint mit Drum-Stem gewählt und begründet in `docs/adr/0004-roformer-checkpoint.md`. Liefert `drums.wav`.
  - Verify: `pytest -m adapters -k roformer`, Lauf auf MDB
  - Dependencies: 5 · Files: `adapters/separators/roformer/*`, ADR

- [x] **Task 9: Transkriber `adtof` (ADTOF-pytorch)** (M)
  - Acceptance: 5 Klassen auf GM-Pitches gemappt, gültiges MIDI.
  - Verify: `pytest -m adapters -k adtof`, Lauf auf MDB
  - Dependencies: 5 · Files: `adapters/transcribers/adtof/*`, `config/classes.yaml`

- [x] **Task 10: Transkriber `muscriptor_s` und `muscriptor_m`** (M)
  - Acceptance: Es wird nur die Drum-Spur aus der Mehrinstrumenten-Ausgabe übernommen. Fehlt der HF-Login, kommt eine klare Fehlermeldung.
  - Verify: `pytest -m adapters -k muscriptor`, Lauf auf MDB
  - Dependencies: 5, User-Login · Files: `adapters/transcribers/muscriptor/*`

- [x] **Task 11: Transkriber `yourmt3`** (M, Risiko): im ersten Anlauf lauffähig; Smoke-Test auf 10 s MDB-Mix, weil das Modell im synthetischen Clip nichts erkennt
  - Acceptance: Die Inferenz aus dem HF-Space-Code läuft lokal mit gepinntem Commit, die Drum-Spur kommt als GM-MIDI heraus. Scheitert das nach 2 Anläufen: Kandidat per ADR streichen.
  - Verify: `pytest -m adapters -k yourmt3`
  - Dependencies: 5 · Files: `adapters/transcribers/yourmt3/*`

- [ ] **Task 12: Transkriber `drumsep_onset`** (M)
  - Acceptance: Das 6-Stem-Modell DrumSep (MDX23C) und eine librosa-Onset-Erkennung pro Stem ergeben ein GM-MIDI.
  - Verify: `pytest -m adapters -k drumsep`, Lauf auf MDB
  - Dependencies: 5 · Files: `adapters/transcribers/drumsep_onset/*`

### Checkpoint B
- [ ] Volle Matrix auf MDB: jede Kombination liefert ein MIDI oder einen protokollierten Fehler (Success Criterion 2)
- [ ] Review mit dem User

## Phase 4: Report und eigene Songs

- [ ] **Task 13: HTML-Report** (M)
  - Acceptance:
    - `stickler report` erzeugt `results/report.html`.
    - Inhalt: Ranking nach Macro-F1, F1 pro Klasse (5er/3er), Laufzeit, RTF, RAM und CPU vs. GPU.
    - Hinweis zur möglichen Trainingsdaten-Überschneidung bei MDB.
  - Verify: Unit-Test auf den Inhalt; manuell im Browser öffnen
  - Dependencies: 5 · Files: `src/stickler/report.py`, `templates/report.html.j2`, Tests

- [x] **Task 14: Beat-Adapter `beat_this`** (S): nur CPU (15 s je Song); ROCm entfällt wie bei ADTOF, weil die GPU bisher nie schneller war (ADR 0003)
  - Acceptance: `beats.json` mit Beats und Downbeats, cpu und rocm.
  - Verify: `pytest -m adapters -k beat_this`
  - Dependencies: 3 · Files: `adapters/beats/beat_this/*`

- [ ] **Task 15: Eigene Songs: Loader, Alignment, Click-Check** (M)
  - Acceptance:
    - `references/own/<song>.mid` + `.yaml` werden über die Beat-Positionen auf die Audio-Zeit gelegt.
    - `stickler align` erzeugt eine Click-Check-WAV.
    - Der Song geht in `run`/`eval` ein (Success Criterion 4).
  - Verify: Unit-Tests für `align` (synthetisches Tempo-Rubato); der User hört die Click-Check-WAV ab
  - Dependencies: 5, 14, User-MIDI · Files: `src/stickler/{align,datasets/own}.py`, Tests

- [ ] **Task 16: ENST-Antrag und Loader** (S)
  - Acceptance: `docs/enst-antrag.md` als Entwurf für den User. `datasets/enst.py` lädt den Datensatz, sobald `data/enst/` existiert, sonst wird er übersprungen.
  - Verify: Unit-Test mit Mini-Fixture
  - Dependencies: 1 · Files: `docs/enst-antrag.md`, `src/stickler/datasets/enst.py`, Tests

### Checkpoint C
- [ ] Report mit MDB und mindestens einem eigenen Song (Success Criteria 3 und 4)
- [ ] Review mit dem User: Gewinner-Pipeline wählen, `docs/adr/0005-gewinner-pipeline.md`

## Phase 5: Noten

- [ ] **Task 17: Quantisierung und MusicXML** (M)
  - Acceptance:
    - `notation.py` quantisiert auf das Beat-Raster (1/16 und Achteltriolen) und filtert Ghost Notes per Velocity-Schwelle.
    - MusicXML mit Taktart, Percussion-Notenzeile und Notenköpfen für Becken.
  - Verify: Unit-Tests (Quantisierung, Triolen-Erkennung, gültiges MusicXML per music21-Roundtrip)
  - Dependencies: 14 · Files: `src/stickler/notation.py`, Tests

- [ ] **Task 18: `stickler notate` von Ende zu Ende** (S)
  - Acceptance: Audio → Gewinner-Pipeline → MusicXML. PDF, falls MuseScore 4 (Flatpak) installiert ist (Success Criterion 5).
  - Verify: „Easy Fill Ins“ notieren, in MuseScore öffnen und mit dem Original-PDF vergleichen
  - Dependencies: 13, 17 · Files: `src/stickler/{api,cli}.py`

### Checkpoint D
- [ ] Alle 9 Success Criteria aus SPEC.md erfüllt
- [ ] Abschluss-Review mit dem User
