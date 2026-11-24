import React, { useCallback, useState } from 'react';

import { API_BASE, pollMlJob, request, toErrorDisplay, type MlJobStatus, type MlJobSubmission } from './api';
import {
  getChannelDefaultOverride,
  type AdvancedAnalysisResult,
  type ChannelOverride,
} from './AdvancedBaselinePanel';
import { LogsPanel } from './LogsPanel';
import type { LogEntry } from './LogsPanel';
import type { RemasterResult } from './ResultPanel';
import { ResultPanel } from './ResultPanel';
import { SoundfontVisualizerPanel } from './SoundfontVisualizerPanel';
import {
  UploadPanel,
  type MlPromptMode,
  type RemasterMode,
  type SoundfontId,
} from './UploadPanel';
import './workstation.css';

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
  const [playbackTime, setPlaybackTime] = useState(0);
  const [loading, setLoading] = useState(false);
  const [applyingMidi, setApplyingMidi] = useState(false);
  const [mlJob, setMlJob] = useState<MlJobStatus | null>(null);
  const mlPolling = React.useRef<AbortController | null>(null);
  const mlSubmitting = React.useRef(false);
  const [error, setError] = useState<import('./api').ErrorDisplay | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');

  React.useEffect(() => () => {
    mlPolling.current?.abort();
  }, []);

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
    if (mode === 'ml' && mlSubmitting.current) return;
    if (!file && (mode === 'baseline' || mlPromptMode === 'audio')) return;
    if (mode === 'baseline' && advancedEnabled && !analysis) {
      await handleAnalyze();
      return;
    }
    mlPolling.current?.abort();
    const controller = mode === 'ml' ? new AbortController() : null;
    mlPolling.current = controller;
    if (controller) mlSubmitting.current = true;
    setMlJob(null);
    setLoading(true);
    setError(null);
    setResult(null);
    setPlaybackTime(0);
    setLogs([]);

    try {
      const endpoint = mode === 'ml' ? '/api/remaster_ml/jobs' : '/api/remaster';
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

      type ResultWithLogs =
        RemasterResult & {
          logs?: Array<{
            ts?: string;
            level?: string;
            step?: string;
            message?: string;
            debug?: string;
          }>;
        };
      let data: ResultWithLogs;
      if (controller) {
        const submission = await request<MlJobSubmission>(endpoint, {
          method: 'POST', body: formData, timeoutMs: 120000, signal: controller.signal,
        });
        if (!submission.job_id) throw new Error('Invalid response: missing job_id');
        if (controller.signal.aborted) return;
        setMlJob({ job_id: submission.job_id, status: 'queued', stage: 'validating', progress: 0,
          message: 'Queued for generation', error: null, result: null });
        data = await pollMlJob(submission.job_id, controller.signal, setMlJob);
      } else {
        data = await request<ResultWithLogs>(endpoint, { method: 'POST', body: formData, timeoutMs });
      }

      // Ensure required fields exist before setting result
      if (!data.request_id) {
        console.error('[Remaster] Response missing request_id:', data);
        throw new Error('Invalid response: missing request_id');
      }

      setResult(data);
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
      if (controller?.signal.aborted) return;
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
      if (!controller || mlPolling.current === controller) {
        if (controller) {
          mlPolling.current = null;
          mlSubmitting.current = false;
        }
        if (!controller?.signal.aborted) setLoading(false);
      }
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
          <h1>MIDI Remaster Lab</h1>
        </div>
        <div className="header-actions">
          <span className="toolbar-context"><span>Mode</span> <strong>{mode === 'baseline' ? 'Baseline' : 'MusicGen'}</strong></span>
          <span className="toolbar-context"><span>Soundfont</span> <strong>{soundfont.toUpperCase()}</strong></span>
          <div className="header-console">
            <span className={`status-dot ${mlAvailable ? 'status-dot--active' : ''}`} />
            {mlAvailable ? 'Baseline + ML ready' : 'Baseline ready · ML unavailable'}
          </div>
          <button type="button" className="theme-toggle" onClick={toggleTheme} aria-pressed={theme === 'dark'} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
            Theme: {theme === 'dark' ? 'Dark' : 'Light'}
          </button>
        </div>
      </header>

      <div className="app-content">
        <main
          className={`app-main ${mode === 'baseline' && advancedEnabled && analysis ? 'app-main--advanced-desktop' : ''}`}
        >
        <section className="app-main__top-grid">
          <div className="app-main__panel-wrap app-main__upload" data-panel="upload">
              <UploadPanel
                file={file}
            soundfont={soundfont}
            mode={mode}
            mlPromptMode={mlPromptMode}
            mlDuration={mlDuration}
            advancedEnabled={advancedEnabled}
            advancedReady={Boolean(analysis)}
            description={description}
            loading={loading || applyingMidi}
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
          <details className="app-main__logs" data-panel="logs">
            <summary>Logs <span>{logs.length}</span></summary>
            <LogsPanel logs={logs} />
          </details>
        </section>
        <section className="app-main__visualizer-row remapped-visualizer-row">
          {result?.visualization ? (
            <SoundfontVisualizerPanel
              key={`${result.request_id}:${result.midi_url ?? ''}:${soundfont}`}
              visualization={result.visualization}
              readOnly={!result.midi_url || result.method === 'musicgen_ml' || result.metadata?.mode === 'ml' || (result.soundfont ?? result.metadata?.style ?? '').toLowerCase() !== soundfont}
              requestId={result.request_id}
              onApplyingChange={setApplyingMidi}
              onEdited={edited => {
                setResult(edited);
                setPlaybackTime(0);
                setError(null);
                if (Array.isArray(edited.logs)) {
                  setLogs(previous => [...previous, ...edited.logs!.filter(event => typeof event.message === 'string').map(event => ({
                    ts: event.ts ?? '', message: event.message ?? 'Unknown message',
                    level: (event.level === 'warn' ? 'warn' : event.level === 'error' ? 'error' : 'info') as LogEntry['level'],
                    step: event.step ?? '', debug: event.debug,
                  }))]);
                }
                if (edited.audio_error) addLog(`Audio warning: ${edited.audio_error}`, 'warning', 'encode');
              }}
              playbackTime={playbackTime}
            />
          ) : result?.method === 'musicgen_ml' || result?.metadata?.mode === 'ml' ? (
            <div className="remapped-visualizer-placeholder remapped-visualizer-placeholder--ml">
              <span className="eyebrow">Generated output</span>
              <h2>{result.prompt_mode === 'audio' ? 'Generated audio · MIDI-conditioned' : 'Generated audio'}</h2>
              {result.prompt_mode === 'audio' ? (
                <p>
                  The uploaded MIDI was rendered and used as an audio conditioning prompt.
                  MusicGen generated new audio, but did not produce a MIDI channel map.
                </p>
              ) : (
                <p>
                  MusicGen generated audio from the text prompt. This output is audio-only and
                  does not include a remapped MIDI channel map.
                </p>
              )}
              <p className="hint">MIDI visualization is unavailable for MusicGen output.</p>
            </div>
          ) : result ? (
            <p className="remapped-visualizer-placeholder">
              {result.visualization_error ?? 'Remapped MIDI visualization is unavailable.'}
            </p>
          ) : (
            <p className="remapped-visualizer-placeholder">
              Remapped MIDI channels will appear after baseline remastering.
            </p>
          )}
        </section>
        <div className="app-main__result" data-panel="result">
          <ResultPanel
            error={error}
            result={result}
            selectedSoundfont={soundfont}
            loading={loading || applyingMidi}
            mlJob={mlJob}
            resolveUrl={resolveUrl}
            onPlaybackTimeChange={setPlaybackTime}
          />
        </div>
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
