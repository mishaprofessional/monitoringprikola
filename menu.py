import json
import os
import urllib.request

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
KEY = os.environ.get("KEY", "")
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
                tg_send(chat_id, START_TEXT)
            else:
                tg_send(chat_id, LOCK_TEXT)

    settings["allowed"] = sorted(allowed)
    save_json(SETTINGS_FILE, settings)
    save_json(MENU_STATE_FILE, mstate)
    print("menu ok, updates:", len(updates))


if __name__ == "__main__":
    main()
