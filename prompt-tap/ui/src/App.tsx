import { useCallback, useEffect, useRef, useState } from 'react';

type PromptBubble = {
  role: string;
  content: string;
};

type PromptWarning = {
  request_id: string;
  message: string;
  chunk?: string;
};

type PromptTurnMetadata = {
  model?: string | null;
  status?: string | null;
  duration_ms?: number | null;
  display_path?: string | null;
};

const PROMPT_BUBBLE_ROLE_CLASS_NAMES = new Set([
  'assistant',
  'error',
  'pending',
  'raw',
  'system',
  'tool_call',
  'unknown',
  'user',
]);

function promptBubbleRoleClassName(role: string) {
  return PROMPT_BUBBLE_ROLE_CLASS_NAMES.has(role) ? role : 'unknown';
}

type PromptTurn = {
  request_id: string;
  timestamp?: string | null;
  path?: string | null;
  request?: unknown;
  response?: unknown;
  status?: string;
  metadata?: PromptTurnMetadata;
  warnings?: PromptWarning[];
  bubbles: PromptBubble[];
};

function recordFields(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function textField(value: unknown, fallback: string) {
  return typeof value === 'string' ? value : fallback;
}

function formatJson(value: unknown) {
  if (value === undefined || value === null) {
    return '无记录';
  }

  return JSON.stringify(value, null, 2);
}

function hasRecord(value: unknown) {
  return value !== undefined && value !== null;
}

function truncationLabel(value: unknown, recordAvailable = true) {
  if (!recordAvailable) return '无记录';
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return '未知';
  const truncated = (value as Record<string, unknown>).body_truncated;
  return truncated === true ? 'true' : truncated === false ? 'false' : '未知';
}

function defaultJsonSection(role: string): JsonSectionName {
  return ['assistant', 'tool_call', 'error', 'pending'].includes(role) ? 'response' : 'current';
}

function formatDuration(durationMs: number | null | undefined) {
  if (durationMs === undefined || durationMs === null) {
    return 'Unknown duration';
  }

  return `${durationMs} ms`;
}

type PromptTurnDisplayMetadata = {
  status: string;
  model: string;
  duration: string;
  displayPath: string;
};

function promptTurnDisplayMetadata(turn: PromptTurn): PromptTurnDisplayMetadata {
  const metadata = turn.metadata ?? {};

  return {
    status: metadata.status ?? turn.status ?? 'unknown',
    model: metadata.model ?? 'Unknown model',
    duration: formatDuration(metadata.duration_ms),
    displayPath: metadata.display_path ?? turn.path ?? 'Unknown path',
  };
}

type SelectionKey = {
  requestId: string;
  bubbleIndex: number;
};

type SelectedPromptBubble = {
  turn: PromptTurn;
  bubble: PromptBubble;
  key: SelectionKey;
};

type JsonSectionName = 'current' | 'request' | 'response';
type CopyFeedback = { section: JsonSectionName; message: string; token: number };

type TodayResponse = {
  date: string;
  log_exists: boolean;
  turns: PromptTurn[];
  warnings?: PromptWarning[];
  message: string;
};

type WebConfigResponse = {
  tail_interval_seconds: number;
};

const DEFAULT_TAIL_INTERVAL_SECONDS = 1;

function tailIntervalMs(config: WebConfigResponse | null) {
  const intervalSeconds = config?.tail_interval_seconds ?? DEFAULT_TAIL_INTERVAL_SECONDS;
  if (!Number.isFinite(intervalSeconds) || intervalSeconds <= 0) {
    return DEFAULT_TAIL_INTERVAL_SECONDS * 1000;
  }

  return intervalSeconds * 1000;
}

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; data: TodayResponse }
  | { status: 'error'; message: string };

function PromptBubbleView({
  bubble,
  isSelected,
  onSelect,
}: {
  bubble: PromptBubble;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      aria-pressed={isSelected}
      className={`prompt-bubble prompt-bubble--${promptBubbleRoleClassName(bubble.role)}`}
      type="button"
      onClick={onSelect}
    >
      <span className="bubble-role">{bubble.role}</span>
      <span className="bubble-content">{bubble.content || '未捕获可显示内容。'}</span>
    </button>
  );
}

function PromptTurnView({
  selectedBubble,
  turn,
  onSelectBubble,
}: {
  selectedBubble: SelectedPromptBubble | null;
  turn: PromptTurn;
  onSelectBubble: (selection: SelectedPromptBubble) => void;
}) {
  const displayMetadata = promptTurnDisplayMetadata(turn);

  return (
    <li className={`prompt-turn prompt-turn--${displayMetadata.status}`}>
      <div className="turn-meta">
        <span>{turn.timestamp ?? 'Unknown time'}</span>
        <span>model: {displayMetadata.model}</span>
        <span>status: {displayMetadata.status}</span>
        <span>duration: {displayMetadata.duration}</span>
        <span>path: {displayMetadata.displayPath}</span>
        <span>{turn.request_id}</span>
      </div>
      <div className="bubble-stack">
        {turn.bubbles.length > 0 ? (
          turn.bubbles.map((bubble, index) => (
            <PromptBubbleView
              key={`${turn.request_id}-${index}`}
              bubble={bubble}
              isSelected={selectedBubble?.key.requestId === turn.request_id && selectedBubble.key.bubbleIndex === index}
              onSelect={() => onSelectBubble({ turn, bubble, key: { requestId: turn.request_id, bubbleIndex: index } })}
            />
          ))
        ) : (
          <p className="empty-turn">No Prompt Bubble could be extracted.</p>
        )}
      </div>
    </li>
  );
}

function WarningPanel({ warnings }: { warnings: PromptWarning[] }) {
  if (warnings.length === 0) {
    return null;
  }

  return (
    <aside className="warning-panel" aria-label="Prompt Log warnings">
      <h3>Warnings</h3>
      <ul>
        {warnings.map((warning, index) => (
          <li key={`${warning.request_id}-${index}`}>
            <strong>{warning.request_id}</strong>: {warning.message}
            {warning.chunk ? <code>{warning.chunk}</code> : null}
          </li>
        ))}
      </ul>
    </aside>
  );
}

function PromptBubbleDetails({ selection, onClose }: { selection: SelectedPromptBubble | null; onClose: () => void }) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const previousSelectionKey = useRef<string | null>(null);
  const [openSections, setOpenSections] = useState<Record<JsonSectionName, boolean>>({ current: true, request: false, response: false });
  const [feedback, setFeedback] = useState<CopyFeedback | null>(null);
  const feedbackToken = useRef(0);

  useEffect(() => {
    if (!selection) {
      previousSelectionKey.current = null;
      return;
    }
    const key = `${selection.key.requestId}:${selection.key.bubbleIndex}`;
    if (previousSelectionKey.current !== key) {
      closeButton.current?.focus();
      previousSelectionKey.current = key;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selection, onClose]);

  const selectionFingerprint = selection ? JSON.stringify({ key: selection.key, bubble: selection.bubble, request: selection.turn.request, response: selection.turn.response }) : null;

  useEffect(() => {
    setFeedback(null);
    feedbackToken.current += 1;
  }, [selectionFingerprint]);

  const responseAvailable = hasRecord(selection?.turn.response);
  useEffect(() => {
    const defaultSection = responseAvailable ? defaultJsonSection(selection?.bubble.role ?? 'unknown') : 'current';
    setOpenSections({ current: defaultSection === 'current', request: false, response: defaultSection === 'response' });
  }, [selection?.key.requestId, selection?.key.bubbleIndex, selection?.bubble.role, responseAvailable]);

  if (!selection) return null;

  const displayMetadata = promptTurnDisplayMetadata(selection.turn);
  const request = recordFields(selection.turn.request);
  const response = selection.turn.response;
  const values: Record<JsonSectionName, unknown> = {
    current: selection.bubble,
    request: selection.turn.request,
    response: response,
  };
  const available: Record<JsonSectionName, boolean> = {
    current: true,
    request: hasRecord(selection.turn.request),
    response: hasRecord(response),
  };
  const labels: Record<JsonSectionName, string> = {
    current: 'Current Bubble JSON',
    request: 'Request JSON',
    response: 'Response JSON',
  };

  async function copySection(section: JsonSectionName) {
    if (!available[section] || !window.navigator.clipboard?.writeText) {
      setFeedback({ section, message: '复制不可用，请使用 HTTPS 或 localhost，或选中 JSON 手动复制。', token: ++feedbackToken.current });
      return;
    }
    const token = ++feedbackToken.current;
    try {
      await globalThis.navigator.clipboard.writeText(formatJson(values[section]));
      if (feedbackToken.current === token) setFeedback({ section, message: '已复制', token });
    } catch {
      if (feedbackToken.current === token) setFeedback({ section, message: '复制失败，请检查浏览器权限或选中 JSON 手动复制。', token });
    }
  }

  return (
    <aside className="bubble-details" aria-label="Prompt Bubble 详情">
      <header className="drawer-header">
        <h3>Prompt Bubble 详情</h3>
        <button ref={closeButton} type="button" onClick={onClose}>关闭详情</button>
      </header>
      <dl className="drawer-metadata">
        <div><dt>Role</dt><dd>{selection.bubble.role}</dd></div>
        <div><dt>Request ID</dt><dd>{selection.turn.request_id}</dd></div>
        <div><dt>Status</dt><dd>{displayMetadata.status}</dd></div>
        <div><dt>Model</dt><dd>{displayMetadata.model}</dd></div>
        <div><dt>Duration</dt><dd>{displayMetadata.duration}</dd></div>
        <div><dt>Timestamp</dt><dd>{textField(request.timestamp, selection.turn.timestamp ?? '未知')}</dd></div>
        <div><dt>Method</dt><dd>{textField(request.method, '未知')}</dd></div>
        <div><dt>Full Path</dt><dd>{textField(request.path, selection.turn.path ?? '未知')}</dd></div>
        <div><dt>Content</dt><dd>{selection.bubble.content || '未捕获可显示内容。'}</dd></div>
      </dl>
      <section aria-label="Safe Request Headers">
        <h4>Safe Request Headers</h4>
        <pre tabIndex={0}>{formatJson(request.headers)}</pre>
      </section>
      {(Object.keys(labels) as JsonSectionName[]).map((section) => (
        <div key={section}>
          {section === 'request' || section === 'response' ? <p className="truncation-info" data-truncated={truncationLabel(values[section], available[section]) === 'true' ? 'true' : undefined}>{section === 'request' ? 'Request' : 'Response'} body_truncated: {truncationLabel(values[section], available[section])}</p> : null}
          <details className="json-section" open={openSections[section]}>
            <summary onClick={(event) => { event.preventDefault(); setOpenSections((current) => ({ ...current, [section]: !current[section] })); }}>{labels[section]}</summary>
            <div className="json-actions">
              <button type="button" disabled={!available[section]} onClick={() => void copySection(section)}>复制 {labels[section]}</button>
              {feedback?.section === section ? <span className="copy-feedback" role="status">{feedback.message}</span> : null}
            </div>
            <pre aria-label={labels[section]} tabIndex={0}>{formatJson(values[section])}</pre>
          </details>
        </div>
      ))}
    </aside>
  );
}

export function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [selectedBubble, setSelectedBubble] = useState<SelectedPromptBubble | null>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const closeDetails = useCallback(() => {
    setSelectedBubble(null);
    trigger.current?.focus();
  }, []);

  function selectBubble(selection: SelectedPromptBubble) {
    trigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSelectedBubble(selection);
  }

  useEffect(() => {
    if (state.status === 'ready' && selectedBubble) {
      const turn = state.data.turns.find((candidate) => candidate.request_id === selectedBubble.key.requestId);
      if (!turn || !turn.bubbles[selectedBubble.key.bubbleIndex]) {
        setSelectedBubble(null);
      } else if (turn !== selectedBubble.turn || turn.bubbles[selectedBubble.key.bubbleIndex] !== selectedBubble.bubble) {
        setSelectedBubble({ turn, bubble: turn.bubbles[selectedBubble.key.bubbleIndex], key: selectedBubble.key });
      }
    }
  }, [state, selectedBubble]);

  useEffect(() => {
    let cancelled = false;

    function loadToday() {
      fetch('/api/today')
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Today API returned ${response.status}`);
          }
          return response.json() as Promise<TodayResponse>;
        })
        .then((data) => {
          if (!cancelled) {
            setState({ status: 'ready', data });
          }
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            const message = error instanceof Error ? error.message : 'Unable to load today Prompt Log.';
            setState({ status: 'error', message });
          }
        });
    }

    let refreshTimer: number | undefined;

    function loadConfig() {
      return fetch('/api/config')
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Config API returned ${response.status}`);
          }
          return response.json() as Promise<WebConfigResponse>;
        })
        .catch(() => null);
    }

    loadToday();
    loadConfig().then((config) => {
      if (!cancelled) {
        refreshTimer = window.setInterval(loadToday, tailIntervalMs(config));
      }
    });

    return () => {
      cancelled = true;
      if (refreshTimer !== undefined) {
        window.clearInterval(refreshTimer);
      }
    };
  }, []);

  return (
    <main className={`shell${selectedBubble ? ' shell--inspecting' : ''}`}>
      <section className="top-bar">
        <div className="hero">
          <p className="eyebrow">Prompt Tap</p>
          <h1>Prompt Tap Web UI</h1>
          <p className="summary">
            Inspect captured OpenAI-compatible prompt payloads from your local Prompt Log.
          </p>
        </div>
        {state.status === 'ready' ? (
          <div className="top-bar-warning-count" aria-label="Warning count">
            <span>Warnings</span>
            <strong>{state.data.warnings?.length ?? 0}</strong>
          </div>
        ) : null}
      </section>

      <section className="card" aria-live="polite">
        {state.status === 'loading' ? <p>Loading today&apos;s Prompt Log…</p> : null}

        {state.status === 'error' ? (
          <div>
            <h2>Web UI backend is not reachable</h2>
            <p>{state.message}</p>
          </div>
        ) : null}

        {state.status === 'ready' ? (
          <div>
            <h2>{state.data.log_exists ? 'Today Prompt Turns' : 'No Prompt Log yet'}</h2>
            <p>{state.data.message}</p>
            <dl className="facts">
              <div>
                <dt>Date</dt>
                <dd>{state.data.date}</dd>
              </div>
              <div>
                <dt>Prompt Turns</dt>
                <dd>{state.data.turns.length}</dd>
              </div>
              <div>
                <dt>Warnings</dt>
                <dd>{state.data.warnings?.length ?? 0}</dd>
              </div>
            </dl>

            <WarningPanel warnings={state.data.warnings ?? []} />

            {state.data.turns.length > 0 ? (
              <div className="timeline-layout">
                <ol className="timeline" aria-label="Today Prompt Turns">
                  {state.data.turns.map((turn) => (
                    <PromptTurnView
                      key={turn.request_id}
                      selectedBubble={selectedBubble}
                      turn={turn}
                      onSelectBubble={selectBubble}
                    />
                  ))}
                </ol>
                <PromptBubbleDetails selection={selectedBubble} onClose={closeDetails} />
              </div>
            ) : (
              <div className="empty-state">Today&apos;s timeline is empty.</div>
            )}
          </div>
        ) : null}
      </section>
    </main>
  );
}
