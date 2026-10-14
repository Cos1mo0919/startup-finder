"""Optional Telethon source adapter; all posts use the ordinary raw queue."""

from __future__ import annotations

from .writer import serialized_worker

import json
import re
from .db import SchedulerCheckpoint, now_utc
from .raw_discovery import ingest_raw


def configured_channels(path):
    data = json.loads(path.read_text())
    channels = data.get("channels", [])
    if not isinstance(channels, list):
        raise ValueError("invalid_telegram_channels")
    return [row["username"].removeprefix("@") for row in channels
            if isinstance(row, dict) and row.get("enabled") is True
            and re.fullmatch(r"[A-Za-z0-9_]{5,32}", row.get("username", "").removeprefix("@"))]


def ingest_post(factory, channel: str, message) -> bool:
    """Persist before processing; the Telegram message ID is the idempotency key."""
    message_id = int(message.id)
    url = f"https://t.me/{channel}/{message_id}"
    body = (getattr(message, "raw_text", None) or "").strip()
    links = re.findall(r"https?://[^\s<>]+", body)
    date = getattr(message, "date", None)
    with factory.begin() as session:
        _, created = ingest_raw(
            session, source_adapter=f"telegram:{channel}", source_url=url,
            source_name=f"Telegram · @{channel}", source_type="telegram",
            page_type="channel_post", external_id=str(message_id),
            title=body.splitlines()[0][:300] if body else f"Telegram post {message_id}",
            description=body[:500], raw_text=body,
            raw_payload={"channel": channel, "message_id": message_id, "message_url": url,
                         "linked_urls": links, "has_media": bool(getattr(message, "media", None))},
            publication_date=date,
        )
    return created


async def poll_channels(settings, factory, client=None):
    channels = configured_channels(settings.telegram_channels_file)
    if not channels:
        return {"status": "not_configured", "new": 0, "errors": []}
    if not settings.telegram_api_id or not settings.telegram_api_hash.get_secret_value() or not settings.telegram_session.get_secret_value():
        return {"status": "credentials_missing", "new": 0, "errors": []}
    own_client = client is None
    if own_client:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        client = TelegramClient(StringSession(settings.telegram_session.get_secret_value()),
                                settings.telegram_api_id, settings.telegram_api_hash.get_secret_value())
        await client.connect()
    total, errors = 0, []
    try:
        if not await client.is_user_authorized():
            return {"status": "session_unauthorized", "new": 0, "errors": []}
        for channel in channels:
            checkpoint_name = f"telegram:{channel}"
            with factory() as session:
                checkpoint = session.get(SchedulerCheckpoint, checkpoint_name)
                last_id = int((checkpoint.cursor or {}).get("last_id", 0)) if checkpoint else 0
            highest = last_id
            try:
                async for message in client.iter_messages(channel, min_id=last_id, reverse=True, limit=100):
                    highest = max(highest, int(message.id))
                    total += int(ingest_post(factory, channel, message))
                with factory.begin() as session:
                    checkpoint = session.get(SchedulerCheckpoint, checkpoint_name)
                    if checkpoint is None:
                        checkpoint = SchedulerCheckpoint(name=checkpoint_name, cursor={})
                        session.add(checkpoint)
                    checkpoint.cursor = {"last_id": highest}
                    checkpoint.last_success_at = now_utc()
            except Exception as exc:
                # Channel failures are isolated. Error type is diagnostic; session secrets stay private.
                errors.append({"channel": channel, "code": type(exc).__name__})
        return {"status": "partial" if errors else "completed", "new": total, "errors": errors}
    finally:
        if own_client:
            await client.disconnect()




@serialized_worker
def poll_once(settings, factory):
    import asyncio
    return asyncio.run(poll_channels(settings, factory))
