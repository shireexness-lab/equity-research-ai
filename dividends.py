"""
dividends.py — หุ้นที่กำลังจะปันผล
====================================

ตอบคำถามเดียว : **ตอนนี้มีหุ้นตัวไหนใกล้ขึ้น XD บ้าง จ่ายเท่าไร กี่ %**

XD คืออะไร
-----------
XD (Ex-Dividend) = วันแรกที่ **ซื้อแล้วไม่ได้ปันผลงวดนั้น**
ต้องถือหุ้นอยู่ตั้งแต่ก่อนวัน XD ถึงจะได้เงิน

วัน XD ราคาหุ้นมักลดลงประมาณเงินปันผลที่จ่าย ซึ่ง **ไม่ใช่หุ้นตก**
แต่เป็นการที่มูลค่าเงินสดก้อนนั้นออกจากราคาไปอยู่ในกระเป๋าผู้ถือหุ้น
การซื้อก่อน XD เพื่อ "กินปันผล" จึงไม่ได้กำไรฟรีอย่างที่หลายคนเข้าใจ

ที่มาของวัน XD — ต่างกันระหว่างสองตลาด
----------------------------------------
| ตลาด | แหล่ง | ได้วันล่วงหน้าไหม |
|------|-------|-------------------|
| สหรัฐ | yfinance (`exDividendDate`) | **ได้** — บริษัทประกาศล่วงหน้าเป็นเดือน |
| ไทย  | เว็บ SET | ได้เมื่อบริษัทประกาศแล้ว |
| ไทย  | yfinance | **มักได้แค่ครั้งล่าสุดที่ผ่านมาแล้ว** |

ทุกแถวจึงมีคอลัมน์ **ที่มาของวัน** บอกตรง ๆ ว่าวันนั้นมาจากไหน
ถ้าเป็นการคาดการณ์จากรอบเดิม จะเขียนว่า "คาดการณ์" ไม่ปนกับของจริง

ข้อจำกัดที่ต้องบอกให้ชัด
--------------------------
SET ไม่ได้เปิด API สาธารณะอย่างเป็นทางการ ที่อยู่ที่ใช้ในไฟล์นี้มาจาก
การสังเกตหน้าเว็บ จึงอาจเปลี่ยนได้ทุกเมื่อ ถ้าเรียกไม่สำเร็จระบบจะไม่พัง
แต่จะตกไปใช้การคาดการณ์จากรอบการจ่ายเดิมแทน และบอกไว้ในตาราง

วิธีใช้จาก Terminal
--------------------
    python3 dividends.py --thai              หุ้นไทยที่ใกล้ XD
    python3 dividends.py --us --days 45      หุ้นสหรัฐ 45 วันข้างหน้า
    python3 dividends.py --ทดสอบ-set          ทดสอบว่าดึงจาก SET ได้ไหม
"""

import argparse
import json
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import snapshot

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

SNAP_KEY = "div-{market}"

# คอลัมน์ที่เก็บและแสดง
KEEP = ["ticker", "ชื่อบริษัท", "วัน XD", "อีกกี่วัน", "ที่มาของวัน",
        "เงินปันผล (ต่อหุ้น)", "ราคา", "ผลตอบแทนงวดนี้ (%)",
        "ปันผลรวม 12 เดือน", "ผลตอบแทนต่อปี (%)", "จ่ายกี่ครั้ง/ปี",
        "ปันผลปีก่อน", "ปันผลปกติต่อปี", "ผลตอบแทนปกติ (%)",
        "รอบการจ่าย", "อัตราจ่ายจากกำไร (%)", "กลุ่ม", "ปัญหา"]


# ---------------------------------------------------------------------------
# 1) ตัวช่วยพื้นฐาน
# ---------------------------------------------------------------------------

def _f(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


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


def _epoch_to_date(x):
    """แปลงวินาทีแบบ Unix เป็นวันที่ — yfinance เก็บวัน XD แบบนี้"""
    v = _f(x)
    if not v or v <= 0:
        return None
    try:
        # ค่าเกิน 1e11 แปลว่าเป็นมิลลิวินาที ไม่ใช่วินาที
        if v > 1e11:
            v /= 1000.0
        return datetime.utcfromtimestamp(v).date()
    except (ValueError, OverflowError, OSError):
        return None


# ---------------------------------------------------------------------------
# 2) ดึงปฏิทิน XD ของหุ้นไทยจากเว็บ SET
# ---------------------------------------------------------------------------

# ที่อยู่ที่เป็นไปได้ — ลองไล่ไปทีละอัน อันไหนได้ก่อนใช้อันนั้น
#
# ทำไมต้องมีหลายอัน : SET เปลี่ยนโครงสร้างเว็บเป็นระยะ
# การใส่ไว้หลายทางทำให้ระบบไม่พังทันทีเมื่อทางใดทางหนึ่งเปลี่ยน
SET_XD_URLS = [
    "https://www.set.or.th/api/set/corporate-action/x-calendar"
    "?caType=XD&fromDate={f}&toDate={t}&lang=th",
    "https://www.set.or.th/api/set/xcalendar/list"
    "?caType=XD&fromDate={f}&toDate={t}&lang=th",
    "https://www.set.or.th/api/set/corporate-action/list"
    "?caType=XD&fromDate={f}&toDate={t}&lang=th",
]

# ชื่อฟิลด์ที่ SET อาจใช้ — เก็บหลายชื่อเพราะแต่ละที่อยู่ตอบไม่เหมือนกัน
_SYM_KEYS = ("symbol", "Symbol", "securitySymbol", "stockSymbol")
_DATE_KEYS = ("xDate", "xdDate", "caDate", "date", "exDate", "effectiveDate")
_AMT_KEYS = ("dividend", "dividendAmount", "amount", "value", "rate")


def _pick(d: dict, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def set_xd_calendar(days_ahead: int = 60) -> dict:
    """
    ปฏิทิน XD ของหุ้นไทยจากเว็บ SET

    คืน dict : {"PTT": {"วัน XD": date, "เงินปันผล": 1.4}, ...}
    ถ้าดึงไม่ได้คืน {} เฉย ๆ — ผู้เรียกต้องเผื่อกรณีนี้เสมอ
    """
    today = datetime.now().date()
    end = today + timedelta(days=days_ahead)
    out = {}

    for tmpl in SET_XD_URLS:
        url = tmpl.format(f=today.strftime("%d/%m/%Y"),
                          t=end.strftime("%d/%m/%Y"))
        try:
            js = _get_json(url)
        except Exception:
            continue

        items = js if isinstance(js, list) else None
        if items is None and isinstance(js, dict):
            for k in ("caList", "xCalendarList", "data", "items", "result"):
                if isinstance(js.get(k), list):
                    items = js[k]
                    break
        if not items:
            continue

        for it in items:
            if not isinstance(it, dict):
                continue
            sym = _pick(it, _SYM_KEYS)
            raw_d = _pick(it, _DATE_KEYS)
            if not sym or not raw_d:
                continue
            try:
                d = pd.to_datetime(str(raw_d)[:10], errors="coerce")
                if pd.isna(d):
                    continue
                d = d.date()
            except Exception:
                continue
            if not (today <= d <= end):
                continue
            out[str(sym).strip().upper()] = {
                "วัน XD": d, "เงินปันผล": _f(_pick(it, _AMT_KEYS))}
        if out:
            break
    return out


# ---------------------------------------------------------------------------
# 3) สรุปพฤติกรรมการจ่ายปันผลของหุ้นหนึ่งตัว
# ---------------------------------------------------------------------------

# ระยะห่างเฉลี่ยระหว่างการจ่าย -> รอบการจ่าย
# ใช้ช่วงกว้างเพราะบริษัทไม่ได้จ่ายตรงวันเป๊ะทุกปี
_CADENCE = [(0, 45, "ทุกเดือน", 12), (46, 115, "ทุกไตรมาส", 4),
            (116, 260, "ทุกครึ่งปี", 2), (261, 500, "ปีละครั้ง", 1)]


def _cadence(gap_days):
    for lo, hi, name, n in _CADENCE:
        if lo <= gap_days <= hi:
            return name, n
    return "ไม่สม่ำเสมอ", None


def dividend_profile(data: dict) -> dict:
    """
    สกัดข้อมูลปันผลจากข้อมูลหุ้นที่ดึงมาแล้ว (ไม่ยิงเน็ตเพิ่ม)

    รับ dict จาก data_layer.get_stock_data
    """
    info = data.get("info", {}) or {}
    prices = data.get("prices")

    price = _f(info.get("currentPrice")) or _f(info.get("regularMarketPrice"))
    if price is None and prices is not None and len(prices):
        price = _f(prices["Close"].iloc[-1])

    out = {
        "ราคา": price,
        "กลุ่ม": info.get("sector") or "-",
        "ชื่อบริษัท": info.get("longName") or data.get("ticker"),
        "อัตราจ่ายจากกำไร (%)": (_f(info.get("payoutRatio")) or 0) * 100 or None,
    }

    # ---- ประวัติการจ่ายจากราคาย้อนหลัง ----
    hist = pd.Series(dtype=float)
    if prices is not None and "Dividends" in prices.columns:
        hist = prices["Dividends"]
        hist = hist[hist > 0]

    if len(hist):
        idx = pd.to_datetime(hist.index).tz_localize(None)
        out["เงินปันผล (ต่อหุ้น)"] = float(hist.iloc[-1])

        # ---- รอบการจ่าย : ดูระยะห่างค่ากลางของ 8 ครั้งล่าสุด ----
        # ใช้ค่ากลางเพราะบางปีมีจ่ายพิเศษแทรก ซึ่งจะทำให้ค่าเฉลี่ยเพี้ยน
        n_year = None
        if len(idx) >= 3:
            gaps = pd.Series(idx).diff().dt.days.dropna().tail(8)
            if len(gaps):
                name, n_year = _cadence(float(gaps.median()))
                out["รอบการจ่าย"] = name

        # ---- ปันผลรวมต่อปี ----
        #
        # ทำไมไม่ใช้ "ทุกครั้งที่จ่ายใน 365 วันล่าสุด"
        # ------------------------------------------------
        # PTT จ่ายปีละ 2 ครั้ง (มีนาคม กับ ตุลาคม)
        # แต่หน้าต่าง 365 วันจับได้ 3 ครั้ง เพราะมีนาคมปีนี้กับมีนาคมปีที่แล้ว
        # ห่างกัน 364 วัน จึงเข้าเงื่อนไขทั้งคู่
        # ผลคือปันผลรวมเกินจริงครึ่งหนึ่ง และผลตอบแทนกลายเป็น 9.3%
        # ทั้งที่ความจริงราว 5.9% — ผิดมากพอที่จะทำให้ตัดสินใจผิด
        #
        # จึงใช้ "เอา N ครั้งล่าสุด" โดย N มาจากรอบการจ่ายที่ตรวจได้แทน
        if n_year and len(hist) >= n_year:
            recent = hist.tail(n_year)
            out["ปันผลรวม 12 เดือน"] = float(recent.sum())
            out["จ่ายกี่ครั้ง/ปี"] = int(n_year)

            # ---- ตรวจจับเงินปันผลพิเศษ : เทียบกับ "ปีก่อน" ไม่ใช่ค่ากลาง ----
            #
            # ทำไมต้องเทียบปีต่อปี
            # ---------------------
            # ตอนแรกใช้ "งวดล่าสุดสูงกว่าค่ากลาง 2.5 เท่า" แล้วติดธงผิด
            # KBANK จ่ายงวดใหญ่ปีละครั้ง (12 บาท) + งวดเล็กระหว่างปี (2 บาท)
            # ค่ากลางจึงเป็น 2 และงวดใหญ่ 12 บาทถูกมองว่าผิดปกติ
            # ทั้งที่เป็นรูปแบบการจ่ายปกติของธนาคารไทยหลายแห่ง
            #
            # การเทียบยอด "รวมทั้งปีนี้" กับ "รวมทั้งปีก่อน" ไม่มีปัญหานั้น
            # เพราะทั้งสองปีมีงวดใหญ่และงวดเล็กเหมือนกัน
            prev = hist.iloc[-2 * n_year:-n_year] if len(hist) >= 2 * n_year \
                else pd.Series(dtype=float)
            if len(prev):
                py = float(prev.sum())
                out["ปันผลปีก่อน"] = py
                # เกณฑ์ 1.8 เท่า — ปันผลขึ้นลง 30-50% ตามกำไรเป็นเรื่องปกติ
                # แต่โตเกินเท่าตัวมักแปลว่ามีรายการพิเศษ เช่น ขายสินทรัพย์
                if py > 0 and float(recent.sum()) > py * 1.8:
                    out["รอบการจ่าย"] = \
                        f"{out.get('รอบการจ่าย','-')} · สูงกว่าปีก่อนมาก"
                    out["ปันผลปกติต่อปี"] = py
        else:
            last12 = hist[idx > (idx.max() - pd.Timedelta(days=365))]
            if len(last12):
                out["ปันผลรวม 12 เดือน"] = float(last12.sum())
                out["จ่ายกี่ครั้ง/ปี"] = int(len(last12))

    # ---- ค่าจาก info เป็นตัวสำรอง ----
    if not out.get("ปันผลรวม 12 เดือน"):
        out["ปันผลรวม 12 เดือน"] = (_f(info.get("dividendRate"))
                                    or _f(info.get("trailingAnnualDividendRate")))
    if not out.get("เงินปันผล (ต่อหุ้น)"):
        out["เงินปันผล (ต่อหุ้น)"] = _f(info.get("lastDividendValue"))

    # ---- ผลตอบแทน ----
    # คำนวณเองจากราคาปัจจุบันเสมอ ไม่ใช้ dividendYield จาก Yahoo ตรง ๆ
    # เพราะ Yahoo สลับหน่วยระหว่าง 5.42 (เปอร์เซ็นต์) กับ 0.0542 (สัดส่วน)
    # แล้วแต่ตลาดและแล้วแต่ช่วงเวลา ซึ่งทำให้ตัวเลขผิด 100 เท่าโดยไม่รู้ตัว
    yr = out.get("ปันผลรวม 12 เดือน")
    out["ผลตอบแทนต่อปี (%)"] = (yr / price * 100) if (yr and price) else None
    nm = out.get("ปันผลปกติต่อปี")
    out["ผลตอบแทนปกติ (%)"] = (nm / price * 100) if (nm and price) else None
    d1 = out.get("เงินปันผล (ต่อหุ้น)")
    out["ผลตอบแทนงวดนี้ (%)"] = (d1 / price * 100) if (d1 and price) else None

    # ---- วัน XD จาก yfinance ----
    ex = _epoch_to_date(info.get("exDividendDate"))
    out["_xd_yf"] = ex
    return out


def _predict_next_xd(prices, n_per_year):
    """
    คาดการณ์วัน XD ครั้งถัดไปจากรอบการจ่ายเดิม

    **นี่คือการคาดเดา ไม่ใช่ข้อมูลจริง** ใช้เมื่อยังไม่มีประกาศเท่านั้น
    และต้องติดป้ายให้ผู้ใช้เห็นเสมอว่าเป็นค่าคาดการณ์

    วิธี : เอาวัน XD ครั้งล่าสุด + ระยะห่างค่ากลางของรอบที่ผ่านมา
    ถ้าผลลัพธ์ยังอยู่ในอดีต ให้บวกรอบไปเรื่อย ๆ จนถึงอนาคต
    """
    if prices is None or "Dividends" not in prices.columns:
        return None
    h = prices["Dividends"]
    h = h[h > 0]
    if len(h) < 2:
        return None
    idx = pd.to_datetime(h.index).tz_localize(None)
    gaps = pd.Series(idx).diff().dt.days.dropna().tail(8)
    if not len(gaps):
        return None
    step = float(gaps.median())
    if step <= 0 or step > 500:
        return None
    nxt = idx.max().date()
    today = datetime.now().date()
    for _ in range(6):
        nxt = nxt + timedelta(days=int(round(step)))
        if nxt > today:
            return nxt
    return None


# ---------------------------------------------------------------------------
# 4) สแกนทั้งตลาด
# ---------------------------------------------------------------------------

def scan(tickers, market: str, days_ahead: int = 60, progress=None) -> pd.DataFrame:
    """
    ไล่ดูหุ้นทีละตัว แล้วสรุปว่าตัวไหนใกล้ XD

    ใช้แคชของ data_layer เป็นหลัก จึงเร็วมากถ้าเคยดึงข้อมูลมาแล้ว
    """
    from data_layer import get_stock_data

    xd_set = {}
    if market == "thai":
        try:
            xd_set = set_xd_calendar(days_ahead)
        except Exception:
            xd_set = {}

    today = datetime.now().date()
    rows = []
    total = len(tickers)

    for i, tk in enumerate(tickers, 1):
        row = {"ticker": tk, "ปัญหา": ""}
        try:
            data = get_stock_data(tk)
            p = dividend_profile(data)
            row.update({k: v for k, v in p.items() if not k.startswith("_")})

            # ---- เลือกวัน XD ตามลำดับความน่าเชื่อถือ ----
            sym = tk.replace(".BK", "").upper()
            xd, src = None, ""

            if sym in xd_set:                      # 1. SET ประกาศแล้ว
                xd = xd_set[sym]["วัน XD"]
                src = "SET ประกาศแล้ว"
                if xd_set[sym].get("เงินปันผล"):
                    row["เงินปันผล (ต่อหุ้น)"] = xd_set[sym]["เงินปันผล"]
                    pr = row.get("ราคา")
                    if pr:
                        row["ผลตอบแทนงวดนี้ (%)"] = \
                            xd_set[sym]["เงินปันผล"] / pr * 100
            elif p.get("_xd_yf") and p["_xd_yf"] >= today:   # 2. Yahoo ล่วงหน้า
                xd = p["_xd_yf"]
                src = "ประกาศแล้ว"
            else:                                   # 3. คาดการณ์จากรอบเดิม
                xd = _predict_next_xd(data.get("prices"),
                                      row.get("จ่ายกี่ครั้ง/ปี"))
                src = "คาดการณ์จากรอบเดิม" if xd else ""

            row["วัน XD"] = xd.strftime("%Y-%m-%d") if xd else None
            row["อีกกี่วัน"] = (xd - today).days if xd else None
            row["ที่มาของวัน"] = src or "ไม่ทราบ"
        except Exception as e:
            row["ปัญหา"] = f"{type(e).__name__}: {str(e)[:60]}"

        rows.append(row)
        if progress:
            try:
                progress(i, total, tk)
            except Exception:
                pass

    df = pd.DataFrame(rows)
    for c in KEEP:
        if c not in df.columns:
            df[c] = None
    return df[KEEP]


def upcoming(df: pd.DataFrame, days: int = 60, min_yield=None,
             only_confirmed=False) -> pd.DataFrame:
    """กรองเฉพาะตัวที่ XD อยู่ในช่วงข้างหน้าที่กำหนด เรียงตามวันที่ใกล้ที่สุด"""
    if df is None or df.empty:
        return pd.DataFrame(columns=KEEP)
    d = df[df["ปัญหา"].eq("")] if "ปัญหา" in df.columns else df
    n = pd.to_numeric(d["อีกกี่วัน"], errors="coerce")
    d = d[n.between(0, days)]
    if only_confirmed:
        d = d[d["ที่มาของวัน"].astype(str).str.contains("ประกาศ")]
    if min_yield:
        y = pd.to_numeric(d["ผลตอบแทนงวดนี้ (%)"], errors="coerce").fillna(0)
        d = d[y >= min_yield]
    return d.sort_values("อีกกี่วัน", na_position="last").reset_index(drop=True)


def save(market: str, df: pd.DataFrame):
    snapshot.save(SNAP_KEY.format(market=market), df, to_repo=True,
                  extra={"ตลาด": market, "จำนวน": len(df)})


def load(market: str):
    return snapshot.info(SNAP_KEY.format(market=market))


# ---------------------------------------------------------------------------
# 5) เรียกจาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="หุ้นที่กำลังจะปันผล")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--thai", action="store_true")
    g.add_argument("--us", action="store_true")
    p.add_argument("--days", type=int, default=60, help="มองไปข้างหน้ากี่วัน")
    p.add_argument("--limit", type=int, default=None, help="จำกัดจำนวนหุ้นที่สแกน")
    p.add_argument("--ทดสอบ-set", dest="test_set", action="store_true",
                   help="ทดสอบว่าดึงปฏิทิน XD จากเว็บ SET ได้ไหม")
    a = p.parse_args()

    if a.test_set:
        print("\nทดสอบการดึงปฏิทิน XD จากเว็บ SET")
        print("=" * 66)
        today = datetime.now().date()
        end = today + timedelta(days=a.days)
        ok_any = False
        for tmpl in SET_XD_URLS:
            url = tmpl.format(f=today.strftime("%d/%m/%Y"),
                              t=end.strftime("%d/%m/%Y"))
            print(f"\n  {url}")
            try:
                js = _get_json(url)
                head = json.dumps(js, ensure_ascii=False)[:220]
                print(f"    สำเร็จ — {head}")
                ok_any = True
            except Exception as e:
                print(f"    ล้มเหลว : {type(e).__name__} {str(e)[:90]}")
        print("\n" + "=" * 66)
        cal = set_xd_calendar(a.days)
        print(f"  ปฏิทินที่อ่านได้ : {len(cal):,} รายการ")
        for s, v in list(cal.items())[:10]:
            print(f"    {s:<10} {v['วัน XD']}  {v.get('เงินปันผล')}")
        if not ok_any:
            print("\n  ดึงจาก SET ไม่ได้เลย — ระบบจะใช้การคาดการณ์จากรอบเดิมแทน")
            print("  (ยังใช้งานได้ แต่วันที่จะเป็นค่าประมาณ ต้องตรวจกับ SET ก่อนซื้อ)")
        return 0

    if a.thai:
        from tickers import thai_universe
        uni, market = list(thai_universe()), "thai"
    elif a.us:
        from tickers import us_tickers
        uni, market = list(us_tickers().keys()), "us"
    else:
        p.error("ต้องระบุ --thai หรือ --us")

    if a.limit:
        uni = uni[:a.limit]

    print(f"\n  สแกนหุ้น {len(uni):,} ตัว เพื่อหาตัวที่ใกล้ XD ภายใน {a.days} วัน\n")

    def bar(i, total, tk):
        w = 30
        f = int(w * i / total)
        sys.stdout.write(f"\r  [{'█'*f}{'·'*(w-f)}] {i:,}/{total:,}  {tk:<14}")
        sys.stdout.flush()

    df = scan(uni, market, a.days, progress=bar)
    print()
    save(market, df)

    up = upcoming(df, a.days)
    print(f"\n  ใกล้ XD ภายใน {a.days} วัน : {len(up):,} ตัว")
    if len(up):
        cols = ["ticker", "วัน XD", "อีกกี่วัน", "ที่มาของวัน",
                "เงินปันผล (ต่อหุ้น)", "ผลตอบแทนงวดนี้ (%)",
                "ผลตอบแทนต่อปี (%)", "จ่ายกี่ครั้ง/ปี"]
        print(up.head(30)[cols].to_string(index=False))
        n_conf = up["ที่มาของวัน"].astype(str).str.contains("ประกาศ").sum()
        print(f"\n  ประกาศแล้วจริง {n_conf:,} ตัว · "
              f"คาดการณ์ {len(up)-n_conf:,} ตัว")
        print("  ตัวที่เป็นคาดการณ์ต้องไปตรวจกับประกาศของ SET ก่อนตัดสินใจเสมอ")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
