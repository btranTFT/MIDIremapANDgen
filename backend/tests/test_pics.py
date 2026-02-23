"""
Tests for Pitch-Interval Contour Similarity (PICS).

Proposal citation:
    main.tex §Evaluation Table 2: "Pitch-interval contour similarity —
        Input vs. baseline audio — Content preservation (RQ1)"
    main.tex §Success Criteria: "pitch-interval contour similarity >= 0.70"
    Reference: MIREX Symbolic Melodic Similarity task (mirex_sms)

Run:
    cd backend
    python -m pytest tests/test_pics.py -v
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import mido
import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from src.evaluation.pics import (
    pics,
    pics_from_paths,
    _pitch_to_contour,
    _lcs_length,
)


# ── Unit tests for internal helpers ──────────────────────────────────────────


class TestPitchToContour:
    def test_ascending(self):
        assert _pitch_to_contour([60, 62, 64]) == [1, 1]

    def test_descending(self):
        assert _pitch_to_contour([72, 67, 60]) == [-1, -1]

    def test_repeated(self):
        assert _pitch_to_contour([60, 60, 60]) == [0, 0]

    def test_mixed(self):
        # up, down, same
        assert _pitch_to_contour([60, 64, 62, 62]) == [1, -1, 0]

    def test_single_note(self):
        assert _pitch_to_contour([60]) == []

    def test_empty(self):
        assert _pitch_to_contour([]) == []


class TestLCSLength:
    def test_identical(self):
        assert _lcs_length([1, -1, 0, 1], [1, -1, 0, 1]) == 4

    def test_one_empty(self):
        assert _lcs_length([], [1, -1, 0]) == 0
        assert _lcs_length([1, -1, 0], []) == 0

    def test_both_empty(self):
        assert _lcs_length([], []) == 0

    def test_no_common(self):
        assert _lcs_length([1, 1, 1], [-1, -1, -1]) == 0

    def test_partial_overlap(self):
        # LCS of [1, -1, 1] and [1, 1, -1] -> [1, -1] or [1, 1] = length 2
        assert _lcs_length([1, -1, 1], [1, 1, -1]) == 2

    def test_subsequence(self):
        # [1, -1] is a subsequence of [1, 0, -1, 1]
        assert _lcs_length([1, -1], [1, 0, -1, 1]) == 2


# ── Integration tests with MIDI fixtures ─────────────────────────────────────


class TestPICS:
    def test_identical_midi_gives_perfect_score(self, minimal_midi_path):
        """Identical files must produce PICS = 1.0 (RQ1 sanity check)."""
        score = pics(minimal_midi_path, minimal_midi_path)
        assert score == 1.0, f"Expected 1.0, got {score}"

    def test_score_in_range(self, minimal_midi_path):
        """PICS must be in [0, 1] for any valid MIDI pair."""
        score = pics(minimal_midi_path, minimal_midi_path)
        assert 0.0 <= score <= 1.0

    def test_transposition_invariance(self, minimal_midi_path):
        """
        Transposing all notes by a constant should not change the contour,
        so PICS should remain 1.0.
        """
        midi = mido.MidiFile(str(minimal_midi_path))

        # Create a transposed copy (+5 semitones)
        transposed = mido.MidiFile(type=midi.type, ticks_per_beat=midi.ticks_per_beat)
        for track in midi.tracks:
            new_track = mido.MidiTrack()
            for msg in track:
                if msg.type in ("note_on", "note_off"):
                    new_msg = msg.copy(note=min(msg.note + 5, 127))
                    new_track.append(new_msg)
                else:
                    new_track.append(msg)
            transposed.tracks.append(new_track)

        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            tmp = f.name
        try:
            transposed.save(tmp)
            score = pics(minimal_midi_path, tmp)
            assert score == 1.0, (
                f"Transposition should not affect contour, but PICS = {score}"
            )
        finally:
            os.unlink(tmp)

    def test_inverted_contour_gives_zero(self):
        """
        A melody and its pitch-inversion should have no common contour
        subsequence (all +1 vs all -1).
        """
        # Ascending melody
        asc = mido.MidiFile(type=1, ticks_per_beat=480)
        t0 = mido.MidiTrack()
        t0.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))
        t0.append(mido.MetaMessage("end_of_track", time=0))
        asc.tracks.append(t0)
        t1 = mido.MidiTrack()
        for note in [60, 62, 64, 66, 68]:
            t1.append(mido.Message("note_on", note=note, velocity=80, channel=0, time=0))
            t1.append(mido.Message("note_off", note=note, velocity=0, channel=0, time=240))
        t1.append(mido.MetaMessage("end_of_track", time=0))
        asc.tracks.append(t1)

        # Descending melody
        desc = mido.MidiFile(type=1, ticks_per_beat=480)
        t0d = mido.MidiTrack()
        t0d.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))
        t0d.append(mido.MetaMessage("end_of_track", time=0))
        desc.tracks.append(t0d)
        t1d = mido.MidiTrack()
        for note in [68, 66, 64, 62, 60]:
            t1d.append(mido.Message("note_on", note=note, velocity=80, channel=0, time=0))
            t1d.append(mido.Message("note_off", note=note, velocity=0, channel=0, time=240))
        t1d.append(mido.MetaMessage("end_of_track", time=0))
        desc.tracks.append(t1d)

        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f2:
            asc_path, desc_path = f1.name, f2.name
        try:
            asc.save(asc_path)
            desc.save(desc_path)
            score = pics(asc_path, desc_path)
            assert score == 0.0, f"Inverted contour should give 0.0, got {score}"
        finally:
            os.unlink(asc_path)
            os.unlink(desc_path)

    def test_empty_midi_returns_zero(self):
        """Empty MIDI (no note events) must return 0.0 without raising."""
        empty = mido.MidiFile(type=1, ticks_per_beat=480)
        t0 = mido.MidiTrack()
        t0.append(mido.MetaMessage("end_of_track", time=0))
        empty.tracks.append(t0)

        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            tmp = f.name
        try:
            empty.save(tmp)
            assert pics(tmp, tmp) == 0.0
        finally:
            os.unlink(tmp)

    def test_baseline_remap_preserves_contour(self, minimal_midi_path):
        """
        Baseline remap should preserve all note events, so PICS should be 1.0
        (remapping only changes instrument programs, not notes).
        """
        from src.instrument_mapper import remap_midi

        midi = mido.MidiFile(str(minimal_midi_path))
        remapped = remap_midi(midi, soundfont_id="snes")

        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            tmp = f.name
        try:
            remapped.save(tmp)
            score = pics(minimal_midi_path, tmp)
            assert score >= 0.70, (
                f"PICS after baseline remap = {score:.3f}, below proposal "
                f"threshold of 0.70. Remap may have altered note content."
            )
        finally:
            os.unlink(tmp)

    def test_from_paths_convenience(self, minimal_midi_path):
        """pics_from_paths should give the same result as pics()."""
        score1 = pics(minimal_midi_path, minimal_midi_path)
        score2 = pics_from_paths(str(minimal_midi_path), str(minimal_midi_path))
        assert score1 == score2
