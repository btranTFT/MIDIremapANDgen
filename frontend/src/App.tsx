import React, { useCallback, useRef, useState } from 'react';

import { API_BASE, request, toErrorDisplay } from './api';
import { LogsPanel } from './LogsPanel';
import type { LogEntry } from './LogsPanel';
import type { RemasterResult } from './ResultPanel';
import { ResultPanel } from './ResultPanel';
import {
  UploadPanel,
  type RemasterMode,
  type SoundfontId,
} from './UploadPanel';
import './styles.css';

const CAPABILITIES_TIMEOUT_MS = 5000;
const DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

interface HealthCapabilities {
  ml_available?: boolean;
  available_styles?: string[];
  ml_available_styles?: string[];
  max_upload_bytes?: number;
}

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [soundfont, setSoundfont] = useState<SoundfontId>('snes');
  const [mode, setMode] = useState<RemasterMode>('baseline');
  const [description, setDescription] = useState<string>('');
  const [mlAvailableSoundfonts, setMlAvailableSoundfonts] = useState<string[]>(
    [],
  );
  const [mlAvailable, setMlAvailable] = useState(false);
  const [maxUploadBytes, setMaxUploadBytes] = useState(DEFAULT_MAX_UPLOAD_BYTES);
  const [result, setResult] = useState<RemasterResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<import('./api').ErrorDisplay | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [progress, setProgress] = useState(0);
  const [activeMobileTab, setActiveMobileTab] = useState<
    'upload' | 'logs' | 'result'
  >('upload');
  const progressIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null,
  );

  // Single capabilities source: GET /health. On failure (offline/timeout), ML stays disabled.
  React.useEffect(() => {
    request<HealthCapabilities>('/health', {
      method: 'GET',
      timeoutMs: CAPABILITIES_TIMEOUT_MS,
    })
      .then(data => {
        if (typeof data.ml_available === 'boolean') {
          setMlAvailable(data.ml_available);
        }
        if (Array.isArray(data.ml_available_styles)) {
          setMlAvailableSoundfonts(data.ml_available_styles);
        }
        if (typeof data.max_upload_bytes === 'number' && data.max_upload_bytes > 0) {
          setMaxUploadBytes(data.max_upload_bytes);
        }
      })
      .catch(() => {
        // Offline, timeout, or parse error: leave mlAvailable false, mlAvailableSoundfonts []
      });
  }, []);

  const addLog = useCallback((
    message: string,
    type: LogEntry['type'] = 'info',
    step?: string,
    debug?: string,
  ) => {
    const now = new Date();
    const timestamp = now.toLocaleTimeString();
    const ts = now.toISOString().slice(0, 23) + 'Z';
    setLogs(prev => [...prev, { timestamp, ts, message, type, step, debug }]);
  }, []);

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
    setResult(null);
    setLogs([]);
    setProgress(0);

    try {
      const endpoint = mode === 'ml' ? '/api/remaster_ml' : '/api/remaster';
      addLog(
        `Mode: ${mode.toUpperCase()} | Soundfont: ${soundfont.toUpperCase()}`,
        'info',
        'upload',
      );
      addLog('Starting upload...', 'info', 'upload');
      setProgress(10);

      const formData = new FormData();
      formData.append('file', file);
      formData.append('soundfont', soundfont);
      if (mode === 'ml' && description.trim()) {
        formData.append('description', description.trim());
      }

      addLog('Uploading file to backend...', 'info', 'upload');
      setProgress(25);

      const timeoutMs = mode === 'ml' ? 900000 : 300000;
      // Use functional update to avoid stale closure, batch updates
      progressIntervalRef.current = setInterval(() => {
        setProgress(p => {
          const next = p < 95 ? p + 1 : p;
          return next;
        });
      }, 2000);

      // Debug logging: log request details
      console.log('[Remaster] Starting request:', {
        endpoint,
        mode,
        soundfont,
        fileSize: file.size,
        timeoutMs,
      });

      const data = await request<
        RemasterResult & {
          logs?: Array<{
            ts?: string;
            level?: string;
            step?: string;
            message?: string;
            debug?: string;
          }>;
        }
      >(endpoint, {
        method: 'POST',
        body: formData,
        timeoutMs,
      });

      // Debug logging: log response shape for troubleshooting
      console.log('[Remaster] Response received:', {
        hasRequestId: !!data.request_id,
        hasMidiUrl: !!data.midi_url,
        hasAudioUrl: !!data.audio_url,
        hasLogs: Array.isArray(data.logs),
        logsCount: Array.isArray(data.logs) ? data.logs.length : 0,
        hasClassifications: !!data.classifications,
        hasMetadata: !!data.metadata,
      });

      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
        progressIntervalRef.current = null;
      }
      setProgress(90);

      // Ensure required fields exist before setting result
      if (!data.request_id) {
        console.error('[Remaster] Response missing request_id:', data);
        throw new Error('Invalid response: missing request_id');
      }

      setResult(data);
      setProgress(100);
      if (Array.isArray(data.logs) && data.logs.length > 0) {
        const mapped = data.logs
          .filter(ev => ev && typeof ev.message === 'string')
          .map(ev => ({
            ts: ev.ts ?? '',
            message: ev.message ?? 'Unknown message',
            level: (ev.level === 'warn' ? 'warn' : ev.level === 'error' ? 'error' : 'info') as LogEntry['level'],
            step: ev.step ?? '',
            debug: ev.debug,
          }));
        setLogs(prev => [...prev, ...mapped]);
        addLog('Remaster complete.', 'success');
      } else {
        addLog('Remaster complete.', 'success');
      }

      if (data.audio_error) {
        addLog(`Audio warning: ${data.audio_error}`, 'warning', 'encode');
      }
    } catch (err) {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
        progressIntervalRef.current = null;
      }
      // Debug logging: log error details
      console.error('[Remaster] Request failed:', err);
      if (err instanceof Error) {
        console.error('[Remaster] Error stack:', err.stack);
      }
      const display = toErrorDisplay(err);
      console.log('[Remaster] Error display:', display);
      setError(display);
      addLog(display.detail, 'error', undefined, display.debug);
      setProgress(0);
    } finally {
      setLoading(false);
    }
  };

  const resolveUrl = useCallback((url?: string | null) => {
    if (!url) return undefined;
    return url.startsWith('http') ? url : `${API_BASE}${url}`;
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand-stack">
          <h1>MIDI REMASTER LAB</h1>
          <p>Transform MIDI to Console Soundfonts.</p>
        </div>
      </header>

      <main className="app-main">
        <nav
          className="app-main__mobile-tabs"
          aria-label="Sections"
        >
          <button
            type="button"
            className={`app-main__mobile-tab ${activeMobileTab === 'upload' ? 'app-main__mobile-tab--active' : ''}`}
            onClick={() => setActiveMobileTab('upload')}
            aria-pressed={activeMobileTab === 'upload'}
          >
            Upload
          </button>
          <button
            type="button"
            className={`app-main__mobile-tab ${activeMobileTab === 'logs' ? 'app-main__mobile-tab--active' : ''}`}
            onClick={() => setActiveMobileTab('logs')}
            aria-pressed={activeMobileTab === 'logs'}
          >
            Logs
          </button>
          <button
            type="button"
            className={`app-main__mobile-tab ${activeMobileTab === 'result' ? 'app-main__mobile-tab--active' : ''}`}
            onClick={() => setActiveMobileTab('result')}
            aria-pressed={activeMobileTab === 'result'}
          >
            Result
          </button>
        </nav>
        <div
          className={`app-main__panel-wrap ${activeMobileTab === 'upload' ? 'app-main__panel-wrap--visible' : ''}`}
          data-panel="upload"
        >
          <UploadPanel
            file={file}
            soundfont={soundfont}
            mode={mode}
            description={description}
            loading={loading}
            progress={progress}
            mlAvailableSoundfonts={mlAvailableSoundfonts}
            mlAvailable={mlAvailable}
            maxUploadBytes={maxUploadBytes}
            onFileChange={handleFileChange}
            onUpload={handleUpload}
            onModeChange={setMode}
            onSoundfontChange={setSoundfont}
            onDescriptionChange={setDescription}
          />
        </div>
        <div
          className={`app-main__panel-wrap ${activeMobileTab === 'logs' ? 'app-main__panel-wrap--visible' : ''}`}
          data-panel="logs"
        >
          <LogsPanel logs={logs} />
        </div>
        <div
          className={`app-main__panel-wrap ${activeMobileTab === 'result' ? 'app-main__panel-wrap--visible' : ''}`}
          data-panel="result"
        >
          <ResultPanel
            error={error}
            result={result}
            loading={loading}
            resolveUrl={resolveUrl}
          />
        </div>
      </main>

      <footer className="app-footer">
        <p>
          MIDI Remaster Lab |{' '}
          <a href={`${API_BASE}/health`} target="_blank" rel="noreferrer">
            API Health
          </a>
        </p>
      </footer>
    </div>
  );
}

export default App;
