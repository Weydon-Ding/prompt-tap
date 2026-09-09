import asyncio
import importlib
import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient


PROJECT_PATH = Path(__file__).resolve().parents[1]


def load_module(name):
    sys.path.insert(0, str(PROJECT_PATH))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(PROJECT_PATH))


def test_broadcaster_delivers_each_update_to_all_subscribers():
    live_updates = load_module("web.live_updates")

    async def exercise():
        broadcaster = live_updates.PromptTurnBroadcaster()
        async with broadcaster.subscribe() as first, broadcaster.subscribe() as second:
            update = {"request_id": "request-1", "bubbles": []}
            await broadcaster.publish(update)

            assert await first.get() == update
            assert await second.get() == update
            assert broadcaster.subscriber_count == 2

        assert broadcaster.subscriber_count == 0

    asyncio.run(exercise())


def test_log_tailer_publishes_added_and_updated_complete_turns(tmp_path):
    live_updates = load_module("web.live_updates")
    log_reader = load_module("web.log_reader")
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    request = {
        "type": "request",
        "request_id": "request-1",
        "timestamp": f"{log_date}T10:00:00+0800",
        "payload": {"messages": [{"role": "user", "content": "Hello"}]},
    }
    response = {
        "type": "response",
        "request_id": "request-1",
        "timestamp": f"{log_date}T10:00:01+0800",
        "payload": {"choices": [{"message": {"content": "Hi"}}]},
    }
    log_path.write_text(json.dumps(request) + "\n", encoding="utf-8")

    async def exercise():
        broadcaster = live_updates.PromptTurnBroadcaster()
        tailer = live_updates.PromptLogTailer(
            log_dir=tmp_path,
            max_turns=10,
            timezone="Asia/Shanghai",
            broadcaster=broadcaster,
        )
        async with broadcaster.subscribe() as updates:
            await tailer.poll_once()
            pending_turn = await updates.get()

            with log_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(response) + "\n")

            await tailer.poll_once()
            complete_turn = await updates.get()

        assert pending_turn["request_id"] == "request-1"
        assert pending_turn["status"] in {"pending", "missing_response"}
        assert pending_turn["bubbles"][-1]["role"] == "pending"
        assert complete_turn["request_id"] == "request-1"
        assert complete_turn["status"] == "complete"
        assert complete_turn["bubbles"][-1] == {"role": "assistant", "content": "Hi"}

    asyncio.run(exercise())


def test_log_tailer_only_publishes_turns_changed_since_previous_poll(tmp_path):
    live_updates = load_module("web.live_updates")
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    first_request = {
        "type": "request",
        "request_id": "request-1",
        "payload": {"messages": [{"role": "user", "content": "First"}]},
    }
    second_request = {
        "type": "request",
        "request_id": "request-2",
        "payload": {"messages": [{"role": "user", "content": "Second"}]},
    }
    log_path.write_text(json.dumps(first_request) + "\n", encoding="utf-8")

    async def exercise():
        broadcaster = live_updates.PromptTurnBroadcaster()
        tailer = live_updates.PromptLogTailer(
            log_dir=tmp_path,
            max_turns=10,
            timezone="Asia/Shanghai",
            broadcaster=broadcaster,
        )
        async with broadcaster.subscribe() as updates:
            await tailer.poll_once()
            assert (await updates.get())["request_id"] == "request-1"

            with log_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(second_request) + "\n")

            await tailer.poll_once()
            assert (await updates.get())["request_id"] == "request-2"
            assert updates.empty()

    asyncio.run(exercise())


def test_app_uses_one_shared_broadcaster_for_all_sse_connections(tmp_path):
    web_app = load_module("web.app")
    live_updates = load_module("web.live_updates")
    broadcaster = live_updates.PromptTurnBroadcaster()

    app = web_app.create_app(
        config=web_app.WebConfig(log_dir=tmp_path),
        broadcaster=broadcaster,
        start_tailer=False,
    )

    assert app.state.prompt_turn_broadcaster is broadcaster
    assert app.state.prompt_log_tailer.broadcaster is broadcaster


def test_log_tailer_publishes_rewritten_turn_when_record_count_is_unchanged(tmp_path):
    live_updates = load_module("web.live_updates")
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    original = {
        "type": "request",
        "request_id": "request-1",
        "payload": {"messages": [{"role": "user", "content": "First"}]},
    }
    rewritten = {
        "type": "request",
        "request_id": "request-1",
        "payload": {"messages": [{"role": "user", "content": "Other"}]},
    }
    log_path.write_text(json.dumps(original) + "\n", encoding="utf-8")

    async def exercise():
        broadcaster = live_updates.PromptTurnBroadcaster()
        tailer = live_updates.PromptLogTailer(
            log_dir=tmp_path,
            max_turns=10,
            timezone="Asia/Shanghai",
            broadcaster=broadcaster,
        )
        async with broadcaster.subscribe() as updates:
            await tailer.poll_once()
            await updates.get()

            log_path.write_text(json.dumps(rewritten) + "\n", encoding="utf-8")
            await tailer.poll_once()

            assert (await updates.get())["bubbles"][0] == {
                "role": "user",
                "content": "Other",
            }

    asyncio.run(exercise())


def test_log_tailer_retries_an_incomplete_trailing_record(tmp_path):
    live_updates = load_module("web.live_updates")
    log_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    log_path = tmp_path / f"prompt-{log_date}.jsonl"
    log_path.write_text('{"type":"request"', encoding="utf-8")

    async def exercise():
        broadcaster = live_updates.PromptTurnBroadcaster()
        tailer = live_updates.PromptLogTailer(
            log_dir=tmp_path,
            max_turns=10,
            timezone="Asia/Shanghai",
            broadcaster=broadcaster,
        )
        async with broadcaster.subscribe() as updates:
            await tailer.poll_once()
            assert updates.empty()

            record = {
                "type": "request",
                "request_id": "request-1",
                "payload": {"messages": [{"role": "user", "content": "Recovered"}]},
            }
            log_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            await tailer.poll_once()

            assert (await updates.get())["request_id"] == "request-1"

    asyncio.run(exercise())


def test_sse_event_contains_a_complete_prompt_turn():
    live_updates = load_module("web.live_updates")
    turn = {
        "request_id": "request-1",
        "status": "complete",
        "bubbles": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
    }

    event = live_updates.encode_prompt_turn_event(turn)

    assert event == (
        "event: prompt_turn\n"
        'data: {"request_id":"request-1","status":"complete","bubbles":'
        '[{"role":"user","content":"Hello"},{"role":"assistant","content":"Hi"}]}\n\n'
    )
