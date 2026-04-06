"""
Fréchet Audio Distance (FAD).

Proposal citation:
    main.tex §Evaluation, Table 2: "FAD — Reference in-style set vs. ML output
        — Style consistency (RQ4)"
    main.tex §Evaluation: "Fréchet Audio Distance (FAD) [kilgour2019] is computed
        between a reference set of open-licensed in-style audio (>=10 pieces per
        evaluated style) and the ML-generated outputs."
    Reference: Kilgour, K. et al. (2019). "Fréchet Audio Distance: A reference-free
        metric for evaluating music enhancement algorithms."
        Proc. Interspeech, pp. 2350–2354.
        DOI: https://doi.org/10.21437/Interspeech.2019-2219
    Proposal cite key: kilgour2019

Method:
    1. Extract fixed-length embeddings from each audio file in both the
       reference set and the generated set using a pretrained audio model.
    2. Fit a multivariate Gaussian (mean, covariance) to each set.
    3. Compute the Fréchet distance (Wasserstein-2) between the two Gaussians:
           FAD = ||mu_r - mu_g||^2 + Tr(Sigma_r + Sigma_g - 2*(Sigma_r @ Sigma_g)^(1/2))

    Lower FAD = generated distribution is closer to the reference distribution.

Embedding backends:
    - "vggish" (default): Google VGGish via torch.hub. Requires torch + torchaudio.
    - Custom: pass any callable(waveform, sample_rate) -> np.ndarray to compute_fad().

Dependencies:
    torch, torchaudio — optional; required only when actually computing FAD.
    numpy, scipy — required (scipy for sqrtm).
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)

# Type alias for an embedding function:
#   (waveform: np.ndarray [mono, float32], sample_rate: int) -> np.ndarray [D,]
EmbedFn = Callable[[np.ndarray, int], np.ndarray]


# ── Fréchet distance ────────────────────────────────────────────────────────


def _frechet_distance(
    mu1: np.ndarray,
    sigma1: np.ndarray,
    mu2: np.ndarray,
    sigma2: np.ndarray,
) -> float:
    """
    Compute the Fréchet distance between two multivariate Gaussians.

    FAD = ||mu1 - mu2||^2 + Tr(sigma1 + sigma2 - 2 * sqrtm(sigma1 @ sigma2))
    """
    from scipy.linalg import sqrtm

    diff = mu1 - mu2
    mean_term = float(np.dot(diff, diff))

    product = sigma1 @ sigma2
    sqrt_product = sqrtm(product)

    # sqrtm may return complex values due to numerical issues; take the real part.
    if np.iscomplexobj(sqrt_product):
        imag_norm = np.linalg.norm(sqrt_product.imag)
        if imag_norm > 1e-3:
            warnings.warn(
                f"Imaginary component {imag_norm:.4f} in sqrtm result — "
                "covariance matrices may be poorly conditioned."
            )
        sqrt_product = sqrt_product.real

    trace_term = float(
        np.trace(sigma1 + sigma2 - 2.0 * sqrt_product)
    )

    return mean_term + trace_term


# ── Embedding extraction ────────────────────────────────────────────────────


def _load_audio_as_mono(path: Path, target_sr: int = 16000) -> tuple[np.ndarray, int]:
    """
    Load an audio file as a mono float32 numpy array, resampled to *target_sr*.

    Requires torchaudio. Returns (waveform, sample_rate).
    """
    import torch
    import soundfile as sf
    from math import gcd
    from scipy.signal import resample_poly

    audio_np, sr = sf.read(str(path), dtype="float32", always_2d=True)
    # soundfile returns [samples, channels]; transpose to [channels, samples]
    waveform = audio_np.T
    # Mix to mono
    if waveform.shape[0] > 1:
        waveform = waveform.mean(axis=0, keepdims=True)
    # Resample if needed
    if sr != target_sr:
        g = gcd(int(sr), int(target_sr))
        waveform = np.stack([
            resample_poly(ch, int(target_sr) // g, int(sr) // g)
            for ch in waveform
        ])
    return waveform.squeeze(0).astype(np.float32), target_sr


def _get_vggish_embed_fn() -> EmbedFn:
    """
    Return a VGGish embedding function via torch.hub.

    The returned function maps (waveform, sample_rate) -> embedding vector.
    VGGish expects 16 kHz mono. We average over the time-frame dimension
    to get a single fixed-length embedding per clip.
    """
    import torch

    model = torch.hub.load("harritaylor/torchvggish", "vggish")
    model.eval()

    def _embed(waveform: np.ndarray, sample_rate: int) -> np.ndarray:
        with torch.no_grad():
            # torchvggish accepts numpy arrays and handles framing internally
            embeddings = model.forward(waveform, sample_rate)
            # embeddings shape: (num_frames, 128) — average over frames
            if isinstance(embeddings, torch.Tensor):
                embeddings = embeddings.cpu().numpy()
            return np.mean(embeddings, axis=0).astype(np.float64)

    return _embed


def _extract_embeddings(
    audio_paths: list[Path],
    embed_fn: EmbedFn,
    target_sr: int = 16000,
) -> np.ndarray:
    """
    Extract embeddings for a list of audio files.

    Returns an (N, D) array where N = number of files and D = embedding dim.
    Skips files that fail to load or embed (with a warning).
    """
    embeddings: list[np.ndarray] = []
    for path in audio_paths:
        try:
            waveform, sr = _load_audio_as_mono(path, target_sr)
            emb = embed_fn(waveform, sr)
            embeddings.append(emb)
        except Exception as exc:
            logger.warning("Skipping %s: %s", path.name, exc)

    if not embeddings:
        raise ValueError("No embeddings could be extracted — all files failed.")

    return np.stack(embeddings, axis=0)


# ── Public API ───────────────────────────────────────────────────────────────


def compute_fad(
    reference_dir: Path | str,
    generated_dir: Path | str,
    embed_fn: EmbedFn | None = None,
    audio_extensions: tuple[str, ...] = (".wav", ".mp3", ".flac", ".ogg"),
    target_sr: int = 16000,
) -> float:
    """
    Compute the Fréchet Audio Distance between two directories of audio files.

    Args:
        reference_dir:    Directory of reference in-style audio files.
        generated_dir:    Directory of ML-generated audio files.
        embed_fn:         Optional custom embedding function. If None, uses VGGish.
        audio_extensions: File extensions to include.
        target_sr:        Target sample rate for audio loading.

    Returns:
        FAD score (float). Lower is better; 0.0 means identical distributions.

    Raises:
        ValueError: If either directory contains no valid audio files.
        ImportError: If torch/torchaudio are not installed.
    """
    reference_dir = Path(reference_dir)
    generated_dir = Path(generated_dir)

    ref_files = sorted(
        p for p in reference_dir.iterdir()
        if p.is_file() and p.suffix.lower() in audio_extensions
    )
    gen_files = sorted(
        p for p in generated_dir.iterdir()
        if p.is_file() and p.suffix.lower() in audio_extensions
    )

    if not ref_files:
        raise ValueError(f"No audio files found in reference directory: {reference_dir}")
    if not gen_files:
        raise ValueError(f"No audio files found in generated directory: {generated_dir}")

    logger.info(
        "Computing FAD: %d reference files, %d generated files",
        len(ref_files), len(gen_files),
    )

    if embed_fn is None:
        embed_fn = _get_vggish_embed_fn()

    ref_embeddings = _extract_embeddings(ref_files, embed_fn, target_sr)
    gen_embeddings = _extract_embeddings(gen_files, embed_fn, target_sr)

    if ref_embeddings.shape[0] < 2 or gen_embeddings.shape[0] < 2:
        raise ValueError(
            f"Need at least 2 successfully embedded files per set to compute "
            f"covariance. Got {ref_embeddings.shape[0]} reference, "
            f"{gen_embeddings.shape[0]} generated."
        )

    # Compute statistics
    mu_ref = np.mean(ref_embeddings, axis=0)
    sigma_ref = np.cov(ref_embeddings, rowvar=False)

    mu_gen = np.mean(gen_embeddings, axis=0)
    sigma_gen = np.cov(gen_embeddings, rowvar=False)

    return _frechet_distance(mu_ref, sigma_ref, mu_gen, sigma_gen)


def compute_fad_from_embeddings(
    ref_embeddings: np.ndarray,
    gen_embeddings: np.ndarray,
) -> float:
    """
    Compute FAD directly from pre-extracted embedding arrays.

    Args:
        ref_embeddings: (N_ref, D) array of reference embeddings.
        gen_embeddings: (N_gen, D) array of generated embeddings.

    Returns:
        FAD score (float). Lower is better.
    """
    if ref_embeddings.ndim != 2 or gen_embeddings.ndim != 2:
        raise ValueError("Embeddings must be 2-D arrays of shape (N, D).")
    if ref_embeddings.shape[1] != gen_embeddings.shape[1]:
        raise ValueError(
            f"Embedding dimensions do not match: "
            f"{ref_embeddings.shape[1]} vs {gen_embeddings.shape[1]}"
        )
    if ref_embeddings.shape[0] < 2 or gen_embeddings.shape[0] < 2:
        raise ValueError("Need at least 2 embeddings per set to compute covariance.")

    mu_ref = np.mean(ref_embeddings, axis=0)
    sigma_ref = np.cov(ref_embeddings, rowvar=False)

    mu_gen = np.mean(gen_embeddings, axis=0)
    sigma_gen = np.cov(gen_embeddings, rowvar=False)

    return _frechet_distance(mu_ref, sigma_ref, mu_gen, sigma_gen)
