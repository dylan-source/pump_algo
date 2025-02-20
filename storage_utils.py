import asyncio
import json
import os
import csv
from datetime import datetime, timezone
from config import CSV_MIGRATIONS_FILE, CSV_TRADES_FILE, migrations_logger, trade_logger

#---------------------
#   REDIS FUNCTIONS
#---------------------

# Cache the trade data when a buy is executed
async def store_trade_data(redis, token_address, trade_data):
    '''
        trade_data schema:
                {
                    'buy_timestamp': timestamp, 
                    'buy_transaction_hash': str(signature), 
                    'buy_pair_address': str(signature), 
                    'buy_tokens_spent': tokens_spent, 
                    'buy_tokens_received': tokens_received
                 }
    '''

    trade_data_json = json.dumps(trade_data)
    result = await redis.set(token_address, trade_data_json)
    return result


# Fetch teh trade data for when a sell is executed
async def fetch_trade_data(redis_client_trades, token_address):
    data = await redis_client_trades.get(token_address)
    if data:
        return json.loads(data)


# When the script starts fetch any non-SOL tokens that in the wallet to be sold
async def warmup_fetch_trades(redis_client):
    token_address = '5QBhsB1BndNhCN9bLQnzXAvmFYjz8RHzvBPQESjmpump'  # Example address to assist in identifying the pattern
    pattern = f'{token_address}0*'
    matching_keys = [key async for key in redis_client.scan_iter(pattern)]
    values = await asyncio.gather(*(redis_client.get(key) for key in matching_keys))
    trades = dict(zip(matching_keys, values))
    # print(trades)


# Store the newly migrated token's address
async def store_token_address(redis_client_token, timestamp, signature, token_address):
    token_data = {
        'signature': signature, 
        'timestamp': timestamp
        }
    trade_data_json = json.dumps(token_data)
    result = await redis_client_token.set(token_address, trade_data_json)
    return result


# Fetch token addresses in the cache
async def fetch_token_address(redis_client_token, token_address):
    data = await redis_client_token.get(token_address)
    if data:
        return json.loads(data)


#--------------------
#   CSV FUNCTIONS
#--------------------

# Parse migrations to be saved in a csv
async def parse_migrations_to_save(token_address, data_to_save, filters_result):
    
    # Get the current timestamp
    current_time_utc = datetime.now(timezone.utc)
    timestamp_str = current_time_utc.strftime('%Y-%m-%d %H:%M:%S')
    
    # Unpack the various dictionaries
    metadata = data_to_save.get('metadata', '')
    risks = data_to_save.get('risks', '')
    holder_metrics = data_to_save.get('holder_metrics', '')

     
    # Unpack the details of each dictionary
    results = {
        'timestamp': timestamp_str, 
        'token_address': token_address, 

        # Rugcheck token metadata
        'name': metadata.get('name', ''), 
        'symbol': metadata.get('symbol', ''), 
        'description': metadata.get('description', ''), 
        'ipfs_description': metadata.get('ipfs_description'), 
        'creator': metadata.get('creator', ''), 
        'decimals': metadata.get('decimals', 0), 
        'ipfs_url': metadata.get('ipfs_url', 0), 
        'twitter_url': metadata.get('twitter_url', 0), 
        'twitter_handle': metadata.get('twitter_handle', 0), 
        'website_url': metadata.get('website_url', 0), 
        'website_valid': metadata.get('website_valid', 0), 
        'telegram_url': metadata.get('telegram_url', 0), 
        'image_url': metadata.get('image_url', 0), 

        # Unpack Rugcheck risks
        'risks': risks.get('risks', 0), 
        'score': risks.get('score', 0), 

        # Unpack Rugcheck holder analysis
        'total_pct_top_5': holder_metrics.get('total_pct_top_5', 0), 
        'total_pct_top_10': holder_metrics.get('total_pct_top_10', 0), 
        'total_pct_top_20': holder_metrics.get('total_pct_top_20', 0), 
        'total_pct_insiders': holder_metrics.get('total_pct_insiders', 0), 

        # Get DexScreener resutls
        'is_dexscreener_paid_parsed': data_to_save.get('is_dex_paid_parsed', 0), 
        'is_dexscreener_paid_raw': data_to_save.get('is_dex_paid_raw', 0), 

        # Do we execute the trade or not - what is the result of the trade filters?
        'execute_trade': filters_result
        }
    
    # Save the results to a csv
    await write_migrations_to_csv(results)


# Save migrations to a csv for further analysis
async def write_migrations_to_csv(data_dict):
    
    # Define the CSV columns
    token_columns = [
        'timestamp', 
        'token_address', 
        'name', 
        'symbol', 
        'description', 
        'ipfs_description', 
        'creator', 
        'decimals', 
        'ipfs_url', 
        'twitter_url', 
        'twitter_handle', 
        'website_url', 
        'website_valid', 
        'telegram_url', 
        'image_url', 
        'risks', 
        'score', 
        'total_pct_top_5', 
        'total_pct_top_10', 
        'total_pct_top_20', 
        'total_pct_insiders', 
        'is_dexscreener_paid_parsed', 
        'is_dexscreener_paid_raw', 
        'number_of_twitter_handles', 
        'previous_twitter_handles', 
        'total_followers', 
        'total_influencers_count', 
        'total_projects_count', 
        'total_venture_capitals_count', 
        'total_user_protected', 
        'twitter_score', 
        'twitter_name', 
        'twitter_screen_name', 
        'twitter_description', 
        'twitter_followers_count', 
        'twitter_friends_count', 
        'twitter_register_date', 
        'twitter_tweets_count', 
        'twitter_verified', 
        'twitter_can_dm', 
        'execute_trade'
        ]

    file_exists = os.path.isfile(CSV_MIGRATIONS_FILE)
    with open(CSV_MIGRATIONS_FILE, mode='a', newline='', encoding='utf-8') as csvfile:
        fieldnames = token_columns
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data_dict)
    migrations_logger.info('Saved new token to migrations csv')


# Save trade data to a csv
async def write_trades_to_csv(redis_client, tx_address, sell_data_dict):
    
    # Get buy trade data from cache
    buy_data_dict = await fetch_trade_data(redis_client, tx_address)
    pair_address = buy_data_dict.get("pair_address", "Not pair_address in cache")
    
    try:
        effective_buy_price = -buy_data_dict['buy_tokens_spent'] / buy_data_dict['buy_tokens_received']
        effective_sell_price = sell_data_dict['sell_tokens_received'] / -sell_data_dict['sell_tokens_spent']
        return_value = sell_data_dict['sell_tokens_received'] + buy_data_dict['buy_tokens_spent']
        return_perc = (sell_data_dict['sell_tokens_received'] / -buy_data_dict['buy_tokens_spent'] - 1) * 100
        trade_logger.info(f'Return value in SOL for {pair_address}: {return_value}')
        trade_logger.info(f'Return % for {pair_address}: {round(return_perc,2)}%')

        token_columns = [
            'token_address', 
            'buy_timestamp', 
            'buy_transaction_hash', 
            'buy_tokens_spent', 
            'buy_tokens_received', 
            'buy_effective_price', 
            'sell_timestamp', 
            'sell_transaction_hash', 
            'sell_tokens_spent', 
            'sell_tokens_received', 
            'sell_effective_price', 
            'return_value', 
            'return_perc' 
            ]
        
        # Merge the 2 dictionaries and update it with the new fileds
        data_dict = buy_data_dict | sell_data_dict
        data_dict.update({
            'token_address': tx_address, 
            'return_value': return_value, 
            'return_perc': return_perc, 
            'buy_effective_price': effective_buy_price, 
            'sell_effective_price': effective_sell_price
            })
        
        # Save to CSV
        file_exists = os.path.isfile(CSV_TRADES_FILE)
        with open(CSV_TRADES_FILE, mode='a', newline='', encoding='utf-8') as csvfile:
            fieldnames = token_columns
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(data_dict)

            # Log the saved result
            trade_logger.info('Saved new trade to csv')
            
            # Delete the key from Redis and log accordingly
            # result = await redis_client.delete(tx_address)
            # if result:
            #     trade_logger.info(f'Redis key deleted for {pair_address}: True')
            # else:
            #     trade_logger.error(f'Redis key NOT deleted for {pair_address}: False')

    except Exception as e:
        trade_logger.error(f'Error with write_trades_to_csv function: {e}')