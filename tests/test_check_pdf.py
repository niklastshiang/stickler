"""scripts/check_pdf.py: the Windows app's PDF checked on the runner (module `win-sheet`)."""

import importlib.util
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_pdf", ROOT / "scripts" / "check_pdf.py")
check_pdf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_pdf)


def pdf(pages: int, box: str = "0 0 595.28 841.89", title: bytes | None = b"(Groove)") -> bytes:
    """A small PDF as Chromium writes one: the page dictionaries, the title in /Info."""
    body = b"%PDF-1.4\n" + b"1 0 obj << /Type /Pages /Count %d >> endobj\n" % pages
    for k in range(pages):
        body += b"%d 0 obj << /Type /Page /MediaBox [%s] >> endobj\n" % (k + 2, box.encode())
    if title is not None:
        body += b"9 0 obj << /Title " + title + b" /Creator (Chromium) >> endobj\n"
    return body + b"%%EOF\n"


def write(tmp_path, data: bytes) -> Path:
    out = tmp_path / "sheet.pdf"
    out.write_bytes(data)
    return out


def test_a_right_pdf_passes_and_says_what_it_found(tmp_path, capsys):
    out = write(tmp_path, pdf(2))
    assert check_pdf.main([str(out), "--pages", "2", "--title", "Groove"]) == 0
    assert "2 A4 pages, title 'Groove'" in capsys.readouterr().out


def test_wrong_pages_size_or_title_fail(tmp_path, capsys):
    out = write(tmp_path, pdf(1, box="0 0 612 792", title=b"(Other)"))
    assert check_pdf.main([str(out), "--pages", "2", "--title", "Groove"]) == 1
    err = capsys.readouterr().err
    assert "1 pages, not 2" in err
    assert "612 × 792 points, not A4" in err
    assert "the title is 'Other'" in err


def test_a_missing_title_is_not_a_failure_and_a_missing_size_is():
    assert check_pdf.problems(Path("nowhere.pdf"), 1, None) == ["nowhere.pdf is no PDF"]
    pages, boxes, title = check_pdf.inspect(pdf(1, title=None))
    assert (pages, title) == (1, None)
    assert boxes == [(595.28, 841.89)]


def test_titles_in_hex_utf16_and_escapes_and_compressed_objects_are_read(tmp_path):
    hex_title = b"<FEFF0045007900650020006F0066>"  # "Eye of" in UTF-16
    assert check_pdf.inspect(pdf(1, title=hex_title))[2] == "Eye of"
    assert check_pdf.inspect(pdf(1, title=b"(Rock \\(live\\))"))[2] == "Rock (live)"
    hidden = zlib.compress(b"<< /Type /Page /MediaBox [0 0 595 842] >>")
    data = b"%PDF-1.5\n5 0 obj << /Length 9 >>\nstream\n" + hidden + b"\nendstream\nendobj\n"
    data += b"6 0 obj << /Length 3 >>\nstream\nxyz\nendstream\nendobj\n"  # not compressed
    out = write(tmp_path, data)
    assert check_pdf.problems(out, 1, None) == []
    empty = write(tmp_path, b"%PDF-1.4\n1 0 obj << /Type /Page >> endobj\n")
    assert check_pdf.problems(empty, 1, None) == ["no page size"]
