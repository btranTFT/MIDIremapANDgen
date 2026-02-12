"""ML inference module for MusicGen-based audio generation."""

import os
from pathlib import Path
from typing import Optional

import torch

# Defer imports to allow startup without ML dependencies
_AUDIOCRAFT_AVAILABLE = False
try:
    from audiocraft.models import MusicGen
    _AUDIOCRAFT_AVAILABLE = True
except ImportError:
    MusicGen = None


def check_ml_dependencies(soundfont_id: Optional[str] = None) -> dict:
    """Check if ML dependencies are installed and model checkpoint exists."""
    result = {
        "torch": torch.__version__ if hasattr(torch, "__version__") else "unknown",
        "audiocraft": _AUDIOCRAFT_AVAILABLE,
    }
    
    if soundfont_id:
        # Check specific soundfont
        checkpoint_path = get_checkpoint_path(soundfont_id)
        result["checkpoint_exists"] = checkpoint_path is not None and checkpoint_path.exists()
        result["checkpoint_path"] = str(checkpoint_path) if checkpoint_path else None
    else:
        # Check all soundfonts
        available_soundfonts = []
        for sf_id in ["snes", "gba", "nds", "ps2", "wii"]:
            checkpoint_path = get_checkpoint_path(sf_id)
            if checkpoint_path and checkpoint_path.exists():
                available_soundfonts.append(sf_id)
        result["available_soundfonts"] = available_soundfonts
        result["checkpoint_exists"] = len(available_soundfonts) > 0
    
    return result


def get_checkpoint_path(soundfont_id: str = "snes") -> Optional[Path]:
    """Get the path to the fine-tuned model checkpoint for a specific soundfont."""
    # Check env var first (can use {soundfont} placeholder)
    env_path = os.getenv("MUSICGEN_CHECKPOINT_PATH")
    if env_path:
        return Path(env_path.replace("{soundfont}", soundfont_id))
    
    # Default: backend/../MLtraining/best_model_{soundfont}.pt
    # For backwards compatibility, also check best_model.pt for snes
    backend_root = Path(__file__).resolve().parent.parent
    mltraining_dir = backend_root.parent / "MLtraining"
    
    # Try soundfont-specific checkpoint first
    specific_path = mltraining_dir / f"best_model_{soundfont_id}.pt"
    if specific_path.exists():
        return specific_path
    
    # Fall back to generic best_model.pt (only for SNES for backwards compatibility)
    if soundfont_id == "snes":
        generic_path = mltraining_dir / "best_model.pt"
        if generic_path.exists():
            return generic_path
    
    return None


def get_model_config() -> dict:
    """Get ML model configuration."""
    return {
        "model_name": os.getenv("MUSICGEN_MODEL_NAME", "facebook/musicgen-melody"),
        "duration": float(os.getenv("MUSICGEN_DURATION", "30.0")),
        "device": os.getenv("MUSICGEN_DEVICE", "cuda" if torch.cuda.is_available() else "cpu"),
        "top_k": int(os.getenv("MUSICGEN_TOP_K", "250")),
        "top_p": float(os.getenv("MUSICGEN_TOP_P", "0.0")),
        "temperature": float(os.getenv("MUSICGEN_TEMPERATURE", "1.0")),
    }


class MusicGenInference:
    """Wrapper for MusicGen model loading and inference."""
    
    def __init__(self, soundfont_id: str = "snes"):
        if not _AUDIOCRAFT_AVAILABLE:
            raise RuntimeError(
                "audiocraft not installed. Install with: pip install audiocraft"
            )
        
        self.soundfont_id = soundfont_id
        self.model = None
        self.config = get_model_config()
        self.device = self.config["device"]
    
    def load_model(self):
        """Load the base MusicGen model and apply fine-tuned checkpoint for the soundfont."""
        if self.model is not None:
            return  # Already loaded
        
        print(f"[ML] Loading MusicGen model: {self.config['model_name']} on {self.device}")
        print(f"[ML] Target soundfont: {self.soundfont_id.upper()}")
        
        # Load base pretrained model
        self.model = MusicGen.get_pretrained(self.config["model_name"], device=self.device)
        
        # Load fine-tuned checkpoint for this soundfont
        checkpoint_path = get_checkpoint_path(self.soundfont_id)
        if not checkpoint_path or not checkpoint_path.exists():
            raise FileNotFoundError(
                f"Checkpoint not found for {self.soundfont_id.upper()} at {checkpoint_path}. "
                f"Place best_model_{self.soundfont_id}.pt in MLtraining/ or set MUSICGEN_CHECKPOINT_PATH env var."
            )
        
        print(f"[ML] Loading checkpoint from {checkpoint_path}")
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        
        # Apply checkpoint to language model
        # MusicGen structure: model.lm (CompressionModel has .condition_provider, .lm)
        if hasattr(self.model, "lm") and hasattr(self.model.lm, "load_state_dict"):
            self.model.lm.load_state_dict(checkpoint, strict=False)
            print(f"[ML] Checkpoint loaded into language model for {self.soundfont_id.upper()}")
        else:
            print("[ML] WARNING: Could not load checkpoint - model structure unexpected")
        
        self.model.set_generation_params(
            duration=self.config["duration"],
            top_k=self.config["top_k"],
            top_p=self.config["top_p"],
            temperature=self.config["temperature"],
        )
        
        print(f"[ML] Model ready for inference ({self.soundfont_id.upper()})")
    
    def generate_from_audio(
        self,
        audio_prompt_path: Path,
        output_path: Path,
        descriptions: Optional[list[str]] = None,
    ) -> Path:
        """
        Generate audio conditioned on an audio prompt (melody).
        
        Args:
            audio_prompt_path: Path to WAV file to use as melody/prompt
            output_path: Path where generated audio will be saved
            descriptions: Optional text descriptions (list of strings)
        
        Returns:
            Path to generated audio file
        """
        if self.model is None:
            self.load_model()
        
        print(f"[ML] Generating audio conditioned on {audio_prompt_path.name}")
        
        # Load audio prompt
        import torchaudio
        melody, sr = torchaudio.load(str(audio_prompt_path))
        
        # Resample to model's expected sample rate if needed
        model_sr = self.model.sample_rate
        if sr != model_sr:
            resampler = torchaudio.transforms.Resample(sr, model_sr)
            melody = resampler(melody)
        
        # Ensure stereo or mono as expected by model
        if melody.shape[0] > 2:
            melody = melody[:2]  # Take first 2 channels
        
        # Move to device and add batch dimension if needed
        melody = melody.unsqueeze(0).to(self.device)
        
        # Generate with melody conditioning
        if descriptions is None or not descriptions or descriptions[0] == "":
            descriptions = [f"{self.soundfont_id} style video game music"]
        
        print(f"[ML] Description: {descriptions[0]}")
        
        with torch.no_grad():
            generated = self.model.generate_with_chroma(
                descriptions=descriptions,
                melody_wavs=melody,
                melody_sample_rate=model_sr,
                progress=True,
            )
        
        # Save output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # generated shape: (batch, channels, samples)
        # Save first in batch
        audio_tensor = generated[0].cpu()
        torchaudio.save(
            str(output_path),
            audio_tensor,
            sample_rate=model_sr,
        )
        
        print(f"[ML] Generated audio saved to {output_path.name}")
        return output_path


# Global instances per soundfont (lazy-loaded)
_inference_instances: dict[str, MusicGenInference] = {}


def get_inference_engine(soundfont_id: str = "snes") -> MusicGenInference:
    """Get or create a MusicGen inference instance for the specified soundfont."""
    global _inference_instances
    if soundfont_id not in _inference_instances:
        _inference_instances[soundfont_id] = MusicGenInference(soundfont_id)
    return _inference_instances[soundfont_id]
