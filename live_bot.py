import requests
import time
import pandas as pd
import numpy as np
import hmac
import hashlib
import logging
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

# ================= CONFIG =================
API_KEY = os.getenv("BINGX_API_KEY", "")
API_SECRET = os.getenv("BINGX_API_SECRET", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_URL = "https://open-api.bingx.com"
SYMBOL = os.getenv("SYMBOL", "BTC-USDT")
ACCOUNT_BALANCE = float(os.getenv("ACCOUNT_BALANCE", 100))

# 🎯 OPTİMİZE PARAMETRELER (Backtest'ten aynı)
EMA_PERIOD = 50
MTF_MIN_ALIGN = 3
BUFFER_PCT = 0.015
SL_ATR = 3.5
TRAIL_ATR = 2.0
BE_ATR = 2.0
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", 0.02))
MIN_VOLUME_FILTER = 1.2

# LOGGING
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s',
                    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()])

# ================= TELEGRAM =================
def send_msg(msg):
    if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        logging.warning("Telegram credentials missing")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        logging.error(f"Telegram error: {e}")

# ================= BINGX API =================
def _sign(params, secret):
    params["timestamp"] = int(time.time() * 1000)
    query = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    sig = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    return sig

def _request(method, path, params=None):
    url = f"{BASE_URL}{path}"
    headers = {"X-BX-APIKEY": API_KEY, "Content-Type": "application/x-www-form-urlencoded"}
    
    for attempt in range(3):
        try:
            if params:
                params["timestamp"] = int(time.time() * 1000)
                params["signature"] = _sign(params.copy(), API_SECRET)
            
            if method == "GET":
                r = requests.get(url, params=params, headers=headers, timeout=10)
            else:
                r = requests.post(url, data=params, headers=headers, timeout=10)
            
            r.raise_for_status()
            res = r.json()
            if res.get("code") not in [0, "0", None]:
                logging.warning(f"API Warning: {res.get('msg')}")
            return res
        except Exception as e:
            logging.error(f"API Error (attempt {attempt+1}): {e}")
            time.sleep(2)
    raise RuntimeError("API request failed")

def get_klines(symbol, interval, limit=200):
    r = _request("GET", "/openApi/swap/v3/quote/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if "data" not in r: return None
    df = pd.DataFrame(r["data"], columns=["time","open","high","low","close","volume"])
    df = df.astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df.set_index("time", inplace=True)
    return df

def place_order(symbol, side, qty):
    params = {"symbol": symbol, "side": side, "type": "MARKET", "quantity": f"{qty:.4f}"}
    r = _request("POST", "/openApi/swap/v2/trade/order", params)
    logging.info(f"Order placed: {r}")
    return r

def close_position(symbol, side, qty):
    params = {"symbol": symbol, "side": side, "type": "MARKET", "quantity": f"{qty:.4f}"}
    r = _request("POST", "/openApi/swap/v2/trade/order", params)
    logging.info(f"Position closed: {r}")
    return r

# ================= ANALYSIS ENGINE =================
def analyze():
    df_1h = get_klines(SYMBOL, "1h", 300)
    if df_1h is None or len(df_1h) < 100: return None
    
    # İndikatörler
    df_1h["e1"] = df_1h["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
    df_1h["e4"] = df_1h["close"].resample("4h").last().ewm(span=EMA_PERIOD, adjust=False).mean().reindex(df_1h.index).ffill()
    df_1h["eD"] = df_1h["close"].resample("1D").last().ewm(span=EMA_PERIOD, adjust=False).mean().reindex(df_1h.index).ffill()
    
    df_1h["pH"] = df_1h["high"].resample("1D").max().shift(1).reindex(df_1h.index).ffill()
    df_1h["pL"] = df_1h["low"].resample("1D").min().shift(1).reindex(df_1h.index).ffill()
    
    prev_c = df_1h["close"].shift(1)
    tr = pd.concat([df_1h["high"]-df_1h["low"], (df_1h["high"]-prev_c).abs(), (df_1h["low"]-prev_c).abs()], axis=1).max(axis=1)
    df_1h["atr"] = tr.rolling(14).mean()
    df_1h["vol_ma"] = df_1h["volume"].rolling(20).mean()
    
    r = df_1h.iloc[-1]
    
    # Hacim filtresi
    if r["volume"] < r["vol_ma"] * MIN_VOLUME_FILTER:
        return None
    
    # MTF Skor
    up = int(r["close"] > r["e1"]) + int(r["close"] > r["e4"]) + int(r["close"] > r["eD"])
    dn = int(r["close"] < r["e1"]) + int(r["close"] < r["e4"]) + int(r["close"] < r["eD"])
    
    # Kırılım + Buffer
    bh = r["close"] > (r["pH"] * (1 + BUFFER_PCT))
    bl = r["close"] < (r["pL"] * (1 - BUFFER_PCT))
    
    if bh and up >= MTF_MIN_ALIGN:
        return {"signal": "LONG", "entry": r["close"], "atr": r["atr"], "up": up, "dn": dn}
    elif bl and dn >= MTF_MIN_ALIGN:
        return {"signal": "SHORT", "entry": r["close"], "atr": r["atr"], "up": up, "dn": dn}
    return None

# ================= MAIN LOOP =================
active_pos = None
last_signal_time = 0
COOLDOWN = 3600  # 1 saatte max 1 sinyal

while True:
    try:
        logging.info("Checking signals...")
        
        if not active_pos and (time.time() - last_signal_time) > COOLDOWN:
            sig = analyze()
            if sig:
                sl = sig["entry"] - SL_ATR * sig["atr"] if sig["signal"] == "LONG" else sig["entry"] + SL_ATR * sig["atr"]
                risk_amt = ACCOUNT_BALANCE * RISK_PER_TRADE
                qty = risk_amt / abs(sig["entry"] - sl)
                
                side = "BUY" if sig["signal"] == "LONG" else "SELL"
                place_order(SYMBOL, side, qty)
                
                active_pos = {
                    "side": sig["signal"],
                    "entry": sig["entry"],
                    "sl": sl,
                    "qty": qty,
                    "atr": sig["atr"],
                    "opened_at": time.time()
                }
                
                msg = f"🚀 *{sig['signal']} SIGNAL*\n💰 Entry: `{sig['entry']:.2f}`\n🛑 SL: `{sl:.2f}`\n📊 Qty: `{qty:.4f}`\n⏰ {datetime.now().strftime('%H:%M')}"
                send_msg(msg)
                logging.info(f"Position opened: {active_pos}")
                last_signal_time = time.time()
                
        elif active_pos:
            # Trailing Stop + BE Management
            df = get_klines(SYMBOL, "1h", 50)
            if df is not None:
                curr = df.iloc[-1]["close"]
                atr = active_pos["atr"]
                
                if active_pos["side"] == "LONG":
                    if curr >= active_pos["entry"] + BE_ATR * atr:
                        active_pos["sl"] = max(active_pos["sl"], active_pos["entry"])
                    trail = curr - TRAIL_ATR * atr
                    if trail > active_pos["sl"]:
                        active_pos["sl"] = trail
                    if curr <= active_pos["sl"]:
                        close_side = "SELL"
                        close_position(SYMBOL, close_side, active_pos["qty"])
                        pnl = (active_pos["sl"] - active_pos["entry"]) * active_pos["qty"]
                        send_msg(f"🔴 *LONG CLOSED*\n💵 PnL: `{pnl:.2f}`")
                        logging.info(f"Long closed, PnL: {pnl}")
                        active_pos = None
                else:
                    if curr <= active_pos["entry"] - BE_ATR * atr:
                        active_pos["sl"] = min(active_pos["sl"], active_pos["entry"])
                    trail = curr + TRAIL_ATR * atr
                    if trail < active_pos["sl"]:
                        active_pos["sl"] = trail
                    if curr >= active_pos["sl"]:
                        close_side = "BUY"
                        close_position(SYMBOL, close_side, active_pos["qty"])
                        pnl = (active_pos["entry"] - active_pos["sl"]) * active_pos["qty"]
                        send_msg(f"🟢 *SHORT CLOSED*\n💵 PnL: `{pnl:.2f}`")
                        logging.info(f"Short closed, PnL: {pnl}")
                        active_pos = None
                        
        time.sleep(300)  # 5 dakikada bir kontrol
        
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
        break
    except Exception as e:
        logging.error(f"Critical error: {e}")
        time.sleep(60)