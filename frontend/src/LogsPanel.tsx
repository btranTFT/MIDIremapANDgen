import React, { useEffect, useMemo, useRef, useState } from 'react';

export type LogLevel = 'info' | 'warn' | 'error';

export interface LogEntry {
  timestamp?: string;
  ts?: string;
  message: string;
  type?: 'info' | 'success' | 'error' | 'warning';
  level?: LogLevel;
  step?: string;
  debug?: string;
}

export interface LogsPanelProps {
  logs: LogEntry[];
}

function formatLogTime(entry: LogEntry): string {
  const raw = entry.ts ?? entry.timestamp;
  if (!raw) return '';
  if (raw.includes('T') && raw.endsWith('Z')) {
    try {
      const d = new Date(raw);
      return d.toLocaleTimeString();
    } catch {
      return raw;
    }
  }
  return raw;
}

function logLevel(entry: LogEntry): LogLevel {
  if (entry.level) return entry.level;
  switch (entry.type) {
    case 'error': return 'error';
    case 'warning': return 'warn';
    case 'success':
    case 'info':
    default: return 'info';
  }
}

function logCssType(entry: LogEntry): string {
  const level = logLevel(entry);
  if (level === 'error') return 'error';
  if (level === 'warn') return 'warning';
  return 'info';
}

const LogItem = React.memo<{
  level: LogLevel;
  time: string;
  title?: string;
  step?: string;
  message: string;
}>(({ level, time, title, step, message }) => {
  return (
    <div className={`log log-${level === 'error' ? 'error' : level === 'warn' ? 'warning' : 'info'}`} title={title}>
      <span className="log-time">[{time || '—'}]</span>
      <span className={`log-badge log-badge--${level}`}>{level}</span>
      {step && <span className="log-step">{step}</span>}
      <span className="log-msg">{message}</span>
    </div>
  );
});

LogItem.displayName = 'LogItem';

export const LogsPanel = React.memo(function LogsPanel({ logs }: LogsPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const copyLogs = () => {
    const text = logs
      .map(log => {
        const t = formatLogTime(log);
        const lvl = logLevel(log);
        const step = log.step ? ` [${log.step}]` : '';
        const line = `${t} ${lvl}${step} ${log.message}`;
        return log.debug ? `${line}\n  debug: ${log.debug}` : line;
      })
      .join('\n');
    void navigator.clipboard.writeText(text || 'No logs.');
  };

  return (
    <section className="panel">
      <h2>Logs</h2>
      <div className="logs-toolbar">
        <label className="logs-toolbar__autoscroll">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={e => setAutoScroll(e.target.checked)}
          />
          <span>Auto-scroll</span>
        </label>
        <button type="button" className="logs-toolbar__copy" onClick={copyLogs}>
          Copy logs
        </button>
      </div>
      <div className="logs logs-body" ref={containerRef}>
        {logs.map((log, i) => {
          const level = logLevel(log);
          const time = formatLogTime(log);
          const title = log.debug ? `${log.message}\n\nDebug: ${log.debug}` : undefined;
          // Use stable key: ts if available, otherwise index (for initial logs without ts)
          const key = log.ts ?? log.timestamp ?? `log-${i}`;
          return (
            <LogItem
              key={key}
              level={level}
              time={time}
              title={title}
              step={log.step}
              message={log.message}
            />
          );
        })}
        {logs.length === 0 && <p className="hint">No logs yet.</p>}
      </div>
    </section>
  );
});
