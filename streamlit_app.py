import concurrent.futures
from datetime import datetime
import os
import sqlite3
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from google import genai

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="AI Multi-Asset Radar & ATR Copilot",
    page_icon="📡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

DB_FILE = "trades.db"

ASSETS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "Gold / USD": "GC=F",
}

TRADINGVIEW_SYMBOLS = {
    "EUR/USD": "FX:EURUSD",
    "GBP/USD": "FX:GBPUSD",
    "USD/JPY": "FX:USDJPY",
    "Gold / USD": "OANDA:XAUUSD",
}


# --- DATABASE LAYER (SQLite) ---
def init_db():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            asset TEXT,
            direction TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            risk_amount REAL,
            reward_amount REAL,
            rrr REAL,
            status TEXT,
            pnl REAL,
            notes TEXT
        )
    """)
  conn.commit()
  conn.close()


def save_trade(
    asset,
    direction,
    entry,
    sl,
    tp,
    risk,
    reward,
    rrr,
    status="OPEN",
    pnl=0.0,
    notes="",
):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  now = datetime.now().strftime("%Y-%m-%d %H:%M")
  cursor.execute(
      """
        INSERT INTO trades (timestamp, asset, direction, entry_price, stop_loss, take_profit, risk_amount, reward_amount, rrr, status, pnl, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (now, asset, direction, entry, sl, tp, risk, reward, rrr, status, pnl, notes),
  )
  conn.commit()
  conn.close()


def fetch_trades():
  conn = sqlite3.connect(DB_FILE)
  df = pd.read_sql_query("SELECT * FROM trades ORDER BY id DESC", conn)
  conn.close()
  return df


def update_trade_outcome(trade_id, status, pnl):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute(
      "UPDATE trades SET status = ?, pnl = ? WHERE id = ?",
      (status, pnl, trade_id),
  )
  conn.commit()
  conn.close()


def delete_trade(trade_id):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
  conn.commit()
  conn.close()


init_db()


# --- INDICATOR FUNCTIONS ---
def compute_atr(df, period=14):
  high = df["High"]
  low = df["Low"]
  close = df["Close"].shift(1)

  tr1 = high - low
  tr2 = (high - close).abs()
  tr3 = (low - close).abs()

  tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
  return tr.rolling(window=period).mean()


def fetch_single_asset(name, symbol):
  try:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="10d", interval="1h", timeout=10)
    if df.empty or len(df) < 50:
      return None

    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA_200"] = df["Close"].ewm(span=200, adjust=False).mean()
    df["ATR"] = compute_atr(df, period=14)

    latest = df.iloc[-1]
    current_price = latest["Close"]
    ema9 = latest["EMA_9"]
    ema50 = latest["EMA_50"]
    ema200 = latest["EMA_200"]
    atr = latest["ATR"]

    session_high = df["High"].tail(24).max()
    session_low = df["Low"].tail(24).min()

    trend = (
        "BULLISH 🟢"
        if current_price > ema50 and ema9 > ema50
        else (
            "BEARISH 🔴"
            if current_price < ema50 and ema9 < ema50
            else "NEUTRAL / CHOP ⚪"
        )
    )

    return {
        "asset": name,
        "symbol": symbol,
        "price": current_price,
        "ema9": ema9,
        "ema50": ema50,
        "ema200": ema200,
        "atr": atr,
        "high": session_high,
        "low": session_low,
        "trend": trend,
    }
  except Exception:
    return None


def fetch_all_radar_data():
  results = {}
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    futures = {
        executor.submit(fetch_single_asset, name, sym): name
        for name, sym in ASSETS.items()
    }
    for future in concurrent.futures.as_completed(futures):
      res = future.result()
      if res:
        results[res["asset"]] = res
  return results


# --- APP INTERFACE ---
tab_radar, tab_journal = st.tabs(
    ["📡 Multi-Asset Radar", "📓 Trade Journal & Analytics"]
)

# ==========================================
# TAB 1: RADAR WITH DEEP LINKS & ATR
# ==========================================
with tab_radar:
  st.title("📡 Multi-Asset Radar & Copilot")
  st.caption(
      "1-Hour Institutional EMA Strategy • Volatility Stops • 1-Click TradingView"
  )

  raw_secret_key = ""
  if "GEMINI_API_KEY" in st.secrets:
    raw_secret_key = (
        str(st.secrets["GEMINI_API_KEY"]).strip().strip('"').strip("'")
    )

  api_key_input = st.text_input(
      "Gemini API Key",
      value=raw_secret_key,
      type="password",
      placeholder="Paste your AI Studio API key...",
  )

  active_api_key = api_key_input.strip().strip('"').strip("'")
  account_balance = st.number_input(
      "Trading Capital ($)", min_value=10.0, value=100.0, step=10.0
  )

  if st.button("🚀 Scan All 4 Assets Simultaneously", use_container_width=True):
    if not active_api_key:
      st.error("Please enter your Gemini API Key above.")
    else:
      with st.spinner("Analyzing parallel data & computing ATR volatility..."):
        try:
          radar_data = fetch_all_radar_data()

          if len(radar_data) < 2:
            st.error("Unable to load live market feeds. Please retry.")
          else:
            st.subheader("⚡ Live Market Structure & Volatility")
            m_cols = st.columns(len(radar_data))
            for idx, (name, d) in enumerate(radar_data.items()):
              with m_cols[idx]:
                st.metric(
                    label=name,
                    value=f"{d['price']:.4f}",
                    delta=f"ATR: {d['atr']:.4f}",
                )
                tv_sym = TRADINGVIEW_SYMBOLS.get(name, "FX:EURUSD")
                st.link_button(
                    "📈 Chart",
                    f"https://www.tradingview.com/chart/?symbol={tv_sym}&interval=60",
                    use_container_width=True,
                )

            market_snapshot_text = ""
            for name, d in radar_data.items():
              market_snapshot_text += f"""
ASSET: {name} ({d['symbol']})
- Live Price: {d['price']:.5f}
- 14-period ATR: {d['atr']:.5f} (1.5x SL Buffer: {1.5 * d['atr']:.5f})
- 9 EMA: {d['ema9']:.5f} | 50 EMA: {d['ema50']:.5f} | 200 EMA: {d['ema200']:.5f}
- 24h High: {d['high']:.5f} | 24h Low: {d['low']:.5f}
- Structural Regime: {d['trend']}
"""

            max_risk_cap = account_balance * 0.025
            prompt = f"""
You are an expert Forex Risk Guardian.
Analyze this live 4-asset technical snapshot with 14-period ATR volatility data:
{market_snapshot_text}

Account Capital: ${account_balance:.2f} (Strict max loss: Under ${max_risk_cap:.2f}).
Position Sizing: 0.01 micro lot (1,000 units).

Generate a clear execution guide:

## 1. WATCHLIST OPPORTUNITY RADAR
Grade all 4 pairs:
- **Grade A+ (Prime Pullback / High Probability)**
- **Grade B (Secondary / Momentum Play)**
- **No Trade (Consolidation or Choppy EMAs)**

## 2. TOP ACTIONABLE BLUEPRINT CARD (Highest-Ranked Setup)
Provide the execution plan using ATR-based stop placement:
- **Asset & Order Type**: (e.g. EUR/USD - BUY LIMIT)
- **Recommended Entry Price**:
- **Dynamic ATR Stop Loss Price**: (Calculated using 1.5x ATR buffer, state dollar loss under ${max_risk_cap:.2f})
- **Take Profit Target Price**: (Calculated using 3.0x ATR buffer for 1:2 RRR)
- **Risk-to-Reward Ratio**: (Target 1:2 minimum)
- **Why This Trade Works**: (2 simple sentences on EMA bounce + ATR room)
- **15-Second Action Plan on TradingView**: (3 clean execution steps)
"""

            client = genai.Client(api_key=active_api_key)
            response = client.models.generate_content(
                model="gemini-3.6-flash", contents=prompt
            )

            if response.text:
              st.session_state["radar_blueprint"] = response.text
              st.session_state["radar_data"] = radar_data
              st.success("ATR Volatility Scan Complete!")
              st.markdown(response.text)
            else:
              st.error("Failed to generate trade blueprint. Please retry.")

        except Exception as e:
          st.error(f"Scan Error: {str(e)}")

  # Quick-Log Section with 1-Click TradingView Button
  if "radar_blueprint" in st.session_state:
    st.divider()
    st.subheader("📥 Quick Log Selected Setup to Journal")

    log_asset = st.selectbox(
        "Select Asset to Log or Chart", list(ASSETS.keys())
    )
    selected_tv_sym = TRADINGVIEW_SYMBOLS.get(log_asset, "FX:EURUSD")
    tv_deep_link = f"https://www.tradingview.com/chart/?symbol={selected_tv_sym}&interval=60"

    st.link_button(
        f"📱 Open {log_asset} Directly in TradingView (1H)",
        tv_deep_link,
        use_container_width=True,
    )

    with st.form("quick_log_form"):
      c1, c2 = st.columns(2)
      with c1:
        log_dir = st.selectbox(
            "Direction", ["BUY LIMIT", "SELL LIMIT", "BUY", "SELL"]
        )
        default_entry = st.session_state["radar_data"][log_asset]["price"]
        log_entry = st.number_input(
            "Entry Price", value=float(default_entry), format="%.5f"
        )
      with c2:
        log_sl = st.number_input("Stop Loss Price", value=0.0, format="%.5f")
        log_tp = st.number_input("Take Profit Price", value=0.0, format="%.5f")

      c3, c4 = st.columns(2)
      with c3:
        log_risk = st.number_input(
            "Risk ($)", min_value=0.1, value=2.00, step=0.1
        )
        log_reward = st.number_input(
            "Target Reward ($)", min_value=0.1, value=4.00, step=0.1
        )
      with c4:
        log_notes = st.text_input(
            "Strategy Notes", value="ATR Volatility Sized Setup"
        )

      if st.form_submit_button(
          "💾 Save Trade to Active Journal", use_container_width=True
      ):
        calc_rrr = round(log_reward / log_risk, 2) if log_risk > 0 else 0.0
        save_trade(
            asset=log_asset,
            direction=log_dir,
            entry=log_entry,
            sl=log_sl,
            tp=log_tp,
            risk=log_risk,
            reward=log_reward,
            rrr=calc_rrr,
            status="OPEN",
            pnl=0.0,
            notes=log_notes,
        )
        st.success(f"Saved {log_asset} trade to active database.")


# ==========================================
# TAB 2: TRADE JOURNAL & PERFORMANCE TRACKER
# ==========================================
with tab_journal:
  st.title("📓 Trade Performance Dashboard")

  trades_df = fetch_trades()

  if trades_df.empty:
    st.info("No trades logged yet. Run a scan and click 'Save Trade' to begin.")
  else:
    closed_trades = trades_df[trades_df["status"].isin(["WIN", "LOSS"])]
    total_closed = len(closed_trades)
    wins = len(trades_df[trades_df["status"] == "WIN"])
    losses = len(trades_df[trades_df["status"] == "LOSS"])
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
    net_pnl = trades_df["pnl"].sum()
    avg_rrr = trades_df["rrr"].mean() if not trades_df.empty else 0.0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Trades", len(trades_df))
    k2.metric(
        "Win Rate",
        f"{win_rate:.1f}%",
        f"{wins}W / {losses}L" if total_closed > 0 else "0 Closed",
    )
    k3.metric(
        "Net Realized PnL",
        f"${net_pnl:+.2f}",
        delta_color="normal" if net_pnl >= 0 else "inverse",
    )
    k4.metric("Avg Planned RRR", f"1:{avg_rrr:.2f}")

    st.divider()

    if total_closed > 0:
      st.subheader("📈 Cumulative Equity Curve ($)")
      closed_sorted = closed_trades.sort_values(by="id").copy()
      closed_sorted["Cumulative_PnL"] = closed_sorted["pnl"].cumsum()
      st.line_chart(
          closed_sorted.set_index("timestamp")["Cumulative_PnL"],
          use_container_width=True,
      )

    st.subheader("⏳ Active / Open Positions")
    open_trades = trades_df[trades_df["status"] == "OPEN"]

    if open_trades.empty:
      st.caption("No open positions pending.")
    else:
      for _, row in open_trades.iterrows():
        with st.expander(
            f"🔔 #{row['id']} | {row['asset']} — {row['direction']} (Entry:"
            f" {row['entry_price']})",
            expanded=True,
        ):
          st.write(
              f"**Risk:** ${row['risk_amount']:.2f} | **Target Reward:**"
              f" ${row['reward_amount']:.2f} | **Planned RRR:** 1:{row['rrr']}"
          )
          st.write(
              f"**Stop Loss:** `{row['stop_loss']}` | **Take Profit:**"
              f" `{row['take_profit']}`"
          )
          if row["notes"]:
            st.caption(f"Strategy Notes: {row['notes']}")

          row_tv = TRADINGVIEW_SYMBOLS.get(row["asset"], "FX:EURUSD")
          st.link_button(
              f"📱 Open {row['asset']} on TradingView",
              f"https://www.tradingview.com/chart/?symbol={row_tv}&interval=60",
              use_container_width=True,
          )

          b1, b2, b3, b4 = st.columns(4)
          with b1:
            if st.button(f"✅ WIN (+${row['reward_amount']})", key=f"w_{row['id']}"):
              update_trade_outcome(row["id"], "WIN", float(row["reward_amount"]))
              st.rerun()
          with b2:
            if st.button(f"❌ LOSS (-${row['risk_amount']})", key=f"l_{row['id']}"):
              update_trade_outcome(
                  row["id"], "LOSS", -float(row["risk_amount"])
              )
              st.rerun()
          with b3:
            if st.button("⚖️ BE ($0.00)", key=f"be_{row['id']}"):
              update_trade_outcome(row["id"], "BREAKEVEN", 0.0)
              st.rerun()
          with b4:
            if st.button("🗑️ Delete", key=f"del_{row['id']}"):
              delete_trade(row["id"])
              st.rerun()

    st.divider()
    st.subheader("📋 Trade Log History")
    display_cols = [
        "id",
        "timestamp",
        "asset",
        "direction",
        "entry_price",
        "status",
        "pnl",
        "rrr",
        "notes",
    ]
    st.dataframe(trades_df[display_cols], use_container_width=True)
