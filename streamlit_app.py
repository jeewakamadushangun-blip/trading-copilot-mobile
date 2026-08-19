import os
import pandas as pd
import streamlit as st
import yfinance as yf
from google import genai

# Mobile page layout configuration
st.set_page_config(
    page_title="AI Trading Copilot",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("📈 AI Trading Copilot")
st.caption("Institutional Market Scanner & Risk Guardian")

# 1. API Key Input
api_key = st.text_input(
    "Gemini API Key",
    type="password",
    placeholder="Paste your AI Studio API key...",
    help="Your key is not stored or shared.",
)

# 2. Controls
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

# 3. Execution Function
if st.button("🔍 Scan Market & Generate Blueprint", use_container_width=True):
  if not api_key:
    st.error("Please enter your Gemini API Key above.")
  else:
    with st.spinner("Analyzing market structure and querying AI..."):
      try:
        ticker_symbol = pair_choice.split("(")[1].replace(")", "").strip()

        # Fetch market data
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="5d", interval="1h", timeout=10)

        if df.empty or len(df) < 30:
          st.error("Could not fetch sufficient market data. Try another pair.")
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
              "BULLISH (Uptrend)"
              if current_price > ema50 and ema9 > ema50
              else (
                  "BEARISH (Downtrend)"
                  if current_price < ema50 and ema9 < ema50
                  else "NEUTRAL / CONSOLIDATION"
              )
          )

          market_summary = f"""
                    ASSET: {pair_choice}
                    Current Live Price: {current_price:.5f}
                    9 EMA: {ema9:.5f}
                    50 EMA: {ema50:.5f}
                    24h High: {session_high:.5f}
                    24h Low: {session_low:.5f}
                    Trend State: {trend}
                    Account Capital: ${account_balance:.2f}
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

                    Keep it structured, clean, and concise for rapid manual order entry.
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
            st.success("Blueprint Generated Successfully!")
            st.markdown(blueprint_text)
          else:
            st.error(
                "High model demand across all endpoints. Please retry in a few"
                " seconds."
            )

      except Exception as e:
        st.error(f"Error: {str(e)}")
