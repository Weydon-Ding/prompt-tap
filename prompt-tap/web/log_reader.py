import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


EMPTY_LOG_MESSAGE = (
    "No Prompt Log found for today. "
    "Point your app OpenAI Base URL to http://127.0.0.1:8888/v1 to start capturing prompts."
)


RECENT_TURNS_MESSAGE = "Prompt Log found. Showing today's recent Prompt Turns."


def current_date(timezone: str):
    return datetime.now(ZoneInfo(timezone)).date()


def today_log_path(log_dir: Path, timezone: str, today=None):
    if today is None:
        today = current_date(timezone)

    return log_dir / f"prompt-{today.isoformat()}.jsonl"


def read_prompt_log_records(log_path: Path):
    records = []

    with log_path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            records.append(json.loads(line))

    return records


def as_dict(value):
    if isinstance(value, dict):
        return value

    return {}


def dict_items(value):
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]


def extract_request_bubbles(record):
    payload = as_dict(record.get("payload"))
    bubbles = []

    for message in dict_items(payload.get("messages")):
        if message.get("role") != "user":
            continue

        bubbles.append({
            "role": "user",
            "content": normalize_content(message.get("content")),
        })

    prompt = payload.get("prompt")
    if prompt is not None:
        bubbles.append({"role": "user", "content": normalize_content(prompt)})

    user_input = payload.get("input")
    if user_input is not None:
        bubbles.append({"role": "user", "content": normalize_content(user_input)})

    return bubbles


def extract_response_bubbles(record):
    content = extract_response_content(record)
    if content == "":
        return []

    return [{"role": "assistant", "content": content}]


def extract_response_content(record):
    payload = as_dict(record.get("payload"))
    if payload:
        messages = []
        for choice in dict_items(payload.get("choices")):
            message = as_dict(choice.get("message"))
            content = message.get("content")
            if content:
                messages.append(normalize_content(content))

        if messages:
            return "\n".join(messages)

    raw_body = record.get("raw_body")
    if isinstance(raw_body, str) and raw_body:
        return extract_sse_content(raw_body)

    return ""


def extract_sse_content(raw_body: str):
    content = []

    for line in raw_body.splitlines():
        if not line.startswith("data:"):
            continue

        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue

        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue

        for choice in dict_items(as_dict(event).get("choices")):
            delta = as_dict(choice.get("delta"))
            piece = delta.get("content")
            if piece:
                content.append(str(piece))

    return "".join(content)


def normalize_content(content):
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        return "\n".join(parts)

    return json.dumps(content, ensure_ascii=False)


def to_prompt_turn(turn):
    request_record = turn.get("request")
    response_record = turn.get("response")
    bubbles = []

    if request_record:
        bubbles.extend(extract_request_bubbles(request_record))

    if response_record:
        bubbles.extend(extract_response_bubbles(response_record))

    return {
        "request_id": turn["request_id"],
        "timestamp": turn.get("timestamp"),
        "path": turn.get("path"),
        "request": request_record,
        "response": response_record,
        "bubbles": bubbles,
    }


def merge_prompt_turns(records, max_turns):
    if max_turns <= 0:
        return []

    turns_by_id = {}

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue

        request_id = record.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            continue

        turn = turns_by_id.setdefault(
            request_id,
            {
                "request_id": request_id,
                "timestamp": None,
                "path": None,
                "request": None,
                "response": None,
                "last_index": index,
            },
        )
        turn["last_index"] = index

        if record.get("type") == "request":
            turn["request"] = record
            turn["response"] = None
            turn["timestamp"] = record.get("timestamp") or turn.get("timestamp")
            turn["path"] = record.get("path") or turn.get("path")
        elif record.get("type") == "response":
            turn["response"] = record
            turn["timestamp"] = turn.get("timestamp") or record.get("timestamp")
            turn["path"] = turn.get("path") or record.get("path")

    turns = sorted(turns_by_id.values(), key=lambda turn: turn["last_index"])
    return [to_prompt_turn(turn) for turn in turns[-max_turns:]]


def read_today(log_dir: Path, max_turns: int, timezone: str, today=None):
    log_date = today or current_date(timezone)
    log_path = today_log_path(log_dir, timezone, log_date)

    if not log_path.exists():
        return {
            "date": log_date.isoformat(),
            "log_exists": False,
            "turns": [],
            "message": EMPTY_LOG_MESSAGE,
        }

    records = read_prompt_log_records(log_path)
    turns = merge_prompt_turns(records, max_turns)

    return {
        "date": log_date.isoformat(),
        "log_exists": True,
        "turns": turns,
        "message": RECENT_TURNS_MESSAGE,
    }
