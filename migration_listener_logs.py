import aiohttp
import asyncio
import websockets
import json
from solders.pubkey import Pubkey   # type: ignore
from config import MIGRATION_ADDRESS, WS_URL, RPC_URL, RELAY_DELAY, migrations_logger
from datetime import datetime, timezone

# Set your migration address, WebSocket endpoint, and HTTP RPC endpoint.
MIGRATION_ADDRESS = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"
HTTP_URL = RPC_URL

async def fetch_transaction_details(signature):
    """Fetch full transaction details using getParsedTransaction."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getParsedTransaction",
        "params": [signature, {"encoding": "jsonParsed", "commitment": "confirmed"}]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(HTTP_URL, json=payload) as resp:
            result = await resp.json()
            return result

async def listen_logs():
    async with websockets.connect(WS_URL) as ws:
        # Subscribe to logs that mention the migration address.
        subscription_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [MIGRATION_ADDRESS]},
                {"commitment": "processed"}
            ]
        }
        await ws.send(json.dumps(subscription_request))
        print("Subscribed to logs for migration address:", MIGRATION_ADDRESS)

        while True:
            message = await ws.recv()
            data = json.loads(message)
            print("Received log event:", json.dumps(data, indent=2))

            try:
                # Extract the transaction signature from the log notification.
                current_time_utc = datetime.now(timezone.utc)
                timestamp_str = current_time_utc.strftime('%Y-%m-%d %H:%M:%S')
                print(f"\n\nDATA - {timestamp_str}")
                print(json.dumps(data, indent=2))
                signature = data["params"]["result"]["signature"]
                print("Detected transaction signature:", signature)

                # Fetch full transaction details.
                details = await fetch_transaction_details(signature)
                print("Transaction details:", json.dumps(details, indent=2))

                # At this point, inspect 'details' to locate the token address.
                # For example, if the token address is within an instruction:
                instructions = details.get("result", {}).get("transaction", {}).get("message", {}).get("instructions", [])
                for ix in instructions:
                    # Example: look for an instruction that might contain a 'token' field.
                    if isinstance(ix, dict) and "parsed" in ix:
                        parsed = ix["parsed"]
                        if isinstance(parsed, dict):
                            token_address = parsed.get("info", {}).get("mint")
                            if token_address:
                                print("Found token address:", token_address)
            except Exception as e:
                print("Error processing transaction details:", e)
                continue

async def main():
    try:
        await listen_logs()
    except Exception as e:
        print("Listener encountered an error:", e)


if __name__ == "__main__":
    asyncio.run(main())
    