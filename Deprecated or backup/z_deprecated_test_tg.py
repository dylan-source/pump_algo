from telethon import TelegramClient
import os

api_id = "26638223"
api_hash = "e837a9cec5a25ba9bbb712de90bed659"

client = TelegramClient("anon", api_id=api_id, api_hash=api_hash)

async def main():
    await client.send_message("me", "Hello from python")

with client:
    client.loop.run_until_complete(main())