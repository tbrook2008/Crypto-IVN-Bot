import ccxt.async_support as ccxt
import asyncio
import json
import os
import sys
import pandas as pd
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ict_logic import detect_ict_setup_fast

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'config.json')
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'paper_state.json')

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, 'r') as f:
            return json.load(f)
    return {
        "balance": 1000.0,
        "open_trades": [],
        "trade_history": []
    }

def save_state(state):
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=4)

def calculate_position_size(equity, risk_pct, entry_price, sl_price, max_leverage):
    risk_amount = equity * risk_pct
    price_risk = abs(entry_price - sl_price)
    if price_risk == 0: return 0
    size = risk_amount / price_risk
    
    max_position_value = equity * max_leverage
    if (size * entry_price) > max_position_value:
        size = max_position_value / entry_price
    return size

async def update_open_trades(exchange, state, fee_rate):
    """Check current market prices against open trades to simulate SL/TP hits."""
    still_open = []
    
    for trade in state['open_trades']:
        try:
            # Fetch current ticker to check high/low
            ticker = await exchange.fetch_ticker(trade['symbol'])
            current_price = ticker['last']
            
            closed = False
            exit_price = 0
            
            # Simple check against current price (In a real high-frequency sim we'd check OHLCV, but for 2H/4H ticker is fine)
            if trade['side'] == 'buy':
                if current_price <= trade['sl']: closed = True; exit_price = trade['sl']
                elif current_price >= trade['tp']: closed = True; exit_price = trade['tp']
            else: # sell
                if current_price >= trade['sl']: closed = True; exit_price = trade['sl']
                elif current_price <= trade['tp']: closed = True; exit_price = trade['tp']
                
            if closed:
                pnl = 0
                if trade['side'] == 'buy':
                    pnl = (exit_price - trade['entry_price']) * trade['size']
                else:
                    pnl = (trade['entry_price'] - exit_price) * trade['size']
                
                fee = (exit_price * trade['size']) * fee_rate
                net_pnl = pnl - fee
                state['balance'] += net_pnl
                
                trade['exit_price'] = exit_price
                trade['net_pnl'] = net_pnl
                trade['close_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                state['trade_history'].append(trade)
                
                print(f"[{trade['close_time']}] 💰 TRADE CLOSED: {trade['symbol']} | Net PnL: ${net_pnl:.2f} | New Balance: ${state['balance']:.2f}")
            else:
                still_open.append(trade)
                
        except Exception as e:
            print(f"Error updating {trade['symbol']}: {e}")
            still_open.append(trade)
            
    state['open_trades'] = still_open
    save_state(state)

async def scan_market(exchange, symbol, params, config, state):
    try:
        timeframe = params['timeframe']
        limit = params['lookback'] * 2 
        
        # Public data fetch, no API keys needed
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv: return
            
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        prev = df['close'].shift(1)
        tr = pd.concat([df['high']-df['low'], (df['high']-prev).abs(), (df['low']-prev).abs()], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean().bfill()
        bars = df.to_dict('records')
        window = bars[-params['lookback']:]
        
        setup = detect_ict_setup_fast(window, config['ict_parameters'], htf_bias=None)
        
        if setup:
            # Check if we already have an open trade for this symbol to avoid duplicates
            if any(t['symbol'] == symbol for t in state['open_trades']):
                return
                
            current_price = bars[-1]['close']
            risk_points = setup['risk_points']
            rr = params['rr']
            
            if setup['side'] == 'buy': sl = current_price - risk_points; tp = current_price + (risk_points * rr)
            else: sl = current_price + risk_points; tp = current_price - (risk_points * rr)
                
            # Global Constraints Check
            if len(state['open_trades']) >= config['global_portfolio_constraints']['max_concurrent_trades']:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SKIP {symbol}: Portfolio Full ({len(state['open_trades'])} trades open).")
                return
            
            size = calculate_position_size(state['balance'], config['risk_management']['risk_per_trade_pct'], 
                                           current_price, sl, config['global_portfolio_constraints']['max_total_leverage'])
            
            if size > 0:
                fee_rate = config['risk_management']['fee_rate']
                entry_fee = (current_price * size) * fee_rate
                state['balance'] -= entry_fee
                
                new_trade = {
                    'symbol': symbol,
                    'side': setup['side'],
                    'entry_price': current_price,
                    'sl': sl,
                    'tp': tp,
                    'size': size,
                    'open_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                state['open_trades'].append(new_trade)
                save_state(state)
                print(f"[{new_trade['open_time']}] 🚀 PAPER ENTRY: {symbol} | {setup['side'].upper()} | Entry: {current_price} | SL: {sl} | TP: {tp}")

    except Exception as e:
        print(f"Error scanning {symbol}: {e}")

async def main():
    config = load_config()
    state = load_state()
    
    print("="*60)
    print("LOCAL PAPER TRADING ENGINE STARTED")
    print(f"Current Balance: ${state['balance']:.2f}")
    print(f"Open Trades: {len(state['open_trades'])}")
    print("="*60)
    
    # Initialize public exchange instance (Binance public API is robust and keyless)
    exchange = ccxt.binance({'enableRateLimit': True})
    fee_rate = config['risk_management']['fee_rate']
    
    while True:
        # 1. Update existing trades
        await update_open_trades(exchange, state, fee_rate)
        
        # 2. Scan for new setups
        tasks = []
        for symbol, params in config['assets'].items():
            tasks.append(scan_market(exchange, symbol, params, config, state))
            
        await asyncio.gather(*tasks)
        
        # 3. Print Dashboard
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan complete. Balance: ${state['balance']:.2f} | Open Trades: {len(state['open_trades'])}/{config['global_portfolio_constraints']['max_concurrent_trades']}. Sleeping...")
        
        # Sleep for 5 minutes
        await asyncio.sleep(300)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nPaper bot shutting down safely.")
