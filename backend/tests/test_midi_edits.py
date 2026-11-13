import mido

from src.midi_edits import build_editor_analysis


def _analysis(track: mido.MidiTrack):
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(track)
    return build_editor_analysis(midi, "snes")


def test_analysis_extracts_note_timing_and_metadata():
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name="Lead", time=0))
    track.append(mido.Message("program_change", channel=0, program=40, time=0))
    track.append(mido.Message("note_on", channel=0, note=60, velocity=90, time=120))
    track.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=480))

    result = _analysis(track)

    assert result["notes"] == [{
        "id": "0-0-60-120",
        "track": 0,
        "track_name": "Lead",
        "channel": 0,
        "pitch": 60,
        "start_tick": 120,
        "duration_ticks": 480,
        "start_seconds": 0.125,
        "duration_seconds": 0.5,
        "velocity": 90,
        "program": 40,
        "instrument_name": "Violin",
    }]
    assert result["ticks_per_beat"] == 480
    assert result["tempo"] == 500000
    assert result["duration_seconds"] == 0.625


def test_analysis_returns_empty_notes_for_midi_without_notes():
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name="Tempo", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))

    result = _analysis(track)

    assert result["notes"] == []
    assert result["channels"] == []
    assert result["duration_seconds"] == 0.0


def test_note_on_with_zero_velocity_closes_note():
    track = mido.MidiTrack()
    track.append(mido.Message("note_on", channel=2, note=64, velocity=70, time=0))
    track.append(mido.Message("note_on", channel=2, note=64, velocity=0, time=240))

    result = _analysis(track)

    assert len(result["notes"]) == 1
    assert result["notes"][0]["duration_ticks"] == 240


def test_overlapping_same_pitch_notes_are_preserved():
    track = mido.MidiTrack()
    track.append(mido.Message("note_on", channel=0, note=60, velocity=70, time=0))
    track.append(mido.Message("note_on", channel=0, note=60, velocity=80, time=120))
    track.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=120))
    track.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=120))

    result = _analysis(track)

    assert len(result["notes"]) == 2
    assert {note["start_tick"] for note in result["notes"]} == {0, 120}
    assert {note["duration_ticks"] for note in result["notes"]} == {120, 360}


def test_three_channel_fixture_preserves_channel_counts_and_programs():
    midi = mido.MidiFile(ticks_per_beat=480)
    for channel, pitch in [(0, 60), (1, 64), (2, 67)]:
        track = mido.MidiTrack()
        track.extend([
            mido.Message("program_change", channel=channel, program=40 + channel, time=0),
            mido.Message("note_on", channel=channel, note=pitch, velocity=80, time=0),
            mido.Message("note_off", channel=channel, note=pitch, velocity=0, time=240),
        ])
        midi.tracks.append(track)

    result = build_editor_analysis(midi, "snes")

    assert len(result["notes"]) == 3
    assert {note["channel"] for note in result["notes"]} == {0, 1, 2}
    assert all(note["duration_ticks"] > 0 for note in result["notes"])
    assert {note["program"] for note in result["notes"]} == {40, 41, 42}
    assert {
        channel: sum(note["channel"] == channel for note in result["notes"])
        for channel in range(3)
    } == {0: 1, 1: 1, 2: 1}
