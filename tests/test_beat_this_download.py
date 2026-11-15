"""Beat This!'s checkpoint: JKU first, Stickler's copy when JKU fails, the SHA-256 checked
(SPEC.md, module `setup-assistant`, assumption 3). Imported directly, without torch."""

import hashlib
import http.server
import importlib.util
import threading
from pathlib import Path

import pytest

_FILE = Path(__file__).parents[1] / "adapters" / "beats" / "beat_this" / "download.py"
_spec = importlib.util.spec_from_file_location("beat_this_download", _FILE)
download = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(download)

CONTENT = b"a checkpoint" * 1000


@pytest.fixture
def server():
    """A local server: /good serves CONTENT, /other another file, everything else HTTP 500."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def get(self):
            body = {"/good": CONTENT, "/other": b"something else"}.get(self.path)
            if body is None:
                self.send_error(500)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            return

        do_GET = get  # the name http.server calls

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def _sources(base, *paths):
    return [(f"server {p}", f"{base}{p}") for p in paths]


SHA = hashlib.sha256(CONTENT).hexdigest()


def test_the_first_server_that_answers_with_the_right_file_wins(server, tmp_path):
    dest = tmp_path / "hub" / "checkpoints" / "beat_this-final0.ckpt"
    used = download.fetch(dest, SHA, _sources(server, "/good", "/other"))
    assert used == "server /good" and dest.read_bytes() == CONTENT


def test_when_jku_fails_the_copy_is_used(server, tmp_path):
    dest = tmp_path / "ckpt"
    assert download.fetch(dest, SHA, _sources(server, "/down", "/good")) == "server /good"
    assert dest.read_bytes() == CONTENT and not dest.with_name("ckpt.partial").exists()


def test_a_file_with_another_checksum_is_rejected(server, tmp_path):
    dest = tmp_path / "ckpt"
    with pytest.raises(download.DownloadFailed) as caught:
        download.fetch(dest, SHA, _sources(server, "/other", "/down"))
    assert not dest.exists() and not dest.with_name("ckpt.partial").exists()
    message = str(caught.value)
    assert "server /other" in message and "checksum" in message
    assert "server /down" in message and "500" in message


def test_a_present_file_with_the_right_checksum_is_kept(tmp_path):
    dest = tmp_path / "ckpt"
    dest.write_bytes(CONTENT)
    assert download.fetch(dest, SHA, []) == "already here"


def test_the_sources_are_jku_then_sticklers_copy():
    names = [name for name, _url in download.SOURCES]
    assert names == ["JKU Linz (cloud.cp.jku.at)", "Stickler's copy (github.com)"]
    assert download.SOURCES[0][1].startswith("https://cloud.cp.jku.at/")
    assert download.SOURCES[1][1] == (
        "https://github.com/niklastshiang/stickler/releases/download/beat-this-final0/final0.ckpt"
    )
    assert len(download.SHA256) == 64
