"""Tests for the ROCm variant of the adapter environments (no real GPU, subprocesses mocked)."""

import subprocess
from pathlib import Path

import pytest

from stickler import adapters

PYPROJECT = """[project]
name = "x"
version = "0"
requires-python = ">=3.12,<3.13"
dependencies = ["stickler-adapter", "torch==2.8.0", "torchaudio==2.8.0", "numpy", "soundfile>=0.12"]

[tool.uv.sources]
stickler-adapter = { path = "../../_common", editable = true }
torch = { index = "pytorch-cpu" }

[tool.stickler.rocm]
index = "https://repo.amd.com/rocm/whl-multi-arch/"
replace = ["torch", "torchaudio"]
packages = ["torch[device-gfx1152]==2.12.0+rocm7.14.1", "torchaudio==2.11.0+rocm7.14.1"]
"""


@pytest.fixture
def spec(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "run.py").write_text("", encoding="utf-8")
    return adapters.AdapterSpec(id="x", stage="transcribers", path=tmp_path)


def fake_rocm_env(spec):
    py = spec.path / adapters.ROCM_ENV / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")
    return py


def test_rocm_config_is_read(spec):
    cfg = adapters.rocm_config(spec)
    assert cfg.replace == ["torch", "torchaudio"]
    assert cfg.packages[0].startswith("torch[device-gfx1152]")


def test_rocm_config_missing_is_none(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "y"\n', encoding="utf-8")
    assert adapters.rocm_config(adapters.AdapterSpec("y", "transcribers", tmp_path)) is None


def test_rocm_requirements_use_direct_deps_without_replaced(spec):
    reqs = adapters.rocm_requirements(spec, ["torch", "torchaudio"])
    assert reqs == ["-e ../../_common", "numpy", "soundfile>=0.12"]


@pytest.mark.parametrize(
    ("device", "has_rocm", "variant"),
    [
        ("cpu", True, "cpu"),
        ("auto", False, "cpu"),
        ("auto", True, "rocm"),
        ("gpu", True, "rocm"),
        ("gpu", False, None),
    ],
)
def test_env_variant(spec, device, has_rocm, variant):
    if has_rocm:
        fake_rocm_env(spec)
    assert adapters.env_variant(spec, device) == variant


def test_run_adapter_uses_rocm_python(spec, monkeypatch, tmp_path):
    py = fake_rocm_env(spec)
    seen = []

    def fake_run_group(cmd, timeout):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "deliberate")

    monkeypatch.setattr(adapters, "_run_group", fake_run_group)
    adapters.run_adapter(spec, tmp_path / "a.wav", tmp_path / "out", device="auto")
    assert seen[0][0] == str(py)
    assert seen[0][-1] == "auto"


def test_gpu_without_rocm_env_fails_clearly(spec, tmp_path):
    result = adapters.run_adapter(spec, tmp_path / "a.wav", tmp_path / "out", device="gpu")
    assert not result.ok
    assert "--device rocm" in result.error


def test_setup_rocm_builds_env_with_replaced_torch(spec, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapters.setup_adapter(spec, device="rocm")
    install = next(c for c in calls if c[:3] == ["uv", "pip", "install"])
    assert "torch[device-gfx1152]==2.12.0+rocm7.14.1" in install
    assert "https://repo.amd.com/rocm/whl-multi-arch/" in install
    req = Path(install[install.index("-r") + 1]).read_text()
    assert "torch==" not in req and "numpy" in req and "-e ../../_common" in req


def test_setup_rocm_without_config_raises(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "y"\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="ROCm"):
        adapters.setup_adapter(adapters.AdapterSpec("y", "transcribers", tmp_path), device="rocm")


def test_setup_unknown_device_raises(spec):
    with pytest.raises(ValueError, match="tpu"):
        adapters.setup_adapter(spec, device="tpu")


def test_auto_respects_prefer_gpu_false(spec):
    fake_rocm_env(spec)
    text = (spec.path / "pyproject.toml").read_text(encoding="utf-8")
    (spec.path / "pyproject.toml").write_text(text + "prefer_gpu = false\n", encoding="utf-8")
    assert adapters.env_variant(spec, "auto") == "cpu"
    assert adapters.env_variant(spec, "gpu") == "rocm"
