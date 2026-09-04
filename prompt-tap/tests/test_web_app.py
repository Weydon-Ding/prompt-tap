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
