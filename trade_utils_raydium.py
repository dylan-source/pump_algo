from typing import Union, Any, Dict
import statistics
import json
import asyncio
import httpx
from httpx._config import Timeout
import numpy as np
from solders.transaction_status import TransactionErrorInstructionError, InstructionErrorCustom # type: ignore

from raydium.amm_v4 import buy, sell
from config import trade_logger, RPC_URL, PRIORITY_FEE_DICT, TRADE_AMOUNT_SOL, BUY_SLIPPAGE, SELL_SLIPPAGE, MAX_TRADE_TIME_MINS


# Wrapper to house all trade logic and functions
async def raydium_trade_wrapper(httpx_client: httpx.AsyncClient, pair_address: str):
    # await execute_buy(httpx_client=httpx_client, pair_address=pair_address)
    # await asyncio.sleep(MAX_TRADE_TIME_MINS*60)
    
    await execute_sell(httpx_client=httpx_client, pair_address=pair_address)


# Function to handle buy trade with escalating slippage and priority fees
async def execute_buy(httpx_client: httpx.AsyncClient, pair_address: str) -> Union[Dict[str, Any], bool]:
    """
    Executes a Raydium trade (buy) with incremental adjustments for priority fee and slippage.
    
    If the `buy` function returns None, it's assumed that the priority fee was insufficient.
    If the `buy` function returns an error containing {'Custom': 30}, it's assumed that the
    slippage was insufficient.
    
    :param httpx_client: The async HTTP client for network requests.
    :param pair_address: The address of the token pair.
    :return: The successful trade result, or False if all combinations fail.
    """
    
    trade_logger.info(f"Starting buy transaction for pair address: {pair_address}")
    
    # Get recent priority fees
    try:
        fees_dict = await get_qn_priority_fees(httpx_client=httpx_client)
        trade_logger.info(f"Priority fees: {fees_dict}")
    except Exception as e:
        trade_logger.error(f"Failed to fetch priority fees - {e}")
        return False

    try:
        # Create a loop of increasing priority fee levels
        fee_levels = ['30', '40', '50', '60', '65', '70', '75', '85']
        for level in fee_levels:
            fee_value = fees_dict.get(level)
            if fee_value is None:
                trade_logger.warning(f"No priority fee found for {level}th. Skipping.")
                continue

            # Start with the smallest slippage value and increase if slippage exceed error is received
            current_slippage = BUY_SLIPPAGE['MIN']
            while current_slippage <= BUY_SLIPPAGE['MAX']:
                trade_logger.info(f"Attempting buy with priority fee: {fee_value} ({level}th) and slippage: {current_slippage}%")
                result = await buy(
                    pair_address=pair_address,
                    sol_in=TRADE_AMOUNT_SOL,
                    slippage=current_slippage,
                    priority_fee=fee_value
                )
        
                # If False/None is returned - typically due to insufficient priority fees. Break loop and try next fee level
                if not result:
                    trade_logger.warning(f"Buy failed with fee {fee_value} and slippage {current_slippage}%. Increasing priority fee")
                    break 
                
                # Catch Raydium custom errors
                if isinstance(result, InstructionErrorCustom):      # class 'solders.transaction_status.InstructionErrorCustom'
                # if isinstance(result, TransactionErrorInstructionError):      
                    # error = result.err.code
                    error = result.code
                    if error == 30:
                        trade_logger.warning(f"Buy failed - insufficient slippage ({current_slippage}%). Increasing slippage and retrying")
                        current_slippage = increase_slippage(current_slippage, BUY_SLIPPAGE)
                        continue
                    # Catches other errors
                    else:   
                        trade_logger.error(f"Buy failed with unexpected error: {error}")
                        break

                # If buy function returns True, then trade and confirmation was successful
                trade_logger.info(f"Buy successful with priority fee {fee_value} ({level}th) and slippage {current_slippage}.")
                return result

        # Fail-safe if trade exhausts slippage or priority fee levels return Fa
        trade_logger.error("Buy operation failed for all priority fee and slippage combinations.")
        return False
    
    except Exception as e:
        trade_logger.error(f"Unexpected buy function error: {e}")
        return False


# Helper function to increase slippage in line with dict settings
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
        keys_to_extract = {30, 40, 50, 60, 65, 70, 75, 85}
        filtered_dict = {k: v for k, v in response.items() if int(k) in keys_to_extract}
        
        # Adjust values based on PRIORITY_FEE_MIN and PRIORITY_FEE_MAX
        adjusted_dict = {k: max(min_fee, min(v, max_fee)) for k, v in filtered_dict.items()}
        return adjusted_dict
        
    except Exception:
        return None





# Function to handle sell trade with escalating slippage and priority fees
async def execute_sell(httpx_client: httpx.AsyncClient, pair_address: str) -> Union[Dict[str, Any], bool]:
    """
    Executes a Raydium trade (sell) with incremental adjustments for priority fee and slippage.
    
    If the `sell` function returns None, it's assumed that the priority fee was insufficient.
    If the `sell` function returns an error containing {'Custom': 30}, it's assumed that the
    slippage was insufficient.
    
    :param httpx_client: The async HTTP client for network requests.
    :param pair_address: The address of the token pair.
    :return: The successful trade result, or False if all combinations fail.
    """
    
    trade_logger.info(f"Starting sell transaction for pair address: {pair_address}")
    
    # Get recent priority fees
    try:
        fees_dict = await get_qn_priority_fees(httpx_client=httpx_client)
        trade_logger.info(f"Priority fees: {fees_dict}")
    except Exception as e:
        trade_logger.error(f"Failed to fetch priority fees - {e}")
        return False

    try:
        # Create a loop of increasing priority fee levels
        fee_levels = ['30', '40', '50', '60', '65', '70', '75', '85']
        for level in fee_levels:
            fee_value = fees_dict.get(level)
            if fee_value is None:
                trade_logger.warning(f"No priority fee found for {level}th. Skipping.")
                continue

            # Start with the smallest slippage value and increase if slippage exceed error is received
            current_slippage = SELL_SLIPPAGE['MIN']
            while current_slippage <= SELL_SLIPPAGE['MAX']:
                trade_logger.info(f"Attempting sell with priority fee: {fee_value} ({level}th) and slippage: {current_slippage}%")
                
                
                # Lower percentage for testing
                result = await sell(
                    pair_address=pair_address,
                    percentage=5,
                    slippage=current_slippage,
                    priority_fee=fee_value
                )
        
                # If False/None is returned - typically due to insufficient priority fees. Break loop and try next fee level
                if not result:
                    trade_logger.warning(f"Sell failed with fee {fee_value} and slippage {current_slippage}%. Increasing priority fee")
                    break 
                
                # Catch Raydium custom errors
                if isinstance(result, InstructionErrorCustom):      # class 'solders.transaction_status.InstructionErrorCustom'
                # if isinstance(result, TransactionErrorInstructionError):      
                    # error = result.err.code
                    error = result.code
                    if error == 30:
                        trade_logger.warning(f"Sell failed - insufficient slippage ({current_slippage}%). Increasing slippage and retrying")
                        current_slippage = increase_slippage(current_slippage, SELL_SLIPPAGE)
                        continue
                    # Catches other errors
                    else:   
                        trade_logger.error(f"Sell failed with unexpected error: {error}")
                        break
                
                # Catch all other errors
                elif isinstance(result, Exception):
                    trade_logger.error(f"Generic error - type: {type(result)} - error: {result}")
                    continue

                # If Sell function returns True, then trade and confirmation was successful
                trade_logger.info(f"Sell successful with priority fee {fee_value} ({level}th) and slippage {current_slippage}.")
                return result

        # Fail-safe if trade exhausts slippage or priority fee levels return Fa
        trade_logger.error("Sell operation failed for all priority fee and slippage combinations.")
        return False
    
    except Exception as e:
        trade_logger.error(f"Unexpected buy function error: {e}")
        return False

