"""Audit all presets in each .sf2 soundfont file.

Outputs every preset per soundfont, grouped by bank and program number,
along with GM category classification.
"""

import json
from pathlib import Path
from sf2utils.sf2parse import Sf2File

SF_DIR = Path(__file__).resolve().parent.parent / "backend" / "data" / "soundfonts"

# GM instrument families (program 0-127)
GM_FAMILIES = {
    range(0, 8): "Piano",
    range(8, 16): "Chromatic Percussion",
    range(16, 24): "Organ",
    range(24, 32): "Guitar",
    range(32, 40): "Bass",
    range(40, 48): "Strings",
    range(48, 56): "Ensemble",
    range(56, 64): "Brass",
    range(64, 72): "Reed",
    range(72, 80): "Pipe",
    range(80, 88): "Synth Lead",
    range(88, 96): "Synth Pad",
    range(96, 104): "Synth Effects",
    range(104, 112): "Ethnic",
    range(112, 120): "Percussive",
    range(120, 128): "Sound Effects",
}

# Role classification for the baseline mapper
ROLE_HINTS = {
    range(0, 8): "lead/pad",
    range(8, 16): "lead/percussion",
    range(16, 24): "pad",
    range(24, 32): "lead",
    range(32, 40): "bass",
    range(40, 48): "lead/bass",  # strings span wide range
    range(48, 56): "pad",
    range(56, 64): "lead",
    range(64, 72): "lead",
    range(72, 80): "lead",
    range(80, 88): "lead",
    range(88, 96): "pad",
    range(96, 104): "fx",
    range(104, 112): "lead",
    range(112, 120): "percussion",
    range(120, 128): "fx",
}


def get_gm_family(prog: int) -> str:
    for r, name in GM_FAMILIES.items():
        if prog in r:
            return name
    return "Unknown"


def get_role_hint(prog: int) -> str:
    for r, role in ROLE_HINTS.items():
        if prog in r:
            return role
    return "unknown"


def audit_soundfont(sf_path: Path) -> dict:
    presets = []
    try:
        with open(sf_path, "rb") as f:
            sf = Sf2File(f)
            for preset in sf.presets:
                try:
                    # Skip terminal/EOP preset
                    if preset.name == "EOP" or preset.preset == 65535:
                        continue
                    presets.append({
                        "bank": preset.bank,
                        "program": preset.preset,
                        "name": preset.name.strip() if preset.name else f"Program {preset.preset}",
                        "gm_family": get_gm_family(preset.preset) if preset.bank == 0 else "Drum Kit",
                        "role_hint": get_role_hint(preset.preset) if preset.bank == 0 else "percussion",
                    })
                except (IndexError, AttributeError) as e:
                    # Some presets have malformed bag entries; skip them
                    print(f"  [WARN] Skipping preset in {sf_path.name}: {e}")
    except Exception as e:
        print(f"  [ERROR] Failed to parse {sf_path.name}: {e}")
    presets.sort(key=lambda p: (p["bank"], p["program"]))
    return presets


def main():
    sf_files = sorted(SF_DIR.glob("*.sf2"))
    all_results = {}

    for sf_path in sf_files:
        name = sf_path.stem
        presets = audit_soundfont(sf_path)
        all_results[name] = presets

        print(f"\n{'='*80}")
        print(f"  {name.upper()}.sf2  —  {len(presets)} presets")
        print(f"{'='*80}")

        # Group by role for easy reading
        by_role = {}
        for p in presets:
            role = p["role_hint"]
            by_role.setdefault(role, []).append(p)

        for role in ["lead", "lead/pad", "lead/bass", "pad", "bass", "percussion", "lead/percussion", "fx", "unknown"]:
            items = by_role.get(role, [])
            if not items:
                continue
            print(f"\n  [{role.upper()}]")
            for p in items:
                bank_str = f"bank={p['bank']}" if p["bank"] != 0 else ""
                print(f"    prog={p['program']:>3}  {p['name']:<30}  ({p['gm_family']}) {bank_str}")

        print(f"\n  Summary: {len([p for p in presets if p['bank']==0])} melodic, "
              f"{len([p for p in presets if p['bank']!=0])} drum-bank presets")

    # Save JSON for reference
    out_path = SF_DIR.parent.parent / "soundfont_audit.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n\nFull audit saved to: {out_path}")


if __name__ == "__main__":
    main()
