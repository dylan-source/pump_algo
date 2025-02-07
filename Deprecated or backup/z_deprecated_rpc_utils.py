# rpc_utils.py
import requests
from config import RPC_URL, COMMITTMENT_LEVEL, logger

import requests

def fetch_transaction_details_rpc(signature):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "jsonParsed",
                "commitment": COMMITTMENT_LEVEL,
                "maxSupportedTransactionVersion": 0
            }
        ]
    }

    try:
        # Make the POST request to the RPC URL
        response = requests.post(RPC_URL, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors

        # Parse JSON response
        try:
            data = response.json()
        except ValueError as e:
            logger.error(f"Failed to decode JSON response: {e}")
            logger.debug(f"Raw response: {response.text}")
            return None

        # Ensure the result key exists in the response
        result = data.get("result")
        if not result:
            logger.error(f"'result' key missing in RPC response: {data}")
            return None

        return data  # Return the full response to inspect further downstream
    except requests.exceptions.RequestException as e:
        logger.error(f"Error making request to RPC: {e}")
        return None

