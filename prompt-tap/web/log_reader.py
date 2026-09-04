import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


EMPTY_LOG_MESSAGE = (
    "No Prompt Log found for today. "
    "Point your app OpenAI Base URL to http://127.0.0.1:8888/v1 to start capturing prompts."
)


def current_date(timezone: str):
    return datetime.now(ZoneInfo(timezone)).date()


def today_log_path(log_dir: Path, timezone: str, today=None):
    if today is None:
        today = current_date(timezone)

    return log_dir / f"prompt-{today.isoformat()}.jsonl"


def read_prompt_log_records(log_path: Path, max_records: int):
    records = []

    with log_path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            records.append(json.loads(line))

    return records[-max_records:]


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

    records = read_prompt_log_records(log_path, max_turns)

    return {
        "date": log_date.isoformat(),
        "log_exists": True,
        "turns": records,
        "message": "Prompt Log found. Prompt Turn normalization will be added in a later slice.",
    }
