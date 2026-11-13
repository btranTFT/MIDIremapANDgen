import React from 'react';

export type SoundfontId = 'snes' | 'gba' | 'nds' | 'ps2' | 'wii';
export type RemasterMode = 'baseline' | 'ml';
export type MlPromptMode = 'text' | 'audio';

const SOUNDFONTS: readonly { id: SoundfontId; label: string; note: string }[] = [
  { id: 'snes', label: 'SNES', note: '16‑bit strings' },
  { id: 'gba', label: 'GBA', note: 'Handheld synth' },
  { id: 'nds', label: 'NDS', note: 'Keys & organs' },
  { id: 'ps2', label: 'PS2', note: 'Cinematic mix' },
  { id: 'wii', label: 'Wii', note: 'Orchestral stage' },
];

const ML_UNAVAILABLE_TOOLTIP =
  'ML unavailable: backend does not have AudioCraft. Use Baseline or check API health.';

const MODE_BASELINE_TOOLTIP =
  'Remap MIDI channels to a console soundfont only. Fast, deterministic, no GPU. You get remapped MIDI + rendered audio.';

const MODE_ML_TOOLTIP =
  'Generate 15 or 30 seconds with MusicGen from text, or optionally condition it on a MIDI audio prompt.'

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
  mlPromptMode: MlPromptMode;
  mlDuration: 15 | 30;
  advancedEnabled: boolean;
  advancedReady: boolean;
  description: string;
  loading: boolean;
  primaryActionLabel?: string;
  mlAvailableSoundfonts: string[];
  mlAvailable: boolean;
  mlUnavailableReason: string;
  mlRecommendedAction: string;
  torchError: string | null;
  audiocraftError: string | null;
  maxUploadBytes: number;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onUpload: () => void;
  onModeChange: (mode: RemasterMode) => void;
  onMlPromptModeChange: (mode: MlPromptMode) => void;
  onMlDurationChange: (duration: 15 | 30) => void;
  onSoundfontChange: (id: SoundfontId) => void;
  onDescriptionChange: (value: string) => void;
  onAdvancedToggle: (value: boolean) => void;
}

export function UploadPanel({
  file,
  soundfont,
  mode,
  mlPromptMode,
  mlDuration,
  advancedEnabled,
  advancedReady,
  description,
  loading,
  primaryActionLabel,
  mlAvailableSoundfonts,
  mlAvailable,
  mlUnavailableReason,
  mlRecommendedAction,
  torchError,
  audiocraftError,
  onFileChange,
  onUpload,
  onModeChange,
  onMlPromptModeChange,
  onMlDurationChange,
  onSoundfontChange,
  onDescriptionChange,
  onAdvancedToggle,
  maxUploadBytes,
}: UploadPanelProps) {
  const isMlDisabled = loading;
  const fileTooLarge = file != null && file.size > maxUploadBytes;
  const needsFile = mode === 'baseline' || mlPromptMode === 'audio';
  const needsDescription = mode === 'ml';
  const remasterDisabled =
    (needsFile && !file) ||
    (needsDescription && !description.trim()) ||
    (mode === 'ml' && !mlAvailable) ||
    loading ||
    fileTooLarge;
  const status =
    loading
      ? 'processing'
      : ((needsFile && file && !fileTooLarge) ||
          (!needsFile && description.trim()))
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
      <p className="hint">
        {mode === 'ml' && mlPromptMode === 'text'
          ? 'Text prompt generation; MIDI is optional.'
          : 'Accepts: .mid, .midi'}
      </p>

      <div className="upload-group upload-group--mode field">
        <span className="field__label">How to remaster</span>
        <p className="hint hint--mode">
          Baseline preserves the MIDI with new instruments. MusicGen creates a short audio idea from text or MIDI.
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
            title={!mlAvailable ? mlUnavailableReason : MODE_ML_TOOLTIP}
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
              mode === 'baseline' || !mlAvailable || mlAvailableSoundfonts.includes(sf.id);
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

      {mode === 'baseline' && (
        <div className="upload-group field">
          <span className="field__label">Baseline options</span>
          <label className="advanced-checkbox advanced-checkbox--toggle">
            <input
              type="checkbox"
              checked={advancedEnabled}
              onChange={e => onAdvancedToggle(e.target.checked)}
              disabled={loading}
            />
            <span>Enable advanced pre-remap MIDI editor</span>
          </label>
          <p className="hint hint--inline">
            {advancedEnabled
              ? advancedReady
                ? 'Channel edits are ready. Generate again to apply them.'
                : 'Analyze the MIDI first, then adjust channels before remapping.'
              : 'Use the standard one-click baseline remap.'}
          </p>
        </div>
      )}

      {mode === 'ml' && (
        <div className={`ml-diagnostic${mlAvailable ? ' ml-diagnostic--ready' : ''}`} role="status">
          <strong>{mlAvailable ? 'ML is ready' : 'ML is unavailable'}</strong>
          <p>{mlAvailable ? 'MusicGen can generate audio. Checkpoints are optional.' : mlUnavailableReason}</p>
          {!mlAvailable && torchError && <p><strong>Torch import error:</strong> {torchError}</p>}
          {!mlAvailable && audiocraftError && <p><strong>AudioCraft import error:</strong> {audiocraftError}</p>}
          {!mlAvailable && mlRecommendedAction && <p><strong>Recommended action:</strong> {mlRecommendedAction}</p>}
          {!mlAvailable && (
            <p className="ml-diagnostic__baseline">
              Baseline SoundFont remastering remains available and does not require ML dependencies.
            </p>
          )}
        </div>
      )}

      {mode === 'ml' && (
        <div className="upload-group field">
          <span className="field__label">MusicGen input</span>
          <div className="mode-toggle">
            <button type="button" className={'mode-btn' + (mlPromptMode === 'text' ? ' mode-btn-active' : '')} onClick={() => onMlPromptModeChange('text')} disabled={loading}>
              Text prompt
            </button>
            <button type="button" className={'mode-btn' + (mlPromptMode === 'audio' ? ' mode-btn-active' : '')} onClick={() => onMlPromptModeChange('audio')} disabled={loading}>
              MIDI audio prompt
            </button>
          </div>
          <p className="hint hint--inline">
            {mlPromptMode === 'text'
              ? 'Generate directly from a written description; MIDI is optional.'
              : 'Render the uploaded MIDI first, then use it as MusicGen melody conditioning.'}
          </p>
        </div>
      )}

      {mode === 'ml' && (
        <div className="upload-group upload-group--description field">
          <span className="field__label">Description</span>
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

      {mode === 'ml' && (
        <div className="upload-group field">
          <span className="field__label">Output length</span>
          <select className="text-input" value={mlDuration} onChange={e => onMlDurationChange(Number(e.target.value) as 15 | 30)} disabled={loading}>
            <option value={15}>15 seconds</option>
            <option value={30}>30 seconds</option>
          </select>
        </div>
      )}

      {(mode === 'baseline' || mlPromptMode === 'audio') && (
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
      )}
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
          {loading ? 'Processing…' : primaryActionLabel ?? 'Remaster'}
        </button>
        {!loading && needsFile && !file && (
          <p className="hint hint--inline">Choose a MIDI file to enable.</p>
        )}
        {!loading && !needsFile && !description.trim() && (
          <p className="hint hint--inline">Enter a description to generate.</p>
        )}
        {!loading && needsFile && file && !fileTooLarge && (
          <p className="hint hint--inline">Ready to remaster.</p>
        )}
        {loading && (
          <div className="progress progress--indeterminate" role="status" aria-live="polite">
            <div className="bar"><div className="fill" /></div>
            <span>{mode === 'ml' ? 'Generating…' : 'Rendering…'}</span>
          </div>
        )}
      </div>
    </section>
  );
}
