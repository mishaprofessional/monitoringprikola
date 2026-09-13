import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape

try:
    from zoneinfo import ZoneInfo
    MSK = ZoneInfo("Europe/Moscow")
except Exception:
    MSK = timezone(timedelta(hours=3))

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

API_URL = "https://n-api.arizona-rp.com/api/map"   # новый адрес API Arizona
SERVER_IDS = list(range(1, 34))                     # сервера 1..33
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

EXPIRE_HOURS = 2        # через сколько часов дом "слетит"
ROUND_UP_HOUR = False   # True - округлять слет вверх до часа (как в образце)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://arizona-rp.com/",
    "Origin": "https://arizona-rp.com",
}


def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def tg_send(text):
    payload = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_houses(sid):
    """Скачивает дома сервера sid. Возвращает список или None при ошибке."""
    try:
        data = http_get_json(f"{API_URL}/{sid}")
    except urllib.error.HTTPError as e:
        print(f"server {sid}: HTTP {e.code}")
        return None
    except Exception as e:
        print(f"server {sid}: error {e}")
        return None

    houses = data.get("houses") if isinstance(data, dict) else None
    if isinstance(houses, dict):
        # внутри списки: hasOwner / noOwner и т.п. - собираем все
        items = [h for lst in houses.values() if isinstance(lst, list) for h in lst if isinstance(h, dict)]
    elif isinstance(houses, list):
        items = [h for h in houses if isinstance(h, dict)]
    else:
        items = []
    return items


def is_free(h):
    """Зелёный дом = нет владельца."""
    if "isOwned" in h:
        return not bool(h["isOwned"])
    return h.get("owner") in (None, "", "нет", "None")


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def notify(sid, new_houses, now):
    deadline = now + timedelta(hours=EXPIRE_HOURS)
    if ROUND_UP_HOUR:
        deadline = (deadline + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    header = f"🏛 Найдено имущество: {len(new_houses)}"
    server_line = f"🖥 Сервер: [{sid}]"
    times = (f"⚪ Найдено: {now.strftime('%d.%m %H:%M')}\n"
             f"⌛ Слет: {deadline.strftime('%d.%m %H:%M')}")
    block_lines = [f"🏠 ДОМА ({len(new_houses)})"]
    for h in new_houses:
        line = f"#{h.get('id')}"
        title = (h.get("name") or "").strip()
        if title:
            line += f" - {title}"
        block_lines.append(line)
    text = (f"{header}\n\n{server_line}\n\n{times}\n\n"
            f"<pre>{escape(chr(10).join(block_lines))}</pre>")
    try:
        tg_send(text)
    except Exception as e:
        print("Ошибка отправки в Telegram:", e)


def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Не заданы BOT_TOKEN / CHAT_ID в Secrets")
        sys.exit(1)

    state = load_state()
    ok = 0

    for sid in SERVER_IDS:
        houses = None
        for _ in range(3):
            houses = fetch_houses(sid)
            if houses is not None:
                break
            time.sleep(2)
        if houses is None:
            continue
        ok += 1

        free = [h for h in houses if is_free(h)]
        free_ids = sorted(h["id"] for h in free)
        free_map = {h["id"]: h for h in free}

        prev = state.get(str(sid))
        if not prev or not prev.get("init"):
            state[str(sid)] = {"init": True, "free": free_ids}
            print(f"server {sid}: базовый снимок, свободных {len(free_ids)}")
            continue

        new_ids = [i for i in free_ids if i not in set(prev.get("free", []))]
        if new_ids:
            print(f"server {sid}: новые свободные {new_ids}")
            notify(sid, [free_map[i] for i in new_ids], datetime.now(MSK))
            time.sleep(1)

        state[str(sid)] = {"init": True, "free": free_ids}

    save_state(state)
    print(f"Готово. Серверов отвечают: {ok}/{len(SERVER_IDS)}")


if __name__ == "__main__":
    main()
