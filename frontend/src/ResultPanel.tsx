import React, { useEffect, useMemo, useState } from 'react';

import { head } from './api';

export interface ProvenanceMetadata {
  input_filename?: string;
  mode?: string;
  style?: string;
  timestamp?: string;
  tool_versions?: Record<string, string>;
  checkpoint?: string | null;
  fallback_to_base?: boolean;
}

export interface RemasterResult {
  request_id: string;
  midi_url?: string;
  audio_url?: string;
  audio_url_alt?: string;
  audio_error?: string;
  soundfont?: string;
  prompt_soundfont?: string;
  method?: string;
  description?: string;
  metadata_url?: string;
  metadata?: ProvenanceMetadata;
  classifications?: {
    [channel: string]: {
      program: number;
      name: string;
    };
  };
}

export interface ResultPanelProps {
  error: import('./api').ErrorDisplay | null;
  result: RemasterResult | null;
  loading?: boolean;
  resolveUrl: (url?: string | null) => string | undefined;
}

const ClassificationsList = React.memo<{
  classifications: RemasterResult['classifications'];
}>(({ classifications }) => {
  const entries = useMemo(
    () => Object.entries(classifications || {}),
    [classifications],
  );
  return (
    <div className="result-section result-section--mapping">
      <div className="section-header">
        <h3>Channel mapping</h3>
      </div>
      <ul className="classifications">
        {entries.map(([ch, info]) => (
          <li key={ch}>
            <strong>Channel {ch}:</strong> {info.name} (Program{' '}
            {info.program})
          </li>
        ))}
      </ul>
    </div>
  );
});

ClassificationsList.displayName = 'ClassificationsList';

export function ResultPanel({
  error,
  result,
  loading = false,
  resolveUrl,
}: ResultPanelProps) {
  const [audioSourceIndex, setAudioSourceIndex] = useState<0 | 1>(0);
  const [audioUnavailable, setAudioUnavailable] = useState(false);
  const [midiUnavailable, setMidiUnavailable] = useState(false);
  const [provenanceOpen, setProvenanceOpen] = useState(false);

  const audioUrls = [
    result?.audio_url,
    result?.audio_url_alt,
  ].filter(Boolean) as string[];
  const hasAB = audioUrls.length >= 2;
  const activeAudioUrl = hasAB ? audioUrls[audioSourceIndex] : audioUrls[0];
  const resolvedAudio = activeAudioUrl ? resolveUrl(activeAudioUrl) : undefined;
  const resolvedMidi = result?.midi_url ? resolveUrl(result.midi_url) : undefined;

  // Reset unavailable state when result changes
  useEffect(() => {
    if (!result) return;
    setAudioUnavailable(false);
    setMidiUnavailable(false);
  }, [result?.request_id]);

  // HEAD check for MIDI when we have a URL (detect expired/deleted)
  useEffect(() => {
    if (!resolvedMidi) return;
    let cancelled = false;
    const controller = new AbortController();
    head(resolvedMidi, { signal: controller.signal })
      .then(ok => {
        if (!cancelled && !ok) setMidiUnavailable(true);
      })
      .catch(() => {
        if (!cancelled) setMidiUnavailable(true);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [resolvedMidi]);

  // When switching A/B or new result, reset audio error state
  useEffect(() => {
    setAudioUnavailable(false);
  }, [resolvedAudio]);

  const handleAudioError = () => setAudioUnavailable(true);

  const canPlayAudio = Boolean(
    result?.audio_url && !result?.audio_error && resolvedAudio && !audioUnavailable,
  );
  const canDownloadMidi = Boolean(resolvedMidi && !midiUnavailable);
  const canDownloadAudio = canPlayAudio;

  const status = error
    ? 'error'
    : result
      ? 'complete'
      : loading
        ? 'processing'
        : 'idle';

  return (
    <section className="panel">
      <div className="panel-heading-row">
        <h2>Result</h2>
        <span
          className={`panel-status panel-status--${status}`}
          aria-live="polite"
        >
          {status === 'error'
            ? 'Error'
            : status === 'complete'
              ? 'Complete'
              : status === 'processing'
                ? 'Processing…'
                : 'Idle'}
        </span>
      </div>
      {error && (
        <div className="error-block">
          <p className="error-block__headline">{error.headline}</p>
          <p className="error-block__next">{error.nextStep}</p>
          <details className="error-block__details">
            <summary>Details</summary>
            <div className="error-block__body">
              <p className="error-block__detail">{error.detail}</p>
              {error.debug != null && error.debug !== '' && (
                <pre className="error-block__debug">{error.debug}</pre>
              )}
            </div>
          </details>
        </div>
      )}
      {result && (
        <>
          <div className="result-section result-section--play">
            <div className="section-header">
              <h3>Play & download</h3>
            </div>
            <p className="hint hint--downloads">
              Preview and save the remastered MIDI and rendered audio.
            </p>
            {result.audio_url && !result.audio_error && (
              <div className="result-audio-block">
                {hasAB && (
                  <div className="a-b-toggle" role="tablist" aria-label="Audio source">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={audioSourceIndex === 0}
                      className={'a-b-toggle__btn' + (audioSourceIndex === 0 ? ' a-b-toggle__btn--active' : '')}
                      onClick={() => setAudioSourceIndex(0)}
                    >
                      A
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={audioSourceIndex === 1}
                      className={'a-b-toggle__btn' + (audioSourceIndex === 1 ? ' a-b-toggle__btn--active' : '')}
                      onClick={() => setAudioSourceIndex(1)}
                    >
                      B
                    </button>
                  </div>
                )}
                {audioUnavailable ? (
                  <p className="hint warning">Audio file expired or unavailable.</p>
                ) : (
                  <audio
                    className="result-audio"
                    controls
                    src={resolvedAudio}
                    onError={handleAudioError}
                  >
                    Your browser does not support the audio element.
                  </audio>
                )}
              </div>
            )}
            <div className="downloads">
              {result.midi_url && (
                <>
                  {midiUnavailable ? (
                    <span className="button secondary secondary--disabled">
                      Download MIDI (unavailable)
                    </span>
                  ) : (
                    <a
                      href={resolvedMidi}
                      className="button secondary"
                      download
                      aria-disabled={!canDownloadMidi}
                      title="Save the remapped MIDI file (same notes, new instrument assignments)."
                    >
                      Download MIDI
                    </a>
                  )}
                </>
              )}
              {result.audio_url && !result.audio_error && (
                <>
                  {!canDownloadAudio ? (
                    <span className="button secondary secondary--disabled">
                      Download MP3 {audioUnavailable ? '(unavailable)' : ''}
                    </span>
                  ) : (
                    <a
                      href={resolvedAudio}
                      className="button secondary"
                      download
                      title="Save the rendered audio (MP3) of this remaster."
                    >
                      Download MP3
                    </a>
                  )}
                </>
              )}
            </div>
            {result.audio_error && (
              <p className="warning">
                Audio not available: {result.audio_error}
              </p>
            )}
          </div>

          <div className="result-section result-section--details">
            <div className="section-header">
              <h3>Details</h3>
            </div>
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
          </div>

          {(result.metadata_url ?? result.metadata) && (
            <div className="result-section result-section--provenance">
              <div className="provenance">
              <button
                type="button"
                className="provenance__toggle"
                onClick={() => setProvenanceOpen(prev => !prev)}
                aria-expanded={provenanceOpen}
              >
                {provenanceOpen ? '▼' : '▶'} Provenance
              </button>
              {provenanceOpen && (
                <div className="provenance__body">
                  {result.metadata && (
                    <dl className="provenance__meta">
                      {result.metadata.input_filename != null && (
                        <>
                          <dt>Input</dt>
                          <dd>{result.metadata.input_filename}</dd>
                        </>
                      )}
                      {result.metadata.mode != null && (
                        <>
                          <dt>Mode</dt>
                          <dd>{result.metadata.mode}</dd>
                        </>
                      )}
                      {result.metadata.style != null && (
                        <>
                          <dt>Style</dt>
                          <dd>{result.metadata.style}</dd>
                        </>
                      )}
                      {result.metadata.timestamp != null && (
                        <>
                          <dt>Timestamp</dt>
                          <dd>{result.metadata.timestamp}</dd>
                        </>
                      )}
                      {result.metadata.tool_versions && Object.keys(result.metadata.tool_versions).length > 0 && (
                        <>
                          <dt>Tool versions</dt>
                          <dd>
                            <ul className="provenance__tools">
                              {Object.entries(result.metadata.tool_versions).map(([k, v]) => (
                                <li key={k}>{k}: {String(v ?? '')}</li>
                              ))}
                            </ul>
                          </dd>
                        </>
                      )}
                      {result.metadata.checkpoint != null && (
                        <>
                          <dt>Checkpoint</dt>
                          <dd>{result.metadata.checkpoint}</dd>
                        </>
                      )}
                      {result.metadata.fallback_to_base != null && (
                        <>
                          <dt>Fallback to base</dt>
                          <dd>{String(result.metadata.fallback_to_base)}</dd>
                        </>
                      )}
                    </dl>
                  )}
                  {result.metadata_url && (
                    <a
                      href={resolveUrl(result.metadata_url)}
                      className="button secondary provenance__download"
                      download="metadata.json"
                      title="Save run metadata (input, mode, style, tool versions) for reproducibility."
                    >
                      Download metadata.json
                    </a>
                  )}
                </div>
              )}
              </div>
            </div>
          )}
          {result.classifications && (
            <ClassificationsList classifications={result.classifications} />
          )}
        </>
      )}
      {!error && !result && !loading && (
        <p className="hint result-idle">
          Choose a MIDI file and tap Remaster to see your result here.
        </p>
      )}
      {!error && !result && loading && (
        <p className="hint result-idle">
          Remastering… Your result will appear here when complete.
        </p>
      )}
    </section>
  );
}
