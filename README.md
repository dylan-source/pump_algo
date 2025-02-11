# Pump.fun Migration Sniper
Post migration pump.fun sniper bot

To-do list:
1. Understand why it fails sometimes!
    - Sometimes the trade executes, but tokens received and confirmation are none. Code runs faster than propagation? Seems like this happens when chain is very slow
2. {'InstructionError': [6, 'ProgramFailedToComplete']} is due to trading not yet being available - I suspect. Loop until trading is avaiable or due to priority fees
3. Switch trading directly to raydium rather than Jupiter (jupiter has a time lag after migration and also extra fees)

Use DexScreener for prices?
1. Increase buy slippage max if price is increasing (and vice verse for selling)?
2. Endpoint to get prices: https://api.dexscreener.com/latest/dex/pairs/{chainId}/{pairId}


Completed:
1. What to do when confirm_result is None - implementation: loop and try again
2. Create loop for when buy slippage is exceeded or "when Unable to confirm transaction ..." error is received - implementation: loop until max slippage is reached

Not critical:
1. In execute_swap function, should I filter for multiple routes - currently defauls to first route - reason: pump.fun tokens only have a single raydium route

Other packages to look into:
 - UV Loop
 - AIOjobs
 - anyio
 - tenacity



Some other filters:
- Some filters from PepeBoost bot
- 150+ holders
- 50+ replies/comments
- No holder with more than 6%
- Time to KOH (king of the hill) 5 minutes +
- Red flag if 100% raydium reach
- Red flag if 100% KOH
- DEX paid
