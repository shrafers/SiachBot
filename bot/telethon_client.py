"""Telethon MTProto client for large file downloads (no 20MB limit)."""

import os
from telethon import TelegramClient
from telethon.sessions import StringSession

_client: TelegramClient | None = None


async def _get_client() -> TelegramClient:
    global _client
    if _client is not None and _client.is_connected():
        return _client
    _client = TelegramClient(
        StringSession(),
        int(os.environ["TELEGRAM_API_ID"]),
        os.environ["TELEGRAM_API_HASH"],
    )
    await _client.start(bot_token=os.environ["TELEGRAM_BOT_TOKEN"])
    return _client


async def download_file(chat_id: int, message_id: int) -> bytes:
    """Download any file from Telegram via MTProto — no size limit."""
    client = await _get_client()
    message = await client.get_messages(chat_id, ids=message_id)
    data = await client.download_media(message, file=bytes)
    return bytes(data)
