import React, { useEffect, useMemo, useRef, useState } from 'react';

import type { SoundfontId } from './UploadPanel';

export interface VisualizationNote {
  id: string;
  track: number;
  channel: number;
  pitch: number;
  start_tick: number;
  duration_ticks: number;
  start_seconds: number;
  duration_seconds: number;
  velocity: number;
  program: number | null;
  instrument_name: string;
}

export interface VisualizationChannel {
  channel: number;
  instrument_name: string;
  program: number | null;
  note_count: number;
  is_drum: boolean;
}

export interface VisualizationPayload {
  source: 'remapped' | string;
  soundfont: SoundfontId;
  ticks_per_beat: number;
  duration_seconds: number;
  channels: VisualizationChannel[];
  notes: VisualizationNote[];
}

interface Props {
  visualization: VisualizationPayload;
  readOnly?: boolean;
  playbackTime?: number;
}

const PROFILE_COLORS: Record<SoundfontId, string[]> = {
  snes: ['#7dd3fc', '#a78bfa', '#f0abfc', '#67e8f9'],
  gba: ['#86efac', '#bef264', '#facc15', '#5eead4'],
  nds: ['#f9a8d4', '#c4b5fd', '#93c5fd', '#fda4af'],
  ps2: ['#fdba74', '#fca5a5', '#d8b4fe', '#93c5fd'],
  wii: ['#fde68a', '#99f6e4', '#bfdbfe', '#fbcfe8'],
};

const PROFILE_LABELS: Record<SoundfontId, string> = {
  snes: 'SNES',
  gba: 'GBA',
  nds: 'NDS',
  ps2: 'PS2',
  wii: 'Wii',
};

function formatTime(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
}

export function SoundfontVisualizerPanel({ visualization, playbackTime = 0 }: Props) {
  const [zoom, setZoom] = useState(90);
  const timelineRef = useRef<HTMLDivElement>(null);
  const notes = Array.isArray(visualization?.notes) ? visualization.notes : [];
  const ticksPerBeat = visualization.ticks_per_beat || 480;
  const timelineTicks = Math.max(1, ...notes.map(note => note.start_tick + note.duration_ticks));
  const width = Math.max(720, (timelineTicks / ticksPerBeat) * zoom);
  const rowHeight = 86;
  const colors = PROFILE_COLORS[visualization.soundfont] ?? PROFILE_COLORS.snes;
  const notesByChannel = useMemo(() => {
    const grouped = new Map<number, VisualizationNote[]>();
    notes.forEach(note => grouped.set(note.channel, [...(grouped.get(note.channel) ?? []), note]));
    return grouped;
  }, [notes]);
  const playheadX = 44 + (playbackTime / Math.max(0.001, visualization.duration_seconds)) * (timelineTicks / ticksPerBeat) * zoom;

  useEffect(() => {
    const container = timelineRef.current;
    if (!container || playbackTime <= 0) return;
    const target = Math.max(0, playheadX - container.clientWidth * 0.35);
    container.scrollTo({ left: target, behavior: 'smooth' });
  }, [playbackTime, playheadX]);

  return (
    <section className="panel soundfont-visualizer-panel" aria-labelledby="remapped-channels-title">
      <div className="sf-visualizer-heading">
        <div>
          <span className="eyebrow">Remastered output</span>
          <h2 id="remapped-channels-title">Remapped Channels</h2>
          <p className="hint">Inspect the instruments and note activity produced by the selected SoundFont.</p>
        </div>
        <div className="sf-profile-badge">
          <span className="sf-profile-dot" style={{ background: colors[0] }} />
          {PROFILE_LABELS[visualization.soundfont] ?? visualization.soundfont} soundfont profile
        </div>
      </div>
      <div className="sf-analysis-meta">
        <span>{notes.length} notes</span>
        <span>{visualization.channels.length} remapped channels</span>
        <span>{formatTime(visualization.duration_seconds)}</span>
        <span className="technical-meta">Source: {visualization.source}</span>
        <label className="sf-zoom-control">
          Zoom
          <input
            type="range"
            min="45"
            max="220"
            value={zoom}
            onChange={event => setZoom(Number(event.target.value))}
          />
        </label>
      </div>
      {notes.length === 0 ? (
        <p className="sf-empty-state sf-empty-state--compact">No note data was returned for this remastered MIDI.</p>
      ) : (
        <div className="sf-editor-layout">
          <aside className="sf-channel-list">
            <div className="sf-section-title"><h3>Remapped instruments</h3><span>{visualization.channels.length}</span></div>
            {visualization.channels.map(channel => (
              <div className="sf-channel-row sf-channel-row--active" key={channel.channel}>
                <span className="sf-channel-row__top">
                  <strong>CH {String(channel.channel + 1).padStart(2, '0')}</strong>
                  <span>{channel.note_count} notes</span>
                </span>
                <span className="sf-channel-row__instrument">{channel.instrument_name}</span>
                <span className="sf-channel-row__name">
                  Program {channel.program ?? '—'}{channel.is_drum ? ' · Drums' : ''}
                </span>
              </div>
            ))}
          </aside>
          <div className="sf-editor-main">
            <div ref={timelineRef} className="sf-visualizer-scroll" aria-label="Remapped MIDI note timeline">
              <svg className="sf-note-grid" width={width + 44} height={Math.max(rowHeight, visualization.channels.length * rowHeight)} role="img" aria-label="Remapped MIDI piano roll">
                {visualization.channels.map((channel, index) => {
                  const y = index * rowHeight;
                  return (
                    <g key={channel.channel}>
                      <rect x={0} y={y} width={width + 44} height={rowHeight} className="sf-lane sf-lane--selected" />
                      {Array.from({ length: Math.ceil(timelineTicks / ticksPerBeat) + 1 }, (_, beat) => (
                        <line key={beat} x1={44 + beat * zoom} y1={y} x2={44 + beat * zoom} y2={y + rowHeight} className={beat % 4 === 0 ? 'sf-grid-line sf-grid-line--measure' : 'sf-grid-line'} />
                      ))}
                      {(notesByChannel.get(channel.channel) ?? []).map(note => (
                        <rect
                          key={note.id}
                          x={44 + (note.start_tick / ticksPerBeat) * zoom}
                          y={y + rowHeight - 8 - (note.pitch / 128) * (rowHeight - 16) - 7}
                          width={Math.max(3, (note.duration_ticks / ticksPerBeat) * zoom)}
                          height={7}
                          rx={3}
                          fill={colors[channel.channel % colors.length]}
                          opacity={0.45 + note.velocity / 254}
                        >
                          <title>{note.instrument_name} · MIDI {note.pitch} · {formatTime(note.start_seconds)}</title>
                        </rect>
                      ))}
                    </g>
                  );
                })}
                {playbackTime > 0 && playbackTime <= visualization.duration_seconds && (
                  <line
                    x1={playheadX}
                    y1={0}
                    x2={playheadX}
                    y2={Math.max(rowHeight, visualization.channels.length * rowHeight)}
                    className="sf-playhead"
                  />
                )}
              </svg>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
