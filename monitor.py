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
    TZ = ZoneInfo("Europe/Moscow")
except Exception:
    TZ = timezone(timedelta(hours=3))

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except Exception:
    HAS_PIL = False

R = lambda s: s[::-1]
SRC = R("pam/ipa/moc.pr-anozira.ipa-n//:sptth")
SRCS = R("anozira/srevres/moc.pr-anozira.ipa-n//:sptth")
TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT = os.environ.get("CHAT_ID", "")
IDS = list(range(1, 34))
DIR = os.path.dirname(os.path.abspath(__file__))
ST = os.path.join(DIR, "state.json")
CF = os.path.join(DIR, "settings.json")
MP = os.path.join(DIR, "map.png")
FT = os.path.join(DIR, "font.ttf")
EH = 2
SH = -1
ML = 60
AL = 200
FK = ("noOwner", "onMarketplace")
MB = 3000.0
CL = 1024
HD = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": R("/moc.pr-anozira//:sptth"),
    "Origin": R("moc.pr-anozira//:sptth"),
}
IK = ("serverId", "server_id", "id", "number", "num", "serverNumber")
NK = ("name", "fullName", "full_name", "title", "serverName", "label", "displayName")
NM = {}


def gj(url, timeout=30):
    req = urllib.request.Request(url, headers=HD)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def pn(data):
    out = {}

    def entry(d):
        sid = None
        for k in IK:
            if k in d:
                try:
                    sid = int(d[k])
                    break
                except Exception:
                    continue
        nm = None
        for k in NK:
            if d.get(k):
                nm = str(d[k]).strip()
                break
        return sid, nm

    def walk(o):
        if isinstance(o, dict):
            sid, nm = entry(o)
            if sid is not None and nm:
                out[sid] = nm
                return
            for k, v in o.items():
                if isinstance(v, dict):
                    if str(k).isdigit():
                        _, nm2 = entry(v)
                        if nm2:
                            out[int(k)] = nm2
                            continue
                    walk(v)
                elif isinstance(v, list):
                    walk(v)
                elif isinstance(v, str) and str(k).isdigit() and v.strip():
                    out[int(k)] = v.strip()
        elif isinstance(o, list):
            for it in o:
                walk(it)

    walk(data)
    return out


def lsn():
    global NM
    try:
        NM = pn(gj(SRCS))
    except Exception as e:
        print("names:", e)


def ps(chat_id, text):
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def pp(chat_id, path, caption, parse_mode=None):
    b = "mpb"
    body = b""
    fields = [("chat_id", str(chat_id)), ("caption", caption)]
    if parse_mode:
        fields.append(("parse_mode", parse_mode))
    for k, v in fields:
        body += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8")
    with open(path, "rb") as f:
        data = f.read()
    body += f"--{b}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"i.png\"\r\nContent-Type: image/png\r\n\r\n".encode("utf-8")
    body += data + b"\r\n"
    body += f"--{b}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={b}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fd(sid):
    try:
        data = gj(f"{SRC}/{sid}")
    except urllib.error.HTTPError as e:
        print(f"{sid}: http {e.code}")
        return None
    except Exception as e:
        print(f"{sid}: {e}")
        return None

    houses = data.get("houses") if isinstance(data, dict) else None
    if not isinstance(houses, dict):
        return {"free": [], "occupied": 0}

    free = []
    for key in FK:
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


def et(now):
    return (now + timedelta(hours=EH)).replace(minute=0, second=0, microsecond=0)


def lst():
    try:
        with open(ST, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def svst(state):
    with open(ST, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def la():
    try:
        with open(CF, "r", encoding="utf-8") as f:
            return list(json.load(f).get("allowed", []))
    except Exception:
        return [int(CHAT)] if CHAT else []


def di(h):
    return h.get("id", 0) + SH


def gf(size):
    paths = []
    if os.path.exists(FT):
        paths.append(FT)
    paths += ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def bm(houses, sid):
    if not HAS_PIL:
        return None
    try:
        if os.path.exists(MP):
            base = Image.open(MP).convert("RGB")
            base = base.resize((640, max(1, int(640 * base.height / base.width))))
        else:
            base = Image.new("RGB", (512, 512), (16, 18, 24))
            d0 = ImageDraw.Draw(base)
            for i in range(1, 8):
                p = i * 512 / 8
                d0.line([(p, 0), (p, 512)], fill=(30, 34, 42))
                d0.line([(0, p), (512, p)], fill=(30, 34, 42))
            for r in (80, 160, 240):
                d0.ellipse([256 - r, 256 - r, 256 + r, 256 + r], outline=(28, 32, 40))
        d = ImageDraw.Draw(base)
        W, H = base.size
        f_lab = gf(max(20, W // 30))
        f_head = gf(max(16, W // 38))
        r_dot = max(4, W // 140)
        for h in houses:
            lx = h.get("lx", 0)
            ly = h.get("ly", 0)
            x = min(max((lx + MB) / (2 * MB) * W, 8), W - 8)
            y = min(max((MB - ly) / (2 * MB) * H, 8), H - 8)
            d.ellipse([x - r_dot, y - r_dot, x + r_dot, y + r_dot], fill=(255, 30, 30))
            lab = str(di(h))
            tw = int(d.textlength(lab, font=f_lab))
            th = f_lab.size
            tx, ty = x + 10, y - 14 - th
            d.rectangle([tx - 6, ty - 4, tx + tw + 6, ty + th + 4], fill=(0, 0, 0))
            d.text((tx, ty), lab, fill=(255, 255, 255), font=f_lab)
        head = f"[{sid:02d}] {NM.get(sid, '')}"
        tw2 = int(d.textlength(head, font=f_head))
        th2 = f_head.size
        d.rectangle([8, 8, 8 + tw2 + 16, 8 + th2 + 10], fill=(0, 0, 0))
        d.text((16, 8 + (th2 + 10) / 2), head, fill=(255, 255, 255),
               font=f_head, anchor="lm")
        path = os.path.join(tempfile.gettempdir(), "i.png")
        base.save(path)
        return path
    except Exception as e:
        print("img:", e)
        return None


def nt(chats, sid, new_houses, now):
    deadline = et(now)
    name = NM.get(sid, "")
    total = len(new_houses)
    shown = new_houses[:ML]
    header = f"🏛 Найдено имущество: {total}"
    server_line = f"🖥 Сервер: [{sid:02d}]" + (f" {name}" if name else "")
    times = (f"🕒 Найдено: {now.strftime('%d.%m %H:%M')}\n"
             f"⏳ Слет: {deadline.strftime('%d.%m %H:%M')}")
    block_lines = [f"🏠 ДОМА ({total})"]
    for h in shown:
        line = f"#{di(h)}"
        title = (h.get("name") or "").strip()
        if title:
            line += f" - {title}"
        block_lines.append(line)
    if total > len(shown):
        block_lines.append(f"… и ещё {total - len(shown)}")
    text = (f"{header}\n\n{server_line}\n\n{times}\n\n"
            f"<pre>{escape(chr(10).join(block_lines))}</pre>")
    img = bm(new_houses, sid)
    combined = img is not None and len(text) <= CL
    for chat in chats:
        try:
            if combined:
                pp(chat, img, text, parse_mode="HTML")
            else:
                ps(chat, text)
                if img:
                    pp(chat, img, f"📍 Сервер [{sid:02d}] {name}: позиция дома")
        except Exception as e:
            print("send:", e)
        time.sleep(1)


def main():
    if not TOKEN:
        sys.exit(1)

    lsn()
    state = lst()
    allowed = la()
    ok = 0

    for sid in IDS:
        d = None
        for _ in range(3):
            d = fd(sid)
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

        if len(new_ids) > AL:
            print(f"{sid}: skip {len(new_ids)}")
        elif new_ids:
            if allowed:
                print(f"{sid}: +{len(new_ids)}")
                nt(allowed, sid, [free_map[i] for i in new_ids], datetime.now(TZ))
            else:
                print(f"{sid}: no users")

        print(f"{sid}: {len(free_ids)}")
        state[str(sid)] = {"init": True, "free": free_ids}

    svst(state)
    print(f"ok {ok}/{len(IDS)}")


if __name__ == "__main__":
    main()
