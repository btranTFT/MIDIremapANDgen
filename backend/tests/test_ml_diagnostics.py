from types import SimpleNamespace

import mido

import src.ml_inference as ml_inference
from src.instrument_mapper import remap_midi


def _set_unavailable(monkeypatch, torch_error, audiocraft_error="ImportError: AudioCraft is missing"):
    monkeypatch.setattr(ml_inference, "torch", None)
    monkeypatch.setattr(ml_inference, "_TORCH_IMPORT_ERROR", torch_error)
    monkeypatch.setattr(ml_inference, "_AUDIOCRAFT_AVAILABLE", False)
    monkeypatch.setattr(ml_inference, "_AUDIOCRAFT_IMPORT_ERROR", audiocraft_error)


def test_torch_import_error_is_exposed(monkeypatch):
    _set_unavailable(monkeypatch, "ImportError: No module named 'torch'")

    diagnostics = ml_inference.get_ml_diagnostics()

    assert diagnostics["torch_available"] is False
    assert diagnostics["torch_error"] == "ImportError: No module named 'torch'"
    assert "Torch is unavailable" in diagnostics["ml_reason"]


def test_torch_oserror_is_exposed(monkeypatch):
    error = "OSError: [WinError 4551] An Application Control policy has blocked this file."
    _set_unavailable(monkeypatch, error)

    diagnostics = ml_inference.get_ml_diagnostics()

    assert diagnostics["torch_error"] == error
    assert "Windows Application Control policy" in diagnostics["ml_reason"]
    assert "not a missing dependency" in diagnostics["ml_reason"]


def test_audiocraft_oserror_uses_policy_diagnostic(monkeypatch):
    monkeypatch.setattr(ml_inference, "torch", SimpleNamespace(__version__="2.0"))
    monkeypatch.setattr(ml_inference, "_TORCH_IMPORT_ERROR", None)
    monkeypatch.setattr(ml_inference, "_AUDIOCRAFT_AVAILABLE", False)
    monkeypatch.setattr(
        ml_inference,
        "_AUDIOCRAFT_IMPORT_ERROR",
        "OSError: [WinError 4551] blocked DLL",
    )

    diagnostics = ml_inference.get_ml_diagnostics()

    assert diagnostics["audiocraft_available"] is False
    assert "Windows Application Control policy" in diagnostics["ml_reason"]
    assert "CPU-only" in diagnostics["recommended_action"]


def test_normal_ml_availability(monkeypatch):
    monkeypatch.setattr(ml_inference, "torch", SimpleNamespace(__version__="2.0"))
    monkeypatch.setattr(ml_inference, "_TORCH_IMPORT_ERROR", None)
    monkeypatch.setattr(ml_inference, "_AUDIOCRAFT_AVAILABLE", True)
    monkeypatch.setattr(ml_inference, "_AUDIOCRAFT_IMPORT_ERROR", None)

    diagnostics = ml_inference.get_ml_diagnostics()

    assert diagnostics["ml_available"] is True
    assert diagnostics["torch_error"] is None
    assert diagnostics["audiocraft_error"] is None
    assert diagnostics["recommended_action"] == "No action required."


def test_baseline_operation_remains_available_without_ml(monkeypatch, minimal_midi_path):
    _set_unavailable(monkeypatch, "OSError: [WinError 4551] blocked")

    diagnostics = ml_inference.get_ml_diagnostics()
    remapped = remap_midi(mido.MidiFile(minimal_midi_path), soundfont_id="snes")

    assert diagnostics["ml_available"] is False
    assert len(remapped.tracks) > 0
