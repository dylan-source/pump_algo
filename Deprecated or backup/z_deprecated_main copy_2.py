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
from z_backup_filter_utils_1 import get_dex_paid, tweet_scout_get_followers, tweet_scout_get_score, tweet_scout_get_user_info

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

        if metadata is None:
            logger.error(f"Rugcheck error for: {token_address}")
            break

        else:
            twitter_handle = metadata.get("twitter_handle", "")
            # # Get the current timestamp
            # current_time_utc = datetime.now(timezone.utc)
            # timestamp_str = current_time_utc.strftime('%Y-%m-%d %H:%M:%S')

            # # Rugcheck - Unpack metadata
            # name = metadata.get("name", "")
            # symbol = metadata.get("symbol", "")
            # description = metadata.get("description", "")
            # creator = metadata.get("creator", "")
            # decimals = metadata.get("decimals", 0)
            # ipfs_url = metadata.get("ipfs_url", "")
            # ipfs_description = metadata.get("ipfs_description")
            # twitter_url = metadata.get("twitter_url", "")
            # twitter_handle = metadata.get("twitter_handle", "")
            # website_url = metadata.get("website_url", "")
            # website_valid = metadata.get("website_valid", "")
            # telegram_url = metadata.get("telegram_url", "")
            # image_url = metadata.get("image_url", "")

            # # Rugcheck - unpack risks
            # risk_list = risks.get("risks", [])
            # risk_score = risks.get("score", 0)

            # # Rugcheck - unpack holder metrics
            # total_pct_top_5 = holder_metrics.get("total_pct_top_5", 0)
            # total_pct_top_10 = holder_metrics.get("total_pct_top_10", 0)
            # total_pct_top_20 = holder_metrics.get("total_pct_top_20", 0)
            # total_pct_insiders = holder_metrics.get("total_pct_insiders", 0)
            
            logger.info(f"{metadata.get("symbol", "")} - {metadata.get("name", "")}")

            # results = {
            #     "timestamp": timestamp_str,
            #     "token_address": token_address,
            #     "pair_address": pair_address, 
            #     "name": name,
            #     "symbol": symbol,
            #     "description": description,
            #     "ipfs_description": ipfs_description,
            #     "creator": creator,
            #     "decimals": decimals,
            #     "ipfs_url": ipfs_url,
            #     "twitter_url": twitter_url,
            #     "twitter_handle": twitter_handle,
            #     "website_url": website_url,
            #     "website_valid": website_valid,
            #     "telegram_url": telegram_url,
            #     "image_url": image_url,
            #     "risks": ", ".join(risk_list),
            #     "score": risk_score,
            #     "total_pct_top_5": total_pct_top_5,
            #     "total_pct_top_10": total_pct_top_10,
            #     "total_pct_top_20": total_pct_top_20,
            #     "total_pct_insiders": total_pct_insiders}

        # Is DexScreener paid
        is_dex_paid_parsed, is_dex_paid_raw = await get_dex_paid(httpx_client=httpx_client, token_mint_address=token_address)
        # results["is_dexscreener_paid_parsed"] = is_dex_paid_parsed
        # results["is_dexscreener_paid_raw"] = is_dex_paid_raw
        
        print("DexScreener done")
        print(twitter_handle)

        # Extract the number of previous projects
        if twitter_handle:
            followers = tweet_scout_get_followers(twitter_handle=twitter_handle)
            twitter_score = tweet_scout_get_score(twitter_handle=twitter_handle)
            user_info = tweet_scout_get_user_info(twitter_handle=twitter_handle)

            # results["total_followers"] = followers["followers_count"]
            # results["total_influencers_count"] = followers["influencers_count"]
            # results["total_projects_count"] = followers["projects_count"]
            # results["total_venture_capitals_count"] = followers["venture_capitals_count"]
            # results["total_user_protected"] = followers["user_protected"]
            # results["twitter_score"] = twitter_score["score"]
            # results["twitter_name"] = user_info["name"]
            # results["twitter_screen_name"] = user_info["screen_name"]
            # results["twitter_description"] = user_info["description"]
            # results["twitter_followers_count"] = user_info["followers_count"]
            # results["twitter_friends_count"] = user_info["friends_count"]
            # results["twitter_register_date"] = user_info["register_date"]
            # results["twitter_tweets_count"] = user_info["tweets_count"]
            # results["twitter_verified"] = user_info["verified"]
            # results["twitter_can_dm"] = user_info["can_dm"]
        # else:
        #     twitter_score = "n/a"
        #     user_info = {key: "n/a" for key in user_info}
        #     followers = {key: "n/a" for key in followers}

        print("TweetScout done")

        # Save results to a CSV for further analysis
        await parse_data_to_save(token_address, pair_address, metadata, risks, holder_metrics, is_dex_paid_parsed, is_dex_paid_raw, followers, twitter_score, user_info)
        # await write_to_csv(results)


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



