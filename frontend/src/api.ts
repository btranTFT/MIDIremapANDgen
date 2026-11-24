/**
 * Central API client: timeout, JSON parse errors, request-id, consistent error shape.
 */

// Read from env var (Vite exposes import.meta.env.VITE_*)
// Default to localhost:8001 for local dev (safe default)
export const API_BASE =
  import.meta.env.VITE_API_BASE ?? 'http://localhost:8001';

import type { RemasterResult } from './ResultPanel';

export interface UpdateNoteOperation {
  type: 'update_note';
  note_id: string;
  pitch?: number;
  velocity?: number;
  start_tick?: number;
  duration_ticks?: number;
}

export interface DeleteNoteOperation {
  type: 'delete_note';
  note_id: string;
}

export interface SetChannelProgramOperation {
  type: 'set_channel_program';
  channel: number;
  program: number;
}

export type NoteEditOperation = UpdateNoteOperation | DeleteNoteOperation | SetChannelProgramOperation;
export interface EditedRemasterResponse extends RemasterResult {
  visualization: import('./SoundfontVisualizerPanel').VisualizationPayload;
  logs?: Array<{ ts?: string; level?: string; step?: string; message?: string; debug?: string }>;
}

export function applyMidiEdits(requestId: string, operations: NoteEditOperation[]): Promise<EditedRemasterResponse> {
  return request<EditedRemasterResponse>(`/api/remaster/${encodeURIComponent(requestId)}/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operations }),
    timeoutMs: 300000,
  });
}

export interface MlJobSubmission {
  job_id: string;
}

export interface MlJobStatus {
  job_id: string;
  status: 'queued' | 'running' | 'complete' | 'failed';
  stage: 'validating' | 'loading_model' | 'rendering_prompt' | 'generating' | 'encoding' | 'complete';
  progress: number;
  message: string;
  error: { detail?: string; code?: string; debug?: string; headline?: string; next_step?: string } | string | null;
  result: (RemasterResult & { logs?: Array<{ ts?: string; level?: string; step?: string; message?: string; debug?: string }> }) | null;
}

export interface ErrorDisplay {
  headline: string;
  nextStep: string;
  detail: string;
  debug?: string;
}

/** Build UX error shape from ApiError or unknown for display in Result panel. */
export function toErrorDisplay(err: unknown): ErrorDisplay {
  const detail =
    err instanceof ApiError ? err.detail ?? err.message : err instanceof Error ? err.message : 'Upload failed';
  if (err instanceof ApiError) {
    const { statusCode, code, headline: backendHeadline, nextStep: backendNextStep } = err;
    let headline = backendHeadline ?? 'Something went wrong';
    let nextStep = backendNextStep ?? 'Try again or check your connection.';
    if (!backendHeadline || !backendNextStep) {
      if (statusCode === 400) {
        if (!backendHeadline) {
          if (code === 'INVALID_EXTENSION') headline = 'Invalid file';
          else if (code === 'INVALID_CONTENT_TYPE') headline = 'Invalid file type';
          else headline = 'Invalid request';
        }
        if (!backendNextStep) {
          if (code === 'INVALID_EXTENSION') nextStep = 'Choose a .mid or .midi file and try again.';
          else if (code === 'INVALID_CONTENT_TYPE') nextStep = 'Use a MIDI file or try another browser.';
          else nextStep = 'Check your input and try again.';
        }
      } else if (statusCode === 401) {
        if (!backendHeadline) headline = 'Not authorized';
        if (!backendNextStep) nextStep = 'Check your credentials or session.';
      } else if (statusCode === 413 || code === 'PAYLOAD_TOO_LARGE') {
        if (!backendHeadline) headline = 'File too large';
        if (!backendNextStep) nextStep = 'Choose a smaller file or check the max size limit.';
      } else if (statusCode === 500) {
        if (!backendHeadline) headline = 'Processing error';
        if (!backendNextStep) nextStep = 'Try again or check the logs.';
      } else if (statusCode === 503) {
        if (!backendHeadline) headline = 'Service unavailable';
        if (!backendNextStep)
          nextStep =
            code === 'ML_UNAVAILABLE' || code === 'CHECKPOINT_NOT_FOUND' || code === 'SOUNDFONT_NOT_FOUND'
              ? 'Use Baseline mode or try again later.'
              : 'Try again in a few moments.';
      }
    }
    return { headline, nextStep, detail, debug: err.debug };
  }
  return { headline: 'Something went wrong', nextStep: 'Try again.', detail };
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly detail?: string,
    public readonly debug?: string,
    public readonly requestId?: string,
    public readonly statusCode?: number,
    public readonly code?: string,
    public readonly headline?: string,
    public readonly nextStep?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function pollMlJob(
  jobId: string,
  signal: AbortSignal,
  onUpdate: (job: MlJobStatus) => void,
): Promise<NonNullable<MlJobStatus['result']>> {
  while (!signal.aborted) {
    let job: MlJobStatus;
    try {
      job = await request<MlJobStatus>(`/api/remaster_ml/jobs/${encodeURIComponent(jobId)}`, {
        signal,
        timeoutMs: 10000,
      });
    } catch (error) {
      if (error instanceof ApiError && error.statusCode === 404) {
        throw new ApiError('The ML job expired before the result was retrieved. Please run it again.');
      }
      throw error;
    }
    if (signal.aborted) throw new DOMException('Polling stopped', 'AbortError');
    onUpdate(job);
    if (job.status === 'complete') {
      if (!job.result) throw new ApiError('The ML job completed without a result.');
      return job.result;
    }
    if (job.status === 'failed') {
      const error = job.error;
      const detail = typeof error === 'string' ? error : error?.detail ?? job.message ?? 'ML generation failed.';
      throw new ApiError(detail, detail, typeof error === 'object' && error ? error.debug : undefined,
        undefined, undefined, typeof error === 'object' && error ? error.code : undefined,
        typeof error === 'object' && error ? error.headline : undefined,
        typeof error === 'object' && error ? error.next_step : undefined);
    }
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        signal.removeEventListener('abort', abort);
        resolve();
      }, 1000);
      const abort = () => {
        clearTimeout(timer);
        reject(new DOMException('Polling stopped', 'AbortError'));
      };
      signal.addEventListener('abort', abort, { once: true });
      if (signal.aborted) abort();
    });
  }
  throw new DOMException('Polling stopped', 'AbortError');
}

function getRequestId(response: Response): string | undefined {
  return (
    response.headers.get('x-request-id') ??
    response.headers.get('request-id') ??
    undefined
  );
}

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

/**
 * Fetch with timeout, JSON response, and consistent error shape.
 * Path is relative to API_BASE unless it starts with "http".
 */
export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { timeoutMs, ...init } = options;
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const controller = new AbortController();
  const abortRequest = () => controller.abort();
  if (init.signal?.aborted) controller.abort();
  else init.signal?.addEventListener('abort', abortRequest, { once: true });
  const timeoutId =
    timeoutMs != null ? setTimeout(() => controller.abort(), timeoutMs) : undefined;

  try {
    const response = await fetch(url, {
      ...init,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    const requestId = getRequestId(response);

    if (!response.ok) {
      let detail = 'Request failed';
      let debug: string | undefined;
      let code: string | undefined;
      let headline: string | undefined;
      let nextStep: string | undefined;
      const contentType = response.headers.get('content-type') || '';
      const isJson = contentType.includes('application/json');
      
      try {
        if (isJson) {
          const err = await response.json();
          if (err.detail)
            detail =
              typeof err.detail === 'string'
                ? err.detail
                : (err.detail?.detail ?? detail);
          if (err.debug) debug = err.debug;
          if (typeof err.code === 'string') code = err.code;
          if (typeof err.headline === 'string') headline = err.headline;
          if (typeof err.next_step === 'string') nextStep = err.next_step;
        } else {
          // Non-JSON error response (HTML, plaintext, etc.)
          const text = await response.text();
          detail = text || `HTTP ${response.status}: ${response.statusText}`;
          console.warn('[API] Non-JSON error response:', { status: response.status, contentType, text: text.substring(0, 200) });
        }
      } catch (parseErr) {
        // Failed to read response body
        console.error('[API] Failed to parse error response:', parseErr);
        detail = `HTTP ${response.status}: ${response.statusText}`;
      }
      throw new ApiError(
        detail,
        detail,
        debug,
        requestId,
        response.status,
        code,
        headline,
        nextStep,
      );
    }

    const contentType = response.headers.get('content-type') || '';
    const isJson = contentType.includes('application/json');
    
    if (!isJson) {
      console.warn('[API] Expected JSON but got:', contentType);
      throw new ApiError(
        `Expected JSON response but received ${contentType}`,
        undefined,
        `Content-Type: ${contentType}`,
        requestId,
        response.status,
        'INVALID_CONTENT_TYPE',
      );
    }

    try {
      const text = await response.text();
      if (!text || text.trim().length === 0) {
        throw new ApiError(
          'Empty response body',
          undefined,
          undefined,
          requestId,
          response.status,
          'EMPTY_RESPONSE',
        );
      }
      const data = JSON.parse(text);
      return data as T;
    } catch (parseErr) {
      console.error('[API] JSON parse error:', parseErr);
      throw new ApiError(
        'Invalid JSON response',
        parseErr instanceof Error ? parseErr.message : 'JSON parse failed',
        undefined,
        requestId,
        response.status,
        'JSON_PARSE_ERROR',
      );
    }
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof ApiError) throw err;
    if (err instanceof Error) {
      if (err.name === 'AbortError')
        throw new ApiError(
          timeoutMs != null && timeoutMs >= 60_000
            ? 'Request timed out (5 min).'
            : 'Request timed out.',
        );
      if (err.message.includes('Failed to fetch'))
        throw new ApiError(`Backend not reachable on ${API_BASE}`);
      throw new ApiError(err.message);
    }
    throw new ApiError('Request failed');
  } finally {
    init.signal?.removeEventListener('abort', abortRequest);
  }
}

export interface HeadOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

/**
 * HEAD request; returns true only when response.ok. Used for availability checks.
 */
export async function head(
  url: string,
  options: HeadOptions = {},
): Promise<boolean> {
  const { timeoutMs = 5000, signal } = options;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  if (signal) {
    signal.addEventListener('abort', () => controller.abort());
  }
  try {
    const response = await fetch(url, {
      method: 'HEAD',
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return response.ok;
  } catch {
    clearTimeout(timeoutId);
    return false;
  }
}
