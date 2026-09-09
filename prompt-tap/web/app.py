import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

try:
    from .config import WebConfig
    from .live_updates import PromptLogTailer, PromptTurnBroadcaster, encode_prompt_turn_event
    from .log_reader import read_today
except ImportError:
    from config import WebConfig
    from live_updates import PromptLogTailer, PromptTurnBroadcaster, encode_prompt_turn_event
    from log_reader import read_today


DEFAULT_CONFIG = WebConfig()


def create_app(config=DEFAULT_CONFIG, broadcaster=None, start_tailer=True):
    broadcaster = broadcaster or PromptTurnBroadcaster()
    tailer = PromptLogTailer(
        config.log_dir,
        config.max_turns,
        config.timezone,
        broadcaster,
    )

    @asynccontextmanager
    async def lifespan(app):
        task = None
        if start_tailer:
            task = asyncio.create_task(tailer.run(config.tail_interval_seconds))
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(title="Prompt Tap Web UI", lifespan=lifespan)
    app.state.prompt_turn_broadcaster = broadcaster
    app.state.prompt_log_tailer = tailer

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/api/today")
    def today():
        return read_today(config.log_dir, config.max_turns, config.timezone)

    @app.get("/api/config")
    def web_config():
        return {"tail_interval_seconds": config.tail_interval_seconds}

    @app.get("/api/events")
    async def events():
        async def stream():
            async with broadcaster.subscribe() as updates:
                while True:
                    turn = await updates.get()
                    yield encode_prompt_turn_event(turn)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app


app = create_app()
