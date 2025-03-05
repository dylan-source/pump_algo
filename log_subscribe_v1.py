import asyncio
import websockets
import json
import re
import aiohttp
from datetime import datetime
from config import MIGRATION_ADDRESS, WS_URL, RPC_URL, RELAY_DELAY, migrations_logger
from pprint import pprint

from solders.signature import Signature # type: ignore
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
        
        # If details is not already a dict, convert it.
        if isinstance(details, dict):
            data = details
        else:
            details_json = details.to_json()
            data = json.loads(details_json)
        
        result = data.get("result")
        if not result:
            migrations_logger.warning("No result in transaction details.")
            return None

        if is_withdraw:
            # Fetch token mint from the withdraw logs (postTokenBalances)
            post_token_balances = result.get("meta", {}).get("postTokenBalances", [])
            
            # Use a generator expression to find the token mint where the owner matches MIGRATION_ADDRESS.
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
                return liquidity_pool_address  # Return the extracted address
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
            try:
                #  message = await websocket.recv()        # response = await asyncio.wait_for(websocket.recv(), timeout=30)
                message = await asyncio.wait_for(websocket.recv(), timeout=30)
                data = json.loads(message)
                
                if (
                        'method' in data and data['method'] == 'logsNotification' and
                        'params' in data and 'result' in data['params']
                    ):
                        # pprint(data)
                        block_data = data['params']['result']
                        if 'value' in block_data and 'logs' in block_data['value']:
                            logs = block_data['value']['logs']
                            if 'Program log: Instruction: Withdraw' in logs:
                                sig = data['params']['result']["value"]["signature"]
                                migrations_logger.info(f"Withdraw signature: {sig}")
                                await fetch_transaction_details(sig, True)
                                
                            elif contains_initialize2_log(logs):
                                sig = data['params']['result']["value"]["signature"]
                                migrations_logger.info(f"Initialize2 signature: {sig}")
                                await fetch_transaction_details(sig, False)
                
            
            except Exception as e:
                migrations_logger.error(f"Exception: {e}")

async def main():
    try:
        await listen_logs()
    except Exception as e:
        migrations_logger.error(f"Listener exception: {e}")
        migrations_logger.error(f"Sleeping for {RELAY_DELAY} seconds")
        await asyncio.sleep(RELAY_DELAY)

if __name__ == "__main__":
    # signature = "6xrH8US6hJFpsmZnSWNvZfMhqYgyovcG9LqRohQQE8wMhdJmF4C3Podw6m7heED1gUVWAwFgcj6WLM4sWe84kD2"
    # res = asyncio.run(fetch_transaction_details(signature, False))
    asyncio.run(main())
