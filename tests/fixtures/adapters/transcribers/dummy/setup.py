"""Dummy setup: leaves a marker file."""

from pathlib import Path

(Path(__file__).parent / ".setup-done").write_text("ok", encoding="utf-8")
