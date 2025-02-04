import statistics
import aiohttp
import requests
import base64
import json
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
from solders.keypair import Keypair # type: ignore
from solders.pubkey import Pubkey # type: ignore
from solders.hash import Hash       # type: ignore
from solders.message import MessageV0       # type: ignore
from config import (PRIORITY_FEE_MULTIPLIER, trade_logger)


# Get priority fees from QuickNode API
async def get_priority_fees_QN_function(httpx_client, rpc_url):
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "qn_estimatePriorityFees",
        "params": {
            "last_n_blocks": 25,        # max 100
            "account": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
            "api_version": 2
        }
    }

    try:
        # Make an async POST request
        response = await httpx_client.post(rpc_url, json=payload, headers=headers)

        if response.status_code == 200:
            response_data = response.json()
            recommended_fee = response_data["result"]["recommended"]
            print(json.dumps(response_data, indent=4)) 
            return int(recommended_fee * PRIORITY_FEE_MULTIPLIER)
        else:
            trade_logger.error(f"Priority fees error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        trade_logger.error(f"Error making HTTP call: {e}")
        return None
    

# Is the blockhash valid
async def get_block_info(RPC_URL, blockhash):
        # RPC request to get block information for a blockhash
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "isBlockhashValid",
            "params": [blockhash, {"commitment": "processed"}]
        }
        response = httpx.post(RPC_URL, json=payload)
        response_data = response.json()
        return response_data["result"]["value"]


# Pick the route with the highest "outAmount"
def pick_best_route(quote_response: dict):
    """
    Given a Jupiter quote_response dict, return the single best route 
    based on highest 'outAmount'.
    """

    # If the response has 'data' as a list of routes
    if isinstance(quote_response.get("data"), list):
        routes = quote_response["data"]
        if not routes:
            return None
        # Pick the one with the highest outAmount
        best = max(routes, key=lambda r: int(r["outAmount"]))
        return best

    # Else, if 'quote_response' itself looks like a single route
    # (some Jupiter endpoints return a single route with no 'data' array)
    if "outAmount" in quote_response:
        # We can assume it's already a single route object
        return quote_response

    return None


# Get the number of tokens purchased or sold    
async def tokens_purchased(async_client, wallet_address, token_address, commitment="processed"):
    public_key = Pubkey.from_string(wallet_address)
    mint_account = Pubkey.from_string(token_address)
    
    response = await async_client.get_token_accounts_by_owner_json_parsed(public_key, TokenAccountOpts(mint=mint_account), commitment=commitment)
    response_json = response.to_json()
    data = json.loads(response_json)
    token_amount = data["result"]["value"][0]['account']['data']['parsed']['info']['tokenAmount']['uiAmount']
    return token_amount


async def get_transaction_details(rpc_client, signature, wallet_address:str, input_mint:str, output_mint:str):
    
    # Returns the balance for a given mint token
    def find_token_balance_from_tx_hash(token_balances, mint, owner):
        for t in token_balances:
            if t["mint"] == mint and t.get("owner") == owner:
                return float(t["uiTokenAmount"]["uiAmountString"])
        return 0.0

    # signature = Signature.from_string(signature)
    status = await rpc_client.get_transaction(signature, "json", commitment=Confirmed, max_supported_transaction_version=0)
    transaction_json = status.to_json()
    data = json.loads(transaction_json)

    # print(json.dumps(data, indent=4))

    if data["result"] is None:
        trade_logger.error(f"Error fetching transaction details for Signature: {signature} - inputMint: {input_mint} and outputMint: {output_mint}")
        return None

    # Navigate to relevant sections
    timestamp = data["result"]["blockTime"]
    meta = data["result"]["meta"]
    pre_balances = meta["preBalances"]
    post_balances = meta["postBalances"]
    pre_token_balances = meta.get("preTokenBalances", [])
    post_token_balances = meta.get("postTokenBalances", [])

    # If statement for various trade scenarios
    # When a coin is bought with SOL
    if output_mint==SOL_MINT:
        sol_diff = post_balances[0] - pre_balances[0]
        token_out_diff = sol_diff/10**9

        pre_amount = find_token_balance_from_tx_hash(pre_token_balances, input_mint, wallet_address)
        post_amount = find_token_balance_from_tx_hash(post_token_balances, input_mint, wallet_address)
        token_in_diff = post_amount - pre_amount

    # When a coin is bought for SOL
    elif input_mint==SOL_MINT:
        sol_diff = post_balances[0] - pre_balances[0]
        token_in_diff = sol_diff/10**9

        pre_amount = find_token_balance_from_tx_hash(pre_token_balances, output_mint, wallet_address)
        post_amount = find_token_balance_from_tx_hash(post_token_balances, output_mint, wallet_address)
        token_out_diff = post_amount - pre_amount

    # When SOL is not part of the transaction
    elif output_mint!=SOL_MINT and input_mint!=SOL_MINT:
        token_out_pre_amount = find_token_balance_from_tx_hash(pre_token_balances, output_mint, wallet_address)
        token_out_post_amount = find_token_balance_from_tx_hash(post_token_balances, output_mint, wallet_address)
        token_in_pre_amount = find_token_balance_from_tx_hash(pre_token_balances, input_mint, wallet_address)
        token_in_post_amount = find_token_balance_from_tx_hash(post_token_balances, input_mint, wallet_address)

        token_out_diff = token_out_post_amount - token_out_pre_amount
        token_in_diff = token_in_post_amount - token_in_pre_amount 

    # Parse blocktime to datetime
    dt_object = datetime.datetime.fromtimestamp(timestamp)
    formatted_datetime = dt_object.strftime("%Y-%m-%d %H:%M:%S")

    # logger.info(f"Tokens out: {token_out_diff}. Tokens in: {token_in_diff}")
    return {"timestamp": formatted_datetime, "token_in_diff": token_in_diff, "token_out_diff": token_out_diff}


# Get current SOL balance
async def get_sol_balance(rpc_client, wallet_address):
    pubkey = Pubkey.from_string(wallet_address)
    response = await rpc_client.get_balance(pubkey)
    sol_val = response.value
    sol_bal = sol_val / 10**9
    return sol_bal


# Get the wallet balance of a token
async def get_token_balance(rpc_url, httpx_client, wallet, token_address):
    
    headers = {"accept": "application/json", "content-type": "application/json"}

    payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "getTokenAccountsByOwner",
        "params": [
            wallet,
            {"mint": token_address},
            {"encoding": "jsonParsed"},
        ],
    }

    response = await httpx_client.post(url=rpc_url, json=payload, headers=headers)
    response_data = response.json()
    token_amount = response_data["result"]["value"][0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]
    decimals = response_data['result']['value'][0]['account']['data']['parsed']['info']["tokenAmount"]["decimals"]
    return token_amount, decimals


# Returns the amount convert into lamports
def lamports_converstion(amount, decimals):
    return int(amount * (10 ** decimals))


async def get_price(client:httpx.AsyncClient, address, purpose="stoploss", timeout=10):

    # Cannot use vsToken and showExtraInfo. vsToken provides the derived (or market average) price
    # All prices are in USDC (unless if vsToken is used)

    payload = {
        "ids":address,
        "showExtraInfo": True
    }

    while True:
        response = await client.get(url=JUPITER_PRICE_URL, params=payload, timeout=Timeout(timeout=timeout))
        response = response.json()
        response = response["data"][address]
        print(response)

        # If a trade hasn't occured in the last 15 seconds it will return None. Therefore used the derivedPrice
        # if response["lastJupiterSellPrice"] is None or response["lastJupiterBuyPrice"] is None:
        #     response = await client.get(url=JUPITER_PRICE_URL, params={"ids": address}, timeout=Timeout(timeout=timeout))
        #     response = response.json()
        #     return response["data"][address]['price']
            
        # For the stoploss, monitor the last sell price. Else monitor the buy price
        if response["price"] is None:
            trade_logger.error(f"No price received for {address}")
            await asyncio.sleep(MONITOR_PRICE_DELAY)
            continue
        else:
            last_swapped_price = response["extraInfo"]["lastSwappedPrice"]
            last_quoted_price = response["extraInfo"]["quotedPrice"]

            if purpose=="stoploss" and last_swapped_price["lastJupiterSellPrice"] is not None:
                last_sell_price = last_swapped_price["lastJupiterSellPrice"]
                return last_sell_price
            elif purpose=="takeprofit" and last_swapped_price["lastJupiterBuyPrice"] is not None:
                last_buy_price = last_swapped_price["lastJupiterBuyPrice"]
                return last_buy_price
            else:
                response = await client.get(url=JUPITER_PRICE_URL, params={"ids": address}, timeout=Timeout(timeout=timeout))
                response = response.json()
                return response["data"][address]['price']
        