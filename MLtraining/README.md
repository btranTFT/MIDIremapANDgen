# ML Training Checkpoints

This folder contains fine-tuned MusicGen model checkpoints for each console soundfont.

## File naming convention

Each checkpoint must be named according to its target soundfont:

- `best_model_snes.pt` - SNES (Super Nintendo) soundfont model
- `best_model_gba.pt` - GBA (Game Boy Advance) soundfont model
- `best_model_nds.pt` - NDS (Nintendo DS) soundfont model
- `best_model_ps2.pt` - PS2 (PlayStation 2) soundfont model
- `best_model_wii.pt` - Wii soundfont model

## Current status

- ✅ **SNES**: `best_model_snes.pt` (trained)
- ⏳ **GBA**: `best_model_gba.pt` (pending)
- ⏳ **NDS**: `best_model_nds.pt` (pending)
- ⏳ **PS2**: `best_model_ps2.pt` (pending)
- ⏳ **Wii**: `best_model_wii.pt` (pending)

## How it works

1. The backend automatically detects which checkpoints exist
2. The frontend queries `/api/ml/available_soundfonts` on startup
3. Only soundfonts with checkpoints are enabled in ML mode
4. Each model is loaded lazily when first requested and cached in memory

## Training new models

When training a new model for a soundfont:

1. Fine-tune MusicGen on audio samples from that console
2. Save the language model weights as `best_model_{soundfont}.pt`
3. Place the checkpoint in this folder
4. Restart the app - the new soundfont will automatically appear in ML mode

## Technical details

- Base model: `facebook/musicgen-melody` (1.5B parameters, supports audio conditioning)
- Checkpoint contains: Language model state dict only
- Backend loads base MusicGen, then applies checkpoint weights via `lm.load_state_dict()`
- Each soundfont gets its own model instance (cached in `_inference_instances`)
