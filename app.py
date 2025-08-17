import threading
import time
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
from dotenv import load_dotenv  

load_dotenv()

# --- CONFIGURATION ---
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

if not BINANCE_API_KEY or not BINANCE_API_SECRET:
    print("FATAL ERROR: Binance API Key/Secret not found.")
    exit() 

# --- NEW: Configuration for Scalper View ---
SCALPER_VIEW_RANGE_PERCENT = 0.03 # e.g., 0.03 = show levels within +/- 3% of the current price

SYMBOL = 'SOL/USDT'
TIMEFRAMES = ['1d', '1h', '15m', '5m']
LOOKBACK_DAYS = 90
CONVERGENCE_PROXIMITY_PERCENT = 0.005
ALERT_PROXIMITY_PERCENT = 0.005
LOOP_INTERVAL_SECONDS = 180
DIVERGENCE_LOOKBACK = 60
ADX_TREND_THRESHOLD = 25
VOLUME_SPIKE_FACTOR = 1.75

warnings.simplefilter(action='ignore', category=pd.errors.SettingWithCopyWarning)
warnings.simplefilter(action='ignore', category=FutureWarning)

app = Flask(__name__)

#<editor-fold desc=" --- Analysis Logic (Unchanged) --- ">
exchange = ccxt.binance({'apiKey': BINANCE_API_KEY, 'secret': BINANCE_API_SECRET})

def send_notification(title, message):
    try: notification.notify(title=title, message=message, app_name='Crypto Scanner', timeout=30); print("--- NOTIFICATION SENT ---")
    except Exception as e: print(f"Error sending notification: {e}")

def fetch_data(symbol, timeframe, lookback_days):
    try:
        since = exchange.parse8601(pd.to_datetime('now', utc=True) - pd.to_timedelta(f'{lookback_days}d')); ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']); df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms'); df.set_index('timestamp', inplace=True); return df
    except Exception as e: print(f"Error fetching data for {timeframe}: {e}"); return None

def calculate_indicators(df):
    if df is None or df.empty: return df
    df.ta.ema(length=21, append=True); df.ta.ema(length=50, append=True); df.ta.ema(length=99, append=True); df.ta.ema(length=200, append=True)
    df.ta.rsi(length=14, append=True); df.ta.vwap(append=True)
    df.ta.adx(append=True); df.ta.atr(append=True)
    df.ta.cdl_pattern(name="all", append=True, use_talib=False)
    df['Volume_MA_20'] = df.ta.sma(length=20, close='volume')
    highest_high = df['high'].max(); lowest_low = df['low'].min(); diff = highest_high - lowest_low
    df['fib_0.236'] = highest_high - (diff * 0.236); df['fib_0.382'] = highest_high - (diff * 0.382); df['fib_0.500'] = highest_high - (diff * 0.500); df['fib_0.618'] = highest_high - (diff * 0.618); df['fib_0.786'] = highest_high - (diff * 0.786)
    return df

def analyze_sentiment(df_5m, df_1h):
    sentiment = {'score': 0, 'description': 'Neutral'}
    if df_5m is None or df_1h is None or df_5m.empty or df_1h.empty: return sentiment
    current_price = df_5m['close'].iloc[-1]
    if 'EMA_200' in df_1h.columns and pd.notna(df_1h['EMA_200'].iloc[-1]):
        if current_price > df_1h['EMA_200'].iloc[-1]: sentiment['score'] += 2
        else: sentiment['score'] -= 2
    if 'VWAP_D' in df_5m.columns and pd.notna(df_5m['VWAP_D'].iloc[-1]):
        if current_price > df_5m['VWAP_D'].iloc[-1]: sentiment['score'] += 1
        else: sentiment['score'] -= 1
    if 'EMA_21' in df_5m.columns and 'EMA_50' in df_5m.columns and pd.notna(df_5m['EMA_21'].iloc[-1]) and pd.notna(df_5m['EMA_50'].iloc[-1]):
        if df_5m['EMA_21'].iloc[-1] > df_5m['EMA_50'].iloc[-1]: sentiment['score'] += 1
        else: sentiment['score'] -= 1
    if sentiment['score'] > 1: sentiment['description'] = 'Bullish'
    elif sentiment['score'] < -1: sentiment['description'] = 'Bearish'
    return sentiment

def detect_rsi_divergence(df, timeframe, lookback):
    if df is None or len(df) < lookback or 'RSI_14' not in df.columns: return "N/A"
    df_slice = df.iloc[-lookback:]; order=5 
    price_highs_idx = argrelextrema(df_slice['high'].values, np.greater, order=order)[0]; price_lows_idx = argrelextrema(df_slice['low'].values, np.less, order=order)[0]
    rsi_highs_idx = argrelextrema(df_slice['RSI_14'].values, np.greater, order=order)[0]; rsi_lows_idx = argrelextrema(df_slice['RSI_14'].values, np.less, order=order)[0]
    if len(price_highs_idx) >= 2 and len(rsi_highs_idx) >= 2:
        if abs(price_highs_idx[-1] - rsi_highs_idx[-1]) < (order + 1):
            if df_slice['high'].iloc[price_highs_idx[-1]] > df_slice['high'].iloc[price_highs_idx[-2]] and df_slice['RSI_14'].iloc[rsi_highs_idx[-1]] < df_slice['RSI_14'].iloc[rsi_highs_idx[-2]]: return f"Bearish on {timeframe}"
    if len(price_lows_idx) >= 2 and len(rsi_lows_idx) >= 2:
        if abs(price_lows_idx[-1] - rsi_lows_idx[-1]) < (order + 1):
            if df_slice['low'].iloc[price_lows_idx[-1]] < df_slice['low'].iloc[price_lows_idx[-2]] and df_slice['RSI_14'].iloc[rsi_lows_idx[-1]] > df_slice['RSI_14'].iloc[rsi_lows_idx[-2]]: return f"Bullish on {timeframe}"
    return "None"

def find_sr_zones(df, proximity_percent=0.005, min_touches=2):
    if df is None or df.empty: return []
    highs_idx = argrelextrema(df['high'].values, np.greater_equal, order=5)[0]
    lows_idx = argrelextrema(df['low'].values, np.less_equal, order=5)[0]
    pivots = np.concatenate((df['high'].iloc[highs_idx].values, df['low'].iloc[lows_idx].values))
    if len(pivots) == 0: return []
    pivots = np.sort(pivots)
    zones = []; current_zone = [pivots[0]]
    for i in range(1, len(pivots)):
        if (pivots[i] - current_zone[-1]) / current_zone[-1] < proximity_percent: current_zone.append(pivots[i])
        else: zones.append(current_zone); current_zone = [pivots[i]]
    zones.append(current_zone)
    sr_zones = []
    for zone in zones:
        if len(zone) >= min_touches:
            sr_zones.append({'price': np.mean(zone), 'touches': len(zone)})
    return sr_zones

def find_confluence_zones(all_levels):
    if not all_levels: return []
    all_levels.sort(key=lambda x: x['price'])
    confluence_zones = []; current_zone = [all_levels[0]]
    for i in range(1, len(all_levels)):
        anchor_price = current_zone[0]['price']
        if abs(all_levels[i]['price'] - anchor_price) / anchor_price < CONVERGENCE_PROXIMITY_PERCENT: current_zone.append(all_levels[i])
        else: confluence_zones.append(current_zone); current_zone = [all_levels[i]]
    confluence_zones.append(current_zone)
    potential_entries = []
    for zone in confluence_zones:
        if len(zone) > 1:
            avg_price = np.mean([l['price'] for l in zone]); score = sum(l.get('weight', 1) for l in zone); sources = [l['source'] for l in zone]
            potential_entries.append({'price': avg_price, 'score': int(score), 'sources': sources, 'confirmations': []})
    potential_entries.sort(key=lambda x: x['score'], reverse=True); return potential_entries
#</editor-fold>

def analysis_worker(window):
    print("Analysis worker started.")
    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Running analysis cycle...")
            data_frames = {}; all_data_fetched = True
            for tf in TIMEFRAMES:
                df = fetch_data(SYMBOL, tf, LOOKBACK_DAYS)
                if df is not None and not df.empty: data_frames[tf] = calculate_indicators(df)
                else: all_data_fetched = False; break
            if not all_data_fetched:
                print("Fetch failed. Waiting..."); time.sleep(60); continue

            master_levels = []
            df_daily = data_frames['1d']
            daily_df_resampled = df_daily.resample('D').agg({'high': 'max', 'low': 'min'})
            weekly_df_resampled = df_daily.resample('W').agg({'high': 'max', 'low': 'min'})
            monthly_df_resampled = df_daily.resample('ME').agg({'high': 'max', 'low': 'min'})
            key_levels_map = {
                "Prev Day Low (PDL)": daily_df_resampled['low'].iloc[-2] if len(daily_df_resampled) > 1 else None, "Prev Day High (PDH)": daily_df_resampled['high'].iloc[-2] if len(daily_df_resampled) > 1 else None,
                "Prev Week Low (PWL)": weekly_df_resampled['low'].iloc[-2] if len(weekly_df_resampled) > 1 else None, "Prev Week High (PWH)": weekly_df_resampled['high'].iloc[-2] if len(weekly_df_resampled) > 1 else None,
                "Prev Month Low (PML)": monthly_df_resampled['low'].iloc[-2] if len(monthly_df_resampled) > 1 else None, "Prev Month High (PMH)": monthly_df_resampled['high'].iloc[-2] if len(monthly_df_resampled) > 1 else None,
            }
            for name, price in key_levels_map.items():
                if price: master_levels.append({'price': price, 'source': name, 'weight': 8})
            for tf in ['1d', '1h']:
                sr_zones = find_sr_zones(data_frames[tf])
                for zone in sr_zones:
                    weight = (15 if tf == '1d' else 5) + zone['touches']; master_levels.append({'price': zone['price'], 'source': f"{tf} S/R Zone ({zone['touches']} touches)", 'weight': weight})
            tf_weight_map = {'1d': 5, '1h': 2, '15m': 1, '5m': 0}
            for tf in TIMEFRAMES:
                df = data_frames.get(tf); last_row = df.iloc[-1]
                for ema in [21, 50, 99, 200]:
                    col_name = f'EMA_{ema}'; weight = tf_weight_map[tf] + (2 if ema in [99,200] and tf in ['1d', '1h'] else 0)
                    if col_name in last_row and pd.notna(last_row[col_name]): master_levels.append({'price': last_row[col_name], 'source': f'{tf} EMA {ema}', 'weight': weight})
                if tf != '1d' and 'VWAP_D' in last_row and pd.notna(last_row['VWAP_D']): 
                    master_levels.append({'price': last_row['VWAP_D'], 'source': f'{tf} VWAP', 'weight': tf_weight_map[tf] + 1})
                for fib in [0.236, 0.382, 0.500, 0.618, 0.786]:
                    col_name = f'fib_{fib:.3f}';
                    if col_name in last_row and pd.notna(last_row[col_name]): master_levels.append({'price': last_row[col_name], 'source': f'{tf} Fib {fib:.3f}', 'weight': tf_weight_map[tf]})
            
            all_entries = find_confluence_zones(master_levels)
            
            current_price = data_frames['5m']['close'].iloc[-1]
            sentiment = analyze_sentiment(data_frames['5m'], data_frames['1h'])
            divergence_status = detect_rsi_divergence(data_frames['5m'], '5m', DIVERGENCE_LOOKBACK)
            adx_value = data_frames['1h']['ADX_14'].iloc[-1]
            market_regime_text = f"TRENDING ({adx_value:.1f})" if adx_value > ADX_TREND_THRESHOLD else f"RANGING ({adx_value:.1f})"
            volatility_text = f"Volatility: {(data_frames['5m']['ATRr_14'].iloc[-1] / current_price) * 100:.2f}%"

            df_5m = data_frames['5m']
            for entry in all_entries:
                if abs(current_price - entry['price']) / entry['price'] < ALERT_PROXIMITY_PERCENT:
                    if df_5m['volume'].iloc[-1] > df_5m['Volume_MA_20'].iloc[-1] * VOLUME_SPIKE_FACTOR: entry['confirmations'].append("🔥 Volume Spike")
                    candle_cols = [col for col in df_5m.columns if col.startswith('CDL_')]; last_candle = df_5m[candle_cols].iloc[-1]; found_patterns = last_candle[last_candle != 0]
                    for pattern_name, value in found_patterns.items(): entry['confirmations'].append(f"🕯️ {pattern_name[4:]} ({'Bullish' if value > 0 else 'Bearish'})")
            
            # --- NEW: Filter for Scalper View ---
            price_upper_bound = current_price * (1 + SCALPER_VIEW_RANGE_PERCENT)
            price_lower_bound = current_price * (1 - SCALPER_VIEW_RANGE_PERCENT)
            scalper_entries = [e for e in all_entries if price_lower_bound <= e['price'] <= price_upper_bound]

            payload = { 
                "current_price": current_price, 
                "sentiment": sentiment, 
                "potential_entries": all_entries[:10], # The macro view
                "scalper_entries": scalper_entries, # The new filtered view
                "divergence_status": divergence_status, 
                "market_regime": market_regime_text, 
                "volatility": volatility_text, 
                "status": f"Last updated: {datetime.now().strftime('%H:%M:%S')}" 
            }
            
            if window:
                window.evaluate_js(f"window.updateData({payload})")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Update sent to GUI.")

        except Exception as e:
            print(f"An error occurred in the analysis worker: {e}")
        time.sleep(LOOP_INTERVAL_SECONDS)

# --- MODIFIED HTML with new "Scalper View" tab ---
HTML_CONTENT = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Vivi's Trade Helper</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>Vivi's Trade Helper</h1>
        </header>

        <div class="tabs">
            <button class="tab-button active" onclick="showTab('dashboard')">Macro View</button>
            <button class="tab-button" onclick="showTab('scalper')">Scalper View</button>
            <button class="tab-button" onclick="showTab('help')">Help & Info</button>
        </div>

        <div id="dashboard-content" class="tab-content active">
            <div class="dashboard">
                <div class="card" id="price-card"><div class="card-title">Current Price</div><div class="card-value" id="current-price">---</div></div>
                <div class="card" id="sentiment-card"><div class="card-title">Sentiment</div><div class="card-value" id="sentiment">---</div></div>
                <div class="card" id="divergence-card"><div class="card-title">RSI Divergence</div><div class="card-value" id="divergence">---</div></div>
                <div class="card" id="regime-card"><div class="card-title">Market Regime (1h ADX)</div><div class="card-value" id="market-regime">---</div><div class="card-subtitle" id="volatility">---</div></div>
            </div>
            <div class="zones-container-wrapper">
                <h2>Top Potential Entry Zones (Macro)</h2>
                <div id="zones-container"></div>
            </div>
        </div>
        
        <div id="scalper-content" class="tab-content">
             <div class="zones-container-wrapper">
                <h2>Nearby Entry Zones (+/- {SCALPER_VIEW_RANGE_PERCENT*100:.1f}%)</h2>
                <div id="scalper-zones-container"></div>
            </div>
        </div>

        <div id="help-content" class="tab-content">
            <div class="help-section">
                <h2>How This Tool Works</h2>
                <p>This tool analyzes market data to find high-probability bounce zones where multiple technical indicators converge.</p>
                <h2>Views Explained</h2>
                <h3>Macro View</h3>
                <p>This tab shows the highest conviction support and resistance zones based on long-term data (up to 90 days). These are major structural levels, but may be far from the current price. Ideal for swing trading or identifying major market turning points.</p>
                <h3>Scalper View</h3>
                <p>This tab filters all calculated zones to show only those within a tight range (+/- {SCALPER_VIEW_RANGE_PERCENT*100:.1f}%) of the current price. These are the most immediately actionable levels for short-term scalping and intraday trading.</p>
                
                <h2>The Dashboard Explained</h2>
                <h3>Sentiment</h3>
                <p>Provides a quick snapshot of the current market sentiment based on a scoring system:<br>
                    • Price vs 1h 200 EMA (+/- 2 pts), Price vs 5m VWAP (+/- 1 pt), 5m 21/50 EMA Cross (+/- 1 pt).</p>
                <h3>RSI Divergence</h3>
                <p>An early warning of a potential reversal. Bullish: Price makes a lower low, RSI makes a higher low. Bearish: Price makes a higher high, RSI makes a lower high.</p>
                <h3>Market Regime (1h ADX)</h3>
                <p>Measures the STRENGTH of the 1-hour trend.<br>
                    • RANGING (ADX < {ADX_TREND_THRESHOLD}): Good for bounce trading.<br>
                    • TRENDING (ADX > {ADX_TREND_THRESHOLD}): Dangerous for bounce trading; levels are more likely to break.</p>
                <h3>How is the Score Calculated?</h3>
                <p>A weighted sum of all indicators in a zone. Higher timeframe and multi-touch S/R zones are weighted much more heavily than low timeframe indicators.</p>
            </div>
        </div>
        
        <footer id="status-footer">Initializing...</footer>
    </div>
    <script src="/static/script.js"></script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_CONTENT)

if __name__ == '__main__':
    window = webview.create_window(
        'Vivi Trade Helper',
        app,
        width=1200,
        height=800,
        resizable=True,
        background_color='#1a1a1d'
    )
    
    analysis_thread = threading.Thread(target=analysis_worker, args=(window,), daemon=True)
    analysis_thread.start()
    
    webview.start()