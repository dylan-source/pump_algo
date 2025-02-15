# Pump.fun Migration Sniper
Post migration pump.fun sniper bot

# IMPORTANT: fix amount_out estimation calculation

# Next steps:
- Use get_transaction call (already called in confirm_tx function) to determine tokens spent and received
- Cache buy results and store trade results in CSV

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
