import threading
import time
import json
from datetime import datetime
import warnings
import numpy as np
from scipy.signal import argrelextrema
import pandas as pd
import pandas_ta as ta
import ccxt
from plyer import notification
from flask import Flask, render_template_string
import webview
import os 
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv  

load_dotenv()

# --- CONFIGURATION ---
class Config:
    API_KEY = os.getenv("BINANCE_API_KEY")
    API_SECRET = os.getenv("BINANCE_API_SECRET")
    SYMBOL = 'SOL/USDT'
    TIMEFRAMES = ['1d', '1h', '15m', '5m']
    LOOKBACK_DAYS = 90
    SCALPER_RANGE = 0.03
    LOOP_INTERVAL = 60
    ADX_THRESHOLD = 25
    WEIGHTS = {'1d': 5, '1h': 3, '15m': 1, '5m': 0.5}

# Suppress Warnings
warnings.simplefilter(action='ignore', category=pd.errors.SettingWithCopyWarning)
warnings.simplefilter(action='ignore', category=FutureWarning)

app = Flask(__name__)

# --- HELPER: Fixes the "np is not defined" error ---
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NumpyEncoder, self).default(obj)

# --- ANALYSIS ENGINE ---
class MarketAnalyzer:
    def __init__(self):
        self.exchange = ccxt.binance({'apiKey': Config.API_KEY, 'secret': Config.API_SECRET})
        
    def fetch_ohlcv(self, timeframe):
        try:
            since = self.exchange.parse8601(pd.to_datetime('now', utc=True) - pd.to_timedelta(f'{Config.LOOKBACK_DAYS}d'))
            ohlcv = self.exchange.fetch_ohlcv(Config.SYMBOL, timeframe=timeframe, since=since)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return timeframe, df
        except Exception as e:
            print(f"Error fetching {timeframe}: {e}")
            return timeframe, None

    def get_all_data(self):
        data = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(self.fetch_ohlcv, tf) for tf in Config.TIMEFRAMES]
            for future in futures:
                tf, df = future.result()
                if df is not None:
                    data[tf] = self.calculate_indicators(df)
        return data

    def calculate_indicators(self, df):
        for length in [21, 50, 99, 200]:
            df.ta.ema(length=length, append=True)
        
        df.ta.rsi(length=14, append=True)
        df.ta.vwap(append=True)
        df.ta.adx(append=True)
        df.ta.atr(append=True)
        
        # NOTE: Candle patterns generate the "Requires TA-Lib" spam. 
        # It is harmless, but if it annoys you, comment out the line below.
        try:
            df.ta.cdl_pattern(name="all", append=True, use_talib=False) 
        except:
            pass # Skip if it fails

        df['Volume_MA_20'] = df.ta.sma(length=20, close='volume')
        
        high, low = df['high'].max(), df['low'].min()
        diff = high - low
        for level in [0.236, 0.382, 0.500, 0.618, 0.786]:
            df[f'fib_{level}'] = high - (diff * level)
            
        return df

    def find_sr_zones(self, df, timeframe):
        zones = []
        if df is None: return zones
        
        order = 5
        # Convert to numpy arrays immediately to avoid index issues
        highs_idx = argrelextrema(df['high'].values, np.greater_equal, order=order)[0]
        lows_idx = argrelextrema(df['low'].values, np.less_equal, order=order)[0]
        
        levels = np.concatenate((df['high'].iloc[highs_idx].values, df['low'].iloc[lows_idx].values))
        if len(levels) == 0: return []
        
        levels.sort()
        clusters = []
        current_cluster = [levels[0]]
        
        for i in range(1, len(levels)):
            if (levels[i] - current_cluster[-1]) / current_cluster[-1] < 0.005:
                current_cluster.append(levels[i])
            else:
                clusters.append(current_cluster)
                current_cluster = [levels[i]]
        clusters.append(current_cluster)
        
        for cluster in clusters:
            if len(cluster) >= 2:
                zones.append({
                    'price': float(np.mean(cluster)), # FORCE FLOAT
                    'source': f"{timeframe} S/R ({len(cluster)}x)", 
                    'weight': Config.WEIGHTS.get(timeframe, 1) + len(cluster)
                })
        return zones

    def detect_divergence(self, df):
        if df is None or len(df) < 60: return "None"
        rsi = df['RSI_14'].iloc[-1]
        if rsi > 70: return "Overbought (>70)"
        if rsi < 30: return "Oversold (<30)"
        return "Neutral"

    def analyze_sentiment(self, df_5m, df_1h):
        score = 0
        current_price = df_5m['close'].iloc[-1]
        
        if 'EMA_200' in df_1h.columns:
            score += 2 if current_price > df_1h['EMA_200'].iloc[-1] else -2
            
        if 'VWAP_D' in df_5m.columns:
            score += 1 if current_price > df_5m['VWAP_D'].iloc[-1] else -1
            
        if 'EMA_21' in df_5m.columns and 'EMA_50' in df_5m.columns:
            if df_5m['EMA_21'].iloc[-1] > df_5m['EMA_50'].iloc[-1]: score += 1
            else: score -= 1
        
        desc = "Neutral"
        if score >= 2: desc = "Bullish"
        if score <= -2: desc = "Bearish"
        
        return {'score': int(score), 'description': desc}

    def generate_levels(self, data_frames):
        master_levels = []
        df_d = data_frames.get('1d')
        if df_d is not None:
            prev = df_d.iloc[-2]
            master_levels.append({'price': float(prev['high']), 'source': 'PDH', 'weight': 8})
            master_levels.append({'price': float(prev['low']), 'source': 'PDL', 'weight': 8})
        
        for tf, df in data_frames.items():
            if df is None: continue
            last_row = df.iloc[-1]
            base_weight = Config.WEIGHTS.get(tf, 1)
            
            for ema in [200, 99, 50]:
                col = f'EMA_{ema}'
                if col in last_row:
                    w = base_weight + (2 if ema == 200 else 0)
                    master_levels.append({'price': float(last_row[col]), 'source': f'{tf} EMA {ema}', 'weight': w})
            
            if tf in ['15m', '5m'] and 'VWAP_D' in last_row:
                master_levels.append({'price': float(last_row['VWAP_D']), 'source': f'{tf} VWAP', 'weight': base_weight + 2})
                
            sr = self.find_sr_zones(df, tf)
            master_levels.extend(sr)

        return master_levels

    def cluster_confluence(self, levels):
        if not levels: return []
        levels.sort(key=lambda x: x['price'])
        
        clustered = []
        current = [levels[0]]
        
        for i in range(1, len(levels)):
            if abs(levels[i]['price'] - current[0]['price']) / current[0]['price'] < 0.005:
                current.append(levels[i])
            else:
                clustered.append(current)
                current = [levels[i]]
        clustered.append(current)
        
        results = []
        for c in clustered:
            if len(c) > 1:
                price = np.mean([x['price'] for x in c])
                score = sum(x['weight'] for x in c)
                sources = list(set([x['source'] for x in c]))
                results.append({
                    'price': float(price), # FORCE FLOAT
                    'score': int(score),   # FORCE INT
                    'sources': sources, 
                    'confirmations': []
                })
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results

# --- WORKER THREAD ---
def analysis_worker(window):
    analyzer = MarketAnalyzer()
    
    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching data...")
            data_frames = analyzer.get_all_data()
            
            if not data_frames:
                time.sleep(10)
                continue

            current_price = float(data_frames['5m']['close'].iloc[-1])
            sentiment = analyzer.analyze_sentiment(data_frames['5m'], data_frames['1h'])
            raw_levels = analyzer.generate_levels(data_frames)
            zones = analyzer.cluster_confluence(raw_levels)
            
            # Simple Confirmation Logic
            df_5m = data_frames['5m']
            last_vol = float(df_5m['volume'].iloc[-1])
            avg_vol = float(df_5m['Volume_MA_20'].iloc[-1])
            
            for z in zones:
                if abs(current_price - z['price']) / z['price'] < 0.005:
                    if last_vol > avg_vol * 1.5:
                        z['confirmations'].append("High Vol")

            upper = current_price * (1 + Config.SCALPER_RANGE)
            lower = current_price * (1 - Config.SCALPER_RANGE)
            scalper_zones = [z for z in zones if lower <= z['price'] <= upper]

            payload = {
                "current_price": current_price,
                "sentiment": sentiment,
                "potential_entries": zones[:12],
                "scalper_entries": scalper_zones,
                "divergence_status": analyzer.detect_divergence(data_frames['5m']),
                "market_regime": f"ADX: {float(data_frames['1h']['ADX_14'].iloc[-1]):.1f}",
                "volatility": f"ATR: {float(data_frames['5m']['ATRr_14'].iloc[-1]):.2f}",
                "status": f"Updated: {datetime.now().strftime('%H:%M:%S')}"
            }
            
            # --- CRITICAL FIX: Convert Payload to JSON String using NumpyEncoder ---
            # This turns np.float64(100.5) into plain 100.5 so JS can understand it
            json_payload = json.dumps(payload, cls=NumpyEncoder)
            
            if window:
                window.evaluate_js(f"window.updateData({json_payload})")
                
        except Exception as e:
            print(f"Loop Error: {e}")
            import traceback
            traceback.print_exc()
            
        time.sleep(Config.LOOP_INTERVAL)

# --- HTML TEMPLATE (Linked to Static Files) ---
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vivi's Scalp Terminal</title>
    <link rel="stylesheet" href="/static/style.css">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
</head>
<body>
    <div class="container">
        <header>
            <h1>Vivi's Trading Terminal <span style="font-size:0.5em; color:var(--accent-blue)">SOL/USDT</span></h1>
            <div id="last-updated" class="status-badge">Connecting...</div>
        </header>

        <div class="dashboard-grid">
            <div class="metric-card">
                <span class="metric-label">Price</span>
                <span class="metric-value" id="current-price">---</span>
            </div>
            <div class="metric-card">
                <span class="metric-label">Sentiment</span>
                <span class="metric-value" id="sentiment-val">---</span>
                <span class="metric-sub" id="sentiment-sub">Score: 0</span>
            </div>
            <div class="metric-card">
                <span class="metric-label">Market Regime</span>
                <span class="metric-value" id="regime-val">---</span>
                <span class="metric-sub" id="volatility-val">---</span>
            </div>
            <div class="metric-card">
                <span class="metric-label">RSI Status</span>
                <span class="metric-value" id="divergence-val">---</span>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-button active" onclick="showTab('scalper')">⚡ Scalper (±3%)</button>
            <button class="tab-button" onclick="showTab('zones')">🌍 Macro Zones</button>
        </div>

        <div id="scalper-content" class="tab-content active">
            <div class="zones-wrapper">
                <div id="scalper-zones-container"></div>
            </div>
        </div>

        <div id="zones-content" class="tab-content">
            <div class="zones-wrapper">
                <div id="zones-container"></div>
            </div>
        </div>
    </div>
    <script src="/static/script.js"></script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

if __name__ == '__main__':
    if not Config.API_KEY or not Config.API_SECRET:
        print("⚠️  WARNING: Binance API Keys not found in .env. Data fetching will fail.")

    window = webview.create_window(
        'Vivi Scalp Terminal',
        app,
        width=1300,
        height=900,
        background_color='#0b0e11'
    )
    
    t = threading.Thread(target=analysis_worker, args=(window,), daemon=True)
    t.start()
    
    webview.start()