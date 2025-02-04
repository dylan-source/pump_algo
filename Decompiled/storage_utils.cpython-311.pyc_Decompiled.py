# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: /Users/dylanmartens/Documents/Coding/Pump sniping/Feb_03/storage_utils.py
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2025-01-31 08:43:10 UTC (1738312990)

import asyncio
import json
import os
import csv
from datetime import datetime, timezone
from config import CSV_MIGRATIONS_FILE, CSV_TRADES_FILE, migrations_logger, trade_logger

async def store_trade_data(redis_client_trades, signature, timestamp, token_address, tokens_spent, tokens_received):
    trade_data = {'buy_timestamp': timestamp, 'buy_transaction_hash': str(signature), 'buy_tokens_spent': tokens_spent, 'buy_tokens_received': tokens_received}
    trade_data_json = json.dumps(trade_data)
    result = await redis_client_trades.set(token_address, trade_data_json)
    return result

async def fetch_trade_data(redis_client_trades, token_address):
    data = await redis_client_trades.get(token_address)
    if data:
        return json.loads(data)

async def warmup_fetch_trades(redis_client):
    token_address = '5QBhsB1BndNhCN9bLQnzXAvmFYjz8RHzvBPQESjmpump'
    pattern = f'{token_address}0*'
    matching_keys = [key async for key in redis_client.scan_iter(pattern)]
    values = await asyncio.gather(*(redis_client.get(key) for key in matching_keys))
    trades = dict(zip(matching_keys, values))
    print(trades)

async def store_token_address(redis_client_token, timestamp, signature, token_address):
    token_data = {'signature': signature, 'timestamp': timestamp}
    trade_data_json = json.dumps(token_data)
    result = await redis_client_token.set(token_address, trade_data_json)
    return result

async def fetch_token_address(redis_client_token, token_address):
    data = await redis_client_token.get(token_address)
    if data:
        return json.loads(data)

async def parse_migrations_to_save(token_address, pair_address, data_to_save, filters_result):
    current_time_utc = datetime.now(timezone.utc)
    timestamp_str = current_time_utc.strftime('%Y-%m-%d %H:%M:%S')
    metadata = data_to_save.get('metadata', '')
    risks = data_to_save.get('risks', '')
    holder_metrics = data_to_save.get('holder_metrics', '')
    results = {'timestamp': timestamp_str, 'token_address': token_address, 'pair_address': pair_address, 'name': metadata.get('name', ''), 'symbol': metadata.get('symbol', ''), 'description': metadata.get('description', ''), 'ipfs_description': metadata.get('ipfs_description'), 'creator': metadata.get('creator', ''), 'decimals': metadata.get('decimals', 0), 'telegram_url': risks.get('score', 0), 'total_pct_top_10': holder_metrics.get('total_pct_top_5', 0), 'total_pct_top_20': holder_metrics.get('total_pct_top_20', 0), 'total_pct_insiders': data_to_save.get('is_dex_paid_parsed', 0), 'is_dex_paid_raw': data_to_save.get('is_dex_paid_raw', 0), 'filters_result': filters_result}
    await write_migrations_to_csv(results)

async def write_migrations_to_csv(data_dict):
    token_columns = ['timestamp', 'token_address', 'pair_address', 'name', 'symbol', 'description', 'ipfs_description', 'creator', 'decimals', 'ipfs_url', 'twitter_url', 'twitter_handle', 'website_url', 'website_valid', 'telegram_url', 'image_url', 'risks', 'score', 'total_pct_top_5', 'total_pct_top_10', 'total_pct_top_20', 'total_pct_insiders', 'is_dexscreener_paid_parsed', 'is_dexscreener_paid_raw', 'number_of_twitter_handles', 'previous_twitter_handles', 'total_followers', 'total_influencers_count', 'total_projects_count', 'total_venture_capitals_count', 'total_user_protected', 'twitter_score', 'twitter_name', 'twitter_screen_name', 'twitter_description', 'twitter_followers_count', 'twitter_friends_count', 'twitter_register_date', 'twitter_tweets_count', 'twitter_verified', 'twitter_can_dm', 'execute_trade']
    file_exists = os.path.isfile(CSV_MIGRATIONS_FILE)
    with open(CSV_MIGRATIONS_FILE, mode='a', newline='', encoding='utf-8') as csvfile:
        fieldnames = token_columns
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data_dict)
    migrations_logger.info('Saved new token to csv')

async def write_trades_to_csv(tx_address, buy_data_dict, sell_data_dict, redis_client):
    try:
        effective_buy_price = -buy_data_dict['buy_tokens_spent'] / buy_data_dict['buy_tokens_received']
        effective_sell_price = -sell_data_dict['sell_tokens_received'] / sell_data_dict['sell_tokens_spent']
        return_value = sell_data_dict['sell_tokens_received'] + buy_data_dict['buy_tokens_spent']
        return_perc = (sell_data_dict['sell_tokens_received'] / -buy_data_dict['buy_tokens_spent'] - 1) * 100
        trade_logger.info(f'Return value in SOL for {tx_address}: {return_value}0')
        trade_logger.info(f'Return % for {tx_address}: {return_perc}0')
        token_columns = ['token_address', 'buy_timestamp', 'buy_transaction_hash', 'buy_tokens_spent', 'buy_tokens_received', 'buy_effective_price', 'sell_timestamp', 'sell_transaction_hash', 'sell_tokens_spent', 'sell_tokens_received', 'sell_effective_price', 'return_value', 'return_perc']
        data_dict = buy_data_dict | sell_data_dict
        data_dict.update({'token_address': tx_address, 'return_value': return_value, 'return_perc': return_perc, 'buy_effective_price': effective_buy_price, 'sell_effective_price': effective_sell_price})
        file_exists = os.path.isfile(CSV_TRADES_FILE)
        with open(CSV_TRADES_FILE, mode='a', newline='', encoding='utf-8') as csvfile:
            fieldnames = token_columns
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(data_dict)
            trade_logger.info('Saved new trade to csv')
            result = await redis_client.delete(tx_address)
            if result:
                trade_logger.info(f'Redis key deleted for {tx_address}: True')
            else:
                trade_logger.error(f'Redis key NOT deleted for {tx_address}0')
    except Exception as e:
        trade_logger.error(f'Error with write_trades_to_csv function: {e}0')