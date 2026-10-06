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

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def calculate_position_size(equity, risk_pct, entry_price, sl_price, max_leverage):
    risk_amount = equity * risk_pct
    price_risk = abs(entry_price - sl_price)
    if price_risk == 0: return 0
    size = risk_amount / price_risk
    
    max_position_value = equity * max_leverage
    if (size * entry_price) > max_position_value:
        size = max_position_value / entry_price
        
    return size

async def fetch_and_analyze(exchange, symbol, params, config):
    try:
        # Fetch OHLCV data
        timeframe = params['timeframe']
        limit = params['lookback'] * 2  # Buffer for ATR calculation
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        if not ohlcv:
            return
            
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calculate ATR
        prev = df['close'].shift(1)
        tr = pd.concat([df['high']-df['low'], (df['high']-prev).abs(), (df['low']-prev).abs()], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean().bfill()
        
        bars = df.to_dict('records')
        
        # We only pass the required lookback window to the detection engine
        window = bars[-params['lookback']:]
        
        # Detect setup using the exactly matched core engine logic
        setup = detect_ict_setup_fast(window, config['ict_parameters'], htf_bias=None)
        
        if setup:
            current_price = bars[-1]['close']
            risk_points = setup['risk_points']
            rr = params['rr']
            
            if setup['side'] == 'buy':
                sl = current_price - risk_points
                tp = current_price + (risk_points * rr)
            else:
                sl = current_price + risk_points
                tp = current_price - (risk_points * rr)
                
            # Fetch balance to calculate size dynamically
            # balance = await exchange.fetch_balance()
            # equity = balance['USDT']['total']
            equity = 1000.0  # Placeholder for paper trading log
            
            size = calculate_position_size(equity, config['risk_management']['risk_per_trade_pct'], 
                                           current_price, sl, config['risk_management']['max_leverage'])
            
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔥 SETUP DETECTED: {symbol} | {setup['side'].upper()} | Entry: {current_price} | SL: {sl} | TP: {tp} | Size: {size:.4f}")
            
            # --- LIVE EXECUTION LOGIC GOES HERE ---
            # await exchange.create_order(symbol, 'market', setup['side'], size)
            # await exchange.create_order(symbol, 'limit', 'stop_loss', size, sl, params={'stopPrice': sl})
            # await exchange.create_order(symbol, 'limit', 'take_profit', size, tp, params={'stopPrice': tp})
            
    except Exception as e:
        print(f"Error processing {symbol}: {e}")

async def main():
    config = load_config()
    print("="*60)
    print("INITIALIZING CRYPTO-IVN-BOT LIVE ENGINE")
    print("Loaded Verified Assets:", list(config['assets'].keys()))
    print("="*60)
    
    # Initialize exchange (using Binance as default, swap to user's via .env later)
    exchange = ccxt.binance({
        'enableRateLimit': True,
    })
    
    while True:
        tasks = []
        for symbol, params in config['assets'].items():
            tasks.append(fetch_and_analyze(exchange, symbol, params, config))
            
        await asyncio.gather(*tasks)
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scan complete. Sleeping for 5 minutes...")
        await asyncio.sleep(300)  # Scan every 5 minutes (since lowest TF is 2H)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot shutting down.")
