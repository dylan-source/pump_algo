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
from trade_utils_raydium import raydium_trade_wrapper# , startup_sell

# Initialize the rpc_client and httpx_client globally.
rpc_client = AsyncClient(RPC_URL)
httpx_client = httpx.AsyncClient(timeout=HTTPX_TIMEOUT)

async def fetch_transaction_details(signature, pending_trades, is_withdraw=True):
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

        # Fetch token mint from postTokenBalances using the same logic for both cases.
        post_token_balances = result.get("meta", {}).get("postTokenBalances", [])
        token_mint = next(
            (tb.get("mint") for tb in post_token_balances if tb.get("owner") == MIGRATION_ADDRESS),
            None
        )
        
        if is_withdraw:
            if token_mint and token_mint not in pending_trades:
                migrations_logger.info(f"Withdraw detected | token mint: {token_mint}")
                # Run the risk filters.
                filters_result, data_to_save = await process_new_tokens(httpx_client, token_mint)
                
                # Save data regardless, but mark whether the token passed.
                if filters_result is True:
                    pending_trades[token_mint] = {"data": data_to_save, "passed": True}
                    await parse_migrations_to_save(token_address=token_mint, data_to_save=data_to_save, filters_result=filters_result)
                else:
                    pending_trades[token_mint] = {"data": data_to_save, "passed": False}
                
                return token_mint
            else:
                migrations_logger.warning("Withdraw detected | no token mint found or token already processed.")
                return None
        
        else:
            # For initialize2 events, also fetch the liquidity pool (pair) address.
            account_keys = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
            if len(account_keys) > 2:
                liquidity_pool_address = account_keys[2]
                # Check if we have recorded this token from a previous withdraw event.
                if token_mint in pending_trades:
                    trade_info = pending_trades[token_mint]
                    if trade_info["passed"]:
                        migrations_logger.info(f"Token mint: {token_mint} | LP address: {liquidity_pool_address} - executing trade")
                        
                        print(f"EXECUTE TRADE FOR {token_mint}")
                        # Execute trade logic here (e.g., call an async function to perform the trade)
                        # asyncio.create_task(execute_trade(token_mint, liquidity_pool_address, trade_info["data"]))
                    else:
                        migrations_logger.info(f"Token mint: {token_mint} | LP address: {liquidity_pool_address} - risk filters did not pass.")
                    # Remove the token from pending trades after processing.
                    pending_trades.pop(token_mint)
                    return (token_mint, liquidity_pool_address)
                else:
                    migrations_logger.info(f"Initialize2 event for token {token_mint} but no prior withdraw event found.")
                    return None
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
    global rpc_client
    global httpx_client
    # Use a dictionary to track tokens from withdraw events and their filter outcomes.
    pending_trades = {}
    
    while True:
        try:
            # Pass ping_interval and ping_timeout to maintain a heartbeat.
            async with websockets.connect(WS_URL, ping_interval=60, ping_timeout=20) as websocket:
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
                migrations_logger.info(f"Subscription response: {response}")
                migrations_logger.info("Listening for Pump.fun migrations - withdraw and initialize2 instructions...")

                while True:
                    message = await asyncio.wait_for(websocket.recv(), timeout=300)
                    data = json.loads(message)
                    
                    if (
                        "method" in data and data["method"] == "logsNotification" and
                        "params" in data and "result" in data["params"]
                    ):
                        block_data = data["params"]["result"]
                        if "value" in block_data and "logs" in block_data["value"]:
                            logs = block_data["value"]["logs"]
                            sig = block_data["value"].get("signature")
                            if not sig:
                                continue
                            
                            if "Program log: Instruction: Withdraw" in logs:
                                migrations_logger.info(f"Withdraw signature: {sig}")
                                asyncio.create_task(fetch_transaction_details(sig, pending_trades, True))
                            
                            elif contains_initialize2_log(logs):
                                migrations_logger.info(f"Initialize2 signature: {sig}")
                                asyncio.create_task(fetch_transaction_details(sig, pending_trades, False))
        except Exception as e:
            migrations_logger.error(f"Exception in listen_logs: {e}")
            migrations_logger.info(f"Reconnecting in {RELAY_DELAY} seconds...")
            try:
                await rpc_client.close()
                await httpx_client.aclose()
            except Exception as close_e:
                migrations_logger.error(f"Error closing async clients: {close_e}")
            rpc_client = AsyncClient(RPC_URL)
            httpx_client = httpx.AsyncClient(timeout=HTTPX_TIMEOUT)
            await asyncio.sleep(RELAY_DELAY)

async def execute_trade(token_mint, liquidity_pool_address, extra_data):
    """
    Placeholder for your trade logic. This function should contain the code to execute a trade
    using the token mint, LP address, and any additional data from the filters.
    """
    migrations_logger.info(f"Executing trade for token {token_mint} with LP {liquidity_pool_address}")
    # Insert your trade execution code here.
    await asyncio.sleep(0)  # For example purposes.

async def main():
    try:
        await listen_logs()
    except Exception as e:
        migrations_logger.error(f"Listener exception in main: {e}")
        migrations_logger.info(f"Sleeping for {RELAY_DELAY} seconds before retrying...")
        await asyncio.sleep(RELAY_DELAY)

if __name__ == "__main__":
    asyncio.run(main())
