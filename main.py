"""
🚀 Multi-Timeframe Breakout Trading Bot
Author: [Senin Adın]
Description: 
A trend-following breakout strategy utilizing Multi-Timeframe Analysis (1H, 4H, 1D).
Features:
- Dynamic ATR-based Stop Loss & Trailing Stop
- Volume & Trend Strength (ADX) Filtering
- Risk Management (Fixed % Risk per Trade)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import warnings
import pandas_ta as ta

warnings.filterwarnings('ignore')
plt.style.use('ggplot')

class TradingBot:
    def __init__(self, filepath, initial_capital=10000):
        self.filepath = filepath
        self.capital = initial_capital
        self.df = None
        
        # Strategy Parameters (Optimized for Stability)
        self.params = {
            "ema_period": 50,
            "mtf_min_align": 3,
            "buffer_pct": 0.015,
            "sl_atr": 3.5,
            "be_atr": 2.0,
            "trail_atr": 2.0,
            "risk_per_trade": 0.01,
            "min_vol_filter": 1.2,
            "adx_threshold": 25
        }

    def load_data(self):
        df = pd.read_csv(self.filepath, index_col="time", parse_dates=["time"])
        self.df = df[["open", "high", "low", "close", "volume"]].astype(float)
        self.df.sort_index(inplace=True)
        print(f"✅ Data Loaded: {len(self.df)} candles ({self.df.index[0].date()} to {self.df.index[-1].date()})")

    def add_indicators(self):
        df = self.df
        p = self.params
        
        df["ema_1h"] = df["close"].ewm(span=p["ema_period"], adjust=False).mean()
        df["ema_4h"] = df["close"].resample("4h").last().ewm(span=p["ema_period"], adjust=False).mean().reindex(df.index).ffill()
        df["ema_1d"] = df["close"].resample("1D").last().ewm(span=p["ema_period"], adjust=False).mean().reindex(df.index).ffill()
        
        df["prev_high"] = df["high"].resample("1D").max().shift(1).reindex(df.index).ffill()
        df["prev_low"]  = df["low"].resample("1D").min().shift(1).reindex(df.index).ffill()
        
        prev_c = df["close"].shift(1)
        tr = pd.concat([df["high"]-df["low"], (df["high"]-prev_c).abs(), (df["low"]-prev_c).abs()], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()
        df["vol_ma"] = df["volume"].rolling(20).mean()
        
        adx_data = ta.adx(df["high"], df["low"], df["close"], length=14)
        df["adx"] = adx_data["ADX_14"]
        
        self.df = df.dropna()

    def run_backtest(self):
        df = self.df
        p = self.params
        start_idx = 800
        
        equity_curve = [self.capital] * (start_idx + 1)
        trades = []
        in_trade = False
        position = {}
        
        print("🔄 Running Backtest Engine...")
        
        for i in range(start_idx, len(df)-1):
            row = df.iloc[i]
            next_row = df.iloc[i+1]
            
            # Filters
            if row["adx"] < p["adx_threshold"] or row["volume"] < row["vol_ma"] * p["min_vol_filter"]:
                equity_curve.append(self.capital) # ✅ HATA DÜZELTİLDİ: Filtre geçilse bile equity güncellenir
                continue
            
            up = int(row["close"] > row["ema_1h"]) + int(row["close"] > row["ema_4h"]) + int(row["close"] > row["ema_1d"])
            dn = int(row["close"] < row["ema_1h"]) + int(row["close"] < row["ema_4h"]) + int(row["close"] < row["ema_1d"])
            
            broke_high = row["close"] > (row["prev_high"] * (1 + p["buffer_pct"]))
            broke_low  = row["close"] < (row["prev_low"] * (1 - p["buffer_pct"]))
            
            if not in_trade:
                if broke_high and up >= p["mtf_min_align"]:
                    in_trade = True
                    position = {"side": "LONG", "entry": next_row["open"], "atr": row["atr"]}
                    position["sl"] = position["entry"] - p["sl_atr"] * position["atr"]
                    position["qty"] = (self.capital * p["risk_per_trade"]) / abs(next_row["open"] - position["sl"])
                elif broke_low and dn >= p["mtf_min_align"]:
                    in_trade = True
                    position = {"side": "SHORT", "entry": next_row["open"], "atr": row["atr"]}
                    position["sl"] = position["entry"] + p["sl_atr"] * position["atr"]
                    position["qty"] = (self.capital * p["risk_per_trade"]) / abs(next_row["open"] - position["sl"])
            
            if in_trade:
                if position["side"] == "LONG":
                    if next_row["high"] >= position["entry"] + p["be_atr"] * position["atr"]:
                        position["sl"] = max(position["sl"], position["entry"])
                    trail = next_row["close"] - p["trail_atr"] * position["atr"]
                    if trail > position["sl"]: position["sl"] = trail
                    if next_row["low"] <= position["sl"]:
                        pnl = (position["sl"] - position["entry"]) * position["qty"]
                        self.capital += pnl
                        trades.append({"pnl": pnl, "type": "LONG"})
                        in_trade = False
                else:
                    if next_row["low"] <= position["entry"] - p["be_atr"] * position["atr"]:
                        position["sl"] = min(position["sl"], position["entry"])
                    trail = next_row["close"] + p["trail_atr"] * position["atr"]
                    if trail < position["sl"]: position["sl"] = trail
                    if next_row["high"] >= position["sl"]:
                        pnl = (position["entry"] - position["sl"]) * position["qty"]
                        self.capital += pnl
                        trades.append({"pnl": pnl, "type": "SHORT"})
                        in_trade = False
            
            equity_curve.append(self.capital)
            
        self.equity_curve = equity_curve
        self.trades = trades
        self.print_results()

    def print_results(self):
        t = np.array([tr["pnl"] for tr in self.trades])
        if len(t) == 0:
            print("⚠️ No trades executed.")
            return
            
        wins = t[t > 0]
        losses = t[t <= 0]
        wr = len(wins) / len(t)
        pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 else np.inf
        
        years = (self.df.index[-1] - self.df.index[800]).days / 365
        cagr = ((self.capital / 10000) ** (1/years) - 1) * 100
        
        print("\n" + "="*50)
        print("📊 BACKTEST RESULTS")
        print("="*50)
        print(f"Period: {years:.1f} Years")
        print(f"Total Trades: {len(t)}")
        print(f"Win Rate: {wr*100:.1f}%")
        print(f"Profit Factor: {pf:.2f}")
        print(f"CAGR: {cagr:.1f}%")
        print(f"Final Capital: ${self.capital:,.0f}")
        print("="*50)
        
        # ✅ HATA DÜZELTİLDİ: Index ve equity uzunlukları senkronize edildi
        plot_start = 800
        plot_len = len(self.equity_curve) - plot_start - 1
        plt.figure(figsize=(12, 6))
        plt.plot(self.df.index[plot_start:plot_start+plot_len], self.equity_curve[plot_start:-1], color='#2563eb', linewidth=2)
        plt.title("Strategy Equity Curve", fontsize=16)
        plt.ylabel("Capital ($)")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig("equity_curve.png", dpi=300)
        print("📈 Chart saved as 'equity_curve.png'")

if __name__ == "__main__":
    bot = TradingBot("btc_real_data.csv")
    bot.load_data()
    bot.add_indicators()
    bot.run_backtest()