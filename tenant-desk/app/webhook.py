"""FastAPI app that receives WhatsApp webhooks from Meta.

GET  /webhook  Meta's one-time verification: echo hub.challenge if the
               verify token matches, else 403.
POST /webhook  Check the signature (401 if bad or missing), parse the
               payload, handle each message. Returns 200 whenever the
               signature is valid, even if one message fails, so Meta
               does not keep retrying; failures are logged.

Dependencies (repository, WhatsApp client, transcriber, clock) are
built in build_deps() from settings. Tests call create_app(deps) with
fakes instead.

Run locally:  .venv\\Scripts\\python -m app.webhook
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool

from app.parser import parse_webhook
from app.repo_sqlite import SqliteRepository
from app.service import handle_message
from app.signature import verify_signature
from app.transcriber import FakeTranscriber, FasterWhisperTranscriber
from app.whatsapp_client import WhatsAppClient
from shared.config import load_env, optional, require
from shared.logging_setup import get_logger

PROJECT_DIR = Path(__file__).resolve().parents[1]
log = get_logger("tenant_desk.webhook")


@dataclass
class Settings:
    whatsapp_token: str
    phone_number_id: str
    app_secret: str
    verify_token: str
    db_path: str
    media_dir: str
    transcriber: str  # "fake" or "whisper"
    port: int


@dataclass
class Deps:
    repo: object
    wa_client: object
    transcriber: object
    media_dir: str
    app_secret: str
    verify_token: str
    clock: Callable[[], datetime]


def load_settings():
    """Read tenant-desk/.env (real environment variables win)."""
    load_env(PROJECT_DIR / ".env")
    return Settings(
        whatsapp_token=require("WHATSAPP_TOKEN"),
        phone_number_id=require("WHATSAPP_PHONE_NUMBER_ID"),
        app_secret=require("WHATSAPP_APP_SECRET"),
        verify_token=require("WHATSAPP_VERIFY_TOKEN"),
        db_path=optional("DB_PATH", "data/tenant_desk.db"),
        media_dir=optional("MEDIA_DIR", "media"),
        transcriber=optional("TRANSCRIBER", "whisper"),
        port=int(optional("PORT", "8001")),
    )


def utc_now():
    return datetime.now(timezone.utc)


def build_deps(settings):
    """Create the real objects from settings. Relative paths are inside tenant-desk."""
    if settings.transcriber == "fake":
        transcriber = FakeTranscriber()
    else:
        transcriber = FasterWhisperTranscriber()
    return Deps(
        repo=SqliteRepository(PROJECT_DIR / settings.db_path),
        wa_client=WhatsAppClient(settings.whatsapp_token, settings.phone_number_id),
        transcriber=transcriber,
        media_dir=str(PROJECT_DIR / settings.media_dir),
        app_secret=settings.app_secret,
        verify_token=settings.verify_token,
        clock=utc_now,
    )


def create_app(deps=None):
    if deps is None:
        deps = build_deps(load_settings())
    app = FastAPI(title="Tenant Desk")

    @app.get("/webhook")
    def verify(request: Request):
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge", "")
        if mode == "subscribe" and token == deps.verify_token:
            return PlainTextResponse(challenge)
        return PlainTextResponse("forbidden", status_code=403)

    @app.post("/webhook")
    async def receive(request: Request):
        raw_body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256")
        if not verify_signature(raw_body, signature, deps.app_secret):
            log.warning("Rejected webhook with bad or missing signature")
            return PlainTextResponse("invalid signature", status_code=401)
        # The work below is blocking (database, HTTP, Whisper), so run it
        # on a worker thread instead of blocking the async event loop.
        await run_in_threadpool(process_body, raw_body, deps)
        return PlainTextResponse("ok")

    return app


def process_body(raw_body, deps):
    """Parse the payload and handle each message; log errors instead of failing."""
    try:
        payload = json.loads(raw_body)
    except ValueError:
        log.warning("Signed webhook body was not valid JSON")
        return
    for msg in parse_webhook(payload):
        try:
            result = handle_message(msg, deps.repo, deps.wa_client, deps.transcriber,
                                    deps.media_dir, deps.clock())
            log.info("message %s -> %s %s", msg.wa_message_id, result.status, result.ticket_id)
        except Exception:
            log.exception("Failed to handle message %s", msg.wa_message_id)


def main():
    import uvicorn
    settings = load_settings()
    uvicorn.run(create_app(build_deps(settings)), host="127.0.0.1", port=settings.port)


if __name__ == "__main__":
    main()
