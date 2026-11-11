"""Tests für `stickler doctor`: Systemprüfung ohne echte GPU (Pfade und Befehle gemockt)."""

from pathlib import Path

from stickler import doctor


def adapter(root: Path, stage: str, name: str, rocm: bool = False, weights: bool = False) -> Path:
    d = root / stage / name
    d.mkdir(parents=True)
    (d / "run.py").write_text("", encoding="utf-8")
    text = '[project]\nname = "x"\n'
    if rocm:
        text += '[tool.stickler.rocm]\nindex = "i"\nreplace = []\npackages = []\n'
    (d / "pyproject.toml").write_text(text, encoding="utf-8")
    (d / ".venv").mkdir()
    if weights:
        (d / "setup.py").write_text("", encoding="utf-8")
        (d / "weights").mkdir()
        (d / "weights" / "model.bin").write_bytes(b"x")
    return d


def by_name(checks):
    return {c.name: c for c in checks}


def test_gpu_detected_from_sysfs(tmp_path):
    (tmp_path / "kfd").write_text("")
    card = tmp_path / "drm" / "card1" / "device"
    card.mkdir(parents=True)
    (card / "vendor").write_text("0x1002\n")
    check = doctor.check_gpu(kfd=tmp_path / "kfd", drm=tmp_path / "drm")
    assert check.ok and "AMD" in check.detail


def test_gpu_missing(tmp_path):
    check = doctor.check_gpu(kfd=tmp_path / "fehlt", drm=tmp_path)
    assert not check.ok


def test_adapter_checks(tmp_path):
    adapter(tmp_path, "transcribers", "a", rocm=True, weights=True)
    adapter(tmp_path, "transcribers", "b")
    (tmp_path / "transcribers" / "c").mkdir()
    (tmp_path / "transcribers" / "c" / "run.py").write_text("", encoding="utf-8")
    (tmp_path / "transcribers" / "c" / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "transcribers" / "c" / "setup.py").write_text("", encoding="utf-8")
    checks = by_name(doctor.check_adapters(tmp_path))
    assert checks["adapter a"].ok and "ROCm: nicht gebaut" in checks["adapter a"].detail
    assert checks["adapter b"].ok and "ROCm: –" in checks["adapter b"].detail
    assert not checks["adapter c"].ok and "setup" in checks["adapter c"].detail


def test_hf_login_via_env_or_token_file(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert not doctor.check_hf_login(token_file=tmp_path / "token").ok
    (tmp_path / "token").write_text("x")
    assert doctor.check_hf_login(token_file=tmp_path / "token").ok
    monkeypatch.setenv("HF_TOKEN", "x")
    assert doctor.check_hf_login(token_file=tmp_path / "fehlt").ok


def test_musescore_found_via_path_or_flatpak(monkeypatch):
    monkeypatch.setattr(
        doctor.shutil, "which", lambda name: "/usr/bin/mscore" if name == "mscore" else None
    )
    assert doctor.check_musescore(flatpak_ids=lambda: set()).ok
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    assert doctor.check_musescore(flatpak_ids=lambda: {"org.musescore.MuseScore"}).ok
    assert not doctor.check_musescore(flatpak_ids=lambda: set()).ok


def test_datasets(tmp_path):
    assert not by_name(doctor.check_datasets(tmp_path))["datensatz mdb"].ok
