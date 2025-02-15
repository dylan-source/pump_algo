import json
import asyncio
from solana.rpc.commitment import Processed, Confirmed, Finalized
from solana.rpc.types import TokenAccountOpts
from solders.signature import Signature #type: ignore
from solders.pubkey import Pubkey  # type: ignore
from raydium.constants import TOKEN_PROGRAM_ID
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

async def confirm_txn(txn_sig: Signature, max_retries: int = 15, retry_interval: int = 3) -> bool:    
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
                return True
            
            # trade_logger.error("Error: Transaction not confirmed. Retrying...")
            error = txn_json['err']
            if error:
                trade_logger.error(f"Transaction failed...{error}")     # {'InstructionError': [4, {'Custom': 30}]}
                
                print("\nERROR TYPE IN CONFIRM_TX FUNCTION")
                print(error)
                print(type(error))
                print("\n\n")
                
                next_level = error["err"]
                print("\nNEXT ERROR LEVEL IN CONFIRM_TX FUNCTION")
                print(next_level)
                print(type(next_level))
                print("\n\n")
                
                return error
        except Exception as e:
            trade_logger.info(f"Awaiting confirmation... try count: {retries}")
            retries += 1
            await asyncio.sleep(retry_interval)
    
    trade_logger.error("Max retries reached. Transaction confirmation failed.")
    return None


