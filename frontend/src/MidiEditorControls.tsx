import { useEffect, useState } from 'react';

import type { UpdateNoteOperation } from './api';
import { GM_PROGRAMS } from './gmPrograms';
import type { SnapMode, VisualizationChannel, VisualizationNote } from './SoundfontVisualizerPanel';
import type { useMidiEditor } from './useMidiEditor';
import './midi-editor.css';

type Editor = ReturnType<typeof useMidiEditor>;

function parseInteger(value: string, minimum: number, maximum = Number.MAX_SAFE_INTEGER): number | null {
  if (!/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
}

function NoteInspector({ note, editor }: { note: VisualizationNote; editor: Editor }) {
  const pending = editor.operations.find((operation): operation is UpdateNoteOperation => operation.type === 'update_note' && operation.note_id === note.id);
  const [pitch, setPitch] = useState(String(pending?.pitch ?? note.pitch));
  const [velocity, setVelocity] = useState(String(pending?.velocity ?? note.velocity));
  const [start, setStart] = useState(String(pending?.start_tick ?? note.start_tick));
  const [duration, setDuration] = useState(String(pending?.duration_ticks ?? note.duration_ticks));
  const [validation, setValidation] = useState('');

  useEffect(() => {
    setPitch(String(note.pitch));
    setVelocity(String(note.velocity));
    setStart(String(note.start_tick));
    setDuration(String(note.duration_ticks));
  }, [note.id, note.pitch, note.velocity, note.start_tick, note.duration_ticks]);

  const queue = () => {
    const values = {
      pitch: parseInteger(pitch, 0, 127),
      velocity: parseInteger(velocity, 1, 127),
      start_tick: parseInteger(start, 0),
      duration_ticks: parseInteger(duration, 1),
    };
    if (values.pitch === null || values.velocity === null || values.start_tick === null || values.duration_ticks === null) {
      setValidation('Enter whole numbers: pitch 0-127, velocity 1-127, start tick 0 or greater, and duration at least 1 tick.');
      return;
    }
    if (values.pitch === note.pitch && values.velocity === note.velocity && values.start_tick === note.start_tick && values.duration_ticks === note.duration_ticks) {
      setValidation('Change at least one note value before adding an edit.');
      return;
    }
    setValidation('');
    editor.queueNote({ type: 'update_note', note_id: note.id, pitch: values.pitch, velocity: values.velocity,
      start_tick: values.start_tick, duration_ticks: values.duration_ticks });
  };

  return (
    <div className="midi-editor__inspector">
      <h3>Selected note</h3>
      <p>Track {note.track + 1} · Channel {note.channel + 1} · {note.instrument_name}</p>
      <div className="midi-editor__fields">
        <label>Pitch<input type="number" min="0" max="127" step="1" value={pitch} onChange={event => setPitch(event.target.value)} /></label>
        <label>Velocity<input type="number" min="1" max="127" step="1" value={velocity} onChange={event => setVelocity(event.target.value)} /></label>
        <label>Start tick<input type="number" min="0" step="1" value={start} onChange={event => setStart(event.target.value)} /></label>
        <label>Duration ticks<input type="number" min="1" step="1" value={duration} onChange={event => setDuration(event.target.value)} /></label>
      </div>
      {validation && <p className="warning" role="alert">{validation}</p>}
      <div className="midi-editor__actions">
        <button type="button" className="button secondary" onClick={queue}>Add note changes</button>
        <button type="button" className="button secondary" onClick={() => editor.deleteNote(note.id)}>Delete note</button>
      </div>
    </div>
  );
}

export function MidiEditorControls({ editor, note, channels, snap, onSnapChange }: {
  editor: Editor; note: VisualizationNote | undefined; channels: VisualizationChannel[];
  snap: SnapMode; onSnapChange: (value: SnapMode) => void;
}) {
  const validChannels = channels.filter(channel => Number.isInteger(channel.channel) && channel.channel >= 0 && channel.channel <= 15);
  const [channel, setChannel] = useState(String(validChannels[0]?.channel ?? ''));
  const initialProgram = validChannels[0]?.program;
  const [program, setProgram] = useState(String(initialProgram != null && initialProgram >= 0 && initialProgram <= 127 ? initialProgram : 0));
  const [validation, setValidation] = useState('');
  const queueProgram = () => {
    const channelValue = parseInteger(channel, 0, 15);
    const programValue = parseInteger(program, 0, 127);
    if (channelValue === null || programValue === null) {
      setValidation('Choose a channel and a GM program between 0 and 127.');
      return;
    }
    setValidation('');
    editor.queueProgram(channelValue, programValue);
  };

  return (
    <div className="midi-editor" aria-label="MIDI edit controls">
      <fieldset disabled={editor.applying}>
        <div className="midi-editor__actions">
          <label>Grid snap
            <select value={snap} onChange={event => onSnapChange(event.target.value as SnapMode)}>
              <option value="free">Free movement</option>
              <option value="sixteenth">Sixteenth notes</option>
              <option value="eighth">Eighth notes</option>
              <option value="quarter">Quarter notes</option>
            </select>
          </label>
          <button type="button" className="button secondary" onClick={editor.undo} disabled={!editor.canUndo} title="Undo (Ctrl+Z)">Undo</button>
          <button type="button" className="button secondary" onClick={editor.redo} disabled={!editor.canRedo} title="Redo (Ctrl+Y or Ctrl+Shift+Z)">Redo</button>
        </div>
        <div className="midi-editor__columns">
          {note ? <NoteInspector key={note.id} note={note} editor={editor} /> : <p className="hint">Select a note to inspect it.</p>}
          <div className="midi-editor__program">
            <h3>Channel program</h3>
            <label>Channel
              <select value={channel} onChange={event => {
                setChannel(event.target.value);
                const selected = validChannels.find(item => String(item.channel) === event.target.value);
                setProgram(String(selected?.program != null && selected.program <= 127 ? selected.program : 0));
              }}>
                {validChannels.length === 0 && <option value="">No channels</option>}
                {validChannels.map(item => <option key={item.channel} value={item.channel}>Channel {item.channel + 1}{item.is_drum ? ' (drums)' : ''}</option>)}
              </select>
            </label>
            <label>GM program
              <select value={program} onChange={event => setProgram(event.target.value)}>
                {GM_PROGRAMS.map((name, index) => <option key={index} value={index}>{index} · {name}</option>)}
              </select>
            </label>
            {validation && <p className="warning" role="alert">{validation}</p>}
            <button type="button" className="button secondary" onClick={queueProgram}>Add program change</button>
          </div>
        </div>
        <div className="midi-editor__actions midi-editor__footer">
          <strong aria-live="polite">{editor.operations.length} pending {editor.operations.length === 1 ? 'edit' : 'edits'}</strong>
          {editor.operations.length > 0 && <span>Unapplied changes</span>}
          <button type="button" className="button secondary" onClick={editor.discard} disabled={!editor.operations.length && !editor.canUndo && !editor.canRedo}>Discard pending edits</button>
          <button type="button" className="button primary" onClick={() => void editor.apply()} disabled={!editor.operations.length}>Confirm edits &amp; render MP3</button>
        </div>
      </fieldset>
      {editor.applying && <p role="status">Applying edits and rendering audio...</p>}
      {editor.error && <p className="warning" role="alert">{editor.error}</p>}
      <p className="hint">Ambiguous overlapping-note timing or unsupported note pairing may be rejected. Note IDs change after edits are applied.</p>
    </div>
  );
}