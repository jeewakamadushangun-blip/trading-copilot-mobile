import os
import requests
import yfinance as yf
from google import genai

# --- CONFIGURATION ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


def send_discord_alert(title, description, color=0x00FF88):
  if not DISCORD_WEBHOOK_URL:
    print("Error: DISCORD_WEBHOOK_URL secret is missing.")
    return

  payload = {
      "username": "AI Trading Copilot",
      "avatar_url": "https://cdn-icons-png.flaticon.com/512/2936/2936886.png",
      "embeds": [{
          "title": title,
          "description": description,
          "color": color,
          "footer": {"text": "System Alert Test • Automated Cloud Scanner"},
      }],
  }
  response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
  print(f"Discord Webhook Response Code: {response.status_code}")


def test_notification():
  print("Testing market data fetch & AI signal generation...")

  # Fetch live EUR/USD price
  ticker = yf.Ticker("EURUSD=X")
  df = ticker.history(period="2d", interval="1h")
  current_price = df["Close"].iloc[-1] if not df.empty else 1.1668

  prompt = f"""
    You are a Forex Trading Risk Guardian.
    Generate a sample trade signal for testing Discord push notifications:
    - Asset: EUR/USD (Live Price: {current_price:.5f})
    - Direction: BUY LIMIT
    - Capital: $100.00 (Risk: strictly under $2.00)

    Include:
    1. Setup: BUY LIMIT
    2. Entry Price: {current_price - 0.0010:.5f}
    3. Stop Loss: {current_price - 0.0030:.5f} ($2.00 Risk)
    4. Take Profit: {current_price + 0.0040:.5f} ($4.00 Reward)
    5. 15-Second Action: 3 clean bullet points for TradingView.
    """

  client = genai.Client(api_key=GEMINI_API_KEY)
  response = client.models.generate_content(
      model="gemini-3.6-flash",
      contents=prompt,
  )

  send_discord_alert(
      title="🔔 [TEST ALERT] AI Trading Copilot Connection Verified",
      description=response.text,
      color=0x00FF88,
  )


if __name__ == "__main__":
  test_notification()
