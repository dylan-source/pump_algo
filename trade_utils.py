

import statistics
import aiohttp
import requests
import base64
from pprint import pprint
import time
import json
import datetime
import numpy as np
import httpx
from httpx._config import Timeout
import asyncio
from solana.rpc.async_api import AsyncClient
from solders.transaction import VersionedTransaction # type: ignore
from solders.signature import Signature # type: ignore
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Processed, Confirmed, Finalized
from solana.rpc.types import TokenAccountOpts
from spl.token.constants import TOKEN_PROGRAM_ID
from solders.keypair import Keypair # type: ignore
from solders.pubkey import Pubkey # type: ignore
from solders.hash import Hash       # type: ignore
from solders.message import MessageV0       # type: ignore
from config import (RPC_URL, PRIVATE_KEY, JUPITER_QUOTE_URL, JUPITER_SWAP_URL, JUPITER_PRICE_URL,
                    WALLET_ADDRESS, COLD_WALLET_ADDRESS, TIME_TO_SLEEP, PRIORITY_FEE_MULTIPLIER, METIS_RPC_URL, MAX_TRADE_TIME_MINS,
                    PRIORITY_FEE_NUM_BLOCKS, PRIORITY_FEE_MIN, PRIORITY_FEE_MAX, SOL_AMOUNT_LAMPORTS, SOL_DECIMALS, SOL_MINT, 
                    trade_logger, MIN_SOL_BALANCE, SOL_MIN_BALANCE_LAMPORTS, SELL_LOOP_DELAY, MONITOR_PRICE_DELAY, STOPLOSS, PRICE_LOOP_RETRIES,
                    BUY_SLIPPAGE, SELL_SLIPPAGE, START_UP_SLEEP, SELL_SLIPPAGE_DELAY, PRIORITY_FEE_STOPLOSS_MULTIPLIER)
# from metadata_utils import fetch_token_metadata
from storage_utils import store_trade_data, fetch_trade_data, write_trades_to_csv
import redis.asyncio as redis


# rpc_client = AsyncClient(RPC_URL)
# httpx_client = httpx.AsyncClient(timeout=30)
# redis_client_trades = redis.Redis(host='localhost', port=6379, db=1)
quote_url = METIS_RPC_URL + "/quote"
swap_url = METIS_RPC_URL + "/swap"

MAX_TRADE_TIME_MINS = 1  # for testing purposes
MAX_TRADE_TIME_SECONDS = MAX_TRADE_TIME_MINS * 60


# Helper to parse error responses from simulation/confirmation.
def parse_simulation_error(error_obj):
    if isinstance(error_obj, dict) and "InstructionError" in error_obj:
        instruction_error = error_obj["InstructionError"]
        if isinstance(instruction_error, list) and len(instruction_error) > 1:
            if isinstance(instruction_error[1], dict):
                return instruction_error[1].get("Custom")
            elif isinstance(instruction_error[1], str):
                return instruction_error[1]
    return None


# Get the transaction details - amount of tokens in/out of the wallet
async def get_transaction_details(rpc_client, signature, wallet_address: str, input_mint: str, output_mint: str):

    # Help function to parse the response
    def find_token_balance_from_tx_hash(token_balances, mint, owner):
        for t in token_balances:
            if t['mint'] == mint and t.get('owner') == owner:
                return float(t['uiTokenAmount']['uiAmountString'])
        else:
            return 0.0
    
    # Make the API call and convert it to JSON format
    status = await rpc_client.get_transaction(signature, 'json', commitment=Confirmed, max_supported_transaction_version=0)
    transaction_json = status.to_json()
    data = json.loads(transaction_json)

    # Log the error if no response is found
    if data['result'] is None:
        trade_logger.error(f'Error fetching transaction details for Signature: {signature} - inputMint: {input_mint} and outputMint: {output_mint}')
        return
    
    # Extract the relevant data points
    timestamp = data['result']['blockTime']
    meta = data['result']['meta']
    pre_balances = meta['preBalances']
    post_balances = meta['postBalances']
    pre_token_balances = meta.get('preTokenBalances', [])
    post_token_balances = meta.get('postTokenBalances', [])

    # Extract the relevant details based on whether SOL is the input/output token
    if output_mint == SOL_MINT:
        sol_diff = post_balances[0] - pre_balances[0]
        token_out_diff = sol_diff / 10 ** SOL_DECIMALS
        pre_amount = find_token_balance_from_tx_hash(pre_token_balances, input_mint, wallet_address)
        post_amount = find_token_balance_from_tx_hash(post_token_balances, input_mint, wallet_address)
        token_in_diff = post_amount - pre_amount
    elif input_mint == SOL_MINT:
        sol_diff = post_balances[0] - pre_balances[0]
        token_in_diff = sol_diff / 10 ** SOL_DECIMALS
        pre_amount = find_token_balance_from_tx_hash(pre_token_balances, output_mint, wallet_address)
        post_amount = find_token_balance_from_tx_hash(post_token_balances, output_mint, wallet_address)
        token_out_diff = post_amount - pre_amount

    # Convert the block time to a datetime object
    dt_object = datetime.datetime.fromtimestamp(timestamp)
    formatted_datetime = dt_object.strftime('%Y-%m-%d %H:%M:%S')

    return {'timestamp': formatted_datetime, 'inputMint_diff': token_in_diff, 'outputMint_diff': token_out_diff}


# Get the amount of SPL tokens in a particular wallet - returns the lamports amount
async def get_token_balance(rpc_client: AsyncClient, wallet_address: str, token_mint_address: str) -> int:
    """
    Get the balance of a specific token in a wallet on the Solana blockchain.

    Args:
        wallet_address (str): The wallet address (public key) as a string.
        token_mint_address (str): The token mint address as a string.

    Returns:
        float: The balance of the token in the wallet.
    """
    
    # Get the number of tokens for the inputted wallet and token address
    wallet_pubkey = Pubkey.from_string(wallet_address)
    token_mint_pubkey = Pubkey.from_string(token_mint_address)
    token_accounts = await rpc_client.get_token_accounts_by_owner_json_parsed(wallet_pubkey, TokenAccountOpts(mint=token_mint_pubkey))
   
    # Return zero if no tokens are found
    if not token_accounts.value:
        return 0.0
    
    # Parse the response - then log and return it
    token_account_info = token_accounts.value[0].account.data.parsed['info']
    token_balance = token_account_info['tokenAmount']['amount']
    trade_logger.info(f'Token balance for {token_mint_address}: {token_balance}0')
    
    return token_balance


# Get a list of the tokens that are currently in the wallet
async def get_spl_tokens_in_wallet(async_client:AsyncClient,  wallet_address: str) -> list[dict]:
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

    # Get all token accounts by owner
    # We specify the SPL Token Program to avoid any SOL accounts
    resp = await async_client.get_token_accounts_by_owner_json_parsed(owner=wallet_pubkey, opts=TokenAccountOpts(program_id=TOKEN_PROGRAM_ID), commitment=Finalized)
    resp = resp.value

    # Fallback if RPC doesn't return what's expected
    if resp is None:
        await async_client.close()
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

    # Close RPC connection
    # await async_client.close()
    return tokens


# Get recent priority fees
async def get_recent_prioritization_fees(httpx_client: httpx.AsyncClient, url:str=RPC_URL, input_mint: str="So11111111111111111111111111111111111111112", 
                                         multiplier: float=PRIORITY_FEE_MULTIPLIER, num_blocks: int=PRIORITY_FEE_NUM_BLOCKS, 
                                         max_fee: int=PRIORITY_FEE_MAX, min_fee: int=PRIORITY_FEE_MIN):
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getRecentPrioritizationFees",
        "params": [[input_mint]]
    }

    try:
        response = await httpx_client.post(RPC_URL, headers={'Accept':'application/json'}, json=body)
        json_response = response.json()

        if json_response and "result" in json_response:
            fees = [fee["prioritizationFee"] for fee in json_response["result"]]
            fees = fees[-num_blocks:]
            median = int(statistics.median(fees))
            recommended_fee = int(median * multiplier)

            priority_fees = {
                "recommended": recommended_fee,
                "mean": int(statistics.mean(fees)),
                "median": median,
                "percentile_65": int(np.percentile(fees, 65)),
                "percentile_75": int(np.percentile(fees, 75)),
                "percentile_85": int(np.percentile(fees, 85))
            }

            # If the recommended fee is too high or too low then recommended fee is the max/min allowed
            if recommended_fee >= max_fee:
                priority_fees["recommended"] = max_fee
            elif recommended_fee < min_fee:
                priority_fees["recommended"] = min_fee

            # Log the final priority fees dictionary
            trade_logger.info(f"Priority fees: {priority_fees}")
            return priority_fees
              
    except Exception as e:
        trade_logger.error(f"Error getting priority fees - {e}")
        return None


# Confirm if the transaction was successful
async def confirm_tx(rpc_client, signature, commitment=Finalized):
   
    # If swapTransaction fails the execute_swap function returns None
    if signature is None:
        return None
    
    # If no issues, confirm the transaction
    # Convert signature to a string for logging
    signature_string = str(signature)

    try:
        confirmation = await rpc_client.confirm_transaction(signature, commitment=commitment)

        if confirmation.value and len(confirmation.value) > 0:
            transaction_status = confirmation.value[0]  
            transaction_status = transaction_status.to_json()
            transaction_status = json.loads(transaction_status)
        
            # Unpack and log the results
            status = next(iter(transaction_status["status"].keys()), None)
            error = transaction_status["err"]
            confirmationStatus = transaction_status["confirmationStatus"]

            trade_logger.info(f"Trade confirmation for {signature_string} - Status: {status} - Error: {error} - ConfirmationStatus: {confirmationStatus}")

            return {
                "Status": status,
                "Error": error,
                "confirmationStatus": confirmationStatus
            }
        else:
            trade_logger.error(f"No transaction status in confirmation response: {signature_string}")
            return None
    except Exception as e:
        trade_logger.error(f"Trade confirmation error: {e}")
        return None


# Replace the jupiter blockhash with a fresh one
def clone_v0_message_with_new_blockhash(old_msg: MessageV0, new_blockhash_str: str) -> MessageV0:
    # Convert the string blockhash into a solders Hash
    new_hash = Hash.from_string(new_blockhash_str)

    # Create a new MessageV0, reusing the old fields
    # except for recent_blockhash, which we overwrite
    new_msg = MessageV0(
        header=old_msg.header,
        account_keys=old_msg.account_keys,
        recent_blockhash=new_hash,
        instructions=old_msg.instructions,
        address_table_lookups=old_msg.address_table_lookups  # might be None or a value
    )
    return new_msg


# Simulate the transaction
async def simulate_versioned_transaction(httpx_client, rpc_url, signed_txn):
    """Calls `simulateTransaction` directly via HTTP to your QuickNode (or other) RPC."""
    raw_b64_tx = base64.b64encode(bytes(signed_txn)).decode("utf-8")
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "simulateTransaction",
        "params": [
            raw_b64_tx,
            {
                "commitment": "processed",
                "encoding": "base64",
                "sigVerify": True
            }
        ],
    }

    # async with httpx.AsyncClient() as client:
    resp = await httpx_client.post(rpc_url, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()


# Is the block still valid
async def check_valid_block(httpx_client, RPC_URL, blockhash):
        
        # RPC request to get block information for a blockhash
        headers = {"Content-Type": "application/json"}
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "isBlockhashValid",
            "params": [str(blockhash), {"commitment": "processed"}]
        }
        response = await httpx_client.post(RPC_URL, json=payload, headers=headers)
        response_data = response.json()
        return response_data["result"]["value"]


# Get a quote
async def get_jupiter_quote(httpx_client:httpx.AsyncClient, input_address:str, output_address:str, amount:int, slippage:str, is_buy:bool):
    """
    Fetch a quote from Jupiter v6 asynchronously.
    'amount' is in lamport
    'slippage_bps' in basis points
    """
    params = {
        "inputMint": input_address,
        "outputMint": output_address,
        "amount": amount,
        "slippageBps": slippage,
        # "restrictIntermediateTokens": True,
        "swapMode": "ExactIn"
    }

    # quote_response = await httpx_client.get(JUPITER_QUOTE_URL, headers={'Accept':'application/json'}, params=params)
    quote_response = await httpx_client.get(quote_url, headers={'Accept':'application/json'}, params=params)
    quote_response = quote_response.json()

    # Define risky address for logging purposes
    if is_buy: 
        risk_address = output_address
    else:
        risk_address = input_address

    # Log and return the result for the best route
    if not quote_response or quote_response.get("error"):
        trade_logger.error(f"No routes found for: {risk_address}")
        trade_logger.error(f"Quote response: {quote_response}")
        return None
    else:
        trade_logger.info(f"Routes found for address: {risk_address}")
        return quote_response


# Execute a swap based upon quote
async def execute_swap(rpc_client:AsyncClient, httpx_client:httpx.AsyncClient, quote, priority_fee:int):

    payload = {
        "quoteResponse": quote,
        "userPublicKey": WALLET_ADDRESS,
        "wrapUnwrapSOL": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": priority_fee  
    }

    try:
        # Post a call to the Jupiter swap API
        # swap_response = await httpx_client.post(JUPITER_SWAP_URL, headers={'Accept': 'application/json'}, json=payload)
        swap_response = await httpx_client.post(swap_url, headers={'Accept': 'application/json'}, json=payload)
        swap_data = swap_response.json()
        swap_transaction = swap_data.get('swapTransaction')  

        # swapTransaction contains the serialized instructions to execute the swap. Return none, if no instructions were found
        if not swap_transaction:
            trade_logger.error("No swapTransaction found in the response.")
            await asyncio.sleep(5)
            return None
        
        # If swapTransaction is found, decode the swap instructions and sign the transaction
        else:
            # Decode and sign the transaction
            raw_transaction = VersionedTransaction.from_bytes(base64.b64decode(swap_transaction))
            old_msg = raw_transaction.message

            # Get a fresh blockhash 
            fresh_blockhash_resp = await rpc_client.get_latest_blockhash()
            fresh_blockhash = str(fresh_blockhash_resp.value.blockhash)
            
            # Replace Jupiter blockhash with the fresho one - prevents forked/ephemeral blockhash issues
            new_msg = clone_v0_message_with_new_blockhash(old_msg, fresh_blockhash)
            signed_tx = VersionedTransaction(new_msg, [PRIVATE_KEY])

            # Simulate the transaction
            simulate_resp = await simulate_versioned_transaction(httpx_client=httpx_client, rpc_url=RPC_URL, signed_txn=signed_tx)
            err = simulate_resp.get("result", {}).get("value", {}).get("err")
            if err is not None:
                trade_logger.error(f"Simulation failed: {err}")
                # trade_logger.error(f"Simulation failed: {simulate_resp}")
                return {"Error": err}
            trade_logger.info("No simulation error")

            # If simulation is successful, send the signed transaction
            opts = TxOpts(skip_confirmation=True, skip_preflight=True, preflight_commitment=Processed, max_retries=2)
            transaction_id = await rpc_client.send_transaction(signed_tx, opts=opts)
            return transaction_id.value  # Returns a Signature object

    except Exception as e:
        trade_logger.error(f"Error executing swap transaction: {e}")
        return None
    

# Fetch the price from DexScreener using pair address
async def fetch_dexscreener_price_with_pair_id(httpx_client:httpx.AsyncClient, pair_id:str, chain_id:str="solana"):
    """
    Fetch pair data from DexScreener using the token_address.
    """

    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain_id}/{pair_id}"
    try:
        response = await httpx_client.get(url)
        response.raise_for_status()  # Raises an error for 4xx/5xx responses.
        data = response.json()

        # First, try to find priceNative in the "pair" object.
        if "pair" in data and "priceNative" in data["pair"]:
            price_native_str = data["pair"]["priceNative"]
            
        # Otherwise, fall back to the first element in the "pairs" list.
        elif "pairs" in data and len(data["pairs"]) > 0 and "priceNative" in data["pairs"][0]:
            price_native_str = data["pairs"][0]["priceNative"]
        else:
            trade_logger.error("Could not find 'priceNative' in the response data.")
            return None
        
        return float(price_native_str)
    
    except httpx.HTTPStatusError as e:
        trade_logger.error(f"HTTP error while fetching DexScreener pair data: {e} - Response: {e.response.text}")
    except Exception as e:
        trade_logger.error(f"Unexpected error fetching DexScreener pair data: {e}")
    
    return None


# Fetch token price from Jupiter
async def get_price(client:httpx.AsyncClient, address, timeout=10):

    # Cannot use vsToken and showExtraInfo. vsToken provides the derived (or market average) price
    # All prices are in USDC (unless if vsToken is used)

    payload = {
        "ids":address,
        # "vsToken": SOL_MINT,
        "showExtraInfo": False
    }

    loop_count = 0
    while True:
        response = await client.get(url=JUPITER_PRICE_URL, params=payload, timeout=Timeout(timeout=timeout))
        response = response.json()

        # Sometimes no prices are available yet
        if response is None or response["data"][address] is None:
            return None
        
        derived_price = response["data"][address]["price"]
            
        # Error handling
        if derived_price is None:
            trade_logger.error(f"No price received for {address}")

            loop_count += 1
            if loop_count > PRICE_LOOP_RETRIES:
                return None
            else:
                await asyncio.sleep(MONITOR_PRICE_DELAY)
                continue
        else:
            return float(derived_price)
        

# Fetch the price from DexScreener using token address
async def get_price_dexscreener(httpx_client:httpx.AsyncClient, token_address:str, chain_id:str="solana") -> float:
    """
    Fetch the priceNative value from the DexScreener token-pairs API for the given chain and token.
    Returns: float: The priceNative (price relative to SOL) value as a float, or None if an error occurs.
    """
    url = f"https://api.dexscreener.com/token-pairs/v1/{chain_id}/{token_address}"
    try:
        response = await httpx_client.get(url)
        response.raise_for_status()  # Raises an error for 4xx/5xx responses.
        data = response.json()

        # Check that the data is a non-empty list.
        if isinstance(data, list) and len(data) > 0:
            first_pair = data[0]
            if "priceNative" in first_pair:
                price_native_str = first_pair["priceNative"]
                # user_price = first_pair["priceUsd"]
                return float(price_native_str)*10**5
            else:
                trade_logger.error("Could not find 'priceNative' in the first pair object.")
                return None
        else:
            trade_logger.error("Response JSON is not a non-empty list.")
            return None

    except httpx.HTTPStatusError as e:
        trade_logger.error(f"HTTP error while fetching priceNative: {e} - Response: {e.response.text}")
    except Exception as e:
        trade_logger.error(f"Unexpected error fetching priceNative: {e}")
    
    return None


# Failsafe execute sell - to clear wallet of SPL tokens
async def startup_sell(rpc_client:AsyncClient, redis_client_trades:redis.Redis, sell_slippage:dict=SELL_SLIPPAGE):
    
    httpx_client = httpx.AsyncClient(timeout=30)
    try:
        tokens = await get_spl_tokens_in_wallet(async_client=rpc_client,  wallet_address=WALLET_ADDRESS)

        # If there are no tokens return None
        if len(tokens) == 0:
            trade_logger.info(f"No startup tokens to sell")
        
        else:
            # Otherwise loop throughs tokens and perform sell swap
            trade_logger.info(f"Confirming startup tokens to be sold")
            for token in tokens:
                mint = token.get("mint", "")
                trade_logger.info(f"Executing start-up sell for {mint}")
                await execute_sell(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=mint, sell_slippage=sell_slippage, is_stoploss= False)
                await asyncio.sleep(5)
        
        await httpx_client.aclose()
        return None
    
    except Exception as e:
        trade_logger.error(f"Error with startup_sell function - {e}")
        await httpx_client.aclose()
        return None
           


async def execute_sell(rpc_client:AsyncClient, httpx_client:httpx.AsyncClient, redis_client_trades:redis.Redis, risky_address:str, 
                       sell_slippage:dict=SELL_SLIPPAGE, is_stoploss:bool=False):
    """
    Execute a sell trade for the token at risky_address.

    This function:
      1. Checks that the token balance > 0.
      2. Retrieves the latest priority fee data.
      3. Executes a Jupiter swap simulation and, if successful, sends the transaction.
      4. Uses a retry loop to adjust the slippage (and, if needed, the priority fee) 
         in case of simulation or confirmation errors.

    When is_stoploss is False (the default):
      - The function uses the standard sell slippage (SELL_SLIPPAGE["MIN"]) and
        rotates through priority fee levels as usual.
    
    When is_stoploss is True:
      - The initial slippage is set to SELL_SLIPPAGE["STOPLOSS_MIN"] instead of SELL_SLIPPAGE["MIN"].
      - The priority fee is multiplied by PRIORITY_FEE_STOPLOSS_MULTIPLIER
        (to increase the chance of rapid execution).
      - The same error-handling logic applies (i.e. increasing slippage if a 6001 error is detected, or
        rotating to a higher fee if "ProgramFailedToComplete" is returned).
    """

    # 1. Confirm that the wallet holds the risky token
    risky_amount = await get_token_balance(rpc_client=rpc_client, wallet_address=WALLET_ADDRESS, token_mint_address=risky_address)
    if risky_amount == 0:
        trade_logger.error(f"No tokens found for {risky_address}")
        return None


    # 2. Get the latest priority fee data; retry if necessary
    while True:
        priority_fee_dict = await get_recent_prioritization_fees(httpx_client, RPC_URL)
        if priority_fee_dict is None:
            trade_logger.error("Sell function - priority fees not found - retrying")
            await asyncio.sleep(SELL_LOOP_DELAY)
        else:
            break

    # Use a list of fee levels in order of preference. Multiply the fee for stoploss trades.
    fee_index = 0
    fee_keys = ["recommended", "percentile_65", "percentile_75"] 
    current_priority_fee = priority_fee_dict[fee_keys[fee_index]]
    if is_stoploss:
        current_priority_fee = int(current_priority_fee * PRIORITY_FEE_STOPLOSS_MULTIPLIER)


    # 3. Set the starting slippage.
    if is_stoploss:
        current_slippage = sell_slippage["STOPLOSS_MIN"]
    else:
        current_slippage = sell_slippage["MIN"]


    # 4. Main loop for executing the sell trade.
    while True:
        trade_logger.info(f"Attempting sell trade with slippage: {current_slippage}bps and priority fee: {current_priority_fee}.")
        
        # Get a quote from Jupiter and execute a swap
        sell_quote = await get_jupiter_quote(httpx_client, input_address=risky_address, output_address=SOL_MINT, amount=risky_amount, slippage=current_slippage, is_buy=False)
        sell_swap_response = await execute_swap(rpc_client=rpc_client, httpx_client=httpx_client, quote=sell_quote, priority_fee=current_priority_fee)
    

        # --- CASE 1: SIMULATION FAILURE ---
        # Check if swap_result is None - happens when no routes are found or swapTransaction is None
        if sell_swap_response is None:
            if fee_index < len(fee_keys) - 1:
                fee_index += 1
                fees = await get_recent_prioritization_fees(httpx_client, RPC_URL)
                current_priority_fee = fees[fee_keys[fee_index]]
                if is_stoploss:
                    current_priority_fee = int(current_priority_fee * PRIORITY_FEE_STOPLOSS_MULTIPLIER)
                trade_logger.info(f"SellSwapResult returned None. Increasing priority fee to {current_priority_fee} using '{fee_keys[fee_index]}' and retrying.")
                continue
        
        # If the simulation fails, execute_swap returns a dict with an "Error" key.
        elif isinstance(sell_swap_response, dict) and "Error" in sell_swap_response:
            error_code = parse_simulation_error(sell_swap_response["Error"])
            
            # 6001 → insufficient slippage error.
            if error_code == 6001: 
                if current_slippage < sell_slippage["MAX"]:
                    current_slippage += sell_slippage["INCREMENTS"]
                    trade_logger.info(f"Sell error: insufficient slippage. Increasing slippage to {current_slippage}bps and retrying.")
                    continue
                else:
                    trade_logger.error(f"Maximum sell slippage reached ({current_slippage}bps). Aborting trade.")
                    return False
            
            # This error is often due to insufficient priority fees.
            elif error_code == "ProgramFailedToComplete":
                if fee_index < len(fee_keys) - 1:
                    fee_index += 1
                    priority_fee_dict = await get_recent_prioritization_fees(httpx_client, RPC_URL)
                    current_priority_fee = priority_fee_dict[fee_keys[fee_index]]
                    if is_stoploss:
                        current_priority_fee = int(current_priority_fee * PRIORITY_FEE_STOPLOSS_MULTIPLIER)
                    trade_logger.info(f"Sell error: ProgramFailedToComplete detected. Increasing priority fee to {current_priority_fee} using '{fee_keys[fee_index]}' and retrying.")
                    continue
                else:
                    trade_logger.error("All priority fee levels exhausted during sell simulation error. Aborting trade.")
                    return False
            
            # For any other simulation error, try increasing slippage.                
            else:
                if current_slippage < sell_slippage["MAX"]:
                    current_slippage += sell_slippage["INCREMENTS"]
                    trade_logger.info(f"Sell error with code {error_code}. Increasing slippage to {current_slippage}bps and retrying.")
                    continue
                else:
                    trade_logger.error(f"Trade aborted due to sell simulation error code {error_code}.")
                    return False

        # Otherwise, if we did not get an error we assume sell_swap_response is a valid signature.
        signature = sell_swap_response

        # --- CASE 2: CONFIRMATION HANDLING ---
        sell_confirm_result = await confirm_tx(rpc_client=rpc_client, signature=signature, commitment="finalized")

        # If no confirmation is returned, assume the transaction never propagated (likely due to insufficient priority fees).
        if sell_confirm_result is None:
            if fee_index < len(fee_keys) - 1:
                fee_index += 1
                priority_fee_dict = await get_recent_prioritization_fees(httpx_client, RPC_URL)
                current_priority_fee = priority_fee_dict[fee_keys[fee_index]]
                if is_stoploss:
                    current_priority_fee = int(current_priority_fee * PRIORITY_FEE_STOPLOSS_MULTIPLIER)
                trade_logger.info(f"Sell confirmation returned None. Increasing priority fee to {current_priority_fee} using '{fee_keys[fee_index]}' and retrying.")
                continue
            else:
                trade_logger.error("All priority fee levels exhausted during sell confirmation. Aborting trade.")
                return False

        # If confirmation returned an error, inspect it.
        if sell_confirm_result.get("Status") != "Ok":
            error_obj = sell_confirm_result.get("Error")
            error_code = parse_simulation_error(error_obj) if error_obj else None

            if error_code == 6001:
                if current_slippage < sell_slippage["MAX"]:
                    current_slippage += sell_slippage["INCREMENTS"]
                    trade_logger.error(f"Sell confirmation error: insufficient slippage (error code {error_code}). Increasing slippage to {current_slippage}bps and retrying.")
                    continue
                else:
                    trade_logger.error(f"Maximum sell slippage reached during confirmation ({current_slippage}bps). Aborting trade.")
                    return False
            elif error_code == "ProgramFailedToComplete":
                if fee_index < len(fee_keys) - 1:
                    fee_index += 1
                    priority_fee_dict = await get_recent_prioritization_fees(httpx_client, RPC_URL)
                    current_priority_fee = priority_fee_dict[fee_keys[fee_index]]
                    if is_stoploss:
                        current_priority_fee = int(current_priority_fee * PRIORITY_FEE_STOPLOSS_MULTIPLIER)
                    trade_logger.error(f"Sell confirmation error: ProgramFailedToComplete detected. Increasing priority fee to {current_priority_fee} using '{fee_keys[fee_index]}' and retrying.")
                    continue
                else:
                    trade_logger.error("All priority fee levels exhausted during sell confirmation error. Aborting trade.")
                    return False
            else:
                # For any other error assume insufficient priority fee.
                if fee_index < len(fee_keys) - 1:
                    fee_index += 1
                    priority_fee_dict = await get_recent_prioritization_fees(httpx_client, RPC_URL)
                    current_priority_fee = priority_fee_dict[fee_keys[fee_index]]
                    if is_stoploss:
                        current_priority_fee = int(current_priority_fee * PRIORITY_FEE_STOPLOSS_MULTIPLIER)
                    trade_logger.error(f"Sell confirmation error with code {error_code}. Increasing priority fee to {current_priority_fee} using '{fee_keys[fee_index]}' and retrying.")
                    continue
                else:
                    trade_logger.error("All priority fee levels exhausted during sell confirmation error. Aborting trade.")
                    return False

        # --- SUCCESS: Transaction Confirmed ---
        trade_logger.info(f"Sell transaction sent: https://solscan.io/tx/{signature}")
        sell_tx_result = await get_transaction_details(rpc_client=rpc_client, signature=signature, wallet_address=WALLET_ADDRESS, input_mint=risky_address, output_mint=SOL_MINT)

        # Retrieve buy trade data from Redis and write both buy & sell data to CSV.
        buy_trade_data = await fetch_trade_data(redis_client_trades=redis_client_trades, token_address=risky_address)
        sell_trade_data = {
            "sell_timestamp": sell_tx_result["timestamp"],
            "sell_transaction_hash": str(signature),
            "sell_tokens_spent": sell_tx_result["inputMint_diff"],
            "sell_tokens_received": sell_tx_result["outputMint_diff"]
        }
        await write_trades_to_csv(tx_address=risky_address, buy_data_dict=buy_trade_data, sell_data_dict=sell_trade_data, redis_client=redis_client_trades)
        return True





# Function to execute a buy
async def execute_buy(rpc_client:AsyncClient, httpx_client:httpx.AsyncClient, redis_client_trades:redis.Redis, risky_address:str, 
                        sol_address:str=SOL_MINT, trade_amount:int=SOL_AMOUNT_LAMPORTS, buy_slippage:dict=BUY_SLIPPAGE):
    
    
    # 1. Check SOL balance.
    balance_resp = await rpc_client.get_balance(Pubkey.from_string(WALLET_ADDRESS))
    sol_value = balance_resp.value
    if sol_value <= SOL_MIN_BALANCE_LAMPORTS:
        trade_logger.error(f"SOL balance below threshold - Wallet: {sol_value}, Threshold: {SOL_MIN_BALANCE_LAMPORTS}")
        return False
    else:
        trade_logger.info(f"Sufficient SOL for trade - Wallet: {sol_value}, Trade amount: {SOL_AMOUNT_LAMPORTS}")

    # 2. Get initial priority fees and choose the starting fee level.
    fees = await get_recent_prioritization_fees(httpx_client, RPC_URL)
    if fees is None:
        return False
    
    # Define the order in which we want to try fees.
    fee_index = 0
    fee_keys = ["recommended", "percentile_65", "percentile_75"]
    current_priority_fee = fees[fee_keys[fee_index]]

    # 3. Set starting slippage.
    current_slippage = buy_slippage["MIN"]

    # 4. Main loop: try simulation and confirmation until success or until limits are reached.
    while True:
        
        # Log the current settings, get a quote from Jupiter & execute (simulate & send) the swap.
        trade_logger.info(f"Attempting buy trade with slippage: {current_slippage}bps and priority fee: {current_priority_fee}.")
        quote = await get_jupiter_quote(httpx_client,input_address=sol_address, output_address=risky_address, amount=trade_amount, slippage=current_slippage, is_buy=True)
        swap_result = await execute_swap(rpc_client=rpc_client, httpx_client=httpx_client, quote=quote, priority_fee=current_priority_fee)

        # --- CASE 1: Simulation failure ---
        # Check if swap_result is None - happens when no routes are found or swapTransaction is None
        if swap_result is None:
            if fee_index < len(fee_keys) - 1:
                fee_index += 1
                fees = await get_recent_prioritization_fees(httpx_client, RPC_URL)
                current_priority_fee = fees[fee_keys[fee_index]]
                trade_logger.info(f"SwapResult returned None. Increasing priority fee to {current_priority_fee} using '{fee_keys[fee_index]}' and retrying.")
                continue
        
        # Check if swap_result is a dict with an "Error" key.
        elif isinstance(swap_result, dict) and "Error" in swap_result:
            error_code = parse_simulation_error(swap_result["Error"])

            # If simulation fails due to insufficient slippage - increase and retry
            if error_code == 6001:
                if current_slippage < buy_slippage["MAX"]:
                    current_slippage += buy_slippage["INCREMENTS"]
                    trade_logger.info(f"Buy error. Insufficient slippage. Increasing slippage to {current_slippage}bps and retrying.")
                    continue
                else:
                    trade_logger.error(f"Maximum slippage reached. Aborting trade for {risky_address}.")
                    return False
            
            # Likely due to insufficient priority fees: increase fee level.
            elif error_code == "ProgramFailedToComplete":
                if fee_index < len(fee_keys) - 1:
                    fee_index += 1
                    fees = await get_recent_prioritization_fees(httpx_client, RPC_URL)
                    current_priority_fee = fees[fee_keys[fee_index]]
                    trade_logger.info(f"Buy error. ProgramFailedToComplete detected. Increasing priority fee to {current_priority_fee} using '{fee_keys[fee_index]}' and retrying.")
                    continue
                else:
                    trade_logger.error("All priority fee levels exhausted during simulation error. Aborting trade.")
                    return False
            
            # For any other simulation error, attempt to increase slippage if possible.
            else:
                if current_slippage < buy_slippage["MAX"]:
                    current_slippage += buy_slippage["INCREMENTS"]
                    trade_logger.info(f"Buy error with code {error_code}. Increasing slippage to {current_slippage}bps and retrying.")
                    continue
                else:
                    trade_logger.error(f"Trade aborted due to simulation error code {error_code}.")
                    return False

        # If swap_result is not a simulation error dictionary, assume it is a valid signature.
        signature = swap_result

        # --- CONFIRMATION HANDLING ---
        confirm_result = await confirm_tx(rpc_client=rpc_client, signature=signature, commitment="finalized")

        # If confirm_tx returns None, assume it did not confirm due to insufficient priority fee.
        if confirm_result is None:
            if fee_index < len(fee_keys) - 1:
                fee_index += 1
                fees = await get_recent_prioritization_fees(httpx_client, RPC_URL)
                current_priority_fee = fees[fee_keys[fee_index]]
                trade_logger.error(f"Confirm_tx returned None. Increasing priority fee to {current_priority_fee} using '{fee_keys[fee_index]}' and retrying.")
                continue
            else:
                trade_logger.error("All priority fee levels exhausted during confirmation. Aborting trade.")
                return False

        # If a confirmation error is returned, inspect it.
        if confirm_result.get("Status") != "Ok":
            error_obj = confirm_result.get("Error")
            error_code = parse_simulation_error(error_obj) if error_obj else None
            # trade_logger.error(f"CONFIRM_RESULT ERROR: {error_code}")
            
            if error_code == 6001:
                if current_slippage < buy_slippage["MAX"]:
                    current_slippage += buy_slippage["INCREMENTS"]
                    trade_logger.error(f"Buy confirmation error: insufficient slippage (error code {error_code}). Increasing slippage to {current_slippage}bps and retrying.")
                    continue
                else:
                    trade_logger.error(f"Maximum slippage reached during confirmation ({current_slippage}bps). Aborting trade.")
                    return False
            elif error_code == "ProgramFailedToComplete":
                if fee_index < len(fee_keys) - 1:
                    fee_index += 1
                    fees = await get_recent_prioritization_fees(httpx_client, RPC_URL)
                    current_priority_fee = fees[fee_keys[fee_index]]
                    trade_logger.error(f"Buy confirmation error: ProgramFailedToComplete detected. Increasing priority fee to {current_priority_fee} using '{fee_keys[fee_index]}' and retrying.")
                    continue
                else:
                    trade_logger.error("All priority fee levels exhausted during confirmation error. Aborting trade.")
                    return False
                
            # For any other confirmation error, assume it may be a fee issue.
            else:
                if fee_index < len(fee_keys) - 1:
                    fee_index += 1
                    fees = await get_recent_prioritization_fees(httpx_client, RPC_URL)
                    current_priority_fee = fees[fee_keys[fee_index]]
                    trade_logger.error(f"Buy confirmation error with code {error_code}. Increasing priority fee to {current_priority_fee} using '{fee_keys[fee_index]}' and retrying.")
                    continue
                else:
                    trade_logger.error("All priority fee levels exhausted during confirmation error. Aborting trade.")
                    return False

            
        # --- SUCCESS: Transaction confirmed ---
        trade_logger.info(f"Transaction sent: https://solscan.io/tx/{signature}")
        tx_result = await get_transaction_details(rpc_client=rpc_client, signature=signature, wallet_address=WALLET_ADDRESS, input_mint=sol_address, output_mint=risky_address)
        trades_cache_result = await store_trade_data(
            redis_client_trades=redis_client_trades,
            signature=signature,
            timestamp=tx_result["timestamp"],
            token_address=risky_address,
            tokens_spent=tx_result["inputMint_diff"],
            tokens_received=tx_result["outputMint_diff"]
        )
        trade_logger.info(f"Cached buy results for {risky_address}: {trades_cache_result}")
        return True


# Wrapper to house full trade logic
# async def trade_wrapper(rpc_client:AsyncClient, httpx_client:httpx.AsyncClient, redis_client_trades: redis.Redis, risky_address:str, sol_address:str=SOL_MINT,
#                         trade_amount:int=SOL_AMOUNT_LAMPORTS, buy_slippage:dict=BUY_SLIPPAGE, sell_slippage:dict=SELL_SLIPPAGE):

#     # Need to wait a bit before trading is possible - otherwise simulation error occurs
#     trade_logger.info(f"Sleeping for {START_UP_SLEEP} seconds before trading")
#     await asyncio.sleep(START_UP_SLEEP)

#     # Execute the buy function
#     buy_trade_result = await execute_buy(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=risky_address, 
#                                          sol_address=sol_address, trade_amount=trade_amount, buy_slippage=buy_slippage)

#     # Stop the execution if buy is unsuccessful
#     if buy_trade_result is False:
#         return None
    
#      # Get spot price
#     buy_spot_price = await get_price(httpx_client, risky_address)
#     trade_logger.info(f"Buy spot price for {risky_address}: {buy_spot_price}")

#     # Continue the transaction if buy_trade_result is True
#     trade_logger.info("TRADE IN PROGRESS")

#     if buy_spot_price is not None:
#         stoploss_trigger = buy_spot_price * (1-STOPLOSS)
#         trade_logger.info(f"Stoploss price: {stoploss_trigger} for {risky_address}")
    
#     # Enter trade duration loop
#     trade_start_time = time.time()
#     while True:
        
#         # Break the loop if the total duration has passed - this triggers an ordered sell
#         elapsed_time = time.time() - trade_start_time
#         if elapsed_time >= (MAX_TRADE_TIME_MINS * 60):
#             trade_logger.info(f"Initiating ordered sell for {risky_address}")
#             sell_result = await execute_sell(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=risky_address, sell_slippage=sell_slippage)
#             if sell_result: break
        
#         else:
#             # Check if stoploss has been triggered. If not sleep for MONITOR_PRICE_DELAY seconds
#             if buy_spot_price is None:
#                 buy_spot_price = await get_price(httpx_client, risky_address)
#                 stoploss_trigger = buy_spot_price * (1-STOPLOSS)
#                 trade_logger.info(f"Stoploss price: {stoploss_trigger} for {risky_address}")
            
#             stoploss_price = await get_price(httpx_client, risky_address)

#             if stoploss_price < stoploss_trigger:
#                 trade_logger.info(f"Initiating stoploss sell for {risky_address}")
#                 sell_result = await execute_sell(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=risky_address, sell_slippage=sell_slippage)
#                 if sell_result: break
#             else:
#                 await asyncio.sleep(MONITOR_PRICE_DELAY)

        



async def trade_wrapper(rpc_client: AsyncClient, httpx_client: httpx.AsyncClient, redis_client_trades: redis.Redis, risky_address: str, sol_address: str = SOL_MINT, 
                        trade_amount: int = SOL_AMOUNT_LAMPORTS, buy_slippage: dict = BUY_SLIPPAGE, sell_slippage: dict = SELL_SLIPPAGE):
    """
    Wrapper function that:
      1. Waits a startup delay.
      2. Executes the buy trade.
      3. Monitors the price, updating a trailing stoploss.
      4. Initiates a sell if the overall trade duration exceeds MAX_TRADE_TIME_MINS
         OR if the trailing stoploss is triggered.
    """

    # Wait a bit before trading begins.
    trade_logger.info(f"Sleeping for {START_UP_SLEEP} seconds before trading")
    await asyncio.sleep(START_UP_SLEEP)

    # Execute the buy function.
    buy_trade_result = await execute_buy(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=risky_address,
                                         sol_address=sol_address, trade_amount=trade_amount, buy_slippage=buy_slippage)

    # If the buy trade was unsuccessful, abort.
    if buy_trade_result is False:
        trade_logger.error("Buy trade failed. Exiting trade_wrapper.")
        return None

    # Get the initial buy price.
    initial_price = await get_price(httpx_client, risky_address)
    if initial_price is None:
        trade_logger.error(f"Unable to obtain initial price for {risky_address}. Exiting trade_wrapper.")
        return None

    # Continue the transaction if buy_trade_result is True        
    trade_logger.info("TRADE IN PROGRESS")
    trade_logger.info(f"Buy spot price for {risky_address}: {initial_price}")    

    # For a trailing stoploss, we record the highest observed price.
    highest_price = initial_price
    stoploss_trigger = highest_price * (1 - STOPLOSS)
    trade_logger.info(f"Initial trailing stoploss set at {stoploss_trigger} for {risky_address}")

    # Record the trade start time.
    trade_start_time = time.time()

    # Monitor the price until either the maximum trade duration elapses or the stoploss is triggered
    while True:
        
        # 1. If the trade duration exceeds the maximum allowed time, execute an ordered sell
        elapsed_time = time.time() - trade_start_time
        if elapsed_time >= (MAX_TRADE_TIME_MINS * 60):
            trade_logger.info(f"Trade duration for {risky_address} completed. Initiating ordered sell")
            sell_result = await execute_sell(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=risky_address, sell_slippage=sell_slippage, is_stoploss=False)
            if sell_result:
                break

        else:
            # 2. Trailing stoploss logic:
            #    - Get the current price.
            #    - If the current price is higher than our highest price, update highest_price and recalc stoploss_trigger.
            #    - If the current price falls below the stoploss trigger, sell.
            current_price = await get_price(httpx_client, risky_address)
            if current_price is None:
                trade_logger.warning(f"Unable to retrieve current price for {risky_address}. Will retry in {MONITOR_PRICE_DELAY} seconds.")
            else:
                trade_logger.info(f"New price for {risky_address}: Current price: {current_price}. Current trailing stoploss to {stoploss_trigger}.")

                # Update highest_price and trailing stoploss trigger if a new high is reached.
                if current_price > highest_price:
                    highest_price = current_price
                    stoploss_trigger = highest_price * (1 - STOPLOSS)
                    trade_logger.info(f"New high for {risky_address}: {highest_price}. Updated trailing stoploss to {stoploss_trigger}.")

                # Check if the price has fallen below the trailing stoploss trigger.
                if current_price < stoploss_trigger:
                    trade_logger.info(f"Current price {current_price} is below trailing stoploss {stoploss_trigger} for {risky_address}. Initiating stoploss sell.")
                    sell_result = await execute_sell(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=risky_address, sell_slippage=sell_slippage, is_stoploss=True)
                    if sell_result:
                        break

        # Wait for the monitoring delay before checking the price again.
        await asyncio.sleep(MONITOR_PRICE_DELAY)

    trade_logger.info(f"Trade completed for {risky_address}")