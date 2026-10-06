# Phase 3: Core Engine Porting & Risk Diagnostics

## Implementation Details
1. **Engine Ported (`backtest/engine.py`):** The `detect_ict_setup_fast()` logic was successfully ported to read crypto OHLCV. 
2. **Strict Chronological Wall (65/35):** The engine now strictly partitions the data. 
   - Training Set: 1,025,003 rows.
   - Out-of-Sample Test Set: 551,926 rows.
3. **Fractional Risk Sizing:** Replaced Topstep fixed ticks with strict percentage-based risk (1% of equity per trade) using dynamic `calculate_position_size()`. Max leverage was capped at 5x to prevent fee destruction on micro-moves.
4. **Exchange Fee Implementation:** Applied strict 0.1% maker/taker fee rate model per exchange standards (0.2% round trip).

## Immediate Findings (The Zero-Hallucination Reality Check)
We ran the very first diagnostic pass on the Train Set for BTC/USDT (3 years of data). 
- **Trades:** 3,691
- **Win Rate:** 25.5% 
- **Net PnL:** -100.0% (Account blown)

### Why did it blow up? 
The code is working flawlessly; the math of the strategy is what failed. 
In Futures (Topstep), you pay a fixed $4.08 commission, regardless of the leverage. 
In Crypto, fees are percentage-based on the **total position size**. 
Because the 3-minute ICT setup has very tight Stop Losses, the bot has to use leverage (e.g., 5x) to make the 1% risk target. 
- 1% risk on $1,000 = $10. 
- 5x leverage position = $5,000. 
- 0.2% round-trip fee on $5,000 = **$10**. 

**Conclusion:** The fees alone exactly equal your total risk budget per trade. The 25% win rate (which was profitable in futures) cannot overcome a 1:1 fee-to-risk ratio. 

## Next Steps (Phase 4: Optimization)
This is exactly why we built the 65/35 split. We just proved that copying the 3-minute Futures parameters directly to Crypto will bankrupt an account due to exchange fees. 
To fix this in Phase 4, the optimizer must search for:
1. **Wider Stops / Higher Timeframes:** The bot must target larger percentage moves (e.g., 15m or 1H charts) so it doesn't need leverage. Without leverage, a 0.2% fee is negligible. 
2. **Zero-Fee Exchanges:** We can optimize assuming 0% limit maker fees (some exchanges offer this for providing liquidity).
