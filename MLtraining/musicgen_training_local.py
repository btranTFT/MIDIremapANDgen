#!/usr/bin/env python3
"""
MusicGen Local Training Script - SNES Soundfont
Adapted from Colab notebook for local GPU training
"""

import torch
import torchaudio
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import torch.optim as optim
from torch.optim.lr_scheduler import LambdaLR
from pathlib import Path
import random
import time
import json
from tqdm import tqdm
from datetime import datetime

# ============================================================================
# CONFIGURATION
# ============================================================================

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / 'datasets' / 'snes'
CHECKPOINT_DIR = PROJECT_DIR / 'checkpoints'
LOGS_DIR = PROJECT_DIR / 'logs'

# Create directories
for d in [DATA_DIR, CHECKPOINT_DIR, LOGS_DIR]:
    d.mkdir(exist_ok=True, parents=True)

TRAINING_CONFIG = {
    'soundfont': 'snes',
    'batch_size': 4,  # Reduce to 2 or 1 if out of memory
    'learning_rate': 1e-5,
    'num_epochs': 50,
    'gradient_accumulation_steps': 4,  # Effective batch = batch_size * this
    'warmup_steps': 100,
    'max_grad_norm': 1.0,
    'weight_decay': 0.01,
    'audio_duration': 30.0,  # seconds
    'sample_rate': 32000,
}

print("="*60)
print(f"MUSICGEN TRAINING - {TRAINING_CONFIG['soundfont'].upper()}")
print("="*60)
print(f"\nConfiguration:")
for key, value in TRAINING_CONFIG.items():
    print(f"  {key}: {value}")
print()

# ============================================================================
# CHECK GPU
# ============================================================================

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Device: {device}")

if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
    mem_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    if mem_gb < 12:
        print("\n⚠️  WARNING: Less than 12GB GPU memory.")
        print("   Reduce batch_size to 2 or 1 if you encounter OOM errors.")
else:
    print("\n❌ NO GPU DETECTED!")
    print("   Training on CPU is extremely slow and not recommended.")
    response = input("   Continue anyway? (y/n): ")
    if response.lower() != 'y':
        exit(1)

print()

# ============================================================================
# DATASET CLASS
# ============================================================================

class MusicDataset(Dataset):
    """Dataset for MusicGen fine-tuning"""
    
    def __init__(self, audio_files, sample_rate=32000, duration=30, augment=True):
        self.audio_files = audio_files
        self.sample_rate = sample_rate
        self.duration = duration
        self.samples_per_file = int(duration * sample_rate)
        self.augment = augment
    
    def __len__(self):
        return len(self.audio_files)
    
    def __getitem__(self, idx):
        audio_path = self.audio_files[idx]
        
        try:
            # Load audio
            waveform, sr = torchaudio.load(audio_path)
            
            # Convert to mono
            if waveform.shape[0] > 1:
                waveform = torch.mean(waveform, dim=0, keepdim=True)
            
            # Resample if needed
            if sr != self.sample_rate:
                resampler = torchaudio.transforms.Resample(sr, self.sample_rate)
                waveform = resampler(waveform)
            
            # Handle length
            if waveform.shape[1] > self.samples_per_file:
                # Random crop during training
                start = random.randint(0, waveform.shape[1] - self.samples_per_file)
                waveform = waveform[:, start:start + self.samples_per_file]
            elif waveform.shape[1] < self.samples_per_file:
                # Pad if too short
                padding = self.samples_per_file - waveform.shape[1]
                waveform = F.pad(waveform, (0, padding))
            
            # Simple augmentation (optional)
            if self.augment and random.random() > 0.5:
                # Random volume adjustment
                volume_factor = random.uniform(0.8, 1.2)
                waveform = waveform * volume_factor
            
            return {
                'audio': waveform.squeeze(0),  # Remove channel dimension
                'path': str(audio_path)
            }
        
        except Exception as e:
            print(f"Error loading {audio_path}: {e}")
            # Return silence if file fails to load
            return {
                'audio': torch.zeros(self.samples_per_file),
                'path': str(audio_path)
            }

# ============================================================================
# LOAD DATASET
# ============================================================================

print("Loading dataset...")
print(f"Looking for audio files in: {DATA_DIR}")

# Find all audio files
audio_extensions = ['.wav', '.mp3', '.flac', '.ogg', '.m4a']
all_audio_files = []
for ext in audio_extensions:
    all_audio_files.extend(DATA_DIR.glob(f'**/*{ext}'))

print(f"Found {len(all_audio_files)} audio files")

if len(all_audio_files) < 10:
    print("\n❌ ERROR: Not enough audio files found!")
    print(f"   Please place at least 100 audio files in: {DATA_DIR}")
    print("   Supported formats: WAV, MP3, FLAC, OGG, M4A")
    exit(1)

# Split into train/val
random.shuffle(all_audio_files)
split_idx = int(0.9 * len(all_audio_files))
train_files = all_audio_files[:split_idx]
val_files = all_audio_files[split_idx:]

print(f"Training samples: {len(train_files)}")
print(f"Validation samples: {len(val_files)}")

# Create datasets
train_dataset = MusicDataset(
    train_files, 
    sample_rate=TRAINING_CONFIG['sample_rate'],
    duration=TRAINING_CONFIG['audio_duration'],
    augment=True
)
val_dataset = MusicDataset(
    val_files,
    sample_rate=TRAINING_CONFIG['sample_rate'],
    duration=TRAINING_CONFIG['audio_duration'],
    augment=False
)

# Create dataloaders
train_loader = DataLoader(
    train_dataset,
    batch_size=TRAINING_CONFIG['batch_size'],
    shuffle=True,
    num_workers=2,
    pin_memory=True if torch.cuda.is_available() else False
)

val_loader = DataLoader(
    val_dataset,
    batch_size=TRAINING_CONFIG['batch_size'],
    shuffle=False,
    num_workers=2,
    pin_memory=True if torch.cuda.is_available() else False
)

print(f"Training batches per epoch: {len(train_loader)}")
print(f"Validation batches: {len(val_loader)}")
print()

# ============================================================================
# LOAD MODEL
# ============================================================================

print("Loading MusicGen model...")
print("This may take a few minutes on first run (downloading weights)...")

try:
    from audiocraft.models import MusicGen
except ImportError:
    print("\n❌ ERROR: AudioCraft not installed!")
    print("   Install with: pip install git+https://github.com/facebookresearch/audiocraft.git")
    exit(1)

model = MusicGen.get_pretrained('facebook/musicgen-melody')
lm = model.lm.to(device)
compression_model = model.compression_model.to(device)

print(f"✓ Model loaded on {device}")
print(f"✓ Language model parameters: {sum(p.numel() for p in lm.parameters()) / 1e6:.1f}M")
print()

# ============================================================================
# TRAINING SETUP
# ============================================================================

# Optimizer
optimizer = optim.AdamW(
    lm.parameters(),
    lr=TRAINING_CONFIG['learning_rate'],
    weight_decay=TRAINING_CONFIG['weight_decay']
)

# Learning rate scheduler with warmup
def lr_lambda(step):
    if step < TRAINING_CONFIG['warmup_steps']:
        return step / TRAINING_CONFIG['warmup_steps']
    return 1.0

scheduler = LambdaLR(optimizer, lr_lambda)

print("✓ Optimizer and scheduler configured")
print()

# ============================================================================
# TRAINING FUNCTIONS
# ============================================================================

def train_epoch(lm, compression_model, train_loader, optimizer, scheduler, device, config, epoch):
    """Train for one epoch"""
    lm.train()
    compression_model.eval()  # Keep compression model frozen
    
    total_loss = 0
    optimizer.zero_grad()
    
    pbar = tqdm(train_loader, desc=f"Epoch {epoch+1}")
    for batch_idx, batch in enumerate(pbar):
        try:
            audio = batch['audio'].to(device)
            
            # Encode audio to tokens using compression model
            with torch.no_grad():
                codes, _ = compression_model.encode(audio.unsqueeze(1))  # Add channel dim
            
            # Simple training approach: predict next token
            input_codes = codes[0][:, :-1]  # All but last token
            target_codes = codes[0][:, 1:]   # All but first token
            
            # Forward pass through language model
            logits = lm.forward(input_codes)
            
            # Compute loss
            loss = F.cross_entropy(
                logits.reshape(-1, logits.size(-1)),
                target_codes.reshape(-1),
                ignore_index=-100
            )
            
            # Normalize loss for gradient accumulation
            loss = loss / config['gradient_accumulation_steps']
            loss.backward()
            
            # Gradient accumulation
            if (batch_idx + 1) % config['gradient_accumulation_steps'] == 0:
                # Clip gradients
                torch.nn.utils.clip_grad_norm_(lm.parameters(), config['max_grad_norm'])
                
                # Update weights
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
            
            total_loss += loss.item() * config['gradient_accumulation_steps']
            
            # Update progress bar
            pbar.set_postfix({'loss': f"{loss.item() * config['gradient_accumulation_steps']:.4f}"})
            
        except Exception as e:
            print(f"\nError in batch {batch_idx}: {e}")
            continue
        
        # Clear GPU cache periodically
        if batch_idx % 50 == 0:
            torch.cuda.empty_cache()
    
    return total_loss / len(train_loader)

def validate(lm, compression_model, val_loader, device):
    """Validate the model"""
    lm.eval()
    compression_model.eval()
    
    total_loss = 0
    
    with torch.no_grad():
        for batch in tqdm(val_loader, desc="Validating"):
            try:
                audio = batch['audio'].to(device)
                
                # Encode audio
                codes, _ = compression_model.encode(audio.unsqueeze(1))
                
                # Forward pass
                input_codes = codes[0][:, :-1]
                target_codes = codes[0][:, 1:]
                logits = lm.forward(input_codes)
                
                # Compute loss
                loss = F.cross_entropy(
                    logits.reshape(-1, logits.size(-1)),
                    target_codes.reshape(-1),
                    ignore_index=-100
                )
                
                total_loss += loss.item()
            except Exception as e:
                print(f"\nError in validation batch: {e}")
                continue
    
    return total_loss / len(val_loader) if len(val_loader) > 0 else 0

# ============================================================================
# TRAINING LOOP
# ============================================================================

print("="*60)
print("STARTING TRAINING")
print("="*60)
print(f"Training for {TRAINING_CONFIG['num_epochs']} epochs")
print(f"Checkpoints will be saved to: {CHECKPOINT_DIR}")
print("="*60)
print()

training_history = {
    'train_loss': [],
    'val_loss': [],
    'epochs': []
}

best_val_loss = float('inf')
start_time = time.time()

for epoch in range(TRAINING_CONFIG['num_epochs']):
    print(f"\n{'='*60}")
    print(f"EPOCH {epoch + 1}/{TRAINING_CONFIG['num_epochs']}")
    print(f"{'='*60}")
    
    # Train
    train_loss = train_epoch(
        lm, compression_model, train_loader, optimizer, scheduler,
        device, TRAINING_CONFIG, epoch
    )
    
    # Validate
    val_loss = validate(lm, compression_model, val_loader, device)
    
    # Record history
    training_history['train_loss'].append(train_loss)
    training_history['val_loss'].append(val_loss)
    training_history['epochs'].append(epoch + 1)
    
    # Print stats
    elapsed = time.time() - start_time
    print(f"\nEpoch {epoch + 1} Summary:")
    print(f"  Train Loss: {train_loss:.4f}")
    print(f"  Val Loss: {val_loss:.4f}")
    print(f"  Time: {elapsed/60:.1f} minutes")
    print(f"  LR: {scheduler.get_last_lr()[0]:.2e}")
    
    # Save checkpoint
    checkpoint_path = CHECKPOINT_DIR / f"checkpoint_epoch_{epoch+1}.pt"
    torch.save({
        'epoch': epoch + 1,
        'model_state_dict': lm.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict(),
        'train_loss': train_loss,
        'val_loss': val_loss,
        'config': TRAINING_CONFIG,
    }, checkpoint_path)
    print(f"  ✓ Checkpoint saved: {checkpoint_path.name}")
    
    # Save best model
    if val_loss < best_val_loss:
        best_val_loss = val_loss
        best_model_path = CHECKPOINT_DIR / f"best_model_{TRAINING_CONFIG['soundfont']}.pt"
        torch.save({
            'epoch': epoch + 1,
            'model_state_dict': lm.state_dict(),
            'val_loss': val_loss,
            'config': TRAINING_CONFIG,
        }, best_model_path)
        print(f"  ✓ New best model saved! (val_loss: {val_loss:.4f})")

total_time = time.time() - start_time
print(f"\n{'='*60}")
print("TRAINING COMPLETE!")
print(f"{'='*60}")
print(f"Total time: {total_time/3600:.2f} hours")
print(f"Best validation loss: {best_val_loss:.4f}")
print(f"Best model: {CHECKPOINT_DIR / f'best_model_{TRAINING_CONFIG[\"soundfont\"]}.pt'}")
print()

# Save training history
history_path = LOGS_DIR / f'training_history_{TRAINING_CONFIG["soundfont"]}.json'
with open(history_path, 'w') as f:
    json.dump(training_history, f, indent=2)

print(f"✓ Training history saved to: {history_path}")
print()
print("To use this model:")
print(f"1. Copy {CHECKPOINT_DIR / f'best_model_{TRAINING_CONFIG[\"soundfont\"]}.pt'}")
print(f"2. To: {PROJECT_DIR / f'best_model_{TRAINING_CONFIG[\"soundfont\"]}.pt'}")
print("3. Restart the app - the model will be automatically detected!")
