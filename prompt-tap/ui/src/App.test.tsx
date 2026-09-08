import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { App } from './App';

function makeTurn() {
  return {
    request_id: 'request-7',
    timestamp: '2026-09-08T10:00:00+08:00',
    path: '/v1/chat/completions?trace=1',
    request: {
      type: 'request',
      request_id: 'request-7',
      timestamp: '2026-09-08T10:00:00+08:00',
      method: 'POST',
      path: '/v1/chat/completions?trace=1',
      headers: { 'content-type': 'application/json', 'user-agent': 'test-client', 'x-request-id': 'safe-id' },
      body_truncated: false,
      payload: { model: 'test-model', messages: [{ role: 'user', content: 'Hello' }] },
    },
    response: { type: 'response', status_code: 200, duration_ms: 42, body_truncated: true, raw_body: 'recorded response' } as Record<string, unknown> | null,
    metadata: { model: 'test-model', status: 'complete', duration_ms: 42, display_path: '/v1/chat/completions' },
    bubbles: [{ role: 'user', content: 'Hello' }, { role: 'assistant', content: 'Hi there' }],
  };
}

function showApp(turn = makeTurn()) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    ok: true,
    json: async () => url === '/api/config'
      ? { tail_interval_seconds: 3600 }
      : { date: '2026-09-08', log_exists: true, message: 'Recent turns', turns: [turn] },
  })));
  render(<App />);
  return userEvent.setup();
}

test('详情展示完整请求元信息、含 query 的路径和 Safe Request Headers', async () => {
  const user = showApp();
  await user.click(await screen.findByRole('button', { name: /user\s*Hello/ }));
  const drawer = within(screen.getByRole('complementary', { name: 'Prompt Bubble 详情' }));
  for (const value of ['request-7', '2026-09-08T10:00:00+08:00', 'POST', '/v1/chat/completions?trace=1', 'test-model', 'complete', '42 ms']) {
    expect(drawer.getByText(value, { exact: true })).toBeVisible();
  }
  const headers = drawer.getByRole('region', { name: 'Safe Request Headers' });
  expect(headers).toHaveTextContent('content-type');
  expect(headers).toHaveTextContent('application/json');
  expect(headers).toHaveTextContent('test-client');
  expect(headers).toHaveTextContent('safe-id');
});

test('关闭按钮与 Escape 关闭抽屉并恢复气泡焦点', async () => {
  const user = showApp();
  const bubble = await screen.findByRole('button', { name: /user\s*Hello/ });
  await user.click(bubble);
  expect(screen.getByRole('button', { name: '关闭详情' })).toHaveFocus();
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('complementary', { name: 'Prompt Bubble 详情' })).not.toBeInTheDocument();
  expect(bubble).toHaveFocus();
  await user.click(bubble);
  await user.click(screen.getByRole('button', { name: '关闭详情' }));
  expect(screen.queryByRole('complementary', { name: 'Prompt Bubble 详情' })).not.toBeInTheDocument();
  expect(bubble).toHaveFocus();
});

test('点击 Prompt Bubble 打开具名详情抽屉且保留时间线', async () => {
  const user = showApp();
  expect(screen.queryByRole('complementary', { name: 'Prompt Bubble 详情' })).not.toBeInTheDocument();
  await user.click(await screen.findByRole('button', { name: /user\s*Hello/ }));
  const drawer = screen.getByRole('complementary', { name: 'Prompt Bubble 详情' });
  expect(within(drawer).getByRole('button', { name: '关闭详情' })).toBeVisible();
  expect(screen.getByRole('list', { name: 'Today Prompt Turns' })).toBeVisible();
});

test('轮询同步详情且不抢焦点，角色变化后可恢复焦点，目标消失时关闭', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
  let turn = makeTurn();
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    ok: true,
    json: async () => url === '/api/config'
      ? { tail_interval_seconds: 1 }
      : { date: '2026-09-08', log_exists: true, message: 'Recent turns', turns: [turn] },
  })));
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(<App />);
  await act(async () => {});
  await user.click(screen.getByRole('button', { name: /user\s*Hello/ }));
  const json = screen.getByLabelText('Current Bubble JSON');
  json.focus();
  turn = { ...turn, bubbles: [{ role: 'assistant', content: 'Updated Hello' }] };
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(within(screen.getByRole('complementary', { name: 'Prompt Bubble 详情' })).getByText('Updated Hello')).toBeVisible();
  expect(json).toHaveFocus();
  await user.keyboard('{Escape}');
  const updatedBubble = screen.getByRole('button', { name: /assistant\s*Updated Hello/ });
  expect(updatedBubble).toHaveFocus();
  await user.click(updatedBubble);
  turn = { ...turn, bubbles: [] };
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(screen.queryByRole('complementary', { name: 'Prompt Bubble 详情' })).not.toBeInTheDocument();
});

test('详情按角色提供可折叠的三段完整 JSON', async () => {
  const turn = {
    ...makeTurn(),
    request: { ...makeTurn().request, marker: 'request-record' },
    response: { ...makeTurn().response, marker: 'response-record' },
    bubbles: [{ role: 'system', content: 'system text' }],
  };
  const user = showApp(turn as ReturnType<typeof makeTurn>);
  await user.click(await screen.findByRole('button', { name: /system\s*system text/ }));
  const drawer = screen.getByRole('complementary', { name: 'Prompt Bubble 详情' });
  expect(within(drawer).getByLabelText('Current Bubble JSON')).toBeVisible();
  expect(within(drawer).getByLabelText('Request JSON')).not.toBeVisible();
  expect(within(drawer).getByLabelText('Response JSON')).not.toBeVisible();
  expect(within(drawer).getByText('Request body_truncated: false')).toBeVisible();
  expect(within(drawer).getByText('Response body_truncated: true')).toBeVisible();
  expect(within(drawer).getByLabelText('Current Bubble JSON')).toHaveTextContent('"role": "system"');
  await user.click(within(drawer).getByText('Request JSON', { selector: 'summary' }));
  expect(within(drawer).getByLabelText('Current Bubble JSON')).toBeVisible();
  expect(within(drawer).getByLabelText('Request JSON')).toBeVisible();
});

test('三个 JSON 区段复制完整 pretty JSON 并在成功后反馈', async () => {
  const turn = {
    ...makeTurn(),
    request: { kind: 'request', body_truncated: false, payload: { marker: 'request' } } as Record<string, unknown>,
    response: { kind: 'response', body_truncated: false, raw_body: 'response body' } as Record<string, unknown>,
    bubbles: [{ role: 'user', content: 'bubble content' }],
  };
  const writes: string[] = [];
  const user = showApp(turn as ReturnType<typeof makeTurn>);
  const writeText = vi.fn(async (value: string) => { writes.push(value); });
  vi.spyOn(navigator.clipboard, 'writeText').mockImplementation(writeText);
  await user.click(await screen.findByRole('button', { name: /user\s*bubble content/ }));
  const drawer = screen.getByRole('complementary', { name: 'Prompt Bubble 详情' });
  await user.click(within(drawer).getByRole('button', { name: '复制 Current Bubble JSON' }));
  await user.click(within(drawer).getByText('Request JSON', { selector: 'summary' }));
  await user.click(within(drawer).getByRole('button', { name: '复制 Request JSON' }));
  await user.click(within(drawer).getByText('Response JSON', { selector: 'summary' }));
  await user.click(within(drawer).getByRole('button', { name: '复制 Response JSON' }));
  expect(writes).toEqual([
    '{\n  "role": "user",\n  "content": "bubble content"\n}',
    '{\n  "kind": "request",\n  "body_truncated": false,\n  "payload": {\n    "marker": "request"\n  }\n}',
    '{\n  "kind": "response",\n  "body_truncated": false,\n  "raw_body": "response body"\n}',
  ]);
  expect(within(drawer).getAllByRole('status').length).toBeGreaterThan(0);
});

test('切换气泡后延迟复制不会显示旧反馈', async () => {
  const turn = { ...makeTurn(), bubbles: [{ role: 'user', content: 'first' }, { role: 'assistant', content: 'second' }] };
  let resolveCopy!: () => void;
  const user = showApp(turn as ReturnType<typeof makeTurn>);
  vi.spyOn(navigator.clipboard, 'writeText').mockImplementation(() => new Promise<void>((resolve) => { resolveCopy = resolve; }));
  await user.click(await screen.findByRole('button', { name: /user\s*first/ }));
  const drawer = screen.getByRole('complementary', { name: 'Prompt Bubble 详情' });
  await user.click(within(drawer).getByRole('button', { name: '复制 Current Bubble JSON' }));
  await user.click(await screen.findByRole('button', { name: /assistant\s*second/ }));
  await act(async () => resolveCopy());
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

test.each(['system', 'user', 'raw', 'unknown', 'other', 'assistant', 'tool_call', 'error', 'pending'])('%s 默认展开对应来源且重开时重置', async (role) => {
  const user = showApp({ ...makeTurn(), bubbles: [{ role, content: 'inspect' }] });
  const bubble = await screen.findByRole('button', { name: new RegExp(`${role}\\s*inspect`) });
  await user.click(bubble);
  const responseRole = ['assistant', 'tool_call', 'error', 'pending'].includes(role);
  expect(screen.getByLabelText('Current Bubble JSON')).toHaveProperty('textContent', `{\n  "role": "${role}",\n  "content": "inspect"\n}`);
  expect(screen.getByLabelText(responseRole ? 'Response JSON' : 'Current Bubble JSON')).toBeVisible();
  expect(screen.getByLabelText(responseRole ? 'Current Bubble JSON' : 'Response JSON')).not.toBeVisible();
  await user.click(screen.getByText('Request JSON', { selector: 'summary' }));
  await user.keyboard('{Escape}');
  await user.click(bubble);
  expect(screen.getByLabelText('Request JSON')).not.toBeVisible();
  expect(screen.getByLabelText(responseRole ? 'Response JSON' : 'Current Bubble JSON')).toBeVisible();
});

test('剪贴板拒绝和不可用都提供可操作的失败反馈', async () => {
  const user = showApp();
  vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('Permission denied'));
  await user.click(await screen.findByRole('button', { name: /user\s*Hello/ }));
  await user.click(screen.getByRole('button', { name: '复制 Current Bubble JSON' }));
  expect(screen.getByRole('status')).toHaveTextContent('复制失败');
  expect(screen.getByRole('status')).toHaveTextContent('手动复制');
  vi.spyOn(navigator, 'clipboard', 'get').mockReturnValue(undefined as unknown as Clipboard);
  await user.click(screen.getByRole('button', { name: '复制 Current Bubble JSON' }));
  expect(screen.getByRole('status')).toHaveTextContent('复制不可用');
});

test.each([true, false, undefined])('截断标识 %s 与长 raw_body 展示及复制均保持原值', async (truncated) => {
  const rawBody = '完整原始记录'.repeat(12000) + 'END-OF-RECORD';
  const turn = makeTurn();
  turn.response = { body_truncated: truncated, raw_body: rawBody };
  const user = showApp(turn);
  const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
  await user.click(await screen.findByRole('button', { name: /assistant\s*Hi there/ }));
  expect(screen.getByText(`Response body_truncated: ${truncated === undefined ? '未知' : truncated}`)).toBeVisible();
  const displayed = screen.getByLabelText('Response JSON').textContent ?? '';
  expect(JSON.parse(displayed).raw_body).toBe(rawBody);
  expect(displayed).toContain('\n  "raw_body":');
  await user.click(screen.getByRole('button', { name: '复制 Response JSON' }));
  expect(JSON.parse(writeText.mock.calls[0][0]).raw_body).toBe(rawBody);
});

test('缺失响应回退当前气泡并禁用 Response JSON 复制', async () => {
  const turn = { ...makeTurn(), response: null, bubbles: [{ role: 'assistant', content: 'reply' }] };
  const user = showApp(turn as ReturnType<typeof makeTurn>);
  await user.click(await screen.findByRole('button', { name: /assistant\s*reply/ }));
  const drawer = screen.getByRole('complementary', { name: 'Prompt Bubble 详情' });
  expect(within(drawer).getByLabelText('Current Bubble JSON')).toBeVisible();
  expect(within(drawer).getByLabelText('Response JSON')).not.toBeVisible();
  await user.click(within(drawer).getByText('Response JSON', { selector: 'summary' }));
  expect(within(drawer).getByLabelText('Response JSON')).toHaveTextContent('无记录');
  expect(within(drawer).getByRole('button', { name: '复制 Response JSON' })).toBeDisabled();
});
