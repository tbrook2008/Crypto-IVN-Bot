import pandas as pd
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ict_logic import detect_ict_setup_fast

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'config.json')

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def calculate_position_size(equity, risk_pct, entry_price, sl_price, fee_rate, max_leverage=10):
    """
    Calculate fractional crypto sizing based on fixed percentage risk.
    Includes max leverage cap to prevent fee-death on tight stops.
    """
    risk_amount = equity * risk_pct
    price_risk = abs(entry_price - sl_price)
    
    if price_risk == 0:
        return 0
        
    # Uncapped size
    size = risk_amount / price_risk
    
    # Cap by max leverage
    max_position_value = equity * max_leverage
    if (size * entry_price) > max_position_value:
        size = max_position_value / entry_price
        
    return size

def run_backtest(data_path, config, is_test_set=False):
    df = pd.read_csv(data_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)
    
    split_idx = int(len(df) * 0.65)
    if is_test_set:
        df = df.iloc[split_idx:]
    else:
        df = df.iloc[:split_idx]
        
    df_3m = df.resample('3min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
    
    prev = df_3m['close'].shift(1)
    tr = pd.concat([
        df_3m['high'] - df_3m['low'],
        (df_3m['high'] - prev).abs(),
        (df_3m['low'] - prev).abs()
    ], axis=1).max(axis=1)
    df_3m['atr'] = tr.rolling(14).mean().bfill()
    
    df_3m.reset_index(inplace=True)
    bars = df_3m.to_dict('records')
    
    ict_params = config['ict_parameters']
    risk_params = config['risk_management']
    fee_rate = risk_params['fee_rate']
    
    balance = 1000.0
    peak = balance
    max_dd_pct = 0.0
    wins, losses = 0, 0
    pos = None
    
    lb = ict_params['LOOKBACK_BARS']
    rr = ict_params['RR_RATIO']
    
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
                    sl = entry_price - risk_points
                    tp = entry_price + (risk_points * rr)
                else:
                    sl = entry_price + risk_points
                    tp = entry_price - (risk_points * rr)
                    
                size = calculate_position_size(balance, risk_params['risk_per_trade_pct'], entry_price, sl, fee_rate, max_leverage=5)
                
                if size > 0:
                    entry_fee = (entry_price * size) * fee_rate
                    balance -= entry_fee
                    pos = {'side': setup['side'], 'entry': entry_price, 'sl': sl, 'tp': tp, 'size': size}
                
    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    return {
        'trades': total_trades,
        'win_rate': win_rate,
        'net_pnl': balance - 1000.0,
        'final_balance': balance,
        'max_dd_pct': max_dd_pct * 100
    }

if __name__ == "__main__":
    csv_path = sys.argv[1]
    cfg = load_config()
    print("\n" + "="*50)
    res_train = run_backtest(csv_path, cfg, is_test_set=False)
    print(f"Results (Train 65%): {res_train['trades']} Trades | {res_train['win_rate']:.1f}% WR | PnL: ${res_train['net_pnl']:.2f} | DD: {res_train['max_dd_pct']:.2f}%")
    res_test = run_backtest(csv_path, cfg, is_test_set=True)
    print(f"Results (Test 35%):  {res_test['trades']} Trades | {res_test['win_rate']:.1f}% WR | PnL: ${res_test['net_pnl']:.2f} | DD: {res_test['max_dd_pct']:.2f}%")
