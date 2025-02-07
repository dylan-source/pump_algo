import requests
import base64
import base58
import json
import httpx
from httpx._config import Timeout
import asyncio
import aiohttp
from solana.rpc.api import Client
from solana.rpc.async_api import AsyncClient
# from solana.transaction import Transaction
from solders.transaction import VersionedTransaction # type: ignore
from solders.signature import Signature # type: ignore
from solders import message
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Processed, Confirmed, Finalized
from solana.rpc.types import TokenAccountOpts
from solders.keypair import Keypair # type: ignore
from config import (RPC_URL, PRIVATE_KEY, JUPITER_QUOTE_URL, JUPITER_SWAP_URL, JUPITER_PRICE_URL,
                    WALLET_ADDRESS, TIME_TO_SLEEP, logger)
# from balance_utils import get_token_balance, get_sol_balance, lamports_converstion, get_transaction_details
# from metadata_utils import fetch_token_metadata
from solders.pubkey import Pubkey # type: ignore
from solders.hash import Hash       # type: ignore
from solders.message import MessageV0       # type: ignore

rpc_client = AsyncClient(RPC_URL)
httpx_client = httpx.AsyncClient(timeout=30)


# Confirm if the transaction was successful
async def confirm_tx(rpc_client, signature, commitment=Finalized):
    
    # Convert signature to a string for logging
    signature_string = str(signature.value)
    # print(type(signature_string))
    # print(signature_string)

    try:
        confirmation = await rpc_client.confirm_transaction(signature.value, commitment=commitment)

        if confirmation.value and len(confirmation.value) > 0:
            transaction_status = confirmation.value[0]  
            transaction_status = transaction_status.to_json()
            transaction_status = json.loads(transaction_status)
        
            # Unpack and log the results
            status = next(iter(transaction_status["status"].keys()), None)
            error = transaction_status["err"]
            confirmationStatus = transaction_status["confirmationStatus"]

            logger.info(f"Trade confirmation for {signature_string} - {status} - {error} - {confirmationStatus}")

            return {
                "Status": status,
                "Error": error,
                "confirmationStatus": confirmationStatus
            }
        else:
            logger.error(f"No transaction status in confirmation response: {signature_string}")
            return None
    except Exception:
        logger.error(f"Confirmation error: {signature_string}")
        return None

# Get recent priority fees
def get_priority_fees(RPC_URL):
    
    payload = json.dumps({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "qn_estimatePriorityFees",
    "params": {
        "last_n_blocks": 100,
        "account": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
        "api_version": 2
    }
    })
    headers = {
    'Content-Type': 'application/json',
    }

    response = requests.request("POST", RPC_URL, headers=headers, data=payload)

    if response.status_code == 200:
        response_data = response.json()
        print(json.dumps(response_data, indent=4))  # Indent to pretty-print
    else:
        print(f"Error: {response.status_code} - {response.text}")


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
async def check_valid_block(RPC_URL, blockhash):
        
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


# Get a quote
async def get_jupiter_quote(httpx_client, input_address:str, output_address:str, amount:int, slippage:str, is_buy:bool):
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
        "swapMode": "ExactIn"
    }

    quote_response = await httpx_client.get(JUPITER_QUOTE_URL, headers={'Accept':'application/json'}, params=params)
    quote_response = quote_response.json()

    # Define risky address for logging purposes
    if is_buy: 
        risk_address = output_address
    else:
        risk_address = input_address

    # Log and return the result for the best route
    # routes = quote_response.get("routePlan", [])
    if not quote_response:
        logger.error(f"No routes found for {risk_address} - {slippage}")
        return None
    else:
        logger.info(f"Routes found for {risk_address} - {slippage}")
        return quote_response


# Execute a swap based upon quote
async def execute_swap(rpc_client, httpx_client, quote, address):

    balance_resp = await rpc_client.get_balance(Pubkey.from_string(WALLET_ADDRESS))
    value = (balance_resp.value)/10**9
    print("Balance:", value)  # In SOL

    payload = {
        "quoteResponse": quote,
        "userPublicKey": WALLET_ADDRESS,
        "wrapUnwrapSOL": True,
        "prioritizationFeeLamports": int(0.0007*10**9)  
    }

    try:
        # Post a call to the Jupiter swap API
        swap_response = await httpx_client.post(JUPITER_SWAP_URL, headers={'Accept': 'application/json'}, json=payload)
        swap_data = swap_response.json()
        swap_transaction = swap_data.get('swapTransaction')  

        # swapTransaction contains the serialized instructions to execute the swap. Return none, if no instructions were found
        if not swap_transaction:
            logger.error("No swapTransaction found in the response.")
            return None
        
        # If swapTransaction is found, decode the swap instructions and sign the transaction
        else:
            # Decode and sign the transaction
            raw_transaction = VersionedTransaction.from_bytes(base64.b64decode(swap_transaction))
            old_msg = raw_transaction.message

            # The blockhash inside your Jupiter transaction
            # jup_blockhash = raw_transaction.message.recent_blockhash
            # print("Jupiter's blockhash:", jup_blockhash)
            # jup_blockhash_valid = await check_valid_block(RPC_URL, jup_blockhash)
            # print("Jupiter's blockhash valid:", jup_blockhash_valid)

            # A fresh blockhash from your node
            fresh_blockhash_resp = await rpc_client.get_latest_blockhash()
            fresh_blockhash = str(fresh_blockhash_resp.value.blockhash)
            # fresh_blockhash_valid = await check_valid_block(RPC_URL, fresh_blockhash)
            # print("Fresh blockhash:", fresh_blockhash)
            # print("Fresh blockhash valid:", fresh_blockhash_valid)

            # print("Message accountKeys:", raw_transaction.message.account_keys)
            # print("Signers needed:", raw_transaction.message.header.num_required_signatures)

            # Sign the transaction - old method
            # signature = PRIVATE_KEY.sign_message(message.to_bytes_versioned(raw_transaction.message))

            # status_resp = await rpc_client.get_signature_statuses([signature])
            # print(status_resp.value)

            # signed_txn = VersionedTransaction.populate(raw_transaction.message, [signature])

            # Replace the Jupiter blockhash with a freash one to prevent forked/ephemeral blockhash issues
            new_msg = clone_v0_message_with_new_blockhash(old_msg, fresh_blockhash)
            # signed_tx = VersionedTransaction(raw_transaction.message, [PRIVATE_KEY])
            signed_tx = VersionedTransaction(new_msg, [PRIVATE_KEY])
            

            # Simulate the transaction
            simulate_resp = await simulate_versioned_transaction(httpx_client=httpx_client, rpc_url=RPC_URL, signed_txn=signed_tx)
            err = simulate_resp.get("result", {}).get("value", {}).get("err")
            if err is not None:
                logger.error(f"Simulation failed: {err}")
                return None
            print("Simulation error: ", err)


            # Send the message      
            opts = TxOpts(skip_preflight=False, preflight_commitment=Finalized)      
            transaction_id = await rpc_client.send_transaction(signed_tx, opts=opts)
            print(transaction_id.value)

            # Send the signed transaction. Preflight means the node performs a "dry-run" of the TX before broadcasting to the validators
            # opts = TxOpts(skip_preflight=False, preflight_commitment=Processed)
            # result = await rpc_client.send_raw_transaction(txn=bytes(signed_txn), opts=opts)
            # print(result.value)
            
            # Check if the transaction was confirmed
            confirm_result = await confirm_tx(rpc_client, transaction_id, commitment=Processed)
            
            if confirm_result is not None:
                # confirmation = await rpc_client.confirm_transaction(result.value, commitment=Finalized)
                
                # Get result of signed message
                transaction_id = transaction_id.value
                if transaction_id is None:
                    logger.error(f"No transaction ID in RPC response for {address}")
                    return None
                else:
                    logger.info(f"Transaction sent: https://solscan.io/tx/{transaction_id}")
                    logger.info(f"Swap executed: {transaction_id}")
                    return transaction_id
            else:
                return None

    except KeyError as e:
        logger.error(f"KeyError: {e}")
        return None
    except Exception as e:
        logger.error(f"Error sending transaction: {e}")
        return None


# Get the transaction status - was the transaction validly executed?
# async def get_transaction_status(async_client, signature):
    
#     # sig = Signature.from_string(transaction_id)
#     status = await async_client.get_signature_statuses([signature],search_transaction_history=True)
#     transaction_json = status.to_json()
#     data = json.loads(transaction_json)
#     data = data["result"]["value"][0]
    
#     if data is None:
#         logger.error(f"Transaction failed")
#         return False
    
#     elif data["err"] is not None:
#         transaction_error = data["err"]
#         logger.error(f"Transaction error: {transaction_error}")
#         return False
    
#     else:
#         tx_status = data["confirmationStatus"]
#         logger.info(f"Transaction status: {tx_status}")
#         return True
    
    
# # Get the number of tokens purchased or sold    
# async def tokens_purchased(async_client, wallet_address, token_address, commitment="processed"):
#     public_key = Pubkey.from_string(wallet_address)
#     mint_account = Pubkey.from_string(token_address)
    
#     response = await async_client.get_token_accounts_by_owner_json_parsed(public_key, TokenAccountOpts(mint=mint_account), commitment=commitment)
#     response_json = response.to_json()
#     data = json.loads(response_json)
#     token_amount = data["result"]["value"][0]['account']['data']['parsed']['info']['tokenAmount']['uiAmount']
#     return token_amount


# Fetch token price from Jupiter
async def get_price(client, address, purpose="stoploss", timeout=10):

    # Cannot use vsToken and showExtraInfo. vsToken provides the derived (or market average) price
    # All prices are in USDC (unless if vsToken is used)

    payload = {
        "ids":address,
        "showExtraInfo": True
    }
    response = await client.get(url=JUPITER_PRICE_URL, params=payload, timeout=Timeout(timeout=timeout))
    response = response.json()
    response = response["data"][address]["extraInfo"]["lastSwappedPrice"]

    # If a trade hasn't occured in the last 15 seconds it will return None. Therefore used the derivedPrice
    # if response["lastJupiterSellPrice"] is None or response["lastJupiterBuyPrice"] is None:
    #     response = await client.get(url=JUPITER_PRICE_URL, params={"ids": address}, timeout=Timeout(timeout=timeout))
    #     response = response.json()
    #     return response["data"][address]['price']
        
    # For the stoploss, monitor the last sell price. Else monitor the buy price
    if purpose=="stoploss" and response["lastJupiterSellPrice"] is not None:
        last_sell_price = response["lastJupiterSellPrice"]
        return last_sell_price
    elif purpose=="takeprofit" and response["lastJupiterBuyPrice"] is not None:
        last_buy_price = response["lastJupiterBuyPrice"]
        return last_buy_price
    else:
        response = await client.get(url=JUPITER_PRICE_URL, params={"ids": address}, timeout=Timeout(timeout=timeout))
        response = response.json()
        return response["data"][address]['price']





# # My code
# async def execute_sell(input_address: str, output_address: str, perc_sell: float, rpc_client, slippage_bps: int):
#     """
#     Asynchronously execute a sell transaction.
#     """
#     # If get_token_balance is synchronous, wrap it in asyncio.to_thread:
#     sell_bal, decimals = await asyncio.to_thread(get_token_balance, RPC_URL, WALLET_ADDRESS, input_address)
#     sell_bal = lamports_converstion(sell_bal, decimals)
#     amount_to_sell = int(sell_bal * perc_sell)

#     logger.info(f"Amount of {output_address} to sell: {amount_to_sell}")

#     tx_id = await execute_swap(input_address, output_address, amount_to_sell, rpc_client, slippage_bps)
#     return tx_id

# # Execute swap function
# async def execute_swap(private_key, async_client, jupiter, input_address, output_address, amount, slippage):
     
#     # Execute order
#     transaction_data = await jupiter.swap(
#         input_mint=input_address,  
#         output_mint=output_address,  
#         amount=amount,  # Amount in lamports
#         slippage_bps=slippage,  # Slippage in basis points
#     )

#     # Deserialize the transaction
#     raw_transaction = VersionedTransaction.from_bytes(base64.b64decode(transaction_data))
#     signature = private_key.sign_message(message.to_bytes_versioned(raw_transaction.message))
#     signed_txn = VersionedTransaction.populate(raw_transaction.message, [signature])

#     # Send the transaction
#     opts = TxOpts(skip_preflight=False, preflight_commitment=Processed)
#     result = await async_client.send_raw_transaction(txn=bytes(signed_txn), opts=opts)
#     transaction_id = json.loads(result.to_json())['result']
    
#     print("My function hash: ", transaction_id)
#     return transaction_id


# # Function to execute a buy transaction
# async def execute_buy(PRIVATE_KEY, rpc_client, redis_client, jupiter, SOL_MINT, token_address, SOL_AMOUNT, BUY_SLIPPAGE_BPS):
    
#     # Execute the buy swap for new token
#     tx_id = await execute_swap(PRIVATE_KEY, rpc_client, jupiter, SOL_MINT, token_address, SOL_AMOUNT, BUY_SLIPPAGE_BPS)
#     logger.info(f"Buy Executed: {tx_id}")
#     logger.info(f"Trade link: https://solscan.io/tx/{tx_id}")

#     if tx_id:
        
#         # Get the transaction status
#         status = await transaction_status(rpc_client, tx_id)
#         logger.info(f"Transaction status: {status}")
        
#         # Wait a bit to confirm TX finalization and fetch token metadata
#         await asyncio.sleep(TIME_TO_SLEEP)
#         timestamp, token_out_diff, token_in_diff = await get_transaction_details(rpc_client, tx_id, WALLET_ADDRESS, SOL_MINT, token_address)
#         name, symbol = await fetch_token_metadata(rpc_client, token_address)
#         logger.info(f"Transaction details: Bought: {symbol}, {name}, {token_in_diff} - Sold: SOL, Solana, {token_out_diff}")

#         # Store the relevant info in a Redis cache for later retrieval
#         result = await store_trade_data(redis_client, tx_id, timestamp, token_address, symbol, name, token_out_diff, token_in_diff)
#         logger.info(f"Trade details cached: {result}")
        
#     else:
#         logger.error(f"Failed to execute swap for {token_address}.")


async def trade_wrapper():
    INPUT_MINT = "So11111111111111111111111111111111111111112"  # SOL
    OUTPUT_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC
    # INPUT_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # SOL
    # OUTPUT_MINT = "So11111111111111111111111111111111111111112"  # USDC
    AMOUNT = int(0.001*10**9)
    AUTO_MULTIPLIER = 1.1 # a 10% bump to the median of getRecentPrioritizationFees over last 150 blocks
    SLIPPAGE_BPS = 500  # Slippage tolerance in basis

    quote = await get_jupiter_quote(httpx_client, input_address=INPUT_MINT, output_address=OUTPUT_MINT, amount=AMOUNT, slippage=SLIPPAGE_BPS, is_buy=True)
    await execute_swap(rpc_client, httpx_client, quote, OUTPUT_MINT)





if __name__ == "__main__":

    # actual_pubkey = PRIVATE_KEY.pubkey()
    # print("Private key's public key is:", actual_pubkey)
    # print("Jupiter userPublicKey / WALLET_ADDRESS is:", WALLET_ADDRESS)

    # if str(actual_pubkey) != WALLET_ADDRESS:
    #     print("Mismatch! The PRIVATE_KEY doesn't match WALLET_ADDRESS.")

    asyncio.run(trade_wrapper())
    # get_priority_fees()
