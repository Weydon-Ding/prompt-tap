import { useEffect, useState } from 'react';

import {
  loadTodayState,
  mergePromptTurnState,
  promptBubbleId,
  type LoadState,
  type PromptBubble,
  type PromptTurn,
  type PromptWarning,
  type TodayResponse,
} from './liveUpdates';

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

function formatJson(value: unknown) {
  if (value === undefined || value === null) {
    return 'Not captured.';
  }

  return JSON.stringify(value, null, 2);
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

type SelectedPromptBubble = {
  turn: PromptTurn;
  bubble: PromptBubble;
};

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
      <span className="bubble-content">{bubble.content || 'No displayable content captured.'}</span>
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
              key={promptBubbleId(turn, bubble, index)}
              bubble={bubble}
              isSelected={selectedBubble?.turn.request_id === turn.request_id && selectedBubble.bubble === bubble}
              onSelect={() => onSelectBubble({ turn, bubble })}
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

function PromptBubbleDetails({ selection }: { selection: SelectedPromptBubble | null }) {
  if (!selection) {
    return <div className="bubble-details empty-state">Select a Prompt Bubble to inspect it.</div>;
  }

  const displayMetadata = promptTurnDisplayMetadata(selection.turn);

  return (
    <aside className="bubble-details">
      <h3>Prompt Bubble</h3>
      <dl>
        <div>
          <dt>Role</dt>
          <dd>{selection.bubble.role}</dd>
        </div>
        <div>
          <dt>Request ID</dt>
          <dd>{selection.turn.request_id}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{displayMetadata.status}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>{displayMetadata.model}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{displayMetadata.duration}</dd>
        </div>
        <div>
          <dt>Display Path</dt>
          <dd>{displayMetadata.displayPath}</dd>
        </div>
        <div>
          <dt>Content</dt>
          <dd>{selection.bubble.content || 'No displayable content captured.'}</dd>
        </div>
        <div>
          <dt>Request JSON</dt>
          <dd>{formatJson(selection.turn.request)}</dd>
        </div>
        <div>
          <dt>Response JSON</dt>
          <dd>{formatJson(selection.turn.response)}</dd>
        </div>
      </dl>
    </aside>
  );
}

export function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading', pendingTurns: [] });
  const [selectedBubble, setSelectedBubble] = useState<SelectedPromptBubble | null>(null);

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
            setState((current) => loadTodayState(current, data));
          }
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            const message = error instanceof Error ? error.message : 'Unable to load today Prompt Log.';
            setState((current) => ({
              status: 'error',
              message,
              pendingTurns: current.status === 'ready' ? current.data.turns : current.pendingTurns,
            }));
          }
        });
    }

    const events = new EventSource('/api/events');
    events.addEventListener('open', loadToday);
    events.addEventListener('prompt_turn', (event) => {
      const turn = JSON.parse((event as MessageEvent<string>).data) as PromptTurn;
      setState((current) => mergePromptTurnState(current, turn));
    });

    loadToday();

    return () => {
      cancelled = true;
      events.close();
    };
  }, []);

  return (
    <main className="shell">
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
                      onSelectBubble={setSelectedBubble}
                    />
                  ))}
                </ol>
                <PromptBubbleDetails selection={selectedBubble} />
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
