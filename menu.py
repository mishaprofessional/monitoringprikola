import json
import os
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
KEY = os.environ.get("KEY", "")
API_URL = "https://n-api.arizona-rp.com/api/map"
SERVERS_URL = "https://n-api.arizona-rp.com/api/servers/arizona"
SERVER_IDS = list(range(1, 34))
BASE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE, "settings.json")
MENU_STATE_FILE = os.path.join(BASE, "menu_state.json")

EXPIRE_HOURS = 2
ROUND_UP_HOUR = True
HOUSE_ID_SHIFT = -1
MAX_LIST_IN_MSG = 60
FREE_KEYS = ("noOwner", "onMarketplace")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://arizona-rp.com/",
    "Origin": "https://arizona-rp.com",
}

ID_KEYS = ("serverId", "server_id", "id", "number", "num", "serverNumber")
NAME_KEYS = ("name", "fullName", "full_name", "title", "serverName", "label", "displayName")

SERVER_NAMES = {}

LOCK_TEXT = ("🔒 Данный бот является приватным.\n\n"
             "Чтобы использовать его, пришлите ключ доступа.")
OK_TEXT = ("✅ Доступ открыт!\n\n"
           "Напиши /start — бот сразу покажет всё свободное имущество на 33 серверах, "
           "а дальше будет следить сам: новые слёты будут приходить каждые ~10 минут.")


def tg(method, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def tg_send(chat_id, text):
    try:
        tg("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except Exception as e:
        print("Ошибка отправки:", e)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def parse_names(data):
    names = {}

    def entry(d):
        sid = None
        for k in ID_KEYS:
            if k in d:
                try:
                    sid = int(d[k])
                    break
                except Exception:
                    continue
        nm = None
        for k in NAME_KEYS:
            if d.get(k):
                nm = str(d[k]).strip()
                break
        return sid, nm

    def walk(o):
        if isinstance(o, dict):
            sid, nm = entry(o)
            if sid is not None and nm:
                names[sid] = nm
                return
            for k, v in o.items():
                if isinstance(v, dict):
                    if str(k).isdigit():
                        _, nm2 = entry(v)
                        if nm2:
                            names[int(k)] = nm2
                            continue
                    walk(v)
                elif isinstance(v, list):
                    walk(v)
                elif isinstance(v, str) and str(k).isdigit() and v.strip():
                    names[int(k)] = v.strip()
        elif isinstance(o, list):
            for it in o:
                walk(it)

    walk(data)
    return names


def load_server_names():
    global SERVER_NAMES
    try:
        req = urllib.request.Request(SERVERS_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            SERVER_NAMES = parse_names(json.loads(r.read().decode("utf-8")))
    except Exception as e:
        print("Список серверов не получен:", e)


def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_free(sid):
    try:
        data = http_get_json(f"{API_URL}/{sid}")
    except Exception:
        return None
    houses = data.get("houses") if isinstance(data, dict) else None
    if not isinstance(houses, dict):
        return []
    free = []
    for key in FREE_KEYS:
        lst = houses.get(key)
        if isinstance(lst, list):
            free.extend(h for h in lst if isinstance(h, dict))
    lst = houses.get("hasOwner")
    if isinstance(lst, list):
        free.extend(h for h in lst if isinstance(h, dict) and not (h.get("owner") or "").strip())
    return free


def expire_time(now):
    d = now + timedelta(hours=EXPIRE_HOURS)
    if ROUND_UP_HOUR:
        d = d.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return d


def display_id(h):
    return h.get("id", 0) + HOUSE_ID_SHIFT


def card_text(sid, houses, now):
    deadline = expire_time(now)
    name = SERVER_NAMES.get(sid, "")
    total = len(houses)
    shown = houses[:MAX_LIST_IN_MSG]
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
    return (f"{header}\n\n{server_line}\n\n{times}\n\n"
            f"<pre>{escape(chr(10).join(block_lines))}</pre>")


def dump_all_free(chat_id):
    load_server_names()
    tg_send(chat_id, "🔎 Проверяю 33 сервера, присылаю всё свободное на данный момент…")
    sent = 0
    for sid in SERVER_IDS:
        free = None
        for _ in range(3):
            free = fetch_free(sid)
            if free is not None:
                break
            time.sleep(2)
        if not free:
            continue
        sent += 1
        tg_send(chat_id, card_text(sid, free, datetime.now(MSK)))
        time.sleep(1)
    if not sent:
        tg_send(chat_id, "🟢 Сейчас свободных домов нет ни на одном сервере. "
                         "Бот продолжит следить и пришлёт сообщение, как только что-то слетит.")


def main():
    if not BOT_TOKEN:
        return
    mstate = load_json(MENU_STATE_FILE, {"offset": 0})
    settings = load_json(SETTINGS_FILE, {"allowed": []})
    allowed = set(settings.get("allowed", []))

    try:
        resp = tg("getUpdates", {"offset": mstate.get("offset", 0), "timeout": 5,
                                 "allowed_updates": ["message"]})
    except Exception as e:
        print("getUpdates error:", e)
        return
    updates = resp.get("result", [])

    for u in updates:
        mstate["offset"] = max(mstate.get("offset", 0), u["update_id"] + 1)
        msg = u.get("message") or {}
        chat_id = msg.get("chat", {}).get("id")
        if chat_id is None:
            continue
        text = (msg.get("text") or "").strip()

        if KEY and text == KEY:
            allowed.add(chat_id)
            tg_send(chat_id, OK_TEXT)
            continue

        if text in ("/start", "/menu", "Меню", "меню"):
            if chat_id in allowed:
                dump_all_free(chat_id)
            else:
                tg_send(chat_id, LOCK_TEXT)

    settings["allowed"] = sorted(allowed)
    save_json(SETTINGS_FILE, settings)
    save_json(MENU_STATE_FILE, mstate)
    print("menu ok, updates:", len(updates))


if __name__ == "__main__":
    main()
