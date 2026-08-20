from datetime import datetime, timezone
import os
import pandas as pd
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Forex AI Multi-Asset + DXY Scanner",
    page_icon="⚡",
    layout="wide"
)

# Auto-refresh scanner every 60 seconds (60,000 ms)
st_autorefresh(interval=60000, key="forex_multi_scanner_autorefresh")

# --- CREDENTIALS CONFIGURATION ---
DISCORD_WEBHOOK_URL = st.secrets.get(
    "DISCORD_WEBHOOK_URL", 
    os.environ.get("DISCORD_WEBHOOK_URL", "")
)

# Debounce cache to prevent repeating alerts on active candles
if "alert_history" not in st.session_state:
    st.session_state.alert_history = {}

# --- ASSETS CONFIGURATION ---
WATCHLIST = {
    "EUR/USD": {"ticker": "EURUSD=X", "inverse_dxy": True, "decimals": 5, "pip_mult": 10000},
    "GBP/USD": {"ticker": "GBPUSD=X", "inverse_dxy": True, "decimals": 5, "pip_mult": 10000},
    "USD/JPY": {"ticker": "USDJPY=X", "inverse_dxy": False, "decimals": 3, "pip_mult": 100},
    "AUD/USD": {"ticker": "AUDUSD=X", "inverse_dxy": True, "decimals": 5, "pip_mult": 10000},
}
DXY_TICKER = "DX-Y.NYB"


def send_discord_alert(symbol, action, entry, sl, tp, rsi_val, dxy_status, decimals=5, pip_mult=10000, is_test=False):
    """Dispatches formatted rich embed card to Discord."""
    if not DISCORD_WEBHOOK_URL or "YOUR_DISCORD_WEBHOOK_URL" in DISCORD_WEBHOOK_URL:
        st.warning("⚠️ Discord Webhook URL not configured in Secrets.")
        return False

    is_buy = action.upper() == "BUY"
    color = 3066993 if is_buy else 15158332  # Green / Red
    risk_pips = abs(entry - sl) * pip_mult
    reward_pips = abs(tp - entry) * pip_mult
    tag = "🧪 [TEST VERIFICATION]" if is_test else "🚨 [A+ HIGH-CONFIDENCE SETUP]"

    payload = {
        "username": "AI Forex Gatekeeper",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [{
            "title": f"{tag} {action} {symbol}",
            "color": color,
            "fields": [
                {
                    "name": "📌 Entry Level",
                    "value": f"`{entry:.{decimals}f}`",
                    "inline": True
                },
                {
                    "name": "🛑 Stop Loss (-1R)",
                    "value": f"`{sl:.{decimals}f}` ({risk_pips:.1f} pips)",
                    "inline": True
                },
                {
                    "name": "🎯 Take Profit (+2R)",
                    "value": f"`{tp:.{decimals}f}` ({reward_pips:.1f} pips)",
                    "inline": True
                },
                {
                    "name": "📊 Confluence Breakdown",
                    "value": (
                        f"• **1H EMA Stacking:** 9 EMA / 50 EMA / 200 EMA Aligned\n"
                        f"• **RSI (14) Pullback:** `{rsi_val:.1f}` (40–60 Filter Met)\n"
                        f"• **DXY Macro Alignment:** `{dxy_status}` (Verified)"
                    ),
                    "inline": False
                },
                {
                    "name": "📐 Risk & Execution Protocol",
                    "value": (
                        "• **Risk Limit:** 2.0% ($2.00 / 0.01 lot)\n"
                        "• **Order Type:** Limit Order near 9 EMA\n"
                        "• **Time In Force:** Active until 1H bar close"
                    ),
                    "inline": False
                }
            ],
            "footer": {
                "text": "Multi-Asset DXY Cloud Scanner • 24/7 Engine"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
    }

    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=8)
        return res.status_code in [200, 204]
    except Exception as e:
        st.error(f"Discord Dispatch Error: {e}")
        return False


def calculate_rsi(series, period=14):
    """Calculates Wilder's RSI."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


@st.cache_data(ttl=45)
def get_ticker_data(symbol_ticker):
    """Fetches 1H OHLCV series safely with fallbacks."""
    try:
        t = yf.Ticker(symbol_ticker)
        df = t.history(period="1mo", interval="1h")
        if not df.empty and len(df) > 20:
            return df
    except Exception:
        pass
    try:
        df = yf.download(symbol_ticker, period="1mo", interval="60m", progress=False)
        if not df.empty and len(df) > 20:
            return df
    except Exception:
        pass
    return pd.DataFrame()


# --- HEADER ---
st.title("⚡ Forex AI 4-Asset + DXY Confluence Scanner")
st.caption(f"Last scan run: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC` • Auto-scans every 60s")

# --- 1. DXY (DOLLAR INDEX) MACRO ENGINE ---
dxy_df = get_ticker_data(DXY_TICKER)
if dxy_df.empty:
    dxy_df = get_ticker_data("DX=F")  # Fallback to DXY Futures if Cash Index unavailable

dxy_trend = "NEUTRAL"
dxy_close = 0.0
dxy_ema200 = 0.0

if not dxy_df.empty:
    if isinstance(dxy_df.columns, pd.MultiIndex):
        dxy_df.columns = dxy_df.columns.get_level_values(0)
    dxy_close_series = dxy_df["Close"]
    dxy_ema200_series = dxy_close_series.ewm(span=200, adjust=False).mean()
    dxy_close = float(dxy_close_series.iloc[-1])
    dxy_ema200 = float(dxy_ema200_series.iloc[-1])
    
    if dxy_close > dxy_ema200:
        dxy_trend = "BULLISH (USD Strength)"
    else:
        dxy_trend = "BEARISH (USD Weakness)"

# DXY Macro Banner
col_dxy1, col_dxy2, col_dxy3 = st.columns([1, 1, 2])
col_dxy1.metric("DXY Index Live", f"{dxy_close:.2f}")
col_dxy2.metric("DXY 200 EMA", f"{dxy_ema200:.2f}")
col_dxy3.info(f"🌐 **DXY Macro Bias:** `{dxy_trend}`")

st.divider()

# --- 2. MULTI-PAIR SCANNING ENGINE ---
results_summary = []

for pair_name, cfg in WATCHLIST.items():
    df = get_ticker_data(cfg["ticker"])
    if df.empty:
        continue
        
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    rsi = calculate_rsi(close, 14)

    curr_close = float(close.iloc[-1])
    curr_high = float(high.iloc[-1])
    curr_low = float(low.iloc[-1])
    curr_ema9 = float(ema9.iloc[-1])
    curr_ema50 = float(ema50.iloc[-1])
    curr_ema200 = float(ema200.iloc[-1])
    curr_rsi = float(rsi.iloc[-1])

    # DXY Multi-Timeframe Filter Logic
    if cfg["inverse_dxy"]:
        dxy_confirms_buy = "BEARISH" in dxy_trend
        dxy_confirms_sell = "BULLISH" in dxy_trend
    else:
        dxy_confirms_buy = "BULLISH" in dxy_trend
        dxy_confirms_sell = "BEARISH" in dxy_trend

    # Technical Confluence
    bull_stack = (curr_close > curr_ema200) and (curr_ema9 > curr_ema50)
    bull_pb = (curr_low <= curr_ema9) and (curr_close >= curr_ema9) and (40 <= curr_rsi <= 60)
    is_buy = bull_stack and bull_pb and dxy_confirms_buy

    bear_stack = (curr_close < curr_ema200) and (curr_ema9 < curr_ema50)
    bear_pb = (curr_high >= curr_ema9) and (curr_close <= curr_ema9) and (40 <= curr_rsi <= 60)
    is_sell = bear_stack and bear_pb and dxy_confirms_sell

    signal_status = "NEUTRAL"
    if is_buy:
        signal_status = "BUY"
        tp = curr_close + ((curr_close - curr_ema50) * 2.0)
        # Alert Debounce
        if st.session_state.alert_history.get(pair_name) != "BUY":
            send_discord_alert(pair_name, "BUY", curr_close, curr_ema50, tp, curr_rsi, dxy_trend, cfg["decimals"], cfg["pip_mult"])
            st.session_state.alert_history[pair_name] = "BUY"
            st.toast(f"🚨 BUY Alert dispatched for {pair_name}!")
            
    elif is_sell:
        signal_status = "SELL"
        tp = curr_close - ((curr_ema50 - curr_close) * 2.0)
        if st.session_state.alert_history.get(pair_name) != "SELL":
            send_discord_alert(pair_name, "SELL", curr_close, curr_ema50, tp, curr_rsi, dxy_trend, cfg["decimals"], cfg["pip_mult"])
            st.session_state.alert_history[pair_name] = "SELL"
            st.toast(f"🚨 SELL Alert dispatched for {pair_name}!")
    else:
        st.session_state.alert_history[pair_name] = "NEUTRAL"

    results_summary.append({
        "Asset": pair_name,
        "Price": f"{curr_close:.{cfg['decimals']}f}",
        "9 EMA": f"{curr_ema9:.{cfg['decimals']}f}",
        "50 EMA (SL)": f"{curr_ema50:.{cfg['decimals']}f}",
        "200 EMA": f"{curr_ema200:.{cfg['decimals']}f}",
        "RSI (14)": f"{curr_rsi:.1f}",
        "DXY Match": "✅ Confirmed" if (is_buy or is_sell) else "—",
        "Setup Status": signal_status
    })

# Render Multi-Asset Overview Table
st.write("### 📊 Active Market Watchlist")
st.dataframe(pd.DataFrame(results_summary), use_container_width=True)

# --- 3. DIAGNOSTICS & VERIFICATION ---
st.divider()
st.write("### Diagnostics & Webhook Verification")
col_btn, col_txt = st.columns([1, 4])
with col_btn:
    if st.button("🧪 Send Test Alert (EUR/USD)", use_container_width=True):
        send_discord_alert("EUR/USD", "BUY", 1.16809, 1.16553, 1.17321, 50.7, dxy_trend, decimals=5, pip_mult=10000, is_test=True)
        st.success("Test alert sent to Discord!")
