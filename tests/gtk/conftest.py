"""The app's tests never read or write the user's real data, cache or settings."""

import pytest


@pytest.fixture(autouse=True)
def _private_xdg_folders(tmp_path, monkeypatch):
    for name in ("XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        folder = tmp_path / name.lower()
        folder.mkdir()
        monkeypatch.setenv(name, str(folder))
