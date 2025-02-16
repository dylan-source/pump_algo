import datetime
import json
import asyncio
from solana.rpc.commitment import Processed, Confirmed, Finalized
from solana.rpc.types import TokenAccountOpts
from solders.signature import Signature #type: ignore
from solders.pubkey import Pubkey  # type: ignore
# from raydium.constants import TOKEN_PROGRAM_ID
from config import client, payer_keypair, trade_logger, WALLET_ADDRESS

def get_wallet_changes(tx, spl_mint, wallet_pubkey):
    """
    Given a getTransaction result (tx), the mint address of the SPL token,
    and your wallet public key, returns a tuple:
      (sol_change, spl_token_change)
    
    SOL change is calculated from the first value of preBalances and postBalances.
    The SPL token change is determined by filtering the preTokenBalances and
    postTokenBalances for the given mint and owner (your wallet).
    
    Parameters:
      tx (dict): The transaction object returned by getTransaction.
      spl_mint (str): The mint address of the SPL token of interest.
      wallet_pubkey (str): Your wallet’s public key.
    
    Returns:
      tuple: (sol_change, spl_token_change)
             where sol_change is in lamports.
             and spl_token_change is the difference in the "amount" field.
    """
    
    # Filter outer details to get transaction timestamp
    txn_json = json.loads(tx.value.to_json())
    blocktime = txn_json['blockTime']
    dt_object = datetime.datetime.fromtimestamp(blocktime)
    formatted_datetime = dt_object.strftime('%Y-%m-%d %H:%M:%S')
    
    # Filter for inner instructions
    tx = json.loads(tx.value.transaction.meta.to_json())
    
    # Compute SOL change using the first element in preBalances/postBalances.
    sol_change = tx["postBalances"][0] - tx["preBalances"][0]

    # Find the SPL token account that belongs to your wallet.
    pre_amount = 0
    post_amount = 0
    
    for token in tx.get("preTokenBalances", []):
        if token.get("mint") == spl_mint and token.get("owner") == wallet_pubkey:
            pre_amount = int(token["uiTokenAmount"]["amount"])
            break  # assume only one token account per wallet for this mint

    for token in tx.get("postTokenBalances", []):
        if token.get("mint") == spl_mint and token.get("owner") == wallet_pubkey:
            post_amount = int(token["uiTokenAmount"]["amount"])
            break

    spl_token_change = post_amount - pre_amount

    return {"Timestamp": formatted_datetime, "SOL change": sol_change, "Token change": spl_token_change}

async def get_token_balance(mint_str: str) -> float | None:

    mint = Pubkey.from_string(mint_str)
    response = await client.get_token_accounts_by_owner_json_parsed(
        payer_keypair.pubkey(),
        TokenAccountOpts(mint=mint),
        commitment=Processed
    )

    if response.value:
        accounts = response.value
        if accounts:
            token_amount = accounts[0].account.data.parsed['info']['tokenAmount']['uiAmount']
            if token_amount:
                return float(token_amount)
    return None


async def confirm_txn(txn_sig: Signature, spl_mint:str, max_retries: int = 15, retry_interval: int = 3) -> bool:    
    retries = 1
    
    while retries < max_retries:
        try:
            txn_res = await client.get_transaction(
                txn_sig, 
                encoding="json", 
                commitment=Confirmed, 
                max_supported_transaction_version=0)
            
            txn_json = json.loads(txn_res.value.transaction.meta.to_json())
            
            if txn_json['err'] is None:
                trade_logger.info(f"Transaction confirmed")
                wallet_changes = get_wallet_changes(txn_res, spl_mint, WALLET_ADDRESS)
                trade_logger.info(f"Transaction details: | SOL change: {wallet_changes.get('SOL change', '')} | Token change: {wallet_changes.get('Token change', '')}")
                return True, wallet_changes
            
            # trade_logger.error("Error: Transaction not confirmed. Retrying...")
            error = txn_json['err']
            if error:
                trade_logger.error(f"Transaction failed...{error}")     # {'InstructionError': [4, {'Custom': 30}]}            
                return error, None

        except Exception as e:
            # Catch the error specifically relating to the confirmation failing
            if str(e) == "'NoneType' object has no attribute 'transaction'":
                trade_logger.info(f"Awaiting confirmation... try count: {retries}")
                retries += 1
                await asyncio.sleep(retry_interval)
            else:
                trade_logger.error(f"Confirm_tx error: {e}")
                return e, None
    
    trade_logger.error("Max retries reached. Transaction confirmation failed.")
    return None, None



# async def confirm_txn_original(txn_sig: Signature, max_retries: int = 15, retry_interval: int = 3) -> bool:    
#     retries = 1
    
#     while retries < max_retries:
#         try:
#             txn_res = await client.get_transaction(
#                 txn_sig, 
#                 encoding="json", 
#                 commitment=Confirmed, 
#                 max_supported_transaction_version=0)
            
#             txn_json = json.loads(txn_res.value.transaction.meta.to_json())
            
#             if txn_json['err'] is None:
#                 trade_logger.info(f"Transaction confirmed")
#                 return True
            
#             # trade_logger.error("Error: Transaction not confirmed. Retrying...")
#             error = txn_json['err']
#             if error:
#                 trade_logger.error(f"Transaction failed...{error}")     # {'InstructionError': [4, {'Custom': 30}]}            
#                 return error
#         except Exception as e:
#             trade_logger.info(f"Awaiting confirmation... try count: {retries}")
#             retries += 1
#             await asyncio.sleep(retry_interval)
    
#     trade_logger.error("Max retries reached. Transaction confirmation failed.")
#     return None

