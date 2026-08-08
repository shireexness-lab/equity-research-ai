"""
news.py — ข่าวและปฏิทินสิทธิประโยชน์รายตัว (เน้นหุ้นไทย)
==========================================================
หน้าที่ : เติม "เรื่องราว" ให้ตัวเลข — XD เมื่อไร ปันผลเท่าไร มีข่าวอะไรบ้าง

แบ่งเป็น 2 ส่วนที่ความน่าเชื่อถือต่างกันมาก
---------------------------------------------

**ส่วนที่ 1 — ปฏิทินสิทธิประโยชน์ (เชื่อถือได้)**
XD / ปันผล / แตกพาร์ ดึงจาก yfinance ซึ่งเก็บเป็นข้อมูลมีโครงสร้าง
ไม่ต้องแกะหน้าเว็บ จึงไม่พังเมื่อเว็บเปลี่ยนหน้าตา

**ส่วนที่ 2 — หัวข้อข่าว (ไม่แน่นอน)**
ข่าวหุ้นไทยหายากกว่าหุ้นสหรัฐมาก และ SET ไม่มี API สาธารณะที่ประกาศไว้เป็นทางการ
โค้ดนี้จึงลองหลายทางตามลำดับ และถ้าไม่ได้เลย **จะให้ลิงก์ไปหน้า SET โดยตรง**
ไม่ปล่อยให้ผู้ใช้เจอหน้าว่างโดยไม่รู้จะไปต่อทางไหน

ทำไมต้องมีทางถอยเสมอ
---------------------
การดึงข่าวจากเว็บที่ไม่ได้เปิด API ไว้ จะพังในวันที่เจ้าของเว็บปรับหน้าตา
ซึ่งเป็นเรื่องที่เกิดขึ้นแน่นอน ไม่ใช่แค่อาจจะ
ระบบที่ดีต้องยอมรับว่าส่วนนี้พังได้ แล้วออกแบบให้ยังใช้งานต่อได้

วิธีใช้
-------
    python3 news.py PTT.BK
    python3 news.py ADVANC.BK --limit 15
"""

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import pandas as pd

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"

SET_NEWS_PAGE = "https://www.set.or.th/th/market/product/stock/quote/{sym}/news"
SET_FACT_PAGE = "https://www.set.or.th/th/market/product/stock/quote/{sym}/factsheet"


def is_thai(ticker: str) -> bool:
    return str(ticker).upper().endswith(".BK")


def base_symbol(ticker: str) -> str:
    """PTT.BK -> PTT — SET ใช้ชื่อย่อไม่มี .BK"""
    return str(ticker).upper().replace(".BK", "").strip()


def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get_json(url: str, timeout=12):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json",
        "Referer": "https://www.set.or.th/"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# ส่วนที่ 1 — ปฏิทินสิทธิประโยชน์
# ---------------------------------------------------------------------------

def dividend_calendar(ticker: str, years: int = 5) -> dict:
    """
    ประวัติปันผลและวัน XD

    XD (Ex-Dividend) = วันที่ซื้อแล้ว **ไม่ได้** ปันผลงวดนั้น
    ใครถือหุ้นอยู่ก่อนวันนี้ถึงจะได้ — ราคาหุ้นมักลดลงประมาณเงินปันผลในวัน XD
    ซึ่งไม่ใช่การที่หุ้น "ตก" แต่เป็นการที่มูลค่าปันผลออกจากราคาไป
    """
    import yfinance as yf

    out = {"ticker": ticker, "ปันผลย้อนหลัง": pd.DataFrame(), "ปัญหา": ""}
    try:
        t = yf.Ticker(ticker)
        div = t.dividends
        info = t.info or {}
        splits = t.splits
    except Exception as e:
        out["ปัญหา"] = f"{type(e).__name__}: {str(e)[:70]}"
        return out

    if div is not None and len(div):
        cut = pd.Timestamp.now(tz=div.index.tz) - pd.DateOffset(years=years)
        d = div[div.index >= cut]
        if len(d):
            df = d.reset_index()
            df.columns = ["วัน XD", "เงินปันผล (ต่อหุ้น)"]
            df["วัน XD"] = pd.to_datetime(df["วัน XD"]).dt.strftime("%Y-%m-%d")
            out["ปันผลย้อนหลัง"] = df.sort_values("วัน XD", ascending=False)
            out["รวม 12 เดือน"] = float(
                d[d.index >= pd.Timestamp.now(tz=d.index.tz) - pd.DateOffset(years=1)].sum())
            out["จำนวนครั้ง/ปี"] = round(len(d) / max(years, 1), 1)

    # วัน XD ครั้งถัดไปหรือครั้งล่าสุด
    ex = info.get("exDividendDate")
    if ex:
        try:
            dt = datetime.utcfromtimestamp(int(ex))
            out["XD ล่าสุด/ถัดไป"] = dt.strftime("%Y-%m-%d")
            days = (dt.date() - datetime.utcnow().date()).days
            out["อีกกี่วัน"] = days
        except Exception:
            pass

    y = info.get("dividendYield")
    if y is not None:
        out["ปันผลตอบแทน (%)"] = float(y)

    if splits is not None and len(splits):
        s = splits.reset_index()
        s.columns = ["วันที่", "อัตราส่วน"]
        s["วันที่"] = pd.to_datetime(s["วันที่"]).dt.strftime("%Y-%m-%d")
        out["แตกพาร์/รวมพาร์"] = s.sort_values("วันที่", ascending=False).head(8)

    return out


# ---------------------------------------------------------------------------
# ส่วนที่ 2 — หัวข้อข่าว
# ---------------------------------------------------------------------------

def _from_yfinance(ticker: str, limit: int):
    """ข่าวที่ yfinance แนบมากับหุ้น — โครงสร้างเปลี่ยนบ่อย จึงต้องรับหลายแบบ"""
    import yfinance as yf
    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        return []

    out = []
    for it in items[:limit]:
        # yfinance เคยคืนเป็น {title, publisher, link, providerPublishTime}
        # รุ่นใหม่ห่อไว้ใน {"content": {...}} จึงต้องรองรับทั้งสองแบบ
        c = it.get("content") if isinstance(it.get("content"), dict) else it
        title = c.get("title") or it.get("title")
        if not title:
            continue
        link = (c.get("canonicalUrl", {}).get("url") if isinstance(c.get("canonicalUrl"), dict)
                else c.get("clickThroughUrl", {}).get("url")
                if isinstance(c.get("clickThroughUrl"), dict) else None) \
            or it.get("link") or ""
        pub = (c.get("provider", {}).get("displayName")
               if isinstance(c.get("provider"), dict) else None) \
            or it.get("publisher") or "Yahoo Finance"
        ts = it.get("providerPublishTime") or c.get("pubDate") or c.get("displayTime")
        when = ""
        if isinstance(ts, (int, float)):
            when = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        elif isinstance(ts, str):
            when = ts[:10]
        out.append({"วันที่": when, "หัวข้อ": title, "ที่มา": pub, "ลิงก์": link})
    return out


def _from_set(ticker: str, limit: int, days_back: int = 180):
    """
    ข่าวจากเว็บตลาดหลักทรัพย์

    หมายเหตุตรงไปตรงมา : SET ไม่ได้ประกาศ API สาธารณะไว้อย่างเป็นทางการ
    ที่อยู่ที่ใช้ตรงนี้มาจากการสังเกตหน้าเว็บ จึงอาจเปลี่ยนได้ทุกเมื่อ
    ถ้าเรียกไม่สำเร็จให้ถือว่าเป็นเรื่องปกติ ไม่ใช่บั๊ก และตกไปใช้ลิงก์แทน
    """
    sym = base_symbol(ticker)
    today = datetime.now()
    since = today - timedelta(days=days_back)
    urls = [
        "https://www.set.or.th/api/set/news/search?" + urllib.parse.urlencode({
            "symbol": sym, "fromDate": since.strftime("%d/%m/%Y"),
            "toDate": today.strftime("%d/%m/%Y"), "lang": "th"}),
        f"https://www.set.or.th/api/set/news/{sym}/list?lang=th",
    ]
    for url in urls:
        try:
            js = _get_json(url)
        except Exception:
            continue
        items = None
        for key in ("newsInfoList", "newsList", "data", "items"):
            if isinstance(js, dict) and isinstance(js.get(key), list):
                items = js[key]
                break
        if items is None and isinstance(js, list):
            items = js
        if not items:
            continue

        out = []
        for it in items[:limit]:
            if not isinstance(it, dict):
                continue
            title = (it.get("headline") or it.get("title") or it.get("name") or "")
            if not title:
                continue
            when = str(it.get("datetime") or it.get("newsDateTime")
                       or it.get("date") or "")[:10]
            url_ = it.get("url") or it.get("newsUrl") or ""
            if url_ and url_.startswith("/"):
                url_ = "https://www.set.or.th" + url_
            out.append({"วันที่": when, "หัวข้อ": title.strip(),
                        "ที่มา": "SET", "ลิงก์": url_ or SET_NEWS_PAGE.format(sym=sym)})
        if out:
            return out
    return []


def headlines(ticker: str, limit: int = 12) -> dict:
    """
    รวมหัวข้อข่าวจากทุกแหล่งที่ทำได้

    คืน dict :
      รายการ  = list ของข่าว
      ที่มา    = แหล่งที่ได้ผลจริง
      ลิงก์SET = ลิงก์ไปหน้าข่าวของ SET (ใช้เสมอ ไม่ว่าจะดึงข่าวได้หรือไม่)
    """
    sym = base_symbol(ticker)
    out = {"ticker": ticker, "รายการ": [], "ที่มา": [],
           "ลิงก์ SET": SET_NEWS_PAGE.format(sym=sym) if is_thai(ticker) else "",
           "ลิงก์ Factsheet": SET_FACT_PAGE.format(sym=sym) if is_thai(ticker) else ""}

    if is_thai(ticker):
        got = _from_set(ticker, limit)
        if got:
            out["รายการ"] += got
            out["ที่มา"].append("SET")

    if len(out["รายการ"]) < limit:
        got = _from_yfinance(ticker, limit - len(out["รายการ"]))
        if got:
            out["รายการ"] += got
            out["ที่มา"].append("Yahoo Finance")

    # ข่าวเก่ากว่าอยู่ล่าง · ข่าวไม่มีวันที่ไปท้ายสุด
    out["รายการ"].sort(key=lambda r: r.get("วันที่") or "", reverse=True)
    return out


# ---------------------------------------------------------------------------
# ใช้จาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="ข่าวและปฏิทินสิทธิประโยชน์รายตัว")
    p.add_argument("ticker")
    p.add_argument("--limit", type=int, default=12)
    a = p.parse_args()
    t = a.ticker.upper()

    print(f"\n{'='*70}\n  {t}\n{'='*70}")

    d = dividend_calendar(t)
    print("\n  [ปฏิทินสิทธิประโยชน์]")
    if d.get("ปัญหา"):
        print(f"    ดึงไม่สำเร็จ: {d['ปัญหา']}")
    else:
        if d.get("XD ล่าสุด/ถัดไป"):
            days = d.get("อีกกี่วัน")
            when = ("ผ่านมาแล้ว {} วัน".format(-days) if days is not None and days < 0
                    else "อีก {} วัน".format(days) if days is not None else "")
            print(f"    วัน XD          : {d['XD ล่าสุด/ถัดไป']}  {when}")
        if d.get("ปันผลตอบแทน (%)") is not None:
            print(f"    ปันผลตอบแทน    : {d['ปันผลตอบแทน (%)']:.2f}%")
        if d.get("รวม 12 เดือน"):
            print(f"    ปันผล 12 เดือน  : {d['รวม 12 เดือน']:.4f} ต่อหุ้น"
                  f"  ({d.get('จำนวนครั้ง/ปี','-')} ครั้ง/ปี)")
        hist = d.get("ปันผลย้อนหลัง")
        if hist is not None and len(hist):
            print("\n    ปันผลย้อนหลัง 5 ปี:")
            for _, r in hist.head(10).iterrows():
                print(f"      {r['วัน XD']}   {r['เงินปันผล (ต่อหุ้น)']:.4f}")
        sp = d.get("แตกพาร์/รวมพาร์")
        if sp is not None and len(sp):
            print("\n    แตกพาร์/รวมพาร์:")
            for _, r in sp.iterrows():
                print(f"      {r['วันที่']}   {r['อัตราส่วน']}")

    n = headlines(t, a.limit)
    print(f"\n  [หัวข้อข่าว]  แหล่งที่ได้ผล: {', '.join(n['ที่มา']) or 'ไม่มี'}")
    if n["รายการ"]:
        for it in n["รายการ"]:
            print(f"    {it['วันที่'] or '—':<12} {it['หัวข้อ'][:70]}")
            print(f"    {'':<12} ({it['ที่มา']})")
    else:
        print("    ดึงข่าวอัตโนมัติไม่ได้ — เปิดดูที่ SET โดยตรงได้ที่ลิงก์ด้านล่าง")
    if n.get("ลิงก์ SET"):
        print(f"\n    ข่าวทั้งหมดที่ SET : {n['ลิงก์ SET']}")
        print(f"    Factsheet         : {n['ลิงก์ Factsheet']}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
