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
SRCS = R("anozira/srevres/ipa/moc.pr-anozira.ipa-n//:sptth")
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
BL = ("нефтевышка",)
QCOLOR = "7856F0"
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
LK = []


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


def wb(o, out):
    if isinstance(o, dict):
        if "lx" in o and "owner" in o:
            out.append(o)
        else:
            for v in o.values():
                wb(v, out)
    elif isinstance(o, list):
        for v in o:
            wb(v, out)


def on_auction(x):
    return (x.get("hasAuction") or 0) == 1 or (x.get("auTimeEnd") or 0) > 0


def is_free_biz(b):
    nm = (b.get("name") or "").strip().lower()
    for bad in BL:
        if bad in nm:
            return False
    if on_auction(b):
        return False
    o = (b.get("owner") or "").strip().lower()
    return o == "" or o == "the state"


def fd(sid):
    global LK
    try:
        data = gj(f"{SRC}/{sid}")
    except urllib.error.HTTPError as e:
        print(f"{sid}: http {e.code}")
        return None
    except Exception as e:
        print(f"{sid}: {e}")
        return None

    if isinstance(data, dict):
        if not LK:
            LK = list(data.keys())
        if sid == IDS[0]:
            bs = data.get("businesses") or {}
            parts = []
            for k, v in bs.items():
                parts.append(f"{k}:{len(v) if isinstance(v, (list, dict)) else -1}")
            print("bizstruct:", ",".join(parts))
            na = bs.get("noAuction")
            if isinstance(na, dict) and na:
                k0 = next(iter(na))
                print("bizsample:", json.dumps({k0: na[k0]}, ensure_ascii=False)[:300])
            elif isinstance(na, list) and na:
                print("bizsample:", json.dumps(na[0], ensure_ascii=False)[:300])

    houses = data.get("houses") if isinstance(data, dict) else None
    if not isinstance(houses, dict):
        return {"free": [], "biz": [], "occupied": 0}

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
    free = [h for h in free if not on_auction(h)]

    biz_all = []
    wb(data.get("businesses"), biz_all)
    biz = [b for b in biz_all if isinstance(b, dict) and "id" in b and is_free_biz(b)]
    return {"free": free, "biz": biz, "occupied": occupied}


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


def bm(items, sid, kind):
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
        f_head = gf(max(14, W // 44))
        f_lab = gf(max(14, W // 40))
        r_dot = max(6, W // 100)
        col = (255, 30, 30) if kind == "h" else (60, 220, 90)
        for it in items:
            lx = it.get("lx", 0)
            ly = it.get("ly", 0)
            x = min(max((lx + MB) / (2 * MB) * W, 8), W - 8)
            y = min(max((MB - ly) / (2 * MB) * H, 8), H - 8)
            d.ellipse([x - r_dot + 2, y - r_dot + 3, x + r_dot + 2, y + r_dot + 3],
                      fill=(0, 0, 0))
            d.ellipse([x - r_dot, y - r_dot, x + r_dot, y + r_dot],
                      fill=col, outline=(0, 0, 0), width=2)
            if kind == "h":
                lab = str(di(it))
            else:
                nm = (it.get("name") or "").strip() or str(it.get("id", 0))
                lab = nm if len(nm) <= 16 else nm[:15] + "…"
            tw = int(d.textlength(lab, font=f_lab))
            th = f_lab.size
            bx0 = min(max(x + r_dot, 4), W - tw - 10)
            by0 = min(max(y - r_dot - (th + 2), 4), H - th - 6)
            d.rectangle([bx0, by0, bx0 + tw + 6, by0 + th + 2], fill=(0, 0, 0))
            d.text((bx0 + (tw + 6) / 2, by0 + (th + 2) / 2), lab,
                   fill=(255, 255, 255), font=f_lab, anchor="mm")
        head = f"[{sid:02d}] {NM.get(sid, '')}"
        tw2 = int(d.textlength(head, font=f_head))
        th2 = f_head.size
        d.rectangle([8, 8, 8 + tw2 + 16, 8 + th2 + 10], fill=(0, 0, 0))
        d.text((8 + (tw2 + 16) / 2, 8 + (th2 + 10) / 2), head,
               fill=(255, 255, 255), font=f_head, anchor="mm")
        path = os.path.join(tempfile.gettempdir(), "i.png")
        base.save(path)
        return path
    except Exception as e:
        print("img:", e)
        return None


def ct(sid, items, now, kind):
    deadline = et(now)
    name = NM.get(sid, "")
    total = len(items)
    shown = items[:ML]
    if kind == "h":
        head = ("🏠 Найден дом" if total == 1 else "🏘 Найдено несколько домов").upper()
        block = [f"🏠 ДОМА (Количество: {total})"]
        for it in shown:
            line = f"#{di(it)}"
            t = (it.get("name") or "").strip()
            if t:
                line += f" - {t}"
            block.append(line)
    else:
        head = ("🏦 Найден бизнес" if total == 1 else "🏬 Найдено несколько бизнесов").upper()
        block = [f"💼 БИЗНЕСЫ (Количество: {total})"]
        for it in shown:
            t = (it.get("name") or "").strip() or f"#{it.get('id', 0)}"
            block.append(t)
    if total > len(shown):
        block.append(f"… и ещё {total - len(shown)}")
    srv = f"[{sid:02d}]" + (f" {name}" if name else "")
    t1 = now.strftime("%H:%M")
    d1 = now.strftime("%d.%m.%Y")
    t2 = deadline.strftime("%H:%M")
    d2 = deadline.strftime("%d.%m.%Y")
    q = "<blockquote color=\"CLRPH\">"
    text = (f"{q}<code>{escape(head)}</code></blockquote>\n"
            f"{q}<code>Сервер:</code> <b>{escape(srv)}</b></blockquote>\n"
            f"{q}<code>Обнаружено:</code> <b>{t1}</b> <tg-spoiler><b>D1TK</b></tg-spoiler>\n"
            f"<code>Слет:</code> <b>{t2}</b> <tg-spoiler><b>D2TK</b></tg-spoiler></blockquote>\n"
            f"<pre>{escape(chr(10).join(block))}</pre>")
    text = text.replace("0", "<b>O</b>")
    text = text.replace("CLRPH", QCOLOR)
    text = text.replace("D1TK", d1)
    text = text.replace("D2TK", d2)
    return text


def nt(chats, sid, h_items, b_items, now):
    for kind, items in (("h", h_items), ("b", b_items)):
        if not items:
            continue
        name = NM.get(sid, "")
        text = ct(sid, items, now, kind)
        plain = text.replace(f" color=\"{QCOLOR}\"", "")
        img = bm(items, sid, kind)
        for chat in chats:
            if img:
                try:
                    pp(chat, img, "")
                except Exception as e:
                    print("send:", e)
            ok_sent = False
            for variant in (text, plain):
                try:
                    ps(chat, variant)
                    ok_sent = True
                    break
                except Exception as e:
                    print("send:", e)
            if not ok_sent and img:
                try:
                    pp(chat, img, f"📍 Сервер [{sid:02d}] {name}")
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
        biz_map = {b["id"]: b for b in d["biz"]}
        biz_ids = sorted(biz_map)

        prev = state.get(str(sid))
        prev_free = set(prev.get("free", [])) if prev else set()
        prev_biz = set(prev.get("biz", [])) if prev else set()

        new_h = [i for i in free_ids if i not in prev_free]
        new_b = [i for i in biz_ids if i not in prev_biz]

        if len(new_h) > AL:
            print(f"{sid}: skip h {len(new_h)}")
            new_h = []
        if len(new_b) > AL:
            print(f"{sid}: skip b {len(new_b)}")
            new_b = []

        if (new_h or new_b) and allowed:
            print(f"{sid}: +h{len(new_h)} +b{len(new_b)}")
            nt(allowed, sid, [free_map[i] for i in new_h],
               [biz_map[i] for i in new_b], datetime.now(TZ))

        print(f"{sid}: h{len(free_ids)} b{len(biz_ids)}")
        state[str(sid)] = {"init": True, "free": free_ids, "biz": biz_ids}

    svst(state)
    print(f"ok {ok}/{len(IDS)}")
    if LK:
        print("topkeys:", ",".join(LK))


if __name__ == "__main__":
    main()
