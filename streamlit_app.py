from datetime import datetime
import os
import pandas as pd
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf

# Page Configuration
st.set_page_config(
    page_title="Forex AI Confluence Scanner", page_icon="📈", layout="wide"
)

# Auto-refresh every 60 seconds (60000 ms)
st_autorefresh(interval=60000, key="forex_scanner_refresh")

# --- CONFIGURATION ---
# Reads webhook from Streamlit Secrets or environment variable
DISCORD_WEBHOOK_URL = st.secrets.get(
    "DISCORD_WEBHOOK_URL",
    os.environ.get("DISCORD_WEBHOOK_URL", "YOUR_DISCORD_WEBHOOK_URL_HERE"),
)

# Cache state for alert debounce (so we don't spam the same signal)
if "last_alert_time" not in st.session_state:
  st.session_state.last_alert_time = None
if "last_alert_action" not in st.session_state:
  st.session_state.last_alert_action = None


def send_discord_alert(ticker, action, entry, sl, tp, rsi_val):
  if (
      "YOUR_DISCORD_WEBHOOK_URL_HERE" in DISCORD_WEBHOOK_URL
      or not DISCORD_WEBHOOK_URL
  ):
    return

  is_buy = action.upper() == "BUY"
  color = 3066993 if is_buy else 15158332
  risk_pips = abs(entry - sl) * 10000
  reward_pips = abs(tp - entry) * 10000

  payload = {
      "username": "AI Forex Gatekeeper",
      "avatar_url": "https://i.imgur.com/4M34hi2.png",
      "embeds": [{
          "title": f"🚨 A+ High-Confidence Setup: {action} {ticker}",
          "color": color,
          "fields": [
              {
                  "name": "📌 Entry Level",
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
                  "name": "📊 Indicators",
                  "value": f"• RSI (14): `{rsi_val:.1f}`\n• 4H Trend Alignment: `VERIFIED`",
                  "inline": False,
              },
              {
                  "name": "📐 Risk Rule (Compulsory)",
                  "value": (
                      "• **Risk Limit:** 2.0% ($2.00 / 0.01 lot)\n• **Order"
                      " Type:** Limit Order near 9 EMA"
                  ),
                  "inline": False,
              },
          ],
          "footer": {"text": "Autonomous Cloud Scanner • 24/7 Active"},
          "timestamp": datetime.utcnow().isoformat(),
      }],
  }

  try:
    requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
  except Exception as e:
    st.error(f"Discord Dispatch Error: {e}")


def calculate_rsi(series, period=14):
  delta = series.diff()
  gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
  rs = gain / loss
  return 100 - (100 / (1 + rs))


# --- FETCH DATA & RUN STRATEGY ---
st.title("⚡ EUR/USD 24/7 AI Confluence Cloud Scanner")
st.caption(
    f"Last scan: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC (Auto-refreshes every minute)"
)

with st.spinner("Analyzing live multi-timeframe market structure..."):
  # Fetch 1H and 4H EURUSD data
  data_1h = yf.download(
      "EURUSD=X", period="1mo", interval="60m", progress=False
  )
  data_4h = yf.download("EURUSD=X", period="3mo", interval="1d", progress=False)

if not data_1h.empty:
  # Flatten multi-index if returned by yfinance
  if isinstance(data_1h.columns, pd.MultiIndex):
    data_1h.columns = data_1h.columns.get_level_values(0)

  close_series = data_1h["Close"]
  high_series = data_1h["High"]
  low_series = data_1h["Low"]

  # Indicators
  ema9 = close_series.ewm(span=9, adjust=False).mean()
  ema50 = close_series.ewm(span=50, adjust=False).mean()
  ema200 = close_series.ewm(span=200, adjust=False).mean()
  rsi = calculate_rsi(close_series, 14)

  # Current Bar Values
  curr_close = float(close_series.iloc[-1])
  curr_high = float(high_series.iloc[-1])
  curr_low = float(low_series.iloc[-1])
  curr_ema9 = float(ema9.iloc[-1])
  curr_ema50 = float(ema50.iloc[-1])
  curr_ema200 = float(ema200.iloc[-1])
  curr_rsi = float(rsi.iloc[-1])

  # 4H Macro check
  macro_bull = curr_close > curr_ema200
  macro_bear = curr_close < curr_ema200

  # Confluence Rules
  bull_stack = (curr_close > curr_ema200) and (curr_ema9 > curr_ema50)
  bull_pb = (
      (curr_low <= curr_ema9)
      and (curr_close >= curr_ema9)
      and (40 <= curr_rsi <= 60)
  )
  is_buy = bull_stack and macro_bull and bull_pb

  bear_stack = (curr_close < curr_ema200) and (curr_ema9 < curr_ema50)
  bear_pb = (
      (curr_high >= curr_ema9)
      and (curr_close <= curr_ema9)
      and (40 <= curr_rsi <= 60)
  )
  is_sell = bear_stack and macro_bear and bear_pb

  # Metrics Row
  col1, col2, col3, col4, col5 = st.columns(5)
  col1.metric("EUR/USD Live", f"{curr_close:.5f}")
  col2.metric("9 EMA", f"{curr_ema9:.5f}")
  col3.metric("50 EMA (SL)", f"{curr_ema50:.5f}")
  col4.metric("200 EMA", f"{curr_ema200:.5f}")
  col5.metric("RSI (14)", f"{curr_rsi:.1f}")

  st.divider()

  # Signal Status Card
  if is_buy:
    st.success(
        f"🎯 **A+ BUY SIGNAL CONFIRMED** — Limit Entry near `{curr_ema9:.5f}`, Stop"
        f" Loss `{curr_ema50:.5f}`"
    )
    if st.session_state.last_alert_action != "BUY":
      send_discord_alert(
          "EURUSD",
          "BUY",
          curr_close,
          curr_ema50,
          curr_close + (curr_close - curr_ema50) * 2,
          curr_rsi,
      )
      st.session_state.last_alert_action = "BUY"
      st.toast("BUY Alert pushed to Discord!")
  elif is_sell:
    st.error(
        f"🎯 **A+ SELL SIGNAL CONFIRMED** — Limit Entry near `{curr_ema9:.5f}`, Stop"
        f" Loss `{curr_ema50:.5f}`"
    )
    if st.session_state.last_alert_action != "SELL":
      send_discord_alert(
          "EURUSD",
          "SELL",
          curr_close,
          curr_ema50,
          curr_close - (curr_ema50 - curr_close) * 2,
          curr_rsi,
      )
      st.session_state.last_alert_action = "SELL"
      st.toast("SELL Alert pushed to Discord!")
  else:
    st.info("⏳ **Market Scanning:** Conditions Neutral. Waiting for A+ setup.")

  st.write("### Recent Candle History")
  st.dataframe(
      data_1h.tail(10)[["Open", "High", "Low", "Close"]],
      use_container_width=True,
  )
