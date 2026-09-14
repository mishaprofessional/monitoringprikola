import json
import os
import urllib.request

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
SERVERS_URL = "https://n-api.arizona-rp.com/api/servers/arizona"
SERVER_IDS = list(range(1, 34))
BASE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE, "settings.json")
MENU_STATE_FILE = os.path.join(BASE, "menu_state.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://arizona-rp.com/",
    "Origin": "https://arizona-rp.com",
}

ID_KEYS = ("serverId", "server_id", "id", "number", "num", "serverNumber")
NAME_KEYS = ("name", "fullName", "full_name", "title", "serverName", "label", "displayName")


def tg(method, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


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


def server_names():
    try:
        req = urllib.request.Request(SERVERS_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        return parse_names(data)
    except Exception as e:
        print("Список серверов не получен:", e)
        return {}


def is_sub(settings, sid):
    sub = settings.get("servers")
    return sub is None or sid in sub


def cur_text(settings, names):
    sub = settings.get("servers")
    if sub is None:
        return "все 33 сервера"
    if not sub:
        return "ничего не выбрано"
    return ", ".join(f"{s:02d} {names.get(s, '')}".strip() for s in sorted(sub))


def main_text():
    return "👋 Привет, охотник за имуществом!\n\nВыбери нужный раздел ниже."


def main_kb():
    return {"inline_keyboard": [
        [{"text": "🔍 Найти имущество", "callback_data": "find"}],
    ]}


def sel_text(settings, names):
    return ("🖥 Выбери серверы, о слётах домов на которых хочешь получать уведомления:\n\n"
            "✅ — уведомления приходят\n"
            "⬜️ — выключено\n\n"
            f"Сейчас подписка: {cur_text(settings, names)}\n\n"
            "Когда закончишь — жми «✅ Готово».")


def sel_kb(settings, names):
    rows, row = [], []
    for sid in SERVER_IDS:
        mark = "✅" if is_sub(settings, sid) else "⬜️"
        nm = names.get(sid, f"Сервер {sid}")[:12]
        row.append({"text": f"{mark} {sid:02d} {nm}", "callback_data": f"t:{sid}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "✅ Готово", "callback_data": "done"}])
    rows.append([{"text": "← Назад", "callback_data": "back"}])
    return {"inline_keyboard": rows}


def confirm_text(settings, names):
    return ("✅ Отлично! Настройки сохранены.\n\n"
            f"Ты подписан на: {cur_text(settings, names)}.\n"
            "Если что-то слетит на выбранных серверах — бот сразу же тебя оповестит! 🏠🔔")


def main():
    if not BOT_TOKEN or not CHAT_ID:
        return
    chat_id = int(CHAT_ID)
    mstate = load_json(MENU_STATE_FILE, {"offset": 0})
    settings = load_json(SETTINGS_FILE, {"servers": None})
    names = server_names()

    try:
        resp = tg("getUpdates", {"offset": mstate.get("offset", 0), "timeout": 5,
                                 "allowed_updates": ["message", "callback_query"]})
    except Exception as e:
        print("getUpdates error:", e)
        return
    updates = resp.get("result", [])

    for u in updates:
        mstate["offset"] = max(mstate.get("offset", 0), u["update_id"] + 1)
        cb = u.get("callback_query")
        if cb:
            if (cb.get("from") or {}).get("id") != chat_id:
                continue
            data = cb.get("data", "")
            mid = (cb.get("message") or {}).get("message_id")
            try:
                tg("answerCallbackQuery", {"callback_query_id": cb.get("id")})
            except Exception:
                pass

            if data == "find":
                try:
                    tg("editMessageText", {"chat_id": chat_id, "message_id": mid,
                                           "text": sel_text(settings, names),
                                           "reply_markup": sel_kb(settings, names)})
                except Exception as e:
                    print("edit error:", e)
            elif data == "back":
                try:
                    tg("editMessageText", {"chat_id": chat_id, "message_id": mid,
                                           "text": main_text(), "reply_markup": main_kb()})
                except Exception as e:
                    print("edit error:", e)
            elif data.startswith("t:"):
                sid = int(data[2:])
                sub = settings.get("servers")
                if sub is None:
                    sub = list(SERVER_IDS)
                if sid in sub:
                    sub.remove(sid)
                else:
                    sub.append(sid)
                settings["servers"] = sorted(sub)
                try:
                    tg("editMessageText", {"chat_id": chat_id, "message_id": mid,
                                           "text": sel_text(settings, names),
                                           "reply_markup": sel_kb(settings, names)})
                except Exception as e:
                    print("edit error:", e)
            elif data == "done":
                try:
                    tg("editMessageText", {"chat_id": chat_id, "message_id": mid,
                                           "text": "✅ Выбор сохранён."})
                except Exception:
                    pass
                try:
                    tg("sendMessage", {"chat_id": chat_id,
                                       "text": confirm_text(settings, names),
                                       "reply_markup": main_kb()})
                except Exception as e:
                    print("send error:", e)
            continue

        msg = u.get("message") or {}
        if msg.get("chat", {}).get("id") != chat_id:
            continue
        text = (msg.get("text") or "").strip()
        if text in ("/start", "/menu", "/settings", "Меню", "меню"):
            try:
                tg("sendMessage", {"chat_id": chat_id, "text": main_text(),
                                   "reply_markup": main_kb()})
            except Exception as e:
                print("send error:", e)

    save_json(SETTINGS_FILE, settings)
    save_json(MENU_STATE_FILE, mstate)
    print("menu ok, updates:", len(updates))


if __name__ == "__main__":
    main()
