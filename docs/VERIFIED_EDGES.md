# Verified Crypto Edges (Master Discovery Results)

These configurations were trained on 65% of the 3-year data. They were then forced through the blind 35% Out-of-Sample test. 

Only configurations that maintained a positive Net PnL and kept their Max Drawdown strictly under 20% on the **unseen data** were allowed onto this list.

| Coin | Timeframe | Risk/Reward | Lookback | Train WinRate | Test WinRate | Test PnL (on $1k) | Test Max DD | Total Trades |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SOL** | 4h | 1.5 | 20 | 59.2% | **56.5%** | **+$87.07** | 5.08% | 72 |
| **BNB** | 4h | 2.0 | 40 | 43.2% | **47.1%** | **+$62.54** | 4.13% | 61 |
| **DOGE**| 4h | 3.0 | 20 | 37.8% | **33.3%** | **+$51.07** | 5.13% | 63 |
| **LTC** | 2h | 2.0 | 30 | 37.2% | **38.2%** | **+$22.52** | 6.32% | 112 |
| **XRP** | 2h | 1.5 | 30 | 54.0% | **44.4%** | **+$22.07** | 9.44% | 126 |
| **ETH** | 4h | 3.0 | 40 | 39.5% | **50.0%** | **+$19.01** | 1.05% | 40 |
| **LINK**| 2h | 1.0 | 20 | 58.0% | **53.8%** | **+$12.22** | 8.50% | 209 |
| **BTC** | 2h | 1.5 | 30 | 51.0% | **44.4%** | **+$8.79** | 9.19% | 167 |
| **AVAX**| 4h | 3.0 | 20 | 40.0% | **26.7%** | **+$2.49** | 4.27% | 50 |

---

### 🛑 FAILED ASSET: Cardano (ADA)
The pipeline completely rejected Cardano. It ground through all top configurations from the training set, and every single one of them failed to produce a profitable edge in the Out-of-Sample test. 

**Conclusion:** ADA does not mathematically respect this specific ICT structural pattern enough to overcome exchange fees. We will absolutely not trade it.
