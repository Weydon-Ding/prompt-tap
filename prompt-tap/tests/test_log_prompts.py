import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "log_prompts.py"


def load_module():
    spec = importlib.util.spec_from_file_location("log_prompts", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRequest:
    def __init__(self, *, method="POST", path="/v1/chat/completions", text="{}", headers=None, host="new-api"):
        self.method = method
        self.path = path
        self.headers = headers or {}
        self.host = host
        self._text = text

    def get_text(self, strict=False):
        return self._text


class FakeResponse:
    def __init__(self, status_code=200, text="", raw_content=None):
        self.status_code = status_code
        self._text = text
        self.raw_content = text.encode("utf-8") if raw_content is None else raw_content

    def get_text(self, strict=False):
        return self._text


class FakeFlow:
    def __init__(self, request, response=None):
        self.request = request
        self.response = response
        self.metadata = {}


def test_watches_all_methods_under_configured_v1_prefix_by_default():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(watch_path_prefix="/v1/", watch_methods="*")

    flow = FakeFlow(FakeRequest(method="GET", path="/v1/models"))

    assert log_prompts.is_watched_request(flow, config)


def test_request_record_uses_complete_json_as_prompt_payload():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(write_raw_body=False)
    flow = FakeFlow(FakeRequest(
        text='{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}],"provider_specific":{"trace":true}}',
        headers={"content-type": "application/json", "authorization": "Bearer secret"},
    ))

    record = log_prompts.build_request_record(flow, "request-1", config)

    assert record["payload"] == {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "provider_specific": {"trace": True},
    }
    assert "raw_body" not in record
    assert record["headers"] == {"content-type": "application/json"}


def test_parse_error_records_raw_body_in_same_request_record():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(write_raw_body=False)
    flow = FakeFlow(FakeRequest(text="not-json"))

    record = log_prompts.build_request_record(flow, "request-1", config)

    assert record["payload"] is None
    assert record["parse_error"]
    assert record["raw_body"] == "not-json"


def test_write_raw_body_records_raw_body_when_json_parse_succeeds():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(write_raw_body=True)
    flow = FakeFlow(FakeRequest(text='{"model":"gpt-4o-mini"}'))

    record = log_prompts.build_request_record(flow, "request-1", config)

    assert record["payload"] == {"model": "gpt-4o-mini"}
    assert record["parse_error"] is None
    assert record["raw_body"] == '{"model":"gpt-4o-mini"}'


def test_truncates_body_when_max_body_bytes_is_non_zero():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(max_body_bytes=4)
    flow = FakeFlow(FakeRequest(text="abcdef"))

    record = log_prompts.build_request_record(flow, "request-1", config)

    assert record["body_truncated"] is True
    assert record["raw_body"] == "abcd"


def test_max_body_bytes_zero_does_not_truncate():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(max_body_bytes=0)
    flow = FakeFlow(FakeRequest(text="abcdef"))

    record = log_prompts.build_request_record(flow, "request-1", config)

    assert record["body_truncated"] is False
    assert record["raw_body"] == "abcdef"


def test_truncation_never_records_more_than_max_utf8_bytes():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(max_body_bytes=2)
    flow = FakeFlow(FakeRequest(text="你abcdef"))

    record = log_prompts.build_request_record(flow, "request-1", config)

    assert record["body_truncated"] is True
    assert len(record["raw_body"].encode("utf-8")) <= 2


def test_response_record_uses_minimal_summary():
    log_prompts = load_module()
    flow = FakeFlow(FakeRequest(path="/v1/responses"), FakeResponse(status_code=201))
    flow.metadata["prompt_tap_request_id"] = "request-1"
    flow.metadata["prompt_tap_start_time"] = 10.0

    record = log_prompts.build_response_record(flow, now=11.25)

    assert record == {
        "type": "response",
        "request_id": "request-1",
        "timestamp": record["timestamp"],
        "path": "/v1/responses",
        "status_code": 201,
        "duration_ms": 1250.0,
        "response_body_capture": False,
    }


def test_response_record_does_not_include_body_by_default():
    log_prompts = load_module()
    flow = FakeFlow(
        FakeRequest(path="/v1/chat/completions"),
        FakeResponse(text='{"choices":[{"message":{"content":"hi"}}]}'),
    )

    record = log_prompts.build_response_record(flow)

    assert record["response_body_capture"] is False
    assert "payload" not in record
    assert "raw_body" not in record
    assert "body_truncated" not in record


def test_response_record_captures_json_body_when_enabled():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(write_response_body=True)
    flow = FakeFlow(
        FakeRequest(path="/v1/chat/completions"),
        FakeResponse(text='{"choices":[{"message":{"content":"hi"}}]}'),
    )

    record = log_prompts.build_response_record(flow, config=config)

    assert record["response_body_capture"] is True
    assert record["payload"] == {"choices": [{"message": {"content": "hi"}}]}
    assert record["parse_error"] is None
    assert record["body_truncated"] is False
    assert "raw_body" not in record


def test_response_record_decodes_utf8_raw_content_when_response_charset_is_wrong():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(write_response_body=True)
    sse_body = 'data: {"choices":[{"delta":{"content":"你好"}}]}\n\n'
    flow = FakeFlow(
        FakeRequest(path="/v1/chat/completions"),
        FakeResponse(
            text='data: {"choices":[{"delta":{"content":"ä½ å¥½"}}]}\n\n',
            raw_content=sse_body.encode("utf-8"),
        ),
    )

    record = log_prompts.build_response_record(flow, config=config)

    assert "你好" in record["raw_body"]
    assert "ä½ å¥½" not in record["raw_body"]


def test_response_record_captures_raw_text_and_sse_when_enabled():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(write_response_body=True)
    sse_body = 'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'
    flow = FakeFlow(FakeRequest(path="/v1/chat/completions"), FakeResponse(text=sse_body))

    record = log_prompts.build_response_record(flow, config=config)

    assert record["raw_body"] == sse_body
    assert record["parse_error"]
    assert record["body_truncated"] is False
    assert "payload" not in record


def test_response_record_truncates_body_using_response_limit():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(
        write_response_body=True,
        max_response_body_bytes=4,
    )
    flow = FakeFlow(FakeRequest(), FakeResponse(text="abcdef"))

    record = log_prompts.build_response_record(flow, config=config)

    assert record["raw_body"] == "abcd"
    assert record["body_truncated"] is True


def test_response_record_handles_missing_response_when_enabled():
    log_prompts = load_module()
    config = log_prompts.PromptTapConfig(write_response_body=True)
    flow = FakeFlow(FakeRequest(), response=None)

    record = log_prompts.build_response_record(flow, config=config)

    assert record["status_code"] is None
    assert "payload" not in record
    assert "raw_body" not in record


def test_formats_console_request_as_pretty_block():
    log_prompts = load_module()
    record = {
        "request_id": "request-1",
        "method": "POST",
        "path": "/v1/chat/completions",
        "payload": {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
    }

    text = log_prompts.format_request_log(record)

    assert "========== PROMPT TAP REQUEST ==========" in text
    assert "request_id: request-1" in text
    assert '"messages": [' in text
    assert "========================================" in text
