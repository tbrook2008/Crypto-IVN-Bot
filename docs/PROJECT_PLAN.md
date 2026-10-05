# Crypto-IVN-Bot Master Plan

## 🎯 Core Directive
Adapt the proven ICT execution engine to the Crypto markets using a strict, zero-hallucination quantitative methodology. All backtest logic must have 1:1 parity with live execution logic. All code changes follow the 7-Step SOP.

---

## Phase 1: Foundation & Version Control
1. **Repository Setup:** Initialize a clean local directory and link it to `https://github.com/tbrook2008/Crypto-IVN-Bot`.
2. **Architecture Scaffold:** Create strict separation between `data/`, `backtest/`, `live/`, and `config/`.
3. **Config Unification:** Build a single `config.json` that both the backtester and live trader consume. **Rule:** If a parameter is not in this file, it cannot be traded or tested.

## Phase 2: Data Engineering & Strict Splitting
1. **Asset Selection:** Identify 10-15 highly liquid major/minor cryptos (e.g., BTC, ETH, SOL, AVAX, LINK).
2. **Data Ingestion:** Download exactly 3 years of 1-minute OHLCV data using Binance/CCXT public APIs.
3. **The 65/35 Split:**
   - **Train Set (65%):** ~23.4 months of chronological data. Used exclusively for parameter optimization.
   - **Test Set (35%):** ~12.6 months of recent data. Locked away. The bot will only see this data *once* to verify the edge.

## Phase 3: Core Engine Porting & Risk Management
1. **Engine Porting:** Port `detect_ict_setup_fast()` to read crypto decimals correctly.
2. **Risk Management Translation:** Carry over the Topstep risk logic. Instead of fixed point stops, adapt to percentage-based position sizing (e.g., risk exactly 1% of account balance per trade based on SL distance).
3. **Fee Modeling:** Hardcode conservative crypto exchange fees (0.1% maker/taker) into the backtest engine to ensure realistic PnL.

## Phase 4: Multi-Objective Optimization
1. **Grid Search (Train Set Only):** Run a massive parameter grid on the 65% Train Set.
2. **The Fitness Function:** Score combinations using a weighted formula:
   - Highest Net PnL
   - Lowest Max Drawdown
   - Highest Trade Frequency (Law of Large Numbers)
   - Profit Velocity (Derivative of PnL over time - avoiding stagnation periods)
3. **Out-of-Sample Verification:** Take the absolute best config from the Train Set and run it exactly *once* on the 35% Test Set. If it fails, the strategy is scrapped. If it passes, we deploy.

## Phase 5: Live Trading Architecture
1. **Broker Integration:** Integrate `ccxt` for universal exchange connectivity (Kraken/Coinbase).
2. **Execution Loop:** Build the asynchronous execution loop that directly references `config.json`.
3. **Paper Trading:** Run live for 1 week in a simulated/paper environment to guarantee backtest/live parity.

---

## 🛑 The 7-Step SOP (Mandatory for ALL Updates)
Before any `git commit` or `git push` to the Crypto-IVN-Bot repo, the AI must output this checklist:
1. **Test Logic:** Local script run to verify specific function.
2. **Regression Test:** Verified no other systems broke.
3. **Backtest:** Verified no negative impact on strategy edge.
4. **Documentation:** Updated README/comments.
5. **Compile Check:** `python -m py_compile <file.py>` passed.
6. **User Approval:** Explicitly requested "Yes" from the user.
7. **Publish:** Push executed only after approval.
