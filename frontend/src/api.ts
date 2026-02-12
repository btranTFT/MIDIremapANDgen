/**
 * Central API client: timeout, JSON parse errors, request-id, consistent error shape.
 */

// Read from env var (Vite exposes import.meta.env.VITE_*)
// Default to localhost:8001 for local dev (safe default)
export const API_BASE =
  import.meta.env.VITE_API_BASE ?? 'http://localhost:8001';

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
  const timeoutId =
    timeoutMs != null ? setTimeout(() => controller.abort(), timeoutMs) : undefined;

  try {
    const response = await fetch(url, {
      ...init,
      signal: init.signal ?? controller.signal,
    });
    clearTimeout(timeoutId);
    const requestId = getRequestId(response);

    if (!response.ok) {
      let detail = 'Request failed';
      let debug: string | undefined;
      let code: string | undefined;
      let headline: string | undefined;
      let nextStep: string | undefined;
      try {
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
      } catch {
        /* non-JSON or empty body */
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

    try {
      const data = await response.json();
      return data as T;
    } catch {
      throw new ApiError(
        'Invalid JSON response',
        undefined,
        undefined,
        requestId,
        undefined,
        undefined,
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
