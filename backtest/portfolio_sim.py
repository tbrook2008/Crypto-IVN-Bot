import pandas as pd
import json
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ict_logic import detect_ict_setup_fast

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'config.json')
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def get_exact_exit(df_1m, start_time, sl, tp, side):
    """Scan 1m data to find the exact timestamp the trade hits SL or TP."""
    future = df_1m.loc[start_time:]
    for idx, row in future.iterrows():
        h, l = row['high'], row['low']
        if side == 'buy':
            if l <= sl: return idx, sl, 'sl'
            if h >= tp: return idx, tp, 'tp'
        else:
            if h >= sl: return idx, sl, 'sl'
            if l <= tp: return idx, tp, 'tp'
    return None, None, 'open'

def run_portfolio_simulation():
    cfg = load_config()
    assets = cfg['assets']
    max_concurrent = cfg['global_portfolio_constraints']['max_concurrent_trades']
    risk_pct = cfg['risk_management']['risk_per_trade_pct']
    fee_rate = cfg['risk_management']['fee_rate']
    max_leverage = cfg['global_portfolio_constraints']['max_total_leverage']
    ict_params = cfg['ict_parameters']
    
    print(f"Loading data and extracting signals for {len(assets)} assets on locked 35% Test Set...")
    
    all_signals = []
    
    for coin_pair, params in assets.items():
        coin = coin_pair.split('/')[0]
        csv_path = os.path.join(DATA_DIR, f"{coin}_USDT_3yr.csv")
        
        # 1. Load Data
        df = pd.read_csv(csv_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        # 2. Strict 35% Test Split
        split_idx = int(len(df) * 0.65)
        df_1m = df.iloc[split_idx:]
        
        # 3. Resample
        tf = params['timeframe']
        df_tf = df_1m.resample(tf).agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
        
        # 4. Calculate ATR
        prev = df_tf['close'].shift(1)
        tr = pd.concat([df_tf['high']-df_tf['low'], (df_tf['high']-prev).abs(), (df_tf['low']-prev).abs()], axis=1).max(axis=1)
        df_tf['atr'] = tr.rolling(14).mean().bfill()
        
        df_tf.reset_index(inplace=True)
        bars = df_tf.to_dict('records')
        
        lb = params['lookback']
        rr = params['rr']
        
        for i in range(lb, len(bars)):
            b = bars[i]
            window = bars[i-lb : i+1]
            setup = detect_ict_setup_fast(window, ict_params, htf_bias=None)
            
            if setup:
                ep = b['close']
                rp = setup['risk_points']
                if setup['side'] == 'buy': sl=ep-rp; tp=ep+(rp*rr)
                else: sl=ep+rp; tp=ep-(rp*rr)
                
                # Find exact exit
                exit_time, exit_price, reason = get_exact_exit(df_1m, b['timestamp'], sl, tp, setup['side'])
                
                if exit_time:
                    all_signals.append({
                        'coin': coin,
                        'entry_time': b['timestamp'],
                        'exit_time': exit_time,
                        'side': setup['side'],
                        'entry_price': ep,
                        'exit_price': exit_price,
                        'sl': sl,
                        'tp': tp,
                        'reason': reason
                    })
                    
    # Sort all signals globally by entry time
    all_signals.sort(key=lambda x: x['entry_time'])
    print(f"Extracted {len(all_signals)} total raw signals across the portfolio.")
    print("Running Multi-Asset Dry Run Simulation...")
    
    balance = 1000.0
    peak = balance
    max_dd_pct = 0.0
    
    open_trades = []
    executed_trades = 0
    skipped_trades = 0
    wins, losses = 0, 0
    
    trade_log = []
    
    for sig in all_signals:
        current_time = sig['entry_time']
        
        # 1. Close any trades that hit their exit_time before or exactly at current_time
        still_open = []
        for t in open_trades:
            if t['exit_time'] <= current_time:
                # Close trade
                pnl = 0
                if t['side'] == 'buy':
                    pnl = (t['exit_price'] - t['entry_price']) * t['size']
                else:
                    pnl = (t['entry_price'] - t['exit_price']) * t['size']
                    
                fee = (t['exit_price'] * t['size']) * fee_rate
                balance += (pnl - fee)
                
                if pnl > 0: wins += 1
                else: losses += 1
                
                if balance > peak: peak = balance
                dd = (peak - balance) / peak
                if dd > max_dd_pct: max_dd_pct = dd
            else:
                still_open.append(t)
        open_trades = still_open
        
        # 2. Check Global Constraints
        if len(open_trades) >= max_concurrent:
            skipped_trades += 1
            continue
            
        # 3. Calculate Size and Execute
        risk_amount = balance * risk_pct
        price_risk = abs(sig['entry_price'] - sig['sl'])
        if price_risk == 0: continue
        
        size = risk_amount / price_risk
        
        # Apply Leverage Cap (Portfolio level)
        # Notional value of all current open trades
        current_notional = sum([t['entry_price'] * t['size'] for t in open_trades])
        max_notional_allowed = (balance * max_leverage) - current_notional
        
        trade_notional = size * sig['entry_price']
        if trade_notional > max_notional_allowed:
            size = max_notional_allowed / sig['entry_price']
            
        if size <= 0:
            skipped_trades += 1
            continue
            
        # Execute Entry
        entry_fee = (sig['entry_price'] * size) * fee_rate
        balance -= entry_fee
        
        sig['size'] = size
        open_trades.append(sig)
        executed_trades += 1
        trade_log.append(sig)
        
    # Close out any remaining open trades at the end of the simulation based on their predetermined exits
    for t in open_trades:
        pnl = 0
        if t['side'] == 'buy': pnl = (t['exit_price'] - t['entry_price']) * t['size']
        else: pnl = (t['entry_price'] - t['exit_price']) * t['size']
        fee = (t['exit_price'] * t['size']) * fee_rate
        balance += (pnl - fee)
        if pnl > 0: wins += 1
        else: losses += 1
        if balance > peak: peak = balance
        dd = (peak - balance) / peak
        if dd > max_dd_pct: max_dd_pct = dd
        
    print("\n" + "="*50)
    print("PORTFOLIO DRY RUN RESULTS (35% OUT-OF-SAMPLE)")
    print("="*50)
    print(f"Starting Balance:   $1,000.00")
    print(f"Ending Balance:     ${balance:.2f}")
    print(f"Net PnL:            ${balance - 1000.0:.2f} ({(balance-1000)/10:.2f}%)")
    print(f"Max Drawdown:       {max_dd_pct*100:.2f}%")
    print(f"Executed Trades:    {executed_trades}")
    print(f"Skipped Trades:     {skipped_trades} (Due to Portfolio Limits)")
    print(f"Win Rate:           {(wins/executed_trades*100) if executed_trades > 0 else 0:.1f}%")
    print("="*50)
    
if __name__ == "__main__":
    run_portfolio_simulation()
