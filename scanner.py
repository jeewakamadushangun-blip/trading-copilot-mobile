import os
import requests
import yfinance as yf
from google import genai

# --- CONFIGURATION ---
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
    print("Discord webhook not set.")
    return

  payload = {
      "username": "AI Trading Copilot",
      "avatar_url": "https://cdn-icons-png.flaticon.com/512/2936/2936886.png",
      "embeds": [{
          "title": title,
          "description": description,
          "color": color,
          "footer": {"text": "Institutional 1-Hour EMA Strategy • Risk < 2.5%"},
      }],
  }
  response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
  print(f"Discord response: {response.status_code}")


def check_markets():
  high_quality_setups = []

  for name, symbol in ASSETS.items():
    try:
      ticker = yf.Ticker(symbol)
      df = ticker.history(period="5d", interval="1h", timeout=10)
      if df.empty or len(df) < 30:
        continue

      df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
      df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()

      latest = df.iloc[-1]
      price = latest["Close"]
      ema9 = latest["EMA_9"]
      ema50 = latest["EMA_50"]

      # Condition for Strong Pullback near dynamic 9 EMA
      # Bullish: Price above 50 EMA and within 0.25% of 9 EMA
      # Bearish: Price below 50 EMA and within 0.25% of 9 EMA
      diff_pct = abs(price - ema9) / price * 100

      if price > ema50 and ema9 > ema50 and diff_pct < 0.35:
        high_quality_setups.append(
            f"🟢 **{name} (BUY PULLBACK)** | Price: {price:.5f} near 9 EMA:"
            f" {ema9:.5f}"
        )
      elif price < ema50 and ema9 < ema50 and diff_pct < 0.35:
        high_quality_setups.append(
            f"🔴 **{name} (SELL PULLBACK)** | Price: {price:.5f} near 9 EMA:"
            f" {ema9:.5f}"
        )

    except Exception as e:
      print(f"Error checking {name}: {e}")

  if not high_quality_setups:
    print("No A+ setups currently meeting entry conditions.")
    return

  # Generate AI Execution Blueprint
  market_summary = "\n".join(high_quality_setups)
  prompt = f"""
    You are a friendly Forex Risk Guardian.
    Strong market conditions detected:
    {market_summary}

    Write a short, clear trade alert for Discord:
    1. State the top pair and direction (BUY LIMIT or SELL LIMIT).
    2. Give the exact Entry, Stop Loss (max $2 loss for $100 balance), and Take Profit.
    3. 2 simple sentences explaining why this trade works.
    4. Exact 3-step action for TradingView on phone.
    Keep it concise and easy to read in 15 seconds.
    """

  client = genai.Client(api_key=GEMINI_API_KEY)
  try:
    response = client.models.generate_content(
        model="gemini-3.6-flash", contents=prompt
    )
    alert_text = response.text
    send_discord_alert(
        title="🚨 NEW HIGH-PROBABILITY TRADE SIGNAL",
        description=alert_text,
        color=0x00FF88 if "BUY" in market_summary else 0xFF3366,
    )
  except Exception as e:
    print(f"AI Generation Error: {e}")


if __name__ == "__main__":
  check_markets()
