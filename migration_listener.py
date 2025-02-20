import websockets
import asyncio
import json
from solders.pubkey import Pubkey   # type: ignore
from datetime import datetime, timezone
from config import MIGRATION_ADDRESS, WS_URL, RPC_URL, RELAY_DELAY, migrations_logger
from storage_utils import store_token_address, fetch_token_address

async def process_withdraw_transaction(data, withdraw_tokens_set):
    """Process and decode a withdraw transaction.
    
    This function extracts the token (and pair) addresses from the transaction
    when a withdraw instruction is seen and adds the token to our local cache.
    """
    # print(data)
    try:
        print(data)
        # signature = data['transaction']['signatures'][0]
        account_keys = data['transaction']['message']['accountKeys']
        if len(account_keys) > 10:
            token_address = account_keys[18]
            pair_address = account_keys[2]
            if token_address not in withdraw_tokens_set:
                migrations_logger.info(f'Withdraw event detected: Token {token_address} - Pair {pair_address}')
                withdraw_tokens_set.add(token_address)
            else:
                migrations_logger.info(f'Withdraw event already processed for token {token_address}')
        else:
            migrations_logger.error(f'Error in withdraw: Not enough account keys (found {len(account_keys)})')
    except Exception as e:
        migrations_logger.error(f'Error processing withdraw transaction: {str(e)}')


async def process_initialize2_transaction(data, redis_client_tokens, queue, withdraw_tokens_set):
    """Process and decode an initialize2 transaction only if a prior withdraw event was detected.
    
    If the token (extracted from account_keys[18]) has been seen via a withdraw event,
    then we push it to our queue, store it, and log the event.
    """
    try:
        signature = data['transaction']['signatures'][0]
        account_keys = data['transaction']['message']['accountKeys']
        if len(account_keys) > 18:
            token_address = account_keys[18]
            pair_address = account_keys[2]
            if token_address in withdraw_tokens_set:
                # Check if token has already been processed (cached)
                cached_token_data = await fetch_token_address(redis_client_tokens, token_address)
                if not cached_token_data:
                    migrations_logger.info(f'Both events confirmed for token: {token_address} - Pair: {pair_address}')
                    await queue.put((token_address, pair_address))
                    timestamp_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                    await store_token_address(redis_client_tokens, timestamp_str, signature, token_address)
                    migrations_logger.info(f'Token processed and cached: {token_address}')
                # Remove token from the set once processed
                withdraw_tokens_set.remove(token_address)
            else:
                migrations_logger.info(f'Initialize2 event for token {token_address} but no prior withdraw event found.')
        else:
            migrations_logger.error(f'Error in initialize2: Not enough account keys (found {len(account_keys)})')
    except Exception as e:
        migrations_logger.error(f'Error processing initialize2 transaction: {str(e)}')


async def listen_for_migrations(redis_client_tokens, queue):
    """
    Listen for both withdraw and initialize2 instructions.

    A local set (withdraw_tokens) keeps track of tokens that have had a withdraw event.
    Later, when an initialize2 event is seen for a token already in that set, it is processed.
    """
    # Local cache to record tokens with a withdraw event
    withdraw_tokens = set()

    try:
        async with websockets.connect(WS_URL) as websocket:
            subscription_message = json.dumps({
                'jsonrpc': '2.0', 
                'id': 1, 
                'method': 'blockSubscribe', 
                'params': [{
                    'mentionsAccountOrProgram': str(MIGRATION_ADDRESS)
                }, {
                    'commitment': 'confirmed',  
                    'transactionDetails': 'full', 
                    'showRewards': False, 
                    'encoding': 'json', 
                    'maxSupportedTransactionVersion': 0
                }]
            })
            
            await websocket.send(subscription_message)
            response = await websocket.recv()
            migrations_logger.info(f'Subscription response: {response}')
            migrations_logger.info('Listening for Pump.fun migrations - withdraw and initialize2 instructions...')

            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=30)
                    data = json.loads(response)
                    
                    if (
                        'method' in data and data['method'] == 'blockNotification' and
                        'params' in data and 'result' in data['params']
                    ):
                        block_data = data['params']['result']
                        if 'value' in block_data and 'block' in block_data['value']:
                            block = block_data['value']['block']
                            if 'transactions' in block:
                                for tx in block['transactions']:
                                    logs = tx.get('meta', {}).get('logMessages', [])
                                    for log in logs:
                                        if 'Program log: Instruction: Withdraw' in log:
                                            print("\n\n WITHDRAW INSTRUCTION FOUND\n\n")
                                            await process_withdraw_transaction(tx, withdraw_tokens)
                                        elif 'Program log: initialize2: InitializeInstruction2' in log:
                                            await process_initialize2_transaction(tx, redis_client_tokens, queue, withdraw_tokens)
                except asyncio.TimeoutError:
                    pass

    except Exception as e:
        migrations_logger.error(f'Connection error: {str(e)}')
        migrations_logger.error(f'Retrying in {RELAY_DELAY} seconds...')
        await asyncio.sleep(RELAY_DELAY)
        await listen_for_migrations(redis_client_tokens, queue)
