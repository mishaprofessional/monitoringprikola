import json
import os
import sys
import tempfile
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

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except Exception:
    HAS_PIL = False

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

API_URL = "https://n-api.arizona-rp.com/api/map"
SERVERS_URL = "https://n-api.arizona-rp.com/api/servers/arizona"
SERVER_IDS = list(range(1, 34))
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

EXPIRE_HOURS = 3
HOUSE_ID_SHIFT = -1
MAX_LIST_IN_MSG = 60
ANOMALY_LIMIT = 200
FREE_KEYS = ("noOwner", "onMarketplace")
MAP_BOUND = 3000.0   # игровые координаты примерно от -3000 до 3000

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


def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


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
        SERVER_NAMES = parse_names(http_get_json(SERVERS_URL))
    except Exception as e:
        print("Список серверов не получен:", e)


def tg_send(chat_id, text):
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def tg_send_photo(chat_id, path, caption):
    boundary = "arzmapbound"
    body = b""
    for k, v in (("chat_id", str(chat_id)), ("caption", caption)):
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8")
    with open(path, "rb") as f:
        data = f.read()
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"map.png\"\r\nContent-Type: image/png\r\n\r\n".encode("utf-8")
    body += data + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_server_data(sid):
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
    return (now + timedelta(hours=EXPIRE_HOURS)).replace(minute=0, second=0, microsecond=0)


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def load_allowed():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return list(json.load(f).get("allowed", []))
    except Exception:
        return [int(CHAT_ID)] if CHAT_ID else []


def display_id(h):
    return h.get("id", 0) + HOUSE_ID_SHIFT


def build_radar_image(houses, sid):
    if not HAS_PIL:
        return None
    try:
        S = 512
        img = Image.new("RGB", (S, S), (16, 18, 24))
        d = ImageDraw.Draw(img)
        for i in range(1, 8):
            p = i * S / 8
            d.line([(p, 0), (p, S)], fill=(30, 34, 42))
            d.line([(0, p), (S, p)], fill=(30, 34, 42))
        for r in (80, 160, 240):
            d.ellipse([S / 2 - r, S / 2 - r, S / 2 + r, S / 2 + r], outline=(28, 32, 40))
        for h in houses:
            lx = h.get("lx", 0)
            ly = h.get("ly", 0)
            x = min(max((lx + MAP_BOUND) / (2 * MAP_BOUND) * S, 8), S - 8)
            y = min(max((MAP_BOUND - ly) / (2 * MAP_BOUND) * S, 8), S - 8)
            d.ellipse([x - 10, y - 10, x + 10, y + 10], outline=(255, 60, 60), width=3)
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(255, 60, 60))
            lab = f"#{display_id(h)}"
            d.rectangle([x + 12, y - 26, x + 12 + 7 * len(lab) + 6, y - 8], fill=(0, 0, 0))
            d.text((x + 15, y - 24), lab, fill=(255, 255, 255))
        d.text((10, 8), f"[{sid:02d}] {SERVER_NAMES.get(sid, '')}", fill=(140, 150, 165))
        d.text((10, S - 22), "схема: позиция дома на карте сервера", fill=(90, 98, 110))
        path = os.path.join(tempfile.gettempdir(), "arz_radar.png")
        img.save(path)
        return path
    except Exception as e:
        print("Ошибка сборки схемы:", e)
        return None


def notify(chats, sid, new_houses, now):
    deadline = expire_time(now)
    name = SERVER_NAMES.get(sid, "")
    total = len(new_houses)
    shown = new_houses[:MAX_LIST_IN_MSG]
    header = f"🏛 Найдено имущество: {total}"
    server_line = f"🖥 Сервер: [{sid:02d}]" + (f" {name}" if name else "")
    times = (f"🕒 Найдено: {now.strftime('%d.%m %H:%M')}\n"
             f"⏳ Слет: {deadline.strftime('%d.%m %H:%M')}")
    block_lines = [f"🏠 ДОМА ({total})"]
    for h in shown:
        line = f"#{display_id(h)}"
        title = (h.get("name") or "").strip()
        if title:
            line += f" - {title}"
        block_lines.append(line)
    if total > len(shown):
        block_lines.append(f"… и ещё {total - len(shown)}")
    text = (f"{header}\n\n{server_line}\n\n{times}\n\n"
            f"<pre>{escape(chr(10).join(block_lines))}</pre>")
    img = build_radar_image(new_houses, sid)
    for chat in chats:
        try:
            tg_send(chat, text)
        except Exception as e:
            print("Ошибка отправки:", e)
        if img:
            try:
                tg_send_photo(chat, img, f"📍 Сервер [{sid:02d}] {name}: позиция дома")
            except Exception as e:
                print("Ошибка отправки фото:", e)
        time.sleep(1)


def main():
    if not BOT_TOKEN:
        print("Не задан BOT_TOKEN")
        sys.exit(1)

    load_server_names()
    state = load_state()
    allowed = load_allowed()
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
            if allowed:
                print(f"server {sid}: новые свободные {[display_id(free_map[i]) for i in new_ids]}")
                notify(allowed, sid, [free_map[i] for i in new_ids], datetime.now(MSK))
            else:
                print(f"server {sid}: новые свободные, но нет активированных пользователей")

        print(f"server {sid}: занятых {d['occupied']}, свободных {len(free_ids)}")
        state[str(sid)] = {"init": True, "free": free_ids}

    save_state(state)
    print(f"Готово. Серверов отвечают: {ok}/{len(SERVER_IDS)}")


if __name__ == "__main__":
    main()
