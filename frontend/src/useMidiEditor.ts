import { useReducer, useRef, useState } from 'react';

import { applyMidiEdits, toErrorDisplay, type EditedRemasterResponse, type NoteEditOperation, type UpdateNoteOperation } from './api';

interface EditHistory {
  past: NoteEditOperation[][];
  present: NoteEditOperation[];
  future: NoteEditOperation[][];
}

type HistoryAction =
  | { type: 'queue'; operation: NoteEditOperation }
  | { type: 'undo' | 'redo' | 'reset' };

function editHistory(state: EditHistory, action: HistoryAction): EditHistory {
  if (action.type === 'reset') return { past: [], present: [], future: [] };
  if (action.type === 'undo') {
    if (!state.past.length) return state;
    return { past: state.past.slice(0, -1), present: state.past[state.past.length - 1], future: [state.present, ...state.future] };
  }
  if (action.type === 'redo') {
    if (!state.future.length) return state;
    return { past: [...state.past, state.present], present: state.future[0], future: state.future.slice(1) };
  }
  if (action.type !== 'queue') return state;
  const operation = action.operation;
  const present = [...state.present.filter(item => (
    'note_id' in operation && 'note_id' in item ? item.note_id !== operation.note_id
      : operation.type === 'set_channel_program' && item.type === 'set_channel_program' ? item.channel !== operation.channel : true
  )), { ...operation }];
  if (JSON.stringify(present) === JSON.stringify(state.present)) return state;
  return { past: [...state.past, state.present], present, future: [] };
}

export function useMidiEditor(requestId: string, onApplied: (result: EditedRemasterResponse) => void, onApplyingChange: (value: boolean) => void) {
  const [enabled, setEnabled] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [history, dispatch] = useReducer(editHistory, { past: [], present: [], future: [] });
  const operations = history.present;
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);

  const queueNote = (operation: UpdateNoteOperation) => {
    dispatch({ type: 'queue', operation });
    setError(null);
  };
  const deleteNote = (noteId: string) => {
    dispatch({ type: 'queue', operation: { type: 'delete_note', note_id: noteId } });
    setSelectedId(null);
    setError(null);
  };
  const queueProgram = (channel: number, program: number) => {
    dispatch({ type: 'queue', operation: { type: 'set_channel_program', channel, program } });
    setError(null);
  };
  const discard = () => {
    dispatch({ type: 'reset' });
    setSelectedId(null);
    setError(null);
  };
  const apply = async () => {
    if (submitting.current || operations.length === 0) return;
    submitting.current = true;
    setApplying(true);
    onApplyingChange(true);
    setError(null);
    try {
      const result = await applyMidiEdits(requestId, operations);
      if (!result.request_id || !result.midi_url || !result.visualization) throw new Error('The edited MIDI response is incomplete.');
      dispatch({ type: 'reset' });
      setSelectedId(null);
      onApplied(result);
    } catch (failure) {
      setError(toErrorDisplay(failure).detail);
    } finally {
      submitting.current = false;
      setApplying(false);
      onApplyingChange(false);
    }
  };
  const undo = () => { dispatch({ type: 'undo' }); setError(null); };
  const redo = () => { dispatch({ type: 'redo' }); setError(null); };
  return { enabled, setEnabled, selectedId, setSelectedId, operations, applying, error, setError, queueNote, deleteNote, queueProgram, discard, apply,
    canUndo: history.past.length > 0, canRedo: history.future.length > 0, undo, redo };
}