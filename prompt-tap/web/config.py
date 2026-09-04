import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WebConfig:
    log_dir: Path = Path(os.getenv("LOG_DIR", "/logs"))
    max_turns: int = int(os.getenv("UI_MAX_TURNS", "200"))
    tail_interval_seconds: float = float(os.getenv("UI_TAIL_INTERVAL_SECONDS", "1"))
    timezone: str = os.getenv("TZ", "Asia/Shanghai")
