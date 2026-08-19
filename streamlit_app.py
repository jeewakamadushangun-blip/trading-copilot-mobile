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
    page_title="AI Multi-Asset Radar & Auto-Journal",
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

DXY_SYMBOL = "DX-Y.NYB"

TRADINGVIEW_SYMBOLS = {
    "EUR/USD": "FX:EURUSD",
    "GBP/USD": "FX:GBPUSD",
    "USD/JPY": "FX:USDJPY",
    "Gold / USD": "OANDA:XAUUSD",
}


# --- DATABASE LAYER ---
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


def auto_resolve_open_trades():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("SELECT * FROM trades WHERE status = 'OPEN'")
  open_trades = cursor.fetchall()

  if not open_trades:
    conn.close()
    return 0

  resolved_count = 0
  for trade in open_trades:
    trade_id = trade[0]
    asset_name = trade[2]
    direction = trade[3]
    entry_price = float(trade[4])
    stop_loss = float(trade[5])
    take_profit = float(trade[6])
    risk_amt = float(trade[7])
    reward_amt = float(trade[8])

    symbol = ASSETS.get(asset_name)
    if not symbol or stop_loss == 0.0 or take_profit == 0.0:
      continue

    try:
      ticker = yf.Ticker(symbol)
      df = ticker.history(period="5d", interval="1h")
      if df.empty:
        continue

      recent_high = df["High"].max()
      recent_low = df["Low"].min()

      outcome = None
      pnl = 0.0

      if "BUY" in direction.upper():
        if recent_high >= take_profit:
          outcome = "WIN"
          pnl = reward_amt
        elif recent_low <= stop_loss:
          outcome = "LOSS"
          pnl = -risk_amt

      elif "SELL" in direction.upper():
        if recent_low <= take_profit:
          outcome = "WIN"
          pnl = reward_amt
        elif recent_high >= stop_loss:
          outcome = "LOSS"
          pnl = -risk_amt

      if outcome:
        cursor.execute(
            "UPDATE trades SET status = ?, pnl = ? WHERE id = ?",
            (outcome, pnl, trade_id),
        )
        resolved_count += 1

    except Exception:
      continue

  conn.commit()
  conn.close()
  return resolved_count


init_db()


# --- INDICATORS & TECHNICAL ANALYSIS ---
def compute_atr(df, period=14):
  high = df["High"]
  low = df["Low"]
  close = df["Close"].shift(1)
  tr1 = high - low
  tr2 = (high - close).abs()
  tr3 = (low - close).abs()
  tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
  return tr.rolling(window=period).mean()


def fetch_dxy_regime():
  try:
    ticker = yf.Ticker(DXY_SYMBOL)
    df = ticker.history(period="10d", interval="1h", timeout=10)
    if df.empty or len(df) < 50:
      return {"price": 0.0, "trend": "NEUTRAL", "bias": "No Bias"}
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()
    price = df["Close"].iloc[-1]
    ema9 = df["EMA_9"].iloc[-1]
    ema50 = df["EMA_50"].iloc[-1]

    if price > ema50 and ema9 > ema50:
      return {
          "price": price,
          "trend": "BULLISH 🟢",
          "bias": "FAVOR USD BUYS & EUR/GBP/GOLD SELLS",
      }
    elif price < ema50 and ema9 < ema50:
      return {
          "price": price,
          "trend": "BEARISH 🔴",
          "bias": "FAVOR EUR/GBP/GOLD BUYS & USD SELLS",
      }
    return {"price": price, "trend": "CHOP / RANGE ⚪", "bias": "NEUTRAL"}
  except Exception:
    return {"price": 0.0, "trend": "UNAVAILABLE", "bias": "Standard"}


def fetch_single_asset(name, symbol):
  try:
    ticker = yf.Ticker(symbol)
    df_1h = ticker.history(period="30d", interval="1h", timeout=10)
    if df_1h.empty or len(df_1h) < 100:
      return None

    df_1h["EMA_9"] = df_1h["Close"].ewm(span=9, adjust=False).mean()
    df_1h["EMA_50"] = df_1h["Close"].ewm(span=50, adjust=False).mean()
    df_1h["EMA_200"] = df_1h["Close"].ewm(span=200, adjust=False).mean()
    df_1h["ATR"] = compute_atr(df_1h, period=14)

    latest_1h = df_1h.iloc[-1]
    price = latest_1h["Close"]
    ema9_1h = latest_1h["EMA_9"]
    ema50_1h = latest_1h["EMA_50"]
    ema200_1h = latest_1h["EMA_200"]
    atr = latest_1h["ATR"]

    df_4h = (
        df_1h.resample("4h")
        .agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        })
        .dropna()
    )
    df_4h["EMA_50"] = df_4h["Close"].ewm(span=50, adjust=False).mean()
    ema50_4h = df_4h["EMA_50"].iloc[-1]

    trend_4h = "BULLISH 🟢" if price > ema50_4h else "BEARISH 🔴"
    trend_1h = (
        "BULLISH 🟢"
        if price > ema50_1h and ema9_1h > ema50_1h
        else (
            "BEARISH 🔴"
            if price < ema50_1h and ema9_1h < ema50_1h
            else "CHOP ⚪"
        )
    )

    if "BULLISH" in trend_1h and "BULLISH" in trend_4h:
      mtf_status = "ALIGNED BULLISH 🚀"
    elif "BEARISH" in trend_1h and "BEARISH" in trend_4h:
      mtf_status = "ALIGNED BEARISH 📉"
    else:
      mtf_status = "CONFLICT / WAIT ⚠️"

    return {
        "asset": name,
        "symbol": symbol,
        "price": price,
        "ema9_1h": ema9_1h,
        "ema50_1h": ema50_1h,
        "ema200_1h": ema200_1h,
        "ema50_4h": ema50_4h,
        "trend_1h": trend_1h,
        "trend_4h": trend_4h,
        "mtf_status": mtf_status,
        "atr": atr,
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
# TAB 1: RADAR & AI BLUEPRINT
# ==========================================
with tab_radar:
  st.title("📡 Multi-Asset Radar & Copilot")
  st.caption("4H Trend Stacking • DXY Macro Shield • Dynamic 1.5x ATR Stops")

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

  if st.button(
      "🚀 Scan 4 Assets + 4H Trend Stacking + DXY", use_container_width=True
  ):
    if not active_api_key:
      st.error("Please enter your Gemini API Key above.")
    else:
      with st.spinner(
          "Synchronizing 4H macro trends, 1H pullbacks, and DXY regime..."
      ):
        try:
          dxy_data = fetch_dxy_regime()
          radar_data = fetch_all_radar_data()

          if len(radar_data) < 2:
            st.error("Unable to load market feeds. Please retry.")
          else:
            st.info(
                f"💵 **Macro DXY Regime:** {dxy_data['price']:.2f} —"
                f" {dxy_data['trend']} | **Bias:** {dxy_data['bias']}"
            )

            st.subheader("⚡ Multi-Timeframe Alignment Matrix")
            m_cols = st.columns(len(radar_data))
            for idx, (name, d) in enumerate(radar_data.items()):
              with m_cols[idx]:
                st.metric(
                    label=name,
                    value=f"{d['price']:.4f}",
                    delta=d["mtf_status"].split(" ")[0],
                )
                st.caption(
                    f"1H: {d['trend_1h'].split(' ')[0]} | 4H:"
                    f" {d['trend_4h'].split(' ')[0]}"
                )
                tv_sym = TRADINGVIEW_SYMBOLS.get(name, "FX:EURUSD")
                st.link_button(
                    "📈 Chart",
                    f"https://www.tradingview.com/chart/?symbol={tv_sym}&interval=60",
                    use_container_width=True,
                )

            market_snapshot_text = (
                f"MACRO US DOLLAR INDEX (DXY): {dxy_data['price']:.3f} |"
                f" Regime: {dxy_data['trend']} | Recommended Bias:"
                f" {dxy_data['bias']}\n"
            )
            for name, d in radar_data.items():
              market_snapshot_text += f"""
ASSET: {name} ({d['symbol']})
- Live Price: {d['price']:.5f} | 14 ATR: {d['atr']:.5f} (1.5x SL: {1.5 * d['atr']:.5f})
- 1-Hour: 9 EMA: {d['ema9_1h']:.5f} | 50 EMA: {d['ema50_1h']:.5f} | 200 EMA: {d['ema200_1h']:.5f} ({d['trend_1h']})
- 4-Hour: 50 EMA: {d['ema50_4h']:.5f} ({d['trend_4h']})
- Multi-Timeframe Status: {d['mtf_status']}
"""

            max_risk_cap = account_balance * 0.025
            prompt = f"""
You are an institutional FX Risk Guardian.
Review this 4-asset multi-timeframe snapshot with 4H trend stacking and DXY correlation:
{market_snapshot_text}

Account Capital: ${account_balance:.2f} (Strict max loss under ${max_risk_cap:.2f}).
Position Sizing: 0.01 micro lot (1,000 units).

RULES:
- ONLY allow BUY setups if 1-Hour is Bullish AND 4-Hour is Bullish (Price > 4H 50 EMA).
- ONLY allow SELL setups if 1-Hour is Bearish AND 4-Hour is Bearish (Price < 4H 50 EMA).
- DXY Alignment: If DXY is Bullish, reject EUR/GBP/Gold Buys. If Bearish, reject EUR/GBP/Gold Sells.

Output:
## 1. WATCHLIST OPPORTUNITY RADAR
Rank all 4 pairs and check MTF + DXY confluence.

## 2. TOP ACTIONABLE BLUEPRINT CARD (Highest 4H-Aligned Setup)
- **Asset & Order Type**: (e.g. EUR/USD - BUY LIMIT)
- **Recommended Entry Price**:
- **Dynamic ATR Stop Loss Price**: (1.5x ATR buffer, dollar risk under ${max_risk_cap:.2f})
- **Take Profit Target Price**: (3.0x ATR buffer for 1:2 RRR)
- **4H + 1H Alignment Thesis**: (2 simple sentences)
- **15-Second Action Plan on TradingView**: (3 clean execution steps)
"""

            client = genai.Client(api_key=active_api_key)
            response = client.models.generate_content(
                model="gemini-3.6-flash", contents=prompt
            )

            if response.text:
              st.session_state["radar_blueprint"] = response.text
              st.session_state["radar_data"] = radar_data
              st.success("4H Trend Stacking Scan Complete!")
              st.markdown(response.text)
            else:
              st.error("Failed to generate blueprint. Please retry.")

        except Exception as e:
          st.error(f"Scan Error: {str(e)}")

  # Quick-Log Section
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
            "Strategy Notes", value="4H-Aligned ATR Setup"
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
        st.success(f"Saved {log_asset} trade. Auto-Tracking is now active!")


# ==========================================
# TAB 2: AUTOMATED JOURNAL & ANALYTICS
# ==========================================
with tab_journal:
  st.title("📓 Trade Performance Dashboard")

  # Auto-resolve any open trades that reached TP/SL in recent market candles
  resolved_trades = auto_resolve_open_trades()
  if resolved_trades > 0:
    st.toast(
        f"🎯 {resolved_trades} open position(s) reached TP/SL and were"
        " auto-resolved!",
        icon="🔔",
    )

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

    st.subheader("⏳ Active / Open Positions (Auto-Tracking)")
    open_trades = trades_df[trades_df["status"] == "OPEN"]

    if open_trades.empty:
      st.caption("No active positions open. All orders resolved.")
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
