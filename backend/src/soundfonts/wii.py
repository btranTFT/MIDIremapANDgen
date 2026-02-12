"""Wii soundfont: backend/data/soundfonts/wii.sf2"""

from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
SOUNDFONT_DIR = _BACKEND_ROOT / "data" / "soundfonts"
PATH = SOUNDFONT_DIR / "wii.sf2"

