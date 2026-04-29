import asyncio
import os
import random
import time
import threading
import requests
from datetime import datetime, timedelta

import pyquotex.stable_api as _qx_stable
import pyquotex.expiration as _qx_exp
from pyquotex.stable_api import Quotex

# ── إصلاح bug pyquotex ──
async def _patched_get_server_time(self):
    if self.api is None:
        return int(time.time())
    user_settings = await self.get_profile()
    offset_zone = 0
    if user_settings is not None and getattr(user_settings, "offset", None) is not None:
        offset_zone = user_settings.offset
    self.api.timesync.server_timestamp = _qx_exp.get_server_timer(offset_zone)
    return self.api.timesync.server_timestamp

_qx_stable.Quotex.get_server_time = _patched_get_server_time

def _env(*names, default=""):
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return default

EMAIL      = _env("QUOTEX_EMAIL")
COOKIES    = _env("QUOTEX_COOKIES")
TOKEN      = _env("QUOTEX_TOKEN")
USER_AGENT = _env("QUOTEX_USER_AGENT")
TG_TOKEN   = _env("TELEGRAM_BOT_TOKEN")
TG_CHANNEL = _env("TELEGRAM_CHANNEL")

ASSETS      = ["NZDCHF_otc", "USDINR_otc", "USDBDT_otc", "USDARS_otc", "USDPKR_otc"]
BASE_AMOUNT = 1.0

def send_telegram(text):
    if not TG_TOKEN or not TG_CHANNEL:
        print("TG WARNING: TOKEN or CHANNEL not set")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHANNEL, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        print("TG STATUS:", r.status_code, r.text[:200])
    except Exception as e:
        print("TG ERROR:", e)

class BotState:
    def __init__(self):
        self.running = False
        self.balance = 0
        self.wins    = 0
        self.losses  = 0
        self.trades  = 0
        self.signals = []
        self.status  = "متوقف"

    def reset_stats(self):
        self.wins    = 0
        self.losses  = 0
        self.trades  = 0
        self.signals = []
        self.status  = "تم إعادة الضبط"

    def to_dict(self):
        return {
            "running": self.running,
            "balance": self.balance,
            "wins":    self.wins,
            "losses":  self.losses,
            "trades":  self.trades,
            "signals": self.signals[-20:],
            "status":  self.status,
        }

state = BotState()
_loop = None
_task = None

def _load_session(client):
    """تحميل الـ cookies والـ token مباشرة بدون تسجيل دخول"""
    try:
        session_dir = os.path.join(os.path.expanduser("~"), ".pyquotex")
        os.makedirs(session_dir, exist_ok=True)
        session_file = os.path.join(session_dir, f"{EMAIL}.json")
        
        import json
        session_data = {
            EMAIL: {
                "cookies": COOKIES,
                "token": TOKEN,
                "user_agent": USER_AGENT
            }
        }
        with open(session_file, "w") as f:
            json.dump(session_data, f)
        print("✅ Session file loaded successfully")
        return True
    except Exception as e:
        print("SESSION ERROR:", e)
        return False

async def decide_direction(client, asset):
    try:
        call_score = 0
        put_score  = 0
        last_close = 0

        candles = await client.get_candles(asset, int(time.time()), 5, 60)
        if candles:
            ups   = sum(1 for c in candles if c["close"] > c["open"])
            downs = sum(1 for c in candles if c["close"] < c["open"])
            if ups >= 3:   call_score += 3
            if downs >= 3: put_score  += 3
            last_close = candles[-1]["close"]

        rsi = await client.calculate_indicator(
            asset, "RSI", {"period": 14}, history_size=3600, timeframe=60
        )
        if rsi and "current" in rsi and rsi["current"]:
            rsi_val = float(rsi["current"])
            if rsi_val < 35:   call_score += 2
            elif rsi_val > 65: put_score  += 2

        ema = await client.calculate_indicator(
            asset, "EMA", {"period": 20}, history_size=3600, timeframe=60
        )
        if ema and "current" in ema and ema["current"]:
            ema_val = float(ema["current"])
            if last_close > ema_val:   call_score += 2
            elif last_close < ema_val: put_score  += 2

        if call_score > put_score:   return "call"
        elif put_score > call_score: return "put"
        else: return random.choice(["call", "put"])
    except Exception:
        return random.choice(["call", "put"])

async def bot_loop():
    global state

    send_telegram(
        "⏳ <b>LATCHI DZ BOT</b>\n"
        "🔄 جارٍ الاتصال بمنصة Quotex...\n"
        "يرجى الانتظار..."
    )

    client = Quotex(email=EMAIL, password="", lang="en")
    client.set_account_mode("PRACTICE")

    _load_session(client)

    connected, reason = await client.connect()
    if not connected:
        state.status = f"فشل الاتصال: {reason}"
        state.running = False
        send_telegram(
            f"❌ <b>فشل الاتصال بمنصة Quotex</b>\n"
            f"السبب: {reason}\n"
            f"يرجى تجديد الـ cookies"
        )
        return

    await client.change_account("PRACTICE")
    balance = await client.get_balance()
    state.balance = float(balance)
    state.status  = "يعمل الآن"

    send_telegram(
        f"✅ <b>تم الاتصال بمنصة Quotex بنجاح!</b>\n\n"
        f"🚀 <b>LATCHI DZ BOT</b> بدأ التشغيل\n"
        f"💰 الرصيد التجريبي: <b>${state.balance:.2f}</b>\n"
        f"📊 الوضع: تجريبي (PRACTICE)\n\n"
        f"📡 سيبدأ إرسال الإشارات الآن..."
    )

    while state.running:
        try:
            asset     = random.choice(ASSETS)
            direction = await decide_direction(client, asset)
            now         = datetime.now()
            signal_time = now.strftime("%H:%M")

            next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
            wait = (next_minute - datetime.now()).total_seconds() - 2
            if wait > 0:
                await asyncio.sleep(wait)
            if not state.running:
                break

            direction_text = "CALL 🔼" if direction == "call" else "PUT 🔽"
            send_telegram(
                f"📊 <b>إشارة جديدة — LATCHI DZ VIP</b>\n\n"
                f"🎯 الأصل: <b>{asset.upper()}</b>\n"
                f"📈 الاتجاه: <b>{direction_text}</b>\n"
                f"⏱ التوقيت: <b>M1</b> | {next_minute.strftime('%H:%M')}\n"
                f"💵 المبلغ: <b>${BASE_AMOUNT}</b>\n\n"
                f"#QUOTEX #LATCHIDZ"
            )

            success, order_info = await client.buy(BASE_AMOUNT, asset, direction, 60)

            signal = {
                "asset":     asset.upper(),
                "direction": direction,
                "time":      signal_time,
                "result":    "pending",
                "profit":    0,
            }
            state.signals.insert(0, signal)
            state.trades += 1

            if not success or not isinstance(order_info, dict) or "id" not in order_info:
                signal["result"] = "fail"
                send_telegram(f"⚠️ فشل تنفيذ الصفقة على {asset.upper()}")
                await asyncio.sleep(10)
                continue

            await asyncio.sleep(75)

            profit, result_status = await client.check_win(order_info["id"])
            signal["result"] = result_status
            signal["profit"] = round(float(profit), 2) if profit else 0

            new_balance    = await client.get_balance()
            state.balance  = float(new_balance)

            if result_status == "win":
                state.wins += 1
                send_telegram(
                    f"✅ <b>ربح!</b>\n"
                    f"🎯 {asset.upper()} | {direction_text}\n"
                    f"💰 الربح: <b>+${signal['profit']}</b>\n"
                    f"💳 الرصيد: <b>${state.balance:.2f}</b>"
                )
            elif result_status == "loss":
                state.losses += 1
                send_telegram(
                    f"❌ <b>خسارة</b>\n"
                    f"🎯 {asset.upper()} | {direction_text}\n"
                    f"💸 الخسارة: <b>-${BASE_AMOUNT}</b>\n"
                    f"💳 الرصيد: <b>${state.balance:.2f}</b>"
                )

            await asyncio.sleep(5)

        except Exception as e:
            print("BOT ERROR:", e)
            await asyncio.sleep(10)

    state.status = "متوقف"
    send_telegram("🛑 <b>LATCHI DZ BOT</b> تم الإيقاف")
    try:
        await client.close()
    except Exception:
        pass

def _run_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def start_bot():
    global _loop, _task, state
    if state.running:
        return False
    state.running = True
    state.status  = "جارٍ الاتصال..."
    if _loop is None or not _loop.is_running():
        _loop = asyncio.new_event_loop()
        t = threading.Thread(target=_run_loop, args=(_loop,), daemon=True)
        t.start()
    _task = asyncio.run_coroutine_threadsafe(bot_loop(), _loop)
    return True

def stop_bot():
    global state
    if not state.running:
        return False
    state.running = False
    state.status  = "جارٍ الإيقاف..."
    send_telegram("🛑 <b>LATCHI DZ BOT</b> تم الإيقاف")
    return True
