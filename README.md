# MIDI Remaster Lab

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
git clone <your-repo-url>
cd RemasterOSTv2
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

Leave this terminal open. You should see something like:

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
RemasterOSTv2/
├── backend/                 # FastAPI API + MIDI/audio pipeline
│   ├── src/
│   │   ├── api.py           # Main app, /api/remaster, soundfonts, health
│   │   ├── api_ml.py        # /api/remaster_ml, ML health, available soundfonts
│   │   ├── ml_inference.py  # MusicGen load + generate_with_chroma
│   │   ├── audio_renderer.py
│   │   ├── instrument_classifier.py
│   │   ├── instrument_mapper.py
│   │   ├── feature_extractor.py
│   │   └── soundfonts/      # Per–soundfont .sf2 paths
│   ├── data/soundfonts/     # .sf2 files (snes, gba, nds, ps2, wii)
│   └── requirements.txt     # Python deps for API + optional ML
├── frontend/                # React + Vite UI
│   ├── src/
│   │   ├── App.tsx          # Upload, mode toggle, soundfont pills, results
│   │   ├── main.tsx
│   │   └── styles.css
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts       # Port 3000, proxy to backend 8001
├── MLtraining/              # Local MusicGen fine-tuning scripts
│   ├── musicgen_training_local.py      # SNES
│   ├── musicgen_training_*_local.py   # GBA, NDS, PS2, Wii
│   ├── requirements_local.txt
│   └── README.md            # Checkpoint naming, status, training notes
├── MLcolabtraining/         # Colab-oriented training scripts (same per–soundfont)
│   └── musicgen_training*.py
├── .gitignore
├── README.md                # This file
└── requirements.txt         # Root requirements overview (see below)
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

The repo includes a root **requirements.txt** that lists required and optional dependencies for the whole project and points to backend/MLtraining requirements. See that file for one-place overview; actual install is still done per folder (`backend`, `MLtraining`) as above.

---

## Ports

- **Frontend**: 3000  
- **Backend**: 8001  

The frontend proxies `/api`, `/download`, and `/health` to the backend (see `frontend/vite.config.ts`).

---

## License and attribution

Soundfonts in `backend/data/soundfonts/` may have their own terms; ensure you have the right to use and redistribute them.  
ML mode uses [Meta’s AudioCraft / MusicGen](https://github.com/facebookresearch/audiocraft).
