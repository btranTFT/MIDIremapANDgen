import React from 'react';

export type SoundfontId = 'snes' | 'gba' | 'nds' | 'ps2' | 'wii';
export type RemasterMode = 'baseline' | 'ml';

const SOUNDFONTS: readonly { id: SoundfontId; label: string; note: string }[] = [
  { id: 'snes', label: 'SNES', note: '16‑bit strings' },
  { id: 'gba', label: 'GBA', note: 'Handheld synth' },
  { id: 'nds', label: 'NDS', note: 'Keys & organs' },
  { id: 'ps2', label: 'PS2', note: 'Cinematic mix' },
  { id: 'wii', label: 'Wii', note: 'Orchestral stage' },
];

const ML_UNAVAILABLE_TOOLTIP =
  'ML unavailable: backend does not have AudioCraft or checkpoints. Use Baseline or check API health.';

const MODE_BASELINE_TOOLTIP =
  'Remap MIDI channels to a console soundfont only. Fast, deterministic, no GPU. You get remapped MIDI + rendered audio.';

const MODE_ML_TOOLTIP =
  'Generate audio with MusicGen from your MIDI and optional description. Slower, needs backend model; can sound more expressive.';

const SOUNDFONT_TOOLTIPS: Record<
  SoundfontId,
  string
> = {
  snes: 'SNES-style: 16‑bit strings and classic console tone. Good for retro game feel.',
  gba: 'GBA-style: Handheld synth character. Compact and punchy.',
  nds: 'NDS-style: Keys and organs. Richer pads and textures.',
  ps2: 'PS2-style: Cinematic mix. Broader, more film-like.',
  wii: 'Wii-style: Orchestral stage. Larger, more orchestral sound.',
};

export interface UploadPanelProps {
  file: File | null;
  soundfont: SoundfontId;
  mode: RemasterMode;
  description: string;
  loading: boolean;
  progress: number;
  mlAvailableSoundfonts: string[];
  mlAvailable: boolean;
  maxUploadBytes: number;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onUpload: () => void;
  onModeChange: (mode: RemasterMode) => void;
  onSoundfontChange: (id: SoundfontId) => void;
  onDescriptionChange: (value: string) => void;
}

export function UploadPanel({
  file,
  soundfont,
  mode,
  description,
  loading,
  progress,
  mlAvailableSoundfonts,
  mlAvailable,
  onFileChange,
  onUpload,
  onModeChange,
  onSoundfontChange,
  onDescriptionChange,
  maxUploadBytes,
}: UploadPanelProps) {
  const isMlDisabled = loading || !mlAvailable;
  const fileTooLarge = file != null && file.size > maxUploadBytes;
  const remasterDisabled = !file || loading || fileTooLarge;
  const status =
    loading
      ? 'processing'
      : file && !fileTooLarge
        ? 'ready'
        : 'idle';
  return (
    <section className="panel panel-upload">
      <div className="panel-heading-row">
        <h2>Upload</h2>
        <span
          className={`panel-status panel-status--${status}`}
          aria-live="polite"
        >
          {status === 'processing'
            ? 'Processing…'
            : status === 'ready'
              ? 'Ready'
              : 'Idle'}
        </span>
      </div>
      <p className="hint">Accepts: .mid, .midi</p>

      <div className="upload-group upload-group--mode field">
        <span className="field__label">How to remaster</span>
        <p className="hint hint--mode">
          Baseline = soundfont remap only. ML = AI-generated audio from MIDI.
        </p>
        <div className="mode-toggle">
          <button
            type="button"
            className={'mode-btn' + (mode === 'baseline' ? ' mode-btn-active' : '')}
            onClick={() => onModeChange('baseline')}
            disabled={loading}
            title={MODE_BASELINE_TOOLTIP}
          >
            Baseline (Soundfont)
          </button>
          <button
            type="button"
            className={'mode-btn' + (mode === 'ml' ? ' mode-btn-active' : '')}
            onClick={() => onModeChange('ml')}
            disabled={isMlDisabled}
            title={!mlAvailable ? ML_UNAVAILABLE_TOOLTIP : MODE_ML_TOOLTIP}
          >
            ML (MusicGen)
          </button>
        </div>
      </div>

      <div className="upload-group upload-group--style field">
        <span className="field__label">Console style</span>
        <span className="hint" style={{ marginTop: 0 }}>
          {mode === 'ml'
            ? 'Prompt soundfont (style hint for ML)'
            : 'Soundfont bus (instruments used for remap)'}
        </span>
        <div className="sf-board">
          {SOUNDFONTS.map(sf => {
            const isAvailableForML =
              mode === 'baseline' || mlAvailableSoundfonts.includes(sf.id);
            return (
              <button
                key={sf.id}
                type="button"
                className={
                  'sf-pill' +
                  (soundfont === sf.id ? ' sf-pill-active' : '') +
                  (!isAvailableForML ? ' sf-pill-disabled' : '')
                }
                onClick={() => onSoundfontChange(sf.id)}
                disabled={loading || !isAvailableForML}
                title={
                  !isAvailableForML
                    ? `ML model not available for ${sf.label}`
                    : SOUNDFONT_TOOLTIPS[sf.id]
                }
              >
                <span className="sf-pill-label">{sf.label}</span>
                <span className="sf-pill-note">{sf.note}</span>
              </button>
            );
          })}
        </div>
      </div>

      {mode === 'ml' && (
        <div className="upload-group upload-group--description field">
          <span className="field__label">Description (optional)</span>
          <input
            type="text"
            placeholder="e.g., video game music, upbeat chiptune..."
            value={description}
            onChange={e => onDescriptionChange(e.target.value)}
            disabled={loading}
            className="text-input"
          />
        </div>
      )}

      <div className="upload-group upload-group--file field">
        <span className="field__label">MIDI file</span>
        <div className="file-picker">
          <input
            type="file"
            accept=".mid,.midi"
            onChange={onFileChange}
            disabled={loading}
            className="file-picker__input"
          />
          <span className="file-picker__name" title={file?.name ?? undefined}>
            {file ? file.name : 'No file chosen'}
          </span>
        </div>
      </div>
      {fileTooLarge && (
        <p className="warning">
          File exceeds max size ({Math.round(maxUploadBytes / 1024 / 1024)} MB). Choose a smaller file.
        </p>
      )}
      <div className="upload-group upload-group--action action-block">
        <button
          onClick={onUpload}
          disabled={remasterDisabled}
          className="primary"
        >
          {loading ? 'Processing…' : 'Remaster'}
        </button>
        {!loading && !file && (
          <p className="hint hint--inline">Choose a MIDI file to enable.</p>
        )}
        {!loading && file && !fileTooLarge && (
          <p className="hint hint--inline">Ready to remaster.</p>
        )}
        {loading && (
          <div className="progress">
            <div className="bar">
              <div className="fill" style={{ width: `${progress}%` }} />
            </div>
            <span>{progress}%</span>
          </div>
        )}
      </div>
    </section>
  );
}
