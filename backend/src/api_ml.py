"""ML-based audio generation endpoint using MusicGen."""

import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from src.audio_renderer import get_tool_versions, render_midi_to_audio
from src.log_events import log_event
from src.ml_inference import check_ml_dependencies, get_checkpoint_path, get_inference_engine
from src.schema import (
    error_body,
    is_allowed_content_type,
    is_allowed_extension,
    MAX_UPLOAD_BYTES,
    safe_midi_input_basename,
)
from src.soundfonts import get_soundfont_path

router = APIRouter()


def get_ml_availability() -> bool:
    """Return True if ML (AudioCraft + at least one checkpoint) is available."""
    deps = check_ml_dependencies()
    return bool(deps.get("audiocraft") and deps.get("checkpoint_exists"))


def get_ml_available_styles() -> list:
    """Return list of style IDs that have ML checkpoints."""
    deps = check_ml_dependencies()
    return deps.get("available_soundfonts", [])


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
            detail=error_body(
                "ML dependencies not installed. Install audiocraft: pip install audiocraft torch torchaudio",
                code="ML_UNAVAILABLE",
            ),
        )
    if not deps["checkpoint_exists"]:
        available_deps = check_ml_dependencies()
        available = available_deps.get("available_soundfonts", [])
        raise HTTPException(
            503,
            detail=error_body(
                f"Model checkpoint not found for {soundfont.upper()}. "
                f"Available soundfonts: {', '.join(available) if available else 'none'}. "
                f"Place best_model_{soundfont}.pt in MLtraining/",
                code="CHECKPOINT_NOT_FOUND",
            ),
        )

    if not is_allowed_extension(file.filename or ""):
        raise HTTPException(
            400,
            detail=error_body(
                "Only .mid, .midi files accepted for ML generation",
                code="INVALID_EXTENSION",
            ),
        )
    if not is_allowed_content_type(file.content_type):
        raise HTTPException(
            415,
            detail=error_body(
                "Content-Type not allowed for upload. Use audio/midi or application/octet-stream.",
                code="INVALID_CONTENT_TYPE",
            ),
        )

    workspace = create_workspace()
    input_basename = safe_midi_input_basename(file.filename or "input.mid")
    input_path = workspace / input_basename

    try:
        content = b""
        read_size = 0
        chunk_size = 1024 * 1024
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            read_size += len(chunk)
            if read_size > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    413,
                    detail=error_body(
                        f"File exceeds maximum size ({MAX_UPLOAD_BYTES // (1024*1024)} MiB).",
                        code="PAYLOAD_TOO_LARGE",
                    ),
                )
            content += chunk
        input_path.write_bytes(content)
        processing_logs = [log_event("info", "upload", "File received and saved")]

        # Step 1: Render MIDI to WAV using soundfont (this is our melody prompt)
        soundfont_path = get_soundfont_path(soundfont)
        if not soundfont_path.exists():
            raise HTTPException(
                503,
                detail=error_body(
                    f"Soundfont not found: {soundfont_path.name}",
                    code="SOUNDFONT_NOT_FOUND",
                ),
            )

        # Step 1: Render MIDI to WAV with timeout
        try:
            prompt_wav_path = await asyncio.wait_for(
                asyncio.to_thread(render_midi_to_audio, input_path, soundfont_path, "wav"),
                timeout=240.0,
            )
            processing_logs.append(log_event("info", "render", "Prompt WAV rendered from MIDI"))
        except asyncio.TimeoutError:
            raise HTTPException(
                500,
                detail=error_body(
                    "Audio rendering timed out. MIDI file may be too complex.",
                    code="RENDER_TIMEOUT",
                ),
            )

        # Step 2: Generate audio with MusicGen conditioned on the prompt (with timeout)
        inference = get_inference_engine(soundfont)

        stem = Path(input_basename).stem
        safe_stem = "".join(c for c in stem if c.isalnum() or c in " ()-_")[:200] or "song"
        output_filename = f"ML_{soundfont.upper()}_{safe_stem}.wav"
        output_wav_path = workspace / output_filename

        descriptions = [description] if description.strip() else ["video game music"]

        # ML inference with timeout (600s = 10 min for generation)
        try:
            generated_path = await asyncio.wait_for(
                asyncio.to_thread(
                    inference.generate_from_audio,
                    prompt_wav_path,
                    output_wav_path,
                    descriptions,
                ),
                timeout=600.0,
            )
            processing_logs.append(log_event("info", "encode", "MusicGen audio generated"))
        except asyncio.TimeoutError:
            raise HTTPException(
                500,
                detail=error_body(
                    "ML generation timed out after 10 minutes. Try a shorter MIDI file or check GPU availability.",
                    code="ML_GENERATION_TIMEOUT",
                ),
            )

        # Step 3: Convert to MP3
        from src.audio_renderer import convert_to_mp3
        output_mp3_path = generated_path.with_suffix(".mp3")
        convert_to_mp3(generated_path, output_mp3_path)
        processing_logs.append(log_event("info", "encode", "Converted to MP3"))

        # Cleanup: schedule workspace deletion
        async def delayed_cleanup():
            import asyncio
            await asyncio.sleep(1800)  # 30 min
            shutil.rmtree(workspace, ignore_errors=True)

        background_tasks.add_task(delayed_cleanup)

        checkpoint_path = get_checkpoint_path(soundfont)
        tool_versions = get_tool_versions()
        provenance = {
            "input_filename": input_basename,
            "mode": "ml",
            "style": soundfont,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "tool_versions": tool_versions,
            "checkpoint": checkpoint_path.name if checkpoint_path else None,
            "fallback_to_base": False,
        }
        metadata_path = workspace / "metadata.json"
        metadata_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")

        return {
            "request_id": workspace.name,
            "audio_url": f"/download/audio/{workspace.name}/{output_mp3_path.name}",
            "prompt_soundfont": soundfont,
            "description": descriptions[0],
            "method": "musicgen_ml",
            "logs": processing_logs,
            "metadata_url": f"/download/metadata/{workspace.name}",
            "metadata": provenance,
        }

    except HTTPException:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(workspace, ignore_errors=True)
        raise HTTPException(
            500,
            detail=error_body(
                "ML generation failed. Check logs or try again.",
                code="PROCESSING_ERROR",
                debug=str(e),
            ),
        )
