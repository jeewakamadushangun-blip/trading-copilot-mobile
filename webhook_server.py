import json
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

# --- CONFIGURATION ---
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1540037811485286460/CbOoMZKBBhLmK_pDG-NMGl824teSX2w-eG0jeQiGR6YicXLOJoA4qLZJyGhin5Y0n8RP"
DB_PATH = "trading_journal.db"


def init_db():
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
  color = 3066993 if action == "BUY" else 15158332  # Green for BUY, Red for SELL
  risk_pips = abs(entry - sl) * 10000
  reward_pips = abs(tp - entry) * 10000

  embed_payload = {
      "username": "AI Forex Gatekeeper",
      "embeds": [{
          "title": f"🚨 High-Confidence Alert: {action} {ticker}",
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
                  "name": "📐 Risk Parameters",
                  "value": (
                      "• **Risk Cap:** 2.0% ($2.00 on $100)\n• **Lot Size:**"
                      " 0.01 micro\n• **Order Type:** Limit Order"
                  ),
                  "inline": False,
              },
          ],
          "footer": {"text": "Verified Confluence: 4H Trend + 1H EMA + DXY"},
          "timestamp": datetime.utcnow().isoformat(),
      }],
  }
  requests.post(DISCORD_WEBHOOK_URL, json=embed_payload)


@app.route("/tradingview-webhook", methods=["POST"])
def tradingview_webhook():
  payload = request.json
  if not payload:
    return jsonify({"status": "error", "message": "Missing JSON payload"}), 400

  ticker = payload.get("ticker", "EURUSD")
  action = payload.get("action", "BUY")
  entry = float(payload.get("entry", 0.0))
  sl = float(payload.get("sl", 0.0))
  tp = float(payload.get("tp", 0.0))

  # 1. Log trade into SQLite journal
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

  # 2. Dispatch alert to Discord
  send_discord_alert(ticker, action, entry, sl, tp)

  return jsonify({"status": "success", "logged": True}), 200


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000)
