"""Stickler-Adapter: ADT_STR transkribiert Schlagzeug-Audio zu GM-Drum-MIDI.

Zwei Anpassungen gegenüber `ADTTranscriber.transcribe` aus dem HF-Bundle, beide aus dem
offiziellen Repository übernommen:
1. Jeder 2,56-s-Abschnitt wird auf Spitzenpegel normalisiert, wie in der offiziellen
   Auswertung (eval.py → data_modules → utils.audio_utils.normalize). Ohne diesen Schritt
   erkennt das Modell auf MDB kaum Hi-Hats.
2. Das Modell gibt eine eigene Nummerierung (26 Klassen, 35–60) aus, kein GM. Rückübersetzung
   mit `MappingUtils.GM_custom_midi_to_Gm_standard_Mapping` aus dem Bundle.
Audio wird mit soundfile geladen und als Tensor übergeben (offizielle Tensor-API von
`transcribe`). So braucht der Adapter kein torchcodec, das es für ROCm nicht gibt.
"""

import sys
import tempfile
from pathlib import Path

from stickler_adapter import run, torch_device, write_drum_midi

WEIGHTS = Path(__file__).parent / "weights"
VARIANT = "setting-tau-0.8"
VERSION = f"v1.0.0/{VARIANT}@a33c5c6+segnorm+sf"


def transcribe(audio: Path, out_dir: Path, device: str) -> None:
    if not (WEIGHTS / VARIANT).is_dir():
        raise RuntimeError("Gewichte fehlen: zuerst `stickler setup --adapter adt_str`")
    sys.path.insert(0, str(WEIGHTS))  # das HF-Bundle bringt seinen Inferenz-Code selbst mit
    import adt_transcriber
    import pretty_midi
    import soundfile
    import torch
    from utils.audio_utils import normalize
    from utils.mapping_utils import MappingUtils

    original_chunker = adt_transcriber._chunk_audio

    def normalized_chunks(wav, chunk_samples):
        return [
            (start, normalize(chunk) if chunk.abs().max() > 0 else chunk)
            for start, chunk in original_chunker(wav, chunk_samples)
        ]

    adt_transcriber._chunk_audio = normalized_chunks
    to_gm = MappingUtils().GM_custom_midi_to_Gm_standard_Mapping

    model = adt_transcriber.ADTTranscriber.from_pretrained(
        str(WEIGHTS), variant=VARIANT, device=torch_device(device)
    )
    samples, sample_rate = soundfile.read(str(audio), dtype="float32", always_2d=True)
    mono = torch.from_numpy(samples.mean(axis=1))
    with tempfile.TemporaryDirectory() as tmp:
        midi_path = model.transcribe(mono, sample_rate=sample_rate, output_dir=tmp)
        midi = pretty_midi.PrettyMIDI(str(midi_path))
    notes = [
        (n.start, to_gm[n.pitch], n.velocity)
        for inst in midi.instruments
        if inst.is_drum
        for n in inst.notes
    ]
    write_drum_midi(out_dir / "drums.mid", notes)


if __name__ == "__main__":
    run(transcribe, stage="transcribers", adapter="adt_str", version=VERSION)
