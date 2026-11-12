"""Tests for quantization and MusicXML drum notation."""

import music21
import pytest

from stickler import notation

KICK, SNARE, HAT, CRASH, RIDE, FLOOR = 36, 38, 42, 49, 51, 43
BEATS = [k * 0.5 for k in range(17)]  # 120 BPM, 4 bars of 4/4 plus closing beat
DOWNBEATS = BEATS[:-1:4]


def groove(bars=4, jitter=0.0):
    notes = []
    for bar in range(bars):
        t0 = bar * 2.0
        for k in range(8):
            notes.append((t0 + k * 0.25 + (jitter if k % 2 else -jitter), HAT, 90))
        notes += [(t0, KICK, 100), (t0 + 1.0, KICK, 100), (t0 + 0.5, SNARE, 100)]
        notes.append((t0 + 1.5, SNARE, 100))
    return notes


def parse(xml: str):
    return music21.converter.parse(xml, format="musicxml")


def test_quantize_snaps_jittered_hits_to_sixteenths():
    q = notation.quantize(groove(jitter=0.015), BEATS)
    hats = sorted((n.beat, n.position) for n in q if n.pitch == HAT)
    assert hats[:4] == [(0, (0, 4)), (0, (2, 4)), (1, (0, 4)), (1, (2, 4))]


def test_quantize_detects_triplets():
    notes = [(0.0, SNARE, 100), (0.5 / 3, SNARE, 100), (1.0 / 3, SNARE, 100)]
    q = notation.quantize(notes, BEATS)
    assert [n.position for n in q] == [(0, 3), (1, 3), (2, 3)]


def test_hit_just_before_the_beat_belongs_to_it():
    q = notation.quantize([(0.49, SNARE, 100)], BEATS)
    assert [(n.beat, n.position) for n in q] == [(1, (0, 4))]


def test_duplicates_are_merged():
    q = notation.quantize([(0.0, KICK, 100), (0.01, KICK, 80)], BEATS)
    assert len(q) == 1 and q[0].velocity == 100


def test_hits_outside_the_beat_grid_are_dropped():
    q = notation.quantize([(-1.0, KICK, 100), (99.0, KICK, 100), (0.0, KICK, 100)], BEATS)
    assert len(q) == 1


@pytest.mark.parametrize(("per_bar", "expected"), [(4, (4, 4)), (3, (3, 4))])
def test_time_signature_from_downbeats(per_bar, expected):
    assert notation.time_signature(BEATS, BEATS[::per_bar]) == expected


def test_musicxml_is_valid_percussion_score():
    xml = notation.to_musicxml(groove(), BEATS, DOWNBEATS, title="Groove")
    score = parse(xml)
    part = score.parts[0]
    measures = part.getElementsByClass("Measure")
    assert len(measures) == 4
    assert part.recurse().getElementsByClass("TimeSignature")[0].ratioString == "4/4"
    assert isinstance(part.recurse().getElementsByClass("Clef")[0], music21.clef.PercussionClef)
    assert score.metadata.title == "Groove"


def test_every_hit_appears_once_and_measures_are_full():
    xml = notation.to_musicxml(groove(), BEATS, DOWNBEATS)
    part = parse(xml).parts[0]
    hits = sum(len(n.notes) if hasattr(n, "notes") else 1 for n in part.recurse().notes)
    assert hits == len(groove())
    for m in part.getElementsByClass("Measure"):
        for voice in m.voices or [m]:
            assert voice.duration.quarterLength == pytest.approx(4.0)


def test_cymbals_use_x_noteheads_and_kick_stems_down():
    xml = notation.to_musicxml(groove(), BEATS, DOWNBEATS)
    assert "<notehead>x</notehead>" in xml
    kick = notation.STAFF[KICK]
    assert kick.voice == 2 and kick.step == "F" and kick.octave == 4


def test_triplets_are_written_as_tuplets():
    notes = [(0.0, SNARE, 100), (0.5 / 3, SNARE, 100), (1.0 / 3, SNARE, 100)]
    xml = notation.to_musicxml(notes, BEATS, DOWNBEATS)
    assert "<actual-notes>3</actual-notes>" in xml
    part = parse(xml).parts[0]
    first = [n for n in part.recurse().notes][:3]
    assert all(n.duration.quarterLength == pytest.approx(1 / 3) for n in first)


def test_ghost_notes_are_parenthesized_and_quiet_hits_dropped():
    notes = [(0.0, SNARE, 100), (0.25, SNARE, 30), (0.5, SNARE, 5)]
    q = notation.quantize(notes, BEATS, min_velocity=10)
    assert len(q) == 2
    xml = notation.to_musicxml(notes, BEATS, DOWNBEATS, min_velocity=10, ghost_velocity=40)
    assert 'parentheses="yes"' in xml


def test_pickup_beats_before_first_downbeat_form_an_anacrusis():
    beats = [k * 0.5 for k in range(19)]
    downbeats = beats[2:-1:4]  # two pickup beats
    notes = [(0.0, SNARE, 100), (1.0, KICK, 100)]
    part = parse(notation.to_musicxml(notes, beats, downbeats)).parts[0]
    first = part.getElementsByClass("Measure")[0]
    assert first.duration.quarterLength == pytest.approx(2.0)


def test_tempo_from_beats():
    xml = notation.to_musicxml(groove(), BEATS, DOWNBEATS)
    assert 'tempo="120"' in xml


def test_unknown_pitch_falls_back_to_a_neutral_position():
    xml = notation.to_musicxml([(0.0, 81, 100)], BEATS, DOWNBEATS)
    assert len(parse(xml).parts[0].recurse().notes) == 1


def test_hit_a_hair_before_the_first_beat_snaps_to_it():
    q = notation.quantize([(-0.02, KICK, 100), (-0.2, SNARE, 100)], BEATS)
    assert [(n.beat, n.position, n.pitch) for n in q] == [(0, (0, 4), KICK)]


def test_tempo_uses_the_average_beat_not_the_20ms_grid():
    """Beat This! rounds to 20 ms: at 140 BPM most gaps read 0.42 s (143 BPM) or 0.44 s."""
    import numpy as np

    true = np.arange(200) * 60 / 140
    beats = list(np.round(true / 0.02) * 0.02)
    xml = notation.to_musicxml([(0.0, KICK, 100)], beats, beats[::4])
    assert 'tempo="140"' in xml
