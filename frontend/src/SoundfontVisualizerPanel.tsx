import React, { useEffect, useMemo, useRef, useState } from 'react';

import type { EditedRemasterResponse } from './api';
import { MidiEditorControls } from './MidiEditorControls';
import type { SoundfontId } from './UploadPanel';
import { useMidiEditor } from './useMidiEditor';

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
  requestId?: string;
  onEdited?: (result: EditedRemasterResponse) => void;
  onApplyingChange?: (value: boolean) => void;
}

const CHANNEL_COLORS = [
  '#6dc9f7', '#ae8df4', '#e993c3', '#6dd9ba', '#e9bc6c', '#f28c85', '#8ca4fa', '#bfdb79',
  '#d899ec', '#75d9dc', '#f0a572', '#92c5a5', '#d7a1a1', '#a5b7df', '#c5b583', '#a6c5e0',
];

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

export type SnapMode = 'free' | 'sixteenth' | 'eighth' | 'quarter';

interface DragState {
  pointerId: number;
  x: number;
  y: number;
  scrollLeft: number;
  scaleX: number;
  scaleY: number;
  note: VisualizationNote;
}

export function SoundfontVisualizerPanel({ visualization, playbackTime = 0, readOnly = true, requestId = '', onEdited, onApplyingChange }: Props) {
  const [zoom, setZoom] = useState(90);
  const [snap, setSnap] = useState<SnapMode>('sixteenth');
  const [selectedChannel, setSelectedChannel] = useState<number | null>(null);
  const [dragPreview, setDragPreview] = useState<{ id: string; pitch: number; start_tick: number } | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const editor = useMidiEditor(requestId, result => onEdited?.(result), value => onApplyingChange?.(value));
  const timelineRef = useRef<HTMLDivElement>(null);
  const sourceNotes = Array.isArray(visualization?.notes) ? visualization.notes : [];
  const channels = Array.isArray(visualization?.channels) ? visualization.channels : [];
  const ticksPerBeat = Number(visualization?.ticks_per_beat) > 0 ? visualization.ticks_per_beat : 480;
  const durationSeconds = Number(visualization?.duration_seconds) > 0 ? visualization.duration_seconds : 0;
  const rowHeight = 86;
  const snapTicks = snap === 'free' ? 1 : Math.max(1, Math.round(ticksPerBeat / (snap === 'sixteenth' ? 4 : snap === 'eighth' ? 2 : 1)));
  const notes = useMemo(() => {
    const edits = new Map(editor.operations.filter(operation => 'note_id' in operation).map(operation => [operation.note_id, operation]));
    return sourceNotes.flatMap(note => {
      const operation = edits.get(note.id);
      if (operation?.type === 'delete_note') return [];
      const updated = operation?.type === 'update_note' ? {
        ...note, pitch: operation.pitch ?? note.pitch, velocity: operation.velocity ?? note.velocity,
        start_tick: operation.start_tick ?? note.start_tick, duration_ticks: operation.duration_ticks ?? note.duration_ticks,
      } : note;
      return [dragPreview?.id === note.id ? { ...updated, pitch: dragPreview.pitch, start_tick: dragPreview.start_tick } : updated];
    });
  }, [sourceNotes, editor.operations, dragPreview]);
  const timelineTicks = Math.max(1, ...notes.map(note => note.start_tick + note.duration_ticks));
  const width = Math.max(720, (timelineTicks / ticksPerBeat) * zoom);
  const colors = CHANNEL_COLORS;
  const activeChannel = selectedChannel ?? channels[0]?.channel;
  const selectedNote = notes.find(note => note.id === editor.selectedId);
  const notesByChannel = useMemo(() => {
    const grouped = new Map<number, VisualizationNote[]>();
    notes.forEach(note => grouped.set(note.channel, [...(grouped.get(note.channel) ?? []), note]));
    return grouped;
  }, [notes]);
  const playheadX = 44 + (playbackTime / Math.max(0.001, durationSeconds)) * (timelineTicks / ticksPerBeat) * zoom;

  const queueMovedNote = (note: VisualizationNote, pitch: number, startTick: number) => {
    if (pitch === note.pitch && startTick === note.start_tick) return;
    editor.queueNote({ type: 'update_note', note_id: note.id, pitch, velocity: note.velocity,
      start_tick: startTick, duration_ticks: note.duration_ticks });
  };

  useEffect(() => {
    if (readOnly || !editor.enabled || editor.applying) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest('input, select, textarea, [contenteditable]:not([contenteditable="false"])')) return;
      if (event.ctrlKey || event.metaKey) {
        if (event.key.toLowerCase() === 'z') {
          event.preventDefault();
          if (event.shiftKey) editor.redo(); else editor.undo();
        } else if (event.key.toLowerCase() === 'y') {
          event.preventDefault();
          editor.redo();
        }
        return;
      }
      if (!selectedNote || event.altKey) return;
      const pitchStep = event.shiftKey ? 12 : 1;
      if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault();
        editor.deleteNote(selectedNote.id);
      } else if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
        event.preventDefault();
        const pitch = Math.max(0, Math.min(127, selectedNote.pitch + (event.key === 'ArrowUp' ? pitchStep : -pitchStep)));
        queueMovedNote(selectedNote, pitch, selectedNote.start_tick);
      } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        const start = Math.max(0, Math.min(Number.MAX_SAFE_INTEGER, selectedNote.start_tick + (event.key === 'ArrowRight' ? snapTicks : -snapTicks)));
        queueMovedNote(selectedNote, selectedNote.pitch, start);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  const dragPosition = (event: React.PointerEvent<SVGRectElement>, drag: DragState) => {
    const deltaX = (event.clientX - drag.x + (timelineRef.current?.scrollLeft ?? 0) - drag.scrollLeft) / drag.scaleX;
    const deltaY = (event.clientY - drag.y) / drag.scaleY;
    if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 3) return { pitch: drag.note.pitch, start_tick: drag.note.start_tick };
    const rawTick = drag.note.start_tick + deltaX * ticksPerBeat / zoom;
    const snappedTick = Math.abs(deltaX) < 1 ? drag.note.start_tick : snap === 'free' ? Math.round(rawTick) : Math.round(rawTick / snapTicks) * snapTicks;
    return { pitch: Math.max(0, Math.min(127, Math.round(drag.note.pitch - deltaY * 128 / (rowHeight - 16)))),
      start_tick: Math.max(0, Math.min(Number.MAX_SAFE_INTEGER, snappedTick)) };
  };

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
          <span className="eyebrow">Baseline remaster</span>
          <h2 id="remapped-channels-title">Remapped MIDI channels</h2>
          <p className="hint">Exact post-remap MIDI instruments and note activity from the baseline remaster.</p>
        </div>
        <div className="sf-profile-badge">
          <span className="sf-profile-dot" style={{ background: colors[0] }} />
          {PROFILE_LABELS[visualization?.soundfont] ?? visualization?.soundfont ?? 'SNES'} soundfont profile
        </div>
      </div>
      {!readOnly && requestId && (
        <>
          <button type="button" className="button secondary midi-editor__toggle" aria-pressed={editor.enabled}
            disabled={editor.applying} onClick={() => editor.setEnabled(!editor.enabled)}>
            {editor.enabled ? 'Close MIDI editor' : 'Edit MIDI'}
          </button>
          {!editor.enabled && editor.operations.length > 0 && <span> {editor.operations.length} pending {editor.operations.length === 1 ? 'edit' : 'edits'}</span>}
        </>
      )}
      <div className="sf-analysis-meta">
        <span>{notes.length} notes</span>
        <span>{channels.length} remapped channels</span>
        <span>{formatTime(durationSeconds)}</span>
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
            <div className="sf-section-title"><h3>Remapped instruments</h3><span>{channels.length}</span></div>
            {channels.map(channel => (
              <button type="button" className={`sf-channel-row${activeChannel === channel.channel ? ' sf-channel-row--active' : ''}`} key={channel.channel}
                aria-pressed={activeChannel === channel.channel} onClick={() => setSelectedChannel(channel.channel)}
                style={{ borderLeftColor: colors[channel.channel % colors.length] }}>
                <span className="sf-channel-row__top">
                  <strong>CH {String(channel.channel + 1).padStart(2, '0')}</strong>
                  <span>{channel.note_count} notes</span>
                </span>
                <span className="sf-channel-row__instrument">{channel.instrument_name}</span>
                <span className="sf-channel-row__name">
                  Program {channel.program ?? '—'}{channel.is_drum ? ' · Drums' : ''}
                </span>
              </button>
            ))}
          </aside>
          <div className="sf-editor-main">
            <div ref={timelineRef} className="sf-visualizer-scroll" aria-label="Remapped MIDI note timeline">
              <svg className={`sf-note-grid${editor.enabled && !readOnly ? ' midi-editor__canvas' : ''}`} width={width + 44} height={Math.max(rowHeight, channels.length * rowHeight)} role={editor.enabled && !readOnly ? 'group' : 'img'} aria-label="Remapped MIDI piano roll">
                {channels.map((channel, index) => {
                  const y = index * rowHeight;
                  return (
                    <g key={channel.channel}>
                      <rect x={0} y={y} width={width + 44} height={rowHeight} className={`sf-lane${activeChannel === channel.channel ? ' sf-lane--selected' : ''}`} />
                      {Array.from({ length: Math.ceil(timelineTicks / ticksPerBeat) + 1 }, (_, beat) => (
                        <line key={beat} x1={44 + beat * zoom} y1={y} x2={44 + beat * zoom} y2={y + rowHeight} className={beat % 4 === 0 ? 'sf-grid-line sf-grid-line--measure' : 'sf-grid-line'} />
                      ))}
                      {(notesByChannel.get(channel.channel) ?? []).map(note => (
                        <rect
                          key={note.id}
                          className={editor.selectedId === note.id ? 'midi-editor__note midi-editor__note--selected' : 'midi-editor__note'}
                          role={editor.enabled && !readOnly ? 'button' : undefined}
                          tabIndex={editor.enabled && !readOnly && !editor.applying ? 0 : undefined}
                          aria-label={editor.enabled && !readOnly ? `Track ${note.track + 1}, channel ${note.channel + 1}, pitch ${note.pitch}, velocity ${note.velocity}` : undefined}
                          aria-pressed={editor.enabled && !readOnly ? editor.selectedId === note.id : undefined}
                          onClick={editor.enabled && !readOnly && !editor.applying ? () => editor.setSelectedId(note.id) : undefined}
                          onPointerDown={editor.enabled && !readOnly && !editor.applying ? event => {
                            if (event.button !== 0) return;
                            event.preventDefault();
                            const matrix = event.currentTarget.ownerSVGElement?.getScreenCTM();
                            dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY,
                              scrollLeft: timelineRef.current?.scrollLeft ?? 0, scaleX: matrix?.a || 1, scaleY: matrix?.d || 1, note };
                            editor.setSelectedId(note.id);
                            setSelectedChannel(note.channel);
                            event.currentTarget.focus();
                            event.currentTarget.setPointerCapture(event.pointerId);
                          } : undefined}
                          onPointerMove={editor.enabled && !readOnly && !editor.applying ? event => {
                            const drag = dragRef.current;
                            if (!drag || drag.pointerId !== event.pointerId) return;
                            setDragPreview({ id: drag.note.id, ...dragPosition(event, drag) });
                          } : undefined}
                          onPointerUp={editor.enabled && !readOnly && !editor.applying ? event => {
                            const drag = dragRef.current;
                            if (!drag || drag.pointerId !== event.pointerId) return;
                            const position = dragPosition(event, drag);
                            dragRef.current = null;
                            setDragPreview(null);
                            queueMovedNote(drag.note, position.pitch, position.start_tick);
                            if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
                          } : undefined}
                          onPointerCancel={editor.enabled && !readOnly ? () => { dragRef.current = null; setDragPreview(null); } : undefined}
                          onLostPointerCapture={editor.enabled && !readOnly ? () => { dragRef.current = null; setDragPreview(null); } : undefined}
                          onKeyDown={editor.enabled && !readOnly && !editor.applying ? event => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              editor.setSelectedId(note.id);
                              setSelectedChannel(note.channel);
                            }
                          } : undefined}
                          x={44 + (note.start_tick / ticksPerBeat) * zoom}
                          y={y + rowHeight - 8 - (note.pitch / 128) * (rowHeight - 16) - 7}
                          width={Math.max(3, (note.duration_ticks / ticksPerBeat) * zoom)}
                          height={7}
                          rx={3}
                          fill={colors[channel.channel % colors.length]}
                          opacity={0.45 + note.velocity / 254}
                        >
                          <title>{note.instrument_name} · MIDI {note.pitch} · tick {note.start_tick}</title>
                        </rect>
                      ))}
                    </g>
                  );
                })}
                {playbackTime > 0 && playbackTime <= durationSeconds && (
                  <line
                    x1={playheadX}
                    y1={0}
                    x2={playheadX}
                    y2={Math.max(rowHeight, channels.length * rowHeight)}
                    className="sf-playhead"
                  />
                )}
              </svg>
            </div>
          </div>
        </div>
      )}
      {editor.enabled && !readOnly && <MidiEditorControls editor={editor} note={selectedNote} channels={channels} snap={snap} onSnapChange={setSnap} />}
    </section>
  );
}
