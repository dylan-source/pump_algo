import asyncio
import websockets
import json
import aiohttp
from datetime import datetime

# Set your migration address, WebSocket endpoint, and HTTP RPC endpoint.
MIGRATION_ADDRESS = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"
WS_URL = ""        # e.g., QuickNode or GenesysGo WebSocket endpoint
HTTP_URL = ""    # corresponding HTTP endpoint

from solders.signature import Signature # type: ignore
from solana.rpc.commitment import Processed, Confirmed, Finalized
from solana.rpc.async_api import AsyncClient
rpc_client = AsyncClient(HTTP_URL)

def current_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

async def fetch_transaction_details(signature):
    """Fetch full transaction details using getParsedTransaction."""
    
    # payload = {
    #     "jsonrpc": "2.0",
    #     "id": 1,
    #     "method": "getTransaction",
    #     "params": [signature, "json"]# , {"encodmaxSupportedTransactionVersioning": 0, "commitment": "confirmed"}]
    # }
    # headers={"Content-Type":"application/json"}
    # async with aiohttp.ClientSession() as session:
    #     async with session.post(HTTP_URL, json=payload, headers=headers) as resp:
    #         result = await resp.json()
    #         return result
        
    sig = Signature.from_string(signature)
    details = await rpc_client.get_transaction(sig, 'json', commitment=Confirmed, max_supported_transaction_version=0)
    details_json = details.to_json()
    data = json.loads(details_json)
    # relevant_data = data["result"]["meta"]["postTokenBalances"][0]
    # print(relevant_data["mint"])
    
    # owner = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"
    # mint = [address for address in relevant_data if owner==owner]
    # print(json.dumps(mint, indent=2))
    
    # print(json.dumps(relevant_data, indent=2))
    try:
        relevant_data = data["result"]["meta"]["postTokenBalances"][0]
        print(f'{current_timestamp()} {relevant_data["mint"]}')
    except:
        print(f'{current_timestamp()} Not a relevant transaction')
    return details.value

async def listen_logs():
    async with websockets.connect(WS_URL) as ws:
        # Subscribe to logs that mention the migration address.
        subscription_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [MIGRATION_ADDRESS]},
                {"commitment": "confirmed"}
            ]
        }
        await ws.send(json.dumps(subscription_request))
        print(f"[{current_timestamp()}] Subscribed to logs for migration address: {MIGRATION_ADDRESS}")

        while True:
            message = await ws.recv()
            data = json.loads(message)
            print(data)
            # print(f"[{current_timestamp()}] Received log event: {json.dumps(data, indent=2)}")
            
            try:
                # Extract the transaction signature from the log notification.
                signature = data["params"]["result"]["value"]["signature"]
                print(f"[{current_timestamp()}] Detected transaction signature: {signature}")

                # Fetch full transaction details.
                # details = await fetch_transaction_details(signature)
                # print(f"[{current_timestamp()}] Transaction details: {json.dumps(details, indent=2)}")

                # # At this point, inspect 'details' to locate the token address.
                # instructions = details.get("result", {}).get("transaction", {}).get("message", {}).get("instructions", [])
                # for ix in instructions:
                #     # Example: look for an instruction that might contain a 'token' field.
                #     if isinstance(ix, dict) and "parsed" in ix:
                #         parsed = ix["parsed"]
                #         if isinstance(parsed, dict):
                #             token_address = parsed.get("info", {}).get("mint")
                #             if token_address:
                #                 print(f"[{current_timestamp()}] Found token address: {token_address}")
            except Exception as e:
                print(f"[{current_timestamp()}] Error processing transaction details: {e}")

async def main():
    try:
        await listen_logs()
    except Exception as e:
        print(f"[{current_timestamp()}] Listener encountered an error: {e}")

if __name__ == "__main__":
    # signature = "5W6fnjgQhtBLuMrpCckx5P3dYNxsxrKzv1vAuwHucTQPnNxawz8urVcNJMbDZTbxt3Xeg5nT6dRK91ejvUVEmzop"
    # res = asyncio.run(fetch_transaction_details(signature))
    
    asyncio.run(main())
