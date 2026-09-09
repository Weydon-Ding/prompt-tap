export type PromptBubble = {
  role: string;
  content: string;
};

export type PromptWarning = {
  request_id: string;
  message: string;
  chunk?: string;
};

export type PromptTurnMetadata = {
  model?: string | null;
  status?: string | null;
  duration_ms?: number | null;
  display_path?: string | null;
};

export type PromptTurn = {
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

export type LoadState =
  | { status: 'loading'; pendingTurns: PromptTurn[] }
  | { status: 'ready'; data: TodayResponse }
  | { status: 'error'; message: string; pendingTurns: PromptTurn[] };

export function mergePromptTurnState(state: LoadState, update: PromptTurn): LoadState {
  if (state.status === 'ready') {
    const turns = mergePromptTurn(state.data.turns, update);
    return {
      status: 'ready',
      data: {
        ...state.data,
        log_exists: true,
        turns,
        warnings: turns.flatMap((turn) => turn.warnings ?? []),
      },
    };
  }

  return {
    ...state,
    pendingTurns: mergePromptTurn(state.pendingTurns, update),
  };
}

export function loadTodayState(state: LoadState, data: TodayResponse): LoadState {
  const current: TodayResponse = state.status === 'ready'
    ? state.data
    : { ...data, turns: state.pendingTurns, warnings: [] };
  const merged = mergeTodayResponse(current, data);
  return {
    status: 'ready',
    data: {
      ...merged,
      log_exists: merged.log_exists || merged.turns.length > 0,
      warnings: merged.turns.flatMap((turn) => turn.warnings ?? []),
    },
  };
}

export type TodayResponse = {
  date: string;
  log_exists: boolean;
  turns: PromptTurn[];
  warnings?: PromptWarning[];
  message: string;
};

const RESPONSE_ROLES = new Set(['assistant', 'error', 'pending', 'tool', 'tool_call']);

function bubbleSection(bubble: PromptBubble) {
  return RESPONSE_ROLES.has(bubble.role) ? 'response' : 'request';
}

export function promptBubbleId(turn: PromptTurn, bubble: PromptBubble, index: number) {
  const section = bubbleSection(bubble);
  const sectionIndex = turn.bubbles
    .slice(0, index)
    .filter((candidate) => bubbleSection(candidate) === section).length;

  return `${turn.request_id}:${section}:${sectionIndex}`;
}

function mergePromptBubbles(current: PromptTurn, update: PromptTurn) {
  const bubblesById = new Map(
    current.bubbles.map((bubble, index) => [promptBubbleId(current, bubble, index), bubble]),
  );
  update.bubbles.forEach((bubble, index) => {
    bubblesById.set(promptBubbleId(update, bubble, index), bubble);
  });

  return { ...update, bubbles: [...bubblesById.values()] };
}

export function mergePromptTurn(turns: PromptTurn[], update: PromptTurn) {
  const index = turns.findIndex((turn) => turn.request_id === update.request_id);
  if (index === -1) {
    return [...turns, update];
  }

  return turns.map((turn, turnIndex) => (
    turnIndex === index ? mergePromptBubbles(turn, update) : turn
  ));
}

export function mergeTodayResponse(current: TodayResponse, reloaded: TodayResponse) {
  if (current.date !== reloaded.date) {
    return reloaded;
  }

  const reloadedTurns = new Map(reloaded.turns.map((turn) => [turn.request_id, turn]));
  const turns = current.turns.map((turn) => {
    const reloadedTurn = reloadedTurns.get(turn.request_id);
    if (!reloadedTurn) {
      return turn;
    }

    reloadedTurns.delete(turn.request_id);
    return mergePromptBubbles(turn, reloadedTurn);
  });

  return {
    ...reloaded,
    turns: [...turns, ...reloadedTurns.values()],
  };
}
