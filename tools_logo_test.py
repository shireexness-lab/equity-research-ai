"""
tools_logo_test.py — ทดลองดึงโลโก้หุ้น ก่อนตัดสินใจทำจริง
============================================================

จุดประสงค์
-----------
ตอบ 3 คำถามด้วย **ตัวเลขจริง** ไม่ใช่การเดา

    1. ดึงโลโก้ได้กี่ % ของหุ้นที่ลอง
    2. ที่ได้มา คุณภาพใช้ได้จริงกี่ตัว (ไม่เบลอ ไม่ใช่ไอคอนทั่วไป)
    3. ขนาดไฟล์จริงเท่าไร -> ใช้พื้นที่เท่าไรถ้าทำครบทั้งตลาด

**สคริปต์นี้ไม่แตะหน้าเว็บและไม่แตะข้อมูลเดิม** เขียนไฟล์ทดสอบไว้ที่
`cache/logo_test/` อย่างเดียว ลบทิ้งได้ทุกเมื่อโดยไม่กระทบอะไร

หาโลโก้จากไหน
--------------
yfinance เลิกให้ `logo_url` แล้ว (ตรวจ 400 ตัวพบ 0%)
แต่ยังให้ `website` อยู่ (หุ้นไทย 98% · หุ้นสหรัฐ 87%)
จึงไปดึงไอคอนจากเว็บบริษัทเอง โดยไล่ตามลำดับคุณภาพ

    1. apple-touch-icon        180x180 ขึ้นไป — คมที่สุด เว็บสมัยใหม่มีเกือบทุกเว็บ
    2. <link rel="icon"> ที่ระบุขนาดใหญ่สุด
    3. og:image                 รูปที่เว็บใช้ตอนแชร์ มักเป็นโลโก้หรือภาพหน้าปก
    4. /favicon.ico             ตัวสำรองสุดท้าย มักเล็กและเบลอ

วิธีตัดสินว่า "ใช้ได้"
----------------------
    ขนาด >= 64px ทั้งกว้างและสูง     -> คมพอสำหรับแสดงที่ 32-48px บนจอมือถือ
    ไม่ใช่ภาพสีเดียวทั้งภาพ          -> กันไอคอนว่างเปล่าหรือสี่เหลี่ยมทึบ

วิธีใช้
--------
    python3 tools_logo_test.py                 ทดลอง 50 ตัว (ไทย 25 · สหรัฐ 25)
    python3 tools_logo_test.py --n 100         ทดลองมากขึ้น
    python3 tools_logo_test.py --thai          เฉพาะหุ้นไทย
    python3 tools_logo_test.py --เปิดดู        เปิดโฟลเดอร์ผลลัพธ์ให้ดูรูปจริง
"""

import argparse
import io
import pickle
import random
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "cache" / "logo_test"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

# ขนาดต่ำสุดที่ถือว่าคมพอ
#
# บนเว็บเราจะแสดงโลโก้ที่ราว 32-48px
# จอมือถือความละเอียดสูง (Retina) ต้องการรูปใหญ่กว่าที่แสดงจริง 2 เท่า
# 64px จึงเป็นเส้นแบ่งที่สมเหตุสมผล ต่ำกว่านี้จะเห็นเป็นขอบหยัก
MIN_PX = 64

TIMEOUT = 8


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get(url, timeout=TIMEOUT, max_bytes=2_000_000):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,image/*,*/*"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
        return r.read(max_bytes)


def icon_candidates(site: str):
    """
    หาที่อยู่รูปที่น่าจะเป็นโลโก้ เรียงจากคุณภาพดีสุดไปแย่สุด

    อ่านหน้าแรกของเว็บบริษัทแล้วมองหาแท็กที่บอกไอคอนไว้
    """
    out = []
    try:
        html = _get(site).decode("utf-8", errors="replace")
    except Exception:
        html = ""

    base = site.rstrip("/")

    def absolute(u):
        if not u:
            return None
        u = u.strip().strip('"\'')
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        return urllib.parse.urljoin(base + "/", u)

    if html:
        # 1) apple-touch-icon — มาตรฐานของเว็บสมัยใหม่ มักเป็น 180x180
        for m in re.finditer(
                r'<link[^>]+rel=["\'][^"\']*apple-touch-icon[^"\']*["\'][^>]*>',
                html, re.I):
            hm = re.search(r'href=["\']([^"\']+)', m.group(0), re.I)
            if hm:
                out.append(("apple-touch-icon", absolute(hm.group(1))))

        # 2) link rel=icon — เก็บอันที่ระบุขนาดใหญ่สุดไว้ก่อน
        #
        # **ข้ามอันที่ประกาศขนาดไว้ว่าเล็กกว่าเกณฑ์**
        # เว็บใหญ่อย่าง Amazon ประกาศไอคอนไว้หลายขนาด (16 32 48 96 ...)
        # ถ้าไม่ข้าม โควตาการลองจะหมดไปกับไอคอนจิ๋วที่รู้อยู่แล้วว่าใช้ไม่ได้
        # ทำให้ไม่มีโอกาสได้ลองที่อยู่มาตรฐานซึ่งมักมีรูปใหญ่รออยู่
        icons = []
        for m in re.finditer(
                r'<link[^>]+rel=["\'][^"\']*\bicon\b[^"\']*["\'][^>]*>',
                html, re.I):
            tag = m.group(0)
            hm = re.search(r'href=["\']([^"\']+)', tag, re.I)
            if not hm:
                continue
            sm = re.search(r'sizes=["\'](\d+)x(\d+)', tag, re.I)
            px = int(sm.group(1)) if sm else 0
            if px and px < MIN_PX:
                continue          # ประกาศไว้เองว่าเล็ก ไม่ต้องเสียเวลาโหลด
            icons.append((px, absolute(hm.group(1))))
        for px, u in sorted(icons, reverse=True):
            out.append((f"link icon {px}px" if px else "link icon", u))

        # 3) og:image — รูปที่ใช้ตอนแชร์ลิงก์
        m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]*content=["\']([^"\']+)',
            html, re.I)
        if m:
            out.append(("og:image", absolute(m.group(1))))

    # 3.5) เดาที่อยู่มาตรฐานตรง ๆ — **ต้องอยู่ก่อน favicon.ico**
    #
    # ทำไมต้องเดาทั้งที่อ่าน HTML แล้ว
    # ---------------------------------
    # รอบทดสอบแรก AMZN · SMCI · CENTEL.BK ได้แค่ favicon 16-48px
    # ทั้งที่เป็นบริษัทใหญ่ที่เว็บทำมาอย่างดี
    #
    # สาเหตุคือหน้าแรกของเว็บเหล่านี้สร้างด้วย JavaScript
    # สิ่งที่เราดาวน์โหลดมาจึงเป็นโครงเปล่า ไม่มีแท็ก <link> ให้อ่าน
    # แต่ไฟล์ไอคอนยังวางอยู่ที่ตำแหน่งมาตรฐานเสมอ จึงลองเดาตรง ๆ ได้
    for guess in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png",
                  "/apple-icon.png", "/icon.png"):
        out.append((f"เดา {guess}", base + guess))

    # 5) ตัวสำรองสุดท้าย
    out.append(("favicon.ico", base + "/favicon.ico"))

    # ตัดที่อยู่ซ้ำออก คงลำดับเดิมไว้
    seen, uniq = set(), []
    for why, u in out:
        if u and u not in seen:
            seen.add(u)
            uniq.append((why, u))
    return uniq[:12]


# ภาพที่ยาวกว่าสูงเกินกี่เท่า ถือว่าเป็นแบนเนอร์ ไม่ใช่โลโก้
#
# รอบทดสอบแรกพบว่า og:image ของบางเว็บเป็นภาพแชร์ขนาด 1920x412
# พอย่อลงกรอบ 64x64 จะเหลือความสูงแค่ 13px — เป็นเส้นบาง ๆ อ่านไม่ออก
# 1.6 เท่าเป็นเส้นแบ่งที่ยอมให้โลโก้แนวนอนปกติผ่านได้ แต่กันแบนเนอร์ออก
MAX_RATIO = 1.6


def _score(w, h):
    """
    ให้คะแนนรูป — ยิ่งสูงยิ่งเหมาะ

    ตัดสินจากสองอย่าง
        ขนาด      ใหญ่กว่าดีกว่า แต่เกิน 512 ไม่ได้เพิ่มประโยชน์แล้ว
        สัดส่วน   ยิ่งใกล้จัตุรัสยิ่งดี เพราะเราแสดงในกรอบสี่เหลี่ยมจัตุรัส
    """
    if not w or not h:
        return -1
    ratio = max(w, h) / min(w, h)
    size = min(min(w, h), 512) / 512          # 0-1
    shape = 1.0 if ratio <= 1.05 else max(0.0, 1.0 - (ratio - 1.0) / 2.0)
    if ratio > MAX_RATIO:
        shape *= 0.2                          # ลงโทษแรงแต่ยังเก็บไว้เผื่อไม่มีอะไรเลย
    return size * 0.45 + shape * 0.55


def fetch_logo(site: str):
    """
    ลองดึงไอคอนจากทุกที่ที่เป็นไปได้ แล้ว **เลือกอันที่เหมาะที่สุด**

    เดิมเลือกอันที่พื้นที่มากสุด ทำให้แบนเนอร์ 1920x412 ชนะโลโก้ 180x180
    ทั้งที่แบนเนอร์ใช้ไม่ได้เลย ตอนนี้ให้คะแนนทั้งขนาดและความเป็นจัตุรัส
    """
    from PIL import Image
    best = None
    tried = 0
    for why, url in icon_candidates(site):
        # เจอรูปที่ดีพอแล้วค่อยหยุด ไม่ใช่หยุดเพราะลองครบโควตา
        #
        # รอบก่อนตั้งเพดานไว้ 7 ครั้ง แล้วโควตาหมดไปกับไอคอนจิ๋ว
        # ทำให้ที่อยู่มาตรฐานซึ่งอยู่ท้ายรายการไม่เคยได้ลองเลย
        if tried >= 10 or (best is not None and best["คะแนน"] >= 0.7):
            break
        try:
            raw = _get(url)
            im = Image.open(io.BytesIO(raw))
            im.load()
            tried += 1
        except Exception:
            continue

        w, h = im.size
        # ไฟล์ .ico มีหลายขนาดในไฟล์เดียว เอาขนาดใหญ่สุด
        if im.format == "ICO":
            try:
                sizes = sorted(im.ico.sizes())
                im = Image.open(io.BytesIO(raw))
                im.size = sizes[-1]
                im.load()
                w, h = im.size
            except Exception:
                pass

        rec = {"ที่มา": why, "url": url, "กว้าง": w, "สูง": h,
               "ไบต์ต้นทาง": len(raw), "im": im.convert("RGBA"),
               "คะแนน": _score(w, h)}
        if best is None or rec["คะแนน"] > best["คะแนน"]:
            best = rec

        # เจอรูปจัตุรัสคมพอแล้ว หยุดเลย ไม่ต้องรบกวนเว็บเขาต่อ
        if w >= 180 and h >= 180 and max(w, h) / min(w, h) <= 1.05:
            break
    return best


def is_usable(rec) -> tuple:
    """ตัดสินว่ารูปนี้ใช้แสดงบนเว็บได้จริงไหม — คืน (ใช้ได้, เหตุผล)"""
    if rec is None:
        return False, "ดึงไม่ได้"
    if rec["กว้าง"] < MIN_PX or rec["สูง"] < MIN_PX:
        return False, f"เล็กเกินไป {rec['กว้าง']}x{rec['สูง']}"

    ratio = max(rec["กว้าง"], rec["สูง"]) / min(rec["กว้าง"], rec["สูง"])
    if ratio > MAX_RATIO:
        return False, f"เป็นแบนเนอร์ {ratio:.1f}:1"

    im = rec["im"]
    # ภาพสีเดียวทั้งภาพ = ไอคอนว่างหรือสี่เหลี่ยมทึบ ไม่ใช่โลโก้
    try:
        small = im.convert("RGB").resize((16, 16))
        colors = {small.getpixel((x, y)) for x in range(16) for y in range(16)}
        if len(colors) <= 2:
            return False, "ภาพแทบไม่มีรายละเอียด"
    except Exception:
        pass
    return True, "ใช้ได้"


def save_webp(rec, path: Path, px=64) -> int:
    """ย่อเป็น WebP ขนาดที่จะใช้จริง แล้วคืนขนาดไฟล์"""
    # ต้อง import Image จากโมดูล ไม่ใช่ im.__class__
    # เพราะ im.__class__ คือคลาส Image.Image ซึ่งไม่มีเมท็อด new
    # ส่วน Image.new เป็นฟังก์ชันระดับโมดูล — คนละอย่างกัน
    from PIL import Image
    im = rec["im"].copy()
    im.thumbnail((px, px), Image.LANCZOS)
    canvas = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    canvas.paste(im, ((px - im.width) // 2, (px - im.height) // 2))
    canvas.save(path, "WEBP", quality=85, method=6)
    return path.stat().st_size


def pick_sample(n_thai, n_us):
    """เลือกหุ้นมาทดลอง — เอาตัวที่มี website เท่านั้น จะได้วัดอัตราสำเร็จจริง"""
    cache = BASE_DIR / "cache"
    files = list(cache.glob("*.pkl"))
    th = [f for f in files if f.name.endswith(".BK.pkl")]
    us = [f for f in files if not f.name.endswith(".BK.pkl")]
    random.seed(7)

    def take(fs, n):
        out = []
        random.shuffle(fs)
        for f in fs:
            if len(out) >= n:
                break
            try:
                d = pickle.load(open(f, "rb"))
            except Exception:
                continue
            i = d.get("info", {}) or {}
            if i.get("website"):
                out.append((f.stem, i.get("longName") or f.stem, i["website"]))
        return out

    return take(th, n_thai) + take(us, n_us)


def main() -> int:
    p = argparse.ArgumentParser(description="ทดลองดึงโลโก้หุ้น")
    p.add_argument("--n", type=int, default=50, help="จำนวนหุ้นที่ทดลอง")
    p.add_argument("--thai", action="store_true", help="เฉพาะหุ้นไทย")
    p.add_argument("--us", action="store_true", help="เฉพาะหุ้นสหรัฐ")
    p.add_argument("--เปิดดู", dest="open_dir", action="store_true",
                   help="เปิดโฟลเดอร์ผลลัพธ์หลังทำเสร็จ")
    a = p.parse_args()

    try:
        from PIL import Image           # noqa: F401
    except ImportError:
        print("\n  ต้องติดตั้ง Pillow ก่อน :  pip install pillow\n")
        return 1

    n_th = 0 if a.us else (a.n if a.thai else a.n // 2)
    n_us = 0 if a.thai else (a.n if a.us else a.n - a.n // 2)
    sample = pick_sample(n_th, n_us)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*74}")
    print(f"  ทดลองดึงโลโก้ {len(sample)} ตัว  "
          f"(ไทย {n_th} · สหรัฐ {n_us})")
    print(f"  เก็บรูปไว้ที่ {OUT_DIR}")
    print(f"{'='*74}\n")
    print(f"  {'หุ้น':<13}{'ผล':<26}{'ขนาดเดิม':>12}{'ไฟล์ 64px':>11}  ที่มา")
    print("  " + "-" * 72)

    rows = []
    for tk, name, site in sample:
        try:
            rec = fetch_logo(site)
        except Exception:
            rec = None
        ok, why = is_usable(rec)

        # หุ้นตัวเดียวพังต้องไม่ทำให้ทั้งรอบหยุด
        # ไม่งั้นรันไป 40 ตัวแล้วเจอรูปแปลก ๆ ตัวเดียว เสียเวลาทั้งหมด
        size = 0
        if ok:
            try:
                size = save_webp(rec, OUT_DIR / f"{tk}.webp")
            except Exception as e:
                ok, why = False, f"บันทึกไม่ได้ ({type(e).__name__})"

        mark = "✓ " if ok else "✗ "
        dim = f"{rec['กว้าง']}x{rec['สูง']}" if rec else "-"
        src = rec["ที่มา"] if rec else "-"
        print(f"  {tk:<13}{mark + why:<26}{dim:>12}"
              f"{(f'{size/1024:.1f} KB' if size else '-'):>11}  {src}")

        rows.append({"ticker": tk, "ตลาด": "ไทย" if tk.endswith(".BK") else "สหรัฐ",
                     "ใช้ได้": ok, "เหตุผล": why, "ไบต์": size,
                     "ที่มา": src})

    # ---------- สรุป ----------
    import pandas as pd
    df = pd.DataFrame(rows)
    print(f"\n{'='*74}\n  สรุปผล\n{'='*74}")

    for mk in ("ไทย", "สหรัฐ"):
        d = df[df["ตลาด"] == mk]
        if d.empty:
            continue
        ok = int(d["ใช้ได้"].sum())
        print(f"\n  หุ้น{mk} — ลอง {len(d)} ตัว")
        print(f"    ใช้ได้จริง      {ok:>4} ตัว = {ok/len(d)*100:.0f}%")
        print(f"    ใช้ไม่ได้       {len(d)-ok:>4} ตัว")
        bad = d[~d["ใช้ได้"]]["เหตุผล"].value_counts()
        for r, c in bad.items():
            print(f"       {r:<28}{c:>3} ตัว")

    good = df[df["ใช้ได้"]]
    if len(good):
        avg = good["ไบต์"].mean()
        print(f"\n  ขนาดไฟล์จริง (WebP 64px)")
        print(f"    เฉลี่ย {avg/1024:.1f} KB · "
              f"เล็กสุด {good['ไบต์'].min()/1024:.1f} · "
              f"ใหญ่สุด {good['ไบต์'].max()/1024:.1f} KB")

        rate_th = df[df['ตลาด'] == 'ไทย']['ใช้ได้'].mean() if n_th else 0
        rate_us = df[df['ตลาด'] == 'สหรัฐ']['ใช้ได้'].mean() if n_us else 0
        print(f"\n  ประมาณพื้นที่ถ้าทำจริง (จากขนาดเฉลี่ยข้างบน)")
        for label, n, rate in [("หุ้นไทย 866 ตัว", 866, rate_th or rate_us),
                               ("สหรัฐ 500 ตัวใหญ่", 500, rate_us or rate_th),
                               ("สหรัฐ 2,000 ตัว", 2000, rate_us or rate_th),
                               ("สหรัฐทั้งหมด 10,398", 10398, rate_us or rate_th)]:
            print(f"    {label:<24}{n*rate*avg/1e6:>7.1f} MB  "
                  f"(ได้โลโก้ราว {int(n*rate):,} ตัว)")

    print(f"\n  ที่มาของรูปที่ใช้ได้ :")
    for src, c in good["ที่มา"].value_counts().items():
        print(f"    {src:<24}{c:>4} ตัว")

    print(f"\n  **เปิดดูรูปจริงก่อนตัดสินใจ** — ตาโลโก้เบลอหรือไม่ใช่โลโก้")
    print(f"    open {OUT_DIR}")
    print("\n  ลบผลทดสอบทิ้งได้ทุกเมื่อ ไม่กระทบอะไร :")
    print(f"    rm -rf {OUT_DIR}\n")

    if a.open_dir:
        import subprocess
        subprocess.run(["open", str(OUT_DIR)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
