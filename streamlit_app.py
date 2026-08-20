from datetime import datetime
import requests

# 1. Paste your Discord Webhook URL below
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1539684182827991070/BBmfXn58AOTljeU-New6FOHy7weuZmjI9aQz92Q5PIdQO-Q3VCIlxAWEwKs2wQvlRbKs"

# 2. Simulated Live Confluence Values
ticker = "EURUSD"
action = "BUY"
entry = 1.16781
sl = 1.16542
tp = round(entry + ((entry - sl) * 2), 5)
rsi_val = 50.7
risk_pips = abs(entry - sl) * 10000
reward_pips = abs(tp - entry) * 10000

payload = {
    "username": "AI Forex Gatekeeper",
    "avatar_url": "https://i.imgur.com/4M34hi2.png",
    "embeds": [{
        "title": f"🧪 [TEST VERIFICATION] {action} {ticker}",
        "color": 3066993,  # Green
        "fields": [
            {
                "name": "📌 Entry Level",
                "value": f"`{entry:.5f}`",
                "inline": True
            },
            {
                "name": "🛑 Stop Loss (-1R)",
                "value": f"`{sl:.5f}` ({risk_pips:.1f} pips)",
                "inline": True
            },
            {
                "name": "🎯 Take Profit (+2R)",
                "value": f"`{tp:.5f}` ({reward_pips:.1f} pips)",
                "inline": True
            },
            {
                "name": "📊 Confluence Breakdown",
                "value": (
                    "• **1H Stacking:** 9 EMA > 50 EMA > 200 EMA\n"
                    f"• **RSI (14) Pullback:** `{rsi_val:.1f}` (40–60 Filter Met)\n"
                    "• **Macro Trend:** 4H Multi-Timeframe Alignment Confirmed"
                ),
                "inline": False
            },
            {
                "name": "📐 Risk & Execution Protocol",
                "value": (
                    "• **Max Risk Limit:** 2.0% ($2.00 / 0.01 lot)\n"
                    "• **Execution:** Place Limit Order near 9 EMA\n"
                    "• **Time In Force:** Active until session close"
                ),
                "inline": False
            }
        ],
        "footer": {
            "text": "Streamlit Cloud 24/7 Autonomous Scanner • Test Mode"
        },
        "timestamp": datetime.utcnow().isoformat()
    }]
}

# 3. Dispatch to Discord
response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=8)

if response.status_code in [200, 204]:
  print("✅ Success! Test alert delivered to your Discord channel.")
else:
  print(f"❌ Failed to deliver. HTTP Status Code: {response.status_code}")
  print(f"Response: {response.text}")
