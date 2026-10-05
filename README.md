# Crypto-IVN-Bot

A systematic, quantitative algorithmic trading bot applying Inner Circle Trader (ICT) concepts to the cryptocurrency markets.

## Architecture

This bot is built on a strict out-of-sample validation methodology.

- `config/`: The single source of truth for parameter settings. Live and backtest environments read from here to guarantee parity.
- `data/`: Local storage for 1-minute OHLCV historical data.
- `backtest/`: Multi-objective walk-forward optimization engine.
- `live/`: CCXT-based asynchronous execution loop.
- `docs/`: Master project plans and SOPs.
- `reference/`: Legacy futures bot logic being ported to crypto decimals.

## Methodology
- **Train Set:** 65% chronological data (optimization).
- **Test Set:** 35% recent data (locked until final out-of-sample verification).
- **Fitness Function:** Ranks by Net PnL, Max Drawdown, Trade Frequency, and Profit Velocity.
