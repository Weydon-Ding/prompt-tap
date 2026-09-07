import importlib
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient


PROJECT_PATH = Path(__file__).resolve().parents[1]


def load_app_module():
    sys.path.insert(0, str(PROJECT_PATH))
    try:
        return importlib.import_module("web.app")
    finally:
        sys.path.remove(str(PROJECT_PATH))

def test_healthz_returns_ok():
    web_app = load_app_module()
    client = TestClient(web_app.create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_today_returns_empty_state_when_prompt_log_is_missing(tmp_path):
    web_app = load_app_module()
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json() == {
        "date": response.json()["date"],
        "log_exists": False,
        "turns": [],
        "message": "No Prompt Log found for today. Point your app OpenAI Base URL to http://127.0.0.1:8888/v1 to start capturing prompts.",
    }

def test_today_returns_recent_prompt_turns_from_prompt_log_records(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","timestamp":"2026-09-04T10:00:00+0800","path":"/v1/chat/completions","payload":{"messages":[{"role":"system","content":"You are helpful."},{"role":"user","content":"Hello"}]}}',
            '{"type":"response","request_id":"request-1","timestamp":"2026-09-04T10:00:01+0800","path":"/v1/chat/completions","status_code":200,"payload":{"choices":[{"message":{"role":"assistant","content":"Hi there"}}]}}',
            '{"type":"request","request_id":"request-2","timestamp":"2026-09-04T10:01:00+0800","path":"/v1/chat/completions","payload":{"messages":[{"role":"user","content":"Recent"}]}}',
            '{"type":"response","request_id":"request-2","timestamp":"2026-09-04T10:01:01+0800","path":"/v1/chat/completions","status_code":200,"payload":{"choices":[{"message":{"role":"assistant","content":"Latest"}}]}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path, max_turns=1))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json() == {
        "date": log_date,
        "log_exists": True,
        "turns": [
            {
                "request_id": "request-2",
                "timestamp": "2026-09-04T10:01:00+0800",
                "path": "/v1/chat/completions",
                "request": {
                    "type": "request",
                    "request_id": "request-2",
                    "timestamp": "2026-09-04T10:01:00+0800",
                    "path": "/v1/chat/completions",
                    "payload": {"messages": [{"role": "user", "content": "Recent"}]},
                },
                "response": {
                    "type": "response",
                    "request_id": "request-2",
                    "timestamp": "2026-09-04T10:01:01+0800",
                    "path": "/v1/chat/completions",
                    "status_code": 200,
                    "payload": {"choices": [{"message": {"role": "assistant", "content": "Latest"}}]},
                },
                "bubbles": [
                    {"role": "user", "content": "Recent"},
                    {"role": "assistant", "content": "Latest"},
                ],
            }
        ],
        "message": "Prompt Log found. Showing today's recent Prompt Turns.",
    }

def test_today_honors_zero_max_turns(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Hidden"}]}}',
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path, max_turns=0))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"] == []


def test_today_skips_unexpected_nested_prompt_log_shapes(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[null,{"role":"user","content":"Visible"}]}}',
            '{"type":"response","request_id":"request-1","payload":{"choices":[null,{"message":{"content":"Shown"}}]}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Visible"},
        {"role": "assistant", "content": "Shown"},
    ]


def test_today_skips_unexpected_record_shapes(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":{"bad":"id"},"payload":{"messages":[{"role":"user","content":"Skipped"}]}}',
            '{"type":"response","request_id":"request-1","raw_body":{"bad":"body"}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"] == [
        {
            "request_id": "request-1",
            "timestamp": None,
            "path": None,
            "request": None,
            "response": {"type": "response", "request_id": "request-1", "raw_body": {"bad": "body"}},
            "bubbles": [],
        }
    ]


def test_today_uses_latest_records_for_repeated_request_id(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"reused","timestamp":"2026-09-04T10:00:00+0800","payload":{"messages":[{"role":"user","content":"Old"}]}}',
            '{"type":"response","request_id":"reused","timestamp":"2026-09-04T10:00:01+0800","payload":{"choices":[{"message":{"content":"Old response"}}]}}',
            '{"type":"response","request_id":"later","timestamp":"2026-09-04T10:01:00+0800","payload":{"choices":[{"message":{"content":"Other"}}]}}',
            '{"type":"request","request_id":"reused","timestamp":"2026-09-04T10:02:00+0800","payload":{"messages":[{"role":"user","content":"New"}]}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path, max_turns=1))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["request_id"] == "reused"
    assert response.json()["turns"][0]["response"] is None
    assert response.json()["turns"][0]["bubbles"] == [{"role": "user", "content": "New"}]


def test_today_merges_streaming_response_into_assistant_bubble(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","timestamp":"2026-09-04T10:00:00+0800","path":"/v1/chat/completions","payload":{"messages":[{"role":"user","content":"你好"}]}}',
            '{"type":"response","request_id":"request-1","timestamp":"2026-09-04T10:00:01+0800","path":"/v1/chat/completions","status_code":200,"raw_body":"data: {\\"choices\\":[{\\"delta\\":{\\"role\\":\\"assistant\\"}}]}\\n\\ndata: {\\"choices\\":[{\\"delta\\":{\\"content\\":\\"你\\"}}]}\\n\\ndata: {\\"choices\\":[{\\"delta\\":{\\"content\\":\\"好\\"}}]}\\n\\ndata: [DONE]\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好"},
    ]


def test_today_normalizes_request_roles_and_excludes_history(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","timestamp":"2026-09-04T10:00:00+0800","payload":{"messages":[{"role":"system","content":"You are helpful."},{"role":"user","content":"Old input"},{"role":"assistant","content":"Old answer"},{"role":"tool","tool_call_id":"call-1","content":"Old tool result"},{"role":"user","content":"Current input"}],"tools":[{"type":"function","function":{"name":"lookup"}}]}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    turn = response.json()["turns"][0]
    assert turn["request"]["payload"]["messages"][2]["content"] == "Old answer"
    assert turn["bubbles"] == [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Current input"},
    ]


def test_today_collapses_repeated_system_prompts_after_first_display(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","timestamp":"2026-09-04T10:00:00+0800","payload":{"messages":[{"role":"system","content":"Same system"},{"role":"user","content":"First"}]}}',
            '{"type":"request","request_id":"request-2","timestamp":"2026-09-04T10:01:00+0800","payload":{"messages":[{"role":"system","content":"Same system"},{"role":"user","content":"Second"}]}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    turns = response.json()["turns"]
    assert turns[0]["bubbles"][0] == {"role": "system", "content": "Same system"}
    assert turns[1]["bubbles"][0] == {
        "role": "system",
        "content": "Repeated system prompt (same as earlier).",
    }


def test_today_groups_response_tool_calls_into_tool_call_bubble(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Find weather"}],"tools":[{"type":"function","function":{"name":"get_weather"}}]}}',
            '{"type":"response","request_id":"request-1","payload":{"choices":[{"message":{"role":"assistant","content":null,"tool_calls":[{"id":"call-1","type":"function","function":{"name":"get_weather","arguments":"{\\"city\\":\\"Paris\\"}"}},{"id":"call-2","type":"function","function":{"name":"get_time","arguments":"{\\"city\\":\\"Paris\\"}"}}]}}]}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Find weather"},
        {"role": "tool_call", "content": "get_weather (call-1): {\"city\":\"Paris\"}\nget_time (call-2): {\"city\":\"Paris\"}"},
    ]


def test_today_renders_raw_or_unknown_bubbles_for_non_chat_payloads(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"prompt":"Summarize this"}}',
            '{"type":"request","request_id":"request-2","payload":{"model":"embed","dimensions":3}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    turns = response.json()["turns"]
    assert turns[0]["bubbles"] == [{"role": "raw", "content": "Summarize this"}]
    assert turns[1]["bubbles"] == [{"role": "unknown", "content": '{"model": "embed", "dimensions": 3}'}]


def test_today_represents_multiple_response_choices_separately(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Give options"}]}}',
            '{"type":"response","request_id":"request-1","payload":{"choices":[{"message":{"role":"assistant","content":"First"}},{"message":{"role":"assistant","content":"Second"}}]}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Give options"},
        {"role": "assistant", "content": "Choice 1: First"},
        {"role": "assistant", "content": "Choice 2: Second"},
    ]


def test_today_extracts_anthropic_message_response_content(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","path":"/v1/messages","payload":{"messages":[{"role":"user","content":"你好"}]}}',
            '{"type":"response","request_id":"request-1","path":"/v1/messages","payload":{"type":"message","role":"assistant","content":[{"type":"text","text":"你好"}]}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好"},
    ]


def test_today_merges_anthropic_streaming_response_into_assistant_bubble(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","path":"/v1/messages","payload":{"messages":[{"role":"user","content":"你好"}]}}',
            '{"type":"response","request_id":"request-1","path":"/v1/messages","raw_body":"event: content_block_delta\\ndata: {\\"type\\":\\"content_block_delta\\",\\"index\\":0,\\"delta\\":{\\"type\\":\\"text_delta\\",\\"text\\":\\"你\\"}}\\n\\nevent: content_block_delta\\ndata: {\\"type\\":\\"content_block_delta\\",\\"index\\":0,\\"delta\\":{\\"type\\":\\"text_delta\\",\\"text\\":\\"好\\"}}\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好"},
    ]


def test_today_renders_top_level_anthropic_system_prompt(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        '{"type":"request","request_id":"request-1","path":"/v1/messages","payload":{"system":"Use terse answers.","messages":[{"role":"user","content":"Hi"}]}}',
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "system", "content": "Use terse answers."},
        {"role": "user", "content": "Hi"},
    ]


def test_today_does_not_render_tool_definition_only_payload(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        '{"type":"request","request_id":"request-1","payload":{"tools":[{"type":"function","function":{"name":"lookup"}}]}}',
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == []


def test_today_groups_streaming_tool_calls_into_tool_call_bubble(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Find weather"}]}}',
            '{"type":"response","request_id":"request-1","raw_body":"data: {\\"choices\\":[{\\"delta\\":{\\"tool_calls\\":[{\\"index\\":0,\\"id\\":\\"call-1\\",\\"function\\":{\\"name\\":\\"get_weather\\",\\"arguments\\":\\"{\\\\\\"city\\\\\\":\\"}}]}}]}\\n\\ndata: {\\"choices\\":[{\\"delta\\":{\\"tool_calls\\":[{\\"index\\":0,\\"function\\":{\\"arguments\\":\\"\\\\\\"Paris\\\\\\"}\\"}}]}}]}\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Find weather"},
        {"role": "tool_call", "content": "get_weather (call-1): {\"city\":\"Paris\"}"},
    ]


def test_today_represents_multiple_streaming_response_choices_separately(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Give options"}]}}',
            '{"type":"response","request_id":"request-1","raw_body":"data: {\\"choices\\":[{\\"index\\":0,\\"delta\\":{\\"content\\":\\"A\\"}},{\\"index\\":1,\\"delta\\":{\\"content\\":\\"B\\"}}]}\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Give options"},
        {"role": "assistant", "content": "Choice 1: A"},
        {"role": "assistant", "content": "Choice 2: B"},
    ]


def test_today_keeps_streaming_tool_calls_separate_per_choice(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Call tools"}]}}',
            '{"type":"response","request_id":"request-1","raw_body":"data: {\\"choices\\":[{\\"index\\":0,\\"delta\\":{\\"tool_calls\\":[{\\"index\\":0,\\"id\\":\\"call-x\\",\\"function\\":{\\"name\\":\\"x\\",\\"arguments\\":\\"{}\\"}}]}},{\\"index\\":1,\\"delta\\":{\\"tool_calls\\":[{\\"index\\":0,\\"id\\":\\"call-y\\",\\"function\\":{\\"name\\":\\"y\\",\\"arguments\\":\\"{}\\"}}]}}]}\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Call tools"},
        {"role": "tool_call", "content": "x (call-x): {}\ny (call-y): {}"},
    ]


def test_today_groups_anthropic_streaming_tool_use_into_tool_call_bubble(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","path":"/v1/messages","payload":{"messages":[{"role":"user","content":"Find weather"}]}}',
            '{"type":"response","request_id":"request-1","path":"/v1/messages","raw_body":"event: content_block_start\\ndata: {\\"type\\":\\"content_block_start\\",\\"index\\":1,\\"content_block\\":{\\"type\\":\\"tool_use\\",\\"id\\":\\"toolu_1\\",\\"name\\":\\"get_weather\\",\\"input\\":{}}}\\n\\nevent: content_block_delta\\ndata: {\\"type\\":\\"content_block_delta\\",\\"index\\":1,\\"delta\\":{\\"type\\":\\"input_json_delta\\",\\"partial_json\\":\\"{\\\\\\"city\\\\\\":\\"}}\\n\\nevent: content_block_delta\\ndata: {\\"type\\":\\"content_block_delta\\",\\"index\\":1,\\"delta\\":{\\"type\\":\\"input_json_delta\\",\\"partial_json\\":\\"\\\\\\"Paris\\\\\\"}\\"}}\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Find weather"},
        {"role": "tool_call", "content": "get_weather (toolu_1): {\"city\":\"Paris\"}"},
    ]


def test_today_ignores_tool_definition_only_payload_with_metadata(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        '{"type":"request","request_id":"request-1","payload":{"model":"gpt-4o","tools":[{"type":"function","function":{"name":"lookup"}}]}}',
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == []


def test_today_handles_mixed_streaming_tool_events_without_crashing(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Call mixed tools"}]}}',
            '{"type":"response","request_id":"request-1","raw_body":"event: content_block_start\\ndata: {\\"type\\":\\"content_block_start\\",\\"index\\":1,\\"content_block\\":{\\"type\\":\\"tool_use\\",\\"id\\":\\"toolu_1\\",\\"name\\":\\"anthropic_tool\\",\\"input\\":{}}}\\n\\ndata: {\\"choices\\":[{\\"index\\":0,\\"delta\\":{\\"tool_calls\\":[{\\"index\\":0,\\"id\\":\\"call-o\\",\\"function\\":{\\"name\\":\\"openai_tool\\",\\"arguments\\":\\"{}\\"}}]}}]}\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Call mixed tools"},
        {"role": "tool_call", "content": "anthropic_tool (toolu_1)\nopenai_tool (call-o): {}"},
    ]


def test_today_ignores_tool_definition_only_payload_with_common_metadata(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        '{"type":"request","request_id":"request-1","payload":{"model":"gpt-4o","tools":[{"type":"function","function":{"name":"lookup"}}],"response_format":{"type":"json_object"},"stop":["END"],"stream_options":{"include_usage":true},"metadata":{"trace":"abc"}}}',
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == []


def test_today_skips_tool_result_only_user_messages_when_selecting_current_input(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        '{"type":"request","request_id":"request-1","path":"/v1/messages","payload":{"messages":[{"role":"user","content":"Find weather"},{"role":"assistant","content":[{"type":"tool_use","id":"toolu_1","name":"get_weather","input":{"city":"Paris"}}]},{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_1","content":"Sunny"}]}]}}',
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Find weather"},
    ]


def test_today_falls_back_to_input_when_messages_have_no_user_prompt(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"assistant","content":"history"}],"input":"actual input"}}',
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "raw", "content": "actual input"},
    ]


def test_today_groups_non_streaming_tool_calls_across_choices(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Call tools"}]}}',
            '{"type":"response","request_id":"request-1","payload":{"choices":[{"message":{"role":"assistant","tool_calls":[{"id":"call-x","function":{"name":"x","arguments":"{}"}}]}},{"message":{"role":"assistant","tool_calls":[{"id":"call-y","function":{"name":"y","arguments":"{}"}}]}}]}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Call tools"},
        {"role": "tool_call", "content": "x (call-x): {}\ny (call-y): {}"},
    ]


def test_today_represents_streaming_choices_with_empty_deltas(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Give options"}]}}',
            '{"type":"response","request_id":"request-1","raw_body":"data: {\\"choices\\":[{\\"index\\":0,\\"delta\\":{\\"role\\":\\"assistant\\"}},{\\"index\\":1,\\"delta\\":{\\"content\\":\\"B\\"}}]}\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Give options"},
        {"role": "assistant", "content": "Choice 1: "},
        {"role": "assistant", "content": "Choice 2: B"},
    ]


def test_today_does_not_add_empty_assistant_bubble_for_streaming_tool_calls_with_role(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Call tool"}]}}',
            '{"type":"response","request_id":"request-1","raw_body":"data: {\\"choices\\":[{\\"index\\":0,\\"delta\\":{\\"role\\":\\"assistant\\",\\"tool_calls\\":[{\\"index\\":0,\\"id\\":\\"call-1\\",\\"function\\":{\\"name\\":\\"lookup\\",\\"arguments\\":\\"{}\\"}}]}}]}\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Call tool"},
        {"role": "tool_call", "content": "lookup (call-1): {}"},
    ]


def test_today_represents_non_assistant_response_choices(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Show choices"}]}}',
            '{"type":"response","request_id":"request-1","payload":{"choices":[{"message":{"role":"assistant","content":"A"}},{"message":{"role":"tool","content":"B"}}]}}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Show choices"},
        {"role": "assistant", "content": "Choice 1: A"},
        {"role": "tool", "content": "Choice 2: B"},
    ]


def test_today_preserves_streaming_choice_numeric_order_above_ten(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    choices = ",".join(
        f'{{"index":{index},"delta":{{"content":"{index}"}}}}'
        for index in range(12)
    )
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Many choices"}]}}',
            '{"type":"response","request_id":"request-1","raw_body":"data: {\\"choices\\":[' + choices.replace('"', '\\"') + ']}\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"][1:] == [
        {"role": "assistant", "content": f"Choice {index + 1}: {index}"}
        for index in range(12)
    ]


def test_today_represents_fully_empty_streaming_choices(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Give options"}]}}',
            '{"type":"response","request_id":"request-1","raw_body":"data: {\\"choices\\":[{\\"index\\":0,\\"delta\\":{}},{\\"index\\":1,\\"delta\\":{\\"content\\":\\"B\\"}}]}\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Give options"},
        {"role": "assistant", "content": "Choice 1: "},
        {"role": "assistant", "content": "Choice 2: B"},
    ]


def test_today_does_not_crash_on_streaming_choice_null_index(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        "\n".join([
            '{"type":"request","request_id":"request-1","payload":{"messages":[{"role":"user","content":"Give options"}]}}',
            '{"type":"response","request_id":"request-1","raw_body":"data: {\\"choices\\":[{\\"index\\":null,\\"delta\\":{\\"content\\":\\"A\\"}},{\\"index\\":null,\\"delta\\":{\\"content\\":\\"B\\"}}]}\\n"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "user", "content": "Give options"},
        {"role": "assistant", "content": "Choice 1: A"},
        {"role": "assistant", "content": "Choice 2: B"},
    ]


def test_today_ignores_tool_definition_payload_with_empty_messages(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        '{"type":"request","request_id":"request-1","payload":{"messages":[],"tools":[{"type":"function","function":{"name":"lookup"}}],"seed":1,"service_tier":"auto"}}',
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == []


def test_today_unknown_payload_omits_tool_definitions_from_bubble(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        '{"type":"request","request_id":"request-1","payload":{"tools":[{"type":"function","function":{"name":"lookup"}}],"metadata":{"trace":"abc"},"custom":"value"}}',
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {"role": "unknown", "content": '{"custom": "value"}'},
    ]


def test_today_does_not_skip_user_message_with_mixed_tool_result_content(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        '{"type":"request","request_id":"request-1","path":"/v1/messages","payload":{"messages":[{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_1","content":"Sunny"},"Now answer me"]}]}}',
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["turns"][0]["bubbles"] == [
        {
            "role": "user",
            "content": '{"type": "tool_result", "tool_use_id": "toolu_1", "content": "Sunny"}\n"Now answer me"',
        },
    ]
