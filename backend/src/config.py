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

# ---------------------------------------------------------------------------
# Per-soundfont instrument palettes — expanded from full .sf2 preset audit
# Each list contains only GM program numbers confirmed present in bank 0.
# ---------------------------------------------------------------------------

# ── SNES (128 bank-0 melodic presets — full GM set) ────────────────────────
SNES_LEADS = [
    0, 1, 2, 3, 4, 5, 6, 7,           # Piano family (melodic leads)
    24, 25, 26, 27, 28, 29, 30, 31,    # Guitar family
    40, 41,                             # Violin, Viola
    56, 57, 59, 60, 61, 62, 63,        # Brass (Trumpet, Trombone, Muted Tpt, Horn, Brass, SynBrass)
    64, 65, 66, 67, 68, 69, 71,        # Reed (Sax family, Oboe, English Horn, Clarinet)
    72, 73, 74, 75, 76, 77, 78, 79,    # Pipe (Piccolo → Ocarina)
    80, 81, 82, 83, 84, 85, 86, 87,    # Synth Lead (Square → Bass+Lead)
    104, 105, 106, 107, 108, 109, 110, 111,  # Ethnic (Sitar → Shenai)
]
SNES_PADS = [
    16, 17, 18, 19, 20, 21, 22, 23,    # Organ family
    42,                                 # Cello (sustain role)
    44, 45, 46,                         # Tremolo Strings, Pizzicato, Harp
    48, 49, 50, 51,                     # String Ensemble, Synth Strings
    52, 53, 54, 55,                     # Choir, Voice, Orchestra Hit
    88, 89, 90, 91, 92, 93, 94, 95,    # Synth Pad (Fantasia → Sweep)
    96, 97, 98, 99, 100, 101, 102, 103,  # Synth FX (Ice Rain → Star Theme)
]
SNES_BASSES = [
    32, 33, 34, 35, 36, 37, 38, 39,    # Bass family (Acoustic → Synth Bass 2)
    43, 58, 70,                         # Contrabass, Tuba, Bassoon
]
SNES_PERCUSSION = 47  # Timpani

# ── GBA (87 bank-0 melodic presets) ────────────────────────────────────────
GBA_LEADS = [
    0, 1, 2, 3, 4, 5, 6, 7,           # Piano family
    24, 25, 26, 29, 30, 31,            # Guitar (Nylon, Steel, Jazz, OD, Dist, Harmonics)
    40,                                 # Violin
    56, 57, 58, 59, 60,                # Brass (Trumpet, Horn 2, Tuba, Muted Tpt, Horn)
    68, 69, 70, 71,                    # Reed (Oboe, English Horn, Bassoon, Clarinet)
    72, 73, 77, 78, 79,               # Pipe (Clarinet 2, Flute, Shakuhachi, Whistle, Ocarina)
    80, 81, 82, 83, 84, 85, 86, 87,   # Synth Lead (GB Square → GB Bass+Lead)
    105, 106, 107,                     # Ethnic (Banjo, Shamisen, Koto)
]
GBA_PADS = [
    8, 9, 10, 11, 12, 13, 14,         # Chromatic Perc (Celesta → Tubular Bell)
    16, 17, 18, 19, 20, 21,           # Organ family
    44, 45, 46,                        # Pizzicato, Harp
    48, 49, 50, 51,                    # String Ensemble, Synth Strings
    52, 53, 54, 55,                    # Voice, Orchestra Hit
    88, 89, 90, 91, 92, 93,           # Synth Pad 1-6
]
GBA_BASSES = [
    33, 34, 35, 36, 37, 38, 39,       # Electric Bass → Synth Bass 2
]
GBA_PERCUSSION = 47  # Timpani

# ── NDS (89 bank-0 melodic presets) ────────────────────────────────────────
NDS_LEADS = [
    0, 1, 2, 3, 4, 5, 6, 7,           # Piano family
    24, 25, 26, 27, 28, 29, 30, 31,    # Guitar family (Nylon → Riff)
    40, 41,                             # Violin, Viola
    56, 57, 58, 59, 60, 61, 62,        # Brass (Trumpet → Synth Brass)
    64, 68, 71,                         # Reed (Soprano Sax, Oboe, Clarinet)
    73, 75, 77,                         # Pipe (Flute, Pan Flute, Shakuhachi)
    80, 81,                             # Synth Lead (Square, Sawtooth)
    104, 105, 107,                      # Ethnic (Sitar, Banjo, Koto)
]
NDS_PADS = [
    8, 9, 10, 11, 12, 13, 14,         # Chromatic Perc (Celesta → Tubular Bells)
    16, 17, 18, 19, 21,               # Organ family
    42, 44, 45, 46,                    # Cello, Tremolo, Pizzicato, Harp
    48, 49, 50,                        # String Ensemble, Synth Strings
    52, 53, 55,                        # Choir, Orchestra Hit
    88, 89, 90, 91, 92, 93, 94, 95,   # Synth Pad (Deep New Age → Synth Lead 6)
    96, 97, 98, 99,                    # Synth FX
]
NDS_BASSES = [
    32, 33, 34, 35, 36, 37, 38, 39,   # Acoustic Bass → Synth Bass 2
    43,                                 # Contrabass (for deep bass)
]
NDS_PERCUSSION = 47  # Timpani

# ── PS2 (128 bank-0 melodic presets — full GM set) ─────────────────────────
PS2_LEADS = [
    0, 1, 2, 3, 4, 5, 6, 7,           # Piano family
    24, 25, 26, 27, 28, 29, 30, 31,    # Guitar family
    40, 41,                             # Violin, Viola
    56, 57, 58, 59, 60, 61, 62, 63,    # Brass (Trumpet → Popstar Brass)
    64, 65, 66, 67, 68, 69, 71,        # Reed (all 4 Sax, Oboe, Eng Horn, Clarinet)
    72, 73, 74, 75, 76, 77, 78, 79,    # Pipe (Piccolo → Clay Flute)
    80, 81, 82, 83, 84, 85, 86, 87,    # Synth Lead (Square → Bass+Lead)
    104, 105, 106, 107, 108, 109, 110, 111,  # Ethnic (Sitar → Shenai)
]
PS2_PADS = [
    8, 9, 10, 11, 12, 13, 14, 15,     # Chromatic Perc (Celesta → Hurdy Gurdy)
    16, 17, 18, 19, 20, 21, 22, 23,    # Organ family (all 8)
    42, 44, 45, 46,                    # Cello, Tremolo, Pizzicato, Harp
    48, 49, 50, 51,                    # String Ensemble, Synth Strings
    52, 53, 54, 55,                    # Choir, Voice, Hits
    88, 89, 90, 91, 92, 93, 94, 95,    # Synth Pad (Fantasia → Sweep)
    96, 97, 98, 99, 100, 101, 102, 103,  # Synth FX (Ice Rain → Sci-Fi)
]
PS2_BASSES = [
    32, 33, 34, 35, 36, 37, 38, 39,   # Bass family (Jazz → Funky 80s)
    43, 58, 70,                         # Contrabass, Tuba, Bassoon
]
PS2_PERCUSSION = 47  # Kettledrums

# ── Wii (117 bank-0 melodic presets — near-full GM set) ────────────────────
WII_LEADS = [
    0, 1, 2, 3, 4, 5, 6, 7,           # Piano family
    24, 25, 26, 27, 28, 29, 30, 31,    # Guitar family
    40, 41,                             # Violin, Viola
    56, 57, 58, 59, 60, 61, 62, 63,    # Brass (Trumpet → SynBrass 2)
    64, 65, 66, 67, 68, 69, 71,        # Reed (all 4 Sax, Oboe, Eng Horn, Clarinet)
    72, 73, 74, 75, 76, 77, 78, 79,    # Pipe (Piccolo → Ocarina)
    80, 81, 82, 83, 84, 85, 86, 87,    # Synth Lead (Square → Bass+Lead)
    104, 105, 106, 107, 108, 109, 110, 111,  # Ethnic (Sitar → Shanai)
]
WII_PADS = [
    8, 9, 10, 11, 12, 13, 14, 15,     # Chromatic Perc (Celesta → Santur)
    16, 17, 18, 19, 20, 21, 22, 23,    # Organ family (all 8)
    42, 44, 45, 46,                    # Cello, Tremolo, Pizzicato, Harp
    48, 49, 50, 51,                    # String Ensemble, Synth Strings
    52, 53, 54, 55,                    # Choir, Voice, Orchestra Hit
    88, 89, 90, 91, 92, 93, 94, 95,    # Synth Pad (NewAge → Sweep)
    96, 97, 98, 99, 100, 101, 102, 103,  # Synth FX (Ice Rain → Star Theme)
]
WII_BASSES = [
    32, 33, 34, 35, 36, 37, 38, 39,   # Bass family (Acoustic → Synth Bass 2)
    43, 58, 70,                         # Contrabass, Tuba, Bassoon
]
WII_PERCUSSION = 47  # Timpani

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

# Full GM program name map — names sourced from actual soundfont patches
GM_PROGRAM_NAMES = {
    # Piano (0–7)
    0: "Grand Piano", 1: "Bright Piano", 2: "Electric Grand", 3: "Honky-Tonk Piano",
    4: "Electric Piano 1", 5: "Electric Piano 2", 6: "Harpsichord", 7: "Clavinet",
    # Chromatic Percussion (8–15)
    8: "Celesta", 9: "Glockenspiel", 10: "Music Box", 11: "Vibraphone",
    12: "Marimba", 13: "Xylophone", 14: "Tubular Bells", 15: "Dulcimer",
    # Organ (16–23)
    16: "Drawbar Organ", 17: "Percussive Organ", 18: "Rock Organ", 19: "Church Organ",
    20: "Reed Organ", 21: "Accordion", 22: "Harmonica", 23: "Bandoneon",
    # Guitar (24–31)
    24: "Nylon Guitar", 25: "Steel Guitar", 26: "Jazz Guitar", 27: "Clean Guitar",
    28: "Muted Guitar", 29: "Overdrive Guitar", 30: "Distortion Guitar", 31: "Guitar Harmonics",
    # Bass (32–39)
    32: "Acoustic Bass", 33: "Electric Bass (finger)", 34: "Electric Bass (pick)", 35: "Fretless Bass",
    36: "Slap Bass 1", 37: "Slap Bass 2", 38: "Synth Bass 1", 39: "Synth Bass 2",
    # Strings (40–47)
    40: "Violin", 41: "Viola", 42: "Cello", 43: "Contrabass",
    44: "Tremolo Strings", 45: "Pizzicato Strings", 46: "Harp", 47: "Timpani",
    # Ensemble (48–55)
    48: "String Ensemble 1", 49: "String Ensemble 2", 50: "Synth Strings 1", 51: "Synth Strings 2",
    52: "Choir Aahs", 53: "Voice Oohs", 54: "Synth Voice", 55: "Orchestra Hit",
    # Brass (56–63)
    56: "Trumpet", 57: "Trombone", 58: "Tuba", 59: "Muted Trumpet",
    60: "French Horn", 61: "Brass Section", 62: "Synth Brass 1", 63: "Synth Brass 2",
    # Reed (64–71)
    64: "Soprano Sax", 65: "Alto Sax", 66: "Tenor Sax", 67: "Baritone Sax",
    68: "Oboe", 69: "English Horn", 70: "Bassoon", 71: "Clarinet",
    # Pipe (72–79)
    72: "Piccolo", 73: "Flute", 74: "Recorder", 75: "Pan Flute",
    76: "Bottle Blow", 77: "Shakuhachi", 78: "Whistle", 79: "Ocarina",
    # Synth Lead (80–87)
    80: "Square Lead", 81: "Saw Lead", 82: "Calliope Lead", 83: "Chiffer Lead",
    84: "Charang", 85: "Solo Vox", 86: "5th Saw Wave", 87: "Bass + Lead",
    # Synth Pad (88–95)
    88: "Fantasia", 89: "Warm Pad", 90: "Polysynth", 91: "Space Voice",
    92: "Bowed Glass", 93: "Metal Pad", 94: "Halo Pad", 95: "Sweep Pad",
    # Synth FX (96–103)
    96: "Ice Rain", 97: "Soundtrack", 98: "Crystal", 99: "Atmosphere",
    100: "Brightness", 101: "Goblins", 102: "Echo Drops", 103: "Star Theme",
    # Ethnic (104–111)
    104: "Sitar", 105: "Banjo", 106: "Shamisen", 107: "Koto",
    108: "Kalimba", 109: "Bagpipe", 110: "Fiddle", 111: "Shenai",
    # Percussive (112–119)
    112: "Tinkle Bell", 113: "Agogo", 114: "Steel Drums", 115: "Woodblock",
    116: "Taiko Drum", 117: "Melodic Tom", 118: "Synth Drum", 119: "Reverse Cymbal",
    # Sound FX (120–127)
    120: "Fret Noise", 121: "Breath Noise", 122: "Seashore", 123: "Bird Tweet",
    124: "Telephone", 125: "Helicopter", 126: "Applause", 127: "Gunshot",
    # Drums
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

