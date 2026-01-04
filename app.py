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
    BTC_SYMBOL = 'BTC/USDT'
    TIMEFRAMES = ['1d', '1h', '15m', '5m']
    LOOKBACK_DAYS = 90
    SCALPER_RANGE = 0.03
    LOOP_INTERVAL = 60
    ADX_THRESHOLD = 25
    WEIGHTS = {'1d': 5, '1h': 3, '15m': 1, '5m': 0.5}

warnings.simplefilter(action='ignore', category=pd.errors.SettingWithCopyWarning)
warnings.simplefilter(action='ignore', category=FutureWarning)

app = Flask(__name__)

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        return super(NumpyEncoder, self).default(obj)

class MarketAnalyzer:
    def __init__(self):
        self.exchange = ccxt.binance({'apiKey': Config.API_KEY, 'secret': Config.API_SECRET})
        
    def fetch_ohlcv(self, symbol, timeframe):
        try:
            since = self.exchange.parse8601(pd.to_datetime('now', utc=True) - pd.to_timedelta(f'{Config.LOOKBACK_DAYS}d'))
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return (symbol, timeframe), df
        except Exception as e:
            print(f"Error fetching {symbol} {timeframe}: {e}")
            return (symbol, timeframe), None

    def get_all_data(self):
        data = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(self.fetch_ohlcv, Config.SYMBOL, tf) for tf in Config.TIMEFRAMES]
            futures.append(executor.submit(self.fetch_ohlcv, Config.BTC_SYMBOL, '5m'))
            
            for future in futures:
                (sym, tf), df = future.result()
                if df is not None:
                    key = f"{sym}_{tf}"
                    data[key] = self.calculate_indicators(df)
        return data

    def calculate_indicators(self, df):
        for length in [21, 50, 99, 200]:
            df.ta.ema(length=length, append=True)
        
        df.ta.rsi(length=14, append=True)
        df.ta.stochrsi(append=True)
        df.ta.vwap(append=True)
        df.ta.adx(append=True)
        df.ta.atr(append=True)
        
        try:
            df.ta.cdl_pattern(name="all", append=True, use_talib=False) 
        except:
            pass 

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
        # Convert directly to numpy arrays to avoid indexing errors
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

                base_score = Config.WEIGHTS.get(timeframe, 1)

                touch_bonus = min(len(cluster) * 0.2, 5.0)
                
                final_weight = base_score + touch_bonus
                
                zones.append({
                    'price': float(np.mean(cluster)),
                    'source': f"{timeframe} S/R ({len(cluster)}x)", 
                    'weight': final_weight
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
        if df_5m['EMA_21'].iloc[-1] > df_5m['EMA_50'].iloc[-1]: score += 1
        else: score -= 1
        
        desc = "Neutral"
        if score >= 2: desc = "Bullish"
        if score <= -2: desc = "Bearish"
        return {'score': int(score), 'description': desc}

    def analyze_market_context(self, sol_5m, btc_5m):
        warnings_list = []
        is_safe = True
        
        if btc_5m is not None:
            btc_open = btc_5m['open'].iloc[-3]
            btc_close = btc_5m['close'].iloc[-1]
            btc_change = (btc_close - btc_open) / btc_open
            
            if btc_change < -0.005: 
                warnings_list.append("⚠️ BTC Dumping")
                is_safe = False
            elif btc_change > 0.005:
                warnings_list.append("🚀 BTC Pumping")
                is_safe = False

        curr_vol = sol_5m['volume'].iloc[-1]
        avg_vol = sol_5m['Volume_MA_20'].iloc[-1]
        if curr_vol > avg_vol * 2.0:
            warnings_list.append("🌊 Volume Surge")
            is_safe = False
            
        adx = sol_5m['ADX_14'].iloc[-1]
        if adx > 35:
            warnings_list.append(f"🔥 Strong Trend (ADX {adx:.0f})")
            is_safe = False
            
        return is_safe, warnings_list

    def generate_levels(self, data_frames):
        master_levels = []
        df_d = data_frames.get(f"{Config.SYMBOL}_1d")
        if df_d is not None:
            prev = df_d.iloc[-2]
            master_levels.append({'price': float(prev['high']), 'source': 'PDH', 'weight': 8})
            master_levels.append({'price': float(prev['low']), 'source': 'PDL', 'weight': 8})
        
        for tf in Config.TIMEFRAMES:
            df = data_frames.get(f"{Config.SYMBOL}_{tf}")
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
                    'price': float(price),
                    'score': int(score),
                    'sources': sources, 
                    'confirmations': [],
                    'warnings': []
                })
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results

def analysis_worker(window):
    analyzer = MarketAnalyzer()
    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching data...")
            data_frames = analyzer.get_all_data()
            if not data_frames:
                time.sleep(10)
                continue

            sol_5m = data_frames.get(f"{Config.SYMBOL}_5m")
            btc_5m = data_frames.get(f"{Config.BTC_SYMBOL}_5m")
            sol_1h = data_frames.get(f"{Config.SYMBOL}_1h")

            if sol_5m is None: continue

            current_price = float(sol_5m['close'].iloc[-1])
            sentiment = analyzer.analyze_sentiment(sol_5m, sol_1h)
            is_safe, context_warnings = analyzer.analyze_market_context(sol_5m, btc_5m)
            raw_levels = analyzer.generate_levels(data_frames)
            zones = analyzer.cluster_confluence(raw_levels)
            
            for z in zones:
                if current_price > z['price'] and "⚠️ BTC Dumping" in context_warnings:
                    z['warnings'].append("BTC Dump Risk")
                if current_price < z['price'] and "🚀 BTC Pumping" in context_warnings:
                    z['warnings'].append("BTC Pump Risk")
                if sol_5m['ADX_14'].iloc[-1] > 35:
                     z['warnings'].append("High Momentum")
                     
                if len(z['warnings']) == 0: z['confidence'] = "High"
                elif len(z['warnings']) == 1: z['confidence'] = "Medium"
                else: z['confidence'] = "Low"

            upper = current_price * (1 + Config.SCALPER_RANGE)
            lower = current_price * (1 - Config.SCALPER_RANGE)
            scalper_zones = [z for z in zones if lower <= z['price'] <= upper]

            payload = {
                "current_price": current_price,
                "sentiment": sentiment,
                "market_warnings": context_warnings,
                "potential_entries": zones[:12],
                "scalper_entries": scalper_zones,
                "divergence_status": analyzer.detect_divergence(sol_5m),
                "market_regime": f"ADX: {float(sol_1h['ADX_14'].iloc[-1]):.1f}",
                "volatility": f"ATR: {float(sol_5m['ATRr_14'].iloc[-1]):.2f}",
                "status": f"Updated: {datetime.now().strftime('%H:%M:%S')}"
            }
            json_payload = json.dumps(payload, cls=NumpyEncoder)
            if window:
                window.evaluate_js(f"window.updateData({json_payload})")
        except Exception as e:
            print(f"Loop Error: {e}")
        time.sleep(Config.LOOP_INTERVAL)

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
            <h1>Vivi's Terminal <span style="font-size:0.5em; color:var(--accent-blue)">SOL/USDT</span></h1>
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
        print("⚠️  WARNING: Binance API Keys not found in .env.")
    window = webview.create_window('Vivi Scalp Terminal', app, width=1300, height=950, background_color='#0b0e11')
    t = threading.Thread(target=analysis_worker, args=(window,), daemon=True)
    t.start()
    webview.start()