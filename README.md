# Pump.fun Migration Sniper
Post migration pump.fun sniper bot

To-do list:
1. In execute_swap function, determine if I should filter for multiple routes - currently defauls to first route
2. Understand why it fails sometimes!
    - Sometimes the trade executes, but tokens received and confirmation are none. Code runs faster than propagation? Seems like this happens when chain is very slow

Some other filters:
- Some filters from PepeBoost bot
- 150+ holders
- 50+ replies/comments
- No holder with more than 6%
- Time to KOH (king of the hill) 5 minutes +
- Red flag if 100% raydium reach
- Red flag if 100% KOH
- DEX paid
