import websockets
import asyncio
import json
from solders.pubkey import Pubkey   # type: ignore
from datetime import datetime, timezone
from config import MIGRATION_ADDRESS, WS_URL, RPC_URL, RELAY_DELAY, migrations_logger

from filter_utils import process_new_tokens, trade_filters
from storage_utils import parse_migrations_to_save

async def process_withdraw_transaction(data, withdraw_tokens, httpx_client):
    """Process and decode a withdraw transaction.
    
    This function extracts the token and pair addresses from the transaction.
    After running your risk filters (not shown here), if the token passes,
    it is added to the in-memory dictionary.
    """
    try:
        account_keys = data['transaction']['message']['accountKeys']
        if len(account_keys) > 10:
            token_address = account_keys[10] # consider fetching the address from postTokenBalances where owner is the migration address
            if token_address not in withdraw_tokens:
                migrations_logger.info(f'Withdraw event detected - {token_address}')
                withdraw_tokens.add(token_address)
                
                # Run the token filters and save the data to the spreadsheet
                filters_result, data_to_save = await process_new_tokens(httpx_client, token_address)
                if filters_result is not None:
                    await parse_migrations_to_save(token_address=token_address, data_to_save=data_to_save, filters_result=filters_result)
                    
            else:
                migrations_logger.info(f'Withdraw event already processed for token {token_address}')
        else:
            migrations_logger.error(f'Error in withdraw: Not enough account keys (found {len(account_keys)})')
    except Exception as e:
        migrations_logger.error(f'Error processing withdraw transaction: {str(e)}')


async def process_initialize2_transaction(data, queue, withdraw_tokens):
    """Process and decode an initialize2 transaction only if a prior withdraw event was detected.
    
    If the token (extracted from account_keys[18]) has been seen via a withdraw event,
    then we push it to our queue, store it, and log the event.
    """
    try:
        account_keys = data['transaction']['message']['accountKeys']
        if len(account_keys) > 18:
            token_address = account_keys[18]
            pair_address = account_keys[2]
            if token_address in withdraw_tokens:
                # Check if token has already been processed (cached)
                migrations_logger.info(f'Both events confirmed for token: {token_address} - Pair: {pair_address}')
                
                # await execute_buy(token_address, pair_address)
                # await queue.put((token_address, pair_address))
                
                # Remove token from the set once processed
                withdraw_tokens.remove(token_address)
            else:
                migrations_logger.info(f'Initialize2 event for token {token_address} but no prior withdraw event found.')
        else:
            migrations_logger.error(f'Error in initialize2: Not enough account keys (found {len(account_keys)})')
    except Exception as e:
        migrations_logger.error(f'Error processing initialize2 transaction: {str(e)}')


async def listen_for_migrations(queue, httpx_client):
    """
    Listen for both withdraw and initialize2 instructions.

    A local set (withdraw_tokens) keeps track of tokens that have had a withdraw event.
    Later, when an initialize2 event is seen for a token already in that set, it is processed.
    """
    
    # async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as httpx_client:
    # use the client for your HTTP calls

    
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
                                            await process_withdraw_transaction(tx, withdraw_tokens, httpx_client)
                                        elif 'Program log: initialize2: InitializeInstruction2' in log:
                                            await process_initialize2_transaction(tx, queue, withdraw_tokens)
                except asyncio.TimeoutError:
                    pass

    except Exception as e:
        migrations_logger.error(f'Connection error: {str(e)}')
        migrations_logger.error(f'Retrying in {RELAY_DELAY} seconds...')
        await asyncio.sleep(RELAY_DELAY)
        await listen_for_migrations(queue, httpx_client)
