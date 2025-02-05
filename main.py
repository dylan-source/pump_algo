import asyncio
import httpx
import time
import json
import ssl
import websockets
from datetime import datetime, timezone
import redis.asyncio as redis

from config import MIGRATION_ADDRESS, migrations_logger, RPC_URL, SOL_MINT, TRADE_AMOUNT_SOL, SOL_DECIMALS, WALLET_ADDRESS, PRIVATE_KEY, HTTPX_TIMEOUT
from listen_to_raydium_migration import listen_for_migrations
#from trade_utils import get_jupiter_quote, execute_swap, get_transaction_status, tokens_purchased, get_price
from solana.rpc.async_api import AsyncClient
from storage_utils import parse_migrations_to_save, store_trade_data, fetch_trade_data
# from filter_utils import process_new_tokens

time_to_sleep = 5

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
        # filters_result, data_to_save = await process_new_tokens(httpx_client=httpx_client, token_address=token_address, pair_address=pair_address)
        
        # Save results to a CSV for further analysis
        # await parse_migrations_to_save(token_address, pair_address, data_to_save, filters_result)

async def main():
    
    # Create the queue to share between the producer (monitor_transactions) and consumer (consume_queue)
    queue = asyncio.Queue()
     
    # Run both the monitoring and consuming tasks concurrently
    producer_task = asyncio.create_task(listen_for_migrations(redis_client_tokens=redis_client_tokens, queue=queue))
    consumer_task = asyncio.create_task(consume_queue(queue=queue, httpx_client=httpx_client))
    await asyncio.gather(producer_task, consumer_task)

    # Testing
    # token_address_1 = "G2ZebU6Qh222gFoq6fKuMiMPNTqXgZdScYX95yJVpump"
    # await queue.put((token_address_1, "213vwQsv1Lmnj8D4wLFvwsemucH243Ei7YEouhrBSB2o"))
    # consumer_task = asyncio.create_task(consume_queue(queue=queue, httpx_client=httpx_client))
    # await asyncio.gather(consumer_task)


if __name__ == "__main__":
    asyncio.run(main())
