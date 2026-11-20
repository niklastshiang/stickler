"""Builds Stickler's `.deb` and `.rpm` (SPEC.md, module `linux-packages`).

The system brings Python, GTK, libadwaita, GStreamer, ffmpeg and PyYAML (packaging/nfpm.yaml);
the packages bring the app, the wheels from uv.lock the systems lack (one folder per Python
minor version: Ubuntu 26.04 and Fedora 44 have 3.14, Fedora 45 has 3.15), uv, the adapters'
sources (no environments, no weights) and the files every desktop app installs. Every download
is pinned by version and SHA-256.

    uv run python scripts/linux_packages.py build     # dist/Stickler-<v>_amd64.deb and .rpm
    uv run python scripts/linux_packages.py test      # both in clean containers (podman)
"""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = Path("dist/linux-stage")  # relative to ROOT, as packaging/nfpm.yaml names it
DOWNLOADS = Path("dist/downloads")

UV_VERSION = "0.13.9"  # the AppImage's (tests/test_linux_packages.py)
UV_SHA256 = "58ccf5f1792b8a5a88d01bc910ea131a8b3db4a319a17ad5fad75e0845a3e271"
NFPM_VERSION = "2.49.0"  # goreleaser/nfpm, MIT, released 2026-11-12
NFPM_SHA256 = "2afaa5ffb5e3493402e31e7c67a5a1fb42133e3f66fc315ca0051934125561c7"

# what the app imports that the systems do not have; PyYAML is the system's (no cp315 wheel)
PACKAGES = ["numpy", "mido", "packaging", "verovio"]
PYTHONS = {"3.14": "cp314", "3.15": "cp315"}
SKIPPED = {"__pycache__", ".venv", "weights"}


def _flatpak_deps():
    spec = importlib.util.spec_from_file_location("flatpak_deps", ROOT / "scripts/flatpak_deps.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wheels(lock: Path, python_tag: str) -> list[dict]:
    """The locked wheel (URL and hash) of each package for CPython `python_tag` on x86_64."""
    locked = {p["name"]: p for p in tomllib.loads(lock.read_text(encoding="utf-8"))["package"]}
    pick = _flatpak_deps().pick
    return [pick(locked[name].get("wheels", []), python_tag) for name in PACKAGES]


def file_name(kind: str, version: str) -> str:
    return f"Stickler-{version}_amd64.deb" if kind == "deb" else f"Stickler-{version}.x86_64.rpm"


def adapter_files(root: Path) -> list[Path]:
    """The adapters' tracked files: never a local environment, weights or a scratch file."""
    listed = subprocess.run(
        ["git", "ls-files", "adapters"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.split()
    return sorted(Path(p) for p in listed)


def _copy_tree(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*SKIPPED, "*.pyc"))


def _install(source: Path, target: Path, mode: int = 0o644) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(mode)


def stage(root: Path, tree: Path, wheel_files: dict[str, list[Path]], uv: Path) -> None:
    """Lays out the installed files under `tree`/usr, as nFPM packs them."""
    if tree.exists():
        shutil.rmtree(tree)
    usr = tree / "usr"
    lib = usr / "lib/stickler"
    for package in ("stickler", "stickler_app", "stickler_gtk"):
        _copy_tree(root / "src" / package, lib / package)
    for version, files in wheel_files.items():
        folder = lib / f"python{version}"
        folder.mkdir(parents=True)
        for wheel in files:
            with zipfile.ZipFile(wheel) as archive:
                archive.extractall(folder)
        for info in folder.glob("*.dist-info"):  # pip's records: nothing reads them here
            shutil.rmtree(info)
    _install(uv, lib / "bin/uv", 0o755)
    _install(root / "packaging/linux/stickler-gtk", usr / "bin/stickler-gtk", 0o755)
    for relative in adapter_files(root):
        if not SKIPPED.intersection(relative.parts):
            _install(root / relative, usr / "share/stickler" / relative)
    share = {
        "packaging/fonts/Leipzig.ttf": "fonts/stickler/Leipzig.ttf",
        "packaging/icons/ng.tshia.Stickler.svg": (
            "icons/hicolor/scalable/apps/ng.tshia.Stickler.svg"
        ),
        "packaging/icons/ng.tshia.Stickler-symbolic.svg": (
            "icons/hicolor/symbolic/apps/ng.tshia.Stickler-symbolic.svg"
        ),
        "packaging/ng.tshia.Stickler.desktop": "applications/ng.tshia.Stickler.desktop",
        "packaging/ng.tshia.Stickler.metainfo.xml": "metainfo/ng.tshia.Stickler.metainfo.xml",
        "LICENSE": "licenses/stickler/LICENSE",
    }
    for source, target in share.items():
        _install(root / source, usr / "share" / target)
    for po in sorted((root / "po").glob("*.po")):
        mo = usr / "share/locale" / po.stem / "LC_MESSAGES/stickler.mo"
        mo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["msgfmt", "--check", "-o", str(mo), str(po)], check=True)
        mo.chmod(0o644)


def _download(url: str, sha256: str, folder: Path) -> Path:
    target = folder / url.rsplit("/", 1)[-1]
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
        folder.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as response:
            target.write_bytes(response.read())
    if hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
        target.unlink()
        sys.exit(f"{url}: the SHA-256 does not match the pin")
    return target


def _unpack(archive: Path, member: str, folder: Path) -> Path:
    with tarfile.open(archive) as tar:
        found = next(m for m in tar.getmembers() if m.name.endswith(member) and m.isfile())
        tar.extract(found, folder, filter="data")
    return folder / found.name


def build() -> list[Path]:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    downloads = ROOT / DOWNLOADS
    wheel_files = {
        python: [
            _download(w["url"], w["hash"].removeprefix("sha256:"), downloads / "wheels")
            for w in wheels(ROOT / "uv.lock", tag)
        ]
        for python, tag in PYTHONS.items()
    }
    uv_archive = _download(
        f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/"
        "uv-x86_64-unknown-linux-musl.tar.gz",
        UV_SHA256,
        downloads,
    )
    nfpm_archive = _download(
        f"https://github.com/goreleaser/nfpm/releases/download/v{NFPM_VERSION}/"
        f"nfpm_{NFPM_VERSION}_Linux_x86_64.tar.gz",
        NFPM_SHA256,
        downloads,
    )
    uv = _unpack(uv_archive, "/uv", downloads / "uv")
    nfpm = _unpack(nfpm_archive, "nfpm", downloads / "nfpm")
    stage(ROOT, ROOT / STAGE, wheel_files, uv)
    built = []
    for kind in ("deb", "rpm"):
        target = ROOT / "dist" / file_name(kind, version)
        target.unlink(missing_ok=True)
        subprocess.run(
            [str(nfpm), "package", "-f", "packaging/nfpm.yaml", "-p", kind, "-t", str(target)],
            cwd=ROOT,
            env={"VERSION": version, "PATH": "/usr/bin:/bin"},
            check=True,
        )
        print(f"{target.relative_to(ROOT)}  {target.stat().st_size / 1e6:.1f} MB")
        built.append(target)
    return built


def main(argv: list[str]) -> int:
    if argv[1:] == ["build"]:
        build()
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
