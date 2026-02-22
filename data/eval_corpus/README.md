# Evaluation Corpus

This directory holds the **held-out** MIDI corpus used for final evaluation only.

## Proposal citation
`report/main.tex §Evaluation Data Plan` (also `report/sections/05-evaluation.tex §Data Plan`):
> "A fixed MIDI corpus of game or game-like music, all open-licensed or permissioned …
> The evaluation set will be held out from the start (no use in hyperparameter choice,
> checkpoint selection, or feature design)."

## Rules
1. **No file in this directory may be used for training or tuning.**  
   MusicGen checkpoints, classifier thresholds, and feature design must be finalized before the corpus is used.
2. Every file must have a clear license (Public Domain, CC0, CC BY, or explicit permission).
3. Record provenance in `corpus_manifest.csv` (one row per file).

## File naming convention
```
<game_title>_<composer_or_source>_<track_name>.mid
example: smw_koichi_sugiyama_overworld.mid
```

## Corpus manifest format (`corpus_manifest.csv`)
```
filename, source_url, license, game_title, year, held_out_since
```

## Where to find open-licensed game MIDI
- **VGMusic.com**: Community-submitted; check individual file licenses.
- **Lakh MIDI Dataset** (clean subset): https://colinraffel.com/projects/lmd/
  Filter for game-music-style tracks; document subset identifiers.
- **NinSheetMusic** community MIDI: Check CC/permission per sheet.
- Custom recordings: If you own the original game, recording from a known source
  may qualify for fair-use evaluation context (document reasoning per §Ethics in proposal).

## Minimum corpus size
The proposal does not specify a fixed N. Target ≥ 10 distinct pieces spanning
at least 2 console eras to provide interpretable per-style results.

## Current status
- [ ] Corpus not yet populated. Add files and update `corpus_manifest.csv`.
