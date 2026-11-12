# ADR 0004: RoFormer-Separator mit Checkpoint „BS-Roformer-SW“ über python-audio-separator

- Status: angenommen (Herkunft der Gewichte nur teilweise geklärt, siehe unten)
- Datum: 2026-11-11

## Kontext
Band-Split- und Mel-Band-RoFormer gelten in der Community als aktueller Stand der Musik-Quellentrennung. Die Architektur ist offen implementiert ([lucidrains/BS-RoFormer](https://github.com/lucidrains/BS-RoFormer), MIT). Trainierte Gewichte stammen dagegen fast immer aus der Community (ZFTurbo/MSST, MVSEP, UVR) und sind unterschiedlich gut dokumentiert. Stickler braucht einen Checkpoint mit **eigenem Drum-Stem**. Reine Vocal/Instrumental-Modelle helfen nicht.

`python-audio-separator` 0.48.0 (MIT, 2026-10-29) listet unter 172 Modellen genau einen RoFormer mit eigenem Drum-Stem: **BS-Roformer-SW** von jarredou (6 Stems: bass, drums, guitar, other, piano, vocals). Die übrigen Treffer sind Demucs (eigener Adapter), MDX-Net 2021 (kuielab) und BS-Roformer-Viperx-1053, das nur „drum-bass“ gemeinsam trennt.

## Entscheidung
Adapter `roformer` = `audio-separator[cpu]==0.48.0` + `BS-Roformer-SW.ckpt`, Standardparameter der Bibliothek, nur der Stem „Drums“.

## Herkunft und Lizenz (offen)
- Autor laut audio-separator und MVSEP: jarredou. Das ursprüngliche Hugging-Face-Konto wurde laut [openmirlab/bs-roformer-infer](https://github.com/openmirlab/bs-roformer-infer) gelöscht (2026-06). Mirror: `enerjazzer/BS-ROFO-SW-Fixed`.
- Lizenz: Nur eine Sekundärquelle nennt CC BY-NC-SA 4.0 ([Ryan5453/unblend](https://huggingface.co/Ryan5453/unblend)). Ein Originaltext wurde nicht gefunden. Nach ADR 0002 ist NC für private Nutzung zulässig.
- Trainingsdaten: unbekannt. Eine Überschneidung mit MDB/MedleyDB ist nicht auszuschließen. Der Report kennzeichnet das.
- Reproduzierbarkeit: audio-separator prüft den Download per SHA-256 (`24e7d35e…916e`).

## Konsequenzen
- Für eine spätere Veröffentlichung (z. B. GTK-App) ist dieser Checkpoint **ungeeignet**, solange die Lizenz nicht geklärt ist.
- `audio-separator` 0.48.0 deklariert die Abhängigkeit `audioread` nicht, importiert sie aber. Der Adapter ergänzt sie.
- Eigenes Training mit lucidrains/BS-RoFormer oder ZFTurbo/MSST wäre die lizenzsaubere Alternative. Auf der Radeon 840M ist das aber nicht realistisch (siehe ADR 0003).
