# Prompt Tap scope and logging

Prompt Tap is delivered as a standalone proxy component rather than a full New API Compose stack: this keeps it attachable to an existing New API deployment while the upstream is selected at runtime with `NEW_API_BASE_URL`. During debugging, Prompt Tap records full OpenAI-compatible request JSON as sensitive Prompt Log data and intentionally does not record credential headers such as Authorization, Cookie, Set-Cookie, or X-API-Key.

Prompt Tap Web UI changes the default response-body trade-off: `.env.example` enables bounded response-body capture with `WRITE_RESPONSE_BODY=true` and `MAX_RESPONSE_BODY_BYTES=262144` so the local chat-style UI can show AI replies without extra setup. This makes Prompt Log more useful as a prompt/reply debugging artifact, but it also means Prompt Log can contain model responses by default; operators must treat logs as sensitive, short-lived local debugging data and avoid sharing them casually.
