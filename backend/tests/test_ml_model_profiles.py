"""Tests for conditioning-specific MusicGen model selection and caching."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import src.ml_inference as ml_inference
from src.ml_inference import get_model_config


def _reset_engine_cache():
    ml_inference._inference_instances.clear()


def test_checkpoint_specific_engines_are_isolated_by_soundfont(monkeypatch, tmp_path):
    checkpoints = {
        soundfont: tmp_path / f"best_model_{soundfont}.pt"
        for soundfont in ("snes", "gba")
    }
    for checkpoint in checkpoints.values():
        checkpoint.touch()

    monkeypatch.setattr(ml_inference, "get_checkpoint_path", lambda soundfont: checkpoints.get(soundfont))
    monkeypatch.setattr(ml_inference, "MusicGenInference", lambda soundfont, conditioning: _FakeEngine(soundfont, conditioning))
    _reset_engine_cache()

    snes_engine = ml_inference.get_inference_engine("snes", "text")
    gba_engine = ml_inference.get_inference_engine("gba", "text")

    assert snes_engine is not gba_engine
    assert snes_engine.soundfont_id == "snes"
    assert gba_engine.soundfont_id == "gba"


def test_base_model_engine_is_shared_when_no_checkpoint_exists(monkeypatch):
    monkeypatch.setattr(ml_inference, "get_checkpoint_path", lambda soundfont: None)
    monkeypatch.setattr(ml_inference, "MusicGenInference", lambda soundfont, conditioning: _FakeEngine(soundfont, conditioning))
    _reset_engine_cache()

    snes_engine = ml_inference.get_inference_engine("snes", "text")
    gba_engine = ml_inference.get_inference_engine("gba", "text")

    assert gba_engine is snes_engine
    assert gba_engine.soundfont_id == "gba"


def test_text_and_audio_engines_remain_distinct(monkeypatch):
    monkeypatch.setattr(ml_inference, "get_checkpoint_path", lambda soundfont: None)
    monkeypatch.setattr(ml_inference, "MusicGenInference", lambda soundfont, conditioning: _FakeEngine(soundfont, conditioning))
    _reset_engine_cache()

    text_engine = ml_inference.get_inference_engine("gba", "text")
    audio_engine = ml_inference.get_inference_engine("gba", "audio")

    assert audio_engine is not text_engine
    assert text_engine.conditioning_type == "text"
    assert audio_engine.conditioning_type == "audio"


class _FakeEngine:
    def __init__(self, soundfont_id: str, conditioning_type: str):
        self.soundfont_id = soundfont_id
        self.conditioning_type = conditioning_type


def test_default_text_model(monkeypatch):
    monkeypatch.delenv("MUSICGEN_MODEL_NAME", raising=False)
    monkeypatch.delenv("MUSICGEN_TEXT_MODEL_NAME", raising=False)
    assert get_model_config("text")["model_name"] == "facebook/musicgen-small"


def test_default_melody_model(monkeypatch):
    monkeypatch.delenv("MUSICGEN_MODEL_NAME", raising=False)
    monkeypatch.delenv("MUSICGEN_MELODY_MODEL_NAME", raising=False)
    assert get_model_config("audio")["model_name"] == "facebook/musicgen-melody"


def test_legacy_model_name_overrides_conditioning_profiles(monkeypatch):
    monkeypatch.setenv("MUSICGEN_MODEL_NAME", "test/legacy-musicgen")
    monkeypatch.setenv("MUSICGEN_TEXT_MODEL_NAME", "test/text-model")
    monkeypatch.setenv("MUSICGEN_MELODY_MODEL_NAME", "test/melody-model")
    assert get_model_config("text")["model_name"] == "test/legacy-musicgen"
    assert get_model_config("audio")["model_name"] == "test/legacy-musicgen"


def test_model_loading_retries_after_failure_and_reuses_success(monkeypatch):
    calls = []

    class Model:
        def set_generation_params(self, **kwargs):
            if len(calls) == 1:
                raise RuntimeError("initialization failed")

    def get_pretrained(name, device):
        calls.append((name, device))
        return Model()

    monkeypatch.setattr(ml_inference, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    monkeypatch.setattr(ml_inference, "_AUDIOCRAFT_AVAILABLE", True)
    monkeypatch.setattr(ml_inference, "MusicGen", SimpleNamespace(get_pretrained=get_pretrained))
    monkeypatch.setattr(ml_inference, "get_checkpoint_path", lambda style: None)
    monkeypatch.setattr(ml_inference, "get_model_config", lambda conditioning: {
        "model_name": "mock", "device": "cpu", "duration": 15,
        "top_k": 250, "top_p": 0.0, "temperature": 1.0,
    })
    engine = ml_inference.MusicGenInference("snes", "text")
    with pytest.raises(RuntimeError, match="initialization failed"):
        engine.load_model()
    assert engine.model is None
    engine.load_model()
    model = engine.model
    engine.load_model()
    assert engine.model is model
    assert len(calls) == 2


def test_cuda_diagnostics_tolerate_unavailable_memory_stats(monkeypatch):
    def unavailable(device):
        raise RuntimeError("memory stats unavailable")

    def empty_cache():
        raise RuntimeError("cache unavailable")

    cuda = SimpleNamespace(is_available=lambda: True, get_device_name=lambda device: "Mock GPU",
                           memory_allocated=unavailable, empty_cache=empty_cache)
    monkeypatch.setattr(ml_inference, "torch", SimpleNamespace(cuda=cuda))
    diagnostics = ml_inference.get_device_diagnostics("cuda:0")
    assert diagnostics == {
        "selected_device": "cuda:0", "cuda_available": True,
        "gpu_name": "Mock GPU", "allocated_memory_bytes": None,
    }
    ml_inference.release_cuda_cache("cuda:0")
