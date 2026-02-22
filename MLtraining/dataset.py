"""
Dataset loader for MIDI training (MusicGen fine-tuning pipeline).

NOTE: This file was originally in backend/src/dataset.py but has been moved to
MLtraining/ where it belongs — it is not used by the API at runtime.

KNOWN ISSUE: This file previously imported `from src.tokenizer import REMITokenizer`,
but no tokenizer.py exists in the project. The REMITokenizer below is a placeholder
skeleton. If you wish to use REMI tokenization, implement the class or swap in a
library (e.g., miditok: https://github.com/Natooz/MidiTok).

The MusicGen fine-tuning path (MLtraining/) does NOT use token sequences —
it uses raw audio prompts (WAV files). This class is infrastructure for a
potential future MIDI-to-MIDI transformer training loop.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import hashlib
import mido
import torch
from torch.utils.data import Dataset, DataLoader


# ── Placeholder tokenizer (swap out for a real implementation) ──────────────

class REMITokenizer:
    """
    Minimal placeholder for a REMI-style MIDI tokenizer.
    Replace with a real implementation (e.g., miditok.REMI) before use.
    """

    def encode(self, midi: mido.MidiFile) -> list[int]:
        """Encode a MIDI file as a flat integer token sequence."""
        tokens: list[int] = []
        for track in midi.tracks:
            for msg in track:
                if msg.type == "note_on" and msg.velocity > 0:
                    tokens.extend([msg.note, msg.velocity, msg.time])
        return tokens


# ── Dataset ──────────────────────────────────────────────────────────────────

class MIDIDataset(Dataset):
    """
    Dataset for MIDI files. Loads and tokenizes on-the-fly.
    """

    def __init__(
        self,
        midi_files: List[Path],
        tokenizer: REMITokenizer,
        max_seq_len: int = 1024,
        context_len: int = 512,
    ):
        self.midi_files = midi_files
        self.tokenizer = tokenizer
        self.max_seq_len = max_seq_len
        self.context_len = context_len

    def __len__(self) -> int:
        return len(self.midi_files)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        midi_path = self.midi_files[idx]
        try:
            midi = mido.MidiFile(midi_path)
            tokens = self.tokenizer.encode(midi)

            if len(tokens) > self.max_seq_len:
                tokens = tokens[: self.max_seq_len]

            split_point = len(tokens) // 2
            source = tokens[:split_point]
            target = tokens[split_point:]

            if len(source) < self.context_len:
                source = source + [0] * (self.context_len - len(source))
            else:
                source = source[: self.context_len]

            target_len = self.max_seq_len - self.context_len
            if len(target) < target_len:
                target = target + [0] * (target_len - len(target))
            else:
                target = target[:target_len]

            return torch.tensor(source, dtype=torch.long), torch.tensor(target, dtype=torch.long)
        except Exception as e:
            print(f"Error loading {midi_path}: {e}")
            return (
                torch.zeros(self.context_len, dtype=torch.long),
                torch.zeros(self.max_seq_len - self.context_len, dtype=torch.long),
            )


def split_dataset(
    data_dir: Path,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
) -> Tuple[List[Path], List[Path], List[Path]]:
    """
    Split dataset into train/val/test using a deterministic hash-based split
    so the split is reproducible across machines without a fixed seed.
    """
    midi_files = list(data_dir.glob("*.mid")) + list(data_dir.glob("*.midi"))

    if not midi_files:
        raise ValueError(f"No MIDI files found in {data_dir}")

    def file_hash(path: Path) -> int:
        return int(hashlib.md5(path.name.encode()).hexdigest(), 16)

    midi_files.sort(key=file_hash)

    total = len(midi_files)
    train_end = int(total * train_ratio)
    val_end = train_end + int(total * val_ratio)

    train_files = midi_files[:train_end]
    val_files = midi_files[train_end:val_end]
    test_files = midi_files[val_end:]

    print(f"Dataset split: Train={len(train_files)}, Val={len(val_files)}, Test={len(test_files)}")
    return train_files, val_files, test_files


def create_dataloaders(
    data_dir: Path,
    tokenizer: REMITokenizer,
    batch_size: int = 8,
    max_seq_len: int = 1024,
    context_len: int = 512,
    num_workers: int = 0,
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """Create train/val/test DataLoaders from a directory of MIDI files."""
    train_files, val_files, test_files = split_dataset(data_dir)

    train_ds = MIDIDataset(train_files, tokenizer, max_seq_len, context_len)
    val_ds = MIDIDataset(val_files, tokenizer, max_seq_len, context_len)
    test_ds = MIDIDataset(test_files, tokenizer, max_seq_len, context_len)

    kwargs = dict(batch_size=batch_size, num_workers=num_workers, pin_memory=True)
    return (
        DataLoader(train_ds, shuffle=True, **kwargs),
        DataLoader(val_ds, shuffle=False, **kwargs),
        DataLoader(test_ds, shuffle=False, **kwargs),
    )
