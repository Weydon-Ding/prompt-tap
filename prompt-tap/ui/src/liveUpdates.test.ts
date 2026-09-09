import { describe, expect, it } from 'vitest';

import type { LoadState, PromptTurn, TodayResponse } from './liveUpdates';
import {
  loadTodayState,
  mergePromptTurn,
  mergePromptTurnState,
  mergeTodayResponse,
  promptBubbleId,
} from './liveUpdates';

const requestBubble = { role: 'user', content: 'Hello' };
const pendingBubble = { role: 'pending', content: 'Waiting for response.' };
const assistantBubble = { role: 'assistant', content: 'Hi' };

function turn(requestId: string, bubbles = [requestBubble, pendingBubble]): PromptTurn {
  return { request_id: requestId, status: 'pending', bubbles };
}

describe('Prompt Turn live update recovery', () => {
  it('uses stable Prompt Bubble IDs across pending and complete versions', () => {
    const pending = turn('request-1');
    const complete = turn('request-1', [requestBubble, assistantBubble]);

    expect(promptBubbleId(pending, pending.bubbles[0], 0)).toBe('request-1:request:0');
    expect(promptBubbleId(complete, complete.bubbles[0], 0)).toBe('request-1:request:0');
    expect(promptBubbleId(pending, pending.bubbles[1], 1)).toBe('request-1:response:0');
    expect(promptBubbleId(complete, complete.bubbles[1], 1)).toBe('request-1:response:0');
  });

  it('updates an existing Prompt Turn by request id', () => {
    const pending = turn('request-1');
    const complete = { ...turn('request-1', [requestBubble, assistantBubble]), status: 'complete' };

    expect(mergePromptTurn([pending], complete)).toEqual([complete]);
  });

  it('buffers a Prompt Turn while the initial reload is pending', () => {
    const loading: LoadState = { status: 'loading', pendingTurns: [] };
    const liveTurn = turn('request-live');
    const staleReload: TodayResponse = {
      date: '2026-09-08',
      log_exists: false,
      turns: [],
      warnings: [],
      message: 'stale',
    };

    const buffered = mergePromptTurnState(loading, liveTurn);

    expect(loadTodayState(buffered, staleReload)).toMatchObject({
      status: 'ready',
      data: { log_exists: true, turns: [liveTurn] },
    });
  });

  it('includes warnings from a newly added Prompt Turn', () => {
    const ready: LoadState = {
      status: 'ready',
      data: {
        date: '2026-09-08',
        log_exists: true,
        turns: [],
        warnings: [],
        message: 'ready',
      },
    };
    const warningTurn = {
      ...turn('request-warning'),
      warnings: [{ request_id: 'request-warning', message: 'Malformed chunk.' }],
    };

    expect(mergePromptTurnState(ready, warningTurn)).toMatchObject({
      status: 'ready',
      data: { warnings: warningTurn.warnings },
    });
  });

  it('reload preserves a Prompt Turn received after the snapshot was taken', () => {
    const liveTurn = turn('request-live');
    const current: TodayResponse = {
      date: '2026-09-08',
      log_exists: true,
      turns: [liveTurn],
      warnings: [],
      message: 'current',
    };
    const staleReload: TodayResponse = {
      ...current,
      turns: [],
      message: 'reloaded',
    };

    expect(mergeTodayResponse(current, staleReload).turns).toEqual([liveTurn]);
  });

  it('does not preserve yesterday Prompt Turns after the date changes', () => {
    const yesterday: TodayResponse = {
      date: '2026-09-07',
      log_exists: true,
      turns: [turn('request-yesterday')],
      warnings: [],
      message: 'yesterday',
    };
    const today: TodayResponse = {
      date: '2026-09-08',
      log_exists: false,
      turns: [],
      warnings: [],
      message: 'today',
    };

    expect(mergeTodayResponse(yesterday, today)).toEqual(today);
  });

  it('reloads today and deduplicates stable Prompt Bubbles', () => {
    const current: TodayResponse = {
      date: '2026-09-08',
      log_exists: true,
      turns: [turn('request-1')],
      warnings: [],
      message: 'current',
    };
    const reloaded: TodayResponse = {
      ...current,
      turns: [
        turn('request-1', [requestBubble, assistantBubble]),
        turn('request-2'),
      ],
      message: 'reloaded',
    };

    expect(mergeTodayResponse(current, reloaded)).toEqual({
      ...reloaded,
      turns: [
        turn('request-1', [requestBubble, assistantBubble]),
        turn('request-2'),
      ],
    });
  });
});
