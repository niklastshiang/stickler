# ADR 0001: Demucs über den gepflegten Fork adefossez/demucs

- Status: angenommen
- Datum: 2026-11-11

## Kontext
Das ursprüngliche Repository `facebookresearch/demucs` ist seit dem 1. Januar 2025 archiviert und nur noch lesbar. Alexandre Défossez, der Hauptautor, pflegt seitdem den Fork `github.com/adefossez/demucs` und bezeichnet ihn als offiziell gepflegte Fassung. Neue Features sind laut seinem Hinweis nicht geplant. Für Stickler gelten zwei Vorgaben: nur Open Source und nur aktiv gepflegte Projekte.

## Entscheidung
Der Separator-Adapter `demucs` installiert Demucs aus `adefossez/demucs`, gepinnt auf einen Commit bzw. ein Release. Das archivierte Meta-Repo und PyPI-Pakete Dritter (z. B. `demucs-infer`, `demucs-torchcodec`) werden nicht verwendet.

## Konsequenzen
- Fixes für Kompatibilität (neue PyTorch-Versionen, torchaudio → torchcodec) kommen aus dem Fork.
- Demucs ist Vergleichsbasis neben neueren Trennern (BS-/Mel-RoFormer), nicht gesetzt.
- Bricht der Fork mit ROCm-Wheels, wird das im Adapter-README dokumentiert und notfalls nur CPU genutzt.

## Quellen
- https://github.com/facebookresearch/demucs (Archiv-Hinweis)
- https://github.com/adefossez/demucs
