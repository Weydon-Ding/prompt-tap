import asyncio
import json
from contextlib import asynccontextmanager

from .log_reader import merge_prompt_turns, read_prompt_log_records, today_log_path


def encode_prompt_turn_event(turn):
    data = json.dumps(turn, ensure_ascii=False, separators=(",", ":"))
    return f"event: prompt_turn\ndata: {data}\n\n"


class PromptLogTailer:
    def __init__(self, log_dir, max_turns, timezone, broadcaster):
        self.log_dir = log_dir
        self.max_turns = max_turns
        self.timezone = timezone
        self.broadcaster = broadcaster
        self._log_path = None
        self._file_signature = None
        self._record_count = 0

    async def run(self, interval_seconds):
        while True:
            await self.poll_once()
            await asyncio.sleep(interval_seconds)

    async def poll_once(self):
        log_path = today_log_path(self.log_dir, self.timezone)
        stat = log_path.stat() if log_path.exists() else None
        file_signature = (stat.st_size, stat.st_mtime_ns) if stat else None
        if log_path == self._log_path and file_signature == self._file_signature:
            return

        try:
            records = read_prompt_log_records(log_path) if stat else []
        except json.JSONDecodeError:
            return

        file_was_rewritten = (
            log_path == self._log_path
            and self._file_signature is not None
            and len(records) == self._record_count
            and file_signature != self._file_signature
        )
        if log_path != self._log_path or len(records) < self._record_count or file_was_rewritten:
            changed_records = records
        else:
            changed_records = records[self._record_count:]

        self._log_path = log_path
        self._file_signature = file_signature
        self._record_count = len(records)
        changed_request_ids = {
            record.get("request_id")
            for record in changed_records
            if isinstance(record, dict) and isinstance(record.get("request_id"), str)
        }
        turns = merge_prompt_turns(records, self.max_turns)
        for turn in turns:
            if turn["request_id"] in changed_request_ids:
                await self.broadcaster.publish(turn)


class PromptTurnBroadcaster:
    def __init__(self):
        self._subscribers = set()

    @property
    def subscriber_count(self):
        return len(self._subscribers)

    @asynccontextmanager
    async def subscribe(self):
        queue = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.remove(queue)

    async def publish(self, turn):
        for queue in tuple(self._subscribers):
            await queue.put(turn)
