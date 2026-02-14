# MIDI Remaster Lab

**Repo:** [https://github.com/btranTFT/MIDIremapANDgen](https://github.com/btranTFT/MIDIremapANDgen)

Transform MIDI files into console-style audio using soundfont synthesis (Baseline) or AI generation (ML mode). Supports SNES, GBA, NDS, PS2, and Wii soundfonts.

## Prerequisites

Install these on your machine before running the app:

| Requirement | Purpose |
|-------------|---------|
| **Node.js 18+** | Frontend (React + Vite) |
| **Python 3.11** | Backend + optional ML (AudioCraft works best on 3.11) |
| **FluidSynth** | Renders MIDI to WAV using `.sf2` soundfonts |
| **LAME** | Converts WAV to MP3 |

### Installing FluidSynth and LAME

- **Windows**: Download [FluidSynth](https://github.com/FluidSynth/fluidsynth/releases) and [LAME](https://lame.sourceforge.io/), add their folders to your system `PATH`.
- **macOS**: `brew install fluid-synth lame`
- **Linux**: `sudo apt install fluidsynth lame` (or your distro’s equivalent)

Verify from a terminal:

```bash
fluidsynth --version
lame --version
```

---

## Quick start (run locally)

### 1. Clone the repo

```bash
git clone https://github.com/btranTFT/MIDIremapANDgen.git
cd MIDIremapANDgen
```

### 2. Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt
```

Start the API (from the `backend` folder):

```bash
python -m uvicorn src.api:app --host 0.0.0.0 --port 8001
```

Leave this terminal open. Users should see:

- `Uvicorn running on http://0.0.0.0:8001`
- `[API] ML router mounted at /api/remaster_ml` (if ML deps are installed) or `ML router not available` (baseline-only)

### 3. Frontend

In a **second terminal**:

```bash
cd frontend
npm install
npm run dev
```

Then open **http://localhost:3000** in your browser.

---

## Project layout

```
MIDIremapANDgen/
├── backend/                 # FastAPI API + MIDI/audio pipeline
│   ├── src/
│   │   ├── api.py           # Main app, /api/remaster, soundfonts, health
│   │   ├── api_ml.py        # /api/remaster_ml, ML health, available soundfonts
│   │   ├── ml_inference.py  # MusicGen load + generate_with_chroma
│   │   ├── audio_renderer.py
│   │   ├── schema.py        # Validation, upload limits, safe filenames
│   │   ├── log_events.py    # Event logging for UI
│   │   ├── instrument_classifier.py
│   │   ├── instrument_mapper.py
│   │   ├── feature_extractor.py
│   │   └── soundfonts/      # Per–soundfont .sf2 paths (snes, gba, nds, ps2, wii)
│   ├── tests/               # Schema and API tests
│   ├── data/soundfonts/     # .sf2 files (snes, gba, nds, ps2, wii)
│   └── requirements.txt    # Python deps for API + optional ML
├── frontend/                # React + Vite UI
│   ├── src/
│   │   ├── App.tsx          # Upload, mode toggle, soundfont pills, results
│   │   ├── main.tsx
│   │   ├── styles.css
│   │   ├── api.ts           # API client, health, request-id
│   │   ├── UploadPanel.tsx
│   │   ├── ResultPanel.tsx
│   │   ├── LogsPanel.tsx
│   │   └── ErrorBoundary.tsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts       # Port 3000, proxy to backend 8001
├── MLtraining/              # Local MusicGen fine-tuning scripts + checkpoints
│   ├── musicgen_training_local.py      # SNES
│   ├── musicgen_training_*_local.py    # GBA, NDS, PS2, Wii
│   ├── requirements_local.txt
│   └── README.md            # Checkpoint naming, status, training notes
├── MLcolabtraining/         # Colab-oriented training scripts (same per–soundfont)
│   └── musicgen_training*.py
├── .gitignore
├── README.md                # This file
└── requirements.txt        # Root deps (includes backend/requirements.txt)
```

---

## Modes

- **Baseline**: MIDI → analysis & remap → FluidSynth → WAV → LAME → MP3. No ML; only backend `requirements.txt` and FluidSynth/LAME needed.
- **ML**: Same pipeline up to a WAV “prompt”; then MusicGen (with optional fine-tuned checkpoint) generates audio from that prompt. Requires ML dependencies and, for best results, checkpoints in `MLtraining/` (see [MLtraining/README.md](MLtraining/README.md)).

---

## Optional: ML generation

To use the **ML** mode in the app:

1. **Python 3.11** is recommended (AudioCraft compatibility).
2. Install backend deps including ML (see `backend/requirements.txt` comments or use a separate venv with `torch`, `torchaudio`, `audiocraft`).
3. Run the backend with that Python:  
   `py -3.11 -m uvicorn src.api:app --host 0.0.0.0 --port 8001`
4. Place fine-tuned checkpoints (e.g. `best_model_snes.pt`) in `MLtraining/` as described in [MLtraining/README.md](MLtraining/README.md).  
   If no checkpoint is present for a soundfont, ML mode will still load the base MusicGen model but won’t use a custom style for that soundfont.

Training (local or Colab) is documented in `MLtraining/` and uses the scripts in `MLtraining/` and `MLcolabtraining/`.

---

## Root `requirements.txt`

The repo includes a root **requirements.txt** that pulls in backend dependencies (`-r backend/requirements.txt`). Install from repo root with `pip install -r requirements.txt` for the API; for ML training, use `MLtraining/requirements_local.txt` in that folder.

---

## Ports

- **Frontend**: 3000 (configurable via `VITE_PORT` env var or `vite.config.ts`)  
- **Backend**: 8001 (configurable via `PORT` env var or uvicorn `--port`)

The frontend proxies `/api`, `/download`, and `/health` to the backend (see `frontend/vite.config.ts`).

---

## Environment Variables

### Creating .env files

Create `.env.example` files in `backend/` and `frontend/` directories as templates (these should be committed to git). Then copy to `.env` for local use (`.env` files are gitignored).

**`backend/.env.example` content:**
```bash
# Backend Environment Variables
# Copy this file to .env and adjust values for your environment

# CORS Configuration (production: set to your frontend URL)
# Comma-separated list of allowed origins
# Default: http://localhost:3000,http://127.0.0.1:3000 (dev only)
# Security: Never use "*" with credentials enabled
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Backend Port (default: 8001)
# PORT=8001

# Build Mode (set to "commercial" to disable GPL soundfonts)
# BUILD_MODE=

# ML Configuration (optional, only needed for ML mode)
# MUSICGEN_CHECKPOINT_PATH=path/to/checkpoint/{soundfont}.pt
# MUSICGEN_MODEL_NAME=facebook/musicgen-melody
# MUSICGEN_DURATION=30.0
# MUSICGEN_DEVICE=cuda
# MUSICGEN_TOP_K=250
# MUSICGEN_TOP_P=0.0
# MUSICGEN_TEMPERATURE=1.0
```

**`frontend/.env.example` content:**
```bash
# Frontend Environment Variables
# Copy this file to .env and adjust values for your environment

# Backend API Base URL
# Default: http://localhost:8001 (for local development)
# Production: Set to your backend URL
VITE_API_BASE=http://localhost:8001

# Frontend Port (default: 3000)
# VITE_PORT=3000
```

### Backend

Create `backend/.env` (copy from `backend/.env.example` or use the template above).

**Note**: The backend reads environment variables via `os.getenv()`. To use `.env` files:
- Set env vars as system environment variables, OR
- Use a process manager (systemd, Docker, etc.) that loads `.env` files, OR
- Add `python-dotenv` to `requirements.txt` and load in `api.py` (optional convenience)

Environment variables:

- **`CORS_ORIGINS`**: Comma-separated allowed origins (default: localhost only).  
  **Production**: Set to your frontend URL(s), e.g. `CORS_ORIGINS=https://your-app.example.com`  
  **Security**: Never use `"*"` with credentials enabled. The backend will reject `"*"` and fall back to localhost-only.

- **`PORT`**: Backend port (default: 8001)

- **`BUILD_MODE`**: Set to `"commercial"` to disable GPL soundfonts

- **ML config** (optional): `MUSICGEN_CHECKPOINT_PATH`, `MUSICGEN_MODEL_NAME`, `MUSICGEN_DURATION`, `MUSICGEN_DEVICE`, `MUSICGEN_TOP_K`, `MUSICGEN_TOP_P`, `MUSICGEN_TEMPERATURE`

**Example `backend/.env`:**
```bash
# CORS: Production - set to your frontend URL
CORS_ORIGINS=https://your-app.example.com

# Optional ML config
MUSICGEN_DEVICE=cuda
MUSICGEN_DURATION=30.0
```

### Frontend

Create `frontend/.env` (copy from `frontend/.env.example` or use the template above).

**Note**: Vite automatically loads `.env` files. Restart the dev server after creating/editing `.env`.

Environment variables:

- **`VITE_API_BASE`**: Backend API URL (default: `http://localhost:8001`)  
  **Production**: Set to your backend URL, e.g. `VITE_API_BASE=https://api.your-app.example.com`

- **`VITE_PORT`**: Frontend dev server port (default: 3000)

**Example `frontend/.env` for production:**
```bash
VITE_API_BASE=https://api.your-app.example.com
```

**Note**: Vite requires the `VITE_` prefix for env vars exposed to client code.

---

## Production Deployment

### Backend

1. Set `CORS_ORIGINS` to your frontend domain(s):
   ```bash
   export CORS_ORIGINS=https://your-app.example.com
   ```

2. Run with production settings:
   ```bash
   python -m uvicorn src.api:app --host 0.0.0.0 --port 8001 --workers 4
   ```

3. Use a reverse proxy (nginx, Caddy) for HTTPS and static file serving.

4. Ensure FluidSynth and LAME are installed on the server.

### Frontend

1. Set `VITE_API_BASE` to your backend URL:
   ```bash
   export VITE_API_BASE=https://api.your-app.example.com
   ```

2. Build:
   ```bash
   npm run build
   ```

3. Serve `dist/` with a static server (nginx, Caddy, Vercel, Netlify, etc.).

**Security**: In production, ensure:
- CORS only allows your frontend domain (never `"*"`)
- Backend is behind HTTPS
- File upload limits are enforced (default: 50 MB)
- Temp files are cleaned up (automatic cleanup runs every 5 minutes)

---

## Troubleshooting

### FluidSynth or LAME not found

**Symptoms**: Audio rendering fails, backend logs show "FluidSynth not found" or "LAME not found"

**Solutions**:
- **Windows**: Add FluidSynth and LAME folders to system `PATH`. Restart terminal/IDE after adding.
- **macOS/Linux**: Install via package manager (`brew install fluid-synth lame` or `apt install fluidsynth lame`)
- Verify: Run `fluidsynth --version` and `lame --version` from terminal

### ML mode unavailable

**Symptoms**: ML button disabled, backend logs show "ML router not available"

**Solutions**:
- Install ML dependencies: `pip install torch torchaudio audiocraft` (requires Python 3.11+)
- Check backend logs for import errors
- Verify AudioCraft installation: `python -c "from audiocraft.models import MusicGen; print('OK')"`
- ML mode works without checkpoints (uses base MusicGen model), but checkpoints improve style matching

### CORS errors in browser

**Symptoms**: Browser console shows "CORS policy" errors, requests fail

**Solutions**:
- **Local dev**: Ensure backend `CORS_ORIGINS` includes `http://localhost:3000`
- **Production**: Set `CORS_ORIGINS` to your exact frontend URL (protocol + domain + port if non-standard)
- Never use `"*"` with credentials enabled (security risk)

### Backend not reachable

**Symptoms**: Frontend shows "Backend not reachable on http://localhost:8001"

**Solutions**:
- Verify backend is running: `curl http://localhost:8001/health`
- Check `VITE_API_BASE` matches backend URL and port
- If using custom port, update both backend (uvicorn `--port`) and frontend (`VITE_API_BASE`)
- Check firewall/antivirus isn't blocking port 8001

### Port already in use

**Symptoms**: "Address already in use" error when starting backend/frontend

**Solutions**:
- Find process using port: `lsof -i :8001` (macOS/Linux) or `netstat -ano | findstr :8001` (Windows)
- Kill process or use different port (update env vars accordingly)

### Temp directory grows large

**Symptoms**: `backend/temp_uploads` directory uses lots of disk space

**Solutions**:
- Cleanup runs automatically every 5 minutes (deletes workspaces older than 1 hour)
- If over 500 MB, cleanup deletes oldest workspaces until under 400 MB
- Manual cleanup: `rm -rf backend/temp_uploads/*` (Linux/macOS) or delete folder contents (Windows)
- Ensure background cleanup task is running (check backend logs on startup)

### MIDI parsing timeout

**Symptoms**: Error "MIDI file parsing timed out" after 30 seconds

**Solutions**:
- File may be corrupt or extremely complex
- Try a simpler/shorter MIDI file
- Check file isn't malformed (open in a MIDI editor)

### ML generation timeout

**Symptoms**: Error "ML generation timed out after 10 minutes"

**Solutions**:
- MIDI file may be too long for ML generation
- Check GPU availability (ML runs faster on CUDA)
- Try Baseline mode for very long files
- Reduce `MUSICGEN_DURATION` env var if you need shorter outputs

---

## License and attribution

Soundfonts in `backend/data/soundfonts/` may have their own terms; ensure you have the right to use and redistribute them.  
ML mode uses [Meta’s AudioCraft / MusicGen](https://github.com/facebookresearch/audiocraft).
