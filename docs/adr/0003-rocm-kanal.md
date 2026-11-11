# ADR 0003: GPU über AMD-ROCm-Wheels (Kanal whl-multi-arch, ROCm 7.14.1, PyTorch 2.12)

- Status: angenommen
- Datum: 2026-11-11

## Kontext
Der Rechner hat eine integrierte Radeon 840M (gfx1152, RDNA 3.5) und keine CUDA-GPU. AMD bietet PyTorch-Wheels mit gebündelter ROCm-Runtime an, die kein System-ROCm brauchen. Auf Bluefin/Silverblue ist das wichtig, weil das System unveränderlich ist. Es gibt zwei Kanäle: `repo.amd.com/rocm/whl-multi-arch/` (ROCm 7.13–7.14) und `stable.repo.amd.com/rocm/whl-next/` (ROCm 10.x).

## Spike (2026-11-11)
- `torch[device-gfx1152]==2.12.0+rocm7.14.1` aus `whl-multi-arch`, Python 3.12, Kernel 7.2: `torch.cuda.is_available()` ist True, erkannt wird „AMD Radeon 840M Graphics (gfx1152)“. Ein Transformer-Layer läuft auf der GPU.
- Matmul-Durchsatz: fp32 ~120–200 GFLOP/s, gleichauf mit der CPU. fp16 bis 1,4 TFLOP/s, bf16 bis 1,05 TFLOP/s.
- ADT_STR auf MDB-Drum-Stems (Rock 13 s, Punk 29 s): Die GPU liefert **identische Noten** (F1-Abweichung 0,0), braucht aber 1,5–1,7× länger als die CPU (fp32, autoregressives Dekodieren in kleinen Batches).
- Das PyPI-`torchcodec` ist gegen CUDA gebaut (`libnvrtc.so.13`), und AMD bietet kein ROCm-torchcodec an. Adapter laden Audio deshalb mit `soundfile`.
- Der Kanal `whl-next` (ROCm 10.x) wurde nicht getestet, weil `whl-multi-arch` auf Anhieb lief.

## Entscheidung
- GPU-Unterstützung ist **pro Adapter optional**. Wer `[tool.stickler.rocm]` deklariert, bekommt mit `stickler setup --device rocm` eine zweite Umgebung `.venv-rocm`. Darin sind die Torch-Pakete durch die AMD-Wheels ersetzt. Die übrigen **direkten** Abhängigkeiten löst uv frisch auf, denn die transitiven Pins des CPU-Locks (z. B. `setuptools`) widersprechen den ROCm-Wheels.
- Standard-Kanal: `whl-multi-arch`, ROCm 7.14.1, PyTorch 2.12.0, torchaudio 2.11.0.
- `prefer_gpu = false` sorgt dafür, dass `device=auto` die CPU nimmt, wenn die GPU für ein Modell nachweislich langsamer ist. Das gilt für ADT_STR. `device=gpu` erzwingt die GPU weiterhin.
- Der Cache-Schlüssel enthält die Umgebung (cpu/rocm). Schlüssel für reine CPU-Läufe bleiben unverändert.

## Konsequenzen
- Die ROCm-Umgebung ist weniger reproduzierbar als die CPU-Umgebung (kein Lock). Die Versionen der Torch-Pakete sind gepinnt.
- Ein Geschwindigkeitsgewinn ist vor allem bei Modellen zu erwarten, die fp16/bf16 rechnen oder große Batches verarbeiten (Separatoren wie Demucs/RoFormer). Das misst Task 7/8.
- fp16-Autocast für ADT_STR wäre möglich, verändert aber die Numerik und wäre damit ein anderer Kandidat. Wird nur nach Rückfrage untersucht.
- ~5 GB Speicher je ROCm-Umgebung.
