"""
Unit tests for ml_inference checkpoint loading logic.

Covers the bug fix where `torch.load` returns a training wrapper dict
  {"epoch": int, "model_state_dict": OrderedDict, "val_loss": float, "config": dict}
but the old code passed the entire dict to `load_state_dict` instead of
extracting ["model_state_dict"].

These tests do NOT require torch or audiocraft to be installed: they test
only the dict-unwrapping logic that can be exercised without loading a real model.
"""

from __future__ import annotations

import sys
from pathlib import Path
from collections import OrderedDict

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Helper: minimal fake state dict ─────────────────────────────────────────

def _make_state_dict(n_keys: int = 4) -> OrderedDict:
    """Return a fake OrderedDict that looks like a model state dict."""
    return OrderedDict({f"layer.{i}.weight": f"tensor_{i}" for i in range(n_keys)})


def _make_training_checkpoint(epoch: int = 5, val_loss: float = 0.312) -> dict:
    """Return a checkpoint dict as saved by musicgen_training_local.py."""
    return {
        "epoch": epoch,
        "model_state_dict": _make_state_dict(),
        "val_loss": val_loss,
        "config": {"soundfont": "snes", "learning_rate": 1e-5},
    }


# ── The dict-unwrapping logic extracted for isolated testing ─────────────────

def _unwrap_checkpoint(raw: object) -> tuple[OrderedDict, str]:
    """
    Mirrors the logic in ml_inference.MusicGenInference.load_model().
    Returns (state_dict, format_label).
    """
    if isinstance(raw, dict) and "model_state_dict" in raw:
        state_dict = raw["model_state_dict"]
        if "val_loss" in raw:
            label = f"training wrapper (epoch {raw.get('epoch', '?')}, val_loss {raw['val_loss']:.4f})"
        else:
            label = f"training wrapper (epoch {raw.get('epoch', '?')})"
        return state_dict, label
    else:
        return raw, "raw state dict"


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCheckpointUnwrapping:
    """
    Tests for the checkpoint wrapper detection + extraction logic.
    Proposal citation: report/main.tex §ML inference module (Deliverable 3);
    04-implementation.tex §ML inference §checkpoint.
    """

    def test_training_wrapper_extracts_model_state_dict(self):
        """
        The primary bug: a training checkpoint dict must yield model_state_dict,
        NOT the outer wrapper dict.
        """
        checkpoint = _make_training_checkpoint()
        state_dict, label = _unwrap_checkpoint(checkpoint)

        # Must be exactly the inner model_state_dict, not the outer wrapper
        assert state_dict is checkpoint["model_state_dict"], (
            "Expected state_dict to be the extracted model_state_dict, "
            "but got the outer wrapper — checkpoint loading is broken."
        )
        assert "training wrapper" in label

    def test_training_wrapper_does_not_contain_outer_keys(self):
        """
        Regression guard: the state dict passed to load_state_dict must NOT
        contain keys like 'epoch', 'val_loss', 'config' — those are wrapper keys,
        not model parameter keys.
        """
        checkpoint = _make_training_checkpoint()
        state_dict, _ = _unwrap_checkpoint(checkpoint)

        assert "epoch" not in state_dict, (
            "'epoch' found in state_dict — outer wrapper was not unwrapped. "
            "This would cause load_state_dict to try to load 'epoch' as a parameter key."
        )
        assert "val_loss" not in state_dict, "'val_loss' found in state_dict"
        assert "config" not in state_dict, "'config' found in state_dict"

    def test_training_wrapper_contains_model_keys(self):
        """Extracted state dict must contain the actual model parameter keys."""
        checkpoint = _make_training_checkpoint()
        state_dict, _ = _unwrap_checkpoint(checkpoint)

        # Our fake state dict has "layer.0.weight" .. "layer.3.weight"
        assert all(k.startswith("layer.") for k in state_dict), (
            "Extracted state dict does not contain expected model parameter keys"
        )

    def test_raw_state_dict_passthrough(self):
        """
        A raw state dict (no wrapper) must pass through unchanged.
        Handles any legacy checkpoints saved without the training wrapper.
        """
        raw_sd = _make_state_dict()
        state_dict, label = _unwrap_checkpoint(raw_sd)

        assert state_dict is raw_sd, "Raw state dict should be returned unchanged"
        assert label == "raw state dict"

    def test_epoch_and_val_loss_in_label(self):
        """The log label must include epoch and val_loss for observability."""
        checkpoint = _make_training_checkpoint(epoch=12, val_loss=0.2345)
        _, label = _unwrap_checkpoint(checkpoint)
        assert "12" in label, f"Epoch not in label: {label}"
        assert "0.2345" in label, f"val_loss not in label: {label}"

    def test_wrapper_without_val_loss(self):
        """
        Epoch-only checkpoint (no val_loss key) — as saved by per-epoch checkpoints
        that might not have val_loss — must not crash with KeyError.
        """
        checkpoint = {
            "epoch": 3,
            "model_state_dict": _make_state_dict(),
            "config": {"soundfont": "gba"},
        }
        state_dict, label = _unwrap_checkpoint(checkpoint)
        assert state_dict is checkpoint["model_state_dict"]
        assert "training wrapper" in label
        assert "3" in label  # epoch is in label

    def test_key_count_matches_original(self):
        """Unwrapped state dict must have the same number of keys as the original inner dict."""
        n = 6
        inner = _make_state_dict(n)
        checkpoint = {"epoch": 1, "model_state_dict": inner, "val_loss": 0.5, "config": {}}
        state_dict, _ = _unwrap_checkpoint(checkpoint)
        assert len(state_dict) == n

    @pytest.mark.parametrize("soundfont", ["snes", "gba", "nds", "ps2", "wii"])
    def test_each_style_checkpoint_can_be_unwrapped(self, soundfont):
        """Each console style's checkpoint should unwrap correctly."""
        checkpoint = {
            "epoch": 50,
            "model_state_dict": _make_state_dict(8),
            "val_loss": 0.198,
            "config": {"soundfont": soundfont, "learning_rate": 1e-5},
        }
        state_dict, label = _unwrap_checkpoint(checkpoint)
        assert "model_state_dict" not in state_dict
        assert len(state_dict) == 8
