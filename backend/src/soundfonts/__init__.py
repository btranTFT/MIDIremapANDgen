"""Soundfont registry."""

from pathlib import Path

from . import snes, gba, nds, ps2, wii

_REGISTRY = [
    ("snes", snes.PATH),
    ("gba", gba.PATH),
    ("nds", nds.PATH),
    ("ps2", ps2.PATH),
    ("wii", wii.PATH),
]

VALID_IDS = {sid for sid, _ in _REGISTRY}


def get_soundfont_path(soundfont_id: str) -> Path:
    soundfont_id = (soundfont_id or "").strip().lower()
    for sid, path in _REGISTRY:
        if sid == soundfont_id:
            resolved = path.resolve()
            print(f"[SOUNDFONTS] get_soundfont_path({soundfont_id!r}) -> {resolved}")
            return resolved
    raise ValueError(f"Unknown soundfont id: {soundfont_id!r}. Valid: {sorted(VALID_IDS)}")


def list_soundfonts():
    return [{"id": sid, "label": sid.upper()} for sid, _ in _REGISTRY]

