from datetime import datetime, timezone
import os
import pandas as pd
import requests
import yfinance as yf
from google import genai

ASSETS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "Gold / USD": "GC=F",
}

DXY_SYMBOL = "DX-Y.NYB"

TRADINGVIEW_SYMBOLS = {
    "EUR/USD": "FX:EURUSD",
    "GBP/USD": "FX:GBPUSD",
    "USD/JPY": "FX:USDJPY",
    "Gold / USD": "OANDA:XAUUSD",
}

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


def get_current_session():
  current_utc_hour = datetime.now(timezone.utc).hour
  if 7 <= current_utc_hour <= 10:
    return "London Open (High Liquidity)"
  elif 12 <= current_utc_hour <= 16:
    return "London / NY Overlap (Peak Daily Volume)"
  else:
    return "Off-Peak / Custom Trigger"


def send_discord_alert(title, description, asset_name, color=0x00FF88):
  if not DISCORD_WEBHOOK_URL:
    return
  session_name = get_current_session()
  tv_sym = TRADINGVIEW_SYMBOLS.get(asset_name, "FX:EURUSD")
  tv_link = f"https://www.tradingview.com/chart/?symbol={tv_sym}&interval=60"

  formatted_description = f"{description}\n\n🔗 **[📱 Tap to Open {asset_name} on TradingView (1H)]({tv_link})**"

  payload = {
      "username": "AI Trading Copilot",
      "avatar_url": "https://cdn-icons-png.flaticon.com/512/2936/2936886.png",
      "embeds": [{
          "title": title,
          "url": tv_link,
          "description": formatted_description,
          "color": color,
          "footer": {
              "text": (
                  f"Session: {session_name} • DXY Filter Active • Risk < 2.5%"
              )
          },
      }],
  }
  requests.post(DISCORD_WEBHOOK_URL, json=payload)


def compute_rsi(series, period=14):
  delta = series.diff()
  gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
  rs = gain / loss
  return 100 - (100 / (1 + rs))


def compute_atr(df, period=14):
  high = df["High"]
  low = df["Low"]
  close = df["Close"].shift(1)
  tr1 = high - low
  tr2 = (high - close).abs()
  tr3 = (low - close).abs()
  tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
  return tr.rolling(window=period).mean()


def fetch_dxy_bias():
  try:
    ticker = yf.Ticker(DXY_SYMBOL)
    df = ticker.history(period="10d", interval="1h", timeout=10)
    if df.empty or len(df) < 50:
      return "NEUTRAL", 0.0
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()
    price = df["Close"].iloc[-1]
    ema9 = df["EMA_9"].iloc[-1]
    ema50 = df["EMA_50"].iloc[-1]

    if price > ema50 and ema9 > ema50:
      return "BULLISH", price
    elif price < ema50 and ema9 < ema50:
      return "BEARISH", price
    return "NEUTRAL", price
  except Exception:
    return "NEUTRAL", 0.0


def check_markets_strict():
  session = get_current_session()
  dxy_bias, dxy_price = fetch_dxy_bias()
  confirmed_setups = []
  primary_asset = "EUR/USD"

  for name, symbol in ASSETS.items():
    try:
      ticker = yf.Ticker(symbol)
      df = ticker.history(period="10d", interval="1h", timeout=10)
      if df.empty or len(df) < 50:
        continue

      df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
      df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()
      df["EMA_200"] = df["Close"].ewm(span=200, adjust=False).mean()
      df["RSI"] = compute_rsi(df["Close"])
      df["ATR"] = compute_atr(df)

      curr = df.iloc[-1]
      price = curr["Close"]
      ema9 = curr["EMA_9"]
      ema50 = curr["EMA_50"]
      ema200 = curr["EMA_200"]
      rsi = curr["RSI"]
      atr = curr["ATR"]

      # Strict Technical Bounce Rules
      is_bullish = (
          price > ema200
          and ema9 > ema50
          and 40 <= rsi <= 60
          and curr["Low"] <= ema9 * 1.001
          and curr["Close"] > ema9
      )

      is_bearish = (
          price < ema200
          and ema9 < ema50
          and 40 <= rsi <= 60
          and curr["High"] >= ema9 * 0.999
          and curr["Close"] < ema9
      )

      # DXY Correlation Filter Enforcement
      # If DXY is BULLISH, block EUR/GBP/Gold Buys
      if is_bullish:
        if name in ["EUR/USD", "GBP/USD", "Gold / USD"] and dxy_bias == "BULLISH":
          print(f"Skipping {name} BUY: Blocked by Bullish DXY.")
          continue
        primary_asset = name
        confirmed_setups.append(f"""
ASSET: {name} (BUY SETUP)
- Live Price: {price:.5f} | 14 ATR: {atr:.5f} (1.5x SL Buffer: {1.5 * atr:.5f})
- 9 EMA: {ema9:.5f} | 50 EMA: {ema50:.5f} | 200 EMA: {ema200:.5f}
- RSI: {rsi:.1f} | Macro DXY: {dxy_price:.2f} ({dxy_bias})
""")

      # If DXY is BEARISH, block EUR/GBP/Gold Sells and USD/JPY Buys
      elif is_bearish:
        if name in ["EUR/USD", "GBP/USD", "Gold / USD"] and dxy_bias == "BEARISH":
          print(f"Skipping {name} SELL: Blocked by Bearish DXY.")
          continue
        primary_asset = name
        confirmed_setups.append(f"""
ASSET: {name} (SELL SETUP)
- Live Price: {price:.5f} | 14 ATR: {atr:.5f} (1.5x SL Buffer: {1.5 * atr:.5f})
- 9 EMA: {ema9:.5f} | 50 EMA: {ema50:.5f} | 200 EMA: {ema200:.5f}
- RSI: {rsi:.1f} | Macro DXY: {dxy_price:.2f} ({dxy_bias})
""")

    except Exception as e:
      print(f"Error checking {name}: {e}")

  if not confirmed_setups:
    print(
        f"Zero setups passed strict DXY filter during {session}. System silent."
    )
    return

  market_text = "\n".join(confirmed_setups)
  prompt = f"""
You are an ultra-conservative FX Risk Guardian.
Review these technically validated setups with DXY Macro alignment:
{market_text}

Rule: If the setup lacks clean structure or contradicts DXY, reply ONLY with 'ABORT'.
If valid, format an ATR-sized trade card:
1. Setup: [Pair] [BUY/SELL LIMIT]
2. Active Session: {session} (DXY: {dxy_bias})
3. Recommended Entry Price:
4. Dynamic ATR Stop Loss: (1.5x ATR buffer, dollar risk under $2.00 on $100 capital)
5. Take Profit Target: (3.0x ATR buffer for 1:2 R:R)
6. DXY Alignment Thesis: 1 sentence on why the Dollar Index confirms this direction.
7. 3-step execution plan for TradingView on phone.
"""

  client = genai.Client(api_key=GEMINI_API_KEY)
  try:
    response = client.models.generate_content(
        model="gemini-3.6-flash", contents=prompt
    )
    if "ABORT" not in response.text.upper():
      send_discord_alert(
          title=f"🎯 [{session.upper()}] DXY-ALIGNED SIGNAL",
          description=response.text,
          asset_name=primary_asset,
          color=0x00FF88 if "BUY" in market_text else 0xFF3366,
      )
    else:
      print("AI Gatekeeper rejected setup.")
  except Exception as e:
    print(f"Error: {e}")


if __name__ == "__main__":
  check_markets_strict()
