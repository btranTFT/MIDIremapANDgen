"""FastAPI backend for MIDI remastering."""

import asyncio
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import mido
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.audio_renderer import check_dependencies, render_midi_to_audio
from src.instrument_mapper import get_channel_classifications, remap_midi
from src.soundfonts import VALID_IDS, get_soundfont_path, list_soundfonts as list_soundfonts_options

app = FastAPI(title="MIDI Remastering API", version="0.4.0")

# Mount ML router
try:
    from src.api_ml import router as ml_router
    app.include_router(ml_router, prefix="/api", tags=["ML Generation"])
    print("[API] ML router mounted at /api/remaster_ml")
except ImportError as e:
    print(f"[API] ML router not available: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent
TEMP_DIR = BACKEND_ROOT / "temp_uploads"
TEMP_DIR.mkdir(exist_ok=True)


async def cleanup_old_files():
    while True:
        now = datetime.now()
        for item in TEMP_DIR.iterdir():
            if item.is_dir():
                try:
                    age = now - datetime.fromtimestamp(item.stat().st_mtime)
                    if age > timedelta(hours=1):
                        shutil.rmtree(item, ignore_errors=True)
                except Exception:
                    pass
        await asyncio.sleep(300)


@app.on_event("startup")
async def startup():
    asyncio.create_task(cleanup_old_files())


def create_workspace() -> Path:
    workspace = TEMP_DIR / uuid.uuid4().hex
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@app.get("/api/soundfonts")
async def list_soundfonts():
    options = list_soundfonts_options()
    return options


@app.post("/api/remaster")
async def remaster(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    soundfont: str = Form("snes"),
):
    soundfont = (soundfont or "").strip().lower()
    if soundfont not in VALID_IDS:
        soundfont = "snes"

    valid_extensions = (".mid", ".midi")
    if not any(file.filename.lower().endswith(ext) for ext in valid_extensions):
        raise HTTPException(400, f"Only {', '.join(valid_extensions)} files accepted")

    workspace = create_workspace()
    input_path = workspace / file.filename

    try:
        with input_path.open("wb") as f:
            content = await file.read()
            f.write(content)

        midi = mido.MidiFile(input_path)
        classifications = get_channel_classifications(midi, soundfont_id=soundfont)

        output_midi = remap_midi(midi, soundfont_id=soundfont)
        stem = Path(file.filename).stem
        safe_stem = "".join(c for c in stem if c.isalnum() or c in " ()-_")
        safe_stem = safe_stem[:200] or "song"
        output_filename = f"{soundfont.upper()}remap{safe_stem}.mid"
        output_path = workspace / output_filename
        output_midi.save(str(output_path))

        soundfont_path = get_soundfont_path(soundfont)
        audio_url = None
        audio_error = None
        if soundfont_path.exists():
            try:
                audio_path = await asyncio.wait_for(
                    asyncio.to_thread(render_midi_to_audio, output_path, soundfont_path, "mp3"),
                    timeout=240.0,
                )
                audio_url = f"/download/audio/{workspace.name}/{audio_path.name}?sf={soundfont}"
            except Exception as e:
                audio_error = str(e) if str(e) else "Audio rendering failed."
        else:
            audio_error = f"Soundfont not found: {soundfont_path.name}"

        async def delayed_cleanup():
            await asyncio.sleep(1800)
            shutil.rmtree(workspace, ignore_errors=True)

        background_tasks.add_task(delayed_cleanup)

        return {
            "request_id": workspace.name,
            "midi_url": f"/download/midi/{workspace.name}/{output_filename}",
            "audio_url": audio_url,
            "audio_error": audio_error,
            "soundfont": soundfont,
            "classifications": {
                str(ch): {"program": prog, "name": name}
                for ch, (prog, name) in classifications.items()
            },
        }
    except Exception as e:
        shutil.rmtree(workspace, ignore_errors=True)
        raise HTTPException(500, f"Processing error: {str(e)}")


@app.get("/download/midi/{request_id}/{filename}")
async def download_midi(request_id: str, filename: str):
    path = TEMP_DIR / request_id / filename
    if not path.exists():
        raise HTTPException(404, "File not found or expired")
    return FileResponse(path, media_type="audio/midi", filename=filename)


@app.get("/download/audio/{request_id}/{filename}")
async def download_audio(request_id: str, filename: str):
    path = TEMP_DIR / request_id / filename
    if not path.exists():
        raise HTTPException(404, "File not found or expired")
    return FileResponse(path, media_type="audio/mpeg", filename=filename)


@app.get("/health")
async def health():
    deps = check_dependencies()
    return {"status": "ok", "dependencies": deps}

