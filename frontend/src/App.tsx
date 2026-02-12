import React, { useRef, useState } from 'react';

import './styles.css';

type SoundfontId = 'snes' | 'gba' | 'nds' | 'ps2' | 'wii';
type RemasterMode = 'baseline' | 'ml';

interface RemasterResult {
  request_id: string;
  midi_url?: string;
  audio_url?: string;
  audio_error?: string;
  soundfont?: string;
  prompt_soundfont?: string;
  method?: string;
  description?: string;
  classifications?: {
    [channel: string]: {
      program: number;
      name: string;
    };
  };
}

interface LogEntry {
  timestamp: string;
  message: string;
  type: 'info' | 'success' | 'error' | 'warning';
}

const API_BASE = 'http://localhost:8001';

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [soundfont, setSoundfont] = useState<SoundfontId>('snes');
  const [mode, setMode] = useState<RemasterMode>('baseline');
  const [description, setDescription] = useState<string>('');
  const [mlAvailableSoundfonts, setMlAvailableSoundfonts] = useState<string[]>([]);
  const [result, setResult] = useState<RemasterResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [progress, setProgress] = useState(0);
  const progressIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null,
  );

  // Fetch available ML soundfonts on mount
  React.useEffect(() => {
    fetch(`${API_BASE}/api/ml/available_soundfonts`)
      .then(res => res.json())
      .then(data => {
        if (data.available) {
          setMlAvailableSoundfonts(data.available);
        }
      })
      .catch(() => {
        // ML not available, keep empty
      });
  }, []);

  const addLog = (message: string, type: LogEntry['type'] = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [...prev, { timestamp, message, type }]);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setResult(null);
      setError(null);
      setLogs([]);
      setProgress(0);
      addLog(`Selected file: ${e.target.files[0].name}`, 'info');
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setLogs([]);
    setProgress(0);

    try {
      const endpoint = mode === 'ml' ? '/api/remaster_ml' : '/api/remaster';
      addLog(
        `Mode: ${mode.toUpperCase()} | Soundfont: ${soundfont.toUpperCase()}`,
        'info',
      );
      addLog('Starting upload...', 'info');
      setProgress(10);

      const formData = new FormData();
      formData.append('file', file);
      formData.append('soundfont', soundfont);
      if (mode === 'ml' && description.trim()) {
        formData.append('description', description.trim());
      }

      addLog('Uploading file to backend...', 'info');
      setProgress(25);

      const controller = new AbortController();
      // Longer timeout for ML mode (15 min), shorter for baseline (5 min)
      const timeoutMs = mode === 'ml' ? 900000 : 300000;
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

      progressIntervalRef.current = setInterval(() => {
        setProgress(p => (p < 95 ? p + 1 : p));
      }, 2000);

      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
        progressIntervalRef.current = null;
      }

      setProgress(90);

      if (!response.ok) {
        let detail = 'Upload failed';
        try {
          const err = await response.json();
          if (err.detail) detail = err.detail;
        } catch {
          // ignore parse error
        }
        throw new Error(detail);
      }

      const data: RemasterResult = await response.json();
      setResult(data);
      setProgress(100);
      addLog('Remaster complete.', 'success');

      if (data.audio_error) {
        addLog(`Audio warning: ${data.audio_error}`, 'warning');
      }
    } catch (err) {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
        progressIntervalRef.current = null;
      }
      let msg = err instanceof Error ? err.message : 'Upload failed';
      if (err instanceof Error && err.name === 'AbortError') {
        msg = 'Request timed out (5 min).';
      } else if (msg.includes('Failed to fetch')) {
        msg = 'Backend not reachable on http://localhost:8001';
      }
      setError(msg);
      addLog(`Error: ${msg}`, 'error');
      setProgress(0);
    } finally {
      setLoading(false);
    }
  };

  const resolveUrl = (url?: string | null) => {
    if (!url) return undefined;
    return url.startsWith('http') ? url : `${API_BASE}${url}`;
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand-stack">
          <h1>MIDI REMASTER LAB</h1>
          <p>Transform MIDI to Console Soundfonts.</p>
        </div>
      </header>

      <main className="app-main">
        <section className="panel panel-upload">
          <h2>Upload</h2>
          <p className="hint">Accepts: .mid, .midi</p>

          <div className="field">
            <span>Mode</span>
            <div className="mode-toggle">
              <button
                type="button"
                className={
                  'mode-btn' + (mode === 'baseline' ? ' mode-btn-active' : '')
                }
                onClick={() => setMode('baseline')}
                disabled={loading}
              >
                Baseline (Soundfont)
              </button>
              <button
                type="button"
                className={
                  'mode-btn' + (mode === 'ml' ? ' mode-btn-active' : '')
                }
                onClick={() => setMode('ml')}
                disabled={loading}
              >
                ML (MusicGen)
              </button>
            </div>
          </div>

          <div className="field">
            <span>Console soundfont {mode === 'ml' ? 'prompt' : 'bus'}</span>
            <div className="sf-board">
              {(
                [
                  { id: 'snes', label: 'SNES', note: '16‑bit strings' },
                  { id: 'gba', label: 'GBA', note: 'Handheld synth' },
                  { id: 'nds', label: 'NDS', note: 'Keys & organs' },
                  { id: 'ps2', label: 'PS2', note: 'Cinematic mix' },
                  { id: 'wii', label: 'Wii', note: 'Orchestral stage' },
                ] as const
              ).map(sf => {
                const isAvailableForML =
                  mode === 'baseline' ||
                  mlAvailableSoundfonts.includes(sf.id);
                return (
                  <button
                    key={sf.id}
                    type="button"
                    className={
                      'sf-pill' +
                      (soundfont === sf.id ? ' sf-pill-active' : '') +
                      (!isAvailableForML ? ' sf-pill-disabled' : '')
                    }
                    onClick={() => setSoundfont(sf.id)}
                    disabled={loading || !isAvailableForML}
                    title={
                      !isAvailableForML
                        ? `ML model not available for ${sf.label}`
                        : ''
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
            <div className="field">
              <span>Description (optional)</span>
              <input
                type="text"
                placeholder="e.g., video game music, upbeat chiptune..."
                value={description}
                onChange={e => setDescription(e.target.value)}
                disabled={loading}
                className="text-input"
              />
            </div>
          )}

          <input
            type="file"
            accept=".mid,.midi"
            onChange={handleFileChange}
            disabled={loading}
          />
          <button
            onClick={handleUpload}
            disabled={!file || loading}
            className="primary"
          >
            {loading ? 'Processing…' : 'Remaster'}
          </button>

          {loading && (
            <div className="progress">
              <div className="bar">
                <div className="fill" style={{ width: `${progress}%` }} />
              </div>
              <span>{progress}%</span>
            </div>
          )}
        </section>

        <section className="panel">
          <h2>Logs</h2>
          <div className="logs">
            {logs.map((log, i) => (
              <div key={i} className={`log log-${log.type}`}>
                <span className="log-time">[{log.timestamp}]</span>
                <span className="log-msg">{log.message}</span>
              </div>
            ))}
            {logs.length === 0 && <p className="hint">No logs yet.</p>}
          </div>
        </section>

        <section className="panel">
          <h2>Result</h2>
          {error && <div className="error">Error: {error}</div>}
          {result && (
            <>
              {result.method && (
                <p>
                  Method: <strong>{result.method.toUpperCase()}</strong>
                </p>
              )}
              {result.soundfont && (
                <p>
                  Soundfont: <strong>{result.soundfont.toUpperCase()}</strong>
                </p>
              )}
              {result.prompt_soundfont && (
                <p>
                  Prompt soundfont:{' '}
                  <strong>{result.prompt_soundfont.toUpperCase()}</strong>
                </p>
              )}
              {result.description && (
                <p>
                  Description: <em>{result.description}</em>
                </p>
              )}
              <div className="downloads">
                {result.midi_url && (
                  <a
                    href={resolveUrl(result.midi_url)}
                    className="button secondary"
                    download
                  >
                    Download MIDI
                  </a>
                )}
                {result.audio_url && !result.audio_error && (
                  <a
                    href={resolveUrl(result.audio_url)}
                    className="button secondary"
                    download
                  >
                    Download MP3
                  </a>
                )}
              </div>
              {result.audio_error && (
                <p className="warning">
                  Audio not available: {result.audio_error}
                </p>
              )}
              {result.classifications && (
                <>
                  <h3>Channel classifications</h3>
                  <ul className="classifications">
                    {Object.entries(result.classifications || {}).map(
                      ([ch, info]) => (
                        <li key={ch}>
                          <strong>Channel {ch}:</strong> {info.name} (Program{' '}
                          {info.program})
                        </li>
                      ),
                    )}
                  </ul>
                </>
              )}
            </>
          )}
          {!error && !result && (
            <p className="hint">
              Upload a MIDI and click Remaster to see results.
            </p>
          )}
        </section>
      </main>

      <footer className="app-footer">
        <p>
          TEST - Baseline Remapping |{' '}
          <a href={`${API_BASE}/health`} target="_blank" rel="noreferrer">
            API Health
          </a>
        </p>
      </footer>
    </div>
  );
}

export default App;

