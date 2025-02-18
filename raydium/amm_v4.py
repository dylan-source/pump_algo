import base64
import os
from typing import Optional
from solana.rpc.commitment import Processed
from solana.rpc.types import TokenAccountOpts, TxOpts
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price  # type: ignore
from solders.message import MessageV0  # type: ignore
from solders.pubkey import Pubkey  # type: ignore
from solders.system_program import (
    CreateAccountWithSeedParams,
    create_account_with_seed,
)
from solders.transaction import VersionedTransaction  # type: ignore
# from spl.token.client import Token
from spl.token.async_client import AsyncToken
from spl.token.instructions import (
    CloseAccountParams,
    InitializeAccountParams,
    close_account,
    create_associated_token_account,
    get_associated_token_address,
    initialize_account,
)
from utils.common_utils import confirm_txn, get_token_balance
from utils.pool_utils import (
    AmmV4PoolKeys,
    fetch_amm_v4_pool_keys,
    get_amm_v4_reserves,
    make_amm_v4_swap_instruction
)
from config import client, payer_keypair, UNIT_BUDGET, trade_logger
from raydium.constants import ACCOUNT_LAYOUT_LEN, SOL_DECIMAL, TOKEN_PROGRAM_ID, WSOL


async def buy(pair_address:str, token_mint:str, sol_in:float=0.01, slippage:int=5, priority_fee:int=100_000):
    try:
        # trade_logger.info("Fetching pool keys...")
        pool_keys: Optional[AmmV4PoolKeys] = await fetch_amm_v4_pool_keys(pair_address)
        if pool_keys is None:
            trade_logger.error(f"No pool keys found for {pair_address}")
            return False, None, None
        # trade_logger.info("Pool keys fetched successfully.")

        mint = (pool_keys.base_mint if pool_keys.base_mint != WSOL else pool_keys.quote_mint)

        # trade_logger.info("Calculating transaction amounts...")
        amount_in = int(sol_in * SOL_DECIMAL)

        base_reserve, quote_reserve, token_decimal = await get_amm_v4_reserves(pool_keys)
        amount_out = sol_for_tokens(sol_in, base_reserve, quote_reserve)
        trade_logger.info(f"Estimated Amount Out: {int(amount_out*10**token_decimal)}")

        slippage_adjustment = 1 - (slippage / 100)
        amount_out_with_slippage = amount_out * slippage_adjustment
        minimum_amount_out = int(amount_out_with_slippage * 10**token_decimal)
        trade_logger.info(f"Amount In: {amount_in} | Minimum Amount Out: {minimum_amount_out}")

        # trade_logger.info("Checking for existing token account...")
        token_account_check = await client.get_token_accounts_by_owner(
            payer_keypair.pubkey(), TokenAccountOpts(mint), Processed
        )
        if token_account_check.value:
            token_account = token_account_check.value[0].pubkey
            create_token_account_instruction = None
            # trade_logger.info("Token account found.")
        else:
            token_account = get_associated_token_address(payer_keypair.pubkey(), mint)
            create_token_account_instruction = create_associated_token_account(
                payer_keypair.pubkey(), payer_keypair.pubkey(), mint
            )
            trade_logger.info("No existing token account found; creating associated token account.")

        # trade_logger.info("Generating seed for WSOL account...")
        seed = base64.urlsafe_b64encode(os.urandom(24)).decode("utf-8")
        wsol_token_account = Pubkey.create_with_seed(
            payer_keypair.pubkey(), seed, TOKEN_PROGRAM_ID
        )
        balance_needed = await AsyncToken.get_min_balance_rent_for_exempt_for_account(client)

        # trade_logger.info("Creating and initializing WSOL account...")
        create_wsol_account_instruction = create_account_with_seed(
            CreateAccountWithSeedParams(
                from_pubkey=payer_keypair.pubkey(),
                to_pubkey=wsol_token_account,
                base=payer_keypair.pubkey(),
                seed=seed,
                lamports=int(balance_needed + amount_in),
                space=ACCOUNT_LAYOUT_LEN,
                owner=TOKEN_PROGRAM_ID,
            )
        )

        init_wsol_account_instruction = initialize_account(
            InitializeAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=wsol_token_account,
                mint=WSOL,
                owner=payer_keypair.pubkey(),
            )
        )

        # trade_logger.info("Creating swap instructions...")
        swap_instruction = make_amm_v4_swap_instruction(
            amount_in=amount_in,
            minimum_amount_out=minimum_amount_out,
            token_account_in=wsol_token_account,
            token_account_out=token_account,
            accounts=pool_keys,
            owner=payer_keypair.pubkey(),
        )

        # trade_logger.info("Preparing to close WSOL account after swap...")
        close_wsol_account_instruction = close_account(
            CloseAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=wsol_token_account,
                dest=payer_keypair.pubkey(),
                owner=payer_keypair.pubkey(),
            )
        )

        instructions = [
            set_compute_unit_limit(UNIT_BUDGET),
            set_compute_unit_price(priority_fee),
            create_wsol_account_instruction,
            init_wsol_account_instruction,
        ]

        if create_token_account_instruction:
            instructions.append(create_token_account_instruction)

        instructions.append(swap_instruction)
        instructions.append(close_wsol_account_instruction)

        # trade_logger.info("Compiling transaction message...")
        latest_blockhash = await client.get_latest_blockhash()
        latest_blockhash = latest_blockhash.value.blockhash
        compiled_message = MessageV0.try_compile(
            payer_keypair.pubkey(),
            instructions,
            [],
            latest_blockhash,
        )
        
        trade_logger.info("Simulating buy transaction...")
        simulation_txn_sig = await client.simulate_transaction(
            txn=VersionedTransaction(compiled_message, [payer_keypair]),
            sig_verify=False,
            commitment=Processed
        )
        
        simulation_status = simulation_txn_sig.value.err
        if simulation_status is not None:
            error = simulation_status.err
            trade_logger.error(f"Simulation error - error code: {error} ")
            return error, None, None
        
        trade_logger.info("Sending transaction...")
        txn_sig = await client.send_transaction(
            txn=VersionedTransaction(compiled_message, [payer_keypair]),
            opts=TxOpts(skip_preflight=True),
        )
        txn_sig = txn_sig.value
        trade_logger.info(f"Transaction Signature: {txn_sig}")

        # trade_logger.info("Confirming transaction...")
        confirmed, trade_data = await confirm_txn(txn_sig, token_mint)
        if confirmed is True:
            trade_data["buy_transaction_hash"] = str(txn_sig)
        return confirmed, trade_data, quote_reserve/base_reserve

    except Exception as e:
        trade_logger.error(f"Error occurred during buy transaction: {e}")
        return None, None, None

async def sell(pair_address:str, token_mint:str, percentage:int=100, slippage:int=5, priority_fee:int=100_000):
    try:
        if not (1 <= percentage <= 100):
            trade_logger.error("Percentage must be between 1 and 100.")
            return False, None

        # trade_logger.info("Fetching pool keys...")
        pool_keys: Optional[AmmV4PoolKeys] = await fetch_amm_v4_pool_keys(pair_address)
        if pool_keys is None:
            trade_logger.error("No pool keys found...")
            return False, None
        
        mint = (pool_keys.base_mint if pool_keys.base_mint != WSOL else pool_keys.quote_mint)

        # trade_logger.info("Retrieving token balance...")
        token_balance = await get_token_balance(str(mint))
        trade_logger.info(f"Wallet balance: {token_balance}")

        if token_balance == 0 or token_balance is None:
            trade_logger.error("No tokens available to sell.")
            return False, None

        token_balance = token_balance * (percentage / 100)
        # trade_logger.info(f"Selling {percentage}% of the token balance, adjusted balance: {token_balance}")

        # trade_logger.info("Calculating transaction amounts...")
        base_reserve, quote_reserve, token_decimal = await get_amm_v4_reserves(pool_keys)
        amount_out = tokens_for_sol(token_balance, base_reserve, quote_reserve)
        trade_logger.info(f"Estimated Amount Out: {int(amount_out * SOL_DECIMAL)}")

        slippage_adjustment = 1 - (slippage / 100)
        amount_out_with_slippage = amount_out * slippage_adjustment
        minimum_amount_out = int(amount_out_with_slippage * SOL_DECIMAL)

        amount_in = int(token_balance * 10**token_decimal)
        trade_logger.info(f"Amount In: {amount_in} | Minimum Amount Out: {minimum_amount_out}")
        token_account = get_associated_token_address(payer_keypair.pubkey(), mint)

        # trade_logger.info("Generating seed and creating WSOL account...")
        seed = base64.urlsafe_b64encode(os.urandom(24)).decode("utf-8")
        wsol_token_account = Pubkey.create_with_seed(
            payer_keypair.pubkey(), seed, TOKEN_PROGRAM_ID
        )
        balance_needed = await AsyncToken.get_min_balance_rent_for_exempt_for_account(client)

        create_wsol_account_instruction = create_account_with_seed(
            CreateAccountWithSeedParams(
                from_pubkey=payer_keypair.pubkey(),
                to_pubkey=wsol_token_account,
                base=payer_keypair.pubkey(),
                seed=seed,
                lamports=int(balance_needed),
                space=ACCOUNT_LAYOUT_LEN,
                owner=TOKEN_PROGRAM_ID,
            )
        )

        init_wsol_account_instruction = initialize_account(
            InitializeAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=wsol_token_account,
                mint=WSOL,
                owner=payer_keypair.pubkey(),
            )
        )

        # trade_logger.info("Creating swap instructions...")
        swap_instructions = make_amm_v4_swap_instruction(
            amount_in=amount_in,
            minimum_amount_out=minimum_amount_out,
            token_account_in=token_account,
            token_account_out=wsol_token_account,
            accounts=pool_keys,
            owner=payer_keypair.pubkey(),
        )

        # trade_logger.info("Preparing to close WSOL account after swap...")
        close_wsol_account_instruction = close_account(
            CloseAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=wsol_token_account,
                dest=payer_keypair.pubkey(),
                owner=payer_keypair.pubkey(),
            )
        )

        instructions = [
            set_compute_unit_limit(UNIT_BUDGET),
            set_compute_unit_price(priority_fee),
            create_wsol_account_instruction,
            init_wsol_account_instruction,
            swap_instructions,
            close_wsol_account_instruction,
        ]

        if percentage == 100:
            # trade_logger.info("Preparing to close token account after swap...")
            close_token_account_instruction = close_account(
                CloseAccountParams(
                    program_id=TOKEN_PROGRAM_ID,
                    account=token_account,
                    dest=payer_keypair.pubkey(),
                    owner=payer_keypair.pubkey(),
                )
            )
            instructions.append(close_token_account_instruction)

        # trade_logger.info("Compiling transaction message...")
        
        latest_blockhash = await client.get_latest_blockhash()
        latest_blockhash = latest_blockhash.value.blockhash
        compiled_message = MessageV0.try_compile(
            payer_keypair.pubkey(),
            instructions,
            [],
            latest_blockhash,
        )

        trade_logger.info("Simulating sell transaction...")
        simulation_txn_sig = await client.simulate_transaction(
            txn=VersionedTransaction(compiled_message, [payer_keypair]),
            sig_verify=False,
            commitment=Processed
        )
        
        simulation_status = simulation_txn_sig.value.err
        if simulation_status is not None:
            error = simulation_status.err
            trade_logger.error(f"Simulation error - error code: {error} ")
            return error, None
        # return False
    
        trade_logger.info("Sending transaction...")
        txn_sig = await client.send_transaction(
            txn=VersionedTransaction(compiled_message, [payer_keypair]),
            opts=TxOpts(skip_preflight=True),
        )
        txn_sig = txn_sig.value
        trade_logger.info(f"Transaction Signature: {txn_sig}")

        # trade_logger.info("Confirming transaction...")
        confirmed, trade_data = await confirm_txn(txn_sig, token_mint)
        if confirmed is True:
            trade_data["sell_transaction_hash"] = str(txn_sig)
        return confirmed, trade_data

    except Exception as e:
        trade_logger.error(f"Error occurred during sell transaction: {e}")
        return None, None

def sol_for_tokens(sol_amount, base_vault_balance, quote_vault_balance, swap_fee=0.25):
    effective_sol_used = sol_amount - (sol_amount * (swap_fee / 100))
    constant_product = base_vault_balance * quote_vault_balance
    updated_base_vault_balance = constant_product / (quote_vault_balance + effective_sol_used)
    tokens_received = base_vault_balance - updated_base_vault_balance
    return round(tokens_received, 9)

def tokens_for_sol(token_amount, base_vault_balance, quote_vault_balance, swap_fee=0.25):
    effective_tokens_sold = token_amount * (1 - (swap_fee / 100))
    constant_product = base_vault_balance * quote_vault_balance
    updated_quote_vault_balance = constant_product / (base_vault_balance + effective_tokens_sold)
    sol_received = quote_vault_balance - updated_quote_vault_balance
    return round(sol_received, 9)


