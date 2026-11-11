"""Dummy-Setup: hinterlegt eine Markierungsdatei."""

from pathlib import Path

(Path(__file__).parent / ".setup-done").write_text("ok", encoding="utf-8")
