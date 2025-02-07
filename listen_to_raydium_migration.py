import websockets
import asyncio
import json
from solders.pubkey import Pubkey
from datetime import datetime, timezone
from config import MIGRATION_ADDRESS, WS_URL, RPC_URL, RELAY_DELAY, migrations_logger
from storage_utils import store_token_address, fetch_token_address

# Parse the instruction
async def process_initialize2_transaction(data, redis_client_tokens, queue):
    """Process and decode an initialize2 transaction"""
    try:
        signature = data['transaction']['signatures'][0]
        account_keys = data['transaction']['message']['accountKeys']
        if len(account_keys) > 18:
            token_address = account_keys[18]
            pair_address = account_keys[2]
            cached_token_data = await fetch_token_address(redis_client_tokens, token_address)

            if not cached_token_data:
                migrations_logger.info(f'New token: {token_address} - Pair address: {pair_address}')
                await queue.put((token_address, pair_address))
                timestamp_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                await store_token_address(redis_client_tokens, timestamp_str, signature, token_address)
                migrations_logger.info(f'New token cached - Address: {token_address}0')
        else:
            migrations_logger.error(f'Error: Not enough account keys (found {len(account_keys)})')

    except Exception as e:
        migrations_logger.error(f'Error: {str(e)}')


# Websocket function to listen for migrations
async def listen_for_migrations(redis_client_tokens, queue):
    try:
        async with websockets.connect(WS_URL) as websocket:
            subscription_message = json.dumps({
                'jsonrpc': '2.0', 
                'id': 1, 
                'method': 
                'blockSubscribe', 
                    'params': [{
                        'mentionsAccountOrProgram': str(MIGRATION_ADDRESS)}, 
                        {'commitment': 'confirmed', 
                            'transactionDetails': 'full', 
                            'showRewards': False, 
                            'encoding': 'json', 
                            'maxSupportedTransactionVersion': 0}]
                })
            
            await websocket.send(subscription_message)
            response = await websocket.recv()

            # Log the connection
            migrations_logger.info(f'Subscription response: {response}')
            migrations_logger.info('Listening for Raydium pool initialization events...')

            # Enter loop to listen for new migrations
            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=30)
                    data = json.loads(response)
                    if 'method' in data and data['method'] == 'blockNotification' and ('params' in data) and ('result' in data['params']):
                        block_data = data['params']['result']
                        if 'value' in block_data and 'block' in block_data['value']:
                            block = block_data['value']['block']
                            if 'transactions' in block:
                                for tx in block['transactions']:
                                    logs = tx.get('meta', {}).get('logMessages', [])
                                    for log in logs:
                                        if 'Program log: initialize2: InitializeInstruction2' in log:
                                            await process_initialize2_transaction(tx, redis_client_tokens, queue)
                                            break
                except asyncio.TimeoutError:
                    pass

    except Exception as e:
        migrations_logger.error(f'Connection error: {str(e)}')
        migrations_logger.error(f'Retrying in {RELAY_DELAY} seconds...')
        await asyncio.sleep(RELAY_DELAY)