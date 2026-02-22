"""
Integration tests for the baseline remaster pipeline and API.

Proposal citation:
    Deliverable 4: Demo app — verified to run and return correct structure.
    03-system-design.tex §Baseline Path: Stages — each stage tested below.
    ONBOARDING_REPORT.md §D — "No integration test that actually runs the full pipeline."

Tests:
    - test_instrument_mapper_produces_valid_midi: Baseline remap with each style. (P1-4)
    - test_feature_extractor_on_fixture: Feature extraction returns expected fields.
    - test_evaluation_melody_similarity: Similarity of identical MIDI = 1.0.
    - test_evaluation_onset_fmeasure_identical: F-measure with identical MIDI = 1.0.
    - test_evaluation_onset_fmeasure_empty: F-measure of empty file = 0.0.
    - test_api_remaster_response_shape: Full HTTP POST to /api/remaster (TestClient).
    - test_health_endpoint_structure: /health returns required capability fields.

Run from repo root:
    cd backend
    python -m pytest tests/ -v
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import mido
import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from src.instrument_mapper import remap_midi, get_channel_classifications
from src.feature_extractor import extract_features_from_channel, get_active_channels
from src.evaluation.melody_similarity import melody_contour_similarity
from src.evaluation.onset_alignment import onset_alignment_fmeasure

VALID_STYLES = ["snes", "gba", "nds", "ps2", "wii"]


# ─────────────────────────────────────────────────────────────────────────────
# Baseline pipeline unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFeatureExtractor:
    def test_active_channels_found(self, minimal_midi_path):
        midi = mido.MidiFile(str(minimal_midi_path))
        channels = get_active_channels(midi)
        assert channels, "Should find at least one active channel"

    def test_features_have_expected_fields(self, minimal_midi_path):
        midi = mido.MidiFile(str(minimal_midi_path))
        channels = get_active_channels(midi)
        for ch in channels:
            features = extract_features_from_channel(midi, ch)
            if features is None:
                continue
            assert hasattr(features, "pitch_min")
            assert hasattr(features, "pitch_max")
            assert hasattr(features, "note_density")
            assert hasattr(features, "avg_note_duration")
            assert features.pitch_min <= features.pitch_max

    def test_drum_channel_returns_features(self, minimal_midi_path):
        """Channel 9 can be absent in the fixture — just confirm no crash."""
        midi = mido.MidiFile(str(minimal_midi_path))
        # Channel 9 may not appear in a minimal fixture; extract_features should
        # return None (not raise) for channels with no notes.
        result = extract_features_from_channel(midi, 9)
        assert result is None or hasattr(result, "note_count")


class TestInstrumentMapper:
    @pytest.mark.parametrize("style", VALID_STYLES)
    def test_remap_produces_valid_midi(self, minimal_midi_path, style):
        """
        remap_midi must return a parseable mido.MidiFile for every style.
        Proposal: Obj 2 / Deliverable 2 — deterministic baseline for all 5 styles.
        """
        midi = mido.MidiFile(str(minimal_midi_path))
        remapped = remap_midi(midi, soundfont_id=style)
        assert isinstance(remapped, mido.MidiFile)
        assert len(remapped.tracks) > 0

    @pytest.mark.parametrize("style", VALID_STYLES)
    def test_classifications_dict_structure(self, minimal_midi_path, style):
        midi = mido.MidiFile(str(minimal_midi_path))
        classifications = get_channel_classifications(midi, soundfont_id=style)
        for ch, (prog, name) in classifications.items():
            assert isinstance(ch, int)
            assert isinstance(prog, int)
            assert isinstance(name, str)
            assert 0 <= prog <= 128  # 128 = drums

    @pytest.mark.parametrize("style", VALID_STYLES)
    def test_remap_preserves_track_count(self, minimal_midi_path, style):
        """Remapped MIDI should have the same number of tracks as the input."""
        midi = mido.MidiFile(str(minimal_midi_path))
        remapped = remap_midi(midi, soundfont_id=style)
        assert len(remapped.tracks) == len(midi.tracks)

    def test_remap_notes_are_preserved(self, minimal_midi_path):
        """Note events must not be removed during remapping (timbres change, content preserved)."""
        midi = mido.MidiFile(str(minimal_midi_path))
        remapped = remap_midi(midi, soundfont_id="snes")

        orig_notes = sum(
            1 for track in midi.tracks for msg in track
            if msg.type == "note_on" and msg.velocity > 0
        )
        remap_notes = sum(
            1 for track in remapped.tracks for msg in track
            if msg.type == "note_on" and msg.velocity > 0
        )
        assert remap_notes == orig_notes, (
            f"Note count changed after remap: {orig_notes} → {remap_notes}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation metric tests  (RQ1 — content preservation)
# ─────────────────────────────────────────────────────────────────────────────

class TestMelodySimilarity:
    def test_identical_midi_gives_max_similarity(self, minimal_midi_path):
        """Identical files must produce correlation ≈ 1.0  (RQ1 sanity check)."""
        sim = melody_contour_similarity(minimal_midi_path, minimal_midi_path)
        assert abs(sim - 1.0) < 1e-6, f"Expected ~1.0, got {sim}"

    def test_similarity_range(self, minimal_midi_path):
        """Similarity must be in [-1, 1] for any two valid MIDIs."""
        midi = mido.MidiFile(str(minimal_midi_path))
        remapped = remap_midi(midi, soundfont_id="snes")

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            tmp = f.name
        try:
            remapped.save(tmp)
            sim = melody_contour_similarity(minimal_midi_path, tmp)
            assert -1.0 <= sim <= 1.0, f"Similarity out of range: {sim}"
        finally:
            os.unlink(tmp)

    def test_empty_midi_returns_zero(self):
        """Empty MIDI (no note events) must return 0.0 without raising."""
        empty = mido.MidiFile(type=1, ticks_per_beat=480)
        t0 = mido.MidiTrack()
        t0.append(mido.MetaMessage("end_of_track", time=0))
        empty.tracks.append(t0)

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            tmp = f.name
        try:
            empty.save(tmp)
            result = melody_contour_similarity(tmp, tmp)
            assert result == 0.0
        finally:
            os.unlink(tmp)


class TestOnsetAlignment:
    def test_identical_midi_gives_perfect_fmeasure(self, minimal_midi_path):
        """Identical input → recall = precision = F = 1.0  (RQ1 sanity check)."""
        result = onset_alignment_fmeasure(minimal_midi_path, minimal_midi_path, tolerance_s=0.05)
        assert result["f_measure"] == 1.0, f"Expected 1.0, got {result}"
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0

    def test_returns_expected_keys(self, minimal_midi_path):
        result = onset_alignment_fmeasure(minimal_midi_path, minimal_midi_path)
        assert set(result.keys()) == {"precision", "recall", "f_measure"}

    def test_all_values_in_range(self, minimal_midi_path):
        result = onset_alignment_fmeasure(minimal_midi_path, minimal_midi_path)
        for k, v in result.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"

    def test_remastered_onset_preservation(self, minimal_midi_path):
        """
        Remapped MIDI (baseline output) should have high onset F-measure vs. input
        because remapping preserves all note events.
        Threshold: F ≥ 0.9 with 50 ms tolerance.
        """
        midi = mido.MidiFile(str(minimal_midi_path))
        remapped = remap_midi(midi, soundfont_id="snes")

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            tmp = f.name
        try:
            remapped.save(tmp)
            result = onset_alignment_fmeasure(minimal_midi_path, tmp, tolerance_s=0.05)
            assert result["f_measure"] >= 0.9, (
                f"Onset F-measure after remap too low: {result['f_measure']:.3f}. "
                "This may indicate note events were lost during remapping."
            )
        finally:
            os.unlink(tmp)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP API integration tests (FastAPI TestClient)
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi.testclient import TestClient
    from src.api import app
    _FASTAPI_AVAILABLE = True
except Exception:
    _FASTAPI_AVAILABLE = False


@pytest.mark.skipif(not _FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestAPIRemaster:
    """
    End-to-end HTTP tests using FastAPI's TestClient.
    Audio rendering (FluidSynth/LAME) may be absent in CI — the test accepts
    a successful response regardless of audio_error.
    Proposal: Deliverable 4 (demo app) and 03-system-design.tex §Baseline Path.
    """

    def test_health_endpoint(self):
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        # Proposal: /health returns capability fields used by frontend on load.
        assert "status" in body
        assert "dependencies" in body
        assert "ml_available" in body
        assert "available_styles" in body
        assert "ml_available_styles" in body
        assert "max_upload_bytes" in body

    def test_soundfonts_endpoint(self):
        client = TestClient(app)
        resp = client.get("/api/soundfonts")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        ids = [sf["id"] for sf in body]
        for style in ["snes", "gba", "nds", "ps2", "wii"]:
            assert style in ids, f"{style} missing from /api/soundfonts"

    @pytest.mark.slow
    @pytest.mark.parametrize("style", VALID_STYLES)
    def test_remaster_returns_required_fields(self, minimal_midi_path, style):
        """
        POST /api/remaster must return request_id, midi_url, logs, and soundfont.
        audio_url/audio_error may be present/absent depending on FluidSynth.
        Mark: slow — runs the full pipeline including FluidSynth if available.
        Skip in fast mode: pytest tests/ -m 'not slow'
        """
        client = TestClient(app, raise_server_exceptions=True)
        with open(minimal_midi_path, "rb") as f:
            resp = client.post(
                "/api/remaster",
                data={"soundfont": style},
                files={"file": ("test.mid", f, "audio/midi")},
            )

        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        )
        body = resp.json()
        # Required fields per api.py:253-266 and frontend ResultPanel type
        assert "request_id" in body, "Missing request_id"
        assert "midi_url" in body, "Missing midi_url"
        assert "soundfont" in body, "Missing soundfont"
        assert "logs" in body, "Missing logs"
        assert isinstance(body["logs"], list)
        assert body["soundfont"] == style

    def test_remaster_invalid_extension_returns_400(self, tmp_path):
        client = TestClient(app)
        bad_file = tmp_path / "bad.txt"
        bad_file.write_bytes(b"not a midi")
        with open(bad_file, "rb") as f:
            resp = client.post(
                "/api/remaster",
                data={"soundfont": "snes"},
                files={"file": ("bad.txt", f, "text/plain")},
            )
        assert resp.status_code == 400
        body = resp.json()
        assert body.get("code") == "INVALID_EXTENSION"

    def test_remaster_too_large_returns_413(self, tmp_path):
        """Uploading a file over MAX_UPLOAD_BYTES must return 413 PAYLOAD_TOO_LARGE."""
        from src.schema import MAX_UPLOAD_BYTES
        client = TestClient(app)
        big = tmp_path / "big.mid"
        big.write_bytes(b"\x00" * (MAX_UPLOAD_BYTES + 1))
        with open(big, "rb") as f:
            resp = client.post(
                "/api/remaster",
                data={"soundfont": "snes"},
                files={"file": ("big.mid", f, "audio/midi")},
            )
        assert resp.status_code == 413
        body = resp.json()
        assert body.get("code") == "PAYLOAD_TOO_LARGE"
