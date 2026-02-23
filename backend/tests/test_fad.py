"""
Tests for Fréchet Audio Distance (FAD).

Proposal citation:
    main.tex §Evaluation Table 2: "FAD — Reference in-style set vs. ML output
        — Style consistency (RQ4)"
    Reference: Kilgour, K. et al. (2019). Proc. Interspeech, pp. 2350–2354.
    Proposal cite key: kilgour2019

These tests exercise the FAD computation logic WITHOUT requiring torch/torchaudio/VGGish.
They use synthetic embeddings to verify the Fréchet distance math.

Run:
    cd backend
    python -m pytest tests/test_fad.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from src.evaluation.fad import _frechet_distance, compute_fad_from_embeddings


# ── Fréchet distance math tests ─────────────────────────────────────────────


class TestFrechetDistance:
    def test_identical_distributions_give_zero(self):
        """Identical Gaussians must have FAD = 0."""
        rng = np.random.RandomState(42)
        d = 16
        mu = rng.randn(d)
        sigma = np.eye(d) * 0.5

        fad = _frechet_distance(mu, sigma, mu, sigma)
        assert abs(fad) < 1e-6, f"Expected ~0.0, got {fad}"

    def test_shifted_mean_increases_fad(self):
        """Shifting the mean of one distribution should increase FAD."""
        d = 8
        mu1 = np.zeros(d)
        mu2 = np.ones(d) * 3.0
        sigma = np.eye(d)

        fad = _frechet_distance(mu1, sigma, mu2, sigma)
        # Mean term = ||mu1 - mu2||^2 = d * 9 = 72
        # Trace term = 0 (same covariance)
        assert abs(fad - d * 9.0) < 1e-4, f"Expected {d * 9.0}, got {fad}"

    def test_different_covariance_increases_fad(self):
        """Different covariance matrices (same mean) should produce FAD > 0."""
        d = 4
        mu = np.zeros(d)
        sigma1 = np.eye(d)
        sigma2 = np.eye(d) * 4.0

        fad = _frechet_distance(mu, sigma1, mu, sigma2)
        assert fad > 0, f"Expected FAD > 0, got {fad}"

    def test_symmetry(self):
        """FAD should be symmetric: FAD(A, B) = FAD(B, A)."""
        rng = np.random.RandomState(123)
        d = 8
        mu1, mu2 = rng.randn(d), rng.randn(d)
        # Construct valid PSD covariance matrices
        a = rng.randn(d, d)
        sigma1 = a @ a.T + np.eye(d) * 0.1
        b = rng.randn(d, d)
        sigma2 = b @ b.T + np.eye(d) * 0.1

        fad_ab = _frechet_distance(mu1, sigma1, mu2, sigma2)
        fad_ba = _frechet_distance(mu2, sigma2, mu1, sigma1)
        assert abs(fad_ab - fad_ba) < 1e-4, (
            f"FAD not symmetric: {fad_ab:.6f} vs {fad_ba:.6f}"
        )

    def test_non_negative(self):
        """FAD should always be >= 0."""
        rng = np.random.RandomState(99)
        d = 4
        for _ in range(10):
            mu1, mu2 = rng.randn(d), rng.randn(d)
            a = rng.randn(d, d)
            sigma1 = a @ a.T + np.eye(d) * 0.1
            b = rng.randn(d, d)
            sigma2 = b @ b.T + np.eye(d) * 0.1
            fad = _frechet_distance(mu1, sigma1, mu2, sigma2)
            assert fad >= -1e-6, f"FAD should be non-negative, got {fad}"


# ── compute_fad_from_embeddings tests ────────────────────────────────────────


class TestComputeFADFromEmbeddings:
    def test_identical_embeddings_give_zero(self):
        """Identical embedding sets should give FAD ≈ 0."""
        rng = np.random.RandomState(42)
        embeddings = rng.randn(20, 16)

        fad = compute_fad_from_embeddings(embeddings, embeddings.copy())
        assert abs(fad) < 1e-4, f"Expected ~0.0, got {fad}"

    def test_different_distributions_give_positive(self):
        """Embeddings from different distributions should give FAD > 0."""
        rng = np.random.RandomState(42)
        ref = rng.randn(20, 8)
        gen = rng.randn(20, 8) + 5.0  # shifted mean

        fad = compute_fad_from_embeddings(ref, gen)
        assert fad > 1.0, f"Expected large FAD for shifted distribution, got {fad}"

    def test_rejects_1d_input(self):
        with pytest.raises(ValueError, match="2-D"):
            compute_fad_from_embeddings(np.ones(10), np.ones(10))

    def test_rejects_mismatched_dimensions(self):
        with pytest.raises(ValueError, match="dimensions do not match"):
            compute_fad_from_embeddings(np.ones((5, 8)), np.ones((5, 16)))

    def test_rejects_single_embedding(self):
        with pytest.raises(ValueError, match="at least 2"):
            compute_fad_from_embeddings(np.ones((1, 8)), np.ones((5, 8)))

    def test_result_is_scalar(self):
        rng = np.random.RandomState(42)
        ref = rng.randn(10, 8)
        gen = rng.randn(10, 8)
        fad = compute_fad_from_embeddings(ref, gen)
        assert isinstance(fad, float)
