"""ML-based audio generation endpoint using MusicGen."""

import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from src.audio_renderer import render_midi_to_audio
from src.ml_inference import check_ml_dependencies, get_inference_engine
from src.soundfonts import get_soundfont_path

router = APIRouter()


@router.get("/ml/health")
async def ml_health():
    """Check ML dependencies and model availability for all soundfonts."""
    deps = check_ml_dependencies()
    status = "ready" if deps["audiocraft"] and deps["checkpoint_exists"] else "unavailable"
    return {"status": status, "details": deps}


@router.get("/ml/available_soundfonts")
async def ml_available_soundfonts():
    """Get list of soundfonts with available ML models."""
    deps = check_ml_dependencies()
    return {
        "available": deps.get("available_soundfonts", []),
        "audiocraft_installed": deps.get("audiocraft", False),
    }


@router.post("/remaster_ml")
async def remaster_ml(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    soundfont: str = Form("snes"),
    description: str = Form(""),
):
    """
    Generate audio using fine-tuned MusicGen model.
    
    Process:
    1. Upload MIDI file
    2. Render MIDI to WAV using chosen soundfont (this becomes the melody prompt)
    3. Feed WAV prompt to MusicGen to generate new audio
    4. Return generated MP3
    """
    from src.api import create_workspace
    
    # Validate soundfont
    soundfont = (soundfont or "").strip().lower()
    if soundfont not in ["snes", "gba", "nds", "ps2", "wii"]:
        soundfont = "snes"
    
    # Validate ML dependencies for this specific soundfont
    deps = check_ml_dependencies(soundfont)
    if not deps["audiocraft"]:
        raise HTTPException(
            503,
            "ML dependencies not installed. Install audiocraft: pip install audiocraft torch torchaudio",
        )
    if not deps["checkpoint_exists"]:
        available_deps = check_ml_dependencies()
        available = available_deps.get("available_soundfonts", [])
        raise HTTPException(
            503,
            f"Model checkpoint not found for {soundfont.upper()}. "
            f"Available soundfonts: {', '.join(available) if available else 'none'}. "
            f"Place best_model_{soundfont}.pt in MLtraining/",
        )
    
    # Validate file
    valid_extensions = (".mid", ".midi")
    if not any(file.filename.lower().endswith(ext) for ext in valid_extensions):
        raise HTTPException(400, f"Only {', '.join(valid_extensions)} files accepted for ML generation")
    
    workspace = create_workspace()
    input_path = workspace / file.filename
    
    try:
        # Save uploaded MIDI
        with input_path.open("wb") as f:
            content = await file.read()
            f.write(content)
        
        # Step 1: Render MIDI to WAV using soundfont (this is our melody prompt)
        soundfont_path = get_soundfont_path(soundfont)
        if not soundfont_path.exists():
            raise HTTPException(503, f"Soundfont not found: {soundfont_path.name}")
        
        print(f"[ML API] Rendering MIDI prompt with {soundfont.upper()} soundfont")
        prompt_wav_path = render_midi_to_audio(input_path, soundfont_path, "wav")
        
        # Step 2: Generate audio with MusicGen conditioned on the prompt
        inference = get_inference_engine(soundfont)
        
        stem = Path(file.filename).stem
        safe_stem = "".join(c for c in stem if c.isalnum() or c in " ()-_")[:200] or "song"
        output_filename = f"ML_{soundfont.upper()}_{safe_stem}.wav"
        output_wav_path = workspace / output_filename
        
        descriptions = [description] if description.strip() else ["video game music"]
        
        print(f"[ML API] Generating with MusicGen (prompt: {prompt_wav_path.name})")
        generated_path = inference.generate_from_audio(
            audio_prompt_path=prompt_wav_path,
            output_path=output_wav_path,
            descriptions=descriptions,
        )
        
        # Step 3: Convert to MP3
        from src.audio_renderer import convert_to_mp3
        output_mp3_path = generated_path.with_suffix(".mp3")
        convert_to_mp3(generated_path, output_mp3_path)
        
        # Cleanup: schedule workspace deletion
        async def delayed_cleanup():
            import asyncio
            await asyncio.sleep(1800)  # 30 min
            shutil.rmtree(workspace, ignore_errors=True)
        
        background_tasks.add_task(delayed_cleanup)
        
        return {
            "request_id": workspace.name,
            "audio_url": f"/download/audio/{workspace.name}/{output_mp3_path.name}",
            "prompt_soundfont": soundfont,
            "description": descriptions[0],
            "method": "musicgen_ml",
        }
    
    except Exception as e:
        shutil.rmtree(workspace, ignore_errors=True)
        raise HTTPException(500, f"ML generation error: {str(e)}")
