"""Dataset loader for MIDI training."""

import torch
from torch.utils.data import Dataset, DataLoader
from pathlib import Path
from typing import List, Tuple
import hashlib
import mido

from src.tokenizer import REMITokenizer


class MIDIDataset(Dataset):
    """
    Dataset for MIDI files.
    
    Loads and tokenizes MIDI files on-the-fly.
    """
    
    def __init__(
        self,
        midi_files: List[Path],
        tokenizer: REMITokenizer,
        max_seq_len: int = 1024,
        context_len: int = 512
    ):
        """
        Initialize dataset.
        
        Args:
            midi_files: List of MIDI file paths
            tokenizer: REMI tokenizer
            max_seq_len: Maximum sequence length
            context_len: Context length for conditioning
        """
        self.midi_files = midi_files
        self.tokenizer = tokenizer
        self.max_seq_len = max_seq_len
        self.context_len = context_len
    
    def __len__(self) -> int:
        return len(self.midi_files)
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Get tokenized MIDI file.
        
        Returns:
            (source, target) tuple where:
            - source: Input tokens (for conditioning)
            - target: Target tokens (shifted by 1)
        """
        midi_path = self.midi_files[idx]
        
        try:
            # Load and tokenize
            midi = mido.MidiFile(midi_path)
            tokens = self.tokenizer.encode(midi)
            
            # Truncate if too long
            if len(tokens) > self.max_seq_len:
                tokens = tokens[:self.max_seq_len]
            
            # Split into source and target
            # For MIDI-to-MIDI: use first part as source, second part as target
            split_point = len(tokens) // 2
            
            source = tokens[:split_point]
            target = tokens[split_point:]
            
            # Pad if needed
            if len(source) < self.context_len:
                source = source + [0] * (self.context_len - len(source))
            else:
                source = source[:self.context_len]
            
            if len(target) < self.max_seq_len - self.context_len:
                target = target + [0] * (self.max_seq_len - self.context_len - len(target))
            else:
                target = target[:self.max_seq_len - self.context_len]
            
            return torch.tensor(source, dtype=torch.long), torch.tensor(target, dtype=torch.long)
        
        except Exception as e:
            print(f"Error loading {midi_path}: {e}")
            # Return dummy data
            return torch.zeros(self.context_len, dtype=torch.long), torch.zeros(self.max_seq_len - self.context_len, dtype=torch.long)


def split_dataset(
    data_dir: Path,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1
) -> Tuple[List[Path], List[Path], List[Path]]:
    """
    Split dataset into train/val/test using deterministic hash-based split.
    
    Args:
        data_dir: Directory containing MIDI files
        train_ratio: Training set ratio
        val_ratio: Validation set ratio
        test_ratio: Test set ratio
    
    Returns:
        (train_files, val_files, test_files) tuple
    """
    midi_files = list(data_dir.glob("*.mid"))
    
    if not midi_files:
        raise ValueError(f"No MIDI files found in {data_dir}")
    
    # Sort by deterministic hash of filename
    def file_hash(path: Path) -> int:
        return int(hashlib.md5(path.name.encode()).hexdigest(), 16)
    
    midi_files.sort(key=file_hash)
    
    # Split
    total = len(midi_files)
    train_end = int(total * train_ratio)
    val_end = train_end + int(total * val_ratio)
    
    train_files = midi_files[:train_end]
    val_files = midi_files[train_end:val_end]
    test_files = midi_files[val_end:]
    
    print(f"Dataset split:")
    print(f"  Train: {len(train_files)} files")
    print(f"  Val: {len(val_files)} files")
    print(f"  Test: {len(test_files)} files")
    
    return train_files, val_files, test_files


def create_dataloaders(
    data_dir: Path,
    tokenizer: REMITokenizer,
    batch_size: int = 8,
    max_seq_len: int = 1024,
    context_len: int = 512,
    num_workers: int = 0
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """
    Create train/val/test dataloaders.
    
    Args:
        data_dir: Directory with augmented MIDI files
        tokenizer: REMI tokenizer
        batch_size: Batch size
        max_seq_len: Maximum sequence length
        context_len: Context length
        num_workers: Number of dataloader workers
    
    Returns:
        (train_loader, val_loader, test_loader) tuple
    """
    train_files, val_files, test_files = split_dataset(data_dir)
    
    train_dataset = MIDIDataset(train_files, tokenizer, max_seq_len, context_len)
    val_dataset = MIDIDataset(val_files, tokenizer, max_seq_len, context_len)
    test_dataset = MIDIDataset(test_files, tokenizer, max_seq_len, context_len)
    
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=True
    )
    
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )
    
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )
    
    return train_loader, val_loader, test_loader

