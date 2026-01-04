🛠 Installation & Setup
1. Requirements
Ensure you have Python 3.12 installed. Run the following command to install dependencies:
code
Bash
pip install numpy scipy pandas pandas_ta ccxt plyer flask pywebview python-dotenv
2. API Keys
Create a file named .env in the project folder and add your Binance API keys (needed to fetch live data):
code
Env
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_secret_key_here
3. Running the App
code
Bash
python app.py
📊 Dashboard Indicators (Top Row)
The top row provides a "Weather Report" of the current market.
1. Sentiment
What it is: A composite score based on Price vs. 1H EMA 200 (Long-term trend), Price vs. 5m VWAP (Intraday value), and 5m EMA crosses.
Interpretation:
<span style="color:#0ecb81">Bullish:</span> Buyers are in control. Look for Longs at Support.
<span style="color:#f6465d">Bearish:</span> Sellers are in control. Look for Shorts at Resistance.
Neutral: Market is chopping. Good for range trading.
2. Market Regime (ADX)
What it is: Measures the strength of the trend, not the direction.
Interpretation:
ADX < 25 (Ranging): ✅ BEST for Bounce Trading. Support and Resistance levels are likely to hold.
ADX > 25 (Trending): ⚠️ CAUTION. A strong trend is forming. Counter-trend trades (e.g., catching a falling knife) are risky.
ADX > 35: ⛔ DANGER. The "Steamroller" is active. Levels will likely break.
3. RSI Status & Divergence
What it is: Standard RSI (Relative Strength Index) on the 5m chart.
Interpretation:
Overbought (>70): Price is expensive relative to recent history.
Oversold (<30): Price is cheap relative to recent history.
Note: In strong trends, price can stay Overbought/Oversold for a long time.
🎯 The Zones (Main Area)
The app generates two lists: Scalper View (levels close to price) and Macro View (major levels further away).
Anatomy of a Zone Card
Each card represents a specific price level calculated by the algorithm.
Price & Type:
SUPPORT: A floor where price might bounce up.
RESISTANCE: A ceiling where price might reject down.
Note: If price smashes through Support, it often becomes Resistance (and vice versa).
Confluence Score (The Blue Bar):
The app sums up the "weight" of every indicator at that price.
Score 1-5: Weak level. Likely to break.
Score 5-10: Moderate level.
Score 15+: Strong Wall. These are the levels you want to trade.
Sources:
Lists exactly what exists at this price (e.g., 1h EMA 200, PDL (Previous Day Low), 5m VWAP).
Tip: Higher timeframe indicators (1d, 1h) are much stronger than 5m indicators.
🛡️ The Safety System (Badges)
Since you trade with your entire capital, preservation is key. The app analyzes the broader market to assign a safety rating to every zone.
<span style="background:#0ecb81; color:white; padding:2px 5px; border-radius:4px;">SAFE</span>
Conditions: BTC is stable, ADX is low (Market is Ranging), and Volume is normal.
Action: This is a high-probability setup. You can trust the Confluence Score.
<span style="background:#f0b90b; color:black; padding:2px 5px; border-radius:4px;">CAUTION</span>
Conditions: One risk factor is present (e.g., BTC is moving slightly against you, or momentum is picking up).
Action: Wait for a candle close confirmation on the 1-minute or 5-minute chart before entering. Do not set blind limit orders.
<span style="background:#f6465d; color:white; padding:2px 5px; border-radius:4px;">RISKY</span>
Conditions: The "Steamroller" is coming.
BTC Dump/Pump Risk: Bitcoin is moving aggressively against your level.
High Momentum: ADX is > 35.
Volume Surge: Volume is spiking as it hits the level.
Action: DO NOT TRADE. The probability of the level holding is very low. The price will likely smash through.
⚡ How to Trade With This Tool
The "A+" Setup (Green Light)
Look for this specific combination to deploy capital:
Zone Score: > 12
Badge: <span style="color:#0ecb81">SAFE</span>
Market Regime: Ranging (ADX < 25)
Confirmations: You see "High Vol" or Candle Patterns appear on the card as price touches it.
The "Stay Away" Setup (Red Light)
Ignore the level if:
Badge: <span style="color:#f6465d">RISKY</span>
Warning Text: "BTC Dumping" or "Strong Trend".
Scenario: You are trying to buy Support, but Bitcoin is crashing -0.5% in the last 15 minutes. SOL follows BTC. If BTC dumps, SOL support does not matter.
Summary
Don't trade the "Numbers": Just because a level exists doesn't mean it will hold.
Trade the "Context": Use the badges. If the app says the market context is dangerous, trust it and sit on your hands.