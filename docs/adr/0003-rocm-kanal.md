# ADR 0003: GPU via AMD ROCm wheels (channel whl-multi-arch, ROCm 7.14.1, PyTorch 2.12)

- Status: accepted
- Date: 2026-11-11

## Context
The machine has an integrated Radeon 840M (gfx1152, RDNA 3.5) and no CUDA GPU. AMD offers PyTorch wheels with a bundled ROCm runtime that do not need a system ROCm. On Bluefin/Silverblue this matters, because the system is immutable. There are two channels: `repo.amd.com/rocm/whl-multi-arch/` (ROCm 7.13–7.14) and `stable.repo.amd.com/rocm/whl-next/` (ROCm 10.x).

## Spike (2026-11-11)
- `torch[device-gfx1152]==2.12.0+rocm7.14.1` from `whl-multi-arch`, Python 3.12, kernel 7.2: `torch.cuda.is_available()` is True, and "AMD Radeon 840M Graphics (gfx1152)" is detected. A transformer layer runs on the GPU.
- Matmul throughput: fp32 ~120–200 GFLOP/s, on par with the CPU. fp16 up to 1.4 TFLOP/s, bf16 up to 1.05 TFLOP/s.
- ADT_STR on MDB drum stems (Rock 13 s, Punk 29 s): the GPU produces **identical notes** (F1 deviation 0.0), but takes 1.5–1.7× as long as the CPU (fp32, autoregressive decoding in small batches).
- The PyPI `torchcodec` is built against CUDA (`libnvrtc.so.13`), and AMD does not offer a ROCm build of torchcodec. Adapters therefore load audio with `soundfile`.
- The `whl-next` channel (ROCm 10.x) was not tested, because `whl-multi-arch` worked right away.

## Decision
- GPU support is **optional per adapter**. Whoever declares `[tool.stickler.rocm]` gets a second environment `.venv-rocm` via `stickler setup --device rocm`. In it, the Torch packages are replaced by the AMD wheels. The remaining **direct** dependencies are resolved fresh by uv, because the transitive pins of the CPU lock (e.g. `setuptools`) conflict with the ROCm wheels.
- Default channel: `whl-multi-arch`, ROCm 7.14.1, PyTorch 2.12.0, torchaudio 2.11.0.
- `prefer_gpu = false` ensures that `device=auto` uses the CPU when the GPU is demonstrably slower for a model. This applies to ADT_STR. `device=gpu` still forces the GPU.
- The cache key includes the environment (cpu/rocm). Keys for pure CPU runs remain unchanged.
  *Superseded on 2026-11-12: cache keys no longer include the device (cache v2, see `stickler.runner.cache_dir_for`); the device is recorded in `meta.json`.*

## Consequences
- The ROCm environment is less reproducible than the CPU environment (no lock). The Torch package versions are pinned.
- A speed gain is mainly to be expected for models that compute in fp16/bf16 or process large batches (separators such as Demucs/RoFormer). Tasks 7/8 measure this.
- fp16 autocast for ADT_STR would be possible, but it changes the numerics and would thus be a different candidate. It will only be examined after consultation.
- ~5 GB of storage per ROCm environment.
