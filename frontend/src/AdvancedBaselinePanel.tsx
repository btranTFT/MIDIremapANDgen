import React from 'react';

import type { SoundfontId } from './UploadPanel';

export interface ChannelOverride {
  program: number | null;
  transpose: number;
  velocity_scale: number;
  volume: number | null;
  pan: number | null;
  mute: boolean;
  solo: boolean;
  preserve_program_changes: boolean;
}

export interface AdvancedChannelAnalysis {
  channel: number;
  is_drum: boolean;
  original_program: number | null;
  original_program_name: string | null;
  mapped_program: number;
  mapped_program_name: string;
  note_count: number;
  pitch_min: number | null;
  pitch_max: number | null;
  avg_velocity: number | null;
  defaults: ChannelOverride;
}

export interface ProgramOption {
  program: number;
  name: string;
}

export interface AdvancedAnalysisResult {
  request_id: string;
  input_filename: string;
  soundfont: SoundfontId;
  source_style?: SoundfontId | null;
  preserve_compatible_programs?: boolean;
  channels: AdvancedChannelAnalysis[];
  available_programs: ProgramOption[];
}

interface AdvancedBaselinePanelProps {
  analysis: AdvancedAnalysisResult | null;
  sourceStyle: SoundfontId | '';
  onSourceStyleChange: (value: SoundfontId | '') => void;
  overrides: Record<string, ChannelOverride>;
  onOverrideChange: (channel: number, patch: Partial<ChannelOverride>) => void;
  onResetChannel: (channel: number) => void;
  onResetAll: () => void;
}

const SOURCE_STYLE_OPTIONS: Array<{ value: SoundfontId | ''; label: string }> = [
  { value: '', label: 'Unknown / auto' },
  { value: 'snes', label: 'SNES' },
  { value: 'gba', label: 'GBA' },
  { value: 'nds', label: 'NDS' },
  { value: 'ps2', label: 'PS2' },
  { value: 'wii', label: 'Wii' },
];

function getProgramLabel(
  analysis: AdvancedAnalysisResult,
  program: number | null | undefined,
  fallback: string,
): string {
  if (program == null) return fallback;
  const match = analysis.available_programs.find(option => option.program === program);
  return match ? `${match.program} · ${match.name}` : `${program}`;
}

export function getChannelDefaultOverride(channel: AdvancedChannelAnalysis): ChannelOverride {
  return {
    ...channel.defaults,
    program: channel.defaults.preserve_program_changes ? null : channel.defaults.program,
  };
}

function isDefaultOverride(channel: AdvancedChannelAnalysis, override: ChannelOverride): boolean {
  return JSON.stringify(getChannelDefaultOverride(channel)) === JSON.stringify(override);
}

export function AdvancedBaselinePanel({
  analysis,
  sourceStyle,
  onSourceStyleChange,
  overrides,
  onOverrideChange,
  onResetChannel,
  onResetAll,
}: AdvancedBaselinePanelProps) {
  const [activeView, setActiveView] = React.useState<'overview' | 'editor'>('editor');
  const [selectedChannel, setSelectedChannel] = React.useState<number | null>(null);

  React.useEffect(() => {
    if (!analysis) {
      setSelectedChannel(null);
      return;
    }
    setSelectedChannel(current => {
      if (current != null && analysis.channels.some(channel => channel.channel === current)) {
        return current;
      }
      return analysis.channels[0]?.channel ?? null;
    });
  }, [analysis]);

  if (!analysis) return null;

  const channels = analysis.channels.map(channel => {
    const defaultOverride = getChannelDefaultOverride(channel);
    const override = overrides[String(channel.channel)] ?? defaultOverride;
    const useSourceProgram =
      sourceStyle !== '' && sourceStyle === analysis.soundfont && channel.original_program != null;
    const effectiveProgramLabel = override.mute
      ? 'Muted'
      : override.program != null && !override.preserve_program_changes
        ? `Forced: ${getProgramLabel(analysis, override.program, 'Forced program')}`
        : useSourceProgram && channel.original_program_name
          ? `Source-preserved: ${channel.original_program_name}`
          : `Auto remap: ${channel.mapped_program_name}`;
    const hasCustomEdit = !isDefaultOverride(channel, override);

    return {
      channel,
      defaultOverride,
      override,
      useSourceProgram,
      effectiveProgramLabel,
      hasCustomEdit,
    };
  });

  const modifiedCount = channels.filter(item => item.hasCustomEdit).length;
  const soloCount = channels.filter(item => item.override.solo).length;
  const mutedCount = channels.filter(item => item.override.mute).length;
  const selected = channels.find(item => item.channel.channel === selectedChannel) ?? channels[0] ?? null;

  return (
    <section className="panel advanced-panel">
      <div className="panel-heading-row">
        <h2>Advanced baseline editor</h2>
        <span className="panel-status panel-status--ready">Analyzed</span>
      </div>
      <p className="hint">
        Edit channel-level MIDI behavior before baseline remapping, then run remaster again.
      </p>

      <div className="advanced-shell">
        <div className="advanced-shell__header">
          <div className="advanced-view-tabs" role="tablist" aria-label="Advanced editor views">
            <button
              type="button"
              className={`advanced-view-tab ${activeView === 'editor' ? 'advanced-view-tab--active' : ''}`}
              onClick={() => setActiveView('editor')}
              role="tab"
              aria-selected={activeView === 'editor'}
            >
              Channel editor
            </button>
            <button
              type="button"
              className={`advanced-view-tab ${activeView === 'overview' ? 'advanced-view-tab--active' : ''}`}
              onClick={() => setActiveView('overview')}
              role="tab"
              aria-selected={activeView === 'overview'}
            >
              Overview
            </button>
          </div>

          <div className="advanced-toolbar">
            <div className="field advanced-toolbar__field">
              <label className="field__label" htmlFor="source-style-select">
                Source platform
              </label>
              <select
                id="source-style-select"
                className="advanced-select"
                value={sourceStyle}
                onChange={e => onSourceStyleChange(e.target.value as SoundfontId | '')}
              >
                {SOURCE_STYLE_OPTIONS.map(option => (
                  <option key={option.label} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="hint hint--inline">
                Set this when the uploaded MIDI already targets the same platform as the original OST.
              </p>
            </div>
            <button type="button" className="secondary" onClick={onResetAll}>
              Reset all edits
            </button>
          </div>
        </div>

        {activeView === 'overview' ? (
          <div className="advanced-overview">
            <div className="advanced-summary">
              <div className="advanced-summary__item">
                <strong>{analysis.channels.length}</strong>
                <span>channels analyzed</span>
              </div>
              <div className="advanced-summary__item">
                <strong>{modifiedCount}</strong>
                <span>channels edited</span>
              </div>
              <div className="advanced-summary__item">
                <strong>{mutedCount}</strong>
                <span>muted</span>
              </div>
              <div className="advanced-summary__item">
                <strong>{soloCount}</strong>
                <span>solo</span>
              </div>
            </div>

            <div className="advanced-overview-grid">
              <section className="advanced-overview-card">
                <h3>Session summary</h3>
                <p className="hint">
                  Use the channel editor to focus on one part at a time, then regenerate the
                  remap when your edits look right.
                </p>
                <div className="advanced-overview-list">
                  {channels.map(item => (
                    <button
                      key={item.channel.channel}
                      type="button"
                      className="advanced-overview-row"
                      onClick={() => {
                        setSelectedChannel(item.channel.channel);
                        setActiveView('editor');
                      }}
                    >
                      <span className="advanced-overview-row__title">
                        Channel {item.channel.channel}
                        {item.hasCustomEdit && <span className="advanced-badge">Edited</span>}
                      </span>
                      <span className="advanced-overview-row__meta">{item.effectiveProgramLabel}</span>
                    </button>
                  ))}
                </div>
              </section>

              <section className="advanced-overview-card">
                <h3>What changes affect output</h3>
                <ul className="advanced-bullet-list">
                  <li>Program override changes the patch used before remapping.</li>
                  <li>Transpose moves note pitches before the soundfont remap runs.</li>
                  <li>Velocity scale, volume, and pan alter the rendered MIDI dynamics.</li>
                  <li>Mute and solo directly remove or isolate channels in the exported MIDI.</li>
                </ul>
              </section>
            </div>
          </div>
        ) : (
          <div className="advanced-editor-layout">
            <aside className="advanced-channel-list" aria-label="MIDI channels">
              <div className="advanced-channel-list__header">
                <h3>Channels</h3>
                <span className="hint">Select one to edit</span>
              </div>
              <div className="advanced-channel-list__items">
                {channels.map(item => (
                  <button
                    key={item.channel.channel}
                    type="button"
                    className={`advanced-channel-list__item ${selected?.channel.channel === item.channel.channel ? 'advanced-channel-list__item--active' : ''}`}
                    onClick={() => setSelectedChannel(item.channel.channel)}
                  >
                    <div className="advanced-channel-list__item-top">
                      <strong>Channel {item.channel.channel}</strong>
                      {item.hasCustomEdit && <span className="advanced-badge">Edited</span>}
                    </div>
                    <span className="advanced-channel-list__item-meta">
                      {item.channel.is_drum
                        ? 'Drum lane'
                        : `${item.channel.note_count} notes · ${item.channel.original_program_name ?? 'Unknown'}`}
                    </span>
                    <span className="advanced-channel-list__item-preview">
                      {item.effectiveProgramLabel}
                    </span>
                  </button>
                ))}
              </div>
            </aside>

            <div className="advanced-detail">
              {selected ? (
                <>
                  <div className="advanced-detail__header">
                    <div>
                      <h3>Channel {selected.channel.channel}</h3>
                      <p className="hint">
                        {selected.channel.is_drum
                          ? 'Drum channel'
                          : `${selected.channel.note_count} notes`} · Original:{' '}
                        {selected.channel.original_program_name ?? 'Unknown'} · Detected:{' '}
                        {selected.channel.mapped_program_name}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="secondary advanced-channel-card__reset"
                      onClick={() => onResetChannel(selected.channel.channel)}
                    >
                      Reset channel
                    </button>
                  </div>

                  <div className="advanced-detail__hero">
                    <div>
                      <span className="advanced-detail__eyebrow">Effective mapping</span>
                      <p className="advanced-channel-card__preview">
                        <strong>{selected.effectiveProgramLabel}</strong>
                      </p>
                    </div>
                    <div className="advanced-detail__stats">
                      <span>Range: {selected.channel.pitch_min ?? '—'} to {selected.channel.pitch_max ?? '—'}</span>
                      <span>Avg velocity: {selected.channel.avg_velocity ?? '—'}</span>
                    </div>
                  </div>

                  <div className="advanced-detail-grid">
                    <section className="advanced-detail-card">
                      <h4>Pitch & mapping</h4>
                      <div className="advanced-channel-grid">
                        <label className="field">
                          <span className="field__label">Program override</span>
                          <select
                            className="advanced-select"
                            value={selected.override.program ?? ''}
                            onChange={e =>
                              onOverrideChange(selected.channel.channel, {
                                program: e.target.value === '' ? null : Number(e.target.value),
                                preserve_program_changes:
                                  e.target.value === ''
                                    ? selected.override.preserve_program_changes
                                    : false,
                              })
                            }
                            disabled={selected.channel.is_drum}
                          >
                            <option value="">Keep detected / source</option>
                            {analysis.available_programs.map(option => (
                              <option key={option.program} value={option.program}>
                                {option.program} · {option.name}
                              </option>
                            ))}
                          </select>
                        </label>

                        <label className="field">
                          <span className="field__label">Transpose (semitones)</span>
                          <input
                            className="text-input"
                            type="number"
                            min={-24}
                            max={24}
                            step={1}
                            value={selected.override.transpose}
                            onChange={e =>
                              onOverrideChange(selected.channel.channel, {
                                transpose: Number(e.target.value || 0),
                              })
                            }
                            disabled={selected.channel.is_drum}
                          />
                        </label>

                        <label className="field">
                          <span className="field__label">Preserve later program changes</span>
                          <select
                            className="advanced-select"
                            value={selected.override.preserve_program_changes ? 'yes' : 'no'}
                            onChange={e =>
                              onOverrideChange(selected.channel.channel, {
                                preserve_program_changes: e.target.value === 'yes',
                              })
                            }
                            disabled={selected.channel.is_drum}
                          >
                            <option value="yes">Yes</option>
                            <option value="no">No</option>
                          </select>
                        </label>
                      </div>
                    </section>

                    <section className="advanced-detail-card">
                      <h4>Dynamics & mix</h4>
                      <div className="advanced-channel-grid">
                        <label className="field">
                          <span className="field__label">Velocity scale</span>
                          <input
                            className="text-input"
                            type="number"
                            min={0}
                            max={2}
                            step={0.05}
                            value={selected.override.velocity_scale}
                            onChange={e =>
                              onOverrideChange(selected.channel.channel, {
                                velocity_scale: Number(e.target.value || 1),
                              })
                            }
                            disabled={selected.channel.is_drum}
                          />
                        </label>

                        <label className="field">
                          <span className="field__label">Volume (0-127)</span>
                          <input
                            className="text-input"
                            type="number"
                            min={0}
                            max={127}
                            step={1}
                            value={selected.override.volume ?? ''}
                            onChange={e =>
                              onOverrideChange(selected.channel.channel, {
                                volume: e.target.value === '' ? null : Number(e.target.value),
                              })
                            }
                          />
                        </label>

                        <label className="field">
                          <span className="field__label">Pan (0=L, 64=C, 127=R)</span>
                          <input
                            className="text-input"
                            type="number"
                            min={0}
                            max={127}
                            step={1}
                            value={selected.override.pan ?? ''}
                            onChange={e =>
                              onOverrideChange(selected.channel.channel, {
                                pan: e.target.value === '' ? null : Number(e.target.value),
                              })
                            }
                          />
                        </label>
                      </div>
                    </section>
                  </div>

                  {!selected.channel.is_drum && (
                    <div className="advanced-quick-actions">
                      <button
                        type="button"
                        className="secondary advanced-quick-actions__btn"
                        onClick={() =>
                          onOverrideChange(selected.channel.channel, {
                            program: selected.channel.original_program,
                            preserve_program_changes: false,
                          })
                        }
                        disabled={selected.channel.original_program == null}
                      >
                        Use original patch
                      </button>
                      <button
                        type="button"
                        className="secondary advanced-quick-actions__btn"
                        onClick={() =>
                          onOverrideChange(selected.channel.channel, {
                            program: selected.channel.mapped_program,
                            preserve_program_changes: false,
                          })
                        }
                      >
                        Force detected patch
                      </button>
                      <button
                        type="button"
                        className="secondary advanced-quick-actions__btn"
                        onClick={() =>
                          onOverrideChange(selected.channel.channel, {
                            program: null,
                            preserve_program_changes: true,
                          })
                        }
                      >
                        Follow source changes
                      </button>
                      <button
                        type="button"
                        className="secondary advanced-quick-actions__btn"
                        onClick={() =>
                          onOverrideChange(selected.channel.channel, {
                            pan: 64,
                          })
                        }
                      >
                        Center pan
                      </button>
                    </div>
                  )}

                  <div className="advanced-toggle-row advanced-toggle-row--detail">
                    <label className="advanced-checkbox">
                      <input
                        type="checkbox"
                        checked={selected.override.mute}
                        onChange={e =>
                          onOverrideChange(selected.channel.channel, { mute: e.target.checked })
                        }
                      />
                      <span>Mute channel</span>
                    </label>
                    <label className="advanced-checkbox">
                      <input
                        type="checkbox"
                        checked={selected.override.solo}
                        onChange={e =>
                          onOverrideChange(selected.channel.channel, { solo: e.target.checked })
                        }
                      />
                      <span>Solo channel</span>
                    </label>
                  </div>
                </>
              ) : (
                <p className="hint">No active channels found in this MIDI.</p>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}