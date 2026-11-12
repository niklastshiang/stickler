<h1 align="center">
  <code>STICKLER://DRUMS</code>
</h1>

<p align="center">
  <strong>Song rein, Schlagzeug-Noten raus. Lokal, mit Open-Source-Modellen.</strong><br/>
  <em>Stickler (engl.): Pedant, Korinthenkacker. Und einer, der die Sticks hält.</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/lizenz-MIT-ff8800?style=flat-square&labelColor=0d1117" /></a>
  <img src="https://img.shields.io/badge/python-3.12-ff8800?style=flat-square&logo=python&logoColor=ff8800&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/umgebungen-uv-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/sprache-deutsch%20%F0%9F%87%A9%F0%9F%87%AA-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/modelle-8%20adapter-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/tests-154%20%2B%208%20smoke-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/abdeckung-97%25-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/version-0-ff8800?style=flat-square&labelColor=0d1117" />
  <img src="https://img.shields.io/badge/status-benchmark%20l%C3%A4uft-ff8800?style=flat-square&labelColor=0d1117" />
</p>

<br/>

<pre align="center">
<code>
  ╔═════════════════════════════════════════════════════════════════════════════╗
  ║                                                                             ║
  ║        ███████╗████████╗██╗ ██████╗██╗  ██╗██╗     ███████╗██████╗          ║
  ║        ██╔════╝╚══██╔══╝██║██╔════╝██║ ██╔╝██║     ██╔════╝██╔══██╗         ║
  ║        ███████╗   ██║   ██║██║     █████╔╝ ██║     █████╗  ██████╔╝         ║
  ║        ╚════██║   ██║   ██║██║     ██╔═██╗ ██║     ██╔══╝  ██╔══██╗         ║
  ║        ███████║   ██║   ██║╚██████╗██║  ██╗███████╗███████╗██║  ██║         ║
  ║        ╚══════╝   ╚═╝   ╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝         ║
  ║                                                                             ║
  ║                        🥁 SONG REIN  //  NOTEN RAUS                         ║
  ║         SCHLAGZEUG-NOTEN AUS JEDEM SONG  //  OPEN SOURCE  //  LOKAL         ║
  ║                                                                             ║
  ╚═════════════════════════════════════════════════════════════════════════════╝
</code>
</pre>

---

## `> WAS IST DAS`

**Stickler** wird eine Desktop-Anwendung, die aus einem Song Schlagzeug-Noten macht: MP3
oder FLAC hineinziehen, Noten als MusicXML oder PDF bekommen, in MuseScore nur noch
korrigieren. Mit einer Oberfläche in GTK 4, als Flatpak und AppImage.

**Gerade ist Stickler ein Prüfstand.** Bevor die Anwendung entsteht, muss eine Frage geklärt
sein, die sich nicht durch Lesen von Papern beantworten lässt: **Welche Kombination aus
Drum-Trennung und Transkriptionsmodell liefert die besten Noten?** Gemessen wird auf
Benchmark-Daten und vor allem auf echter Musik. Jedes Modell steckt in einem eigenen
Adapter mit eigener Python-Umgebung und tritt gegen dieselben Referenzen an: Kick, Snare,
Toms, Hi-Hat und Becken, jeder Schlag auf ±50 ms genau. Die Gewinner-Pipeline wird zum
Kern der Anwendung.

Erlaubt sind **nur Open-Source-Modelle aus aktiv gepflegten Projekten.** Kein Cloud-Dienst,
keine Blackbox, alles läuft lokal auf dem eigenen Rechner.

---

## `> WARNUNGEN`

> **⚠ ZAHLEN SIND VORLÄUFIG.** Der erste vollständige Lauf über MDB Drums läuft noch. Die
> Tabelle unten ist eine Stichprobe aus einem einzigen Song.

> **⚠ NUR FÜR DEN PRIVATEN GEBRAUCH.** Einige Gewichte stehen unter Non-Commercial-Lizenzen
> (ADTOF, MuScriptor, vermutlich BS-RoFormer). Für eine Veröffentlichung müssten sie ersetzt
> werden, siehe [ADR 0002](docs/adr/0002-nc-lizenzen.md).

> **⚠ AUF MDB TRAINIERT?** Einige Modelle haben MDB Drums im Training oder in der Auswertung
> gesehen. Der ehrliche Test sind die eigenen Songs.

---

## `> STICHPROBE`

Macro-F1 über 5 Klassen auf MDB `MusicDelta_Punk` (29 s), CPU. **Ein Song, kein Urteil.**

| Transkriber | Original-Mix | Demucs-Stem | Oracle-Stem¹ |
|---|---|---|---|
| **ADTOF** | 0,803 | **0,854** | 0,871 |
| **MuScriptor medium** | **0,825** | 0,813 | – |
| **MuScriptor small** | 0,793 | 0,726 | – |
| **ADT_STR** | –² | 0,790 | 0,811 |
| **YourMT3+** (PS) | 0,588 | – | 0,670 |

¹ Der isolierte Drum-Stem aus dem Datensatz, also eine perfekte Trennung als Obergrenze.<br/>
² ADT_STR verträgt nur getrennte Drum-Spuren und rechnet auf dem Mix ewig.

Auf der Radeon 840M war die GPU bei **jedem** Modell langsamer als die CPU. Die
Benchmark-Läufe rechnen deshalb auf der CPU ([ADR 0003](docs/adr/0003-rocm-kanal.md)).

---

## `> WIE ES FUNKTIONIERT`

```
  Song ──┬──► Trennung ───────► Drum-Stem ───► Transkription ───► drums.mid
         │    none · demucs     (oder Mix)     adtof · adt_str              │
         │    roformer · oracle                muscriptor · yourmt3         │
         │                                                                  ▼
         └──► Beat-Tracking ──► beats.json ──────────────────────► Bewertung gegen
              beat_this                                            die Referenz
                                                                   ±50 ms · 5/3 Klassen
```

- **Ein Adapter je Modell.** Jedes Modell bekommt einen Ordner mit eigenem
  `pyproject.toml` und eigener `uv`-Umgebung. Der Harness ruft es als Subprozess auf und
  importiert nie Modellcode. Ein neuer Kandidat braucht nur einen Ordner und einen
  Config-Eintrag.
- **Alles wird gecacht.** Der Schlüssel aus Eingabe, Adapter-Code und Gerät bestimmt, ob
  ein Ergebnis wiederverwendet wird. Ein abgebrochener Lauf macht dort weiter, wo er stand.
- **Fehler halten nichts auf.** Ein Adapter, der abstürzt oder sein Zeitlimit reißt, wird
  protokolliert. Alle anderen rechnen weiter.

---

## `> KANDIDATEN`

| Stufe | Adapter | Projekt | Lizenz |
|---|---|---|---|
| Trennung | `demucs` | [adefossez/demucs](https://github.com/adefossez/demucs) 4.1, `htdemucs_ft` (gepflegter Fork) | MIT |
| Trennung | `roformer` | [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator), BS-Roformer-SW | MIT / Gewichte ungeklärt |
| Transkription | `adtof` | [ADTOF-pytorch](https://github.com/xavriley/ADTOF-pytorch) (Zehren et al.) | CC BY-NC-SA |
| Transkription | `adt_str` | [ADT_STR](https://huggingface.co/Pierfrancesco/adt-str) (2026), τ = 0,8 | CC BY-SA |
| Transkription | `muscriptor_s`, `muscriptor_m` | [MuScriptor](https://github.com/muscriptor/muscriptor) (Kyutai/IRCAM, 2026) | MIT / Gewichte CC BY-NC |
| Transkription | `yourmt3` | [YourMT3+](https://huggingface.co/spaces/mimbres/YourMT3) YPTF.MoE+Multi (PS) | Apache-2.0 / GPL-3.0 |
| Beats | `beat_this` | [Beat This!](https://github.com/CPJKU/beat_this) (CPJKU, 2024) | MIT |

Jede Modellentscheidung, die nicht offensichtlich war, steht als ADR in
[`docs/adr/`](docs/adr/). Quelle, Version und eigene Messungen stehen im README des
jeweiligen Adapters.

---

## `> EIGENE SONGS`

Benchmark-Daten sind sauber, echte Musik nicht. Deshalb vergleicht Stickler auch mit
eigenen Songs: Noten als MIDI von musescore.com, Aufnahme aus der eigenen Sammlung.

Das Problem ist, dass Noten und Aufnahme nicht zusammen laufen. Intros fehlen, Tempi weichen
ab, Transkribierende lassen Stellen weg. `stickler align` legt die Noten deshalb Schlag für
Schlag auf die Aufnahme. Grundlage sind die Beats von Beat This! und die Rhythmusmuster im
Demucs-Stem, verknüpft per DTW. Passagen ohne Gegenstück werden ausgeklammert.

**Nur gute Referenzen kommen in die Wertung.** Geprüft wird ohne Transkriptionsmodell,
damit die Modelle nicht ihre eigenen Prüfer sind. Die Schwellen sind an MDB kalibriert,
dessen Referenzen nachweislich stimmen:

| Kriterium | Schwelle |
|---|---|
| Notenschläge, deren Beat sauber auf der Aufnahme sitzt (±70 ms) | ≥ 95 % |
| Notenschläge mit hörbarem Anschlag im Drum-Stem (±50 ms) | ≥ 85 % |
| Deutliche Anschläge im Stem, die in den Noten stehen | ≥ 90 % |
| Deutliche Anschläge in ausgeklammerten Bereichen | ≤ 20 % |

Zur Kontrolle mit dem Ohr schreibt `stickler align` je Song eine `click.wav`: links die
Aufnahme, rechts Klicks auf den Notenschlägen.

---

## `> KENNZAHLEN`

```console
scripts/check.sh task
```

```json
{
  "adapter": { "trennung": 2, "transkription": 5, "beats": 1 },
  "datensaetze": { "mdb_drums": 23, "eigene_songs": 10 },
  "tests": 154,
  "smoke_tests_mit_modellen": 8,
  "abdeckung_prozent": 97.5,
  "abdeckung_minimum": 95,
  "adrs": 6,
  "version": 0,
  "status": "benchmark läuft"
}
```

| Wert | Bedeutung |
|---|---|
| `smoke_tests_mit_modellen` | Laufen echte Modelle, deshalb nicht im Standardlauf: `uv run pytest -m adapters` |
| `abdeckung_minimum` | Darunter blockiert der Pre-Commit-Hook. Grenze und Regeln in [`CONSTRAINTS.md`](CONSTRAINTS.md) |
| `eigene_songs` | Beschrieben in `references/own/`. In die Wertung kommt nur, wer die Gütekriterien besteht |

---

## `> FAHRPLAN`

**Erledigt**

- [x] Bewertung nach Klassen, Cache, Zeitlimits, Fehlerprotokoll
- [x] Separatoren Demucs und BS-RoFormer
- [x] Transkriber ADTOF, ADT_STR, MuScriptor small und medium, YourMT3+
- [x] GPU-Weg über ROCm geprüft (langsamer als die CPU, bleibt optional)
- [x] Beat-Tracking mit Beat This!
- [x] Abgleich und Gütekriterien für eigene Songs

**In Arbeit**

- [ ] Vollständiger Lauf über MDB Drums
- [ ] Eigene Songs abgleichen und prüfen
- [ ] Transkriber `drumsep_onset` (DrumSep plus Onset-Erkennung je Trommel)

**Danach: von der Messung zur Anwendung**

- [ ] HTML-Report mit Ranking, Klassen, Laufzeit und Speicher
- [ ] ENST-Drums als dritter Datensatz
- [ ] Noten aus der Gewinner-Pipeline: Quantisierung, MusicXML, `stickler notate`
- [ ] Anwendung mit Oberfläche in GTK 4 und libadwaita
- [ ] Release-Pipeline: Flatpak und AppImage bei jedem Release
- [ ] Alles auf Englisch: Code, Ausgaben und Dokumentation

---

## `> SELBST BAUEN`

### Voraussetzungen

Stickler braucht **`uv`** für die Python-Umgebungen und **`ffmpeg`** zum Dekodieren von
Audio. Alles andere, auch Python 3.12 und PyTorch, holt `uv` je Adapter selbst.

**Fedora, Bluefin und Verwandte**

```console
brew install uv          # oder: curl -LsSf https://astral.sh/uv/install.sh | sh
sudo dnf install ffmpeg-free
```

**Debian, Ubuntu und Verwandte**

```console
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt install ffmpeg
```

### Einrichten

```console
git clone https://github.com/niklastshiang/stickler.git
cd stickler/
uv sync
git config core.hooksPath .githooks    # Prüfungen vor jedem Commit
uv run stickler fetch mdb              # MDB Drums laden (CC BY-NC-SA)
uv run stickler setup                  # alle Adapter-Umgebungen und Gewichte
uv run stickler doctor                 # was fehlt noch?
```

> MuScriptor-Gewichte sind zugangsbeschränkt: Lizenz auf Hugging Face akzeptieren, dann
> `uvx hf auth login`. Das GPU-Setup ist optional: `stickler setup --device rocm`.

### Benchmark

```console
uv run stickler run      # rechnet die Matrix aus config/benchmark.yaml (über Nacht)
uv run stickler eval     # results/metrics.csv und results/summary.csv
uv run stickler align    # eigene Songs abgleichen, prüfen und click.wav schreiben
```

---

## `> ENTSTEHUNG`

<img src="https://img.shields.io/badge/code-Claude%20Code-ff8800?style=flat-square&labelColor=0d1117" />
<img src="https://img.shields.io/badge/entscheidungen-human-ff8800?style=flat-square&labelColor=0d1117" />

**Der Code dieses Projekts stammt von einer KI.** Programmiert, getestet und dokumentiert hat
Claude (Anthropic) in Claude Code.

Vom Projektinhaber kommen die Ziele, die Auswahl der Kandidaten und die Songs. Er trifft
die Entscheidungen und prüft die Ergebnisse mit dem Ohr. Damit der Code dabei nicht
heimlich schlechter wird, gelten feste Leitplanken:

- **Erst die Spezifikation, dann der Code.** Was gebaut wird, steht in
  [`SPEC.md`](SPEC.md), der Plan in [`tasks/`](tasks/). Getroffene Entscheidungen stehen
  in [`docs/adr/`](docs/adr/).
- **Tests zuerst** und eine Mindestabdeckung von 95 %.
- **Ein Floor-Guard prüft jeden Diff.** Er schlägt an, wenn Prüfungen stummgeschaltet,
  Tests übersprungen oder Grenzen gesenkt werden. Ein solcher Commit wird blockiert, siehe
  [`CONSTRAINTS.md`](CONSTRAINTS.md).
- **Messen statt behaupten.** Jede Modellwahl ist mit Messwerten begründet, auch wenn das
  Ergebnis unbequem ist.

---

## `> AUFBAU DES REPOSITORYS`

```
stickler/
├── src/stickler/        # Harness: api, cli, runner, align, onsets, evaluate, datasets/
├── adapters/            # ein Ordner je Modell, jeder mit eigener uv-Umgebung
│   ├── _common/         # gemeinsame Helfer: Geräteauswahl, meta.json, Drum-MIDI
│   ├── separators/      # demucs, roformer
│   ├── transcribers/    # adtof, adt_str, muscriptor_s, muscriptor_m, yourmt3
│   └── beats/           # beat_this
├── config/              # benchmark.yaml (Matrix), classes.yaml (GM-Pitch → Klasse)
├── references/own/      # eigene Songs: Titel, Aufnahme, manuelle Ausschlüsse
├── tests/               # pytest; Smoke-Tests mit echten Modellen unter -m adapters
├── scripts/             # check.sh, floor_guard.py
├── docs/adr/            # Architecture Decision Records
├── tasks/               # Plan und Aufgabenliste
└── data/ cache/ results/   # Datensätze, Zwischenergebnisse, Auswertung (nicht im Repo)
```

---

## `> LIZENZ`

**Der Code von Stickler** steht unter [**MIT**](LICENSE). Das gilt für Harness, Adapter,
Skripte, Tests und Dokumentation. Benutzen, ändern, weitergeben und verkaufen ist erlaubt,
solange der Urheberrechtsvermerk dabei bleibt.

**Die Modelle** sind davon nicht berührt. Stickler lädt sie erst bei
`stickler setup` herunter, sie liegen nicht im Repository und bringen ihre eigenen
Lizenzen mit, siehe [`> KANDIDATEN`](#-kandidaten). Gewichte unter Non-Commercial-Lizenzen
sind nur für den privaten Gebrauch zugelassen ([ADR 0002](docs/adr/0002-nc-lizenzen.md)).
Wer Stickler verteilt, muss sie weglassen oder ersetzen.

**Daten:** MDB Drums steht unter CC BY-NC-SA 4.0. Noten und Aufnahmen der eigenen Songs
gehören ihren Urhebern und liegen deshalb nicht im Repository.

---

<p align="center">
  <strong><code>> ZÄHL MIT. DER STICKLER TUT ES SOWIESO._</code></strong>
</p>
