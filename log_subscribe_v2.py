### Includes new tasks
'''
CONCERNS TO ADDRESS:

1. Reconnection & Timeout Handling
Timeouts:
You already use asyncio.wait_for with a 30-second timeout. If the websocket stalls, this will raise an exception, which you catch. Consider whether 30 seconds is appropriate for your use case.
Reconnect Strategy:
If the websocket disconnects or repeatedly times out, consider adding a reconnection strategy. For example, wrap the while True loop (or the entire listen_logs function) in a try/except block that, upon an exception, waits a bit and then reconnects.

2. Trade Logic in a Separate Task:
You mentioned that the trade logic is already housed in its own task using asyncio.create_task(). That’s a good approach. Just ensure that your tasks are properly managed (e.g. cancellations on shutdown) and that shared state (if any) is protected.
Minimal Blocking in the Listener:
Ensure that any heavy processing (risk checks, API calls) inside tasks is also done asynchronously. Use asynchronous HTTP libraries (like aiohttp) for any API calls.
'''


import asyncio
import websockets
import json
import re
import aiohttp
from datetime import datetime
from config import MIGRATION_ADDRESS, WS_URL, RPC_URL, RELAY_DELAY, migrations_logger
from pprint import pprint

from solders.signature import Signature  # type: ignore
from solana.rpc.commitment import Processed, Confirmed, Finalized
from solana.rpc.async_api import AsyncClient

rpc_client = AsyncClient(RPC_URL)

async def fetch_transaction_details(signature, is_withdraw=True):
    """Fetch full transaction details using getParsedTransaction."""
    try:
        # Convert the signature string to the appropriate Signature type.
        sig = Signature.from_string(signature)
        
        # Fetch the transaction details.
        details = await rpc_client.get_transaction(
            sig,
            'json',
            commitment=Confirmed,
            max_supported_transaction_version=0
        )
        
        # Convert details to dict if necessary.
        if isinstance(details, dict):
            data = details
        else:
            data = json.loads(details.to_json())
        
        result = data.get("result")
        if not result:
            migrations_logger.warning("No result in transaction details.")
            return None

        if is_withdraw:
            # Fetch token mint from the withdraw logs (postTokenBalances)
            post_token_balances = result.get("meta", {}).get("postTokenBalances", [])
            token_mint = next(
                (tb.get("mint") for tb in post_token_balances if tb.get("owner") == MIGRATION_ADDRESS),
                None
            )
            if token_mint:
                migrations_logger.info(f"Withdraw detected | token mint: {token_mint}")
                return token_mint
            else:
                migrations_logger.warning("Withdraw detected | no token mint found in getTransaction call")
                return None
        
        else:
            # Fetch the liquidity pool (pair) address from accountKeys in the transaction message.
            account_keys = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
            if len(account_keys) > 2:
                liquidity_pool_address = account_keys[2]
                migrations_logger.info(f"Liquidity pool address is: {liquidity_pool_address}")
                return liquidity_pool_address
            else:
                migrations_logger.warning("Liquidity pool address not found in the account keys.")
                return None

    except Exception as e:
        migrations_logger.error(f"fetch_transaction_details function error: {e}")
        return None

def contains_initialize2_log(logs):
    pattern = re.compile(r"Program log: initialize2:\s*InitializeInstruction2")
    return any(pattern.search(log) for log in logs)

async def listen_logs():
    while True:
        try:
            async with websockets.connect(WS_URL) as websocket:
                # Subscribe to logs that mention the migration address.
                subscription_request = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": [
                        {"mentions": [MIGRATION_ADDRESS]},
                        {"commitment": "confirmed"}
                    ]
                })
                await websocket.send(subscription_request)
                response = await websocket.recv()
                migrations_logger.info(f'Subscription response: {response}')
                migrations_logger.info('Listening for Pump.fun migrations - withdraw and initialize2 instructions...')

                while True:
                    message = await asyncio.wait_for(websocket.recv(), timeout=30)
                    data = json.loads(message)
                    
                    if (
                        'method' in data and data['method'] == 'logsNotification' and
                        'params' in data and 'result' in data['params']
                    ):
                        block_data = data['params']['result']
                        if 'value' in block_data and 'logs' in block_data['value']:
                            logs = block_data['value']['logs']
                            sig = block_data['value'].get("signature")
                            if not sig:
                                continue
                            
                            if 'Program log: Instruction: Withdraw' in logs:
                                migrations_logger.info(f"Withdraw signature: {sig}")
                                # Launch as a separate task
                                asyncio.create_task(fetch_transaction_details(sig, True))
                            
                            elif contains_initialize2_log(logs):
                                migrations_logger.info(f"Initialize2 signature: {sig}")
                                asyncio.create_task(fetch_transaction_details(sig, False))
        except Exception as e:
            migrations_logger.error(f"Exception in listen_logs: {e}")
            migrations_logger.info(f"Reconnecting in {RELAY_DELAY} seconds...")
            await asyncio.sleep(RELAY_DELAY)

async def main():
    try:
        await listen_logs()
    except Exception as e:
        migrations_logger.error(f"Listener exception in main: {e}")
        migrations_logger.info(f"Sleeping for {RELAY_DELAY} seconds before retrying...")
        await asyncio.sleep(RELAY_DELAY)

if __name__ == "__main__":
    asyncio.run(main())
