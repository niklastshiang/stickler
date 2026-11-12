# ADR 0005: YourMT3+ mit der Variante „YPTF.MoE+Multi (PS)“ statt der Space-Voreinstellung

- Status: angenommen
- Datum: 2026-11-12

## Kontext
Der Hugging-Face-Space mimbres/YourMT3 (Revision `5e66c1e`) bietet fünf Checkpoints an. Voreingestellt ist „YPTF.MoE+Multi (noPS)“. Damit erreichte der Adapter auf MDB auffällig schwache Drum-Werte (Punk-Mix: Macro-F1 0,48).

Geprüft und ausgeschlossen wurden:
- **Fehlerhaftes Laden:** Der Checkpoint lädt vollständig, es gibt keine fehlenden oder überzähligen Gewichte.
- **Falsche Konfiguration:** Die im Checkpoint gespeicherte Audio- und Modell-Konfiguration stimmt mit den Argumenten aus `app.py` überein.
- **Timing:** Der Kick-Median-Versatz liegt bei −0,4 ms.
- **Segmentgrenzen:** Die Fehler verteilen sich gleichmäßig über die 2,048-s-Segmente.
- **Nachbearbeitung:** `trim_overlapping_notes` fasst nur Noten gleicher Tonhöhe zusammen.

Die Autoren werten Schlagzeug nur im 3-Klassen-Schema aus (Kick, Snare, Hi-Hat). Dort erreichen sie auf ENST-Drums DTM 0,87 und auf Slakh 0,90. ENST ist Teil der Trainingsdaten.

## Vergleich (CPU, Macro-F1 5er / 3er)
| MDB-Probe | noPS | PS |
|---|---|---|
| Punk, Oracle-Stem | 0,494 / 0,629 | 0,670 / 0,817 |
| Punk, Mix | 0,481 / 0,610 | 0,588 / 0,687 |
| 80sRock, Mix | 0,664 / 0,697 | 0,911 / 0,966 |
| Reggae, Mix | 0,537 / 0,573 | 0,778 / 0,837 |
| Zeppelin, Mix | 0,603 / 0,470 | 0,933 / 0,911 |
| Hendrix, Mix | 0,889 / 0,889 | 0,992 / 0,992 |
| CoolJazz, Mix | 0,182 / 0,182 | 0,442 / 0,464 |
| **Mittel** | **0,550 / 0,579** | **0,759 / 0,811** |

## Entscheidung
Der Adapter `yourmt3` nutzt `mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b80_ps2/checkpoints/model.ckpt` (759 MB), mit denselben Argumenten wie die noPS-Variante in `app.py`.

## Konsequenzen
- **Auswahlverzerrung:** Die Variante wurde auf 7 MDB-Proben ausgewählt, also auf dem Benchmark-Datensatz selbst. Der Vorsprung ist aber auf allen 7 Proben eindeutig, nicht nur im Mittel. Die eigenen Songs bleiben der unabhängige Test.
- `setup.py` lädt nur noch diesen Checkpoint. Ein bereits geladener noPS-Checkpoint kann aus `weights/` gelöscht werden.
