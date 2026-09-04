# Prompt Tap

Prompt Tap 是一个位于宿主机应用与 New API 之间的透明调试代理。调试时，应用把 OpenAI-compatible Base URL 指向 `http://127.0.0.1:8888/v1`，Prompt Tap 再把请求转发到 `NEW_API_BASE_URL` 指定的 New API。

Prompt Tap 会记录完整 OpenAI-compatible 请求 JSON。Prompt Log 属于敏感日志：它默认不记录 `Authorization`、`Cookie`、`Set-Cookie`、`X-API-Key` 等凭证类请求头。为了配合 Prompt Tap Web UI 的聊天式查看体验，示例配置默认启用受大小限制的模型响应正文记录；prompt、messages、input、tools 和模型回复本身都可能包含敏感信息，Prompt Log 应作为短期本地调试数据谨慎保存和分享。

## 文件

```text
prompt-tap/
├── Dockerfile
├── entrypoint.sh
├── log_prompts.py
├── compose.yaml
├── .env.example
├── README.md
├── requirements-dev.txt
├── requirements-web.txt
├── web/
│   ├── Dockerfile
│   ├── app.py
│   ├── config.py
│   └── log_reader.py
├── ui/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
└── tests/
    ├── test_log_prompts.py
    └── test_web_app.py
```

## 配置

复制示例配置：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

然后按你的 New API 地址修改 `.env`。如果没有创建 `.env` 或没有设置 `NEW_API_BASE_URL`，容器会 fail fast 并提示复制 `.env.example`：

```env
NEW_API_BASE_URL=http://host.docker.internal:3000
WATCH_PATH_PREFIX=/v1/
WATCH_METHODS=*
WRITE_FILE_LOG=true
WRITE_RAW_BODY=false
MAX_BODY_BYTES=0
WRITE_RESPONSE_BODY=true
MAX_RESPONSE_BODY_BYTES=262144
LOG_DIR=/logs
TZ=Asia/Shanghai
UI_MAX_TURNS=200
UI_TAIL_INTERVAL_SECONDS=1
```

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `NEW_API_BASE_URL` | `http://host.docker.internal:3000` | New API 的 HTTP base URL。未配置时容器会 fail fast。 |
| `WATCH_PATH_PREFIX` | `/v1/` | 只记录此前缀下的请求。 |
| `WATCH_METHODS` | `*` | 要记录的方法；`*` 表示全部方法，也可写成 `POST,PUT`。 |
| `WRITE_FILE_LOG` | `true` | 是否写入 `/logs/*.jsonl`。 |
| `WRITE_RAW_BODY` | `false` | JSON 解析成功时，是否额外把 raw body 写入同一条 request record。解析失败时总会记录 raw body。 |
| `MAX_BODY_BYTES` | `0` | 单条请求体最大记录字节数；`0` 表示不截断。 |
| `WRITE_RESPONSE_BODY` | `true` | 是否记录 New API 响应正文；为了配合 Prompt Tap Web UI 默认展示 AI 回复，示例配置默认开启。 |
| `MAX_RESPONSE_BODY_BYTES` | `262144` | 单条响应正文最大记录字节数；`0` 表示不截断。 |
| `LOG_DIR` | `/logs` | 容器内 Prompt Log 目录；本地开发 Web UI 时可设置为 `prompt-tap/logs` 或绝对路径。 |
| `TZ` | `Asia/Shanghai` | 容器本地时区，影响日志日期与时间戳；代理和 Web UI 应使用同一个值。 |
| `UI_MAX_TURNS` | `200` | Prompt Tap Web UI 默认加载的最近 Prompt Turn 数量。 |
| `UI_TAIL_INTERVAL_SECONDS` | `1` | Prompt Tap Web UI 轮询 Prompt Log 新增内容的间隔秒数。 |

## 启动

在 `prompt-tap/` 目录中运行：

```bash
docker compose up -d --build
```

默认会启动三个服务：

- `prompt-tap`：代理入口 `http://127.0.0.1:8888/v1`。
- `prompt-tap-web`：Web UI 后端 `http://127.0.0.1:8000`，提供 `/healthz` 和 `/api/today`。
- `prompt-tap-ui`：Prompt Tap Web UI `http://127.0.0.1:5173`。

查看状态：

```bash
docker compose ps
```

健康检查：

```bash
curl http://127.0.0.1:5173/healthz
```

查看实时 Prompt Payload：

```bash
docker compose logs -f prompt-tap
```

Docker logs 使用多行 pretty JSON block，便于人工实时查看。

## 应用侧配置

宿主机应用原来可能配置为：

```env
OPENAI_BASE_URL=http://127.0.0.1:3000/v1
OPENAI_API_KEY=sk-xxxxxxxx
```

调试期间改为：

```env
OPENAI_BASE_URL=http://127.0.0.1:8888/v1
OPENAI_API_KEY=sk-xxxxxxxx
```

原则是：保持原来的路径结构，只把域名和端口替换为 `127.0.0.1:8080`。

## JSONL schema

Prompt Log 写入 `logs/prompt-YYYY-MM-DD.jsonl`。request 与 response 分别一行，通过 `request_id` 关联。

### request record

| 字段 | 含义 |
| --- | --- |
| `type` | 固定为 `request`。 |
| `request_id` | 一次请求的 UUID。 |
| `timestamp` | 容器本地时区下的 ISO-like 时间。 |
| `method` | HTTP method。 |
| `path` | 请求 path。 |
| `host` | mitmproxy 看到的请求 host。 |
| `headers` | Safe Request Headers 白名单内的请求头。 |
| `body_truncated` | 请求体是否被 `MAX_BODY_BYTES` 截断。 |
| `payload` | JSON 解析成功时的完整请求 JSON；解析失败时为 `null`。 |
| `parse_error` | JSON 解析错误；解析成功时为 `null`。 |
| `raw_body` | 解析失败时总会存在；解析成功且 `WRITE_RAW_BODY=true` 时存在。 |

### response record

| 字段 | 含义 |
| --- | --- |
| `type` | 固定为 `response`。 |
| `request_id` | 与 request record 相同的 ID。 |
| `timestamp` | 容器本地时区下的 ISO-like 时间。 |
| `path` | 请求 path。 |
| `status_code` | New API 返回的 HTTP 状态码。 |
| `duration_ms` | 从 request hook 到 response hook 的耗时毫秒数。 |
| `body_truncated` | 启用响应正文记录时，正文是否被 `MAX_RESPONSE_BODY_BYTES` 截断。 |
| `payload` | 启用响应正文记录且 JSON 解析成功时的完整响应 JSON。 |
| `parse_error` | 启用响应正文记录但 JSON 解析失败时的错误信息；解析成功时为 `null`。 |
| `raw_body` | 启用响应正文记录且响应不是 JSON 时的原始文本，例如 SSE 事件流或上游错误页。 |

示例配置默认记录受大小限制的响应正文，以便 Prompt Tap Web UI 能直接显示 AI 回复。若要只保留响应摘要，可在 `.env` 中设置：

```env
WRITE_RESPONSE_BODY=false
```

普通 JSON 响应会记录到 `payload`。`stream=true` 的 SSE 响应会以完整原始事件流记录到 `raw_body`，并在流结束后写入日志；它不是实时逐 token 输出。超出上限的正文会保留前段内容，并标记 `body_truncated=true`。

## 查询日志

筛选 request records：

```bash
cat logs/prompt-$(date +%F).jsonl | jq 'select(.type == "request")'
```

按 `request_id` 同时查看请求与 AI 回复：

```bash
cat logs/prompt-$(date +%F).jsonl \
  | jq 'select(.request_id == "<request-id>")'
```

查看非流式 JSON 响应中的 AI 回复（适用于 Chat Completions）：

```bash
cat logs/prompt-$(date +%F).jsonl \
  | jq -r '
      select(.type == "response")
      | .payload.choices[]?.message.content
    '
```

筛选 system messages：

```bash
cat logs/prompt-$(date +%F).jsonl \
  | jq -r '
      select(.type == "request")
      | .payload.messages[]?
      | select(.role == "system")
      | .content
    '
```

## Prompt Tap Web UI

Prompt Tap Web UI 提供聊天式 Prompt Log 查看器：

- 打开页面时加载当天最近 200 个 Prompt Turn。
- 持续监听新增 Prompt Log，并自动追加或更新聊天流。
- `system`、`user`、`assistant`、`tool_call` 会以不同 Prompt Bubble 展示。
- 点击 Prompt Bubble 后，右侧详情抽屉展示元数据、Safe Request Headers、当前气泡 JSON、完整 request/response JSON。
- SSE 断线重连后，页面会重新拉取当天日志并去重。

当天无 Prompt Log 时，页面会提示把应用 OpenAI Base URL 指向 `http://127.0.0.1:8888/v1`。

本地开发 Web UI 时，FastAPI 后端默认监听 `8000`，Vite dev server 默认监听 `5173` 并代理 `/api` 与 `/healthz` 到 FastAPI。运行前将 `LOG_DIR` 设置为 `prompt-tap/logs` 或绝对路径。

## 停用与清理

停止容器：

```bash
docker compose stop prompt-tap prompt-tap-web prompt-tap-ui
```

清理 Prompt Log（POSIX shell）：

```bash
rm -rf logs/*
```

清理 Prompt Log（Windows PowerShell）：

```powershell
Remove-Item .\logs\* -Recurse -Force
```

调试结束后，把应用的 Base URL 恢复为原 New API 地址。

## 测试

在仓库根目录运行：

```bash
python -m pip install -r prompt-tap/requirements-dev.txt
python -m pytest
```

Windows 也可以使用 `py -m pip ...` 与 `py -m pytest`。
