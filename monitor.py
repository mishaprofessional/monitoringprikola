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
ROUND_UP_HOUR = False   # True - округлять слет вверх до часа
HOUSE_ID_SHIFT = -1     # номера домов на карте сдвинуты относительно id API

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


def fetch_houses(sid):
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
        items = [h for lst in houses.values() if isinstance(lst, list) for h in lst if isinstance(h, dict)]
    elif isinstance(houses, list):
        items = [h for h in houses if isinstance(h, dict)]
    else:
        items = []
    return items


def is_free_entry(h):
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


def display_id(h):
    return h.get("id", 0) + HOUSE_ID_SHIFT


def notify(sid, new_houses, now):
    deadline = now + timedelta(hours=EXPIRE_HOURS)
    if ROUND_UP_HOUR:
        deadline = (deadline + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    name = SERVER_NAMES.get(sid, "")
    header = f"🏛 Найдено имущество: {len(new_houses)}"
    server_line = f"🖥 Сервер: [{sid}]" + (f" {name}" if name else "")
    times = (f"⚪ Найдено: {now.strftime('%d.%m %H:%M')}\n"
             f"⌛ Слет: {deadline.strftime('%d.%m %H:%M')}")
    block_lines = [f"🏠 ДОМА ({len(new_houses)})"]
    for h in new_houses:
        line = f"#{display_id(h)}"
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

    load_server_names()
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

        cur_ids = sorted(h["id"] for h in houses)
        free_map = {h["id"]: h for h in houses if is_free_entry(h)}

        prev = state.get(str(sid))
        if not prev or not prev.get("init") or "ids" not in prev:
            state[str(sid)] = {"init": True, "ids": cur_ids, "free": sorted(free_map)}
            print(f"server {sid}: базовый снимок, занятых {len(cur_ids)}, свободных {len(free_map)}")
            continue

        disappeared = set(prev.get("ids", [])) - set(cur_ids)
        if len(disappeared) > 50:
            print(f"server {sid}: массовые изменения ({len(disappeared)}), переснимаю снимок без уведомлений")
            state[str(sid)] = {"init": True, "ids": cur_ids, "free": sorted(free_map)}
            continue

        for i in disappeared:
            free_map.setdefault(i, {"id": i, "name": ""})
        if disappeared:
            print(f"server {sid}: исчезли из списка занятых: {sorted(disappeared)}")

        free_ids = sorted(free_map)
        new_ids = [i for i in free_ids if i not in set(prev.get("free", []))]
        if new_ids:
            print(f"server {sid}: новые свободные {[display_id(free_map[i]) for i in new_ids]}")
            notify(sid, [free_map[i] for i in new_ids], datetime.now(MSK))
            time.sleep(1)

        state[str(sid)] = {"init": True, "ids": cur_ids, "free": free_ids}

    save_state(state)
    print(f"Готово. Серверов отвечают: {ok}/{len(SERVER_IDS)}")


if __name__ == "__main__":
    main()
