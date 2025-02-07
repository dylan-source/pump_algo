# listener_wss_utils.py
import asyncio
import json
import ssl
import websockets
from datetime import datetime, timezone

from config import WS_URL, COMMITTMENT_LEVEL, MONITORED_ADDRESS, RELAY_DELAY, logger
from z_deprecated_rpc_utils import fetch_transaction_details_rpc
from z_deprecated_listener_transaction_utils import extract_token_and_pair_from_response
from z_deprecated_metadata_utils import fetch_token_metadata
from backup_csv_utils import write_to_csv
from storage_utils import fetch_token_address, store_token_address

def process_response(data):
    try:
        # Check for top-level 'result'
        if "result" in data:
            result = data["result"]
        else:
            # Check nested structure under 'params'
            params = data.get("params", {})
            result = params.get("result", {})
        
        # Log if 'result' is empty or None
        if not result:
            logger.error(f"'result' missing or empty in data: {data}")
            return None

        # Ensure 'value' exists within 'result'
        value = result.get("value", {})
        if not value:
            logger.error(f"'value' key missing in 'result': {result}")
            return None

        # Extract signature
        signature = value.get("signature", None)
        if not signature:
            logger.error(f"Signature missing in response value: {value}")
            return None

        logger.info(f"Extracted signature: {signature}")
        return signature
    except Exception as e:
        logger.error(f"Error processing response: {e}")
        logger.error(f"Raw data causing error: {data}")
        return None





async def monitor_transactions(queue, redis_client, httpx_client):
    ssl_context = ssl._create_unverified_context()
    retry_delay = RELAY_DELAY
    max_retry_delay = 300

    while True:
        try:
            async with websockets.connect(WS_URL, ssl=ssl_context) as websocket:
                current_time_utc = datetime.now(timezone.utc)
                timestamp_str = current_time_utc.strftime('%Y-%m-%d %H:%M:%S')
                logger.info(timestamp_str)
                logger.info(f"Connected to WebSocket: {WS_URL}")
                retry_delay = RELAY_DELAY

                subscription_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": [
                        {"mentions": [MONITORED_ADDRESS]},
                        {
                            "encoding": "jsonParsed",
                            "commitment": COMMITTMENT_LEVEL
                        }
                    ]
                }

                await websocket.send(json.dumps(subscription_request))
                logger.info(f"Subscribed to logs for address: {MONITORED_ADDRESS}")

                while True:
                    try:
                        response = await websocket.recv()
                        data = json.loads(response)

                        logger.debug(f"Raw WebSocket data: {data}")  # Add this to analyze structure

                        if "result" in data and isinstance(data["result"], int):
                            logger.info(f"Subscription acknowledged with ID: {data['result']}")
                            continue

                        if data.get("method") == "logsNotification":
                            signature = process_response(data)
                            if signature:
                                try:
                                    api_response = fetch_transaction_details_rpc(signature)
                                    logger.debug(f"API Response for signature {signature}: {api_response}")

                                    if not api_response:
                                        logger.error(f"No API response or empty response for signature: {signature}")
                                        continue

                                    try:
                                        token_address, pair_address = extract_token_and_pair_from_response(api_response)
                                        logger.info(f"Extracted addresses for signature {signature}: token={token_address}, pair={pair_address}")

                                        # Check if we have already received the token. 
                                        if token_address and pair_address:
                                            cached_token_data = await fetch_token_address(redis_client, token_address)
                                            if cached_token_data:
                                                logger.info(f"Already received this token: {token_address}")
                                            else:
                                                print("\nNew token alert\n")
                                                token_symbol, token_name = await fetch_token_metadata(httpx_client, token_address)
                                                timestamp_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                                                await queue.put((token_address, pair_address))
                                                await store_token_address(redis_client, timestamp_str, token_address, token_name, token_symbol)
                                                logger.info(f"New token cached: {token_symbol} - {token_name} - {token_address}")
                                        # else:
                                        #     logger.error(f"Failed to extract token/pair addresses for signature: {signature}")
                                    except Exception as e:
                                        logger.error(f"Error extracting token/pair addresses for signature {signature}: {e}")
                                        logger.error(f"API Response at failure: {api_response}")
                                except Exception as e:
                                    logger.error(f"Error processing transaction for signature {signature}: {e}")

                    except json.JSONDecodeError:
                        logger.error("Failed to decode JSON response")
                    except websockets.exceptions.ConnectionClosedError as e:
                        logger.error(f"WebSocket connection closed with error: {e}")
                        break
                    except Exception as e:
                        logger.error(f"Unexpected error in WebSocket listener: {e}")
                        logger.debug(f"Raw response at error: {data}")
                        break

        except Exception as e:
            logger.error(f"Error connecting to WebSocket: {e}")
        logger.error(f"Reconnecting in {retry_delay} seconds...")
        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, max_retry_delay)

