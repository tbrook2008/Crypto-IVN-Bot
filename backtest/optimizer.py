import pandas as pd
import json
import sys
import os
import itertools
from multiprocessing import Pool, cpu_count
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ict_logic import detect_ict_setup_fast

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'config.json')

# Grid Search Parameters
TIMEFRAMES = ['15min', '1h', '4h']
RR_RATIOS = [1.5, 2.0, 3.0, 4.0]
LOOKBACKS = [15, 20, 30]
COINS = ['BTC', 'ETH', 'SOL'] # Subset for speed, can expand later

def calculate_position_size(equity, risk_pct, entry_price, sl_price, fee_rate, max_leverage=5):
    risk_amount = equity * risk_pct
    price_risk = abs(entry_price - sl_price)
    if price_risk == 0: return 0
    size = risk_amount / price_risk
    max_position_value = equity * max_leverage
    if (size * entry_price) > max_position_value:
        size = max_position_value / entry_price
    return size

def evaluate_combination(args):
    coin, tf, rr, lb = args
    csv_path = os.path.join(DATA_DIR, f"{coin}_USDT_3yr.csv")
    if not os.path.exists(csv_path):
        return None
        
    # 1. Load Data
    df = pd.read_csv(csv_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)
    
    # 2. Strict 65% Train Split
    split_idx = int(len(df) * 0.65)
    df = df.iloc[:split_idx]
    
    # 3. Resample Timeframe
    df_tf = df.resample(tf).agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
    
    # 4. Calculate ATR
    prev = df_tf['close'].shift(1)
    tr = pd.concat([
        df_tf['high'] - df_tf['low'],
        (df_tf['high'] - prev).abs(),
        (df_tf['low'] - prev).abs()
    ], axis=1).max(axis=1)
    df_tf['atr'] = tr.rolling(14).mean().bfill()
    
    df_tf.reset_index(inplace=True)
    bars = df_tf.to_dict('records')
    
    # Fixed Params
    fee_rate = 0.001
    risk_pct = 0.01
    ict_params = {
        'MIN_RISK_ATR_MULTIPLIER': 0.5,
        'MAX_RISK_ATR_MULTIPLIER': 5.0,
        'MIN_FVG_ATR_MULTIPLIER': 0.5,
    }
    
    balance = 1000.0
    peak = balance
    max_dd_pct = 0.0
    wins, losses = 0, 0
    pos = None
    
    for i in range(lb, len(bars)):
        if balance <= 0:
            break
            
        b = bars[i]
        
        if pos:
            h, l = b['high'], b['low']
            closed = False
            pnl = 0.0
            
            if pos['side'] == 'buy':
                if l <= pos['sl']:
                    closed = True; exit_price = pos['sl']; pnl = (exit_price - pos['entry']) * pos['size']; losses += 1
                elif h >= pos['tp']:
                    closed = True; exit_price = pos['tp']; pnl = (exit_price - pos['entry']) * pos['size']; wins += 1
            else:
                if h >= pos['sl']:
                    closed = True; exit_price = pos['sl']; pnl = (pos['entry'] - exit_price) * pos['size']; losses += 1
                elif l <= pos['tp']:
                    closed = True; exit_price = pos['tp']; pnl = (pos['entry'] - exit_price) * pos['size']; wins += 1
                    
            if closed:
                fee = (exit_price * pos['size']) * fee_rate
                balance += (pnl - fee)
                if balance > peak: peak = balance
                dd_pct = (peak - balance) / peak
                if dd_pct > max_dd_pct: max_dd_pct = dd_pct
                pos = None
                
        else:
            window = bars[i-lb : i+1]
            setup = detect_ict_setup_fast(window, ict_params, htf_bias=None)
            
            if setup:
                risk_points = setup['risk_points']
                entry_price = b['close']
                
                if setup['side'] == 'buy':
                    sl = entry_price - risk_points; tp = entry_price + (risk_points * rr)
                else:
                    sl = entry_price + risk_points; tp = entry_price - (risk_points * rr)
                    
                size = calculate_position_size(balance, risk_pct, entry_price, sl, fee_rate, max_leverage=5)
                
                if size > 0:
                    entry_fee = (entry_price * size) * fee_rate
                    balance -= entry_fee
                    pos = {'side': setup['side'], 'entry': entry_price, 'sl': sl, 'tp': tp, 'size': size}
                    
    total_trades = wins + losses
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    net_pnl = balance - 1000.0
    
    # Calculate Custom Score (Higher is better)
    # Penalize low trade frequency and high drawdowns
    if total_trades < 10 or max_dd_pct > 0.40:
        score = -9999
    else:
        score = (net_pnl * (total_trades ** 0.5)) / (max_dd_pct if max_dd_pct > 0 else 0.01)
        
    return {
        'coin': coin,
        'timeframe': tf,
        'rr': rr,
        'lookback': lb,
        'trades': total_trades,
        'win_rate': round(win_rate, 2),
        'net_pnl': round(net_pnl, 2),
        'max_dd_pct': round(max_dd_pct * 100, 2),
        'score': round(score, 2)
    }

def run_optimization():
    combinations = list(itertools.product(COINS, TIMEFRAMES, RR_RATIOS, LOOKBACKS))
    print(f"Starting Grid Search on {len(combinations)} combinations using {cpu_count()} CPU cores...")
    
    start_time = time.time()
    
    with Pool(processes=cpu_count()) as pool:
        results = pool.map(evaluate_combination, combinations)
        
    results = [r for r in results if r is not None and r['trades'] > 0]
    
    # Sort by custom fitness score
    results.sort(key=lambda x: x['score'], reverse=True)
    
    df_results = pd.DataFrame(results)
    print("\n--- TOP 10 CONFIGURATIONS (TRAIN SET) ---")
    print(df_results.head(10).to_string(index=False))
    
    out_path = os.path.join(os.path.dirname(__file__), 'optimization_results.csv')
    df_results.to_csv(out_path, index=False)
    print(f"\nSaved full results to {out_path}")
    print(f"Optimization finished in {time.time() - start_time:.2f} seconds.")

if __name__ == "__main__":
    run_optimization()
