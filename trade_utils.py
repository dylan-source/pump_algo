

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
                    BUY_SLIPPAGE, SELL_SLIPPAGE, START_UP_SLEEP, SELL_SLIPPAGE_DELAY)
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
            # recommended_fee = int(np.percentile(fees, 65) * multiplier)

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

    # If simulation fails due to exceeded slippage a custom error is returned by Jupiter
    # if isinstance(signature, dict):
    #     # print("Confirm_tx functon error: ", signature["Error"]["InstructionError"][0]["Custom"])
    #     return signature
    
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
        trade_logger.error(f"No routes found for address: {risk_address} - slippage: {slippage}")
        return None
    else:
        trade_logger.info(f"Routes found for address: {risk_address} - slippage: {slippage}")
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
                trade_logger.error(f"Simulation failed: {simulate_resp}")
                return {"Error": err}
            trade_logger.info("No simulation error")

            # If simulation is successful, send the signed transaction
            opts = TxOpts(skip_confirmation=True, skip_preflight=True, preflight_commitment=Processed, max_retries=2)
            transaction_id = await rpc_client.send_transaction(signed_tx, opts=opts)
            return transaction_id.value  # Returns a Signature object

    except Exception as e:
        trade_logger.error(f"Error executing swap transaction: {e}")
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
        

# Failsafe execute sell - to clear wallet of SPL tokens
async def startup_sell(rpc_client:AsyncClient, httpx_client:httpx.AsyncClient, redis_client_trades:redis.Redis, sell_slippage:dict=SELL_SLIPPAGE):
    
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
                await execute_sell(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=mint, sell_slippage=sell_slippage)
                await asyncio.sleep(5)

        return None
    
    except Exception as e:
        trade_logger.error(f"Error with startup_sell function - {e}")


# Function to execute a sell
async def execute_sell(rpc_client:AsyncClient, httpx_client:httpx.AsyncClient, redis_client_trades:redis.Redis, risky_address:str, sell_slippage:dict=SELL_SLIPPAGE):

    # Initialize some function variables
    sell_slippage = SELL_SLIPPAGE["MIN"]
    sell_loop_count = 0

    # Confirm that the risky token is in the wallet
    risky_amount = await get_token_balance(rpc_client=rpc_client, wallet_address=WALLET_ADDRESS, token_mint_address=risky_address)
    if risky_amount == 0:
        trade_logger.error(f"No tokens found for {risky_address}")
        return None
    
    # Get recommended priority fee - based upon last N blocks times multiplier - do not trade is priority fee is too high/low
    while True:
        priority_fee_dict = await get_recent_prioritization_fees(httpx_client, RPC_URL)
        if priority_fee_dict is None:
            trade_logger.error("Sell function - priority fees not found - retrying")
            await asyncio.sleep(SELL_LOOP_DELAY)
        else:
            break

    # Create the sellLoop to execute sell transaction
    while True:
        match sell_loop_count:
            case 0 if priority_fee_dict["recommended"] <= PRIORITY_FEE_MAX:
                recommended_priority_fee = priority_fee_dict["recommended"]

            case 1 if priority_fee_dict["percentile_65"] <= PRIORITY_FEE_MAX:
                recommended_priority_fee = priority_fee_dict["percentile_65"]

            case 2 if priority_fee_dict["percentile_75"] <= PRIORITY_FEE_MAX:
                recommended_priority_fee = priority_fee_dict["percentile_75"]

            # case 3 if sell_loop_count >= 2 and (priority_fee_dict["percentile_75"] * PRIORITY_FEE_MULTIPLIER) <= PRIORITY_FEE_MAX:
            #     recommended_priority_fee = priority_fee_dict["percentile_75"] * PRIORITY_FEE_MULTIPLIER

            case _:
                trade_logger.error(f"Priority fees too high or swap error for {risky_address} - {risky_amount} - {sell_slippage}")
        trade_logger.info(f"Priority fee to be applied: {recommended_priority_fee}")
        print(f"Priority fee to be applied: {recommended_priority_fee}")


        # Loop until successful if simulation error is received
        while True:

            # Execute the swap
            trade_logger.info(f"Sell slippage to be applied: {sell_slippage}")
            sell_quote = await get_jupiter_quote(httpx_client, input_address=risky_address, output_address=SOL_MINT, amount=risky_amount, slippage=sell_slippage, is_buy=False)
            sell_swap_response = await execute_swap(rpc_client=rpc_client, httpx_client=httpx_client, quote=sell_quote, priority_fee=recommended_priority_fee)
            
            if isinstance(sell_swap_response, dict) and sell_slippage <= SELL_SLIPPAGE["MAX"]:
                sell_slippage = sell_slippage + SELL_SLIPPAGE["INCREMENTS"]
                trade_logger.info(f"Increasing sell slippage to: {sell_slippage}")
                continue
            elif isinstance(sell_swap_response, dict) and sell_slippage > SELL_SLIPPAGE["MAX"]:
                trade_logger.info(f"Maximum sell slippage reached: {sell_slippage}")
                trade_logger.info(f"Sleeping for {SELL_SLIPPAGE_DELAY} seconds and then retrying")

                await asyncio.sleep(30)
                sell_slippage = SELL_SLIPPAGE["MAX"]
                continue

            else:
            
                sell_confirm_result = await confirm_tx(rpc_client=rpc_client, signature=sell_swap_response, commitment=Finalized)

                # If confirmation failed and max slippage is reached then return False
                if (sell_confirm_result is None or sell_confirm_result["Status"] != "Ok") and sell_slippage > SELL_SLIPPAGE["MAX"]:
                    trade_logger.info(f"Maximum sell slippage reached: {sell_slippage} for {risky_address}")
                    trade_logger.info(f"Sell slippage too high for {risky_address} - {risky_amount} - {sell_slippage}")
                    return False

                # If confirmation failed, increase slippage and retry
                elif (sell_confirm_result is None or sell_confirm_result["Status"] != "Ok") and sell_slippage <= SELL_SLIPPAGE["MAX"]:
                    trade_logger.error(f"Sell trade failed - {risky_address} - {risky_amount} - {sell_slippage}")
                    sell_slippage = sell_slippage + SELL_SLIPPAGE["INCREMENTS"]
                    trade_logger.error(f"Increasing sell slippage to: {sell_slippage}")
                    sell_loop_count += 1

                    # Create a priorityFees loop to get an updated priority fees dictionary
                    priority_fees_loop_count = 0
                    while True:
                        priority_fee_dict = await get_recent_prioritization_fees(httpx_client, RPC_URL)
                        if priority_fee_dict is None:
                            trade_logger.error(f"Sell function - priority fees not found - retrying for the {priority_fees_loop_count} time")
                            
                            # Prevent infinite looping
                            priority_fees_loop_count += 1
                            if priority_fees_loop_count > 10: 
                                recommended_priority_fee = PRIORITY_FEE_MAX
                                break 
                            
                            await asyncio.sleep(SELL_LOOP_DELAY)
                        else: break # break priorityFees loop if a new priority fee was received

                    # Break execution loop and apply new prioritization fees
                    break

                # If successful then get the trasnaction details and save the result
                else:
                    # Once confirmed provide the tx link and get the transaction details
                    trade_logger.info(f"Transaction sent: https://solscan.io/tx/{sell_swap_response}")
                    sell_tx_result = await get_transaction_details(rpc_client=rpc_client, signature=sell_swap_response, wallet_address=WALLET_ADDRESS, input_mint=risky_address, output_mint=SOL_MINT)
                    
                    # Fetch the buy data from Redis and save all info in a CSV
                    buy_trade_data = await fetch_trade_data(redis_client_trades=redis_client_trades, token_address=risky_address)
                    sell_trade_data = {
                        "sell_timestamp": sell_tx_result["timestamp"],
                        "sell_transaction_hash": str(sell_swap_response),
                        "sell_tokens_spent": sell_tx_result["inputMint_diff"],
                        "sell_tokens_received": sell_tx_result["outputMint_diff"]
                        }
                    await write_trades_to_csv(tx_address=risky_address, buy_data_dict=buy_trade_data, sell_data_dict=sell_trade_data, redis_client=redis_client_trades)
                    return True
            
        
# Function to execute a buy
async def execute_buy(rpc_client:AsyncClient, httpx_client:httpx.AsyncClient, redis_client_trades:redis.Redis, risky_address:str, sol_address:str=SOL_MINT, 
                      trade_amount:int=SOL_AMOUNT_LAMPORTS, buy_slippage:dict=BUY_SLIPPAGE):

    # Get SOL balance in lamports and confirm if the wallet balance is greater than the minimum threshold
    balance_resp = await rpc_client.get_balance(Pubkey.from_string(WALLET_ADDRESS))
    sol_value = (balance_resp.value) 

    if sol_value <= SOL_MIN_BALANCE_LAMPORTS:
        trade_logger.error(f"SOL balance below wallet minimum threshold - Wallet amount: {sol_value} - Trade amount: {SOL_MIN_BALANCE_LAMPORTS}")
        return False
    else:
        trade_logger.info(f"Sufficient SOL for trade - Wallet amount: {sol_value} - Trade amount: {SOL_AMOUNT_LAMPORTS}")


    # Get recommended priority fee - based upon last N blocks times multiplier -  do not trade is priority fee is too high/low
    recommended_priority_fee = await get_recent_prioritization_fees(httpx_client, RPC_URL)
    if recommended_priority_fee is None:
        trade_logger.error("Priority fees not found")
        return False
    else:
        recommended_priority_fee = recommended_priority_fee["recommended"]
        trade_logger.info(f"Recommended priority fee: {recommended_priority_fee}")


    # Loop until successful if simulation error is received or max slippage is reached
    buy_slippage = BUY_SLIPPAGE["MIN"]
    while True:
        
        # Execute buy transaction
        trade_logger.info(f"Buy slippage to be applied: {buy_slippage}")
        quote = await get_jupiter_quote(httpx_client, input_address=sol_address, output_address=risky_address, amount=trade_amount, slippage=buy_slippage, is_buy=True)
        buy_swap_response = await execute_swap(rpc_client=rpc_client, httpx_client=httpx_client, quote=quote, priority_fee=recommended_priority_fee)
        
        # If the simulation failed, increase the slippage and retry. Return False is max slippage is reached
        if isinstance(buy_swap_response, dict) and buy_slippage <= BUY_SLIPPAGE["MAX"]:
            buy_slippage = buy_slippage + BUY_SLIPPAGE["INCREMENTS"]
            trade_logger.info(f"Increasing buy slippage to: {buy_slippage}")
            continue
        elif isinstance(buy_swap_response, dict) and buy_slippage > BUY_SLIPPAGE["MAX"]:
            trade_logger.info(f"Maximum slippage reached: {buy_slippage} for {risky_address}")
            return False
                
        else:        
            
            # If the simulation passes then confirm the transaction
            confirm_result = await confirm_tx(rpc_client=rpc_client, signature=buy_swap_response, commitment=Finalized)

            # If confirmation failed, increase slippage and retry
            if (confirm_result is None or confirm_result["Status"] != "Ok") and buy_slippage <= BUY_SLIPPAGE["MAX"]:
                trade_logger.error(f"Buy trade failed - {risky_address} - {trade_amount} - {buy_slippage}")
                buy_slippage = buy_slippage + BUY_SLIPPAGE["INCREMENTS"]
                trade_logger.error(f"Increasing buy slippage to: {buy_slippage}")
                continue

            # If confirmation failed and max slippage is reached then return False
            elif (confirm_result is None or confirm_result["Status"] != "Ok") and buy_slippage > BUY_SLIPPAGE["MAX"]:
                trade_logger.info(f"Maximum buy slippage reached: {buy_slippage}")
                trade_logger.info(f"Buy slippage too high for {risky_address} - {trade_amount} - {buy_slippage}")
                return False

            # If confirmation is successful then log the transaction and return True
            else:
                trade_logger.info(f"Transaction sent: https://solscan.io/tx/{buy_swap_response}")
                tx_result = await get_transaction_details(rpc_client=rpc_client, signature=buy_swap_response, wallet_address=WALLET_ADDRESS, input_mint=sol_address, output_mint=risky_address)
                trades_cache_result = await store_trade_data(redis_client_trades=redis_client_trades, signature=buy_swap_response, timestamp=tx_result["timestamp"], 
                                                                token_address=risky_address, tokens_spent=tx_result["inputMint_diff"], tokens_received=tx_result["outputMint_diff"])
                trade_logger.info(f"Cached buy results for {risky_address}: {trades_cache_result}")
                return True


# Wrapper to house full trade logic
async def trade_wrapper(rpc_client:AsyncClient, httpx_client:httpx.AsyncClient, redis_client_trades: redis.Redis, risky_address:str, sol_address:str=SOL_MINT, trade_amount:int=SOL_AMOUNT_LAMPORTS, 
                        buy_slippage:dict=BUY_SLIPPAGE, sell_slippage:dict=SELL_SLIPPAGE):

    # Need to wait a bit before trading is possible - otherwise simulation error occurs
    trade_logger.info(f"Sleeping for {START_UP_SLEEP} seconds before trading")
    await asyncio.sleep(START_UP_SLEEP)

    # Execute the buy function
    buy_trade_result = await execute_buy(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=risky_address, 
                                         sol_address=sol_address, trade_amount=trade_amount, buy_slippage=buy_slippage)

    # Stop the execution if buy is unsuccessful
    if buy_trade_result is False:
        return None
    
     # Get spot price
    buy_spot_price = await get_price(httpx_client, risky_address)
    trade_logger.info(f"Buy spot price for {risky_address}: {buy_spot_price}")

    # Continue the transaction if buy_trade_result is True
    trade_logger.info("TRADE IN PROGRESS")

    if buy_spot_price is not None:
        stoploss_trigger = buy_spot_price * (1-STOPLOSS)
        trade_logger.info(f"Stoploss price: {stoploss_trigger} for {risky_address}")
    
    # Enter trade duration loop
    trade_start_time = time.time()
    while True:
        
        # Break the loop if the total duration has passed - this triggers an ordered sell
        elapsed_time = time.time() - trade_start_time
        if elapsed_time >= (MAX_TRADE_TIME_MINS * 60):
            trade_logger.info(f"Initiating ordered sell for {risky_address}")
            sell_result = await execute_sell(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=risky_address, sell_slippage=sell_slippage)
            if sell_result: break
        
        else:
            # Check if stoploss has been triggered. If not sleep for MONITOR_PRICE_DELAY seconds
            if buy_spot_price is None:
                buy_spot_price = await get_price(httpx_client, risky_address)
                stoploss_trigger = buy_spot_price * (1-STOPLOSS)
                trade_logger.info(f"Stoploss price: {stoploss_trigger} for {risky_address}")
            
            stoploss_price = await get_price(httpx_client, risky_address)

            if stoploss_price < stoploss_trigger:
                trade_logger.info(f"Initiating stoploss sell for {risky_address}")
                sell_result = await execute_sell(rpc_client=rpc_client, httpx_client=httpx_client, redis_client_trades=redis_client_trades, risky_address=risky_address, sell_slippage=sell_slippage)
                if sell_result: break
            else:
                await asyncio.sleep(MONITOR_PRICE_DELAY)

        

