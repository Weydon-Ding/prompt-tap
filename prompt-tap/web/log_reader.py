import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


EMPTY_LOG_MESSAGE = (
    "No Prompt Log found for today. "
    "Point your app OpenAI Base URL to http://127.0.0.1:8888/v1 to start capturing prompts."
)


RECENT_TURNS_MESSAGE = "Prompt Log found. Showing today's recent Prompt Turns."
REPEATED_SYSTEM_PROMPT_MESSAGE = "Repeated system prompt (same as earlier)."
PENDING_RESPONSE_MESSAGE = "Waiting for response."
MISSING_RESPONSE_MESSAGE = "Response has been pending for more than 30 seconds. The response record may be missing."
DISABLED_RESPONSE_BODY_MESSAGE = "Response body capture is disabled. Enable WRITE_RESPONSE_BODY to inspect assistant content."
MISSING_RESPONSE_AFTER_SECONDS = 30
KNOWN_EMPTY_SSE_EVENT_TYPES = {
    "content_block_stop",
    "message_delta",
    "message_start",
    "message_stop",
    "ping",
}
NON_BUBBLE_REQUEST_KEYS = {
    "max_completion_tokens",
    "max_tokens",
    "model",
    "frequency_penalty",
    "logprobs",
    "metadata",
    "messages",
    "n",
    "parallel_tool_calls",
    "presence_penalty",
    "reasoning_effort",
    "response_format",
    "seed",
    "service_tier",
    "stop",
    "store",
    "stream",
    "stream_options",
    "temperature",
    "tool_choice",
    "tools",
    "top_p",
}


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


def extract_request_bubbles(record, seen_system_prompts=None):
    payload = as_dict(record.get("payload"))
    bubbles = []
    messages = dict_items(payload.get("messages"))

    top_level_system = payload.get("system")
    if top_level_system is not None:
        append_system_bubble(bubbles, top_level_system, seen_system_prompts)

    if messages:
        for message in messages:
            if message.get("role") == "system":
                append_system_bubble(bubbles, message.get("content"), seen_system_prompts)

        user_selected = False
        for message in reversed(messages):
            if message.get("role") == "user" and not is_tool_result_message(message):
                bubbles.append({
                    "role": "user",
                    "content": normalize_content(message.get("content")),
                })
                user_selected = True
                break

        if not user_selected:
            append_raw_input_bubbles(bubbles, payload)

        return bubbles

    append_raw_input_bubbles(bubbles, payload)

    if not bubbles and payload:
        unknown_payload = displayable_unknown_payload(payload)
        if unknown_payload:
            bubbles.append({"role": "unknown", "content": normalize_content(unknown_payload)})

    return bubbles


def displayable_unknown_payload(payload):
    if "tools" not in payload and "messages" not in payload:
        return payload

    unknown_payload = {
        key: value for key, value in payload.items() if key not in NON_BUBBLE_REQUEST_KEYS
    }
    if unknown_payload:
        return unknown_payload

    return None


def append_raw_input_bubbles(bubbles, payload):
    prompt = payload.get("prompt")
    if prompt is not None:
        bubbles.append({"role": "raw", "content": normalize_content(prompt)})

    user_input = payload.get("input")
    if user_input is not None:
        bubbles.append({"role": "raw", "content": normalize_content(user_input)})


def append_system_bubble(bubbles, content, seen_system_prompts=None):
    content = normalize_content(content)
    if seen_system_prompts is None or not content:
        display_content = content
    elif content in seen_system_prompts:
        display_content = REPEATED_SYSTEM_PROMPT_MESSAGE
    else:
        seen_system_prompts.add(content)
        display_content = content

    bubbles.append({"role": "system", "content": display_content})


def extract_response_view(record):
    if is_error_status_code(record.get("status_code")):
        return [error_bubble(record)], []

    payload = as_dict(record.get("payload"))
    if payload:
        choice_bubbles = extract_choice_bubbles(payload)
        if choice_bubbles:
            return choice_bubbles, []

        anthropic_bubbles = extract_anthropic_response_bubbles(payload)
        if anthropic_bubbles:
            return anthropic_bubbles, []

    raw_body = record.get("raw_body")
    if isinstance(raw_body, str) and raw_body:
        return parse_sse_bubbles(raw_body)

    return [], []


def is_error_status_code(status_code):
    return isinstance(status_code, int) and 400 <= status_code <= 599



def error_bubble(record):
    status_code = record.get("status_code")
    content = f"HTTP {status_code} response from New API."
    raw_body = record.get("raw_body")
    if isinstance(raw_body, str) and raw_body:
        content = f"{content}\n{raw_body}"
    else:
        payload = as_dict(record.get("payload"))
        if payload:
            content = f"{content}\n{normalize_content(payload)}"

    return {"role": "error", "content": content}


def extract_choice_bubbles(payload):
    choices = dict_items(payload.get("choices"))
    if not choices:
        return []

    bubbles = []
    grouped_tool_calls = []
    multiple_choices = len(choices) > 1

    for index, choice in enumerate(choices, start=1):
        message = as_dict(choice.get("message"))
        if not message:
            message = choice

        grouped_tool_calls.extend(dict_items(message.get("tool_calls")))

        if "content" in message:
            content = normalize_content(message.get("content"))
        else:
            content = normalize_content(message.get("text"))

        if content:
            if multiple_choices:
                content = f"Choice {index}: {content}"
            role = message.get("role")
            bubbles.append({
                "role": role if isinstance(role, str) and role else "assistant",
                "content": content,
            })
        elif not message.get("tool_calls"):
            fallback = normalize_content(choice)
            if fallback:
                if multiple_choices:
                    fallback = f"Choice {index}: {fallback}"
                bubbles.append({"role": "assistant", "content": fallback})

    tool_calls = normalize_tool_call_items(grouped_tool_calls)
    if tool_calls:
        bubbles.insert(0, {"role": "tool_call", "content": tool_calls})

    return bubbles


def extract_anthropic_response_bubbles(payload):
    content = payload.get("content")
    if content is None:
        return []

    bubbles = []
    text_content = normalize_text_blocks(content)
    tool_calls = normalize_tool_use_blocks(content)

    if text_content:
        role = payload.get("role")
        bubbles.append({
            "role": role if isinstance(role, str) and role else "assistant",
            "content": text_content,
        })

    if tool_calls:
        bubbles.append({"role": "tool_call", "content": tool_calls})

    return bubbles


def extract_response_content(record):
    bubbles = [
        bubble
        for bubble in extract_response_view(record)[0]
        if bubble.get("role") == "assistant"
    ]
    return "\n".join(bubble["content"] for bubble in bubbles)


def extract_sse_content(raw_body: str):
    return "\n".join(
        bubble["content"]
        for bubble in parse_sse_bubbles(raw_body)[0]
        if bubble.get("role") == "assistant"
    )


def display_path(path):
    if not isinstance(path, str) or not path:
        return None

    parsed = urlsplit(path)
    return parsed.path or path.split("?", 1)[0]


def request_model(record):
    payload = as_dict(record.get("payload"))
    model = payload.get("model")
    if isinstance(model, str) and model:
        return model

    return None


def parse_timestamp(value):
    if not isinstance(value, str) or not value:
        return None

    normalized = value
    if len(normalized) >= 5 and normalized[-5] in {"+", "-"} and normalized[-3] != ":":
        normalized = f"{normalized[:-2]}:{normalized[-2:]}"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def pending_seconds(turn, now=None):
    timestamp = parse_timestamp(turn.get("timestamp"))
    if timestamp is None:
        return None

    if now is None:
        now = datetime.now(timestamp.tzinfo)
        if timestamp.date() != now.date():
            return None
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timestamp.tzinfo)
    else:
        now = now.astimezone(timestamp.tzinfo)

    return (now - timestamp).total_seconds()


def turn_status(turn, now=None):
    response_record = turn.get("response")
    if not response_record:
        seconds = pending_seconds(turn, now)
        if seconds is not None and seconds > MISSING_RESPONSE_AFTER_SECONDS:
            return "missing_response"
        return "pending"

    if is_error_status_code(response_record.get("status_code")):
        return "error"

    if response_record.get("response_body_capture") is False:
        return "response_body_disabled"

    return "complete"


def turn_metadata(turn, status):
    response_record = turn.get("response") or {}
    request_record = turn.get("request") or {}
    return {
        "model": request_model(request_record),
        "status": status,
        "duration_ms": response_record.get("duration_ms"),
        "display_path": display_path(turn.get("path")),
    }


def with_request_id(warning, request_id):
    return {"request_id": request_id, **warning}


def parse_sse_bubbles(raw_body: str):
    choice_content = {}
    tool_calls = {}
    anthropic_text = []
    warnings = []

    for line in raw_body.splitlines():
        if not line.startswith("data:"):
            continue

        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue

        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            warnings.append({
                "message": "SSE chunk could not be parsed as JSON.",
                "chunk": data,
            })
            continue

        event = as_dict(event)
        recognized = is_known_empty_sse_event(event)
        if event.get("type") == "content_block_start":
            recognized = True
            content_block = as_dict(event.get("content_block"))
            if content_block.get("type") == "tool_use":
                block_index = value_or_default(event.get("index"), len(tool_calls))
                tool_calls[("anthropic", sort_key(block_index))] = {
                    "id": content_block.get("id"),
                    "name": content_block.get("name"),
                    "input": normalize_content(content_block.get("input")) if content_block.get("input") else "",
                }
            continue

        delta = as_dict(event.get("delta"))
        if event.get("type") == "content_block_delta":
            recognized = True
            piece = delta.get("text")
            if piece:
                anthropic_text.append(str(piece))

            partial_json = delta.get("partial_json")
            if partial_json:
                block_index = value_or_default(event.get("index"), len(tool_calls))
                tool_call = tool_calls.setdefault(("anthropic", sort_key(block_index)), {"input": ""})
                tool_call["input"] = tool_call.get("input", "") + str(partial_json)
            continue

        choices = dict_items(event.get("choices"))
        choices_recognized = False
        for choice_position, choice in enumerate(choices):
            choice_index = value_or_default(choice.get("index"), choice_position)
            delta = as_dict(choice.get("delta"))
            choice_recognized = is_recognized_choice_delta(delta) or choice.get("finish_reason") is not None
            choices_recognized = choices_recognized or choice_recognized
            if choice_recognized and (
                "tool_calls" not in delta
                or "content" in delta
                or choice.get("finish_reason") is not None
            ):
                choice_content.setdefault(choice_index, [])

            piece = delta.get("content")
            if piece:
                choice_content.setdefault(choice_index, []).append(str(piece))

            if "tool_calls" in delta:
                merge_streaming_tool_calls(tool_calls, delta.get("tool_calls"), choice_index)

        recognized = recognized or choices_recognized
        if not recognized:
            warnings.append({
                "message": "SSE chunk did not match a recognized response shape.",
                "chunk": data,
            })

    bubbles = []
    if anthropic_text:
        bubbles.append({"role": "assistant", "content": "".join(anthropic_text)})

    if tool_calls:
        bubbles.append({
            "role": "tool_call",
            "content": normalize_tool_calls([
                tool_call for _, tool_call in sorted(tool_calls.items())
            ]),
        })

    if choice_content:
        multiple_choices = len(choice_content) > 1
        for position, choice_index in enumerate(sorted(choice_content, key=sort_key), start=1):
            content = "".join(choice_content[choice_index])
            if multiple_choices:
                content = f"Choice {position}: {content}"
            bubbles.append({"role": "assistant", "content": content})

    return bubbles, warnings


def is_known_empty_sse_event(event):
    if event.get("type") in KNOWN_EMPTY_SSE_EVENT_TYPES:
        return True

    return event.get("choices") == [] and "usage" in event



def is_recognized_choice_delta(delta):
    return not delta or any(key in delta for key in ("content", "role", "tool_calls"))


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


def value_or_default(value, default):
    if value is None:
        return default

    return value


def sort_key(value):
    if isinstance(value, int):
        return ("int", value)

    return (str(type(value).__name__), str(value))


def is_tool_result_message(message):
    content = message.get("content")
    if isinstance(content, list):
        return bool(content) and all(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        )

    return isinstance(content, dict) and content.get("type") == "tool_result"


def normalize_text_blocks(content):
    if not isinstance(content, list):
        return normalize_content(content)

    parts = []
    for item in content:
        if not isinstance(item, dict):
            parts.append(json.dumps(item, ensure_ascii=False))
            continue

        if item.get("type") == "tool_use":
            continue

        if "text" in item:
            parts.append(str(item["text"]))
        else:
            parts.append(json.dumps(item, ensure_ascii=False))

    return "\n".join(parts)


def normalize_tool_calls(tool_calls):
    return normalize_tool_call_items(dict_items(tool_calls))


def normalize_tool_call_items(tool_calls):
    calls = []
    for tool_call in tool_calls:
        calls.append(normalize_tool_call(tool_call))

    return "\n".join(call for call in calls if call)


def normalize_tool_call(tool_call):
    call_id = tool_call.get("id")
    function = as_dict(tool_call.get("function"))
    name = function.get("name") or tool_call.get("name") or "unknown_tool"
    arguments = function.get("arguments")
    if arguments is None:
        arguments = tool_call.get("input")

    parts = [str(name)]
    if call_id:
        parts.append(f"({call_id})")

    prefix = " ".join(parts)
    content = normalize_content(arguments)
    if content:
        return f"{prefix}: {content}"

    return prefix


def normalize_tool_use_blocks(content):
    return normalize_tool_call_items([
        block for block in dict_items(content) if block.get("type") == "tool_use"
    ])


def merge_streaming_tool_calls(tool_calls, delta_tool_calls, choice_index=0):
    for delta_tool_call in dict_items(delta_tool_calls):
        tool_index = value_or_default(delta_tool_call.get("index"), len(tool_calls))
        index = ("openai", sort_key(choice_index), sort_key(tool_index))
        tool_call = tool_calls.setdefault(index, {"function": {}})

        call_id = delta_tool_call.get("id")
        if call_id:
            tool_call["id"] = call_id

        name = delta_tool_call.get("name")
        if name:
            tool_call["name"] = name

        function_delta = as_dict(delta_tool_call.get("function"))
        function = tool_call.setdefault("function", {})
        function_name = function_delta.get("name")
        if function_name:
            function["name"] = function_name

        arguments = function_delta.get("arguments")
        if arguments:
            function["arguments"] = function.get("arguments", "") + str(arguments)

        input_delta = delta_tool_call.get("input")
        if input_delta:
            tool_call["input"] = tool_call.get("input", "") + normalize_content(input_delta)


def to_prompt_turn(turn, seen_system_prompts=None, now=None):
    request_record = turn.get("request")
    response_record = turn.get("response")
    status = turn_status(turn, now)
    bubbles = []

    if request_record:
        bubbles.extend(extract_request_bubbles(request_record, seen_system_prompts))

    warnings = []
    if response_record:
        response_bubbles, warnings = extract_response_view(response_record)
        bubbles.extend(response_bubbles)
        if status == "response_body_disabled":
            bubbles.append({"role": "assistant", "content": DISABLED_RESPONSE_BODY_MESSAGE})
    elif status == "missing_response":
        bubbles.append({"role": "pending", "content": MISSING_RESPONSE_MESSAGE})
    else:
        bubbles.append({"role": "pending", "content": PENDING_RESPONSE_MESSAGE})

    warnings = [with_request_id(warning, turn["request_id"]) for warning in warnings]

    return {
        "request_id": turn["request_id"],
        "timestamp": turn.get("timestamp"),
        "path": turn.get("path"),
        "request": request_record,
        "response": response_record,
        "status": status,
        "metadata": turn_metadata(turn, status),
        "warnings": warnings,
        "bubbles": bubbles,
    }


def merge_prompt_turns(records, max_turns, now=None):
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
    selected_turns = turns[-max_turns:]
    seen_system_prompts = set()
    return [to_prompt_turn(turn, seen_system_prompts, now) for turn in selected_turns]


def read_today(log_dir: Path, max_turns: int, timezone: str, today=None):
    log_date = today or current_date(timezone)
    log_path = today_log_path(log_dir, timezone, log_date)

    if not log_path.exists():
        return {
            "date": log_date.isoformat(),
            "log_exists": False,
            "turns": [],
            "warnings": [],
            "message": EMPTY_LOG_MESSAGE,
        }

    records = read_prompt_log_records(log_path)
    turns = merge_prompt_turns(records, max_turns)
    warnings = [warning for turn in turns for warning in turn.get("warnings", [])]

    return {
        "date": log_date.isoformat(),
        "log_exists": True,
        "turns": turns,
        "warnings": warnings,
        "message": RECENT_TURNS_MESSAGE,
    }
