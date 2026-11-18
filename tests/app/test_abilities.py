"""What each state allows, decided once in the shared core (task 125): the GTK window enables
its actions from `session.abilities`, the bridge sends the same to the Mac app as `can_*`."""

from pathlib import Path

import pytest

from stickler_app import bridge, session

SONG = Path("eye.flac")
RESULT = session.Result(SONG, None, None)  # only the kind matters here
FIELDS = ("open", "cancel", "retry", "close", "export", "agree", "not_now", "retry_setup")

# state → the abilities that are on (open is always on: a new song cancels what runs)
TABLE = [
    (session.Empty(), {"open"}),
    (session.Consent(("adtof",)), {"open", "agree", "not_now"}),
    (session.SettingUp((), 1), {"open", "cancel"}),
    (session.SetupFailed((), "weights:adtof", "", ("adtof",)), {"open", "not_now", "retry_setup"}),
    (session.Analysing(SONG, (), 1, session.Empty()), {"open", "cancel", "close"}),
    (RESULT, {"open", "close", "export"}),
    (session.Exporting(SONG, (), 2, RESULT, Path("drums.flac")), {"open", "cancel", "close"}),
    (session.Failed(SONG, "analysis", "", "", "", session.Empty()), {"open", "retry", "close"}),
    (session.Failed(SONG, "unreadable", "", "", "", session.Empty()), {"open", "close"}),
]


def test_the_table_covers_every_kind_of_state():
    assert {type(state) for state, _on in TABLE} == set(session.State.__args__)


@pytest.mark.parametrize(("state", "on"), TABLE, ids=lambda x: type(x).__name__)
def test_each_state_allows_what_its_screen_offers(state, on):
    found = session.abilities(state, installed=False, removing=False)
    assert {name for name in FIELDS if getattr(found, name)} == on
    assert not found.remove_models


@pytest.mark.parametrize(("state", "_on"), TABLE, ids=lambda x: type(x).__name__)
def test_only_the_installed_app_removes_its_models_and_never_while_a_job_runs(state, _on):
    def remove(installed, removing):
        return session.abilities(state, installed=installed, removing=removing).remove_models

    assert remove(True, False) == (not isinstance(state, session.BUSY))
    assert not remove(False, False) and not remove(True, True)


@pytest.mark.parametrize(("state", "_on"), TABLE, ids=lambda x: type(x).__name__)
def test_the_bridge_sends_exactly_the_shared_abilities(state, _on):
    found = session.abilities(state, installed=True, removing=False)
    for remove_models in (False, True):  # the controller's answer, passed through
        sent = bridge.can(state, remove_models=remove_models)
        assert sent == {f"can_{name}": getattr(found, name) for name in FIELDS} | {
            "can_remove_models": remove_models
        }


def test_busy_is_one_definition():
    from stickler_app import controller

    assert controller.BUSY is session.BUSY
