# 🚀 Multi-Timeframe Breakout Trading Bot

A professional algorithmic trading strategy for crypto futures, built with Python. Focuses on **risk management** and **high-probability setups** using Multi-Timeframe Analysis.

## 📊 Strategy Overview
- **Multi-Timeframe Analysis:** Aligns trends across 1H, 4H, and Daily charts
- **Dynamic Risk Management:** ATR-based Stop Loss & Trailing Stop
- **Smart Filtering:** ADX trend strength + Volume analysis to avoid fake breakouts
- **Backtested:** 3.5 years of real BTC/USDT data (2023-2026)

## 🛠 Tech Stack
- Python 3.10+
- Pandas, NumPy, pandas_ta
- Matplotlib for visualization

## 📈 Backtest Results (BTC/USDT)
| Metric | Value |
|--------|-------|
| Period | 3.2 Years |
| Total Trades | 209 |
| Win Rate | 42.1% |
| Profit Factor | 1.46 |
| CAGR | 7.4% |
| Final Capital | $12,534 |

## 🚀 Usage
```bash
# Install dependencies
pip install pandas pandas_ta matplotlib

# Run backtest
python main.py

# Run live bot (requires .env config)
python live_bot.py
