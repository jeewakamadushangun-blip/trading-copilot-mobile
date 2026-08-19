import os
import threading
import customtkinter as ctk
import pandas as pd
import yfinance as yf
from google import genai

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class TradingCopilotApp(ctk.CTk):

  def __init__(self):
    super().__init__()

    self.title("AI Trading Copilot — Market Scanner")
    self.geometry("720x800")
    self.resizable(False, False)

    # 1. Top Header
    self.header_label = ctk.CTkLabel(
        self,
        text="AI Trading Copilot (Human-in-the-Loop)",
        font=ctk.CTkFont(size=20, weight="bold"),
    )
    self.header_label.pack(pady=(15, 5))

    self.sub_label = ctk.CTkLabel(
        self,
        text="Scans EMA Bounces & Structure • Pre-calculates exact SL/TP/Risk",
        font=ctk.CTkFont(size=12),
        text_color="gray",
    )
    self.sub_label.pack(pady=(0, 15))

    # 2. API Key Entry Frame
    self.key_frame = ctk.CTkFrame(self)
    self.key_frame.pack(fill="x", padx=20, pady=5)

    self.key_label = ctk.CTkLabel(
        self.key_frame, text="Gemini API Key:", font=ctk.CTkFont(size=12)
    )
    self.key_label.pack(side="left", padx=10, pady=10)

    self.api_key_entry = ctk.CTkEntry(
        self.key_frame,
        placeholder_text="Paste your Google AI Studio API key...",
        show="*",
        width=420,
    )
    self.api_key_entry.pack(side="left", padx=10, pady=10)

    # 3. Pair Selection & Balance Controls
    self.controls_frame = ctk.CTkFrame(self)
    self.controls_frame.pack(fill="x", padx=20, pady=10)

    self.pair_label = ctk.CTkLabel(
        self.controls_frame,
        text="Select Asset:",
        font=ctk.CTkFont(size=12, weight="bold"),
    )
    self.pair_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")

    self.pair_menu = ctk.CTkOptionMenu(
        self.controls_frame,
        values=[
            "EUR/USD (EURUSD=X)",
            "GBP/USD (GBPUSD=X)",
            "USD/JPY (JPY=X)",
            "Gold / USD (GC=F)",
        ],
    )
    self.pair_menu.grid(row=0, column=1, padx=10, pady=10)

    self.balance_label = ctk.CTkLabel(
        self.controls_frame,
        text="Account Capital ($):",
        font=ctk.CTkFont(size=12, weight="bold"),
    )
    self.balance_label.grid(row=0, column=2, padx=10, pady=10, sticky="w")

    self.balance_entry = ctk.CTkEntry(self.controls_frame, width=80)
    self.balance_entry.insert(0, "100.00")
    self.balance_entry.grid(row=0, column=3, padx=10, pady=10)

    # 4. Action Button
    self.scan_button = ctk.CTkButton(
        self,
        text="🔍 Scan Market & Generate Blueprint",
        font=ctk.CTkFont(size=14, weight="bold"),
        height=40,
        command=self.start_scan_thread,
    )
    self.scan_button.pack(fill="x", padx=20, pady=10)

    # 5. Output Card Display
    self.output_textbox = ctk.CTkTextbox(
        self, font=ctk.CTkFont(family="Consolas", size=13), wrap="word"
    )
    self.output_textbox.pack(fill="both", expand=True, padx=20, pady=(5, 15))
    self.output_textbox.insert(
        "0.0",
        "Ready. Paste your Gemini API key, select a pair, and click 'Scan"
        " Market'.",
    )

  def start_scan_thread(self):
    self.scan_button.configure(state="disabled", text="Scanning Market Feed...")
    self.output_textbox.delete("0.0", "end")
    self.output_textbox.insert(
        "0.0",
        "⏳ Fetching live hourly candles, calculating 9/50 EMAs, and querying"
        " Gemini...\n",
    )
    threading.Thread(target=self.run_market_analysis, daemon=True).start()

  def run_market_analysis(self):
    try:
      api_key = self.api_key_entry.get().strip() or os.getenv("GEMINI_API_KEY")
      if not api_key:
        self.show_result(
            "❌ Error: Please paste your Gemini API key into the top input"
            " box."
        )
        return

      pair_choice = self.pair_menu.get()
      ticker_symbol = pair_choice.split("(")[1].replace(")", "").strip()
      account_balance = float(self.balance_entry.get().replace("$", "").strip())

      # 1. Fetch live 1-hour candle data
      ticker = yf.Ticker(ticker_symbol)
      df = ticker.history(period="5d", interval="1h")

      if df.empty or len(df) < 50:
        self.show_result(
            "❌ Error: Could not fetch sufficient live market candle data."
        )
        return

      # 2. Calculate Indicators
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

      # 3. Query Gemini via official google-genai SDK
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

      response = client.models.generate_content(
          model="gemini-2.5-flash",
          contents=prompt,
      )

      self.show_result(response.text)

    except Exception as e:
      self.show_result(f"❌ Error occurred: {str(e)}")

  def show_result(self, text):
    self.output_textbox.delete("0.0", "end")
    self.output_textbox.insert("0.0", text)
    self.scan_button.configure(
        state="normal", text="🔍 Scan Market & Generate Blueprint"
    )


if __name__ == "__main__":
  app = TradingCopilotApp()
  app.mainloop()