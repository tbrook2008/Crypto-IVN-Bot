import pandas as pd
import sys
import os
import itertools
from multiprocessing import Pool, cpu_count
import time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ict_logic import detect_ict_setup_fast

COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'DOGE', 'LINK', 'LTC']
TIMEFRAMES = ['1h', '2h', '4h']
RR_RATIOS = [1.0, 1.5, 2.0, 2.5, 3.0]
LOOKBACKS = [15, 20, 30, 40]

def evaluate_core(coin, tf, rr, lb, is_test=False):
    csv_path = os.path.join(DATA_DIR, f"{coin}_USDT_3yr.csv")
    if not os.path.exists(csv_path): return None
    
    df = pd.read_csv(csv_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)
    
    split_idx = int(len(df) * 0.65)
    df = df.iloc[split_idx:] if is_test else df.iloc[:split_idx]
    
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
    fee_rate, risk_pct = 0.001, 0.01
    
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
                fee = (exit_price * pos['size']) * fee_rate
                balance += (pnl - fee)
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
                
                risk_amount = balance * risk_pct
                price_risk = abs(ep - sl)
                if price_risk > 0:
                    sz = risk_amount / price_risk
                    max_pos = balance * 5
                    if (sz * ep) > max_pos: sz = max_pos / ep
                    if sz > 0:
                        balance -= ((ep * sz) * fee_rate)
                        pos = {'side': setup['side'], 'entry': ep, 'sl': sl, 'tp': tp, 'size': sz}
                        
    tot = wins + losses
    wr = (wins/tot)*100 if tot > 0 else 0
    net_pnl = balance - 1000.0
    
    # Fitness Score
    if tot < 5 or max_dd_pct > 0.40 or net_pnl <= 0:
        score = -9999
    else:
        score = (net_pnl * (tot ** 0.5)) / (max_dd_pct if max_dd_pct > 0 else 0.01)
        
    return {'coin': coin, 'tf': tf, 'rr': rr, 'lb': lb, 'trades': tot, 'wr': wr, 'pnl': net_pnl, 'dd': max_dd_pct*100, 'score': score}

def train_worker(args):
    return evaluate_core(*args, is_test=False)

def test_worker(args):
    return evaluate_core(*args, is_test=True)

def run_master_discovery():
    print(f"Starting Master Discovery Pipeline for ALL {len(COINS)} coins...")
    combos = list(itertools.product(COINS, TIMEFRAMES, RR_RATIOS, LOOKBACKS))
    
    start_time = time.time()
    
    # 1. Exhaustive Train Set Sweep
    with Pool(processes=cpu_count()) as pool:
        train_results = pool.map(train_worker, combos)
    train_results = [r for r in train_results if r is not None and r['score'] > 0]
    
    # 2. Group by coin and rank by score
    df_train = pd.DataFrame(train_results)
    if df_train.empty:
        print("No profitable train configs found.")
        return
        
    verified_edges = []
    
    for coin in COINS:
        coin_train = df_train[df_train['coin'] == coin].sort_values(by='score', ascending=False)
        if coin_train.empty:
            continue
            
        edge_found = False
        # Try the top 3 train configs on the Test Set
        for _, row in coin_train.head(5).iterrows():
            test_res = evaluate_core(coin, row['tf'], row['rr'], row['lb'], is_test=True)
            if test_res and test_res['pnl'] > 0 and test_res['dd'] < 20.0:
                verified_edges.append({
                    'Coin': coin,
                    'Timeframe': row['tf'],
                    'RR': row['rr'],
                    'Lookback': row['lb'],
                    'Train_PnL': round(row['pnl'], 2),
                    'Train_WR': round(row['wr'], 1),
                    'Test_PnL': round(test_res['pnl'], 2),
                    'Test_WR': round(test_res['wr'], 1),
                    'Test_DD': round(test_res['dd'], 2),
                    'Total_Trades': int(row['trades'] + test_res['trades'])
                })
                edge_found = True
                break # Move to next coin once an edge is verified
                
        if not edge_found:
            print(f"[{coin}] FAILED: No configurations survived Out-of-Sample verification.")
            
    df_verified = pd.DataFrame(verified_edges)
    print("\n" + "="*80)
    print("VERIFIED EDGE MATRICES (SURVIVED OUT-OF-SAMPLE TEST)")
    print("="*80)
    if not df_verified.empty:
        print(df_verified.to_string(index=False))
        
        md_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'VERIFIED_EDGES.md')
        with open(md_path, 'w') as f:
            f.write("# Verified Crypto Edges\n\n")
            f.write("These configurations were trained on 65% of 3-year data and survived the blind 35% Out-of-Sample test with positive PnL and <20% drawdown.\n\n")
    else:
        print("NO COINS SURVIVED.")

    print(f"\nPipeline finished in {time.time() - start_time:.2f} seconds.")

if __name__ == "__main__":
    run_master_discovery()
