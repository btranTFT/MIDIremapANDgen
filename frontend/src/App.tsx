import React, { useCallback, useState } from 'react';

import { API_BASE, request, toErrorDisplay } from './api';
import {
  getChannelDefaultOverride,
  type AdvancedAnalysisResult,
  type ChannelOverride,
} from './AdvancedBaselinePanel';
import { LogsPanel } from './LogsPanel';
import type { LogEntry } from './LogsPanel';
import type { RemasterResult } from './ResultPanel';
import { ResultPanel } from './ResultPanel';
import { SoundfontVisualizerPanel, type VisualizationPayload } from './SoundfontVisualizerPanel';
import {
  UploadPanel,
  type MlPromptMode,
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
  torch_available?: boolean;
  torch_error?: string | null;
  audiocraft_available?: boolean;
  audiocraft_error?: string | null;
  checkpoint_available?: boolean;
  checkpoint_path?: string | null;
  ml_reason?: string;
  recommended_action?: string;
  reason?: string;
}

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [soundfont, setSoundfont] = useState<SoundfontId>('snes');
  const [mode, setMode] = useState<RemasterMode>('baseline');
  const [mlPromptMode, setMlPromptMode] = useState<MlPromptMode>('text');
  const [mlDuration, setMlDuration] = useState<15 | 30>(15);
  const [advancedEnabled, setAdvancedEnabled] = useState(false);
  const [analysis, setAnalysis] = useState<AdvancedAnalysisResult | null>(null);
  const [channelOverrides, setChannelOverrides] = useState<Record<string, ChannelOverride>>({});
  const [sourceStyle, setSourceStyle] = useState<SoundfontId | ''>('');
  const [description, setDescription] = useState<string>('');
  const [mlAvailableSoundfonts, setMlAvailableSoundfonts] = useState<string[]>(
    [],
  );
  const [mlAvailable, setMlAvailable] = useState(false);
  const [mlUnavailableReason, setMlUnavailableReason] = useState('ML capability diagnostics are unavailable.');
  const [mlRecommendedAction, setMlRecommendedAction] = useState('');
  const [torchError, setTorchError] = useState<string | null>(null);
  const [audiocraftError, setAudiocraftError] = useState<string | null>(null);
  const [maxUploadBytes, setMaxUploadBytes] = useState(DEFAULT_MAX_UPLOAD_BYTES);
  const [result, setResult] = useState<RemasterResult | null>(null);
  const [visualization, setVisualization] = useState<VisualizationPayload | null>(null);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<import('./api').ErrorDisplay | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [activeMobileTab, setActiveMobileTab] = useState<
    'upload' | 'logs' | 'result'
  >('upload');

  React.useLayoutEffect(() => {
    const savedTheme = window.localStorage.getItem('midi-remaster-theme');
    const nextTheme = savedTheme === 'light' || savedTheme === 'dark' ? savedTheme : 'dark';
    document.documentElement.dataset.theme = nextTheme;
    setTheme(nextTheme);
  }, []);

  const toggleTheme = () => {
    setTheme(previous => {
      const next = previous === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      window.localStorage.setItem('midi-remaster-theme', next);
      return next;
    });
  };

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
        if (typeof data.ml_reason === 'string' || typeof data.reason === 'string') {
          setMlUnavailableReason(data.ml_reason ?? data.reason ?? '');
        }
        if (typeof data.recommended_action === 'string') {
          setMlRecommendedAction(data.recommended_action);
        }
        if (typeof data.torch_error === 'string') {
          setTorchError(data.torch_error);
        }
        if (typeof data.audiocraft_error === 'string') {
          setAudiocraftError(data.audiocraft_error);
        }
        if (Array.isArray(data.ml_available_styles)) {
          setMlAvailableSoundfonts(data.ml_available_styles);
        }
        if (typeof data.max_upload_bytes === 'number' && data.max_upload_bytes > 0) {
          setMaxUploadBytes(data.max_upload_bytes);
        }
      })
      .catch(() => {
        setMlUnavailableReason(`Backend health could not be reached at ${API_BASE}. Start the backend and try again.`);
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
      setAnalysis(null);
      setChannelOverrides({});
      setResult(null);
      setVisualization(null);
      setPlaybackTime(0);
      setError(null);
      setLogs([]);
      addLog(`Selected file: ${e.target.files[0].name}`, 'info');
    }
  };

  const initializeOverrides = useCallback((data: AdvancedAnalysisResult) => {
    const initial: Record<string, ChannelOverride> = {};
    for (const channel of data.channels) {
      initial[String(channel.channel)] = getChannelDefaultOverride(channel);
    }
    setChannelOverrides(initial);
  }, []);

  const handleAnalyze = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setLogs([]);

    try {
      addLog(
        `Advanced baseline analysis | Soundfont: ${soundfont.toUpperCase()}`,
        'info',
        'analyze',
      );
      const formData = new FormData();
      formData.append('file', file);
      formData.append('soundfont', soundfont);
      if (sourceStyle) {
        formData.append('source_style', sourceStyle);
      }

      const data = await request<
        AdvancedAnalysisResult & {
          logs?: Array<{ ts?: string; level?: string; step?: string; message?: string; debug?: string }>;
        }
      >('/api/remaster/analyze', {
        method: 'POST',
        body: formData,
        timeoutMs: 120000,
      });

      setAnalysis(data);
      initializeOverrides(data);
      addLog('Advanced editor ready.', 'success', 'analyze');
      if (Array.isArray(data.logs)) {
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
      }
    } catch (err) {
      const display = toErrorDisplay(err);
      setError(display);
      addLog(display.detail, 'error', 'analyze', display.debug);
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async () => {
    if (!file && (mode === 'baseline' || mlPromptMode === 'audio')) return;
    if (mode === 'baseline' && advancedEnabled && !analysis) {
      await handleAnalyze();
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    setVisualization(null);
    setPlaybackTime(0);
    setLogs([]);

    try {
      const endpoint = mode === 'ml' ? '/api/remaster_ml' : '/api/remaster';
      addLog(
        `Mode: ${mode.toUpperCase()} | Soundfont: ${soundfont.toUpperCase()}`,
        'info',
        'upload',
      );
      addLog('Starting upload...', 'info', 'upload');

      const formData = new FormData();
      formData.append('soundfont', soundfont);
      if (sourceStyle) {
        formData.append('source_style', sourceStyle);
      }
      if (mode === 'ml') {
        formData.append('prompt_mode', mlPromptMode);
        formData.append('duration', String(mlDuration));
      }
      if (mode === 'baseline' && advancedEnabled && analysis) {
        formData.append('request_id', analysis.request_id);
        formData.append('channel_overrides', JSON.stringify(channelOverrides));
      } else if (file) {
        formData.append('file', file);
      }
      if (mode === 'ml' && description.trim()) {
        formData.append('description', description.trim());
      }

      addLog(
        mode === 'ml' && mlPromptMode === 'text'
          ? 'Sending text prompt to backend...'
          : 'Uploading file to backend...',
        'info',
        'upload',
      );

      const timeoutMs = mode === 'ml' ? 1800000 : 300000;
      // Debug logging: log request details
      console.log('[Remaster] Starting request:', {
        endpoint,
        mode,
        soundfont,
        fileSize: file?.size ?? 0,
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

      // Ensure required fields exist before setting result
      if (!data.request_id) {
        console.error('[Remaster] Response missing request_id:', data);
        throw new Error('Invalid response: missing request_id');
      }

      setResult(data);
      setVisualization(data.visualization ?? null);
      if (mode === 'baseline' && !data.visualization) {
        addLog(
          data.visualization_error ?? 'Baseline response did not include remapped MIDI visualization.',
          'error',
          'visualize',
        );
      }
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
      // Debug logging: log error details
      console.error('[Remaster] Request failed:', err);
      if (err instanceof Error) {
        console.error('[Remaster] Error stack:', err.stack);
      }
      const display = toErrorDisplay(err);
      console.log('[Remaster] Error display:', display);
      setError(display);
      addLog(display.detail, 'error', undefined, display.debug);
    } finally {
      setLoading(false);
    }
  };

  const resolveUrl = useCallback((url?: string | null) => {
    if (!url) return undefined;
    return url.startsWith('http') ? url : `${API_BASE}${url}`;
  }, []);

  return (
    <div className={`app app--${theme}`}>
      <header className="app-header">
        <div className="brand-stack">
          <div className="brand-kicker">Audio workspace</div>
          <h1>MIDI Remaster Lab</h1>
          <p>Make your soundtrack playable again.</p>
        </div>
        <div className="header-actions">
          <div className="header-console">
            <span className={`status-dot ${mlAvailable ? 'status-dot--active' : ''}`} />
            {mlAvailable ? 'Baseline + ML ready' : 'Baseline ready · ML unavailable'}
          </div>
          <button type="button" className="theme-toggle" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
            {theme === 'dark' ? '☼ Light' : '☾ Dark'}
          </button>
        </div>
      </header>

      <div className="app-content">
        <main
          className={`app-main ${mode === 'baseline' && advancedEnabled && analysis ? 'app-main--advanced-desktop' : ''}`}
        >
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
        <section className="app-main__top-grid">
          <div
            className={`app-main__panel-wrap app-main__upload ${activeMobileTab === 'upload' ? 'app-main__panel-wrap--visible' : ''}`}
            data-panel="upload"
          >
              <UploadPanel
                file={file}
            soundfont={soundfont}
            mode={mode}
            mlPromptMode={mlPromptMode}
            mlDuration={mlDuration}
            advancedEnabled={advancedEnabled}
            advancedReady={Boolean(analysis)}
            description={description}
            loading={loading}
            primaryActionLabel={
              mode === 'baseline' && advancedEnabled
                ? analysis
                  ? 'Generate from edits'
                  : 'Analyze MIDI'
                : 'Remaster'
            }
            mlAvailableSoundfonts={mlAvailableSoundfonts}
            mlAvailable={mlAvailable}
            mlUnavailableReason={mlUnavailableReason}
            mlRecommendedAction={mlRecommendedAction}
            torchError={torchError}
            audiocraftError={audiocraftError}
            maxUploadBytes={maxUploadBytes}
            onFileChange={handleFileChange}
            onUpload={handleUpload}
            onModeChange={nextMode => {
              setMode(nextMode);
              if (nextMode !== 'baseline') {
                setAdvancedEnabled(false);
                setAnalysis(null);
                setChannelOverrides({});
              }
            }}
            onMlPromptModeChange={setMlPromptMode}
            onMlDurationChange={setMlDuration}
            onSoundfontChange={nextSoundfont => {
              setSoundfont(nextSoundfont);
              setVisualization(null);
              setAnalysis(null);
              setChannelOverrides({});
            }}
            onDescriptionChange={setDescription}
            onAdvancedToggle={value => {
              setAdvancedEnabled(value);
              if (!value) {
                setAnalysis(null);
                setChannelOverrides({});
              }
            }}
            />
          </div>
          <div
            className={`app-main__panel-wrap app-main__logs ${activeMobileTab === 'logs' ? 'app-main__panel-wrap--visible' : ''}`}
            data-panel="logs"
          >
            <LogsPanel logs={logs} />
          </div>
          <div
            className={`app-main__panel-wrap app-main__result ${activeMobileTab === 'result' ? 'app-main__panel-wrap--visible' : ''}`}
            data-panel="result"
          >
            <ResultPanel
              error={error}
              result={result}
              loading={loading}
              resolveUrl={resolveUrl}
              onPlaybackTimeChange={setPlaybackTime}
            />
          </div>
        </section>
        <section className="app-main__visualizer-row remapped-visualizer-row">
          {result?.visualization ? (
            <SoundfontVisualizerPanel
              visualization={result.visualization}
              readOnly
              playbackTime={playbackTime}
            />
          ) : result ? (
            <p className="remapped-visualizer-placeholder">
              {result.visualization_error ?? 'No remapped MIDI visualization was returned.'}
            </p>
          ) : (
            <p className="remapped-visualizer-placeholder">
              Remapped channel visualization will appear after remastering.
            </p>
          )}
        </section>
        </main>
      </div>

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
