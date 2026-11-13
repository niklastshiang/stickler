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


def test_artist_is_written_as_composer():
    xml = notation.to_musicxml(groove(), BEATS, DOWNBEATS, title="RATATATA", artist="A & B")
    assert '<creator type="composer">A &amp; B</creator>' in xml
    assert parse(xml).metadata.composer == "A & B"


def test_no_artist_no_creator():
    assert "<creator" not in notation.to_musicxml(groove(), BEATS, DOWNBEATS)


def _measures(xml: str) -> list[str]:
    return xml.split("<measure ")[1:]


def test_empty_bars_become_one_multi_measure_rest():
    notes = [n for n in groove(4) if n[0] >= 4.0]  # bars 1 and 2 empty
    xml = notation.to_musicxml(notes, BEATS, DOWNBEATS)
    first, second = _measures(xml)[:2]
    for m in (first, second):
        assert m.count("<note>") == 1 and '<rest measure="yes"/>' in m
    assert "<multiple-rest>2</multiple-rest>" in first and "multiple-rest" not in second
    for m in parse(xml).parts[0].getElementsByClass("Measure"):
        for voice in m.voices or [m]:
            assert voice.duration.quarterLength == pytest.approx(4.0)


def test_a_single_empty_bar_is_a_whole_bar_rest_without_multi_rest():
    notes = [n for n in groove(4) if not 2.0 <= n[0] < 4.0]  # only bar 2 empty
    second = _measures(notation.to_musicxml(notes, BEATS, DOWNBEATS))[1]
    assert second.count("<note>") == 1 and "multiple-rest" not in second


def test_empty_half_of_a_bar_is_one_half_rest():
    xml = notation.to_musicxml([(0.0, SNARE, 100)], BEATS[:5], DOWNBEATS[:1])
    (bar,) = _measures(xml)
    assert bar.count("<rest") == 2  # beat 2: quarter rest, beats 3-4: half rest
    assert "<type>half</type>" in bar and "<voice>2</voice>" not in bar


BEATS8 = [k * 0.5 for k in range(33)]  # 8 bars of 4/4 plus closing beat
DOWNBEATS8 = BEATS8[:-1:4]


def _bar_keys(q, bars):
    return [
        frozenset(
            (n.beat - bar[0], n.position[0] * 12 // n.position[1], n.pitch)
            for n in q
            if bar[0] <= n.beat <= bar[-1]
        )
        for bar in bars
    ]


def test_similar_bars_get_their_majority_pattern_and_fills_stay():
    notes = groove(8)
    notes.remove((2 * 2.0 + 0.25, HAT, 90))  # bar 3 misses a hi-hat (beat 1 "and")
    notes.append((4 * 2.0 + 0.75, FLOOR, 80))  # bar 5 has an extra floor tom
    notes = [n for n in notes if not 14.0 <= n[0] < 16.0]  # bar 8: a fill instead
    notes += [(14.0 + k * 0.25, FLOOR, 100) for k in range(8)]
    q = notation.quantize(notes, BEATS8)
    layout = notation.bar_layout(BEATS8, DOWNBEATS8)
    simple = notation.simplify(q, layout.bars)
    keys = _bar_keys(simple, layout.bars)
    assert len(set(keys[:7])) == 1  # bars 1-7: one groove
    assert keys[7] == _bar_keys(q, layout.bars)[7]  # the fill is untouched
    assert keys[0] == _bar_keys(q, layout.bars)[0]  # the majority is the plain groove


def test_small_groups_are_left_alone():
    notes = groove(2) + [(4.0 + k * 0.5, FLOOR, 100) for k in range(4)]
    beats, downbeats = BEATS8[:13], DOWNBEATS8[:3]
    q = notation.quantize(notes, beats)
    layout = notation.bar_layout(beats, downbeats)
    assert notation.simplify(q, layout.bars) == q  # only two similar bars


def test_repeated_bars_are_written_once_with_repeat_signs():
    xml = notation.to_musicxml(groove(4), BEATS, DOWNBEATS, repeats=True)
    (bar,) = _measures(xml)
    assert '<repeat direction="forward"/>' in bar
    assert '<repeat direction="backward" times="4"/>' in bar and "4×" in bar
    for m in parse(xml).parts[0].getElementsByClass("Measure"):
        for voice in m.voices or [m]:
            assert voice.duration.quarterLength == pytest.approx(4.0)


def test_a_repeated_two_bar_phrase_is_written_once():
    a, b = groove(1), [(0.0 + k * 0.5, FLOOR, 100) for k in range(4)]
    notes = [
        (t + 4.0 * k, p, v) for k in range(3) for t, p, v in a + [(t + 2.0, p, v) for t, p, v in b]
    ]
    beats = [k * 0.5 for k in range(25)]
    xml = notation.to_musicxml(notes, beats, beats[:-1:4], repeats=True)
    first, second = _measures(xml)
    assert '<repeat direction="forward"/>' in first and 'times="3"' in second


def test_without_repeats_every_bar_is_written_out():
    assert len(_measures(notation.to_musicxml(groove(4), BEATS, DOWNBEATS))) == 4


def _triplet_beat(t0):
    return [(t0 + k * 0.5 / 3, SNARE, 100) for k in range(3)]


def test_simplified_triplet_beats_stay_triplets():
    notes = [n for n in groove(4) if not (n[0] % 2.0 >= 1.5)]  # beat 4 of every bar: empty
    for bar in range(4):
        notes += _triplet_beat(bar * 2.0 + 1.5)
    q = notation.quantize(notes, BEATS)
    layout = notation.bar_layout(BEATS, DOWNBEATS)
    simple = notation.simplify(q, layout.bars)
    assert sorted(simple) == sorted(q)  # identical bars: nothing changes
    xml = notation.to_musicxml(notes, BEATS, DOWNBEATS, simplify_bars=True)
    for m in parse(xml).parts[0].getElementsByClass("Measure"):
        for voice in m.voices or [m]:
            assert voice.duration.quarterLength == pytest.approx(4.0)


def test_a_beat_mixing_sixteenths_and_triplets_keeps_each_bars_own_hits():
    notes = [n for n in groove(4) if not (n[0] % 2.0 >= 1.5)]
    for bar in range(4):  # beat 4: triplets in bars 1-2, sixteenths in bars 3-4
        t0 = bar * 2.0 + 1.5
        notes += (
            _triplet_beat(t0)
            if bar < 2
            else [(t0, SNARE, 100), (t0 + 0.125, SNARE, 100), (t0 + 0.375, SNARE, 100)]
        )
    xml = notation.to_musicxml(notes, BEATS, DOWNBEATS, simplify_bars=True)
    for m in parse(xml).parts[0].getElementsByClass("Measure"):
        for voice in m.voices or [m]:
            assert voice.duration.quarterLength == pytest.approx(4.0)


def test_simplify_never_adds_hits_beyond_the_last_beat():
    notes = [n for n in groove(4) if n[0] < 7.0]  # the last bar has only 2 tracked beats
    beats = BEATS[:15]
    q = notation.quantize(notes, beats)
    layout = notation.bar_layout(beats, DOWNBEATS)
    assert max(layout.bars[-1]) >= len(beats) - 1  # the last bar reaches past the beats
    simple = notation.simplify(q, layout.bars, n_beats=len(beats) - 1)
    assert max(n.beat for n in simple) < len(beats) - 1
