import os
import requests
import yfinance as yf
from google import genai

ASSETS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "Gold / USD": "GC=F",
}

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


def send_discord_alert(title, description, color=0x00FF88):
  if not DISCORD_WEBHOOK_URL:
    return
  payload = {
      "username": "AI Trading Copilot",
      "avatar_url": "https://cdn-icons-png.flaticon.com/512/2936/2936886.png",
      "embeds": [{
          "title": title,
          "description": description,
          "color": color,
          "footer": {"text": "Strict 100% Confluence Model • Risk < 2.5%"},
      }],
  }
  requests.post(DISCORD_WEBHOOK_URL, json=payload)


def compute_rsi(series, period=14):
  delta = series.diff()
  gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
  rs = gain / loss
  return 100 - (100 / (1 + rs))


def check_markets_strict():
  confirmed_setups = []

  for name, symbol in ASSETS.items():
    try:
      ticker = yf.Ticker(symbol)
      df = ticker.history(period="10d", interval="1h", timeout=10)
      if df.empty or len(df) < 50:
        continue

      # 1. Technical Indicators
      df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
      df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()
      df["EMA_200"] = df["Close"].ewm(span=200, adjust=False).mean()
      df["RSI"] = compute_rsi(df["Close"])

      curr = df.iloc[-1]
      prev = df.iloc[-2]

      price = curr["Close"]
      ema9 = curr["EMA_9"]
      ema50 = curr["EMA_50"]
      ema200 = curr["EMA_200"]
      rsi = curr["RSI"]

      # 2. Strict Mathematical Conditions
      # Bullish: Macro uptrend (Price > 200 EMA & EMA9 > EMA50) + Healthy RSI (40-60) + EMA 9 Rejection Wick
      is_bullish_a_plus = (
          price > ema200
          and ema9 > ema50
          and 40 <= rsi <= 60
          and curr["Low"] <= ema9 * 1.001
          and curr["Close"] > ema9
      )

      # Bearish: Macro downtrend (Price < 200 EMA & EMA9 < EMA50) + Healthy RSI (40-60) + EMA 9 Rejection Wick
      is_bearish_a_plus = (
          price < ema200
          and ema9 < ema50
          and 40 <= rsi <= 60
          and curr["High"] >= ema9 * 0.999
          and curr["Close"] < ema9
      )

      if is_bullish_a_plus:
        confirmed_setups.append(f"""
                ASSET: {name} (BUY SETUP)
                - Live Price: {price:.5f}
                - 9 EMA: {ema9:.5f} | 50 EMA: {ema50:.5f} | 200 EMA: {ema200:.5f}
                - RSI (14): {rsi:.1f}
                - Price Action: Rejection bounce off 9 EMA confirmed.
                """)
      elif is_bearish_a_plus:
        confirmed_setups.append(f"""
                ASSET: {name} (SELL SETUP)
                - Live Price: {price:.5f}
                - 9 EMA: {ema9:.5f} | 50 EMA: {ema50:.5f} | 200 EMA: {ema200:.5f}
                - RSI (14): {rsi:.1f}
                - Price Action: Rejection bounce off 9 EMA confirmed.
                """)

    except Exception as e:
      print(f"Error checking {name}: {e}")

  if not confirmed_setups:
    print("Zero setups matched 100% confluence criteria. System silent.")
    return

  # 3. AI Gatekeeper Verification
  market_text = "\n".join(confirmed_setups)
  prompt = f"""
    You are an ultra-conservative institutional risk manager.
    Review these technically validated setups:
    {market_text}

    Rule: If the setup does not have clear trend confluence, reply ONLY with 'ABORT'.
    If it represents an A+ setup, provide:
    1. Setup: [Pair] [BUY/SELL LIMIT]
    2. Entry Price:
    3. Stop Loss: (Strictly under $2.00 risk on a $100 capital base)
    4. Take Profit: (At least 1:2 Risk-to-Reward)
    5. Core Thesis: Why this satisfies maximum confluence.
    6. 3-step execution for TradingView.
    """

  client = genai.Client(api_key=GEMINI_API_KEY)
  try:
    response = client.models.generate_content(
        model="gemini-3.6-flash", contents=prompt
    )
    if "ABORT" not in response.text.upper():
      send_discord_alert(
          title="🎯 A+ MAXIMUM CONFLUENCE SIGNAL",
          description=response.text,
          color=0x00FF88 if "BUY" in market_text else 0xFF3366,
      )
    else:
      print("AI Gatekeeper rejected setup due to incomplete confluence.")
  except Exception as e:
    print(f"Error: {e}")


if __name__ == "__main__":
  check_markets_strict()
