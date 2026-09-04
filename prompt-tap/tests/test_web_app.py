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


def test_today_returns_recent_prompt_log_records(tmp_path):
    web_app = load_app_module()
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text(
        '\n'.join([
            '{"type":"request","request_id":"request-1"}',
            '{"type":"response","request_id":"request-1"}',
        ]),
        encoding="utf-8",
    )
    app = web_app.create_app(config=web_app.WebConfig(log_dir=tmp_path, max_turns=1))
    client = TestClient(app)

    response = client.get("/api/today")

    assert response.status_code == 200
    assert response.json()["date"] == log_date
    assert response.json()["log_exists"] is True
    assert response.json()["turns"] == [{"type": "response", "request_id": "request-1"}]
