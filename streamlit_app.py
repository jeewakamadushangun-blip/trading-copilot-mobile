from datetime import datetime
import json
import os
import sqlite3
import pandas as pd
import streamlit as st
import yfinance as yf
from google import genai

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="AI Trading Copilot & Journal",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

DB_FILE = "trades.db"


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
  df = pd.read_sql_query(
      "SELECT * FROM trades ORDER BY id DESC",
      conn,
  )
  conn.close()
  return df


def update_trade_outcome(trade_id, status, pnl):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute(
      """
        UPDATE trades
        SET status = ?, pnl = ?
        WHERE id = ?
    """,
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

# --- APP NAVIGATION ---
tab_scan, tab_journal = st.tabs(
    ["🔍 Market Scanner", "📓 Trade Journal & Analytics"]
)

# ==========================================
# TAB 1: SCANNER & BLUEPRINT GENERATOR
# ==========================================
with tab_scan:
  st.title("📈 AI Trading Copilot")
  st.caption("Institutional Risk Engine & Live Blueprint Generator")

  default_key = ""
  if "GEMINI_API_KEY" in st.secrets:
    default_key = st.secrets["GEMINI_API_KEY"]

  api_key = st.text_input(
      "Gemini API Key",
      value=default_key,
      type="password",
      placeholder="Paste your AI Studio API key...",
      help="Auto-loaded from Streamlit Secrets if configured.",
  )

  col1, col2 = st.columns(2)
  with col1:
    pair_choice = st.selectbox(
        "Select Asset",
        options=[
            "EUR/USD (EURUSD=X)",
            "GBP/USD (GBPUSD=X)",
            "USD/JPY (JPY=X)",
            "Gold / USD (GC=F)",
        ],
    )
  with col2:
    account_balance = st.number_input(
        "Capital ($)", min_value=10.0, value=100.0, step=10.0
    )

  if st.button("🔍 Scan Market & Generate Blueprint", use_container_width=True):
    if not api_key:
      st.error("Please provide a valid Gemini API Key.")
    else:
      with st.spinner("Fetching candle feeds and computing technical math..."):
        try:
          ticker_symbol = pair_choice.split("(")[1].replace(")", "").strip()
          ticker = yf.Ticker(ticker_symbol)
          df = ticker.history(period="5d", interval="1h", timeout=10)

          if df.empty or len(df) < 30:
            st.error("Insufficient market data. Please try another asset.")
          else:
            df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
            df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()

            latest = df.iloc[-1]
            current_price = latest["Close"]
            ema9 = latest["EMA_9"]
            ema50 = latest["EMA_50"]
            session_high = df["High"].tail(24).max()
            session_low = df["Low"].tail(24).min()

            trend = (
                "BULLISH"
                if current_price > ema50 and ema9 > ema50
                else (
                    "BEARISH"
                    if current_price < ema50 and ema9 < ema50
                    else "NEUTRAL"
                )
            )

            market_summary = f"""
                        ASSET: {pair_choice}
                        Live Price: {current_price:.5f}
                        9 EMA: {ema9:.5f}
                        50 EMA: {ema50:.5f}
                        24h High: {session_high:.5f}
                        24h Low: {session_low:.5f}
                        Trend Regime: {trend}
                        Capital: ${account_balance:.2f}
                        """

            client = genai.Client(api_key=api_key)

            prompt = f"""
                        You are an institutional Forex Trading Risk Guardian.
                        Analyze this live technical snapshot:
                        {market_summary}

                        Formulate a clear Trade Blueprint Card.
                        Strict Rules:
                        1. Max risk must strictly be 1.5% to 2.5% of ${account_balance:.2f} (Under $2.50 risk for a $100 balance).
                        2. Recommended position size must be 1,000 units (0.01 micro lot).
                        3. Provide exact numeric values for:
                           - Trade Setup / Direction (e.g. Buy Limit or Sell Limit)
                           - Recommended Entry Price
                           - Strict Stop Loss Price (with dollar loss amount)
                           - Take Profit Target Price (with dollar gain amount)
                           - Risk-to-Reward Ratio (Must be at least 1:1.5)
                           - Thesis (2 concise sentences on EMA support/resistance)
                           - 15-Second Action Plan for the user on TradingView.

                        Keep it clean, concise, and structured for rapid order execution.
                        """

            models_to_try = [
                "gemini-3.6-flash",
                "gemini-1.5-flash",
                "gemini-1.5-pro",
            ]
            blueprint_text = None

            for model_name in models_to_try:
              try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                blueprint_text = response.text
                break
              except Exception:
                continue

            if blueprint_text:
              st.session_state["last_blueprint"] = blueprint_text
              st.session_state["last_asset"] = pair_choice
              st.session_state["last_price"] = current_price
              st.success("Blueprint Generated Successfully!")
              st.markdown(blueprint_text)
            else:
              st.error(
                  "High API traffic. Please retry your scan in a few seconds."
              )

        except Exception as e:
          st.error(f"Execution Error: {str(e)}")

  # Quick-Log Section
  if "last_blueprint" in st.session_state:
    st.divider()
    st.subheader("📥 Log Setup to Journal")
    with st.form("log_trade_form"):
      f_col1, f_col2, f_col3 = st.columns(3)
      with f_col1:
        log_asset = st.text_input(
            "Asset", value=st.session_state.get("last_asset", "EUR/USD")
        )
        log_direction = st.selectbox(
            "Direction", ["BUY LIMIT", "SELL LIMIT", "BUY", "SELL"]
        )
      with f_col2:
        log_entry = st.number_input(
            "Entry Price",
            value=float(st.session_state.get("last_price", 1.0)),
            format="%.5f",
        )
        log_sl = st.number_input("Stop Loss Price", value=0.0, format="%.5f")
      with f_col3:
        log_tp = st.number_input("Take Profit Price", value=0.0, format="%.5f")
        log_risk = st.number_input(
            "Risk ($)", min_value=0.1, value=2.00, step=0.1
        )

      f_col4, f_col5 = st.columns(2)
      with f_col4:
        log_reward = st.number_input(
            "Reward ($)", min_value=0.1, value=3.80, step=0.1
        )
      with f_col5:
        log_notes = st.text_input(
            "Trade Notes / Strategy", value="9 EMA Dynamic Pullback"
        )

      submit_trade = st.form_submit_button(
          "💾 Save Trade to Active Journal", use_container_width=True
      )
      if submit_trade:
        calc_rrr = round(log_reward / log_risk, 2) if log_risk > 0 else 0.0
        save_trade(
            asset=log_asset,
            direction=log_direction,
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
            f"Logged {log_asset} trade successfully! View it under the"
            " 'Trade Journal' tab."
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
    # 1. Performance KPI Cards
    closed_trades = trades_df[trades_df["status"].isin(["WIN", "LOSS"])]
    total_closed = len(closed_trades)
    wins = len(trades_df[trades_df["status"] == "WIN"])
    losses = len(trades_df[trades_df["status"] == "LOSS"])
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
    net_pnl = trades_df["pnl"].sum()
    avg_rrr = trades_df["rrr"].mean() if not trades_df.empty else 0.0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Trades", len(trades_df))
    kpi2.metric(
        "Win Rate",
        f"{win_rate:.1f}%",
        f"{wins}W / {losses}L" if total_closed > 0 else "0 Closed",
    )
    kpi3.metric(
        "Net Realized PnL",
        f"${net_pnl:+.2f}",
        delta_color="normal" if net_pnl >= 0 else "inverse",
    )
    kpi4.metric("Avg Planned RRR", f"1:{avg_rrr:.2f}")

    st.divider()

    # 2. Equity Growth Visualizer
    if total_closed > 0:
      st.subheader("📈 Cumulative Equity Curve ($)")
      closed_sorted = closed_trades.sort_values(by="id").copy()
      closed_sorted["Cumulative_PnL"] = closed_sorted["pnl"].cumsum()
      st.line_chart(
          closed_sorted.set_index("timestamp")["Cumulative_PnL"],
          use_container_width=True,
      )

    # 3. Active / Open Positions Manager
    st.subheader("⏳ Active / Open Trades")
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

          c1, c2, c3, c4 = st.columns(4)
          with c1:
            if st.button(f"✅ Mark WIN (+${row['reward_amount']})", key=f"w_{row['id']}"):
              update_trade_outcome(row["id"], "WIN", float(row["reward_amount"]))
              st.rerun()
          with c2:
            if st.button(
                f"❌ Mark LOSS (-${row['risk_amount']})", key=f"l_{row['id']}"
            ):
              update_trade_outcome(
                  row["id"], "LOSS", -float(row["risk_amount"])
              )
              st.rerun()
          with c3:
            if st.button("⚖️ Mark BE ($0.00)", key=f"be_{row['id']}"):
              update_trade_outcome(row["id"], "BREAKEVEN", 0.0)
              st.rerun()
          with c4:
            if st.button("🗑️ Delete", key=f"del_{row['id']}"):
              delete_trade(row["id"])
              st.rerun()

    st.divider()

    # 4. Complete Trade History Log
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
