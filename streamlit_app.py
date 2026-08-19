import concurrent.futures
from datetime import datetime
import os
import sqlite3
import pandas as pd
import streamlit as st
import yfinance as yf
from google import genai

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="AI Multi-Asset Radar & Copilot",
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


# --- PARALLEL MARKET DATA FETCHER ---
def fetch_single_asset(name, symbol):
  try:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="5d", interval="1h", timeout=10)
    if df.empty or len(df) < 30:
      return None

    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()

    latest = df.iloc[-1]
    current_price = latest["Close"]
    ema9 = latest["EMA_9"]
    ema50 = latest["EMA_50"]
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
# TAB 1: MULTI-ASSET RADAR & OPPORTUNITY SCAN
# ==========================================
with tab_radar:
  st.title("📡 Institutional Multi-Asset Radar")
  st.caption(
      "Parallel Market Scanner & AI Opportunity Screener (EUR/USD, GBP/USD,"
      " USD/JPY, Gold)"
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
      help="Auto-loaded from Streamlit Secrets.",
  )

  active_api_key = api_key_input.strip().strip('"').strip("'")

  account_balance = st.number_input(
      "Trading Capital ($)", min_value=10.0, value=100.0, step=10.0
  )

  if st.button("🚀 Scan All 4 Assets Simultaneously", use_container_width=True):
    if not active_api_key:
      st.error("Please enter or verify your Gemini API Key above.")
    else:
      with st.spinner("Fetching parallel feeds & analyzing institutional setups..."):
        try:
          radar_data = fetch_all_radar_data()

          if len(radar_data) < 2:
            st.error(
                "Unable to fetch live feeds. Check internet connectivity and"
                " retry."
            )
          else:
            # 1. Display Quick Metric Overview
            st.subheader("⚡ Live Market Structure Snapshot")
            m_cols = st.columns(len(radar_data))
            for idx, (name, d) in enumerate(radar_data.items()):
              with m_cols[idx]:
                st.metric(
                    label=name,
                    value=f"{d['price']:.4f}",
                    delta=d["trend"].split(" ")[0],
                )

            # 2. Build AI Prompt Context
            market_snapshot_text = ""
            for name, d in radar_data.items():
              market_snapshot_text += f"""
ASSET: {name} ({d['symbol']})
- Live Price: {d['price']:.5f}
- 9 EMA: {d['ema9']:.5f} | 50 EMA: {d['ema50']:.5f}
- 24h High: {d['high']:.5f} | 24h Low: {d['low']:.5f}
- Structural Regime: {d['trend']}
"""

            max_risk_cap = account_balance * 0.025
            prompt = f"""
You are an elite Institutional Forex Screener and Risk Guardian.
Analyze this synchronized 4-asset technical snapshot:
{market_snapshot_text}

Trading Capital: ${account_balance:.2f} (Strict 1.5% to 2.5% max risk: Under ${max_risk_cap:.2f}).
Position Sizing: 0.01 micro lot (1,000 units).

Output a clean report with these two sections:

## 1. WATCHLIST OPPORTUNITY RADAR
Rank every asset with an Opportunity Grade:
- **Grade A+ (Prime Pullback / High Probability)**
- **Grade B (Secondary / Momentum Play)**
- **No Trade (Consolidation, Choppy EMA, or Overextended)**
Provide a 1-sentence technical justification for each.

## 2. TOP ACTIONABLE BLUEPRINT CARD (Highest-Ranked Setup)
Provide the full execution card for the top asset:
- **Asset & Setup Direction**: (e.g. EUR/USD - BUY LIMIT)
- **Recommended Entry Price**:
- **Strict Stop Loss Price**: (State dollar loss under ${max_risk_cap:.2f})
- **Take Profit Target Price**: (State dollar reward)
- **Risk-to-Reward Ratio**: (Must exceed 1:1.5)
- **Core Institutional Thesis**: (2 sentences on EMA support/resistance)
- **15-Second Action Plan on TradingView**: (3 clean execution steps)
"""

            client = genai.Client(api_key=active_api_key)
            models_to_try = [
                "gemini-2.0-flash",
                "gemini-1.5-flash",
            ]
            blueprint_text = None
            error_messages = []

            for model_name in models_to_try:
              try:
                response = client.models.generate_content(
                    model=model_name, contents=prompt
                )
                if response.text:
                  blueprint_text = response.text
                  break
              except Exception as e:
                error_messages.append(f"{model_name}: {str(e)}")
                continue

            if blueprint_text:
              st.session_state["radar_blueprint"] = blueprint_text
              st.session_state["radar_data"] = radar_data
              st.success("Radar Scan Complete!")
              st.markdown(blueprint_text)
            else:
              st.error("API Errors: " + " | ".join(error_messages))

        except Exception as e:
          st.error(f"Scan Error: {str(e)}")

  # Quick-Log Section
  if "radar_blueprint" in st.session_state:
    st.divider()
    st.subheader("📥 Quick Log Selected Setup to Journal")
    with st.form("quick_log_form"):
      c1, c2, c3 = st.columns(3)
      with c1:
        log_asset = st.selectbox("Asset", list(ASSETS.keys()))
        log_dir = st.selectbox(
            "Direction", ["BUY LIMIT", "SELL LIMIT", "BUY", "SELL"]
        )
      with c2:
        default_entry = st.session_state["radar_data"][log_asset]["price"]
        log_entry = st.number_input(
            "Entry Price", value=float(default_entry), format="%.5f"
        )
        log_sl = st.number_input("Stop Loss Price", value=0.0, format="%.5f")
      with c3:
        log_tp = st.number_input("Take Profit Price", value=0.0, format="%.5f")
        log_risk = st.number_input(
            "Risk ($)", min_value=0.1, value=2.00, step=0.1
        )

      c4, c5 = st.columns(2)
      with c4:
        log_reward = st.number_input(
            "Target Reward ($)", min_value=0.1, value=4.00, step=0.1
        )
      with c5:
        log_notes = st.text_input(
            "Strategy Notes", value="Multi-Asset Radar A+ Setup"
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
        st.success(
            f"Saved {log_asset} trade. Open the 'Trade Journal' tab to manage"
            " it."
        )


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
