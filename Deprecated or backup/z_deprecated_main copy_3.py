# Raydium initialize2 discriminator [9, 203, 254, 64, 89, 32, 179, 159]
# In the initialize2 account - "pcMint" refers to the pump.fun token and "amm" refers to the LP address

import asyncio
import httpx
import time
import json
import ssl
import websockets
from datetime import datetime, timezone
import redis.asyncio as redis

from config import MIGRATION_ADDRESS, logger, RPC_URL, SOL_MINT, TRADE_AMOUNT_SOL, SOL_DECIMALS, WALLET_ADDRESS, PRIVATE_KEY, BUY_SLIPPAGE_BPS, SOL_AMOUNT, USDC_MINT
from z_deprecated_rpc_utils import fetch_transaction_details_rpc
# from listener_transaction_utils import extract_token_and_pair_from_response
# from metadata_utils import fetch_token_metadata
from backup_csv_utils import write_to_csv, parse_data_to_save
#from listener_wss_utils import monitor_transactions
from listen_to_raydium_migration import listen_for_migrations
#from trade_utils import get_jupiter_quote, execute_swap, get_transaction_status, tokens_purchased, get_price
from solana.rpc.async_api import AsyncClient
# from balance_utils import lamports_converstion, get_transaction_details
# from jupiter_python_sdk.jupiter import Jupiter
from storage_utils import store_trade_data, fetch_trade_data
from rugcheck_utils import rugcheck_analysis    # type: ignore
from z_backup_filter_utils_1 import get_dex_paid, tweet_scout_get_followers, tweet_scout_get_score, tweet_scout_get_user_info, gatekept_data, sync_gatekept_data

from z_backup_telegram_bot import BotManager

time_to_sleep = 5

# Instantiate the relevant objects
rpc_client = AsyncClient(RPC_URL)
httpx_client = httpx.AsyncClient(timeout=10)
tg_bot_manager = BotManager()
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Create a consumer queue to take new tokens and execute trade logic
async def consume_queue(queue, httpx_client):

    while True:
        
        # Get new token address from the queue. Break if no signal
        token_address, pair_address = await queue.get()
        if token_address is None: 
            logger.info(f"Consumer triggered with no token")
        
        # Perform the Rugcheck analysis
        metadata, risks, holder_metrics = await rugcheck_analysis(httpx_client=httpx_client, token_mint_address=token_address)

        if metadata is None:
            logger.error(f"Rugcheck error for: {token_address}")
            break

        else:
            twitter_handle = metadata.get("twitter_handle", "")
            symbol = metadata.get("symbol", "")
            name = metadata.get("name", "")
            logger.info(f"{symbol} - {name}")

        print("Rugcheck done")
    
        # Is DexScreener paid
        is_dex_paid_parsed, is_dex_paid_raw = await get_dex_paid(httpx_client=httpx_client, token_mint_address=token_address)
        print("DexScreener done")
        print(twitter_handle)

        cabal_chance, fake_volume = await gatekept_data(token_address)
        print("Chance of Cabal: ", cabal_chance)
        print("Fake volume: ", fake_volume)

        # Extract the number of previous projects
        # if twitter_handle:
        #     followers = tweet_scout_get_followers(twitter_handle=twitter_handle)
        #     twitter_score = tweet_scout_get_score(twitter_handle=twitter_handle)
        #     user_info = tweet_scout_get_user_info(twitter_handle=twitter_handle)
        #     print("TweetScout done")
        # else:
        #     followers = {}
        #     twitter_score = {}
        #     user_info = {}

        ## Save results to a CSV for further analysis
        # await parse_data_to_save(token_address, pair_address, metadata, risks, holder_metrics, is_dex_paid_parsed, is_dex_paid_raw, followers, twitter_score, user_info)


async def main():
    
    # Create the queue to share between the producer (monitor_transactions) and consumer (consume_queue)
    queue = asyncio.Queue()
    
    # Testing
    # token_address_1 = "92khhnH81NtWwMX4nQybHEZpznKh6SSCH9aNXuSPpump"
    # token_address_2 = "EXNLESvoZRexHWu4XiyyG4gcRfBG1hdHFN4QrN2Lpump"
    # token_address_3 = "97SCktEcLytW3LpQSbcCzQtbdiSf9LZzwe2ZNWXpump"

    # await queue.put((token_address_1, "3ntvj3uiKBg93PKgPn37Wbs9d7YFdJ4KKHTxqPidtrC9"))
    # consumer_task = asyncio.create_task(consume_queue(queue))
    # consumer_task = asyncio.create_task(consume_queue(queue=queue, httpx_client=httpx_client))
    # await asyncio.gather(consumer_task)
    
    # Run both the monitoring and consuming tasks concurrently
    producer_task = asyncio.create_task(listen_for_migrations(redis_client=redis_client, queue=queue))
    consumer_task = asyncio.create_task(consume_queue(queue=queue, httpx_client=httpx_client))
    await asyncio.gather(producer_task, consumer_task)


if __name__ == "__main__":
    asyncio.run(main())



