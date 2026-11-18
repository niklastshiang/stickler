"""docs/bridge.md is the bridge's contract: it must name the code's commands, state kinds,
state fields, events and error codes, and every example must decode."""

import json
import re
from pathlib import Path

import pytest
from fakes import groove_score

from stickler import api
from stickler_app import bridge, session

DOC = Path(__file__).resolve().parents[2] / "docs" / "bridge.md"


def _sections() -> dict[str, dict[str, str]]:
    """`## Part` → `### \\`name\\`` → the text under it."""
    parts: dict[str, dict[str, str]] = {}
    part = name = None
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            part, name = line[3:].strip(), None
            parts[part] = {}
        elif line.startswith("### ") and part is not None:
            name = line[4:].strip().strip("`")
            parts[part][name] = ""
        elif part is not None and name is not None:
            parts[part][name] += line + "\n"
    return parts


def _examples(text: str) -> list[dict]:
    blocks = re.findall(r"```json\n(.*?)```", text, flags=re.S)
    return [json.loads(line) for block in blocks for line in block.splitlines() if line.strip()]


SECTIONS = _sections()


def test_every_example_in_the_document_decodes():
    assert len(_examples(DOC.read_text(encoding="utf-8"))) > 40


def test_the_document_names_every_command_and_each_example_is_its_own():
    assert set(SECTIONS["Commands"]) == bridge.Bridge(None, None).commands
    for name, text in SECTIONS["Commands"].items():
        request, reply = _examples(text)
        assert request["cmd"] == name and isinstance(request["id"], int)
        assert reply["id"] == request["id"] and reply["ok"] is True, name


def test_the_document_names_every_event():
    assert set(SECTIONS["Events"]) == {"hello", "state", "recent", "notice"}
    keys = {
        "hello": {"event", "protocol", "version", "language"},
        "state": {"event", "seq", "state"},
        "recent": {"event", "seq", "rows"},
        "notice": {"event", "seq", "text", "opens"},
    }
    for name, text in SECTIONS["Events"].items():
        (example,) = _examples(text)
        assert example["event"] == name and set(example) == keys[name]


def test_the_document_names_every_error_code():
    table = DOC.read_text(encoding="utf-8").split("## Errors")[1].split("## Events")[0]
    codes = set(re.findall(r"^\| `(\w+)` \|", table, flags=re.M))
    assert codes == {"bad_request", "unknown_command", "bad_argument", "not_now", "internal"}
    source = Path(bridge.__file__).read_text(encoding="utf-8")
    assert {code for code in codes if f'"{code}"' in source} == codes


def _samples(tmp_path) -> dict[str, session.State]:
    """One state of each kind, as the controller makes them."""
    song = tmp_path / "eye.flac"
    score = tmp_path / "eye.musicxml"
    score.write_text(groove_score().musicxml, encoding="utf-8")
    t = api.SongTranscription(song, "fast", None, [], [], [])
    notation = api.Notation(score, None, None, t, [], 109, (4, 4))
    result = session.Result(song, api.SongInfo("Eye", "Survivor", 246.0), notation)
    analysing = session.open_song(song, session.Empty())
    setting_up = session.start_setup(("environment:adtof",))
    return {
        "empty": session.Empty(),
        "consent": session.consent(("adtof",)),
        "setting_up": setting_up,
        "setup_failed": session.failed(setting_up, setting_up.job, RuntimeError("500")),
        "analysing": analysing,
        "result": result,
        "exporting": session.export_drums(result, tmp_path / "d.flac", setup=False),
        "failed": session.failed(analysing, analysing.job, RuntimeError("oom")),
    }


@pytest.mark.parametrize("kind", sorted(bridge.KINDS.values()))
def test_each_state_kind_is_documented_with_exactly_its_fields(kind, tmp_path):
    assert set(SECTIONS["States"]) == set(bridge.KINDS.values())
    (example,) = _examples(SECTIONS["States"][kind])
    encoded = bridge.encode(_samples(tmp_path)[kind])
    assert example["kind"] == kind
    assert set(example) == set(encoded)
    for key in ("steps", "models"):
        if key in encoded:
            assert set(example[key][0]) == set(encoded[key][0])


def test_the_documented_page_has_the_fields_of_an_encoded_one():
    from stickler_app import engraving

    page = bridge.encode_page(engraving.engrave(groove_score().musicxml, 800)[0])
    request, reply = _examples(SECTIONS["Commands"]["pages"])
    documented = reply["pages"][0]
    assert set(documented) == set(page)
    assert set(documented["bars"][0]) == set(page["bars"][0])
