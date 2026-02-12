"""Configuration for soundfonts and instrument mapping."""

import os
from pathlib import Path

COMMERCIAL_BUILD = os.getenv("BUILD_MODE") == "commercial"

# Approved soundfonts (simple allowlist)
ALLOWED_SOUNDFONTS = {
    "snes.sf2": "MIT",
    "gba.sf2": "MIT",
    "nds.sf2": "MIT",
    "ps2.sf2": "MIT",
    "wii.sf2": "MIT",
}

# UI options (id -> filename in backend/data/soundfonts/)
SOUNDFONT_OPTIONS = {
    "snes": "snes.sf2",
    "gba": "gba.sf2",
    "nds": "nds.sf2",
    "ps2": "ps2.sf2",
    "wii": "wii.sf2",
}

# Per-soundfont instrument palettes (kept small but distinct)
SNES_LEADS = [41, 56, 64, 68, 72, 73, 74, 75]
SNES_PADS = [42, 48, 49, 50, 51, 60]
SNES_BASSES = [32, 43, 58, 70]
SNES_PERCUSSION = 47

GBA_LEADS = [80, 81, 82, 83, 87, 88, 89, 90]
GBA_PADS = [92, 93, 94, 95, 98, 99]
GBA_BASSES = [33, 34, 35, 36, 38, 39]
GBA_PERCUSSION = 0

NDS_LEADS = [20, 21, 22, 24, 25, 26, 27, 28]
NDS_PADS = [4, 5, 6, 14, 15, 16, 17]
NDS_BASSES = [32, 35, 39, 40]
NDS_PERCUSSION = 47

PS2_LEADS = [41, 56, 64, 73, 25, 26, 27, 81]
PS2_PADS = [48, 49, 50, 51, 60, 92, 93]
PS2_BASSES = [32, 33, 43, 38]
PS2_PERCUSSION = 47

WII_LEADS = [41, 56, 64, 68, 70, 72, 73, 74]
WII_PADS = [42, 48, 49, 50, 60, 61, 62]
WII_BASSES = [32, 43, 58, 70]
WII_PERCUSSION = 47

SOUNDFONT_INSTRUMENT_SETS = {
    "snes": {"leads": SNES_LEADS, "pads": SNES_PADS, "basses": SNES_BASSES, "percussion": SNES_PERCUSSION},
    "gba": {"leads": GBA_LEADS, "pads": GBA_PADS, "basses": GBA_BASSES, "percussion": GBA_PERCUSSION},
    "nds": {"leads": NDS_LEADS, "pads": NDS_PADS, "basses": NDS_BASSES, "percussion": NDS_PERCUSSION},
    "ps2": {"leads": PS2_LEADS, "pads": PS2_PADS, "basses": PS2_BASSES, "percussion": PS2_PERCUSSION},
    "wii": {"leads": WII_LEADS, "pads": WII_PADS, "basses": WII_BASSES, "percussion": WII_PERCUSSION},
}

SNES_ALL_INSTRUMENTS = sorted(set(SNES_LEADS + SNES_PADS + SNES_BASSES + [SNES_PERCUSSION, 128]))
GBA_ALL_INSTRUMENTS = sorted(set(GBA_LEADS + GBA_PADS + GBA_BASSES + [GBA_PERCUSSION, 128]))
NDS_ALL_INSTRUMENTS = sorted(set(NDS_LEADS + NDS_PADS + NDS_BASSES + [NDS_PERCUSSION, 128]))
PS2_ALL_INSTRUMENTS = sorted(set(PS2_LEADS + PS2_PADS + PS2_BASSES + [PS2_PERCUSSION, 128]))
WII_ALL_INSTRUMENTS = sorted(set(WII_LEADS + WII_PADS + WII_BASSES + [WII_PERCUSSION, 128]))

SOUNDFONT_ALL_INSTRUMENTS = {
    "snes": SNES_ALL_INSTRUMENTS,
    "gba": GBA_ALL_INSTRUMENTS,
    "nds": NDS_ALL_INSTRUMENTS,
    "ps2": PS2_ALL_INSTRUMENTS,
    "wii": WII_ALL_INSTRUMENTS,
}

GM_PROGRAM_NAMES = {
    0: "Piano",
    4: "Electric Piano 1", 5: "Electric Piano 2", 6: "Harpsichord",
    14: "Tubular Bells", 15: "Dulcimer", 16: "Drawbar Organ", 17: "Percussive Organ",
    20: "Church Organ", 21: "Reed Organ", 22: "Accordion",
    24: "Acoustic Guitar", 25: "Electric Guitar", 26: "Distortion Guitar", 27: "Guitar Harmonics",
    32: "Acoustic Bass", 33: "Electric Bass", 34: "Electric Bass (pick)", 35: "Fretless Bass",
    36: "Synth Bass 1", 38: "Synth Bass 2", 39: "Synth Bass 3", 40: "Violin",
    41: "Violin", 42: "Cello", 43: "Contrabass",
    47: "Timpani", 48: "String Ensemble 2", 49: "String Ensemble 1", 50: "Synth Strings 1", 51: "Synth Strings 2",
    56: "Trumpet", 58: "Tuba", 60: "French Horn", 61: "Brass Section", 62: "Synth Brass 1",
    64: "Soprano Sax", 68: "Oboe", 70: "Bassoon", 72: "Piccolo", 73: "Flute", 74: "Recorder", 75: "Pan Flute",
    80: "Lead 1", 81: "Lead 2", 82: "Lead 3", 83: "Lead 4",
    87: "Synth Brass 1", 88: "Synth Brass 2", 89: "Synth Brass 3", 90: "Synth Brass 4",
    92: "Pad 1", 93: "Pad 2", 94: "Pad 3", 95: "Pad 4", 98: "FX 2", 99: "FX 3",
    128: "Drum Kit",
}


def get_program_name(program: int) -> str:
    return GM_PROGRAM_NAMES.get(program, "Drum Kit" if program == 128 else f"Program {program}")


def get_instrument_set(soundfont_id: str) -> dict:
    soundfont_id = (soundfont_id or "snes").strip().lower()
    return SOUNDFONT_INSTRUMENT_SETS.get(soundfont_id, SOUNDFONT_INSTRUMENT_SETS["snes"])


def get_all_instruments(soundfont_id: str) -> list[int]:
    soundfont_id = (soundfont_id or "snes").strip().lower()
    return SOUNDFONT_ALL_INSTRUMENTS.get(soundfont_id, SOUNDFONT_ALL_INSTRUMENTS["snes"])


def is_program_in_soundfont(program: int, soundfont_id: str) -> bool:
    return program in set(get_all_instruments(soundfont_id))


def validate_soundfont(sf_path: Path) -> bool:
    if not sf_path.exists():
        raise FileNotFoundError(f"Soundfont not found: {sf_path}")
    if sf_path.name not in ALLOWED_SOUNDFONTS:
        raise ValueError(f"{sf_path.name} not in approved list. Approved: {sorted(ALLOWED_SOUNDFONTS.keys())}")
    license_type = ALLOWED_SOUNDFONTS[sf_path.name]
    if COMMERCIAL_BUILD and license_type == "GPL":
        raise ValueError("GPL soundfonts not allowed in commercial builds.")
    return True


def get_soundfont_path(choice: str = "snes") -> Path:
    filename = SOUNDFONT_OPTIONS.get(choice, SOUNDFONT_OPTIONS["snes"])
    return Path("data/soundfonts") / filename

