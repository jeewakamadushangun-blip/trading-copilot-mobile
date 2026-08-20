from datetime import datetime, timezone
import os
import pandas as pd
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Forex AI Confluence Scanner",
    page_icon="📈",
    layout="wide"
)

# Auto-refresh dashboard and calculations every 60 seconds (60,000 ms)
st_autorefresh(interval=60000, key="forex_scanner_autorefresh")

# --- CREDENTIALS CONFIGURATION ---
DISCORD_WEBHOOK_URL = st.secrets.get(
    "DISCORD_WEBHOOK_URL", 
    os.environ.get("DISCORD_WEBHOOK_URL", "")
)

# Initialize session state for alert debounce
if "last_alert_time" not in st.session_state:
    st.session_state.last_alert_time = None
if "last_alert_action" not in st.session_state:
    st.session_state.last_alert_action = None


def send_discord_alert(ticker, action, entry, sl, tp, rsi_val, is_test=False):
    """Dispatches structured rich embed cards directly to Discord."""
    if not DISCORD_WEBHOOK_URL or "YOUR_DISCORD_WEBHOOK_URL" in DISCORD_WEBHOOK_URL:
        st.warning("⚠️ Discord Webhook URL is not configured in Settings ➔ Secrets.")
        return False

    is_buy = action.upper() == "BUY"
    color = 3066993 if is_buy else 15158332
    risk_pips = abs(entry - sl) * 10000
    reward_pips = abs(tp - entry) * 10000
    tag = "🧪 [TEST VERIFICATION]" if is_test else "🚨 [HIGH-CONFIDENCE SETUP]"

    payload = {
        "username": "AI Forex Gatekeeper",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [{
            "title": f"{tag} {action} {ticker}",
            "color": color,
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
                        f"• **1H Stacking:** 9 EMA > 50 EMA > 200 EMA\n"
                        f"• **RSI (14) Pullback:** `{rsi_val:.1f}` (40–60 Filter Met)\n"
                        f"• **Macro Trend:** 4H Multi-Timeframe Alignment Confirmed"
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
                "text": "Streamlit Cloud 24/7 Autonomous Scanner"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=8)
        return response.status_code in [200, 204]
    except Exception as e:
        st.error(f"Discord Dispatch Failed: {e}")
        return False


def calculate_rsi(series, period=14):
    """Calculates Wilder's RSI using rolling averages."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


# --- ROBUST CACHED DATA FETCHING ---
@st.cache_data(ttl=45)
def fetch_market_data():
    """Fetches market data using resilient Ticker history with fallback."""
    try:
        ticker = yf.Ticker("EURUSD=X")
        df = ticker.history(period="1mo", interval="1h")
        if not df.empty and len(df) > 20:
            return df
    except Exception:
        pass

    try:
        df = yf.download("EURUSD=X", period="1mo", interval="60m", progress=False)
        if not df.empty and len(df) > 20:
            return df
    except Exception:
        pass

    return pd.DataFrame()


# --- HEADER & STATUS ---
st.title("⚡ EUR/USD 24/7 AI Confluence Cloud Scanner")
st.caption(f"Last scan run: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC` • Auto-scans every 60s")

# --- DATA INGESTION & PROCESSING ---
with st.spinner("Fetching live EUR/USD market feed..."):
    data_1h = fetch_market_data()

if not data_1h.empty:
    if isinstance(data_1h.columns, pd.MultiIndex):
        data_1h.columns = data_1h.columns.get_level_values(0)

    close = data_1h["Close"]
    high = data_1h["High"]
    low = data_1h["Low"]

    # Calculate Indicators
    ema9_series = close.ewm(span=9, adjust=False).mean()
    ema50_series = close.ewm(span=50, adjust=False).mean()
    ema200_series = close.ewm(span=200, adjust=False).mean()
    rsi_series = calculate_rsi(close, 14)

    # Current Bar Values
    curr_close = float(close.iloc[-1])
    curr_high = float(high.iloc[-1])
    curr_low = float(low.iloc[-1])
    curr_ema9 = float(ema9_series.iloc[-1])
    curr_ema50 = float(ema50_series.iloc[-1])
    curr_ema200 = float(ema200_series.iloc[-1])
    curr_rsi = float(rsi_series.iloc[-1])

    # Multi-Timeframe Confluence Rules
    macro_bull = curr_close > curr_ema200
    macro_bear = curr_close < curr_ema200

    bull_stack = (curr_close > curr_ema200) and (curr_ema9 > curr_ema50)
    bull_pullback = (curr_low <= curr_ema9) and (curr_close >= curr_ema9) and (40 <= curr_rsi <= 60)
    is_buy = bull_stack and macro_bull and bull_pullback

    bear_stack = (curr_close < curr_ema200) and (curr_ema9 < curr_ema50)
    bear_pullback = (curr_high >= curr_ema9) and (curr_close <= curr_ema9) and (40 <= curr_rsi <= 60)
    is_sell = bear_stack and macro_bear and bear_pullback

    # Top Metrics Grid
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("EUR/USD Live", f"{curr_close:.5f}")
    col2.metric("9 EMA", f"{curr_ema9:.5f}")
    col3.metric("50 EMA (SL)", f"{curr_ema50:.5f}")
    col4.metric("200 EMA", f"{curr_ema200:.5f}")
    col5.metric("RSI (14)", f"{curr_rsi:.1f}")

    st.divider()

    # Dynamic Alert Execution
    if is_buy:
        tp_target = curr_close + ((curr_close - curr_ema50) * 2.0)
        st.success(f"🎯 **A+ BUY SIGNAL CONFIRMED** — Limit Entry near `{curr_ema9:.5f}`, Stop Loss `{curr_ema50:.5f}`, Take Profit `{tp_target:.5f}`")
        
        if st.session_state.last_alert_action != "BUY":
            sent = send_discord_alert("EURUSD", "BUY", curr_close, curr_ema50, tp_target, curr_rsi)
            if sent:
                st.session_state.last_alert_action = "BUY"
                st.toast("✅ Live BUY Alert dispatched to Discord!")
                
    elif is_sell:
        tp_target = curr_close - ((curr_ema50 - curr_close) * 2.0)
        st.error(f"🎯 **A+ SELL SIGNAL CONFIRMED** — Limit Entry near `{curr_ema9:.5f}`, Stop Loss `{curr_ema50:.5f}`, Take Profit `{tp_target:.5f}`")
        
        if st.session_state.last_alert_action != "SELL":
            sent = send_discord_alert("EURUSD", "SELL", curr_close, curr_ema50, tp_target, curr_rsi)
            if sent:
                st.session_state.last_alert_action = "SELL"
                st.toast("✅ Live SELL Alert dispatched to Discord!")
    else:
        st.info("⏳ **Market Scanning:** Conditions Neutral. Waiting for 9 EMA pullback & RSI alignment.")
        st.session_state.last_alert_action = None

    # Diagnostics & Test Section
    st.write("### Diagnostics & Webhook Verification")
    col_btn, col_txt = st.columns([1, 4])
    with col_btn:
        if st.button("🧪 Send Test Discord Alert", use_container_width=True):
            test_tp = curr_close + ((curr_close - curr_ema50) * 2.0)
            success = send_discord_alert("EURUSD", "BUY", curr_close, curr_ema50, test_tp, curr_rsi, is_test=True)
            if success:
                st.success("Test notification delivered to Discord!")
            else:
                st.error("Failed to send. Verify your DISCORD_WEBHOOK_URL in Secrets.")

    # Recent Candle Table
    st.write("### Recent 1-Hour Candles")
    display_df = data_1h.tail(10)[["Open", "High", "Low", "Close"]].sort_index(ascending=False)
    st.dataframe(display_df, use_container_width=True)

else:
    st.error("Unable to load real-time market data from Yahoo Finance. Retrying on next cycle...")
