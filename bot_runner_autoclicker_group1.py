# ==============================================================================
# SHIBA INU AUTO-TAP — نسخه نهایی، توزیع‌شده و ضداسپم با مدیریت فریز و اسپین دو مرحله‌ای
# ==============================================================================
# ربات هدف: @SHIBAInuTapbot
# اتصال از طریق ورکر کلودفلر (Reverse Proxy)
# ==============================================================================

import os
import json
import asyncio
import time
import random
import urllib.parse
import re
import sys
import aiohttp
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestWebViewRequest
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

API_ID = int(os.getenv("TG_API_ID") or 0)
API_HASH = os.getenv("TG_API_HASH", "")
BOT_USERNAME = "SHIBAInuTapbot"

# ==============================================================================
# [GLOBAL TAP LOCK] قفل سراسری برای تضمین تپ زدن تک‌نوبتی و عدم همپوشانی اکانت‌ها
# ==============================================================================
TAP_LOCK = asyncio.Lock()

# ==============================================================================
# [TELEGRAM NOTIFIER] دریافت توکن و چت‌آیدی از متغیرهای محیطی گیت‌هاب سکرت
# ==============================================================================
TELEGRAM_NOTIFIER_BOT_TOKEN = os.getenv("NOTIFIER_BOT_TOKEN1", "").strip()
TELEGRAM_NOTIFIER_CHAT_ID = os.getenv("NOTIFIER_CHAT_ID", "").strip()

async def send_telegram_alert(session, message: str):
    if not TELEGRAM_NOTIFIER_BOT_TOKEN or not TELEGRAM_NOTIFIER_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_NOTIFIER_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_NOTIFIER_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            pass
    except Exception:
        pass

# ==============================================================================
# آدرس‌های سرویس از طریق ورکر کلودفلر
# ==============================================================================
BASE_URL = "https://shibabotrunnerautoclickgroup1.alibotrunner3.workers.dev"

INIT_URL = f"{BASE_URL}/v1/game/init"
TAP_URL = f"{BASE_URL}/v1/game/tap"
STREAK_URL = f"{BASE_URL}/v1/game/streak"
AD_GRANT_URL = f"{BASE_URL}/v1/game/ad/grant"
SPIN_URL = f"{BASE_URL}/v1/game/spin"

TASKS_URL = f"{BASE_URL}/v1/game/tasks"
TASK_START_URL = f"{BASE_URL}/v1/game/task/start"
TASK_SUBMIT_URL = f"{BASE_URL}/v1/game/task/submit"
CONTEST_URL = f"{BASE_URL}/v1/game/contest"

MAX_RUN_SECONDS = (5 * 3600) + (55 * 60)

RAW_ACCOUNTS = os.getenv("ACCOUNTS_JSON")
if RAW_ACCOUNTS:
    try:
        ACCOUNTS = json.loads(RAW_ACCOUNTS)
    except Exception as e:
        print(f"Error parsing ACCOUNTS_JSON: {e}")
        ACCOUNTS = []
elif os.path.exists("accounts.json"):
    try:
        with open("accounts.json", "r", encoding="utf-8") as f:
            ACCOUNTS = json.load(f)
    except Exception as e:
        print(f"Error reading accounts.json: {e}")
        ACCOUNTS = []
else:
    ACCOUNTS = []

def get_account_headers(acc):
    ua = acc.get("user_agent") or "Mozilla/5.0 (Linux; Android 14; SM-S928B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/128.0.6613.88 Mobile Safari/537.36"
    match = re.search(r"Chrome/(\d+)", ua)
    chrome_ver = match.group(1) if match else "128"
    device_id = acc.get("device_id", "")
    
    headers = {
        "User-Agent": ua,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-CH-UA": f'"Chromium";v="{chrome_ver}", "Not;A=Brand";v="24", "Android WebView";v="{chrome_ver}"',
        "Sec-CH-UA-Mobile": "?1",
        "Sec-CH-UA-Platform": '"Android"',
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Origin": "https://t.bleon.net",
        "Referer": "https://t.bleon.net/"
    }

    if device_id:
        headers["X-Device-Id"] = device_id
        headers["Device-Id"] = device_id

    return headers

async def fetch_init_data(session_str):
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    try:
        bot_peer = await client.get_input_entity(BOT_USERNAME)

        # تنظیم پلتفرم روی اندروید برای همخوانی کامل با مشخصات دستگاه و یوزرایجنت
        web_view = await client(RequestWebViewRequest(
            peer=bot_peer,
            bot=bot_peer,
            platform="android",
            from_bot_menu=False,
            url="https://t.bleon.net/"
        ))
        await client.disconnect()

        match = re.search(r"#tgWebAppData=([^&]+)", web_view.url)
        if match:
            return urllib.parse.unquote(match.group(1))

        parsed_url = urllib.parse.urlparse(web_view.url)
        params = urllib.parse.parse_qs(parsed_url.fragment)
        return params.get("tgWebAppData", [""])[0]
    except Exception as e:
        await client.disconnect()
        raise e

async def send_init(session, init_data):
    payload = {
        "bot": BOT_USERNAME,
        "initData": init_data,
        "open": True
    }
    try:
        async with session.post(INIT_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text()
            if resp.status == 200:
                return json.loads(text)
            else:
                print(f"[Init Error] HTTP {resp.status}: {text}")
                return None
    except Exception as e:
        print(f"[Init Network Exception]: {e}")
        return None

async def send_tap(session, init_data, taps, token):
    payload = {
        "bot": BOT_USERNAME,
        "initData": init_data,
        "taps": taps,
        "token": token
    }
    try:
        async with session.post(TAP_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text()
            if resp.status == 200:
                return json.loads(text)
            elif resp.status == 429:
                return {"rate_limited": True}
            elif resp.status == 401:
                return {"unauthorized": True}
            else:
                print(f"[Tap Error] HTTP {resp.status}: {text}")
                return None
    except Exception as e:
        print(f"[Tap Network Exception]: {e}")
        return None

async def claim_streak(session, init_data):
    payload = {
        "bot": BOT_USERNAME,
        "initData": init_data
    }
    try:
        async with session.post(STREAK_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text()
            if resp.status == 200:
                return json.loads(text)
            return None
    except Exception:
        return None

# ==============================================================================
# اسپین دومرحله‌ای: ۱. تایید مجوز تبلیغاتی ۲. چرخش گردونه
# ==============================================================================
async def claim_spin(session, init_data, acc_name=""):
    ad_payload = {
        "bot": BOT_USERNAME,
        "initData": init_data,
        "kind": "spin"
    }
    try:
        async with session.post(AD_GRANT_URL, json=ad_payload, timeout=aiohttp.ClientTimeout(total=15)) as g_resp:
            if g_resp.status != 200:
                return None
            g_data = await g_resp.json()
            if not g_data.get("ok"):
                return None
            grant_id = g_data.get("grantId")
            if not grant_id:
                return None

        # شبیه‌سازی فاصله منطقی پس از تماشای تبلیغ
        await asyncio.sleep(random.uniform(2.5, 4.0))

        spin_payload = {
            "bot": BOT_USERNAME,
            "grant_id": grant_id,
            "initData": init_data
        }
        async with session.post(SPIN_URL, json=spin_payload, timeout=aiohttp.ClientTimeout(total=15)) as s_resp:
            if s_resp.status == 200:
                return await s_resp.json()
            return None
    except Exception as e:
        print(f"[{acc_name}] Spin execution error: {e}")
        return None

# ==============================================================================
# مدیریت خودکار بخش تسک‌ها
# ==============================================================================
async def process_tasks(session, init_data, acc_name, current_balance):
    payload = {
        "bot": BOT_USERNAME,
        "initData": init_data
    }
    try:
        async with session.post(TASKS_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return current_balance
            data = await resp.json()
            if not data.get("ok"):
                return current_balance
            tasks = data.get("tasks", [])
    except Exception as e:
        print(f"[{acc_name}] Error fetching tasks: {e}")
        return current_balance

    for task in tasks:
        now_ms = time.time() * 1000
        task_id = task.get("id")
        title = task.get("title", "Task")
        state = task.get("state")
        claimable_at = task.get("claimableAt")
        reward = task.get("reward", 0)

        # دریافت پاداش تسک‌هایی که تایمر آنها تمام شده یا آماده ثبت هستند
        is_ready = (state == "claimable") or (claimable_at and now_ms >= claimable_at and state != "done")
        if is_ready:
            claim_payload = {
                "bot": BOT_USERNAME,
                "initData": init_data,
                "task_id": task_id
            }
            try:
                async with session.post(TASK_SUBMIT_URL, json=claim_payload, timeout=aiohttp.ClientTimeout(total=15)) as c_resp:
                    if c_resp.status == 200:
                        c_data = await c_resp.json()
                        if c_data.get("ok"):
                            earned = c_data.get("reward", reward)
                            current_balance += earned
                            print(f"[{acc_name}] Task Claimed: '{title}' (+{earned} SHIB) | Balance: {current_balance}")
                            await send_telegram_alert(session, f"🎯 <b>{acc_name}</b>\nTask Claimed: <b>{title}</b> (+{earned} SHIB)\nBalance: {current_balance}")
            except Exception:
                pass
            await asyncio.sleep(random.uniform(1.8, 2.8))

        # استارت تسک‌های جدید
        elif state == "available":
            start_payload = {
                "bot": BOT_USERNAME,
                "initData": init_data,
                "task_id": task_id
            }
            try:
                async with session.post(TASK_START_URL, json=start_payload, timeout=aiohttp.ClientTimeout(total=15)) as s_resp:
                    if s_resp.status == 200:
                        s_data = await s_resp.json()
                        if s_data.get("ok"):
                            duration = task.get("durationSeconds", 0)
                            print(f"[{acc_name}] Task Started: '{title}' (Timer: {duration}s)")
            except Exception:
                pass
            await asyncio.sleep(random.uniform(1.8, 2.8))

    return current_balance

# ==============================================================================
# دریافت آمار رتبه و امتیاز
# ==============================================================================
async def fetch_contest_stats(session, init_data, acc_name=""):
    payload = {
        "bot": BOT_USERNAME,
        "initData": init_data
    }
    for attempt in range(3):
        try:
            async with session.post(CONTEST_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    contests = data.get("contests", [])
                    for item in contests:
                        if item.get("metric") == "engagement":
                            you_data = item.get("you")
                            if you_data and isinstance(you_data, dict):
                                rank = you_data.get("rank")
                                earnings = you_data.get("value")
                                if rank is not None and earnings is not None:
                                    return rank, earnings

                            for entry in item.get("entries", []):
                                if entry.get("you") is True:
                                    return entry.get("rank", "-"), entry.get("value", "-")

                            return "Unranked", 0

                elif resp.status == 401:
                    break
        except Exception:
            pass
        await asyncio.sleep(1.5)

    return "N/A", "N/A"

# ==============================================================================
# ورکر هر اکانت
# ==============================================================================
async def shiba_worker(acc, initial_offset):
    acc_name = acc.get("name", "Account")
    acc_headers = get_account_headers(acc)

    try:
        if initial_offset > 0:
            print(f"[{acc_name}] Dedicated slot offset: waiting {int(initial_offset)}s...")
            await asyncio.sleep(initial_offset)

        proxy_url = os.getenv("LOCAL_PROXY")
        connector = aiohttp.TCPConnector(ssl=False) if proxy_url else None

        async with aiohttp.ClientSession(headers=acc_headers, connector=connector) as session:
            while True:
                try:
                    print(f"[{acc_name}] Fetching fresh initData...")
                    init_data = await fetch_init_data(acc["session"])
                    if not init_data:
                        await asyncio.sleep(20)
                        continue

                    init_res = await send_init(session, init_data)
                    if not init_res or not init_res.get("ok"):
                        await asyncio.sleep(15)
                        continue

                    player = init_res.get("player") or {}
                    energy = player.get("energy", 0)
                    balance = player.get("balance", 0)
                    current_token = init_res.get("tapToken", "")
                    
                    last_streak = player.get("lastStreakClaim", 0)
                    last_spin = player.get("lastSpin", 0)

                    print(f"[{acc_name}] Turn Active | Balance: {balance} | Energy: {energy}/1000")

                    while True:
                        now_ms = time.time() * 1000

                        # ۱. بررسی استریک روزانه (۲۴ ساعت)
                        if now_ms - last_streak >= 86400000:
                            streak_res = await claim_streak(session, init_data)
                            if streak_res and streak_res.get("ok"):
                                r_reward = streak_res.get("reward", 0)
                                balance = streak_res.get("player", {}).get("balance", balance + r_reward)
                                last_streak = streak_res.get("player", {}).get("lastStreakClaim", now_ms)
                                print(f"[{acc_name}] Daily Streak Claimed! (+{r_reward} SHIB)")
                                await send_telegram_alert(session, f"🎁 <b>{acc_name}</b>\nDaily Streak Claimed! (+{r_reward} SHIB)\nBalance: {balance}")
                            await asyncio.sleep(1.5)

                        # ۲. بررسی اسپین دو مرحله‌ای (۸ ساعت)
                        if now_ms - last_spin >= 28800000:
                            spin_res = await claim_spin(session, init_data, acc_name=acc_name)
                            if spin_res and spin_res.get("ok"):
                                s_reward = spin_res.get("reward", 0)
                                balance = spin_res.get("player", {}).get("balance", balance + s_reward)
                                last_spin = spin_res.get("player", {}).get("lastSpin", now_ms)
                                print(f"[{acc_name}] Lucky Spin Won! (+{s_reward} SHIB) | Balance: {balance}")
                                await send_telegram_alert(session, f"🎡 <b>{acc_name}</b>\nLucky Spin Won! (+{s_reward} SHIB)\nBalance: {balance}")
                            await asyncio.sleep(1.5)

                        # ۳. پردازش اولیه تسک‌ها قبل از شروع تپ
                        balance = await process_tasks(session, init_data, acc_name, balance)

                        # اطمینان از شارژ بودن مخزن تا حداقل ۹۸۰ انرژی قبل از نوبت‌گیری
                        if energy < 980:
                            wait_fill = (1000 - energy) + random.uniform(2.0, 8.0)
                            print(f"[{acc_name}] Energy is {energy}/1000. Waiting {int(wait_fill)}s to reach >= 980...")
                            await asyncio.sleep(wait_fill)
                            energy = 1000

                        stop_threshold = random.randint(0, 10)
                        tap_start_time = time.time()
                        stuck_counter = 0
                        stop_reason = "normal"

                        # ======================================================
                        # فاز انحصاری تپ با TAP_LOCK
                        # ======================================================
                        async with TAP_LOCK:
                            print(f"[{acc_name}] Acquired TAP_LOCK. Tapping down to <= {stop_threshold} energy...")
                            
                            # گارد زمانی ۱۷۵ ثانیه‌ای مناسب برای تخلیه کامل مخزن با بسته‌های کوچک
                            while energy > stop_threshold and (time.time() - tap_start_time < 175.0):
                                max_taps_possible = max(1, energy // 5)
                                taps_to_send = min(random.randint(10, 15), max_taps_possible)

                                res = await send_tap(session, init_data, taps=taps_to_send, token=current_token)
                                
                                if res and res.get("ok") and "player" in res:
                                    # بررسی سقف درآمد روزانه (محدودیت gained: 0)
                                    if res.get("gained") == 0:
                                        print(f"[{acc_name}] Daily cap reached (gained: 0). Account is frozen.")
                                        stop_reason = "capped"
                                        break

                                    current_token = res.get("tapToken", current_token)
                                    new_player = res.get("player")
                                    new_energy = new_player.get("energy")
                                    new_balance = new_player.get("balance")

                                    # تشخیص فریز سرور یا عدم تغییر بالانس و انرژی
                                    if new_balance == balance and new_energy >= energy:
                                        stuck_counter += 1
                                        if stuck_counter >= 3:
                                            print(f"[{acc_name}] Server frozen/rejecting taps. Aborting turn...")
                                            stop_reason = "frozen"
                                            break
                                    else:
                                        stuck_counter = 0

                                    energy = new_energy
                                    balance = new_balance
                                    print(f"[{acc_name}] +{taps_to_send} Taps | Energy: {energy} | Balance: {balance}")

                                    # توقف در صورت اتمام توان اجرای یک تپ کامل (کمتر از ۵ واحد)
                                    if energy < 5:
                                        stop_reason = "normal"
                                        break
                                    
                                elif res and res.get("rate_limited"):
                                    print(f"[{acc_name}] 429 Throttled by server.")
                                    stop_reason = "throttled"
                                    break
                                    
                                elif res and res.get("unauthorized"):
                                    print(f"[{acc_name}] 401 Unauthorized detected.")
                                    stop_reason = "401"
                                    break
                                    
                                else:
                                    print(f"[{acc_name}] Invalid response received.")
                                    stop_reason = "error"
                                    break

                                await asyncio.sleep(random.uniform(6.5, 8.5))

                        # در صورت بروز خطای اعتبار سنجی، حلقه را برای لاگین دوباره بشکن
                        if stop_reason in ["401", "error"]:
                            break

                        # بررسی مجدد تسک‌ها پس از پایان تپ زدن
                        balance = await process_tasks(session, init_data, acc_name, balance)

                        # ======================================================
                        # محاسبه دقیق زمان خواب بر اساس دلیل توقف (رفع باگ اسپم)
                        # ======================================================
                        if stop_reason in ["capped", "frozen"]:
                            # اکانت محدود شده است؛ خواب کامل یک چرخه بدون توجه به پر بودن انرژی مخزن
                            sleep_time = random.uniform(980.0, 1020.0)
                            status_note = "🧊 Account Capped/Frozen. Long sleep engaged."
                        elif stop_reason == "throttled":
                            # خطای ریت‌لیمیت سرور؛ خواب موقت برای رفع محدودیت
                            sleep_time = random.uniform(90.0, 130.0)
                            status_note = "⚠️ 429 Throttled. Short pause to cool down."
                        else:
                            # تخلیه نرمال مخزن؛ محاسبه خواب متناسب با نیاز شارژ تا سقف ۱۰۰۰
                            energy_needed = max(0, 1000 - energy)
                            sleep_time = energy_needed + random.uniform(3.0, 10.0)
                            status_note = "✅ Normal cycle completed."

                        print(f"[{acc_name}] {status_note} Sleeping for {int(sleep_time)}s...")

                        # دریافت رتبه و آمار لیدربرد
                        rank, earnings = await fetch_contest_stats(session, init_data, acc_name=acc_name)
                        if earnings == "N/A" and "tapsTotal" in player:
                            earnings = player.get("tapsTotal", "N/A")

                        earnings_str = f"{earnings:,}" if isinstance(earnings, int) else str(earnings)
                        balance_str = f"{balance:,}" if isinstance(balance, int) else str(balance)
                        rank_str = f"#{rank}" if rank not in ["N/A", "Unranked"] else str(rank)
                        sleep_minutes = max(1, int(round(sleep_time / 60)))

                        notify_msg = (
                            f"💤 <b>{acc_name}</b> Finished Tapping\n"
                            f"💰 Balance: <b>{balance_str}</b>\n"
                            f"💎 Earnings: <b>{earnings_str}</b>\n"
                            f"🏆 Rank: <b>{rank_str}</b>\n"
                            f"🔋 Energy: {energy}/1000\n"
                            f"⏳ Sleeping for: <b>{sleep_minutes} minutes</b>\n"
                            f"<i>Status: {stop_reason.upper()}</i>\n"
                            f"✅ Safe to open on mobile now!"
                        )
                        await send_telegram_alert(session, notify_msg)

                        # رفتن به خواب محاسبه‌شده
                        await asyncio.sleep(sleep_time)

                        # بیدار شدن و همگام‌سازی توکن با ۱ پینگ
                        wake_res = await send_tap(session, init_data, taps=1, token=current_token)
                        if wake_res and wake_res.get("ok") and "player" in wake_res:
                            current_token = wake_res.get("tapToken", current_token)
                            p_data = wake_res.get("player")
                            energy = p_data.get("energy", 1000)
                            balance = p_data.get("balance", balance)
                            last_streak = p_data.get("lastStreakClaim", last_streak)
                            last_spin = p_data.get("lastSpin", last_spin)
                            print(f"[{acc_name}] Woke up! Energy: {energy}/1000")
                        else:
                            print(f"[{acc_name}] Token expired while sleeping. Refreshing session...")
                            break

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"[{acc_name}] Error: {e}. Retrying in 15s...")
                    await asyncio.sleep(15)

    except asyncio.CancelledError:
        pass

# ==============================================================================
# تابع اصلی مدیریت تسک‌های نوبتی
# ==============================================================================
async def main():
    if not ACCOUNTS:
        print("No accounts found in ACCOUNTS_JSON or accounts.json.")
        return

    start_time = time.time()
    num_accounts = len(ACCOUNTS)
    print("==================================================")
    print(f">>> SHIBA Inu Auto-Tap Started ({num_accounts} Accounts)")
    print(">>> Fixed Frozen Logic | Two-Stage Spin | Dynamic Sleep")
    print(f">>> Scheduled Auto-Stop: 5 Hours and 55 Minutes")
    print("==================================================")

    # تقسیم زمان پر شدن مخزن (۱۰۰۰ ثانیه) بر تعداد اکانت‌ها برای جلوگیری از تداخل
    slot_interval = 1000.0 / max(1, num_accounts)
    
    tasks = []
    for i, acc in enumerate(ACCOUNTS):
        offset = (i * slot_interval) + random.uniform(2.0, 6.0) if i > 0 else 0.0
        tasks.append(asyncio.create_task(shiba_worker(acc, initial_offset=offset)))

    try:
        while time.time() - start_time < MAX_RUN_SECONDS:
            await asyncio.sleep(1)

        print("\n[SYSTEM] Run duration limit reached (5h 55m). Exiting cleanly...")
    except asyncio.CancelledError:
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOPPED] Execution stopped cleanly by user.")
        sys.exit(0)
