# pump_sniper
Post migration pump.fun sniper bot

To-do list:
1. Look into changing the listener websocket event from logSubscribe to perhaps accountSubscribe. I suspect that some trades are not included in the logs and are there not picked up by the code (https://www.quicknode.com/docs/solana/logsSubscribe)
2. Use the Anchor IDL to decode the websocket response to improve stability of the instruction decoding
3. In execute_swap function, determine if I should filter for multiple routes - currently defauls to first route
4. Add additional route logging for when a swap route is found
5. Figure out how to get token name and symbol
6. Understand why it fails sometimes!
    - Sometimes it appears to have executed (and I get a signature) but nothing happened. Issues with the route? Preflight fail?
    - Sometimes the trade executes, but tokens received and confirmation are none. Code runs faster than propagation? Seems like this happens when chain is very slow


Considerations:
1. Subscribe to accountSubscribe events to track changes in my wallet for when trades happen. Is this more performant than HTTP calls?


Some other filters:
- Some filters for PepeBoost bot
- 150+ holders
- 50+ replies/comments
- No holder with more than 6%
- Time to KOH (king of the hill) 5 minutes +
- Red flag if 100% raydium reach
- Red flag if 100% KOH
- DEX paid
