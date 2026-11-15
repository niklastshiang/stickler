"""The app's settings (appearance), kept in the XDG config folder."""

from stickler_gtk.logic import settings


def test_appearance_follows_the_system_until_the_user_chooses(tmp_path):
    store = tmp_path / "settings.json"
    assert settings.load(store).appearance == "system"
    settings.save(store, settings.Settings(appearance="dark"))
    assert settings.load(store).appearance == "dark"


def test_a_damaged_or_unknown_setting_falls_back_to_the_default(tmp_path):
    store = tmp_path / "settings.json"
    for text in ("{", '"dark"', '{"appearance": "purple"}', '{"appearance": 3}'):
        store.write_text(text, encoding="utf-8")
        assert settings.load(store) == settings.Settings()


def test_settings_live_in_the_xdg_config_folder(tmp_path):
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    assert settings.store_path(env) == tmp_path / "stickler" / "settings.json"
    assert settings.store_path({"HOME": str(tmp_path)}) == (
        tmp_path / ".config" / "stickler" / "settings.json"
    )


def test_only_the_three_appearances_exist():
    assert settings.APPEARANCES == ("system", "light", "dark")
