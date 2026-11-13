"""Tests for conditioning-specific MusicGen model selection."""

from __future__ import annotations

from src.ml_inference import get_model_config


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
