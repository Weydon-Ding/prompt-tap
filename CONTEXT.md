# Prompt Tap

Prompt Tap 是用于观察应用发送给 New API 的 OpenAI-compatible 请求内容的调试上下文。它关注请求侧 prompt payload 的可见性，同时把凭证类请求头和完整模型响应正文排除在日志边界之外。

## Language

**Prompt Tap**:
一个位于应用与 New API 之间的透明调试代理组件，用来捕获 OpenAI-compatible 请求中的 prompt payload。
_Avoid_: 调试代理, HTTP 代理

**New API**:
被 Prompt Tap 代理的 OpenAI-compatible gateway，负责继续转发请求到上游模型渠道。
_Avoid_: 上游模型, 模型服务

**Prompt Log**:
Prompt Tap 产生的请求调试日志，包含 prompt payload、请求元数据和响应状态摘要。
_Avoid_: 请求日志, 代理日志

**Prompt Payload**:
进入 Prompt Log 的 OpenAI-compatible 请求 JSON 内容；默认保留完整 JSON，以便观察 model、messages、prompt、input、tools 以及 provider-specific 字段。
_Avoid_: body, 已知字段摘要

**Safe Request Headers**:
允许进入 Prompt Log 的非敏感请求头白名单。
_Avoid_: headers, 请求头

**Sensitive Credential Headers**:
不得进入 Prompt Log 的凭证类请求头，例如 Authorization、Cookie 和 X-API-Key。
_Avoid_: 敏感 header, 密钥 header

**Prompt Turn**:
Prompt Log 中同一个 `request_id` 的 request record 与 response record 归并后形成的一次可展示交互。
_Avoid_: Chat Turn, Log Turn, request group

**Prompt Bubble**:
Prompt Turn 中显示在主时间线里的一个可点击展示单元，例如 system、user、assistant 或 tool call 内容。
_Avoid_: Chat Bubble, Log Bubble, message bubble
