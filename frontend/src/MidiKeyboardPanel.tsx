import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const START_NOTE = 48;
const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const KEYBOARD_MAP: Record<string, number> = {
  a: 0, w: 1, s: 2, e: 3, d: 4, f: 5, t: 6, g: 7, y: 8, h: 9, u: 10, j: 11,
  k: 12, o: 13, l: 14, p: 15, ';': 16, ']': 17,
};

function isBlackKey(note: number) {
  return [1, 3, 6, 8, 10].includes(note % 12);
}

export function MidiKeyboardPanel() {
  const [inputs, setInputs] = useState<MIDIInput[]>([]);
  const [selectedInput, setSelectedInput] = useState('');
  const [activeNotes, setActiveNotes] = useState<Set<number>>(new Set());
  const [midiMessage, setMidiMessage] = useState('No MIDI input connected');
  const [browserAudioReady, setBrowserAudioReady] = useState(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const voicesRef = useRef<Map<number, OscillatorNode>>(new Map());
  const sustainRef = useRef(false);
  const sustainedNotesRef = useRef<Set<number>>(new Set());
  const inputsRef = useRef<MIDIInput[]>([]);

  const stopNote = useCallback((note: number) => {
    const oscillator = voicesRef.current.get(note);
    if (oscillator) {
      oscillator.stop();
      voicesRef.current.delete(note);
    }
    setActiveNotes(previous => {
      const next = new Set(previous);
      next.delete(note);
      return next;
    });
  }, []);

  const startNote = useCallback((note: number, velocity = 100) => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext();
    }
    const context = audioContextRef.current;
    void context.resume();
    if (voicesRef.current.has(note)) return;
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = 'triangle';
    oscillator.frequency.value = 440 * Math.pow(2, (note - 69) / 12);
    gain.gain.setValueAtTime(Math.max(0.03, velocity / 127 * 0.18), context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 1.8);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start();
    voicesRef.current.set(note, oscillator);
    setBrowserAudioReady(true);
    setActiveNotes(previous => new Set(previous).add(note));
  }, []);

  const handleNoteOff = useCallback((note: number) => {
    if (sustainRef.current) {
      sustainedNotesRef.current.add(note);
      return;
    }
    stopNote(note);
  }, [stopNote]);

  const handleMidiMessage = useCallback((event: MIDIMessageEvent) => {
    if (!event.data || event.data.length < 3) return;
    const [status, note, velocity] = event.data;
    const command = status & 0xf0;
    if (command === 0x90 && velocity > 0) {
      startNote(note, velocity);
      setMidiMessage(`Note on ${NOTE_NAMES[note % 12]}${Math.floor(note / 12) - 1}`);
    } else if (command === 0x80 || (command === 0x90 && velocity === 0)) {
      handleNoteOff(note);
    } else if (command === 0xb0 && note === 64) {
      const enabled = velocity >= 64;
      sustainRef.current = enabled;
      if (!enabled) {
        sustainedNotesRef.current.forEach(stopNote);
        sustainedNotesRef.current.clear();
      }
    }
  }, [handleNoteOff, startNote, stopNote]);

  useEffect(() => {
    let access: MIDIAccess | null = null;
    const connect = async () => {
      if (!navigator.requestMIDIAccess) {
        setMidiMessage('Web MIDI is not available in this browser');
        return;
      }
      try {
        access = await navigator.requestMIDIAccess({ sysex: false });
        const available = Array.from(access.inputs.values());
        inputsRef.current = available;
        setInputs(available);
        if (available[0]) setSelectedInput(available[0].id);
      } catch {
        setMidiMessage('MIDI access was not granted');
      }
    };
    void connect();
    return () => {
      inputsRef.current.forEach(input => { input.onmidimessage = null; });
      voicesRef.current.forEach(oscillator => oscillator.stop());
      voicesRef.current.clear();
      access = null;
    };
  }, []);

  useEffect(() => {
    inputs.forEach(input => {
      input.onmidimessage = input.id === selectedInput ? handleMidiMessage : null;
    });
    return () => {
      inputs.forEach(input => { input.onmidimessage = null; });
    };
  }, [handleMidiMessage, inputs, selectedInput]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.repeat) return;
      const offset = KEYBOARD_MAP[event.key.toLowerCase()];
      if (offset != null) {
        event.preventDefault();
        startNote(START_NOTE + offset);
      }
    };
    const handleKeyUp = (event: KeyboardEvent) => {
      const offset = KEYBOARD_MAP[event.key.toLowerCase()];
      if (offset != null) handleNoteOff(START_NOTE + offset);
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [handleNoteOff, startNote]);

  useEffect(() => () => {
    voicesRef.current.forEach(oscillator => oscillator.stop());
    voicesRef.current.clear();
    if (audioContextRef.current) void audioContextRef.current.close();
  }, []);

  const keys = useMemo(() => Array.from({ length: 25 }, (_, index) => START_NOTE + index), []);

  return (
    <section className="midi-keyboard-panel" aria-labelledby="midi-keyboard-title">
      <div className="midi-keyboard-panel__heading">
        <div>
          <span className="eyebrow">Browser MIDI</span>
          <h2 id="midi-keyboard-title">MIDI keyboard</h2>
          <p className="hint">Play a connected controller or use your computer keyboard. Browser audio preview only.</p>
        </div>
        <span className="midi-keyboard-panel__status">{browserAudioReady ? 'Browser audio ready' : 'Preview idle'}</span>
      </div>
      <div className="midi-keyboard-panel__controls">
        <label>
          <span className="field__label">MIDI input</span>
          <select
            className="text-input"
            value={selectedInput}
            onChange={event => setSelectedInput(event.target.value)}
            disabled={!inputs.length}
          >
            {!inputs.length && <option value="">No MIDI inputs detected</option>}
            {inputs.map(input => (
              <option key={input.id} value={input.id}>{input.name || input.manufacturer || input.id}</option>
            ))}
          </select>
        </label>
        <span className="midi-keyboard-panel__message">{midiMessage}</span>
      </div>
      <div className="piano" role="application" aria-label="Two octave virtual piano">
        {keys.map(note => (
          <button
            key={note}
            type="button"
            className={`piano__key ${isBlackKey(note) ? 'piano__key--black' : 'piano__key--white'} ${activeNotes.has(note) ? 'piano__key--active' : ''}`}
            onPointerDown={() => startNote(note)}
            onPointerUp={() => handleNoteOff(note)}
            onPointerLeave={() => { if (activeNotes.has(note)) handleNoteOff(note); }}
            aria-label={`${NOTE_NAMES[note % 12]}${Math.floor(note / 12) - 1}`}
          >
            {!isBlackKey(note) && <span>{NOTE_NAMES[note % 12]}</span>}
          </button>
        ))}
      </div>
      <p className="midi-keyboard-panel__hint">Computer keys: A–L and W/E/T/Y/U/O/P for sharps. Sustain pedal CC64 is supported.</p>
    </section>
  );
}
