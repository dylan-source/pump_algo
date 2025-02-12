# Pump.fun Migration Sniper
Post migration pump.fun sniper bot

# To-do list:
1. Understand why it fails sometimes!
    - Sometimes the trade executes, but tokens received and confirmation are none. Code runs faster than propagation? Seems like this happens when chain is very slow
2. {'InstructionError': [6, 'ProgramFailedToComplete']} is due to trading not yet being available - I suspect. Loop until trading is avaiable or due to priority fees
3. Switch trading directly to raydium rather than Jupiter (jupiter has a time lag after migration and also extra fees)
4. Consider adding additional priority fee values to get_recent_prioritization_fees and in the lists for escalating trades (currently stops at 75th percentile)
5. Look into package to handle rate limits (specifically for jupiter's price api calls)
6. Increase buy slippage max if price is increasing (and vice verse for selling)?
7. Looking into DexScreener prices - the price at migration is always 0.0004108, yet I don't get this value when I recalculate it

# Price feeds:
 - Codex.io is the fastest and most accurate in real-time
 - DexScreener has best rate limit but is incredibly slow
 - Jupiter's feed is a bit delayed and somewhat accurate
 - Overall - Codex is best, but most expensive ($350 per month) and free plan is too limited for use

# Not critical:
1. In execute_swap function, filter for multiple routes, currently defauls to first route - not critical reason: pump.fun tokens only have a single raydium route

# Completed:
1. What to do when confirm_result is None - implementation: loop and try again
2. Create loop for when buy slippage is exceeded or "when Unable to confirm transaction ..." error is received - implementation: loop until max slippage is reached
3. When stoploss is triggered use a higher priority fee and slippage values - implementation: done using additional config parameters
4. Use DexScreener for prices - implementation: done, fetching the priceNative (token_price/sol) value

# Other packages to look into:
 - UV Loop
 - AIOjobs
 - anyio
 - tenacity

# Some other filters:
- Some filters from PepeBoost bot
- 150+ holders
- 50+ replies/comments
- No holder with more than 6%
- Time to KOH (king of the hill) 5 minutes +
- Red flag if 100% raydium reach
- Red flag if 100% KOH
- DEX paid
