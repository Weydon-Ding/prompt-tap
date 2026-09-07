import { useEffect, useState } from 'react';

type PromptBubble = {
  role: string;
  content: string;
};

const PROMPT_BUBBLE_ROLE_CLASS_NAMES = new Set([
  'assistant',
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
  timestamp?: string;
  path?: string;
  request?: unknown;
  response?: unknown;
  bubbles: PromptBubble[];
};

function formatJson(value: unknown) {
  if (value === undefined || value === null) {
    return 'Not captured.';
  }

  return JSON.stringify(value, null, 2);
}

type SelectedPromptBubble = {
  turn: PromptTurn;
  bubble: PromptBubble;
};

type TodayResponse = {
  date: string;
  log_exists: boolean;
  turns: PromptTurn[];
  message: string;
};

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
  return (
    <li className="prompt-turn">
      <div className="turn-meta">
        <span>{turn.timestamp ?? 'Unknown time'}</span>
        <span>{turn.path ?? 'Unknown path'}</span>
        <span>{turn.request_id}</span>
      </div>
      <div className="bubble-stack">
        {turn.bubbles.length > 0 ? (
          turn.bubbles.map((bubble, index) => (
            <PromptBubbleView
              key={`${turn.request_id}-${bubble.role}-${index}`}
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

function PromptBubbleDetails({ selection }: { selection: SelectedPromptBubble | null }) {
  if (!selection) {
    return <div className="bubble-details empty-state">Select a Prompt Bubble to inspect it.</div>;
  }

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
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [selectedBubble, setSelectedBubble] = useState<SelectedPromptBubble | null>(null);

  useEffect(() => {
    let cancelled = false;

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

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Prompt Tap</p>
        <h1>Prompt Tap Web UI</h1>
        <p className="summary">
          Inspect captured OpenAI-compatible prompt payloads from your local Prompt Log.
        </p>
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
            </dl>

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
