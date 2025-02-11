import asyncio
import httpx
import time
import json
import ssl
import websockets
from datetime import datetime, timezone
import redis.asyncio as redis
from pprint import pprint

from config import MIGRATION_ADDRESS, migrations_logger, RPC_URL, SOL_MINT, SOL_AMOUNT_LAMPORTS, BUY_SLIPPAGE, SELL_SLIPPAGE, TRADE_AMOUNT_SOL, SOL_DECIMALS, WALLET_ADDRESS, PRIVATE_KEY, HTTPX_TIMEOUT
from listen_to_raydium_migration import listen_for_migrations
from trade_utils import trade_wrapper, startup_sell
from solana.rpc.async_api import AsyncClient
from storage_utils import parse_migrations_to_save, store_trade_data, fetch_trade_data
from filter_utils import process_new_tokens

# Instantiate the relevant objects
rpc_client = AsyncClient(RPC_URL)
httpx_client = httpx.AsyncClient(timeout=HTTPX_TIMEOUT)
redis_client_tokens = redis.Redis(host='localhost', port=6379, db=0)
redis_client_trades = redis.Redis(host='localhost', port=6379, db=1)

# Create a consumer queue to take new tokens and execute trade logic
async def consume_queue(queue, httpx_client):
    
    while True:
        
        # Get new token address from the queue. Break if no signal
        token_address, pair_address = await queue.get()
        if token_address is None: 
            migrations_logger.info(f"Consumer triggered with no token")

        # Run the various filters and save the info for future analysis
        filters_result, data_to_save = await process_new_tokens(httpx_client=httpx_client, token_address=token_address, pair_address=pair_address)

        # Save results to a CSV for further analysis
        await parse_migrations_to_save(token_address=token_address, pair_address=pair_address, data_to_save=data_to_save, filters_result=filters_result)

        # Force trade for testing
        # filters_result = True

        if filters_result:
            asyncio.create_task(
                trade_wrapper(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=token_address, 
                    sol_address=SOL_MINT, trade_amount=SOL_AMOUNT_LAMPORTS, buy_slippage=BUY_SLIPPAGE, sell_slippage=SELL_SLIPPAGE)
                    )


async def main():
    
    # Check to see if any start up tokens that need to be sold
    await startup_sell(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, sell_slippage=SELL_SLIPPAGE)

    # Create the queue to share between the producer (monitor_transactions) and consumer (consume_queue) tasks
    queue = asyncio.Queue()
     
    # Run both the monitoring and consuming tasks concurrently
    producer_task = asyncio.create_task(listen_for_migrations(redis_client_tokens=redis_client_tokens, queue=queue))
    consumer_task = asyncio.create_task(consume_queue(queue=queue, httpx_client=httpx_client))
    await asyncio.gather(producer_task, consumer_task)


if __name__ == "__main__":
    asyncio.run(main())
