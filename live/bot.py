import ccxt.async_support as ccxt
import asyncio
import json
import os
import sys
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables (API Keys)
load_dotenv()

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

async def fetch_and_analyze(exchange, symbol, params, config, portfolio_state):
    try:
        timeframe = params['timeframe']
        limit = params['lookback'] * 2 
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
            current_price = bars[-1]['close']
            risk_points = setup['risk_points']
            rr = params['rr']
            
            if setup['side'] == 'buy':
                sl = current_price - risk_points
                tp = current_price + (risk_points * rr)
            else:
                sl = current_price + risk_points
                tp = current_price - (risk_points * rr)
                
            # Global Portfolio Constraints Check
            async with portfolio_state['lock']:
                if portfolio_state['open_trades'] >= config['global_portfolio_constraints']['max_concurrent_trades']:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SKIP {symbol}: Max concurrent trades reached.")
                    return
                
                # Fetch live balance for sizing
                balance = await exchange.fetch_balance()
                equity = balance['USDT']['total'] if 'USDT' in balance else 1000.0
                
                size = calculate_position_size(equity, config['risk_management']['risk_per_trade_pct'], 
                                               current_price, sl, config['global_portfolio_constraints']['max_total_leverage'])
                
                if size > 0:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔥 EXECUTING: {symbol} | {setup['side'].upper()} | Size: {size:.4f}")
                    
                    try:
                        # 1. Market Entry
                        order = await exchange.create_order(symbol, 'market', setup['side'], size)
                        
                        # 2. Place Stop Loss (using inverse side)
                        exit_side = 'sell' if setup['side'] == 'buy' else 'buy'
                        
                        # CCXT Unified Bracket Order syntax (varies slightly by exchange, mapped for Bybit/Binance Perps)
                        await exchange.create_order(symbol, 'stop', exit_side, size, sl, params={'stopPrice': sl, 'reduceOnly': True})
                        
                        # 3. Place Take Profit
                        await exchange.create_order(symbol, 'limit', exit_side, size, tp, params={'reduceOnly': True})
                        
                        # Register trade in portfolio state
                        portfolio_state['open_trades'] += 1
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ ORDERS PLACED SUCCESSFULLY FOR {symbol}")
                        
                    except Exception as order_err:
                        print(f"Failed to place orders for {symbol}: {order_err}")

    except Exception as e:
        print(f"Error processing {symbol}: {e}")

async def main():
    config = load_config()
    print("="*60)
    print("INITIALIZING CRYPTO-IVN-BOT LIVE ENGINE (TESTNET)")
    print("Loaded Verified Assets:", list(config['assets'].keys()))
    print("="*60)
    
    api_key = os.getenv("EXCHANGE_API_KEY")
    api_secret = os.getenv("EXCHANGE_API_SECRET")
    
    if not api_key or not api_secret:
        print("CRITICAL ERROR: EXCHANGE_API_KEY or EXCHANGE_API_SECRET missing in .env file.")
        sys.exit(1)
    
    # Initialize exchange (Bybit Testnet by default for Perps shorting)
    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'} # Important: 'swap' means Perpetual Futures
    })
    
    # Force Testnet Mode
    exchange.set_sandbox_mode(True)
    
    portfolio_state = {
        'open_trades': 0, # In a full prod bot, this would actively poll exchange.fetch_positions()
        'lock': asyncio.Lock()
    }
    
    while True:
        # In production, we actively sync open positions with the exchange
        try:
            positions = await exchange.fetch_positions()
            active_positions = [p for p in positions if float(p['info'].get('size', 0)) > 0]
            portfolio_state['open_trades'] = len(active_positions)
        except Exception as e:
            print(f"Could not sync positions: {e}")
            
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Active Positions: {portfolio_state['open_trades']}/{config['global_portfolio_constraints']['max_concurrent_trades']}")
        
        tasks = []
        for symbol, params in config['assets'].items():
            # Convert spot symbol to perp symbol depending on exchange (e.g. BTC/USDT:USDT for CCXT unified)
            perp_symbol = symbol + ":USDT" 
            tasks.append(fetch_and_analyze(exchange, perp_symbol, params, config, portfolio_state))
            
        await asyncio.gather(*tasks)
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scan complete. Sleeping for 5 minutes...")
        await asyncio.sleep(300) 

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot shutting down.")
