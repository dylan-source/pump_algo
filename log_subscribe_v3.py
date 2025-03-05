import asyncio
import websockets
import json
import httpx
import re
import aiohttp
from datetime import datetime
from config import MIGRATION_ADDRESS, WS_URL, RPC_URL, RELAY_DELAY, migrations_logger, HTTPX_TIMEOUT
from pprint import pprint

from solders.signature import Signature  # type: ignore
from solana.rpc.commitment import Processed, Confirmed, Finalized
from solana.rpc.async_api import AsyncClient

from filter_utils import process_new_tokens, trade_filters
from storage_utils import parse_migrations_to_save

# Initialize the rpc_client globally.
rpc_client = AsyncClient(RPC_URL)
httpx_client = httpx.AsyncClient(timeout=HTTPX_TIMEOUT)

async def fetch_transaction_details(signature, withdraw_tokens, is_withdraw=True):
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

        post_token_balances = result.get("meta", {}).get("postTokenBalances", [])
        token_mint = next(
            (tb.get("mint") for tb in post_token_balances if tb.get("owner") == MIGRATION_ADDRESS),
            None
        )

        if is_withdraw:
            
            if token_mint and token_mint not in withdraw_tokens:
                migrations_logger.info(f"Withdraw detected | token mint: {token_mint}")
                withdraw_tokens.add(token_mint)
                
                # Run the token filters and save the data to the spreadsheet
                filters_result, data_to_save = await process_new_tokens(httpx_client, token_mint)
                if filters_result is not None:
                    await parse_migrations_to_save(token_address=token_mint, data_to_save=data_to_save, filters_result=filters_result)
                
                return token_mint
            else:
                migrations_logger.warning("Withdraw detected | no token mint found in getTransaction call")
                return None
        
        else:
            # Fetch the liquidity pool (pair) address from accountKeys in the transaction message.
            account_keys = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
            if len(account_keys) > 2:
                liquidity_pool_address = account_keys[2]
                
                if token_mint in withdraw_tokens:
                    migrations_logger.info(f"Token mint: {token_mint} | LP address: {liquidity_pool_address}")
                    withdraw_tokens.remove(token_mint)
                    return (token_mint, liquidity_pool_address)
                else:
                    migrations_logger.info(f'Initialize2 event for token {token_mint} but no prior withdraw event found.')
                    
            else:
                migrations_logger.warning("Token mint or LP address not found in the account keys.")
                return None

    except Exception as e:
        migrations_logger.error(f"fetch_transaction_details function error: {e}")
        return None

def contains_initialize2_log(logs):
    pattern = re.compile(r"Program log: initialize2:\s*InitializeInstruction2")
    return any(pattern.search(log) for log in logs)

async def listen_logs():
    # Declare as global since we may reinitialize it.
    global rpc_client  
    global httpx_client
    
    withdraw_tokens = set()
    while True:
        try:
            # Pass ping_interval and ping_timeout to maintain a heartbeat.
            async with websockets.connect(WS_URL, ping_interval=60, ping_timeout=20) as websocket:
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
                    # Wait for a new message; if nothing is received within 30 seconds, a TimeoutError is raised.
                    message = await asyncio.wait_for(websocket.recv(), timeout=300)
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
                                # Launch as a separate task to avoid blocking.
                                asyncio.create_task(fetch_transaction_details(sig, withdraw_tokens, True))
                            
                            elif contains_initialize2_log(logs):
                                migrations_logger.info(f"Initialize2 signature: {sig}")
                                asyncio.create_task(fetch_transaction_details(sig, withdraw_tokens, False))
                                
        except Exception as e:
            migrations_logger.error(f"Exception in listen_logs: {e}")
            migrations_logger.info(f"Reconnecting in {RELAY_DELAY} seconds...")
            
            # Close the current async clients and reinitialize.
            try:
                await rpc_client.close()
                await httpx_client.aclose()
            except Exception as close_e:
                migrations_logger.error(f"Error closing async clients: {close_e}")
            
            rpc_client = AsyncClient(RPC_URL)
            httpx_client = httpx.AsyncClient(timeout=HTTPX_TIMEOUT)
            await asyncio.sleep(RELAY_DELAY)

async def main():
    try:
        await listen_logs()
    except Exception as e:
        migrations_logger.error(f"Listener exception in main: {e}")
        migrations_logger.info(f"Sleeping for {RELAY_DELAY} seconds before retrying...")
        await asyncio.sleep(RELAY_DELAY)

if __name__ == "__main__":
    # sig = "4Qfkfhag5ehzp3xef8MMveNjzheUkoptJKxCiSi4enyg1LutCcpcJC46i9wWwLAKV14qrXS62FfGhx9i45nQ5YzG"
    # asyncio.run(fetch_transaction_details(sig, is_withdraw=False))
    
    asyncio.run(main())