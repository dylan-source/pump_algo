from typing import Union, Any, Dict
import statistics
import json
import asyncio
import httpx
from httpx._config import Timeout
import numpy as np
from solana.rpc.types import TokenAccountOpts
from solana.rpc.commitment import Processed, Confirmed, Finalized

from solders.pubkey import Pubkey # type: ignore
from solders.transaction_status import TransactionErrorInstructionError, InstructionErrorCustom # type: ignore

from utils.api import get_pool_info_by_mint
from raydium.amm_v4 import buy, sell
from raydium.constants import TOKEN_PROGRAM_ID, WSOL
from config import client, trade_logger, RPC_URL, PRIORITY_FEE_DICT, TRADE_AMOUNT_SOL, BUY_SLIPPAGE, SELL_SLIPPAGE, MAX_TRADE_TIME_MINS, JUPITER_QUOTE_URL, WALLET_ADDRESS


# Wrapper to house all trade logic and functions
async def raydium_trade_wrapper(httpx_client: httpx.AsyncClient, pair_address: str):
    
    buy_result = await execute_buy(httpx_client=httpx_client, pair_address=pair_address)
    if buy_result:
        await asyncio.sleep(MAX_TRADE_TIME_MINS*60)
        await execute_sell(httpx_client=httpx_client, pair_address=pair_address)
    else:
        return None


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
                    percentage=100,
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


# Helper function to increase slippage in line with dict settings
def increase_slippage(current: int, slippage_dict: dict) -> int:
    return min(current + slippage_dict['INCREMENTS'], slippage_dict['MAX'])


# Get recent priority fees
async def get_qn_priority_fees(httpx_client: httpx.AsyncClient, fees_account: str="675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", priority_fee_dict: dict=PRIORITY_FEE_DICT):
    
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


# Fetch quote from Jupiter
async def get_jupiter_quote(httpx_client:httpx.AsyncClient, input_address:str, amount:int=1_000_000, slippage:str=1_000):
    """
    Fetch a quote from Jupiter v6 asynchronously.
    'amount' is in lamport
    'slippage_bps' in basis points
    """
    params = {
        "inputMint": input_address,
        "outputMint": WSOL,
        "amount": amount,
        "slippageBps": slippage,
        # "restrictIntermediateTokens": True,
        "swapMode": "ExactIn"
    }
    
    quote_response = await httpx_client.get(JUPITER_QUOTE_URL, headers={'Accept':'application/json'}, params=params)
    quote_response = quote_response.json()

    # Define risky address for logging purposes
    if not quote_response:
        trade_logger.error(f"No routes found for: {input_address}")
        return None
    else:
        trade_logger.info(f"Routes found for address: {input_address}")
        return quote_response
    
    
# Failsafe execute sell - to clear wallet of SPL tokens
async def startup_sell(httpx_client:httpx.AsyncClient):
    try:
        # Get SPL tokens in wallet and return None if no tokens in wallet
        tokens = await get_spl_tokens_in_wallet(wallet_address=WALLET_ADDRESS)
        if len(tokens) == 0:
            trade_logger.info(f"No startup tokens to sell")
        
        else:
            # Otherwise loop throughs tokens and perform sell swap
            trade_logger.info(f"Confirming startup tokens to be sold")
            for token in tokens:
                mint = token.get("mint", "")
                trade_logger.info(f"Executing start-up sell for {mint}")
                            
                # Get the pool address directly from Raydium. Use Jupiter quote as a fallback
                pool_address = await get_pool_info_by_mint(mint)
                if not pool_address:
                    quote = await get_jupiter_quote(httpx_client, mint, )
                    
                    # Extract the raydium pool address from the quote
                    for route in quote.get("routePlan", []):
                        swap_info = route.get("swapInfo", {})
                        if swap_info.get("label") == "Raydium":
                            amm_key = swap_info.get("ammKey")
                            if amm_key:
                                pool_address = amm_key
                            else:
                                continue
                
                
                await execute_sell(httpx_client, pool_address)
                await asyncio.sleep(5)

        return None
    
    except Exception as e:
        trade_logger.error(f"Error with startup_sell function - {e}")
        return None
            
        
# Get a list of the tokens that are currently in the wallet
async def get_spl_tokens_in_wallet(wallet_address: str) -> list[dict]:
    """
    Fetch all SPL (non-SOL) tokens in a given wallet that have a balance > 0.

    Args:
        wallet_address (str): Base58 string of the wallet public key.
        rpc_url (str): Your QuickNode (or other) Solana RPC endpoint.

    Returns:
        list[dict]: A list of SPL tokens, each entry including:
                    {
                        "mint": <mint address>,
                        "decimals": <decimals>,
                        "ui_amount": <parsed float balance>,
                        "amount": <raw integer amount>,
                    }
    """
    wallet_pubkey = Pubkey.from_string(wallet_address)

    # Get all token accounts by owner - specify the SPL Token Program to avoid any SOL accounts
    resp = await client.get_token_accounts_by_owner_json_parsed(owner=wallet_pubkey, opts=TokenAccountOpts(program_id=TOKEN_PROGRAM_ID), commitment=Finalized)
    resp = resp.value

    # Fallback if None is returned
    if resp is None:
        return []

    tokens = []
    for keyed_account in resp:
        parsed_data = keyed_account.account.data.parsed
        
        info = parsed_data["info"]
        token_amount = info["tokenAmount"]
        
        ui_amount = float(token_amount["uiAmount"])
        if ui_amount > 0:
            tokens.append({
                "mint": info["mint"],
                "decimals": token_amount["decimals"],
                "ui_amount": ui_amount,            
                "amount": token_amount["amount"],  
            })
    
    return tokens


httpx_client = httpx.AsyncClient()
if __name__ == "__main__":
    asyncio.run(startup_sell(httpx_client))