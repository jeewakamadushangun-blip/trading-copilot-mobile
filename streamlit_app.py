from datetime import datetime, timezone
import os
import pandas as pd
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Forex AI Multi-Asset + Macro Regime Scanner",
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

# --- ASSET CONFIGURATIONS ---
WATCHLIST = {
    "EUR/USD": {"ticker": "EURUSD=X", "inverse_dxy": True, "decimals": 5, "pip_mult": 10000, "check_yield": False},
    "GBP/USD": {"ticker": "GBPUSD=X", "inverse_dxy": True, "decimals": 5, "pip_mult": 10000, "check_yield": False},
    "USD/JPY": {"ticker": "USDJPY=X", "inverse_dxy": False, "decimals": 3, "pip_mult": 100, "check_yield": True},
    "AUD/USD": {"ticker": "AUDUSD=X", "inverse_dxy": True, "decimals": 5, "pip_mult": 10000, "check_yield": False},
}

DXY_TICKER = "DX-Y.NYB"
TNX_TICKER = "^TNX"   # US 10-Year Treasury Yield
VIX_TICKER = "^VIX"   # CBOE Volatility Index


def send_discord_alert(symbol, action, entry, sl, tp, rsi_val, dxy_status, vix_val, tnx_status=None, decimals=5, pip_mult=10000, is_test=False):
    """Dispatches rich embed cards with complete macro confluence breakdown to Discord."""
    if not DISCORD_WEBHOOK_URL or "YOUR_DISCORD_WEBHOOK_URL" in DISCORD_WEBHOOK_URL:
        st.warning("⚠️ Discord Webhook URL not configured in Settings ➔ Secrets.")
        return False

    is_buy = action.upper() == "BUY"
    color = 3066993 if is_buy else 15158332
    risk_pips = abs(entry - sl) * pip_mult
    reward_pips = abs(tp - entry) * pip_mult
    tag = "🧪 [TEST VERIFICATION]" if is_test else "🚨 [A+ HIGH-CONFIDENCE SETUP]"

    breakdown_lines = [
        "• **1H EMA Stacking:** 9 EMA / 50 EMA / 200 EMA Aligned",
        f"• **RSI (14) Pullback:** `{rsi_val:.1f}` (40–60 Filter Met)",
        f"• **DXY Trend:** `{dxy_status}` (Verified)",
        f"• **Volatility Regime:** VIX at `{vix_val:.2f}` (< 25 Safe Threshold)"
    ]
    if tnx_status:
        breakdown_lines.append(f"• **US 10Y Yield Spread:** `{tnx_status}` (Bond Yield Confluence)")

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
                    "name": "📊 Intermarket Macro Confluence",
                    "value": "\n".join(breakdown_lines),
                    "inline": False
                },
                {
                    "name": "📐 Compulsory Risk Protocol",
                    "value": (
                        "• **Max Risk Limit:** 2.0% ($2.00 / 0.01 lot)\n"
                        "• **Execution:** Place Limit Order near 9 EMA\n"
                        "• **Time In Force:** Active until 1H bar close"
                    ),
                    "inline": False
                }
            ],
            "footer": {
                "text": "Macro Intermarket 24/7 Cloud Engine"
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
    """Fetches 1H OHLCV series safely with multi-layer fallbacks."""
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


# --- HEADER & CONTROLS ---
st.title("⚡ Forex AI Macro Intermarket Confluence Scanner")
st.caption(f"Last scan run: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC` • Auto-scans every 60s")

col_act1, col_act2, col_empty = st.columns([1.5, 1.5, 3])
with col_act1:
    if st.button("🔄 Manual Scan Now", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with col_act2:
    if st.button("🧪 Send Test Alert (USD/JPY)", use_container_width=True):
        send_discord_alert(
            symbol="USD/JPY",
            action="BUY",
            entry=159.128,
            sl=158.828,
            tp=159.728,
            rsi_val=52.4,
            dxy_status="BULLISH",
            vix_val=15.42,
            tnx_status="BULLISH (> 50 EMA)",
            decimals=3,
            pip_mult=100,
            is_test=True
        )
        st.toast("✅ Test alert sent to Discord!")

st.divider()

# --- 1. MACRO INTERMARKET REGIME ENGINE ---
dxy_df = get_ticker_data(DXY_TICKER)
if dxy_df.empty:
    dxy_df = get_ticker_data("DX=F")

tnx_df = get_ticker_data(TNX_TICKER)
vix_df = get_ticker_data(VIX_TICKER)

# A. Dollar Index (DXY)
dxy_trend = "NEUTRAL"
dxy_close, dxy_ema200 = 0.0, 0.0
if not dxy_df.empty:
    if isinstance(dxy_df.columns, pd.MultiIndex):
        dxy_df.columns = dxy_df.columns.get_level_values(0)
    dxy_close_s = dxy_df["Close"]
    dxy_ema200_s = dxy_close_s.ewm(span=200, adjust=False).mean()
    dxy_close = float(dxy_close_s.iloc[-1])
    dxy_ema200 = float(dxy_ema200_s.iloc[-1])
    dxy_trend = "BULLISH (USD Strength)" if dxy_close > dxy_ema200 else "BEARISH (USD Weakness)"

# B. US 10-Year Yield (TNX)
tnx_trend = "NEUTRAL"
tnx_close, tnx_ema50 = 0.0, 0.0
if not tnx_df.empty:
    if isinstance(tnx_df.columns, pd.MultiIndex):
        tnx_df.columns = tnx_df.columns.get_level_values(0)
    tnx_close_s = tnx_df["Close"]
    tnx_ema50_s = tnx_close_s.ewm(span=50, adjust=False).mean()
    tnx_close = float(tnx_close_s.iloc[-1])
    tnx_ema50 = float(tnx_ema50_s.iloc[-1])
    tnx_trend = "BULLISH (Yield Expansion)" if tnx_close > tnx_ema50 else "BEARISH (Yield Contraction)"

# C. Volatility Index (VIX)
vix_val = 16.0  # Safe fallback default
if not vix_df.empty:
    if isinstance(vix_df.columns, pd.MultiIndex):
        vix_df.columns = vix_df.columns.get_level_values(0)
    vix_val = float(vix_df["Close"].iloc[-1])

vix_safe = vix_val < 25.0
vix_status = f"`{vix_val:.2f}` (Safe Market Regime)" if vix_safe else f"`{vix_val:.2f}` (HIGH RISK / VOLATILITY HALT)"

# Macro Display Panel
col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric("DXY Dollar Index", f"{dxy_close:.2f}", help="Evaluated against 200 EMA")
col_m1.caption(f"Trend: `{dxy_trend}`")

col_m2.metric("US 10Y Yield (^TNX)", f"{tnx_close:.2f}%", help="Evaluated against 50 EMA for USD/JPY")
col_m2.caption(f"Spread: `{tnx_trend}`")

col_m3.metric("CBOE Volatility (^VIX)", f"{vix_val:.2f}", help="Hard gate: Trading halted if VIX > 25")
col_m3.caption(f"Regime: {vix_status}")

if not vix_safe:
    st.error("🚨 **GLOBAL REGIME HALT ACTIVE:** VIX > 25.0. Trend-following signals are automatically muted to prevent whip-saw losses.")

st.divider()

# --- 2. MULTI-ASSET ENGINE WITH INTERMARKET GATES ---
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

    # 1. Base Technical Confluence
    bull_stack = (curr_close > curr_ema200) and (curr_ema9 > curr_ema50)
    bull_pb = (curr_low <= curr_ema9) and (curr_close >= curr_ema9) and (40 <= curr_rsi <= 60)

    bear_stack = (curr_close < curr_ema200) and (curr_ema9 < curr_ema50)
    bear_pb = (curr_high >= curr_ema9) and (curr_close <= curr_ema9) and (40 <= curr_rsi <= 60)

    # 2. DXY Confluence Filter
    if cfg["inverse_dxy"]:
        dxy_confirms_buy = "BEARISH" in dxy_trend
        dxy_confirms_sell = "BULLISH" in dxy_trend
    else:
        dxy_confirms_buy = "BULLISH" in dxy_trend
        dxy_confirms_sell = "BEARISH" in dxy_trend

    # 3. Bond Yield (TNX) Gate (Applied to USD/JPY)
    yield_confirms_buy = True
    yield_confirms_sell = True
    if cfg["check_yield"]:
        yield_confirms_buy = "BULLISH" in tnx_trend
        yield_confirms_sell = "BEARISH" in tnx_trend

    # Final Combined Confluence Evaluation
    is_buy = bull_stack and bull_pb and dxy_confirms_buy and yield_confirms_buy and vix_safe
    is_sell = bear_stack and bear_pb and dxy_confirms_sell and yield_confirms_sell and vix_safe

    signal_status = "NEUTRAL"
    tnx_note = tnx_trend if cfg["check_yield"] else None

    if is_buy:
        signal_status = "BUY"
        tp = curr_close + ((curr_close - curr_ema50) * 2.0)
        if st.session_state.alert_history.get(pair_name) != "BUY":
            send_discord_alert(pair_name, "BUY", curr_close, curr_ema50, tp, curr_rsi, dxy_trend, vix_val, tnx_note, cfg["decimals"], cfg["pip_mult"])
            st.session_state.alert_history[pair_name] = "BUY"
            st.toast(f"🚨 BUY Alert dispatched for {pair_name}!")
            
    elif is_sell:
        signal_status = "SELL"
        tp = curr_close - ((curr_ema50 - curr_close) * 2.0)
        if st.session_state.alert_history.get(pair_name) != "SELL":
            send_discord_alert(pair_name, "SELL", curr_close, curr_ema50, tp, curr_rsi, dxy_trend, vix_val, tnx_note, cfg["decimals"], cfg["pip_mult"])
            st.session_state.alert_history[pair_name] = "SELL"
            st.toast(f"🚨 SELL Alert dispatched for {pair_name}!")
    else:
        st.session_state.alert_history[pair_name] = "NEUTRAL"

    # Macro Confluence Status Pill
    macro_checks = []
    if dxy_confirms_buy if bull_stack else dxy_confirms_sell:
        macro_checks.append("DXY ✅")
    if cfg["check_yield"] and (yield_confirms_buy if bull_stack else yield_confirms_sell):
        macro_checks.append("TNX ✅")
    if vix_safe:
        macro_checks.append("VIX Safe")

    results_summary.append({
        "Asset": pair_name,
        "Price": f"{curr_close:.{cfg['decimals']}f}",
        "9 EMA": f"{curr_ema9:.{cfg['decimals']}f}",
        "50 EMA (SL)": f"{curr_ema50:.{cfg['decimals']}f}",
        "200 EMA": f"{curr_ema200:.{cfg['decimals']}f}",
        "RSI (14)": f"{curr_rsi:.1f}",
        "Macro Gates": " • ".join(macro_checks) if macro_checks else "Waiting Alignment",
        "Setup Status": signal_status
    })

# Render Live Market Watchlist Table
st.write("### 📊 Active Market Watchlist")
st.dataframe(pd.DataFrame(results_summary), use_container_width=True)
