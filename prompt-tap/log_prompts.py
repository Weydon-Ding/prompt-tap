import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

try:
    from mitmproxy import ctx
except Exception:
    class _FallbackLog:
        def info(self, message):
            pass

        def error(self, message):
            pass

    class _FallbackCtx:
        log = _FallbackLog()

    ctx = _FallbackCtx()


@dataclass(frozen=True)
class PromptTapConfig:
    watch_path_prefix: str = os.getenv("WATCH_PATH_PREFIX", "/v1/")
    watch_methods: str = os.getenv("WATCH_METHODS", "*")
    max_body_bytes: int = int(os.getenv("MAX_BODY_BYTES", "0"))
    write_file_log: bool = os.getenv("WRITE_FILE_LOG", "true").lower() == "true"
    write_raw_body: bool = os.getenv("WRITE_RAW_BODY", "false").lower() == "true"
    write_response_body: bool = os.getenv("WRITE_RESPONSE_BODY", "false").lower() == "true"
    max_response_body_bytes: int = int(os.getenv("MAX_RESPONSE_BODY_BYTES", "262144"))
    log_dir: Path = Path(os.getenv("LOG_DIR", "/logs"))


CONFIG = PromptTapConfig()

SAFE_REQUEST_HEADERS = (
    "content-type",
    "user-agent",
    "x-request-id",
)


def _configured_methods(config):
    methods = config.watch_methods.strip()
    if methods == "*":
        return None

    return {
        method.strip().upper()
        for method in methods.split(",")
        if method.strip()
    }


def is_watched_request(flow, config=CONFIG):
    if not flow.request.path.startswith(config.watch_path_prefix):
        return False

    methods = _configured_methods(config)
    if methods is None:
        return True

    return flow.request.method.upper() in methods


def get_safe_headers(headers):
    result = {}

    for key in SAFE_REQUEST_HEADERS:
        value = headers.get(key)
        if value:
            result[key] = value

    return result


def truncate_text(text, config=CONFIG, max_body_bytes=None):
    if max_body_bytes is None:
        max_body_bytes = config.max_body_bytes

    if max_body_bytes <= 0:
        return text, False

    text_bytes = text.encode("utf-8", errors="replace")

    if len(text_bytes) <= max_body_bytes:
        return text, False

    truncated = text_bytes[:max_body_bytes].decode("utf-8", errors="ignore")
    return truncated, True


def build_request_record(flow, request_id, config=CONFIG):
    raw_body = flow.request.get_text(strict=False)
    raw_body, truncated = truncate_text(raw_body, config)

    try:
        payload = json.loads(raw_body)
        parse_error = None
    except Exception as exc:
        payload = None
        parse_error = str(exc)

    record = {
        "type": "request",
        "request_id": request_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "method": flow.request.method,
        "path": flow.request.path,
        "host": flow.request.host,
        "headers": get_safe_headers(flow.request.headers),
        "body_truncated": truncated,
        "payload": payload,
        "parse_error": parse_error,
    }

    if config.write_raw_body or parse_error:
        record["raw_body"] = raw_body

    return record


def build_response_record(flow, now=None, config=CONFIG):
    if now is None:
        now = time.time()

    request_id = flow.metadata.get("prompt_tap_request_id", "unknown")
    start_time = flow.metadata.get("prompt_tap_start_time")
    duration_ms = None

    if start_time:
        duration_ms = round((now - start_time) * 1000, 2)

    status_code = flow.response.status_code if flow.response else None
    record = {
        "type": "response",
        "request_id": request_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "path": flow.request.path,
        "status_code": status_code,
        "duration_ms": duration_ms,
    }

    if not config.write_response_body or not flow.response:
        return record

    raw_content = flow.response.raw_content
    try:
        raw_body = raw_content.decode("utf-8")
    except UnicodeDecodeError:
        raw_body = flow.response.get_text(strict=False)

    raw_body, truncated = truncate_text(
        raw_body,
        config,
        max_body_bytes=config.max_response_body_bytes,
    )
    record["body_truncated"] = truncated

    try:
        record["payload"] = json.loads(raw_body)
        record["parse_error"] = None
    except Exception as exc:
        record["raw_body"] = raw_body
        record["parse_error"] = str(exc)

    return record


def write_jsonl(record, config=CONFIG):
    if not config.write_file_log:
        return

    try:
        config.log_dir.mkdir(parents=True, exist_ok=True)
        filename = config.log_dir / f"prompt-{time.strftime('%Y-%m-%d')}.jsonl"

        with filename.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    except Exception as exc:
        ctx.log.error(f"写入 Prompt Log 文件失败: {exc}")


def format_request_log(record):
    body = record.get("payload")
    if body is None:
        body = record.get("raw_body", "")

    if isinstance(body, (dict, list)):
        body_text = json.dumps(body, ensure_ascii=False, indent=2)
    else:
        body_text = str(body)

    return (
        "\n"
        "========== PROMPT TAP REQUEST ==========\n"
        f"request_id: {record['request_id']}\n"
        f"method: {record['method']}\n"
        f"path: {record['path']}\n"
        f"{body_text}\n"
        "========================================"
    )


def request(flow):
    if not is_watched_request(flow):
        return

    request_id = str(uuid.uuid4())
    flow.metadata["prompt_tap_request_id"] = request_id
    flow.metadata["prompt_tap_start_time"] = time.time()

    record = build_request_record(flow, request_id)
    flow.metadata["prompt_tap_record"] = record

    ctx.log.info(format_request_log(record))
    write_jsonl(record)


def response(flow):
    if not is_watched_request(flow):
        return

    record = build_response_record(flow)

    ctx.log.info(
        f"[PROMPT TAP RESPONSE] "
        f"request_id={record['request_id']} "
        f"status={record['status_code']} "
        f"duration_ms={record['duration_ms']} "
        f"path={record['path']}"
    )
    write_jsonl(record)
