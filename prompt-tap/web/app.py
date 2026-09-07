from fastapi import FastAPI

try:
    from .config import WebConfig
    from .log_reader import read_today
except ImportError:
    from config import WebConfig
    from log_reader import read_today


DEFAULT_CONFIG = WebConfig()


def create_app(config=DEFAULT_CONFIG):
    app = FastAPI(title="Prompt Tap Web UI")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/api/today")
    def today():
        return read_today(config.log_dir, config.max_turns, config.timezone)

    @app.get("/api/config")
    def web_config():
        return {"tail_interval_seconds": config.tail_interval_seconds}

    return app


app = create_app()
