import json
import time
from solana.rpc.commitment import Confirmed, Processed
from solana.rpc.types import TokenAccountOpts
from solders.signature import Signature #type: ignore
from solders.pubkey import Pubkey  # type: ignore
from config import client, payer_keypair, trade_logger

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

async def confirm_txn(txn_sig: Signature, max_retries: int = 20, retry_interval: int = 3) -> bool:
    trade_logger.error(txn_sig)
    trade_logger.error(type(txn_sig))
    
    retries = 1
    
    while retries < max_retries:
        try:
            txn_res = await client.get_transaction(
                txn_sig, 
                encoding="json", 
                commitment=Confirmed, 
                max_supported_transaction_version=0)
            
            trade_logger.error(txn_res)
            trade_logger.error(txn_res.value)
            txn_json = json.loads(txn_res.value.transaction.meta.to_json())
            
            if txn_json['err'] is None:
                trade_logger.info("Transaction confirmed... try count:", retries)
                return True
            
            trade_logger.error("Error: Transaction not confirmed. Retrying...")
            if txn_json['err']:
                trade_logger.error("Transaction failed.")
                return False
        except Exception as e:
            trade_logger.info("Awaiting confirmation... try count:", retries)
            retries += 1
            time.sleep(retry_interval)
    
    trade_logger.error("Max retries reached. Transaction confirmation failed.")
    return None
