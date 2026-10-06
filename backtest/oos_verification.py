import sys
import os
import copy

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.engine import run_backtest, load_config

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

def verify_oos():
    base_config = load_config()
    
    print("\n" + "="*60)
    print("FINAL OUT-OF-SAMPLE VERIFICATION (LOCKED 35% TEST SET)")
    print("="*60)
    
    # --- Config 1: 4H SOL Swing ---
    cfg1 = copy.deepcopy(base_config)
    cfg1['ict_parameters']['RR_RATIO'] = 1.5
    cfg1['ict_parameters']['LOOKBACK_BARS'] = 20
    
    csv_sol = os.path.join(DATA_DIR, "SOL_USDT_3yr.csv")
    
    print("\n[ARCHETYPE 1: HIGH PROBABILITY SWING]")
    print("Asset: SOL | Timeframe: 4H | RR: 1.5 | Lookback: 20")
    # We must mock the resampling to 4H since run_backtest resamples to 3m by default.
    # Actually, run_backtest hardcodes the resample to 3m inside the engine!
    # I need to temporarily adjust engine.py to accept timeframe as a parameter, 
    # but for now I will just rewrite the evaluation here to guarantee accurate OOS testing.
    pass

# To avoid modifying engine.py repeatedly, I will use the evaluate_combination 
# function from optimizer.py which already handles timeframes dynamically.

from backtest.optimizer import evaluate_combination

def run_oos_strict():
    print("\n" + "="*60)
    print("FINAL OUT-OF-SAMPLE VERIFICATION (LOCKED 35% TEST SET)")
    print("="*60)
    
    # To run OOS, we need to modify evaluate_combination to use the Test split.
    import pandas as pd
    from core.ict_logic import detect_ict_setup_fast
    
    def oos_eval(coin, tf, rr, lb):
        csv_path = os.path.join(DATA_DIR, f"{coin}_USDT_3yr.csv")
        df = pd.read_csv(csv_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        # 35% TEST SPLIT (THE LOCKED DATA)
        split_idx = int(len(df) * 0.65)
        df = df.iloc[split_idx:]
        
        df_tf = df.resample(tf).agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
        
        prev = df_tf['close'].shift(1)
        tr = pd.concat([df_tf['high']-df_tf['low'], (df_tf['high']-prev).abs(), (df_tf['low']-prev).abs()], axis=1).max(axis=1)
        df_tf['atr'] = tr.rolling(14).mean().bfill()
        
        df_tf.reset_index(inplace=True)
        bars = df_tf.to_dict('records')
        
        balance = 1000.0
        peak = balance
        max_dd_pct = 0.0
        wins, losses = 0, 0
        pos = None
        
        ict_params = {'MIN_RISK_ATR_MULTIPLIER': 0.5, 'MAX_RISK_ATR_MULTIPLIER': 5.0, 'MIN_FVG_ATR_MULTIPLIER': 0.5}
        
        def calc_size(eq, r_pct, ep, sl, max_lev=5):
            risk = eq * r_pct
            pr = abs(ep - sl)
            if pr == 0: return 0
            sz = risk / pr
            if (sz * ep) > (eq * max_lev): sz = (eq * max_lev) / ep
            return sz
            
        for i in range(lb, len(bars)):
            if balance <= 0: break
            b = bars[i]
            if pos:
                h, l = b['high'], b['low']
                closed = False
                pnl = 0.0
                if pos['side'] == 'buy':
                    if l <= pos['sl']: closed=True; exit_price=pos['sl']; pnl=(exit_price-pos['entry'])*pos['size']; losses+=1
                    elif h >= pos['tp']: closed=True; exit_price=pos['tp']; pnl=(exit_price-pos['entry'])*pos['size']; wins+=1
                else:
                    if h >= pos['sl']: closed=True; exit_price=pos['sl']; pnl=(pos['entry']-exit_price)*pos['size']; losses+=1
                    elif l <= pos['tp']: closed=True; exit_price=pos['tp']; pnl=(pos['entry']-exit_price)*pos['size']; wins+=1
                if closed:
                    balance += (pnl - ((exit_price * pos['size']) * 0.001))
                    if balance > peak: peak = balance
                    dd = (peak - balance) / peak
                    if dd > max_dd_pct: max_dd_pct = dd
                    pos = None
            else:
                setup = detect_ict_setup_fast(bars[i-lb:i+1], ict_params, None)
                if setup:
                    ep = b['close']
                    rp = setup['risk_points']
                    if setup['side'] == 'buy': sl=ep-rp; tp=ep+(rp*rr)
                    else: sl=ep+rp; tp=ep-(rp*rr)
                    sz = calc_size(balance, 0.01, ep, sl)
                    if sz > 0:
                        balance -= ((ep * sz) * 0.001)
                        pos = {'side': setup['side'], 'entry': ep, 'sl': sl, 'tp': tp, 'size': sz}
                        
        tot = wins + losses
        wr = (wins/tot)*100 if tot > 0 else 0
        print(f"Results: {tot} Trades | WinRate: {wr:.1f}% | Net PnL: ${balance-1000:.2f} | Max DD: {max_dd_pct*100:.2f}%")

    print("\n[ARCHETYPE 1: 4H High-Probability Swing] -> SOL, RR 1.5, Lookback 20")
    oos_eval('SOL', '4h', 1.5, 20)
    
    print("\n[ARCHETYPE 2: 1H Trend Runner] -> ETH, RR 3.0, Lookback 20")
    oos_eval('ETH', '1h', 3.0, 20)
    
    print("\n[ARCHETYPE 3: 1H Trend Runner] -> SOL, RR 3.0, Lookback 20")
    oos_eval('SOL', '1h', 3.0, 20)

if __name__ == "__main__":
    run_oos_strict()
