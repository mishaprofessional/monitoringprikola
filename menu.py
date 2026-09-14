import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    MSK = ZoneInfo("Europe/Moscow")
except Exception:
    MSK = timezone(timedelta(hours=3))

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
KEY = os.environ.get("KEY", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
BASE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE, "settings.json")
MENU_STATE_FILE = os.path.join(BASE, "menu_state.json")

LOCK_TEXT = ("🔒 Данный бот является приватным.\n\n"
             "Чтобы использовать его, пришлите ключ доступа.")
OK_TEXT = ("✅ Доступ открыт!\n\n"
           "Напиши /start — и когда бот найдет дом который слили в госс тебе придет уведомление!")
START_TEXT = ("🗺 Бот мониторит карту имущества (33 сервера).\n"
              "Если что-то появится — он сообщит!")


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
        tg("sendMessage", {"chat_id": chat_id, "text": text})
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


def user_title(u):
    fn = (u.get("first_name") or "").strip()
    ln = (u.get("last_name") or "").strip()
    name = " ".join(x for x in (fn, ln) if x)
    un = (u.get("username") or "").strip()
    title = name or un or "Неизвестный пользователь"
    if un:
        title += f" (@{un})"
    return title


def fetch_chat_title(cid):
    try:
        ch = tg("getChat", {"chat_id": cid})
        return user_title(ch)
    except Exception:
        return None


def main():
    if not BOT_TOKEN:
        return
    owner = int(CHAT_ID) if CHAT_ID else None
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
            frm = msg.get("from") or {}
            info = settings.setdefault("allowed_info", {})
            rec = {"name": user_title(frm), "id": chat_id,
                   "since": datetime.now(MSK).strftime("%d.%m.%Y %H:%M")}
            info[str(chat_id)] = rec
            tg_send(chat_id, OK_TEXT)
            if owner is not None and chat_id != owner:
                tg_send(owner, "🔑 Новый доступ активирован!\n"
                               f"👤 {rec['name']}\n"
                               f"🆔 {chat_id}\n"
                               f"🕒 {rec['since']}")
            continue

        if text in ("/who", "/users", "/access"):
            if owner is not None and chat_id == owner:
                info = settings.setdefault("allowed_info", {})
                lines = []
                for cid in sorted(allowed):
                    r = info.get(str(cid))
                    if not r or not r.get("name") or r["name"] == "Неизвестный пользователь":
                        title = fetch_chat_title(cid)
                        if title:
                            r = {"name": title, "id": cid,
                                 "since": (r or {}).get("since", "данных нет")}
                            info[str(cid)] = r
                    if r and r.get("name"):
                        lines.append(f"• {r['name']} — id {cid}, доступ с {r['since']}")
                    else:
                        lines.append(f"• id {cid} (не удалось получить профиль)")
                if not lines:
                    lines.append("Пока никого.")
                tg_send(chat_id, "🔑 У кого есть доступ:\n" + "\n".join(lines))
            else:
                tg_send(chat_id, LOCK_TEXT)
            continue

        if text.startswith(("/revoke", "/ban", "/kick")):
            if owner is not None and chat_id == owner:
                arg = text.split(None, 1)[1].strip() if " " in text else ""
                if not arg:
                    tg_send(chat_id, "Как пользоваться: /revoke <id> или /revoke @юзернейм")
                else:
                    target = None
                    if arg.lstrip("-").isdigit():
                        target = int(arg)
                    else:
                        needle = arg.lstrip("@").lower()
                        info = settings.get("allowed_info", {})
                        for cid in sorted(allowed):
                            nm = ((info.get(str(cid)) or {}).get("name") or "").lower()
                            if needle and (f"@{needle}" in nm or nm.startswith(needle)):
                                target = cid
                                break
                    if target is not None and target in allowed:
                        allowed.discard(target)
                        info = settings.setdefault("allowed_info", {})
                        rec = info.pop(str(target), None)
                        nm = (rec or {}).get("name") or f"id {target}"
                        tg_send(chat_id, f"🚫 Доступ отозван: {nm}")
                        tg_send(target, "🚫 Доступ к боту отозван владельцем.")
                    else:
                        tg_send(chat_id, "😕 Не нашёл такого среди имеющих доступ. Список: /who")
            else:
                tg_send(chat_id, LOCK_TEXT)
            continue

        if text in ("/start", "/menu", "Меню", "меню"):
            if chat_id in allowed:
                tg_send(chat_id, START_TEXT)
            else:
                tg_send(chat_id, LOCK_TEXT)

    settings["allowed"] = sorted(allowed)
    save_json(SETTINGS_FILE, settings)
    save_json(MENU_STATE_FILE, mstate)
    print("menu ok, updates:", len(updates))


if __name__ == "__main__":
    main()
