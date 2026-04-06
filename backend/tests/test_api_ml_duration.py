from pathlib import Path

from src.api_ml import _safe_midi_duration_seconds


def test_safe_midi_duration_seconds_reads_valid_midi(minimal_midi_path):
    duration = _safe_midi_duration_seconds(minimal_midi_path)
    assert duration > 0.0


def test_safe_midi_duration_seconds_falls_back_on_invalid_file(tmp_path: Path):
    bad = tmp_path / "not_a_midi.mid"
    bad.write_bytes(b"this is not midi")

    duration = _safe_midi_duration_seconds(bad, fallback_seconds=12.5)
    assert duration == 12.5
