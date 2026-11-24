"""ML inference module for MusicGen-based audio generation."""

import os
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

try:
    import torch
except (ImportError, OSError) as exc:
    torch = None
    _TORCH_IMPORT_EXCEPTION = exc
    _TORCH_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    _TORCH_IMPORT_EXCEPTION = None
    _TORCH_IMPORT_ERROR = None

# Defer imports to allow startup without ML dependencies
_AUDIOCRAFT_AVAILABLE = False
try:
    from audiocraft.models import MusicGen
    _AUDIOCRAFT_AVAILABLE = True
except (ImportError, OSError) as exc:
    MusicGen = None
    _AUDIOCRAFT_IMPORT_EXCEPTION = exc
    _AUDIOCRAFT_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    _AUDIOCRAFT_IMPORT_EXCEPTION = None
    _AUDIOCRAFT_IMPORT_ERROR = None


def _is_windows_policy_block(error: str | None) -> bool:
    return bool(error and "winerror 4551" in error.lower())


def _dependency_diagnostic(name: str, error: str | None) -> tuple[str, str]:
    """Return a precise user-facing explanation and next action for an import error."""
    if _is_windows_policy_block(error):
        return (
            f"{name} could not be loaded because a Windows Application Control policy "
            f"blocked one of its DLLs ({error}). This is not a missing dependency and "
            "reinstalling the package will not bypass the policy.",
            "Ask your administrator to review the Windows Application Control policy "
            f"for {name}. Do not disable or weaken Windows security controls. "
            "As an optional workaround, a CPU-only PyTorch environment may avoid "
            "the blocked CUDA DLL, but MusicGen will be substantially slower.",
        )
    return (
        f"{name} is unavailable ({error or 'unknown import error'}).",
        f"Install the ML dependencies with `python -m pip install -r "
        "backend/requirements-ml.txt` and install AudioCraft from its documented source.",
    )


def check_ml_dependencies(soundfont_id: Optional[str] = None) -> dict:
    """Check if ML dependencies are installed and model checkpoint exists."""
    result = {
        "torch": torch.__version__ if torch is not None else "unavailable",
        "audiocraft": _AUDIOCRAFT_AVAILABLE,
        "torch_error": _TORCH_IMPORT_ERROR,
        "audiocraft_error": _AUDIOCRAFT_IMPORT_ERROR,
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


def get_ml_diagnostics(soundfont_id: str = "snes") -> dict:
    """Return user-facing ML capability diagnostics without loading a model."""
    checkpoint_path = get_checkpoint_path(soundfont_id)
    checkpoint_available = bool(checkpoint_path and checkpoint_path.exists())
    reasons: list[str] = []
    recommended_actions: list[str] = []
    if torch is None:
        torch_reason, torch_action = _dependency_diagnostic("Torch", _TORCH_IMPORT_ERROR)
        reasons.append(torch_reason)
        recommended_actions.append(torch_action)
    if not _AUDIOCRAFT_AVAILABLE:
        audiocraft_reason, audiocraft_action = _dependency_diagnostic(
            "AudioCraft", _AUDIOCRAFT_IMPORT_ERROR
        )
        reasons.append(audiocraft_reason)
        recommended_actions.append(audiocraft_action)
    if torch is not None and _AUDIOCRAFT_AVAILABLE:
        reason = "ML dependencies are available; checkpoints are optional because the base model can run."
        recommended_action = "No action required."
    elif reasons:
        reason = " ".join(reasons)
        recommended_action = " ".join(dict.fromkeys(recommended_actions))
    else:
        reason = "ML is unavailable for an unknown reason."
        recommended_action = "Review the backend logs for the ML import failure."
    return {
        "torch_available": torch is not None,
        "torch_error": _TORCH_IMPORT_ERROR,
        "audiocraft_available": _AUDIOCRAFT_AVAILABLE,
        "audiocraft_error": _AUDIOCRAFT_IMPORT_ERROR,
        "checkpoint_available": checkpoint_available,
        "checkpoint_path": str(checkpoint_path) if checkpoint_path else None,
        "ml_available": torch is not None and _AUDIOCRAFT_AVAILABLE,
        "ml_reason": reason,
        "recommended_action": recommended_action,
        # Kept for older frontend clients.
        "reason": reason,
    }


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


def get_model_config(conditioning_type: str = "text") -> dict:
    """Get ML model configuration."""
    legacy_model_name = os.getenv("MUSICGEN_MODEL_NAME")
    default_model_name = (
        os.getenv("MUSICGEN_MELODY_MODEL_NAME", "facebook/musicgen-melody")
        if conditioning_type == "audio"
        else os.getenv("MUSICGEN_TEXT_MODEL_NAME", "facebook/musicgen-small")
    )
    return {
        "model_name": legacy_model_name or default_model_name,
        "duration": float(os.getenv("MUSICGEN_DURATION", "15.0")),
        "device": os.getenv(
            "MUSICGEN_DEVICE",
            "cuda" if torch is not None and torch.cuda.is_available() else "cpu",
        ),
        "top_k": int(os.getenv("MUSICGEN_TOP_K", "250")),
        "top_p": float(os.getenv("MUSICGEN_TOP_P", "0.0")),
        "temperature": float(os.getenv("MUSICGEN_TEMPERATURE", "1.0")),
    }


def get_device_diagnostics(device: str) -> dict:
    diagnostics = {
        "selected_device": str(device),
        "cuda_available": False,
        "gpu_name": None,
        "allocated_memory_bytes": None,
    }
    try:
        diagnostics["cuda_available"] = bool(torch is not None and torch.cuda.is_available())
        if diagnostics["cuda_available"]:
            cuda_device = device if str(device).startswith("cuda") else None
            diagnostics["gpu_name"] = torch.cuda.get_device_name(cuda_device)
            if cuda_device is not None:
                diagnostics["allocated_memory_bytes"] = int(torch.cuda.memory_allocated(cuda_device))
    except Exception:
        pass
    return diagnostics


def release_cuda_cache(device: str) -> None:
    try:
        if str(device).startswith("cuda") and torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


class MusicGenInference:
    """Wrapper for MusicGen model loading and inference."""
    
    def __init__(self, soundfont_id: str = "snes", conditioning_type: str = "text"):
        if torch is None or not _AUDIOCRAFT_AVAILABLE:
            raise RuntimeError(
                "audiocraft not installed. Install with: pip install audiocraft"
            )
        
        self.soundfont_id = soundfont_id
        self.conditioning_type = conditioning_type
        self.model = None
        self.checkpoint_loaded = False
        self.config = get_model_config(conditioning_type)
        self.model_name = self.config["model_name"]
        self.device = self.config["device"]
    
    def load_model(self):
        """Load the base MusicGen model and apply fine-tuned checkpoint for the soundfont."""
        if self.model is not None:
            return  # Already loaded
        
        if torch.cuda.is_available():
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

        print(f"[ML] Loading MusicGen model: {self.model_name} on {self.device}")
        print(f"[ML] Target soundfont: {self.soundfont_id.upper()}")
        
        # Load base pretrained model
        model = MusicGen.get_pretrained(self.model_name, device=self.device)
        checkpoint_loaded = False
        
        # Fine-tuned checkpoints are optional; base MusicGen supports text-only use.
        checkpoint_path = get_checkpoint_path(self.soundfont_id)
        if checkpoint_path and checkpoint_path.exists():
            print(f"[ML] Loading checkpoint from {checkpoint_path}")
            raw = torch.load(checkpoint_path, map_location=self.device)
            if isinstance(raw, dict) and "model_state_dict" in raw:
                state_dict = raw["model_state_dict"]
                epoch_info = f" (epoch {raw.get('epoch', '?')}, val_loss {raw.get('val_loss', '?'):.4f})" \
                    if "val_loss" in raw else f" (epoch {raw.get('epoch', '?')})"
                print(f"[ML] Checkpoint format: training wrapper{epoch_info}")
            else:
                state_dict = raw
                print("[ML] Checkpoint format: raw state dict")

            if hasattr(model, "lm") and hasattr(model.lm, "load_state_dict"):
                result = model.lm.load_state_dict(state_dict, strict=False)
                if result.missing_keys:
                    print(f"[ML] WARNING: {len(result.missing_keys)} missing keys in checkpoint "
                          f"(first 5: {result.missing_keys[:5]})")
                if result.unexpected_keys:
                    print(f"[ML] WARNING: {len(result.unexpected_keys)} unexpected keys in checkpoint "
                          f"(first 5: {result.unexpected_keys[:5]})")
                loaded = len(state_dict) - len(result.missing_keys)
                checkpoint_loaded = True
                print(f"[ML] Checkpoint loaded: {loaded}/{len(state_dict)} keys matched "
                      f"for {self.soundfont_id.upper()} language model")
        else:
            print(f"[ML] No checkpoint for {self.soundfont_id.upper()}; using base MusicGen")
        
        model.set_generation_params(
            duration=self.config["duration"],
            top_k=self.config["top_k"],
            top_p=self.config["top_p"],
            temperature=self.config["temperature"],
        )
        self.model = model
        self.checkpoint_loaded = checkpoint_loaded
        
        print(f"[ML] Model ready for inference ({self.soundfont_id.upper()})")
    
    def generate_from_audio(
        self,
        audio_prompt_path: Path,
        output_path: Path,
        descriptions: Optional[list[str]] = None,
        generation_duration_s: Optional[float] = None,
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
        
        # Load audio prompt via soundfile (avoids torchcodec/FFmpeg requirement)
        from math import gcd
        from scipy.signal import resample_poly

        audio_np, sr = sf.read(str(audio_prompt_path), dtype="float32", always_2d=True)
        # soundfile returns [samples, channels] -- transpose to [channels, samples]
        melody = torch.from_numpy(audio_np.T)

        # Resample to model's expected sample rate if needed
        model_sr = self.model.sample_rate
        if sr != model_sr:
            g = gcd(int(sr), int(model_sr))
            melody_np = melody.numpy()
            melody_np = np.stack([
                resample_poly(ch, int(model_sr) // g, int(sr) // g)
                for ch in melody_np
            ])
            melody = torch.from_numpy(melody_np.astype(np.float32))
        
        # Ensure stereo or mono as expected by model
        if melody.shape[0] > 2:
            melody = melody[:2]  # Take first 2 channels
        
        # Move to device and add batch dimension if needed
        melody = melody.unsqueeze(0).to(self.device)
        
        # Generate with melody conditioning
        if descriptions is None or not descriptions or descriptions[0] == "":
            descriptions = [f"{self.soundfont_id} style video game music"]
        
        duration_s = float(generation_duration_s) if generation_duration_s and generation_duration_s > 0 else float(self.config["duration"])
        self.model.set_generation_params(
            duration=duration_s,
            top_k=self.config["top_k"],
            top_p=self.config["top_p"],
            temperature=self.config["temperature"],
        )

        print(f"[ML] Description: {descriptions[0]}")
        print(f"[ML] Target duration: {duration_s:.2f}s")
        
        with torch.inference_mode():
            generated = self.model.generate_with_chroma(
                descriptions=descriptions,
                melody_wavs=melody,
                melody_sample_rate=model_sr,
                progress=True,
            )
        
        # Save output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # generated shape: (batch, channels, samples)
        # Save first in batch using soundfile (avoids torchcodec dependency)
        audio_tensor = generated[0].cpu()
        target_samples = int(round(duration_s * model_sr))
        current_samples = int(audio_tensor.shape[-1])
        if target_samples > 0 and current_samples != target_samples:
            if current_samples > target_samples:
                audio_tensor = audio_tensor[..., :target_samples]
            else:
                pad = target_samples - current_samples
                audio_tensor = torch.nn.functional.pad(audio_tensor, (0, pad))

        # soundfile expects [samples, channels]
        audio_out = audio_tensor.numpy().T
        sf.write(str(output_path), audio_out, model_sr)
        
        print(f"[ML] Generated audio saved to {output_path.name}")
        return output_path

    def generate_from_text(
        self,
        output_path: Path,
        descriptions: list[str],
        generation_duration_s: float,
    ) -> Path:
        """Generate audio from text descriptions without an audio prompt."""
        if self.model is None:
            self.load_model()

        duration_s = float(generation_duration_s)
        self.model.set_generation_params(
            duration=duration_s,
            top_k=self.config["top_k"],
            top_p=self.config["top_p"],
            temperature=self.config["temperature"],
        )
        print(f"[ML] Text description: {descriptions[0]}")
        print(f"[ML] Target duration: {duration_s:.2f}s")
        with torch.inference_mode():
            generated = self.model.generate(
                descriptions=descriptions,
                progress=True,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        audio_tensor = generated[0].cpu()
        target_samples = int(round(duration_s * self.model.sample_rate))
        current_samples = int(audio_tensor.shape[-1])
        if current_samples != target_samples:
            if current_samples > target_samples:
                audio_tensor = audio_tensor[..., :target_samples]
            else:
                audio_tensor = torch.nn.functional.pad(
                    audio_tensor, (0, target_samples - current_samples)
                )
        sf.write(str(output_path), audio_tensor.numpy().T, self.model.sample_rate)
        print(f"[ML] Generated audio saved to {output_path.name}")
        return output_path


# Global instances keyed by model and conditioning type. Instances with
# soundfont-specific checkpoints also include the soundfont ID so fine-tuned
# styles cannot be reused across requests. Instances without checkpoints remain
# shared as base models across soundfonts.
_inference_instances: dict[tuple[str, ...], MusicGenInference] = {}


def get_inference_engine(
    soundfont_id: str = "snes",
    conditioning_type: str = "text",
) -> MusicGenInference:
    """Get or create an inference instance for the model/conditioning pair."""
    global _inference_instances
    model_name = get_model_config(conditioning_type)["model_name"]

    checkpoint_path = get_checkpoint_path(soundfont_id)
    has_soundfont_checkpoint = bool(checkpoint_path and checkpoint_path.exists())

    if has_soundfont_checkpoint:
        key = (model_name, conditioning_type, soundfont_id)
    else:
        key = (model_name, conditioning_type)

    if key not in _inference_instances:
        _inference_instances[key] = MusicGenInference(soundfont_id, conditioning_type)

    engine = _inference_instances[key]
    # A base-model engine may be shared across soundfonts. Keep the engine
    # metadata aligned with every request, including requests after cache reuse.
    engine.soundfont_id = soundfont_id
    return engine
