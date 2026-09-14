import json
import os
import sys
import time
import urllib.error
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

API_URL = "https://n-api.arizona-rp.com/api/map"
SERVERS_URL = "https://n-api.arizona-rp.com/api/servers/arizona"
SERVER_IDS = list(range(1, 34))
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

EXPIRE_HOURS = 2        # слет = находка + N часов
ROUND_UP_HOUR = True    # округлять слет вверх до часа (как в образце)
HOUSE_ID_SHIFT = -1     # номера домов на карте сдвинуты относительно id API
MAX_LIST_IN_MSG = 60    # максимум домов в одной карточке
ANOMALY_LIMIT = 200     # больше сразу = подозрение на глюк API, молча переснять
FREE_KEYS = ("noOwner", "onMarketplace")   # списки свободных домов в ответе API

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://arizona-rp.com/",
    "Origin": "https://arizona-rp.com",
}

SERVER_NAMES = {}


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


def load_server_names():
    global SERVER_NAMES
    try:
        data = http_get_json(SERVERS_URL)
        items = data if isinstance(data, list) else data.get("servers", data.get("items", []))
        for it in items:
            if not isinstance(it, dict):
                continue
            sid = it.get("serverId") or it.get("id")
            name = (it.get("name") or it.get("fullName") or "").strip()
            if sid is not None and name:
                SERVER_NAMES[int(sid)] = name
    except Exception as e:
        print("Список серверов не получен:", e)


def fetch_server_data(sid):
    """Возвращает {"free": [записи свободных домов], "occupied": N} или None."""
    try:
        data = http_get_json(f"{API_URL}/{sid}")
    except urllib.error.HTTPError as e:
        print(f"server {sid}: HTTP {e.code}")
        return None
    except Exception as e:
        print(f"server {sid}: error {e}")
        return None

    houses = data.get("houses") if isinstance(data, dict) else None
    if not isinstance(houses, dict):
        return {"free": [], "occupied": 0}

    free = []
    for key in FREE_KEYS:
        lst = houses.get(key)
        if isinstance(lst, list):
            free.extend(h for h in lst if isinstance(h, dict))
    lst = houses.get("hasOwner")
    if isinstance(lst, list):
        free.extend(h for h in lst if isinstance(h, dict) and not (h.get("owner") or "").strip())
        occupied = len(lst)
    else:
        occupied = 0
    return {"free": free, "occupied": occupied}


def expire_time(now):
    d = now + timedelta(hours=EXPIRE_HOURS)
    if ROUND_UP_HOUR:
        d = d.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return d


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def display_id(h):
    return h.get("id", 0) + HOUSE_ID_SHIFT


def notify(sid, new_houses, now):
    deadline = expire_time(now)
    name = SERVER_NAMES.get(sid, "")
    total = len(new_houses)
    shown = new_houses[:MAX_LIST_IN_MSG]
    header = f"🏛 Найдено имущество: {total}"
    server_line = f"🖥 Сервер: [{sid:02d}]" + (f" {name}" if name else "")
    times = (f"⚪ Найдено: {now.strftime('%d.%m %H:%M')}\n"
             f"⌛ Слет: {deadline.strftime('%d.%m %H:%M')}")
    block_lines = [f"🏠 Дома · {total}"]
    for h in shown:
        line = f"#{display_id(h)} Дом"
        title = (h.get("name") or "").strip()
        if title:
            line += f" · {title}"
        block_lines.append(line)
    if total > len(shown):
        block_lines.append(f"… и ещё {total - len(shown)}")
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

    load_server_names()
    state = load_state()
    ok = 0

    for sid in SERVER_IDS:
        d = None
        for _ in range(3):
            d = fetch_server_data(sid)
            if d is not None:
                break
            time.sleep(2)
        if d is None:
            continue
        ok += 1

        free_map = {h["id"]: h for h in d["free"]}
        free_ids = sorted(free_map)

        prev = state.get(str(sid))
        prev_free = set(prev.get("free", [])) if prev and prev.get("init") else set()
        new_ids = [i for i in free_ids if i not in prev_free]

        if len(new_ids) > ANOMALY_LIMIT:
            print(f"server {sid}: аномалия ({len(new_ids)}), переснимаю молча")
        elif new_ids:
            print(f"server {sid}: новые свободные {[display_id(free_map[i]) for i in new_ids]}")
            notify(sid, [free_map[i] for i in new_ids], datetime.now(MSK))
            time.sleep(1)

        print(f"server {sid}: занятых {d['occupied']}, свободных {len(free_ids)}")
        state[str(sid)] = {"init": True, "free": free_ids}

    save_state(state)
    print(f"Готово. Серверов отвечают: {ok}/{len(SERVER_IDS)}")


if __name__ == "__main__":
    main()
