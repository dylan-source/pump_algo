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
from backup_csv_utils import write_to_csv
#from listener_wss_utils import monitor_transactions
from listen_to_raydium_migration import listen_for_migrations
#from trade_utils import get_jupiter_quote, execute_swap, get_transaction_status, tokens_purchased, get_price
from solana.rpc.async_api import AsyncClient
# from balance_utils import lamports_converstion, get_transaction_details
# from jupiter_python_sdk.jupiter import Jupiter
from storage_utils import store_trade_data, fetch_trade_data
from rugcheck_utils import rugcheck_analysis # type: ignore

from z_backup_telegram_bot import BotManager

time_to_sleep = 5

# Instantiate the relevant objects
rpc_client = AsyncClient(RPC_URL)
httpx_client = httpx.AsyncClient()
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

        # Get the current timestamp
        current_time_utc = datetime.now(timezone.utc)
        timestamp_str = current_time_utc.strftime('%Y-%m-%d %H:%M:%S')

        # Rugcheck - Unpack metadata
        name = metadata.get("name", "")
        symbol = metadata.get("symbol", "")
        description = metadata.get("description", "")
        creator = metadata.get("creator", "")
        decimals = metadata.get("decimals", 0)
        ipfs_url = metadata.get("ipfs_url", "")
        ipfs_description = metadata.get("ipfs_description")
        twitter_url = metadata.get("twitter_url", "")
        website_url = metadata.get("website_url", "")
        telegram_url = metadata.get("telegram_url", "")
        image_url = metadata.get("image_url", "")

        # Rugcheck - unpack risks
        risk_list = risks.get("risks", [])
        risk_score = risks.get("score", 0)

        # Rugcheck - unpack holder metrics
        total_pct_top_5 = holder_metrics.get("total_pct_top_5", 0)
        total_pct_top_10 = holder_metrics.get("total_pct_top_10", 0)
        total_pct_top_20 = holder_metrics.get("total_pct_top_20", 0)
        total_pct_insiders = holder_metrics.get("total_pct_insiders", 0)
        
        logger.info(f"{symbol} - {name}")

        # Telegram bot analysis
        # tg_bot_raw_results, tg_bot_parsed_results = await tg_bot_manager.process_token(token_mint=token_address, website=website_url, twitter=twitter_url)

        # Append to results
        results = {
            "timestamp": timestamp_str,
            "token_address": token_address,
            "pair_address": pair_address, 
            "name": name,
            "symbol": symbol,
            "description": description,
            "ipfs_description": ipfs_description,
            "creator": creator,
            "decimals": decimals,
            "ipfs_url": ipfs_url,
            "twitter_url": twitter_url,
            "website_url": website_url,
            "telegram_url": telegram_url,
            "image_url": image_url,
            "risks": ", ".join(risk_list),
            "score": risk_score,
            "total_pct_top_5": total_pct_top_5,
            "total_pct_top_10": total_pct_top_10,
            "total_pct_top_20": total_pct_top_20,
            "total_pct_insiders": total_pct_insiders,
            # "twitter_parsed": tg_bot_parsed_results["twitter_parsed"],
            # "twitter_raw": tg_bot_parsed_results["twitter_raw"],
            # "website_parsed": tg_bot_parsed_results["website_parsed"],
            # "website_raw": tg_bot_parsed_results["website_raw"],
            # "dp_parsed": tg_bot_parsed_results["dp_parsed"],
            # "dp_raw": tg_bot_parsed_results["dp_raw"],
            # "bundle_parsed": tg_bot_parsed_results["bundle_parsed"],
            # "bundle_raw": tg_bot_parsed_results["bundle_raw"]
        }

        # Save results to a CSV for further analysis
        await write_to_csv(results)


async def main():
    
    # Create the queue to share between the producer (monitor_transactions) and consumer (consume_queue)
    queue = asyncio.Queue()
    
    # Testing
    # token_address_1 = "65P5VMQi7jCgb8XQMRZHHtL9SigzqrKe5RXdJt8qpump"
    # token_address_2 = "EXNLESvoZRexHWu4XiyyG4gcRfBG1hdHFN4QrN2Lpump"
    # token_address_3 = "97SCktEcLytW3LpQSbcCzQtbdiSf9LZzwe2ZNWXpump"

    # await queue.put((token_address_3, token_address_1))
    # consumer_task = asyncio.create_task(consume_queue(queue))
    # await asyncio.gather(consumer_task)
    
    # Run both the monitoring and consuming tasks concurrently
    producer_task = asyncio.create_task(listen_for_migrations(redis_client=redis_client, queue=queue))
    consumer_task = asyncio.create_task(consume_queue(queue=queue, httpx_client=httpx_client))
    await asyncio.gather(producer_task, consumer_task)
    # await asyncio.gather(producer_task)


if __name__ == "__main__":
    asyncio.run(main())



