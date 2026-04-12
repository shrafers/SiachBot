"""
Helper script: List all Telegram groups/channels you're a member of.
Run this once to find the numeric ID of your target group, then set TG_GROUP_ID in .env
"""

import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

load_dotenv()

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
PHONE = os.environ["TG_PHONE"]


async def main():
    async with TelegramClient("siachbot", API_ID, API_HASH) as client:
        await client.start(phone=PHONE)

        print(f"\n{'TYPE':<12} {'ID':<15} NAME")
        print("-" * 60)

        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if isinstance(entity, Channel):
                kind = "channel" if entity.broadcast else "group/super"
                print(f"{kind:<12} {entity.id:<15} {dialog.name}")
            elif isinstance(entity, Chat):
                print(f"{'group':<12} {entity.id:<15} {dialog.name}")

        print("\nTo use a group, set TG_GROUP_ID in .env to its numeric ID.")
        print("Note: Telethon uses positive IDs internally; the full ID is shown above.")


asyncio.run(main())
