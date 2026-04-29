import asyncio
import os
import random
import time
import threading
from datetime import datetime, timedelta

import pyquotex.stable_api as _qx_stable
import pyquotex.expiration as _qx_exp
from pyquotex.stable_api import Quotex
from telethon import TelegramClient
from telethon.sessions import StringSession

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

EMAIL       = _env("QUOTEX_EMAIL")
PASSWORD    = _env("QUOTEX_PASSWORD")
API_ID      = int(_env("TELEGRAM_API_ID", default="0"))
API_HASH    = _env("TELEGRAM_API_HASH")
SESSION_STR = _env("TELEGRAM_SESSION")
TG_CHANNEL  = _env("TELEGRAM_CHANNEL")

ASSETS = ["NZDCHF_otc", "USDINR_otc", "USDBDT_otc", "USDARS_otc", "USDPKR_otc"]
BASE_AMOUNT = 1.0

# ── Telethon client (singleton) ──
_tg_client = None

async def get_tg():
    global _tg_client
    if _tg_client is None:
        _tg_client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
        await _tg_client.connect()
    return _tg_client

async def send_telegram(text):
    if not SESSION_STR or not TG_CHANNEL:
        print("TG: لا يوجد session أو channel")
        return
    try:
        tg = await get_tg()
        await tg.send_message(TG_CHANNEL, text)
    except Exception as e:
        print("TG ERROR:", e)

# ── Strategy ──
async def decide_direction(client, asset):
    call_score = 0
    put_score = 0
    try:
        candles = await client.get_candles(asset, int(time.time()), 5, 60)
        last_close = 0
        if candles:
            ups = sum(1 for c in candles if c["close"] > c["open"])
            downs = sum(1 for c in candles if c["close"] < c["open"])
            if ups >= 3: call_score += 3
            if downs >= 3: put_score += 3
            last_close = candles[-1]["close"]

        rsi = await client.calculate_indicator(asset, "RSI", {"period": 14}, history_size=3600, timeframe=60)
        if rsi and "current" in rsi and rsi["current"]:
            rsi_val = float(rsi["current"])
            if rsi_val < 35: call_score += 2
            elif rsi_val > 65: put_score += 2

        ema = await client.calculate_indicator(asset, "EMA", {"period": 20}, history_size=3600, timeframe=60)
        if ema and "current" in ema and ema["current"]:
            ema_val = float(ema["current"])
            if last_close > ema_val: call_score += 2
            elif last_close < ema_val: put_score += 2

        sma = await client.calculate_indicator(asset, "SMA", {"period": 20}, history_size=3600, timeframe=60)
        if sma and "current" in sma and sma["current"]:
            sma_val = float(sma["current"])
            if last_close > sma_val: call_score += 1
            elif last_close < sma_val: put_score += 1

        macd = await client.calculate_indicator(asset, "MACD", {}, history_size=3600, timeframe=60)
        if macd and "macd" in macd and macd["macd"]:
            if macd["macd"][-1] > macd["signal"][-1]: call_score += 2
            else: put_score += 2

        boll = await client.calculate_indicator(asset, "BOLLINGER", {"period": 20, "std": 2}, history_size=3600, timeframe=60)
        if boll and "middle" in boll:
            if last_close < boll["lower"][-1]: call_score += 2
            elif last_close > boll["upper"][-1]: put_score += 2

        stoch = await client.calculate_indicator(asset, "STOCHASTIC", {"k_period": 14, "d_period": 3}, history_size=3600, timeframe=60)
        if stoch and "current" in stoch and stoch["current"]:
            if stoch["current"] < 20: call_score += 1
            elif stoch["current"] > 80: put_score += 1

        adx = await client.calculate_indicator(asset, "ADX", {"period": 14}, history_size=3600, timeframe=60)
        if adx and "adx" in adx and adx["adx"]:
            if adx["adx"][-1] > 25:
                if call_score > put_score: call_score += 1
                elif put_score > call_score: put_score += 1

        ichi = await client.calculate_indicator(asset, "ICHIMOKU", {"tenkan_period": 9, "kijun_period": 26, "senkou_b_period": 52}, history_size=3600, timeframe=60)
        if ichi and "tenkan" in ichi and ichi["tenkan"]:
            if last_close > ichi["tenkan"][-1]: call_score += 1
            elif last_close < ichi["tenkan"][-1]: put_score += 1

        if call_score > put_score: return "call"
        elif put_score > call_score: return "put"
        else: return random.choice(["call", "put"])
    except Exception as e:
        print("DECIDE ERROR:", e)
        return random.choice(["call", "put"])


# ── Bot State ──
class BotState:
    def __init__(self):
        self.running = False
        self.balance = 0
        self.wins = 0
        self.losses = 0
        self.trades = 0
        self.signals = []
        self.status = "متوقف"

    def reset_stats(self):
        self.wins = 0
        self.losses = 0
        self.trades = 0
        self.signals = []
        self.status = "تم إعادة الضبط"

    def to_dict(self):
        return {
            "running": self.running,
            "balance": self.balance,
            "wins": self.wins,
            "losses": self.losses,
            "trades": self.trades,
            "signals": self.signals[-20:],
            "status": self.status,
        }

state = BotState()
_loop = None
_task = None


async def bot_loop():
    global state

    client = Quotex(email=EMAIL, password=PASSWORD, lang="en")
    client.set_account_mode("PRACTICE")

    connected, reason = await client.connect()
    if not connected:
        state.status = f"فشل الاتصال: {reason}"
        state.running = False
        await send_telegram(f"❌ فشل اتصال البوت: {reason}")
        return

    await client.change_account("PRACTICE")
    balance = await client.get_balance()
    state.balance = float(balance)
    state.status = "يعمل الآن"

    first_asset = random.choice(ASSETS)
    first_direction = await decide_direction(client, first_asset)
    await send_telegram(
        f"🚀✨ LATCHI PRO BOT ✨🚀\n"
        f"📊 تحليل أولي: الزوج المختار هو {first_asset.upper()}\n"
        f"✅ الدخول في الدقيقة القادمة على الشمعة الجديدة\n"
        f"{'🔼 CALL' if first_direction == 'call' else '⬇️ PUT'} حسب التحليل\n\n"
        f"💰 الرصيد التجريبي: ${state.balance:.2f}\n"
        f"#LATCHI_PRO #QUOTEX"
    )

    while state.running:
        try:
            asset = random.choice(ASSETS)
            direction = await decide_direction(client, asset)

            now = datetime.now()
            next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
            signal_time = now.strftime("%H:%M")

            direction_text = "CALL 🔼" if direction == "call" else "PUT ⬇️"

            await send_telegram(
                f"📊 صفقة جديدة LATCHI DZ VIP 🌟:\n\n"
                f"{asset.upper()} | M1 | {next_minute.strftime('%H:%M')} | {direction_text}\n\n"
                f"#QUOTEX"
            )

            wait = (next_minute - datetime.now()).total_seconds() - 2
            if wait > 0:
                await asyncio.sleep(wait)
            if not state.running:
                break

            success, order_info = await client.buy(BASE_AMOUNT, asset, direction, 60)

            signal = {
                "asset": asset.upper(),
                "direction": direction,
                "time": signal_time,
                "result": "pending",
                "profit": 0,
            }
            state.signals.insert(0, signal)
            state.trades += 1

            if not success or not isinstance(order_info, dict) or "id" not in order_info:
                signal["result"] = "fail"
                await send_telegram(f"⚠️ فشل تنفيذ الصفقة على {asset.upper()}")
                await asyncio.sleep(10)
                continue

            await asyncio.sleep(75)

            profit, result_status = await client.check_win(order_info["id"])
            signal["result"] = result_status
            signal["profit"] = round(float(profit), 2) if profit else 0

            new_balance = await client.get_balance()
            state.balance = float(new_balance)

            if result_status == "win":
                state.wins += 1
                await send_telegram(
                    f"🟢 ربح ✅\n"
                    f"🎯 {asset.upper()} | {direction_text}\n"
                    f"💰 الربح: +${signal['profit']}\n"
                    f"💳 الرصيد: ${state.balance:.2f}"
                )
            elif result_status == "loss":
                state.losses += 1
                await send_telegram(
                    f"🔴 خسارة ❌\n"
                    f"🎯 {asset.upper()} | {direction_text}\n"
                    f"💸 الخسارة: -${BASE_AMOUNT}\n"
                    f"💳 الرصيد: ${state.balance:.2f}"
                )

            await asyncio.sleep(5)

        except Exception as e:
            print("BOT ERROR:", e)
            await asyncio.sleep(10)

    state.status = "متوقف"
    await send_telegram("🛑 LATCHI DZ BOT تم الإيقاف")
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
    state.status = "جارٍ الاتصال..."
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
    state.status = "جارٍ الإيقاف..."
    return True
