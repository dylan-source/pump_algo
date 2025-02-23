# Pump.fun Migration Sniper
Post migration pump.fun sniper bot

# New listener
- This new branch listens to the pump.fun "withdraw" instruction
- Thereafter it processes filters
- If passes filters it listens to the relevant initialize2 instruction

# CONCERNS TO ADDRESS (ChatGPT feedback on new listener trade logic):
- Trade Logic in a Separate Task:
You mentioned that the trade logic is already housed in its own task using asyncio.create_task(). That’s a good approach. Just ensure that your tasks are properly managed (e.g. cancellations on shutdown) and that shared state (if any) is protected.
Minimal Blocking in the Listener:
Ensure that any heavy processing (risk checks, API calls) inside tasks is also done asynchronously. Use asynchronous HTTP libraries (like aiohttp) for any API calls.

# Items to note
- pool_utils has been updated to use quicknode RPC to avoid helius rate limit with getting prices (qn_client used rather than client)

# Speed improvements
- Call await client.get_token_accounts_by_owner once at instantiation
- The associated token addresses will always be new. Therefore always derive them
- This call should also always be the same: await AsyncToken.get_min_balance_rent_for_exempt_for_account(client)
- Can also potentially remove the tx simulation
- Change blockSubscribe commitment level to Processed

# IMPORTANT: fix amount_out estimation calculation
- Current the code swaps the Quote and Base reverse values around
- But then corrects the error in the sol_for_tokens and tokens_for_sol functions

# To-do list:
- Change startup sell to raydium 
- Consider adding additional priority fee values to get_recent_prioritization_fees and in the lists for escalating trades (currently stops at 75th percentile)
- Increase buy slippage max if price is increasing (and vice verse for selling)?
- Implement stoploss mechanism
- Look into package to handle rate limits (specifically for jupiter's price api calls)

# Not critical:

# Completed:
1. What to do when confirm_result is None - implementation: loop and try again
2. Create loop for when buy slippage is exceeded or "when Unable to confirm transaction ..." error is received - implementation: loop until max slippage is reached
3. When stoploss is triggered use a higher priority fee and slippage values - implementation: done using additional config parameters
4. Use DexScreener for prices - implementation: done, fetching the priceNative (token_price/sol) value - DexScreener prices very slow. Jupiter is ok. Codex.io is best
5. Switch trading directly to raydium rather than Jupiter (jupiter has a time lag after migration and also extra fees) - done: raydium swap integrated
6. Use get_transaction call (already called in confirm_tx function) to determine tokens spent and received
7. Cache buy results and store trade results in CSV

# Other packages to look into:
 - UV Loop
 - AIOjobs
 - anyio
 - tenacity -> retries when HTTP calls drop

# Some other filters:
- Some filters from PepeBoost bot
- 150+ holders
- 50+ replies/comments
- No holder with more than 6%
- Time to KOH (king of the hill) 5 minutes +
- Red flag if 100% raydium reach
- Red flag if 100% KOH
- DEX paid
