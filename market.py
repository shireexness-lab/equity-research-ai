"""
market.py — ดึงข้อมูลทั้งตลาดแบบรวดเดียว
==========================================
หน้าที่ : ทำให้ "คัดกรองหุ้นทั้งตลาด" เป็นไปได้จริงในไม่กี่นาที

ปัญหาของวิธีเดิม
----------------
ดึงทีละตัวด้วย yfinance : 10,398 ตัว x 1.5 วิ / 8 เส้น = 22 นาที
และมีโอกาสสูงที่จะโดนบล็อกกลางทาง เพราะยิงคำขอเป็นหมื่นครั้ง

วิธีใหม่ — ใช้ API ที่คืนข้อมูล "ทั้งตลาด" ในคำขอเดียว
-------------------------------------------------------
1. **งบการเงิน** : SEC frames API
   https://data.sec.gov/api/xbrl/frames/us-gaap/Assets/USD/CY2025Q1I.json
   คืนค่า Assets ของ **ทุกบริษัทในตลาด** ในคำขอเดียว
   ใช้ 7 คำขอ ก็ได้ครบทุกตัวเลขที่ต้องใช้ (แทนที่จะเป็น 10,398 คำขอ)

2. **ราคาหุ้น** : yfinance ดาวน์โหลดทีละหลายร้อยตัว
   yf.download(["AAPL","MSFT",...]) รับได้ครั้งละ ~200 ตัว

ผลลัพธ์ : จาก 22 นาที เหลือราว 3–5 นาที และจำนวนคำขอลดจากหมื่นเหลือหลักสิบ

ข้อจำกัด
--------
วิธีนี้ใช้ได้เฉพาะ **หุ้นสหรัฐ** เพราะ SEC frames มีเฉพาะบริษัทที่ยื่นงบต่อ SEC
หุ้นไทยยังต้องดึงทีละตัว (แต่มีไม่กี่ร้อยตัว จึงใช้เวลาไม่นาน)

วิธีใช้จาก Terminal
-------------------
    python3 market.py                 # ดึงภาพรวมตลาดสหรัฐทั้งตลาด
    python3 market.py --csv us.csv
"""

import argparse
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd

FRAMES = "https://data.sec.gov/api/xbrl/frames/{tax}/{tag}/{unit}/{period}.json"

# ตัวเลขที่ต้องใช้ + tag สำรองเผื่อบริษัทใช้ชื่อต่างกัน
# kind : "duration" = ยอดสะสมทั้งปี (รายได้ กำไร)
#        "instant"  = ยอด ณ วันสิ้นงวด (สินทรัพย์ ส่วนของผู้ถือหุ้น)
METRICS = [
    ("รายได้", "duration", "us-gaap", "USD",
     ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]),
    ("กำไรสุทธิ", "duration", "us-gaap", "USD", ["NetIncomeLoss"]),
    ("กำไรขั้นต้น", "duration", "us-gaap", "USD", ["GrossProfit"]),
    ("OCF", "duration", "us-gaap", "USD",
     ["NetCashProvidedByUsedInOperatingActivities"]),
    ("CapEx", "duration", "us-gaap", "USD",
     ["PaymentsToAcquirePropertyPlantAndEquipment"]),
    ("ส่วนของผู้ถือหุ้น", "instant", "us-gaap", "USD", ["StockholdersEquity"]),
    ("สินทรัพย์รวม", "instant", "us-gaap", "USD", ["Assets"]),
    ("หนี้สินรวม", "instant", "us-gaap", "USD", ["Liabilities"]),
    ("จำนวนหุ้น", "instant", "dei", "shares",
     ["EntityCommonStockSharesOutstanding"]),
]


# ---------------------------------------------------------------------------
# ชั้นที่ 1 : งบการเงินทั้งตลาดจาก SEC
# ---------------------------------------------------------------------------

def _periods(kind: str, back: int = 3):
    """
    สร้างรายชื่อช่วงเวลาที่จะลอง ไล่จากใหม่ไปเก่า

    ทำไมต้องลองหลายช่วง : งบปีล่าสุดอาจยังยื่นไม่ครบทุกบริษัท
    ถ้าปีล่าสุดข้อมูลน้อย ให้ถอยไปปีก่อนหน้าที่ครบกว่า
    """
    y = datetime.now().year
    out = []
    for i in range(back + 1):
        yy = y - i
        if kind == "duration":
            out.append(f"CY{yy}")
        else:
            out += [f"CY{yy}Q{q}I" for q in (4, 3, 2, 1)]
    return out


def fetch_frame(tag, kind, tax="us-gaap", unit="USD", back=3, min_points=500):
    """
    ดึงค่าของ tag หนึ่งสำหรับ **ทุกบริษัทในตลาด**

    คืน (dict {cik: ค่า}, ช่วงเวลาที่ใช้จริง)
    ถ้าช่วงไหนมีข้อมูลน้อยกว่า min_points จะถือว่ายังไม่ครบ แล้วลองช่วงถัดไป
    """
    from edgar_layer import _get_json
    for period in _periods(kind, back):
        url = FRAMES.format(tax=tax, tag=tag, unit=unit, period=period)
        try:
            js = _get_json(url, timeout=120)
        except Exception:
            continue
        data = js.get("data") or []
        if len(data) < min_points:
            continue
        out = {}
        for d in data:
            cik = d.get("cik")
            val = d.get("val")
            if cik is None or val is None:
                continue
            out[int(cik)] = float(val)
        if out:
            return out, period
    return {}, None


def us_fundamentals(progress=None) -> pd.DataFrame:
    """
    ดึงงบการเงินของหุ้นสหรัฐทั้งตลาด — ใช้เพียง ~8 คำขอ

    คืน DataFrame ที่ index เป็น CIK
    """
    frames, used = {}, {}
    total = len(METRICS)
    for i, (name, kind, tax, unit, tags) in enumerate(METRICS, 1):
        if progress:
            progress(i, total, name)
        merged = {}
        for tag in tags:
            vals, period = fetch_frame(tag, kind, tax, unit)
            if vals:
                # tag แรกในรายการชนะ จึงใส่ค่าจาก tag สำรองก่อนแล้วให้ตัวหลักทับ
                merged = {**vals, **merged}
                used.setdefault(name, []).append(f"{tag}@{period}")
        frames[name] = merged

    df = pd.DataFrame(frames)
    df.index.name = "cik"
    df.attrs["ที่มาของข้อมูล"] = used
    return df


# ---------------------------------------------------------------------------
# ชั้นที่ 2 : ราคาหุ้นแบบดาวน์โหลดทีละหลายร้อยตัว
# ---------------------------------------------------------------------------

def bulk_prices(tickers, batch=180, progress=None) -> dict:
    """
    ดึงราคาปิดล่าสุดของหุ้นจำนวนมาก โดยแบ่งเป็นชุด ๆ ละ ~180 ตัว

    เร็วกว่าดึงทีละตัวราว 100 เท่า เพราะ yfinance รวมหลายตัวไว้ในคำขอเดียวได้
    """
    import yfinance as yf
    out = {}
    tickers = list(dict.fromkeys(tickers))
    chunks = [tickers[i:i + batch] for i in range(0, len(tickers), batch)]
    for i, ch in enumerate(chunks, 1):
        if progress:
            progress(i, len(chunks), f"ราคา {len(out):,} ตัว")
        try:
            px = yf.download(ch, period="5d", interval="1d", progress=False,
                             auto_adjust=False, threads=True)
        except Exception:
            continue
        if px is None or px.empty:
            continue
        try:
            close = px["Close"]
        except Exception:
            continue
        if isinstance(close, pd.Series):          # กรณีมีตัวเดียวในชุด
            close = close.to_frame(name=ch[0])
        for t in close.columns:
            s = close[t].dropna()
            if len(s):
                out[str(t)] = float(s.iloc[-1])
        time.sleep(0.3)
    return out


# ---------------------------------------------------------------------------
# ประกอบเป็นตารางคัดกรองทั้งตลาด
# ---------------------------------------------------------------------------

def us_market_snapshot(progress=None) -> pd.DataFrame:
    """
    ภาพรวมหุ้นสหรัฐทั้งตลาด พร้อมอัตราส่วนที่ใช้คัดกรอง

    ขั้นตอน
      1. งบการเงินทั้งตลาดจาก SEC frames  (~8 คำขอ)
      2. แผนที่ CIK -> ticker จากทะเบียน SEC (1 คำขอ)
      3. ราคาปิดล่าสุดแบบดาวน์โหลดทีละชุด  (~60 คำขอ)
      4. คำนวณ P/E, P/BV, ROE, FCF Yield เอง
    """
    from edgar_layer import TICKER_MAP_URL, _cached, _get_json

    fund = us_fundamentals(progress=progress)
    if fund.empty:
        raise RuntimeError("ดึงงบการเงินจาก SEC ไม่สำเร็จ")

    table = _cached("ticker_map", 24 * 30, lambda: _get_json(TICKER_MAP_URL))
    cik2t, names = {}, {}
    for row in table.values():
        cik = int(row.get("cik_str", 0))
        t = str(row.get("ticker", "")).upper().strip()
        if cik and t and cik not in cik2t:      # 1 บริษัทอาจมีหลายชนิดหุ้น เอาตัวแรก
            cik2t[cik] = t
            names[cik] = str(row.get("title", ""))

    fund = fund[fund.index.isin(cik2t)].copy()
    fund["ticker"] = [cik2t[c] for c in fund.index]
    fund["ชื่อบริษัท"] = [names.get(c, "") for c in fund.index]

    px = bulk_prices(list(fund["ticker"]), progress=progress)
    fund["ราคา"] = [px.get(t) for t in fund["ticker"]]
    fund = fund[fund["ราคา"].notna()].copy()

    sh = pd.to_numeric(fund.get("จำนวนหุ้น"), errors="coerce")
    ni = pd.to_numeric(fund.get("กำไรสุทธิ"), errors="coerce")
    eq = pd.to_numeric(fund.get("ส่วนของผู้ถือหุ้น"), errors="coerce")
    rev = pd.to_numeric(fund.get("รายได้"), errors="coerce")
    ocf = pd.to_numeric(fund.get("OCF"), errors="coerce")
    capex = pd.to_numeric(fund.get("CapEx"), errors="coerce").abs()
    gp = pd.to_numeric(fund.get("กำไรขั้นต้น"), errors="coerce")
    assets = pd.to_numeric(fund.get("สินทรัพย์รวม"), errors="coerce")
    liab = pd.to_numeric(fund.get("หนี้สินรวม"), errors="coerce")

    mcap = fund["ราคา"] * sh
    fcf = ocf - capex.fillna(0)

    def div(a, b):
        b = b.replace(0, np.nan)
        return (a / b).replace([np.inf, -np.inf], np.nan)

    out = pd.DataFrame({
        "ticker": fund["ticker"],
        "ชื่อบริษัท": fund["ชื่อบริษัท"],
        "ราคา": fund["ราคา"],
        "มูลค่าตลาด (ล้าน)": mcap / 1e6,
        "P/E": div(mcap, ni),
        "P/BV": div(mcap, eq),
        "P/S": div(mcap, rev),
        "ROE (%)": div(ni, eq) * 100,
        "อัตรากำไรขั้นต้น (%)": div(gp, rev) * 100,
        "อัตรากำไรสุทธิ (%)": div(ni, rev) * 100,
        "FCF Yield (%)": div(fcf, mcap) * 100,
        "หนี้สิน/สินทรัพย์ (%)": div(liab, assets) * 100,
        "กลุ่ม": "-",
        "สกุลเงิน": "USD",
        "ปันผล (%)": np.nan,
        "EV/EBITDA": np.nan,
        "D/E": div(liab, eq),
        "โตรายได้ (%)": np.nan,
        "ปัญหา": "",
    }).reset_index(drop=True)

    out.attrs["ที่มาของข้อมูล"] = fund.attrs.get("ที่มาของข้อมูล", {})
    return out.sort_values("มูลค่าตลาด (ล้าน)", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# รันจาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="ดึงภาพรวมหุ้นสหรัฐทั้งตลาด")
    p.add_argument("--csv", help="บันทึกเป็นไฟล์ CSV")
    p.add_argument("--top", type=int, default=40, help="แสดงกี่อันดับ")
    args = p.parse_args()

    def show(i, total, what):
        print(f"  [{i}/{total}] {what} ...", flush=True)

    print("\nกำลังดึงข้อมูลทั้งตลาดสหรัฐ — คาดว่าใช้เวลา 3–6 นาที\n")
    try:
        df = us_market_snapshot(progress=show)
    except Exception as e:
        print(f"\n[ไม่สำเร็จ] {type(e).__name__}: {e}\n", file=sys.stderr)
        return 1

    print(f"\nได้ข้อมูล {len(df):,} บริษัท")
    print("\nที่มาของตัวเลขแต่ละรายการ :")
    for k, v in (df.attrs.get("ที่มาของข้อมูล") or {}).items():
        print(f"  {k:<20} {', '.join(v)}")

    cols = ["ticker", "ชื่อบริษัท", "ราคา", "P/E", "P/BV", "ROE (%)",
            "FCF Yield (%)", "มูลค่าตลาด (ล้าน)"]
    print()
    with pd.option_context("display.width", 200):
        print(df[cols].head(args.top).to_string(index=False))

    if args.csv:
        df.to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"\nบันทึกไฟล์แล้ว : {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
