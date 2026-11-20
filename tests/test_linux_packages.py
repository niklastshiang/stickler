"""Building the `.deb` and `.rpm` (SPEC.md, module `linux-packages`): the wheels from uv.lock per
Python minor version, the staged tree, the pins, and the dependencies of both formats."""

import importlib.util
import re
import stat
import subprocess
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
_FILE = ROOT / "scripts" / "linux_packages.py"
_spec = importlib.util.spec_from_file_location("linux_packages", _FILE)
lp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lp)

LOCK = ROOT / "uv.lock"


def test_each_python_gets_its_own_wheels_and_pyyaml_comes_from_the_system():
    for tag in ("cp314", "cp315"):
        names = [w["url"].rsplit("/", 1)[-1] for w in lp.wheels(LOCK, tag)]
        assert len(names) == 4, names
        assert next(n for n in names if n.startswith("numpy-")).split("-")[2] == tag
        assert any(n.startswith("verovio-") and "-abi3-" in n for n in names)
        assert any(n.startswith("mido-") for n in names)
        assert any(n.startswith("packaging-") for n in names)
        assert not any(n.lower().startswith("pyyaml") for n in names)


def _wheel(path: Path, package: str) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{package}/__init__.py", "")
        archive.writestr(f"{package}-1.dist-info/METADATA", "Name: x\n")
    return path


def test_the_staged_tree_has_everything_the_app_needs_and_nothing_else(tmp_path):
    uv = tmp_path / "uv"
    uv.write_text("uv")
    wheels = {
        "3.14": [_wheel(tmp_path / "numpy314.whl", "numpy")],
        "3.15": [_wheel(tmp_path / "numpy315.whl", "numpy")],
    }
    tree = tmp_path / "tree"
    lp.stage(ROOT, tree, wheels, uv)
    lib = tree / "usr/lib/stickler"
    for needed in (
        "usr/bin/stickler-gtk",
        "usr/lib/stickler/stickler_gtk/main.py",
        "usr/lib/stickler/stickler_app/paths.py",
        "usr/lib/stickler/stickler/api.py",
        "usr/lib/stickler/python3.14/numpy/__init__.py",
        "usr/lib/stickler/python3.15/numpy/__init__.py",
        "usr/lib/stickler/bin/uv",
        "usr/share/stickler/adapters/_common/pyproject.toml",
        "usr/share/stickler/adapters/transcribers/adtof/run.py",
        "usr/share/fonts/stickler/Leipzig.ttf",
        "usr/share/icons/hicolor/scalable/apps/ng.tshia.Stickler.svg",
        "usr/share/icons/hicolor/symbolic/apps/ng.tshia.Stickler-symbolic.svg",
        "usr/share/applications/ng.tshia.Stickler.desktop",
        "usr/share/metainfo/ng.tshia.Stickler.metainfo.xml",
        "usr/share/licenses/stickler/LICENSE",
        "usr/share/locale/de/LC_MESSAGES/stickler.mo",
        "usr/share/locale/es/LC_MESSAGES/stickler.mo",
    ):
        assert (tree / needed).is_file(), needed
    for program in (tree / "usr/bin/stickler-gtk", lib / "bin/uv"):
        assert program.stat().st_mode & stat.S_IXOTH
    files = [p.relative_to(tree) for p in tree.rglob("*")]
    for unwanted in (".venv", "weights", "__pycache__", "uv.lock.tmp"):
        assert not any(unwanted in p.parts for p in files), unwanted
    assert not any(p.suffix in (".pyc", ".ckpt", ".pth", ".safetensors") for p in files)
    assert not any(p.name.endswith(".dist-info") for p in (lib / "python3.14").iterdir())
    # the same modes whatever the builder's umask: nothing writable but by its owner (root)
    modes = {p.stat().st_mode & 0o777 for p in tree.rglob("*")}
    assert modes <= {0o644, 0o755}, sorted(oct(m) for m in modes)


def test_the_adapters_are_exactly_the_tracked_files():
    tracked = subprocess.run(
        ["git", "ls-files", "adapters"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    assert lp.adapter_files(ROOT) == sorted(Path(p) for p in tracked)


def test_uv_is_the_appimages_and_every_download_is_pinned():
    appimage = (ROOT / "scripts" / "appimage.sh").read_text(encoding="utf-8")
    assert re.search(r"^UV_VERSION=(\S+)", appimage, re.MULTILINE).group(1) == lp.UV_VERSION
    assert re.search(r"^UV_SHA256=(\S+)", appimage, re.MULTILINE).group(1) == lp.UV_SHA256
    assert re.fullmatch(r"[0-9a-f]{64}", lp.NFPM_SHA256)
    assert re.fullmatch(r"\d+\.\d+\.\d+", lp.NFPM_VERSION)


def test_both_formats_need_libadwaita_18_and_take_ffmpeg_from_the_system():
    config = yaml.safe_load((ROOT / "packaging" / "nfpm.yaml").read_text(encoding="utf-8"))
    deb = config["overrides"]["deb"]["depends"]
    rpm = config["overrides"]["rpm"]["depends"]
    assert "gir1.2-adw-1 (>= 1.8)" in deb and "libadwaita >= 1.8" in rpm
    assert "python3 (>= 3.14)" in deb and "python3 (<< 3.16)" in deb  # the wheels' versions
    assert "(python(abi) = 3.14 or python(abi) = 3.15)" in rpm
    assert (
        "gstreamer1.0-pipewire | gstreamer1.0-pulseaudio"
        in config["overrides"]["deb"]["recommends"]
    )
    assert "ffmpeg" in deb and "/usr/bin/ffmpeg" in rpm and "/usr/bin/ffprobe" in rpm
    assert "python3-yaml" in deb and "python3-pyyaml" in rpm
    assert config["name"] == "stickler" and config["arch"] == "amd64"
    assert config["version_schema"] == "none"  # nFPM would make 9 into 9.0.0
    assert str(lp.STAGE) == "dist/linux-stage"


def test_the_packages_own_only_sticklers_folders_and_every_staged_file(tmp_path):
    """Trees only for Stickler's own folders; a tree of /usr would make the packages own
    /usr/share/fonts, the icon theme's folders and the locale folders."""
    config = yaml.safe_load((ROOT / "packaging" / "nfpm.yaml").read_text(encoding="utf-8"))
    own = ("/usr/lib/stickler", "/usr/share/stickler", "/usr/share/fonts/stickler")
    own += ("/usr/share/licenses/stickler",)
    for entry in config["contents"]:
        assert entry["src"] == f"dist/linux-stage{entry['dst']}"
        if entry.get("type") == "tree":
            assert entry["dst"] in own
    uv = tmp_path / "uv"
    uv.write_text("uv")
    lp.stage(ROOT, tmp_path / "tree", {}, uv)
    staged = {f"/{p.relative_to(tmp_path / 'tree')}" for p in (tmp_path / "tree").rglob("*")}
    staged = {p for p in staged if (tmp_path / "tree" / p.lstrip("/")).is_file()}
    covered = {
        p
        for p in staged
        for entry in config["contents"]
        if p == entry["dst"] or p.startswith(entry["dst"] + "/")
    }
    assert staged == covered


def test_the_file_names_follow_the_other_packages():
    assert lp.file_name("deb", "9") == "Stickler-9_amd64.deb"
    assert lp.file_name("rpm", "9") == "Stickler-9.x86_64.rpm"


def test_every_promised_system_is_tested_and_ubuntu_makes_the_clips_first():
    assert [image.rsplit(":", 1)[1] for image, _ in lp.CONTAINERS] == ["26.04", "44", "45"]
    assert lp.CONTAINERS[0][1] == "deb"
    command = lp.container_command(
        "fedora:45", "rpm", Path("/x/Stickler-9.x86_64.rpm"), Path("/x/clips")
    )
    assert command[-4:] == [
        "/test/container-test.sh",
        "rpm",
        "/test/Stickler-9.x86_64.rpm",
        "/test/clips",
    ]
    assert "/x/Stickler-9.x86_64.rpm:/test/Stickler-9.x86_64.rpm:ro,Z" in command


def test_a_release_attaches_both_packages_after_their_container_test():
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["linux-packages"]
    assert any(step.get("run") == "python3 scripts/linux_packages.py test" for step in job["steps"])
    assert "linux-packages" in workflow["jobs"]["attach"]["needs"]
