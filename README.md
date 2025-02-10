# Pump.fun Migration Sniper
Post migration pump.fun sniper bot

To-do list:
1. In execute_swap function, determine if I should filter for multiple routes - currently defauls to first route
2. Understand why it fails sometimes!
    - Sometimes the trade executes, but tokens received and confirmation are none. Code runs faster than propagation? Seems like this happens when chain is very slow
3. Create loop for when buy slippage is exceeded or "when Unable to confirm transaction ..." error is received
4. {'InstructionError': [6, 'ProgramFailedToComplete']} is due to trading not yet being available - I suspect. Loop until trading is avaiable
5. Switch trading directly to raydium rather than Jupiter (jupiter has a time lag after migration and also extra fees)
6. Look into using UV Loop (or aiojobs/anyio) to handle async operations (apparently it's more efficient at I/O than asyncio)
7. What to do when confirm_result is None (this occurs when swapTransaction returns None) - loop and try again?
8. Increase buy slippage max if price is increasing
9. DexScreener endpoint to get prices https://api.dexscreener.com/latest/dex/pairs/{chainId}/{pairId}




Some other filters:
- Some filters from PepeBoost bot
- 150+ holders
- 50+ replies/comments
- No holder with more than 6%
- Time to KOH (king of the hill) 5 minutes +
- Red flag if 100% raydium reach
- Red flag if 100% KOH
- DEX paid
