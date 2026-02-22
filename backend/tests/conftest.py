"""
Shared pytest fixtures for backend integration tests.

Creates a minimal valid MIDI file in-process via mido so no binary
fixture needs to be committed to the repo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import mido
import pytest

# Allow imports from backend/src when running from repo root
_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(scope="session")
def minimal_midi_path(tmp_path_factory) -> Path:
    """
    Write a minimal but valid type-1 MIDI file to a temp directory.
    Returns the Path. The file has two tracks (tempo + one melody channel).
    """
    tmp = tmp_path_factory.mktemp("fixtures")
    out = tmp / "test_melody.mid"

    mid = mido.MidiFile(type=1, ticks_per_beat=480)

    # Track 0: tempo
    t0 = mido.MidiTrack()
    t0.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))  # 120 BPM
    t0.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(t0)

    # Track 1: simple melody on channel 0 (C-major arpeggio, 8 notes)
    t1 = mido.MidiTrack()
    t1.append(mido.Message("program_change", program=0, channel=0, time=0))
    for note in [60, 64, 67, 72, 67, 64, 60, 55]:
        t1.append(mido.Message("note_on", note=note, velocity=80, channel=0, time=0))
        t1.append(mido.Message("note_off", note=note, velocity=0, channel=0, time=240))
    t1.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(t1)

    mid.save(str(out))
    return out
