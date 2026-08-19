from datetime import datetime, timezone
import os
import sqlite3
import pandas as pd
import requests
import yfinance as yf
from google import genai

DB_FILE = "trades.db"

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
                  f"Session: {session_name} • 4H Trend Stacked • Risk < 2.5%"
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


def auto_check_open_trades_and_alert():
  """Checks any logged trades and notifies Discord if TP or SL was triggered."""
  if not os.path.exists(DB_FILE):
    return

  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("SELECT * FROM trades WHERE status = 'OPEN'")
  open_trades = cursor.fetchall()

  for trade in open_trades:
    trade_id = trade[0]
    asset_name = trade[2]
    direction = trade[3]
    entry_price = float(trade[4])
    stop_loss = float(trade[5])
    take_profit = float(trade[6])
    risk_amt = float(trade[7])
    reward_amt = float(trade[8])

    symbol = ASSETS.get(asset_name)
    if not symbol or stop_loss == 0.0 or take_profit == 0.0:
      continue

    try:
      ticker = yf.Ticker(symbol)
      df = ticker.history(period="3d", interval="1h")
      if df.empty:
        continue

      recent_high = df["High"].max()
      recent_low = df["Low"].min()

      outcome = None
      pnl = 0.0

      if "BUY" in direction.upper():
        if recent_high >= take_profit:
          outcome = "WIN"
          pnl = reward_amt
        elif recent_low <= stop_loss:
          outcome = "LOSS"
          pnl = -risk_amt

      elif "SELL" in direction.upper():
        if recent_low <= take_profit:
          outcome = "WIN"
          pnl = reward_amt
        elif recent_high >= stop_loss:
          outcome = "LOSS"
          pnl = -risk_amt

      if outcome:
        cursor.execute(
            "UPDATE trades SET status = ?, pnl = ? WHERE id = ?",
            (outcome, pnl, trade_id),
        )
        conn.commit()

        # Send resolution alert to Discord
        msg = f"**Trade #{trade_id} ({asset_name} - {direction}) has hit its target!**\n\n• **Outcome:** `{outcome}`\n• **Realized PnL:** `${pnl:+.2f}`"
        send_discord_alert(
            title=f"🔔 TRADE AUTO-RESOLVED: {outcome} (${pnl:+.2f})",
            description=msg,
            asset_name=asset_name,
            color=0x00FF88 if outcome == "WIN" else 0xFF3366,
        )
    except Exception:
      continue

  conn.close()


def check_markets_strict():
  session = get_current_session()
  dxy_bias, dxy_price = fetch_dxy_bias()
  confirmed_setups = []
  primary_asset = "EUR/USD"

  # First resolve any active orders
  auto_check_open_trades_and_alert()

  for name, symbol in ASSETS.items():
    try:
      ticker = yf.Ticker(symbol)
      df_1h = ticker.history(period="30d", interval="1h", timeout=10)
      if df_1h.empty or len(df_1h) < 100:
        continue

      df_1h["EMA_9"] = df_1h["Close"].ewm(span=9, adjust=False).mean()
      df_1h["EMA_50"] = df_1h["Close"].ewm(span=50, adjust=False).mean()
      df_1h["EMA_200"] = df_1h["Close"].ewm(span=200, adjust=False).mean()
      df_1h["RSI"] = compute_rsi(df_1h["Close"])
      df_1h["ATR"] = compute_atr(df_1h)

      curr_1h = df_1h.iloc[-1]
      price = curr_1h["Close"]
      ema9_1h = curr_1h["EMA_9"]
      ema50_1h = curr_1h["EMA_50"]
      ema200_1h = curr_1h["EMA_200"]
      rsi = curr_1h["RSI"]
      atr = curr_1h["ATR"]

      # 4-Hour Trend
      df_4h = (
          df_1h.resample("4h")
          .agg({
              "Open": "first",
              "High": "max",
              "Low": "min",
              "Close": "last",
              "Volume": "sum",
          })
          .dropna()
      )
      df_4h["EMA_50"] = df_4h["Close"].ewm(span=50, adjust=False).mean()
      ema50_4h = df_4h["EMA_50"].iloc[-1]

      is_4h_bullish = price > ema50_4h
      is_4h_bearish = price < ema50_4h

      is_1h_bullish = (
          price > ema200_1h
          and ema9_1h > ema50_1h
          and 40 <= rsi <= 60
          and curr_1h["Low"] <= ema9_1h * 1.001
          and curr_1h["Close"] > ema9_1h
      )

      is_1h_bearish = (
          price < ema200_1h
          and ema9_1h < ema50_1h
          and 40 <= rsi <= 60
          and curr_1h["High"] >= ema9_1h * 0.999
          and curr_1h["Close"] < ema9_1h
      )

      if is_1h_bullish and is_4h_bullish:
        if name in ["EUR/USD", "GBP/USD", "Gold / USD"] and dxy_bias == "BULLISH":
          print(f"Skipping {name} BUY: Blocked by Bullish DXY.")
          continue
        primary_asset = name
        confirmed_setups.append(f"""
ASSET: {name} (4H-STACKED BUY SETUP)
- Live Price: {price:.5f} | 14 ATR: {atr:.5f} (1.5x SL Buffer: {1.5 * atr:.5f})
- 1H EMAs: 9 EMA: {ema9_1h:.5f} | 50 EMA: {ema50_1h:.5f} | 200 EMA: {ema200_1h:.5f}
- 4H 50 EMA: {ema50_4h:.5f} (Bullish Macro Flow)
- RSI: {rsi:.1f} | Macro DXY: {dxy_price:.2f} ({dxy_bias})
""")

      elif is_1h_bearish and is_4h_bearish:
        if name in ["EUR/USD", "GBP/USD", "Gold / USD"] and dxy_bias == "BEARISH":
          print(f"Skipping {name} SELL: Blocked by Bearish DXY.")
          continue
        primary_asset = name
        confirmed_setups.append(f"""
ASSET: {name} (4H-STACKED SELL SETUP)
- Live Price: {price:.5f} | 14 ATR: {atr:.5f} (1.5x SL Buffer: {1.5 * atr:.5f})
- 1H EMAs: 9 EMA: {ema9_1h:.5f} | 50 EMA: {ema50_1h:.5f} | 200 EMA: {ema200_1h:.5f}
- 4H 50 EMA: {ema50_4h:.5f} (Bearish Macro Flow)
- RSI: {rsi:.1f} | Macro DXY: {dxy_price:.2f} ({dxy_bias})
""")

    except Exception as e:
      print(f"Error checking {name}: {e}")

  if not confirmed_setups:
    print(
        f"Zero setups passed 4H Trend Stacking during {session}. System silent."
    )
    return

  market_text = "\n".join(confirmed_setups)
  prompt = f"""
You are an ultra-conservative FX Risk Guardian.
Review these 4H-Trend Stacked setups detected during {session}:
{market_text}

Rule: If the setup lacks clean structure or contradicts DXY, reply ONLY with 'ABORT'.
If valid, format an ATR-sized trade card:
1. Setup: [Pair] [BUY/SELL LIMIT]
2. Active Session: {session}
3. Recommended Entry Price:
4. Dynamic ATR Stop Loss: (1.5x ATR buffer, dollar risk under $2.00 on $100 capital)
5. Take Profit Target: (3.0x ATR buffer for 1:2 R:R)
6. 4H Trend Alignment Thesis: 1 sentence on why the 4H trend confirms the 1H pullback.
7. 3-step execution plan for TradingView on phone.
"""

  client = genai.Client(api_key=GEMINI_API_KEY)
  try:
    response = client.models.generate_content(
        model="gemini-3.6-flash", contents=prompt
    )
    if "ABORT" not in response.text.upper():
      send_discord_alert(
          title=f"🎯 [{session.upper()}] 4H-STACKED SIGNAL",
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
