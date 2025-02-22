import asyncio
import websockets
import json
import re
import aiohttp
from datetime import datetime
from config import MIGRATION_ADDRESS, WS_URL, RPC_URL, RELAY_DELAY, migrations_logger

from solders.signature import Signature # type: ignore
from solana.rpc.commitment import Processed, Confirmed, Finalized
from solana.rpc.async_api import AsyncClient
rpc_client = AsyncClient(RPC_URL)
        

def contains_initialize2_log(logs):
    pattern = re.compile(r"Program log: initialize2:\s*InitializeInstruction2")
    return any(pattern.search(log) for log in logs)


async def listen_logs():
    async with websockets.connect(WS_URL) as websocket:
        # Subscribe to logs that mention the migration address.
        subscription_request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [MIGRATION_ADDRESS]},
                {"commitment": "confirmed"}
            ]
        })
        await websocket.send(subscription_request)
        response = await websocket.recv()
        migrations_logger.info(f'Subscription response: {response}')
        migrations_logger.info('Listening for Pump.fun migrations - withdraw and initialize2 instructions...')

        while True:
            try:
                message = await websocket.recv()        # response = await asyncio.wait_for(websocket.recv(), timeout=30)
                data = json.loads(message)
                
                if (
                        'method' in data and data['method'] == 'logsNotification' and
                        'params' in data and 'result' in data['params']
                    ):
                        # pprint(data)
                        block_data = data['params']['result']
                        if 'value' in block_data and 'logs' in block_data['value']:
                            logs = block_data['value']['logs']
                            if 'Program log: Instruction: Withdraw' in logs:
                                sig = data['params']['result']["value"]["signature"]
                                migrations_logger.info(f"Withdraw signature: {sig}")
                            # elif 'Program log: initialize2:' in logs:
                            elif contains_initialize2_log(logs):
                                sig = data['params']['result']["value"]["signature"]
                                migrations_logger.info(f"Initialize2 signature: {sig}")
                                
                                
                                # for tx in block['transactions']:
                                #     logs = tx.get('meta', {}).get('logMessages', [])
                                    # for log in logs:
                                        # if 'Program log: Instruction: Withdraw' in log:
                                        #     await process_withdraw_transaction(tx, withdraw_tokens, httpx_client)
                                        # elif 'Program log: initialize2: InitializeInstruction2' in log:
                                        #     await process_initialize2_transaction(tx, queue, withdraw_tokens)
                
            
            except Exception as e:
                migrations_logger.error(f"Exception: {e}")

async def main():
    try:
        await listen_logs()
    except Exception as e:
        migrations_logger.error(f"Listener exception: {e}")
        migrations_logger.error(f"Sleeping for {RELAY_DELAY} seconds")
        await asyncio.sleep(RELAY_DELAY)

if __name__ == "__main__":
    # signature = "5W6fnjgQhtBLuMrpCckx5P3dYNxsxrKzv1vAuwHucTQPnNxawz8urVcNJMbDZTbxt3Xeg5nT6dRK91ejvUVEmzop"
    # res = asyncio.run(fetch_transaction_details(signature))
    
    asyncio.run(main())
