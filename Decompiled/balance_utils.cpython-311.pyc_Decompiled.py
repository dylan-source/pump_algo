# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: /Users/dylanmartens/Documents/Coding/Pump sniping/Feb_03/balance_utils.py
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2025-01-29 07:50:21 UTC (1738137021)

import asyncio
import datetime
import json
import base58
import aiohttp
import requests
from solders.signature import Signature
from solders.pubkey import Pubkey
from solana.rpc.types import TokenAccountOpts
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed, Confirmed, Finalized
from config import SOL_MINT, SOL_DECIMALS, trade_logger, RPC_URL, WALLET_ADDRESS

async def get_transaction_details(rpc_client, signature, wallet_address: str, input_mint: str, output_mint: str):

    def find_token_balance_from_tx_hash(token_balances, mint, owner):
        for t in token_balances:
            if t['mint'] == mint and t.get('owner') == owner:
                return float(t['uiTokenAmount']['uiAmountString'])
        else:
            return 0.0
    status = await rpc_client.get_transaction(signature, 'json', commitment=Confirmed, max_supported_transaction_version=0)
    transaction_json = status.to_json()
    data = json.loads(transaction_json)
    if data['result'] is None:
        trade_logger.error(f'Error fetching transaction details for Signature: {signature} - inputMint: {input_mint} and outputMint: {output_mint}0')
        return
    timestamp = data['result']['blockTime']
    meta = data['result']['meta']
    pre_balances = meta['preBalances']
    post_balances = meta['postBalances']
    pre_token_balances = meta.get('preTokenBalances', [])
    post_token_balances = meta.get('postTokenBalances', [])
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
    dt_object = datetime.datetime.fromtimestamp(timestamp)
    formatted_datetime = dt_object.strftime('%Y-%m-%d %H:%M:%S')
    return {'timestamp': formatted_datetime, 'inputMint_diff': token_in_diff, 'outputMint_diff': token_out_diff}

async def get_token_balance(rpc_client: AsyncClient, wallet_address: str, token_mint_address: str) -> int:
    """
    Get the balance of a specific token in a wallet on the Solana blockchain.

    Args:
        wallet_address (str): The wallet address (public key) as a string.
        token_mint_address (str): The token mint address as a string.

    Returns:
        float: The balance of the token in the wallet.
    """
    wallet_pubkey = Pubkey.from_string(wallet_address)
    token_mint_pubkey = Pubkey.from_string(token_mint_address)
    token_accounts = await rpc_client.get_token_accounts_by_owner_json_parsed(wallet_pubkey, TokenAccountOpts(mint=token_mint_pubkey))
    if not token_accounts.value:
        return 0.0
    token_account_info = token_accounts.value[0].account.data.parsed['info']
    token_balance = token_account_info['tokenAmount']['amount']
    trade_logger.info(f'Token balance for {token_mint_address}: {token_balance}0')
    return token_balance