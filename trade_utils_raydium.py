from typing import Union, Any, Dict
import statistics
import json
import asyncio
import httpx
from httpx._config import Timeout
import numpy as np
from pprint import pprint

from raydium.amm_v4 import buy, sell
from config import trade_logger, RPC_URL, PRIORITY_FEE_DICT, TRADE_AMOUNT_SOL, BUY_SLIPPAGE, MAX_TRADE_TIME_MINS


# Wrapper to house all trade logic and functions
async def raydium_trade_wrapper(httpx_client: httpx.AsyncClient, pair_address: str):
    await buy_wrapper(httpx_client=httpx_client, pair_address=pair_address)
    asyncio.sleep(MAX_TRADE_TIME_MINS*60)


# Function to handle buy trade with escalating slippage and priority fees
async def buy_wrapper(httpx_client: httpx.AsyncClient, pair_address: str) -> Union[Dict[str, Any], bool]:
    """
    Executes a Raydium trade (buy) with incremental adjustments for priority fee and slippage.
    
    If the `buy` function returns None, it's assumed that the priority fee was insufficient.
    If the `buy` function returns an error containing {'Custom': 30}, it's assumed that the
    slippage was insufficient.
    
    :param httpx_client: The async HTTP client for network requests.
    :param pair_address: The address of the token pair.
    :return: The successful trade result, or False if all combinations fail.
    """
    
    # Get recent priority fees
    try:
        fees_dict = await get_qn_priority_fees(httpx_client=httpx_client)
        trade_logger.info(f"Priority fees: {fees_dict}")
    except Exception as e:
        trade_logger.error(f"Failed to fetch priority fees - {e}")
        return False

    # Create a loop of increasing priority fee levels
    fee_levels = ['50', '60', '65', '70', '75', '85']
    for level in fee_levels:
        fee_value = fees_dict.get(level)
        if fee_value is None:
            trade_logger.warning(f"No priority fee found for level {level}. Skipping.")
            continue

        # Start with the smallest slippage value and increase if slippage exceed error is received
        current_slippage = BUY_SLIPPAGE['MIN']
        while current_slippage <= BUY_SLIPPAGE['MAX']:
            trade_logger.info(f"Attempting buy with priority fee (level {level}): {fee_value} and slippage: {current_slippage}")
            result = await buy(
                pair_address=pair_address,
                sol_in=TRADE_AMOUNT_SOL,
                slippage=current_slippage,
                priority_fee=fee_value
            )
    
            if not result:
                trade_logger.warning(f"Buy attempt returned None with fee {fee_value} and slippage {current_slippage}. Increasing priority fee level")
                break  # Try the next fee level.

            if isinstance(result, dict) and 'InstructionError' in result:
                errors = result['InstructionError']
                insufficient_slippage = False
                if isinstance(errors, list):
                    if len(errors) >= 2 and isinstance(errors[1], dict) and errors[1].get('Custom') == 30:
                        insufficient_slippage = True
                    else:
                        for err in errors:
                            if isinstance(err, dict) and err.get('Custom') == 30:
                                insufficient_slippage = True
                                break

                if insufficient_slippage:
                    trade_logger.warning(f"Buy attempt failed due to insufficient slippage (current: {current_slippage}). Increasing slippage and retrying")
                    current_slippage = increase_slippage(current_slippage, BUY_SLIPPAGE)
                    continue
                else:
                    trade_logger.error(f"Buy attempt failed with unexpected error: {result}")
                    break

            trade_logger.info(f"Buy successful with priority fee {fee_value} (level {level}) and slippage {current_slippage}.")
            return result

    trade_logger.error("Buy operation failed for all priority fee and slippage combinations.")
    return False





# Wrapper to house all trade logic and functions
async def old_raydium_trade_wrapper(httpx_client: httpx.AsyncClient, pair_address: str):
    '''
        Trade wrapper which executes raydium based trade logic.
    '''

    # Get recent priority fees
    fees_dict = await get_qn_priority_fees(httpx_client=httpx_client)
    trade_logger.info(f"Priority fees: {fees_dict}")

    # Execute buy
    await buy(pair_address=pair_address, sol_in=TRADE_AMOUNT_SOL, slippage=0, priority_fee=100_000)
    
    print("Sleeping")
    await asyncio.sleep(300)
    
    print("Start sell")
    await sell(pair_address=pair_address, percentage=100, slippage=10)
    

def increase_slippage(current: int, slippage_dict: dict) -> int:
    return min(current + slippage_dict['INCREMENTS'], slippage_dict['MAX'])


# Get recent priority fees
async def get_qn_priority_fees(httpx_client: httpx.AsyncClient, fees_account: str="675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", 
                               priority_fee_dict: dict=PRIORITY_FEE_DICT):
    
    # Unpack priority fees dictionary
    multiplier = priority_fee_dict.get("PRIORITY_FEE_MULTIPLIER" ,"")
    num_blocks = priority_fee_dict.get("PRIORITY_FEE_NUM_BLOCKS","")
    max_fee = priority_fee_dict.get("PRIORITY_FEE_MAX","")
    min_fee = priority_fee_dict.get("PRIORITY_FEE_MIN","")
    
    try:

        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "qn_estimatePriorityFees",
            "params": {
                "last_n_blocks": num_blocks,
                "account": fees_account,
                "api_version": 2
            }
            })

        # Fetch the recent fees and filter for the percentiles and in per_compute_unit section
        response = await httpx_client.post(RPC_URL, headers={'Content-Type':'application/json'}, data=payload)
        json_response = response.json()
        response = json_response.get("result", "").get("per_compute_unit", "").get("percentiles", "")

        # Create a new dictionary with only fees greater than the median
        keys_to_extract = {50, 60, 65, 70, 75, 85}
        filtered_dict = {k: v for k, v in response.items() if int(k) in keys_to_extract}
        
        # Adjust values based on PRIORITY_FEE_MIN and PRIORITY_FEE_MAX
        adjusted_dict = {k: max(min_fee, min(v, max_fee)) for k, v in filtered_dict.items()}
        return adjusted_dict
        
    except Exception:
        return None







