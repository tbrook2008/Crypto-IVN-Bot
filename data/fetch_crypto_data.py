import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
import os

# Configuration
EXCHANGE = ccxt.binance({
    'enableRateLimit': True,  # Extremely important to prevent IP bans
})
SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 
    'XRP/USDT', 'ADA/USDT', 'AVAX/USDT', 'DOGE/USDT', 
    'LINK/USDT', 'LTC/USDT'
]
TIMEFRAME = '1m'
YEARS_OF_DATA = 3
DATA_DIR = '/Users/tbrook/Desktop/Projects/Crypto-IVN-Bot/data'

def fetch_data(symbol, start_dt, end_dt):
    print(f"Starting fetch for {symbol}...")
    all_ohlcv = []
    
    # Convert datetimes to milliseconds timestamp
    since = int(start_dt.timestamp() * 1000)
    end_timestamp = int(end_dt.timestamp() * 1000)
    
    while since < end_timestamp:
        try:
            # Fetch 1000 candles at a time
            ohlcv = EXCHANGE.fetch_ohlcv(symbol, TIMEFRAME, since=since, limit=1000)
            if not ohlcv:
                break
                
            all_ohlcv.extend(ohlcv)
            
            # Update 'since' to the last candle's timestamp + 1 minute (60,000 ms)
            since = ohlcv[-1][0] + 60000
            
            # Print progress every ~100k candles
            if len(all_ohlcv) % 100000 == 0:
                current_date = datetime.fromtimestamp(ohlcv[-1][0]/1000).strftime('%Y-%m-%d')
                print(f"[{symbol}] Downloaded {len(all_ohlcv):,} bars... Current date: {current_date}")
                
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            print("Sleeping for 30 seconds before retrying...")
            time.sleep(30)
            
    # Convert to DataFrame
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Save to CSV
    safe_symbol = symbol.replace('/', '_')
    filepath = os.path.join(DATA_DIR, f"{safe_symbol}_{YEARS_OF_DATA}yr.csv")
    df.to_csv(filepath, index=False)
    print(f"Successfully saved {len(df):,} bars for {symbol} to {filepath}\n")

def main():
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=YEARS_OF_DATA * 365)
    
    print(f"Target Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    for symbol in SYMBOLS:
        fetch_data(symbol, start_date, end_date)
        
    print("All data downloads complete.")

if __name__ == "__main__":
    main()
