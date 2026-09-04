import { useEffect, useState } from 'react';

type TodayResponse = {
  date: string;
  log_exists: boolean;
  turns: unknown[];
  message: string;
};

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; data: TodayResponse }
  | { status: 'error'; message: string };

export function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' });

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
            <h2>{state.data.log_exists ? 'Today API connected' : 'No Prompt Log yet'}</h2>
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
          </div>
        ) : null}
      </section>
    </main>
  );
}
