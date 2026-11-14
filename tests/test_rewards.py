"""Tests for the badges of `stickler listen` (SPEC.md, "Gamification")."""

import dataclasses
from datetime import datetime, timedelta

from stickler import rewards

DAY = datetime(2026, 11, 14, 20, 0)


def judged(n, start=DAY):
    return [rewards.Event(start + timedelta(minutes=k), "judged") for k in range(n)]


def test_there_are_eleven_badges_with_a_line_each():
    assert len(rewards.BADGES) == 11
    assert all(b.name and b.line for b in rewards.BADGES)


def test_events_carry_no_answer():
    # the rewards cannot depend on yes/no/unclear: an event only knows when and what happened
    assert [f.name for f in dataclasses.fields(rewards.Event)] == ["when", "kind"]


def test_milestones_count_judged_spots():
    assert set(rewards.earned(judged(9), total=100)) == {"first hit"}
    assert set(rewards.earned(judged(10), total=100)) == {"first hit", "warmed up"}
    names = set(rewards.earned(judged(100), total=100))
    assert {"quarter note", "neighbours: annoyed", "three-quarter time", "encore"} <= names


def test_encore_needs_every_spot_of_the_sample():
    assert "encore" not in rewards.earned(judged(99), total=100)
    assert "encore" in rewards.earned(judged(3), total=3)


def test_a_badge_is_earned_at_the_event_that_triggers_it():
    events = judged(12)
    assert rewards.earned(events, total=100)["warmed up"] == events[9].when


def test_night_shift_and_early_bird_go_by_the_clock():
    night = [rewards.Event(datetime(2026, 11, 15, 0, 30), "judged")]
    early = [rewards.Event(datetime(2026, 11, 15, 6, 15), "judged")]
    late_evening = [rewards.Event(datetime(2026, 11, 14, 23, 59), "judged")]
    assert "night shift" in rewards.earned(night, total=100)
    assert "early bird" in rewards.earned(early, total=100)
    assert {"night shift", "early bird"}.isdisjoint(rewards.earned(late_evening, total=100))


def test_replay_badges():
    replays = [rewards.Event(DAY + timedelta(seconds=k), "replay") for k in range(10)]
    assert set(rewards.earned(replays[:1], total=100)) == {"second opinion"}
    assert "loop pedal" not in rewards.earned(replays[:9], total=100)
    assert "loop pedal" in rewards.earned(replays, total=100)


def test_comeback_tour_needs_a_session_on_a_later_day():
    same_day = [rewards.Event(DAY, "session"), rewards.Event(DAY + timedelta(hours=2), "session")]
    assert "comeback tour" not in rewards.earned(same_day, total=100)
    next_day = [*same_day, rewards.Event(DAY + timedelta(days=1), "session")]
    assert "comeback tour" in rewards.earned(next_day, total=100)


def test_banner_names_the_badge_and_its_line():
    badge = rewards.BADGES[0]
    text = rewards.banner(badge)
    assert badge.name in text and badge.line in text and "BADGE" in text


def test_collection_shows_earned_badges_and_hides_the_others():
    text = rewards.collection({"first hit": DAY})
    assert "1 of 11" in text and "first hit" in text
    assert "encore" not in text and "???" in text


def crow(pipeline, cls, corrected, measured=0.7, low=None, high=None, unclear=0):
    return {
        "pipeline": pipeline,
        "class": cls,
        "measured": measured,
        "corrected": corrected,
        "low": corrected - 0.02 if low is None else low,
        "high": corrected + 0.02 if high is None else high,
        "unclear": unclear,
        "n_ref": 50,
        "n_est": 40,
    }


def test_showdown_compares_fast_and_quality_with_both_numbers():
    rows = [
        crow("none+adtof", "macro", 0.812, measured=0.770, unclear=7),
        crow("combo+quality", "macro", 0.818, measured=0.776, unclear=5),
        crow("none+adtof", "SD", 0.90),
        crow("combo+quality", "SD", 0.93),
        crow("none+adtof", "HH", 0.80),
        crow("combo+quality", "HH", 0.80),
    ]
    text = rewards.showdown(rows)
    assert "SHOWDOWN" in text and "Fast" in text and "Quality" in text
    assert "0.770" in text and "0.812" in text and "0.792–0.832" in text
    assert "snare" in text and "hi-hat" in text and "tie" in text
    assert "Quality" in text.splitlines()[-2] and "+0.006" in text  # the overall winner
    assert "7 of 90" in text  # unclear answers of Fast's spots
