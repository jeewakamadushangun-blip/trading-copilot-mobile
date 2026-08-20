from datetime import datetime
import json
import os
import sqlite3
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

# --- CONFIGURATION ---
# Discord Webhook URL (reads from Render Environment Variables or defaults to hardcoded)
DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL", "YOUR_DISCORD_WEBHOOK_URL_HERE"
)
DB_PATH = "trading_journal.db"


def init_db():
  """Initialize SQLite trade journaling database."""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            ticker TEXT,
            action TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            status TEXT
        )
    """)
  conn.commit()
  conn.close()


init_db()


def send_discord_alert(ticker, action, entry, sl, tp):
  """Dispatches rich embed cards directly to Discord."""
  if "YOUR_DISCORD_WEBHOOK_URL_HERE" in DISCORD_WEBHOOK_URL:
    print("[WARNING] Discord Webhook URL not configured.")
    return

  is_buy = action.upper() == "BUY"
  color = 3066993 if is_buy else 15158332  # Green for BUY, Red for SELL
  risk_pips = abs(entry - sl) * 10000
  reward_pips = abs(tp - entry) * 10000

  embed_payload = {
      "username": "AI Forex Gatekeeper",
      "avatar_url": "https://i.imgur.com/4M34hi2.png",
      "embeds": [{
          "title": f"🚨 High-Confidence Alert: {action.upper()} {ticker}",
          "color": color,
          "fields": [
              {
                  "name": "📌 Entry Price",
                  "value": f"`{entry:.5f}`",
                  "inline": True,
              },
              {
                  "name": "🛑 Stop Loss (-1R)",
                  "value": f"`{sl:.5f}` ({risk_pips:.1f} pips)",
                  "inline": True,
              },
              {
                  "name": "🎯 Take Profit (+2R)",
                  "value": f"`{tp:.5f}` ({reward_pips:.1f} pips)",
                  "inline": True,
              },
              {
                  "name": "📐 Execution Checklist",
                  "value": (
                      "• **Risk Limit:** 2.0% ($2.00 on $100)\n"
                      "• **Lot Size:** 0.01 micro lot\n"
                      "• **Order Type:** Limit Order near 9 EMA\n"
                      "• **Time In Force:** Day / Session Close"
                  ),
                  "inline": False,
              },
          ],
          "footer": {"text": "Verified: 4H Stacking + 1H EMA + DXY Regime"},
          "timestamp": datetime.utcnow().isoformat(),
      }],
  }

  try:
    response = requests.post(DISCORD_WEBHOOK_URL, json=embed_payload, timeout=5)
    print(f"[DISCORD] Dispatched: Status {response.status_code}")
  except Exception as e:
    print(f"[ERROR] Failed to send Discord alert: {e}")


@app.route("/", methods=["GET"])
def health_check():
  """Health check route for cloud uptime monitoring."""
  return (
      jsonify({
          "status": "online",
          "service": "Forex Webhook Receiver",
          "timestamp": datetime.utcnow().isoformat(),
      }),
      200,
  )


@app.route("/tradingview-webhook", methods=["POST"])
def tradingview_webhook():
  """Receives incoming JSON alerts from TradingView."""
  try:
    payload = request.get_json(force=True)
  except Exception:
    payload = request.form.to_dict()

  if not payload:
    return (
        jsonify({"status": "error", "message": "No JSON payload received"}),
        400,
    )

  ticker = payload.get("ticker", "EURUSD")
  action = payload.get("action", "BUY").upper()
  entry = float(payload.get("entry", 0.0))
  sl = float(payload.get("sl", 0.0))
  tp = float(payload.get("tp", 0.0))

  # 1. Log trade to SQLite
  try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
            INSERT INTO journal (timestamp, ticker, action, entry_price, stop_loss, take_profit, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            ticker,
            action,
            entry,
            sl,
            tp,
            "PENDING",
        ),
    )
    conn.commit()
    conn.close()
  except Exception as db_err:
    print(f"[DATABASE ERROR] {db_err}")

  # 2. Forward alert to Discord
  send_discord_alert(ticker, action, entry, sl, tp)

  return (
      jsonify({
          "status": "success",
          "logged": True,
          "ticker": ticker,
          "action": action,
      }),
      200,
  )


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)
