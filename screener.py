"""
screener.py — สแกนหาหุ้นที่ราคาต่ำกว่ามูลค่าที่ประเมินได้
============================================================
หน้าที่ : รันการวิเคราะห์กับหุ้นหลายตัว แล้วเรียงลำดับตามส่วนลดจากมูลค่า

⚠️ ข้อควรรู้ก่อนใช้ — สำคัญมาก
------------------------------
1. **ช้า** : หุ้นแต่ละตัวใช้เวลา 20–40 วินาที (ต้องดึงงบย้อนหลัง 15 ปี)
   สแกน 20 ตัว ≈ 8–12 นาที ครั้งแรก ครั้งต่อไปเร็วเพราะมี cache

2. **"ส่วนลดเยอะ" ไม่เท่ากับ "หุ้นดี"** :
   หุ้นที่ราคาต่ำกว่ามูลค่ามาก ๆ มักมีเหตุผล เช่น กำไรกำลังถดถอย
   หรือธุรกิจกำลังถูกแทนที่ ระบบนี้บอกได้แค่ว่า "ตัวเลขในอดีตกับราคาวันนี้ไม่ตรงกัน"
   ไม่ได้บอกว่าทำไม

3. **ดูคะแนนความน่าเชื่อถือควบคู่เสมอ** :
   หุ้นที่ได้ส่วนลด 60% แต่ความน่าเชื่อถือ "ต่ำ" มีค่าน้อยกว่า
   หุ้นที่ได้ส่วนลด 20% แต่ความน่าเชื่อถือ "สูง"

วิธีใช้จาก Terminal
-------------------
    python3 screener.py AAPL MSFT GOOGL
    python3 screener.py --list thai        # หุ้นไทยชุดตั้งต้น
    python3 screener.py --list us          # หุ้นสหรัฐยอดนิยม
    python3 screener.py --list thai --rf 0.025 --max 15
"""

import argparse
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd

ZONE_ORDER = ["Strong Buy", "Buy", "Hold", "Reduce", "Sell"]


# ===========================================================================
# ชั้นที่ 1 — คัดกรองเร็ว (ใช้ได้กับทั้งตลาด)
#
# ดึงเฉพาะ "ตัวเลขสรุป" ที่ yfinance เตรียมไว้ให้แล้ว (P/E, P/BV, ROE ฯลฯ)
# ไม่ดึงงบย้อนหลัง ไม่ทำ DCF จึงเร็วกว่าชั้นที่ 2 ราว 20 เท่า
#
# ทำไมต้องมี 2 ชั้น :
#   วิเคราะห์เต็มรูปแบบหุ้นสหรัฐทั้งตลาด = 87 ชั่วโมง + โหลดข้อมูล 82 GB
#   จึงต้องคัดจากหมื่นตัวให้เหลือหลักสิบก่อน แล้วค่อยวิเคราะห์ลึก
#   นี่คือวิธีที่ระบบคัดกรองหุ้นมืออาชีพใช้กันจริง
# ===========================================================================

QUICK_COLS = ["ticker", "ชื่อบริษัท", "กลุ่ม", "สกุลเงิน", "ราคา",
              "มูลค่าตลาด (ล้าน)", "P/E", "P/BV", "P/S", "EV/EBITDA",
              "ROE (%)", "อัตรากำไรขั้นต้น (%)", "อัตรากำไรสุทธิ (%)",
              "D/E", "ปันผล (%)", "FCF Yield (%)",
              "รายได้ YoY (%)", "กำไร YoY (%)"]


def _num(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


# กลุ่มธุรกิจที่ "อัตรากำไรขั้นต้น" ไม่มีความหมาย เพราะไม่มีต้นทุนขาย
_FIN_WORDS = ("financial", "bank", "insurance", "capital markets", "credit",
              "asset management")


def is_financial_sector(sector: str) -> bool:
    s = str(sector or "").lower()
    return any(w in s for w in _FIN_WORDS)


def quick_one(ticker: str) -> dict:
    """ดึงตัวเลขสรุปของหุ้น 1 ตัว — เร็ว ไม่แตะ SEC EDGAR"""
    row = {"ticker": ticker}
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        price = _num(info.get("currentPrice") or info.get("regularMarketPrice")
                     or info.get("previousClose"))
        mcap = _num(info.get("marketCap"))
        fcf = _num(info.get("freeCashflow"))
        if not price or not mcap:
            row["ปัญหา"] = "ไม่มีราคาหรือมูลค่าตลาด"
            return row
        sector = info.get("sector") or "-"

        # ค่าที่ไม่มีต้องเป็น "ไม่มีข้อมูล" ไม่ใช่ 0
        # เดิมเขียน (_num(x) or 0) ซึ่งแปลงค่าที่อ่านไม่ได้ให้เป็น 0
        # ผลคือ D/E ขึ้น 0.00 = "ไม่มีหนี้เลย" ทั้งที่ความจริงคือ "ไม่รู้"
        # การเดาแทนผู้ใช้แบบนี้อันตรายกว่าการเว้นว่าง เพราะดูเหมือนข้อมูลจริง
        def pct(k):
            v = _num(info.get(k))
            return v * 100 if v is not None else None

        gross = pct("grossMargins")
        # บริษัทการเงินไม่มี "ต้นทุนขาย" อัตรากำไรขั้นต้นจึงออกมา 100% หรือ 0%
        # ซึ่งไม่ได้แปลว่าดีหรือแย่ และเอาไปเทียบกับบริษัททั่วไปไม่ได้
        # เว้นว่างดีกว่าแสดงตัวเลขที่ตีความผิดได้
        if is_financial_sector(sector):
            gross = None

        de = _num(info.get("debtToEquity"))

        row.update({
            "ชื่อบริษัท": info.get("longName") or info.get("shortName") or ticker,
            "กลุ่ม": sector,
            "สกุลเงิน": info.get("currency") or "",
            "ราคา": price,
            "มูลค่าตลาด (ล้าน)": mcap / 1e6,
            "P/E": _num(info.get("trailingPE")),
            "P/BV": _num(info.get("priceToBook")),
            "P/S": _num(info.get("priceToSalesTrailing12Months")),
            "EV/EBITDA": _num(info.get("enterpriseToEbitda")),
            "ROE (%)": pct("returnOnEquity"),
            # อัตรากำไรขั้นต้น = บอกว่าสินค้า/บริการมีอำนาจตั้งราคาแค่ไหน
            # อัตรากำไรสุทธิ = เหลือถึงมือผู้ถือหุ้นเท่าไรหลังหักทุกอย่าง
            "อัตรากำไรขั้นต้น (%)": gross,
            "อัตรากำไรสุทธิ (%)": pct("profitMargins"),
            # yfinance ให้ debtToEquity มาเป็น % และนับเฉพาะ **หนี้ที่มีดอกเบี้ย**
            # (เงินกู้ระยะสั้น + ระยะยาว) ไม่ใช่หนี้สินรวมทั้งงบดุล
            # จึงไม่รวมเจ้าหนี้การค้าและค่าใช้จ่ายค้างจ่าย
            "D/E": de / 100 if de is not None else None,
            "ปันผล (%)": _num(info.get("dividendYield")),
            "FCF Yield (%)": (fcf / mcap * 100) if fcf and mcap else None,
            # yfinance ให้การเติบโตแบบ **ไตรมาสล่าสุดเทียบไตรมาสเดียวกันปีก่อน**
            # ซึ่งเป็นวิธีที่ถูกต้องสำหรับธุรกิจที่มีฤดูกาล (ห้างสรรพสินค้า ท่องเที่ยว
            # เกษตร) เพราะเทียบช่วงเวลาเดียวกันของปี
            "รายได้ YoY (%)": pct("revenueGrowth"),
            "กำไร YoY (%)": (pct("earningsGrowth")
                             if info.get("earningsGrowth") is not None
                             else pct("earningsQuarterlyGrowth")),
            "ปัญหา": "",
        })
    except Exception as e:
        row["ปัญหา"] = f"{type(e).__name__}: {str(e)[:60]}"
    return row


def quick_screen(tickers, workers=6, progress=None, retries=3) -> pd.DataFrame:
    """
    คัดกรองเร็วหลายตัวพร้อมกัน

    workers : จำนวนเส้นที่ดึงพร้อมกัน — อย่าตั้งเกิน 12
              เพราะ yfinance จะมองว่ายิงถี่เกินไปแล้วบล็อก

    retries : จำนวนรอบที่จะลองซ้ำเฉพาะตัวที่ดึงไม่สำเร็จ

    ทำไมต้องลองซ้ำ — เรื่องนี้สำคัญมาก
    -----------------------------------
    yfinance จะปฏิเสธคำขอเป็นครั้งคราวเมื่อยิงถี่ ตัวที่พลาดจึงไม่ซ้ำกันในแต่ละรอบ
    ผลคือ **คัดกรองด้วยเกณฑ์เดิมสองครั้งอาจได้จำนวนหุ้นไม่เท่ากัน**
    ซึ่งทำให้ผู้ใช้สับสนและไม่รู้ว่าควรเชื่อผลไหน

    การลองซ้ำเฉพาะตัวที่พลาด (พร้อมลดจำนวนเส้นลงและเว้นจังหวะ)
    ช่วยให้ได้ข้อมูลครบขึ้นมาก และผลใกล้เคียงกันทุกครั้ง
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _pass(items, n_workers, done_before=0, total=None):
        out = []
        total = total or len(items)
        with ThreadPoolExecutor(max_workers=min(n_workers, 12)) as ex:
            futs = {ex.submit(quick_one, t): t for t in items}
            for i, f in enumerate(as_completed(futs), 1):
                out.append(f.result())
                if progress:
                    progress(min(done_before + i, total), total, futs[f])
        return out

    total = len(tickers)
    rows = _pass(list(tickers), workers, 0, total)

    # รอบซ้ำ : เอาเฉพาะตัวที่ยังไม่สำเร็จ
    # แต่ละรอบ **ลดจำนวนเส้นลงครึ่งหนึ่งและรอนานขึ้น**
    # เพราะสาเหตุที่พลาดคือยิงถี่เกินไป ถ้ายิงแรงเท่าเดิมก็จะพลาดซ้ำ
    n_workers = workers
    for r in range(retries):
        failed = [x["ticker"] for x in rows if x.get("ปัญหา")]
        if not failed:
            break
        n_workers = max(2, n_workers // 2)
        wait = 3.0 * (r + 1)
        if progress:
            progress(total, total,
                     f"ลองซ้ำรอบ {r+1}/{retries} — {len(failed):,} ตัว "
                     f"(ใช้ {n_workers} เส้น รอ {wait:.0f} วิ)")
        time.sleep(wait)
        fixed = {x["ticker"]: x for x in _pass(failed, n_workers, total, total)}
        rows = [fixed.get(x["ticker"], x) if x.get("ปัญหา") else x for x in rows]

    df = pd.DataFrame(rows)
    for c in QUICK_COLS:
        if c not in df.columns:
            df[c] = np.nan
    df = df[QUICK_COLS + ["ปัญหา"]]
    ok = int(df["ปัญหา"].eq("").sum())
    df.attrs["ดึงสำเร็จ"] = ok
    df.attrs["ทั้งหมด"] = len(df)
    df.attrs["อัตราสำเร็จ (%)"] = round(ok / len(df) * 100, 1) if len(df) else 0.0
    return df


# เพดานที่ถือว่า "ผิดปกติจนเชื่อไม่ได้"
#
# FCF Yield ของกิจการปกติอยู่ราว 3–15%
# ถ้าเกิน 50% มักเป็นเงินสดก้อนเดียวที่ไม่เกิดซ้ำ เช่น
#   • อสังหาฯ ขายคอนโดค้างสต็อกออกได้ในปีนั้น (สินค้าคงเหลือแปลงเป็นเงินสด)
#   • ธุรกิจรถเช่า/ลีสซิ่ง ขายรถเก่าออกจากฝูง
#   • ขายสินทรัพย์ก้อนใหญ่ครั้งเดียว
# เป็นเงินสดจริง แต่ **ไม่เกิดซ้ำทุกปี** จึงเอามาประเมินมูลค่าต่อเนื่องไม่ได้
ABSURD_FCF_YIELD = 50.0
DEFAULT_MIN_MCAP = 1000.0          # ล้าน — ตัดหุ้นเล็กมากที่ตัวเลขผันผวนสุดขั้ว
MIN_SENSIBLE_PE = 0.5              # P/E ต่ำกว่านี้แทบแน่นอนว่าข้อมูลผิด


def quality_flags(df, min_mcap=DEFAULT_MIN_MCAP,
                  max_fcf_yield=ABSURD_FCF_YIELD) -> pd.Series:
    """
    ตรวจว่าแต่ละตัวมีจุดที่ต้องระวังอะไรบ้าง — **ไม่ตัดออก แค่ติดธง**

    ปรัชญา : ระบบไม่ควรซ่อนข้อมูลจากผู้ใช้เงียบ ๆ
    ตัวเลขจริงต้องแสดงเสมอ ส่วนคำเตือนเป็นข้อมูลเพิ่ม ไม่ใช่การตัดสินแทน

    คืน Series ของข้อความเตือน (ว่างเปล่า = ไม่มีจุดต้องระวัง)
    """
    if df.empty:
        return pd.Series(dtype=str)
    nm = pd.to_numeric(df.get("อัตรากำไรสุทธิ (%)"), errors="coerce")
    pbv = pd.to_numeric(df.get("P/BV"), errors="coerce")
    cap = pd.to_numeric(df.get("มูลค่าตลาด (ล้าน)"), errors="coerce")
    fcy = pd.to_numeric(df.get("FCF Yield (%)"), errors="coerce")
    pe = pd.to_numeric(df.get("P/E"), errors="coerce")

    out = []
    for i in df.index:
        w = []
        # ใช้คำสั้นที่สุดที่ยังเข้าใจได้ เพราะคอลัมน์นี้ต้องอยู่ใกล้ชื่อหุ้น
        if pd.notna(nm.get(i)) and nm[i] <= 0:
            w.append("ขาดทุน")
        # กำไรสุทธิเกิน 100% ของรายได้ = กำไรส่วนใหญ่ไม่ได้มาจากการขายของ
        # มักเป็นกำไรจากการขายสินทรัพย์ ตีมูลค่าทรัพย์สินใหม่ หรือส่วนแบ่งจากบริษัทร่วม
        # เป็นตัวเลขจริงในงบ แต่ไม่เกิดซ้ำ จึงเอาไปคาดการณ์อนาคตไม่ได้
        if pd.notna(nm.get(i)) and nm[i] > 100:
            w.append("กำไรพิเศษ")
        if pd.notna(pbv.get(i)) and pbv[i] <= 0:
            w.append("ทุนติดลบ")
        if pd.notna(cap.get(i)) and cap[i] < min_mcap:
            w.append("เล็ก")
        if pd.notna(fcy.get(i)) and abs(fcy[i]) > max_fcf_yield:
            w.append("FCF?")
        if pd.notna(pe.get(i)) and 0 < pe[i] < MIN_SENSIBLE_PE:
            w.append("P/E?")
        out.append(" · ".join(w))
    return pd.Series(out, index=df.index)


def basic_quality(df, min_mcap=DEFAULT_MIN_MCAP,
                  max_fcf_yield=ABSURD_FCF_YIELD) -> pd.DataFrame:
    """
    ตัด "หุ้นที่ตัวเลขดูดีเพราะกิจการพัง" ออกก่อนคัดกรองจริง

    ทำไมต้องมี — นี่คือกับดักคลาสสิกของระบบคัดกรองหุ้น
    ------------------------------------------------------
    อัตราส่วนคำนวณจาก เศษ ÷ ส่วน ถ้า "ส่วน" ยุบลงมาก อัตราส่วนจะดูสวยผิดปกติ
    ตัวอย่างจริงที่พบ : หุ้นราคา 5 สตางค์ มูลค่าตลาดเหลือ 500 ล้าน
    ได้ FCF Yield 1,642% ทั้งที่ขาดทุน −68% และส่วนของผู้ถือหุ้นติดลบ

    เกณฑ์ที่ใช้ตัด
      • ขาดทุนสุทธิ (อัตรากำไรสุทธิติดลบ)
      • ส่วนของผู้ถือหุ้นติดลบ (P/BV ≤ 0)
      • มูลค่าตลาดต่ำกว่าที่กำหนด
      • FCF Yield สูงเกินจริง (ค่าเริ่มต้น > 50%)
      • P/E ต่ำกว่า 0.5 (แทบแน่นอนว่าข้อมูลผิด)
    """
    if df.empty:
        return df
    m = df["ปัญหา"].eq("")
    nm = pd.to_numeric(df.get("อัตรากำไรสุทธิ (%)"), errors="coerce")
    pbv = pd.to_numeric(df.get("P/BV"), errors="coerce")
    cap = pd.to_numeric(df.get("มูลค่าตลาด (ล้าน)"), errors="coerce")
    fcy = pd.to_numeric(df.get("FCF Yield (%)"), errors="coerce")

    m &= nm.isna() | (nm > 0)          # ไม่มีข้อมูลยังผ่าน แต่ถ้ารู้ว่าขาดทุนให้ตัด
    m &= pbv.isna() | (pbv > 0)        # ส่วนทุนติดลบ = ตัด
    m &= cap.isna() | (cap >= min_mcap)
    m &= fcy.isna() | (fcy.abs() <= max_fcf_yield)

    pe = pd.to_numeric(df.get("P/E"), errors="coerce")
    m &= pe.isna() | (pe >= MIN_SENSIBLE_PE)      # P/E 0.0x = ข้อมูลเสีย
    return df[m].reset_index(drop=True)


GROWTH_COLS = ["รายได้ QoQ (%)", "รายได้ YoY-Q (%)",
               "กำไร QoQ (%)", "กำไร YoY-Q (%)",
               "FCF QoQ (%)", "FCF YoY-Q (%)", "งบไตรมาสล่าสุด"]


def _q_growth(s: pd.Series):
    """
    คืน (QoQ, YoY) จากอนุกรมรายไตรมาสที่เรียงจากใหม่ไปเก่า

    QoQ = ไตรมาสล่าสุด เทียบ ไตรมาสก่อนหน้า        (ตำแหน่ง 0 vs 1)
    YoY = ไตรมาสล่าสุด เทียบ ไตรมาสเดียวกันปีก่อน  (ตำแหน่ง 0 vs 4)

    ใช้ค่าสัมบูรณ์ของฐานเป็นตัวหาร เพื่อให้การเปลี่ยนแปลงจากขาดทุนเป็นกำไร
    ได้เครื่องหมายที่ถูกต้อง (ถ้าหารด้วยค่าติดลบตรง ๆ เครื่องหมายจะกลับด้าน
    กำไรที่ดีขึ้นจะกลายเป็นตัวเลขติดลบ ซึ่งอ่านผิดความหมายทันที)
    """
    def _chg(new, old):
        if new is None or old is None or old == 0 or not np.isfinite(old):
            return None
        return (new - old) / abs(old) * 100

    v = [float(x) if pd.notna(x) else None for x in s]
    qoq = _chg(v[0], v[1]) if len(v) >= 2 else None
    yoy = _chg(v[0], v[4]) if len(v) >= 5 else None
    return qoq, yoy


def _row_of(df, *names):
    """หาแถวจากงบ โดยลองหลายชื่อ — yfinance ตั้งชื่อไม่เหมือนกันทุกบริษัท"""
    if df is None or getattr(df, "empty", True):
        return None
    for n in names:
        if n in df.index:
            s = df.loc[n]
            if s.notna().any():
                return s
    return None


def growth_one(ticker: str) -> dict:
    """การเติบโตรายไตรมาสของหุ้น 1 ตัว — ต้องดึงงบไตรมาสเพิ่ม 2 คำขอ"""
    row = {"ticker": ticker}
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        inc = t.quarterly_income_stmt
        cf = t.quarterly_cashflow

        rev = _row_of(inc, "Total Revenue", "Operating Revenue")
        net = _row_of(inc, "Net Income", "Net Income Common Stockholders",
                      "Net Income Including Noncontrolling Interests")
        ocf = _row_of(cf, "Operating Cash Flow",
                      "Total Cash From Operating Activities")
        capex = _row_of(cf, "Capital Expenditure", "Capital Expenditures")

        fcf = None
        if ocf is not None:
            # CapEx ใน yfinance เป็นค่าติดลบอยู่แล้ว จึงบวกเข้าไปตรง ๆ
            fcf = ocf + capex.reindex(ocf.index).fillna(0) if capex is not None else ocf

        for label, s in (("รายได้", rev), ("กำไร", net), ("FCF", fcf)):
            q, y = _q_growth(s) if s is not None else (None, None)
            row[f"{label} QoQ (%)"] = q
            row[f"{label} YoY-Q (%)"] = y

        if inc is not None and not inc.empty and len(inc.columns):
            row["งบไตรมาสล่าสุด"] = str(inc.columns[0])[:10]
        row["ปัญหางบไตรมาส"] = ""
    except Exception as e:
        row["ปัญหางบไตรมาส"] = f"{type(e).__name__}: {str(e)[:50]}"
    return row


def quarterly_growth(tickers, workers=4, progress=None) -> pd.DataFrame:
    """
    ดึงการเติบโตรายไตรมาสของหุ้นหลายตัว

    **ใช้กับรายชื่อที่คัดมาแล้วเท่านั้น ไม่ใช่ทั้งตลาด**
    เพราะต้องดึงงบไตรมาสเพิ่มอีก 2 คำขอต่อหุ้น
    ถ้าทำกับหุ้นไทยทั้ง 866 ตัว = 1,732 คำขอเพิ่ม ซึ่งจะโดน Yahoo บล็อกแน่นอน
    และทำให้อัตราดึงสำเร็จ 99% ที่ได้มายากตกลงทันที
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    tickers = list(dict.fromkeys(tickers))
    rows = []
    with ThreadPoolExecutor(max_workers=min(workers, 8)) as ex:
        futs = {ex.submit(growth_one, t): t for t in tickers}
        for i, f in enumerate(as_completed(futs), 1):
            rows.append(f.result())
            if progress:
                progress(i, len(tickers), futs[f])
    return pd.DataFrame(rows)


def attach_growth(df: pd.DataFrame, growth: pd.DataFrame) -> pd.DataFrame:
    """รวมตารางการเติบโตรายไตรมาสเข้ากับตารางคัดกรอง"""
    if df.empty or growth is None or growth.empty:
        return df
    keep = ["ticker"] + [c for c in GROWTH_COLS if c in growth.columns]
    return df.merge(growth[keep], on="ticker", how="left")


# อัตราส่วนที่ค่าติดลบ "ไม่ได้แปลว่าถูก"
#   P/E ติดลบ       = ขาดทุน
#   P/BV ติดลบ      = ส่วนของผู้ถือหุ้นติดลบ
#   EV/EBITDA ติดลบ = EBITDA ติดลบ (ขาดทุนตั้งแต่ระดับการดำเนินงาน)
#                     หรือมีเงินสดมากกว่ามูลค่ากิจการ ซึ่งพบในบริษัทกำลังจะเลิก
# ถ้าไม่บังคับให้เป็นบวก บริษัทที่แย่ที่สุดจะผ่านเกณฑ์ "ถูก" ทุกครั้ง
POSITIVE_ONLY_FILTER = ("P/E", "P/BV", "EV/EBITDA")


def quick_filter(df, max_pe=None, max_pbv=None, min_roe=None, min_fcf_yield=None,
                 min_mcap=None, min_div=None, max_de=None,
                 min_gross_margin=None, min_net_margin=None,
                 max_ev_ebitda=None) -> pd.DataFrame:
    """
    กรองผลจากชั้นที่ 1 — ทุกเงื่อนไขไม่ใส่ก็ได้

    หลักการ : ค่าที่ **ไม่มีข้อมูล** จะถูกคัดออกเมื่อมีการตั้งเงื่อนไขข้อนั้น
    เพราะเราไม่ควรเดาแทนว่า "ไม่มีข้อมูล = ผ่านเกณฑ์"
    """
    if df.empty:
        return df
    m = df["ปัญหา"].eq("")
    checks = [("P/E", max_pe, "le"), ("P/BV", max_pbv, "le"),
              ("EV/EBITDA", max_ev_ebitda, "le"),
              ("ROE (%)", min_roe, "ge"), ("FCF Yield (%)", min_fcf_yield, "ge"),
              ("มูลค่าตลาด (ล้าน)", min_mcap, "ge"), ("ปันผล (%)", min_div, "ge"),
              ("D/E", max_de, "le"),
              ("อัตรากำไรขั้นต้น (%)", min_gross_margin, "ge"),
              ("อัตรากำไรสุทธิ (%)", min_net_margin, "ge")]
    for col, val, op in checks:
        if val is None or col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        m &= (s <= val) if op == "le" else (s >= val)
        if col in POSITIVE_ONLY_FILTER:
            m &= s > 0
    return df[m].reset_index(drop=True)


# ===========================================================================
# ชั้นที่ 2 — วิเคราะห์ลึก (DCF เต็มรูปแบบ)
# ===========================================================================

def _last(table, row_name):
    """ค่าปีล่าสุดของอัตราส่วนหนึ่ง — คืน None ถ้าไม่มีแถวนั้นหรือไม่มีข้อมูล"""
    if row_name not in getattr(table, "index", []):
        return None
    s = pd.to_numeric(table.loc[row_name], errors="coerce").dropna()
    return float(s.iloc[-1]) if len(s) else None


def scan_one(ticker: str, rf=None, mos=None, refresh=False) -> dict:
    """
    วิเคราะห์หุ้น 1 ตัว คืนผลสรุปบรรทัดเดียว

    ถ้าตัวไหนวิเคราะห์ไม่ได้ จะคืนแถวที่มีคอลัมน์ 'ปัญหา' แทนการหยุดทั้งระบบ
    (สแกน 30 ตัวแล้วพังเพราะตัวที่ 7 = เสียเวลาเปล่า)
    """
    from report import analyze_all
    row = {"ticker": ticker}
    try:
        data, S, R, v, b = analyze_all(ticker, rf=rf, mos=mos, refresh=refresh)
        info = data.get("info", {})
        price = v["ราคาปัจจุบัน"]
        fair = b["มูลค่าที่ประเมินได้"]
        rel = b["ความน่าเชื่อถือ"]
        sm = R["summary"]
        val = R.get("valuation") or {}
        tb = R["table"]
        row.update({
            "ชื่อบริษัท": info.get("longName") or ticker,
            "กลุ่ม": info.get("sector") or "-",
            "สกุลเงิน": v["สกุลเงิน"],

            # ---- มูลค่าและราคา ----
            "ราคา": price,
            "มูลค่าที่ประเมินได้": fair,
            "ส่วนลด (%)": (1 - price / fair) * 100 if fair and price else np.nan,
            "โซน": b["โซนปัจจุบัน"],
            "มูลค่าตลาด (ล้าน)": val.get("มูลค่าตลาด (ล้าน)"),
            "ส่วนเผื่อความปลอดภัย (%)": (b.get("mos ที่ใช้") or 0) * 100,

            # ---- อัตราส่วนราคา (ปีล่าสุด) ----
            "P/E": val.get("P/E"),
            "P/BV": val.get("P/BV"),
            "P/S": val.get("P/S"),
            "P/FCF": val.get("P/FCF"),
            "EV/EBITDA": val.get("EV/EBITDA"),
            "EV/EBIT": val.get("EV/EBIT"),
            "Earnings Yield (%)": val.get("Earnings Yield (%)"),
            "FCF Yield (%)": val.get("FCF Yield (%)"),

            # ---- การเติบโต ----
            "CAGR รายได้ (%)": sm.get("CAGR รายได้ (%)"),
            "CAGR กำไรสุทธิ (%)": sm.get("CAGR กำไรสุทธิ (%)"),
            "CAGR EPS (%)": sm.get("CAGR EPS (%)"),
            "CAGR FCF (%)": sm.get("CAGR FCF (%)"),
            "ตลาดคาดโต (%)": (v["อัตราโตที่ตลาดคาดหวัง"] * 100
                              if v.get("อัตราโตที่ตลาดคาดหวัง") is not None else None),

            # ---- ความสามารถทำกำไร ----
            "Gross Margin (%)": _last(tb, "Gross Margin"),
            "Operating Margin (%)": _last(tb, "Operating Margin"),
            "Net Margin (%)": _last(tb, "Net Margin"),
            "ROE (%)": _last(tb, "ROE"),
            "ROA (%)": _last(tb, "ROA"),
            "ROIC (%)": _last(tb, "ROIC"),
            "ROE เฉลี่ย (%)": sm.get("ROE เฉลี่ย (%)"),
            "ROE ต่ำสุด (%)": sm.get("ROE ต่ำสุด (%)"),
            # ส่วนเบี่ยงเบนต่ำ = ทำกำไรได้สม่ำเสมอ ซึ่งสำคัญกว่าค่าเฉลี่ยสูง ๆ
            # ที่มาจากปีดีปีร้ายสลับกัน เพราะพยากรณ์อนาคตได้ยากกว่ามาก
            "ROE ส่วนเบี่ยงเบน (%)": sm.get("ROE ส่วนเบี่ยงเบน (%)"),
            "ROIC เฉลี่ย (%)": sm.get("ROIC เฉลี่ย (%)"),
            "Gross Margin เฉลี่ย (%)": sm.get("Gross Margin เฉลี่ย (%)"),
            "Gross Margin ส่วนเบี่ยงเบน (%)": sm.get("Gross Margin ส่วนเบี่ยงเบน (%)"),

            # ---- คุณภาพกำไร ----
            "OCF/กำไรสุทธิ เฉลี่ย (x)": sm.get("OCF/กำไรสุทธิ เฉลี่ย (x)"),
            "ปีที่ FCF เป็นบวก": sm.get("ปีที่ FCF เป็นบวก"),
            "Accrual Ratio": _last(tb, "Accrual Ratio"),
            "FCF Margin (%)": _last(tb, "FCF Margin"),
            "CapEx / OCF": _last(tb, "CapEx / OCF"),
            "อัตราภาษีที่แท้จริง (%)": _last(tb, "อัตราภาษีที่แท้จริง"),

            # ---- ฐานะการเงิน ----
            "Current Ratio": _last(tb, "Current Ratio"),
            "Quick Ratio": _last(tb, "Quick Ratio"),
            # D/E ปีล่าสุด — เก็บทั้งสองนิยามเพราะให้ภาพต่างกันมาก
            "D/E": _last(tb, "D/E (หนี้มีดอกเบี้ย)"),
            "D/E (หนี้สินรวม)": _last(tb, "D/E (หนี้สินรวม)"),
            "Net Debt/EBITDA": _last(tb, "Net Debt / EBITDA"),
            "Interest Coverage": _last(tb, "Interest Coverage"),

            # ---- เงินปันผล ----
            "Payout Ratio (%)": _last(tb, "Payout Ratio"),
            "เงินปันผลต่อหุ้น": _last(tb, "เงินปันผลต่อหุ้น"),
            "เงินปันผล / FCF (%)": _last(tb, "เงินปันผล / FCF"),

            # ---- สมมติฐานที่ใช้ประเมิน ----
            "WACC (%)": (v.get("wacc ที่ใช้") or 0) * 100,
            "g1 (%)": (v.get("g1 ที่ใช้") or 0) * 100,
            "g2 (%)": (v.get("g2 ที่ใช้") or 0) * 100,
            "สัดส่วนมูลค่าสุดท้าย (%)": ((v.get("base_dcf") or {})
                                        .get("สัดส่วนมูลค่าสุดท้าย", 0) or 0) * 100,

            # ---- ความน่าเชื่อถือของผลลัพธ์ ----
            "ความน่าเชื่อถือ": rel["ระดับ"],
            "คะแนน": rel["คะแนน"],
            "ปีข้อมูล": v["ปีข้อมูล"],
            "แหล่งงบ": v.get("แหล่งงบ", "-"),
            "ใช้ DCF": "ใช่" if v.get("ใช้ DCF ได้ไหม") else "ไม่",
            "ปัญหา": "",
        })
    except Exception as e:
        row.update({"ชื่อบริษัท": ticker, "ปัญหา": f"{type(e).__name__}: {e}"})
    return row


def scan(tickers, rf=None, mos=None, refresh=False, progress=None) -> pd.DataFrame:
    """
    สแกนหุ้นหลายตัว

    progress : ฟังก์ชันที่จะถูกเรียกทุกครั้งที่ทำเสร็จ 1 ตัว
               รับ (ลำดับที่, จำนวนทั้งหมด, ชื่อหุ้น) — ใช้แสดงแถบความคืบหน้า
    """
    rows = []
    total = len(tickers)
    for i, t in enumerate(tickers, 1):
        if progress:
            progress(i, total, t)
        rows.append(scan_one(t, rf=rf, mos=mos, refresh=refresh))
        time.sleep(0.2)          # เว้นจังหวะเล็กน้อย ไม่ให้ยิงขอข้อมูลถี่เกินไป
    df = pd.DataFrame(rows)
    if "ส่วนลด (%)" in df.columns:
        df = df.sort_values("ส่วนลด (%)", ascending=False, na_position="last")
    return df.reset_index(drop=True)


def undervalued(df: pd.DataFrame, min_discount=0.0, min_score=0) -> pd.DataFrame:
    """
    คัดเฉพาะหุ้นที่ราคาต่ำกว่ามูลค่าที่ประเมินได้

    ถ้าไม่มีคอลัมน์ 'ส่วนลด (%)' เลย แปลว่า **ไม่มีหุ้นตัวใดวิเคราะห์สำเร็จ**
    ต้องคืนตารางว่าง ไม่ใช่คืนตารางเดิมทั้งก้อน
    เพราะแถวที่วิเคราะห์ไม่สำเร็จไม่ใช่ "หุ้นที่ราคาต่ำกว่ามูลค่า"
    (ของเดิมคืน df ทั้งก้อน ทำให้หน้าจอขึ้นว่าพบ 10 ตัวทั้งที่สำเร็จ 0 ตัว
     แล้วโปรแกรมพังตอนไปอ่านคอลัมน์ที่ไม่มีอยู่)
    """
    if df.empty or "ส่วนลด (%)" not in df.columns:
        return df.iloc[0:0]
    m = (df["ส่วนลด (%)"] >= min_discount) & df["ปัญหา"].eq("")
    if min_score:
        m &= df["คะแนน"].fillna(0) >= min_score
    return df[m].reset_index(drop=True)


# ===========================================================================
# เปรียบเทียบหุ้น 2–10 ตัว
# ===========================================================================

# ตารางเปรียบเทียบ แบ่งเป็นหมวดเพื่อให้อ่านทีละเรื่อง
# รูปแบบ : (ชื่อหมวด, [(ป้ายที่แสดง, ชื่อคอลัมน์ในข้อมูล, ทศนิยม), ...])
#
# ทำไมต้องแบ่งหมวด : ตาราง 40 บรรทัดรวดเดียวอ่านไม่ไหว
# แต่ถ้าตัดให้เหลือ 12 บรรทัดก็เสียข้อมูลที่อุตส่าห์คำนวณมาแล้ว
# การแบ่งหมวดให้ทั้งความครบและความอ่านง่ายพร้อมกัน
COMPARE_SECTIONS = [
    ("มูลค่าและราคา", [
        ("ราคาตลาด", "ราคา", 2),
        ("มูลค่าที่ประเมินได้", "มูลค่าที่ประเมินได้", 2),
        ("ส่วนลด/ส่วนเกิน (%)", "ส่วนลด (%)", 1),
        ("โซนราคา", "โซน", None),
        ("ส่วนเผื่อความปลอดภัย (%)", "ส่วนเผื่อความปลอดภัย (%)", 0),
        ("มูลค่าตลาด (ล้าน)", "มูลค่าตลาด (ล้าน)", 0),
    ]),
    ("อัตราส่วนราคา", [
        ("P/E", "P/E", 1),
        ("P/BV", "P/BV", 2),
        ("P/S", "P/S", 2),
        ("P/FCF", "P/FCF", 1),
        ("EV/EBITDA", "EV/EBITDA", 1),
        ("EV/EBIT", "EV/EBIT", 1),
        ("Earnings Yield (%)", "Earnings Yield (%)", 2),
        ("FCF Yield (%)", "FCF Yield (%)", 2),
    ]),
    ("การเติบโต", [
        ("CAGR รายได้ (%)", "CAGR รายได้ (%)", 1),
        ("CAGR กำไรสุทธิ (%)", "CAGR กำไรสุทธิ (%)", 1),
        ("CAGR EPS (%)", "CAGR EPS (%)", 1),
        ("CAGR FCF (%)", "CAGR FCF (%)", 1),
        ("ตลาดคาดให้โต (%)", "ตลาดคาดโต (%)", 1),
    ]),
    ("ความสามารถทำกำไร", [
        ("Gross Margin (%)", "Gross Margin (%)", 1),
        ("Operating Margin (%)", "Operating Margin (%)", 1),
        ("Net Margin (%)", "Net Margin (%)", 1),
        ("ROE ปีล่าสุด (%)", "ROE (%)", 1),
        ("ROE เฉลี่ยทั้งช่วง (%)", "ROE เฉลี่ย (%)", 1),
        ("ROE ต่ำสุด (%)", "ROE ต่ำสุด (%)", 1),
        ("ROE ส่วนเบี่ยงเบน (%)", "ROE ส่วนเบี่ยงเบน (%)", 1),
        ("ROA (%)", "ROA (%)", 1),
        ("ROIC (%)", "ROIC (%)", 1),
        ("ROIC เฉลี่ย (%)", "ROIC เฉลี่ย (%)", 1),
    ]),
    ("คุณภาพกำไร", [
        ("OCF / กำไรสุทธิ (เท่า)", "OCF/กำไรสุทธิ เฉลี่ย (x)", 2),
        ("FCF Margin (%)", "FCF Margin (%)", 1),
        ("ปีที่ FCF เป็นบวก", "ปีที่ FCF เป็นบวก", 0),
        ("Accrual Ratio", "Accrual Ratio", 3),
        ("CapEx / OCF", "CapEx / OCF", 2),
        ("อัตราภาษีที่แท้จริง (%)", "อัตราภาษีที่แท้จริง (%)", 1),
    ]),
    ("ฐานะการเงิน", [
        ("Current Ratio", "Current Ratio", 2),
        ("Quick Ratio", "Quick Ratio", 2),
        ("D/E (หนี้มีดอกเบี้ย)", "D/E", 2),
        ("D/E (หนี้สินรวม)", "D/E (หนี้สินรวม)", 2),
        ("Net Debt / EBITDA", "Net Debt/EBITDA", 2),
        ("Interest Coverage", "Interest Coverage", 1),
    ]),
    ("เงินปันผล", [
        ("เงินปันผลต่อหุ้น", "เงินปันผลต่อหุ้น", 4),
        ("Payout Ratio (%)", "Payout Ratio (%)", 1),
        ("เงินปันผล / FCF (%)", "เงินปันผล / FCF (%)", 1),
    ]),
    ("สมมติฐานที่ใช้ประเมินมูลค่า", [
        ("WACC (%)", "WACC (%)", 2),
        ("อัตราโตช่วงแรก g1 (%)", "g1 (%)", 2),
        ("อัตราโตถาวร g2 (%)", "g2 (%)", 2),
        ("สัดส่วนมูลค่าสุดท้าย (%)", "สัดส่วนมูลค่าสุดท้าย (%)", 0),
        ("ใช้ DCF ได้ไหม", "ใช้ DCF", None),
    ]),
    ("ความน่าเชื่อถือของผลลัพธ์", [
        ("ระดับความน่าเชื่อถือ", "ความน่าเชื่อถือ", None),
        ("คะแนน (เต็ม 100)", "คะแนน", 0),
        ("จำนวนปีข้อมูล", "ปีข้อมูล", 0),
        ("แหล่งงบการเงิน", "แหล่งงบ", None),
        ("กลุ่มอุตสาหกรรม", "กลุ่ม", None),
    ]),
]

# รายการแบบแบนสำหรับโหมดย่อ — ใช้เมื่อผู้ใช้อยากดูเฉพาะหัวข้อสำคัญ
COMPARE_ROWS = ([("ราคาตลาด", "ราคา", 2),
                 ("มูลค่าที่ประเมินได้", "มูลค่าที่ประเมินได้", 2),
                 ("ส่วนลด/ส่วนเกิน (%)", "ส่วนลด (%)", 1),
                 ("โซนราคา", "โซน", None),
                 ("P/E", "P/E", 1),
                 ("P/BV", "P/BV", 2),
                 ("ROE เฉลี่ย (%)", "ROE เฉลี่ย (%)", 1),
                 ("CAGR รายได้ (%)", "CAGR รายได้ (%)", 1),
                 ("D/E (หนี้มีดอกเบี้ย)", "D/E", 2),
                 ("ความน่าเชื่อถือ", "ความน่าเชื่อถือ", None),
                 ("คะแนนความน่าเชื่อถือ", "คะแนน", 0),
                 ("กลุ่มอุตสาหกรรม", "กลุ่ม", None)])

MAX_COMPARE = 10
MIN_COMPARE = 2

# เครื่องหมายนำหน้าชื่อหมวดในตารางรวม — ชั้นแสดงผลใช้ตัวนี้แยกแถวหัวหมวด
# ออกจากแถวข้อมูลปกติ เลือกอักขระที่ไม่มีทางปรากฏในชื่ออัตราส่วนจริง
SECTION_MARK = "§ "


def compare(tickers, rf=None, mos=None, refresh=False, progress=None):
    """
    เปรียบเทียบหุ้น 2–10 ตัวแบบเคียงข้างกัน

    คืน dict :
        table  : DataFrame (แถว = หัวข้อ, คอลัมน์ = หุ้น) พร้อมเปรียบเทียบด้วยตา
        raw    : DataFrame ดิบจาก scan()
        errors : รายการหุ้นที่วิเคราะห์ไม่สำเร็จ
    """
    tickers = [t.strip().upper() for t in tickers if t and str(t).strip()]
    tickers = list(dict.fromkeys(tickers))          # ตัดตัวซ้ำ คงลำดับเดิม
    if len(tickers) < MIN_COMPARE:
        raise ValueError(f"ต้องเลือกอย่างน้อย {MIN_COMPARE} ตัวจึงจะเปรียบเทียบได้")
    if len(tickers) > MAX_COMPARE:
        raise ValueError(f"เปรียบเทียบได้สูงสุด {MAX_COMPARE} ตัว "
                         f"(เลือกมา {len(tickers)} ตัว)\n"
                         "  เหตุผล: มากกว่านี้ตารางจะกว้างจนอ่านไม่รู้เรื่อง "
                         "และใช้เวลานานเกินไป")

    raw = scan(tickers, rf=rf, mos=mos, refresh=refresh, progress=progress)
    return build_compare(raw, order=tickers)


def build_compare(raw: pd.DataFrame, order=None) -> dict:
    """
    ประกอบตารางเปรียบเทียบจากผล scan() ที่มีอยู่แล้ว — **ไม่ดึงข้อมูลใหม่**

    แยกออกมาเป็นฟังก์ชันต่างหาก เพื่อให้โหมด "วิเคราะห์ลึกหลายตัว"
    เอาผลที่วิเคราะห์เสร็จแล้วมาทำตารางเปรียบเทียบต่อได้ทันที
    ไม่ต้องเสียเวลาวิเคราะห์ซ้ำอีกรอบ (ซึ่งกินเวลา 30 วินาทีต่อหุ้น)
    """
    if raw is None or raw.empty:
        return {"table": pd.DataFrame(), "sections": {}, "full": pd.DataFrame(),
                "raw": raw, "errors": [], "winner": None}

    ok = raw[raw["ปัญหา"].eq("")]
    errors = [(r["ticker"], r["ปัญหา"]) for _, r in raw[~raw["ปัญหา"].eq("")].iterrows()]

    if ok.empty:
        return {"table": pd.DataFrame(), "sections": {}, "full": pd.DataFrame(),
                "raw": raw, "errors": errors, "winner": None}

    ok = ok.set_index("ticker")
    if order:                                    # คงลำดับที่ผู้ใช้เลือก
        ok = ok.reindex([t for t in order if t in ok.index])

    def _fmt(t, col, dec):
        v = ok.loc[t, col]
        if pd.isna(v):
            return "—"
        if dec is None:
            return str(v)
        try:
            return f"{float(v):,.{dec}f}"
        except (TypeError, ValueError):
            return str(v)

    def _build(rows):
        out = {}
        for label, col, dec in rows:
            if col not in ok.columns:
                continue
            vals = [_fmt(t, col, dec) for t in ok.index]
            # แถวที่ไม่มีข้อมูลเลยสักตัว ไม่ต้องแสดง — เปลืองพื้นที่โดยไม่ได้อะไร
            if all(x == "—" for x in vals):
                continue
            out[label] = vals
        if not out:
            return pd.DataFrame()
        tbl = pd.DataFrame(out, index=ok.index).T
        tbl.columns = [f"{t}\n{str(ok.loc[t, 'ชื่อบริษัท'])[:22]}" for t in ok.index]
        return tbl

    sections = {}
    for name, rows in COMPARE_SECTIONS:
        tbl = _build(rows)
        if not tbl.empty:
            sections[name] = tbl

    # ---- ตารางเดียวต่อเนื่อง ----
    # แทรกแถวหัวหมวดคั่นไว้ในตารางเดียวกัน แทนการแยกเป็นหลายตาราง
    # ข้อดี : หัวตาราง (ชื่อหุ้น) ตรึงอยู่บนสุดที่เดียว เลื่อนดูยาว ๆ แล้วยังรู้ว่า
    #         คอลัมน์ไหนคือหุ้นตัวไหน ถ้าแยกหลายตารางต้องเลื่อนกลับขึ้นไปดูทุกครั้ง
    # หัวหมวดใช้เครื่องหมาย § นำหน้า เพื่อให้ชั้นแสดงผลรู้ว่าต้องวาดเป็นแถบคั่น
    parts = []
    for name, tbl in sections.items():
        head = pd.DataFrame([[""] * len(tbl.columns)],
                            index=[SECTION_MARK + name], columns=tbl.columns)
        parts.append(head)
        parts.append(tbl)
    full = pd.concat(parts) if parts else pd.DataFrame()

    return {"table": _build(COMPARE_ROWS),        # ตารางย่อ (เข้ากันได้กับของเดิม)
            "sections": sections,                 # แยกเป็นหมวด (เผื่อใช้ที่อื่น)
            "full": full,                         # ตารางเดียวต่อเนื่อง
            "raw": raw, "errors": errors,
            "winner": _pick_best(ok)}


def _pick_best(ok: pd.DataFrame):
    """
    ชี้ตัวที่ "ตัวเลขน่าสนใจที่สุด" — ไม่ใช่คำแนะนำให้ซื้อ

    ให้คะแนนจาก 2 ด้านเท่า ๆ กัน :
        ส่วนลดจากมูลค่า  (ถูกแค่ไหน)
        ความน่าเชื่อถือ   (เชื่อตัวเลขได้แค่ไหน)
    จงใจให้ความน่าเชื่อถือมีน้ำหนักเท่าส่วนลด เพราะหุ้นที่ดู "ถูกมาก"
    จากข้อมูล 4 ปีที่วิธีต่าง ๆ ขัดกัน ไม่ได้น่าสนใจกว่าหุ้นที่ถูกน้อยกว่าแต่ข้อมูลแน่น
    """
    d = pd.to_numeric(ok["ส่วนลด (%)"], errors="coerce")
    s = pd.to_numeric(ok["คะแนน"], errors="coerce")
    if d.notna().sum() == 0:
        return None
    dn = (d - d.min()) / (d.max() - d.min()) if d.max() != d.min() else d * 0 + 0.5
    sn = s / 100.0
    total = (dn.fillna(0) + sn.fillna(0)) / 2
    best = total.idxmax()
    return {"ticker": best, "คะแนนรวม": float(total.max()),
            "ส่วนลด (%)": float(d.get(best, np.nan)),
            "ความน่าเชื่อถือ": ok.loc[best, "ความน่าเชื่อถือ"]}


# ---------------------------------------------------------------------------
# ชุดหุ้นสำเร็จรูป
# ---------------------------------------------------------------------------

def preset(name: str, limit=None):
    """
    ชุดหุ้นตั้งต้น

        thai       หุ้นไทยทั้งตลาด (SET + mai, เฉพาะหุ้นสามัญ)
        set        เฉพาะตลาด SET
        mai        เฉพาะตลาด mai
        us         หุ้นสหรัฐยอดนิยม 39 ตัว
        us-all     หุ้นสหรัฐทั้งตลาดจากทะเบียน SEC (~10,000 ตัว)
        all        ไทย + สหรัฐทั้งตลาด
    """
    from tickers import POPULAR_US, thai_universe, us_universe
    if name == "thai":
        out = thai_universe()
    elif name == "set":
        out = thai_universe(market="SET")
    elif name == "mai":
        out = thai_universe(market="mai")
    elif name == "us":
        out = list(POPULAR_US)
    elif name == "us-all":
        out = us_universe()
    elif name == "all":
        out = thai_universe() + us_universe()
    else:
        raise ValueError("ชุดหุ้นมีให้เลือก : thai / set / mai / us / us-all / all")
    return out[:limit] if limit else out


# ---------------------------------------------------------------------------
# แสดงผล
# ---------------------------------------------------------------------------

def print_report(df: pd.DataFrame, min_discount=0.0):
    W = 108
    ok = df[df["ปัญหา"].eq("")] if "ปัญหา" in df.columns else df
    bad = df[~df["ปัญหา"].eq("")] if "ปัญหา" in df.columns else pd.DataFrame()
    under = undervalued(df, min_discount)

    print("=" * W)
    print(f"  ผลการสแกน {len(df)} ตัว · วิเคราะห์สำเร็จ {len(ok)} · "
          f"ราคาต่ำกว่ามูลค่า {len(under)}")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * W)

    if under.empty:
        print("\n  ไม่มีหุ้นตัวใดที่ราคาต่ำกว่ามูลค่าที่ประเมินได้ตามเกณฑ์ที่ตั้งไว้")
    else:
        print(f"\n  หุ้นที่ราคาต่ำกว่ามูลค่า (เรียงจากส่วนลดมากไปน้อย)")
        print("  " + "-" * (W - 4))
        print(f"  {'หุ้น':<12}{'ราคา':>10}{'มูลค่า':>11}{'ส่วนลด':>9}"
              f"{'โซน':>12}{'เชื่อถือ':>10}{'ปี':>4}  ชื่อบริษัท")
        for _, r in under.iterrows():
            print(f"  {r['ticker']:<12}{r['ราคา']:>10,.2f}{r['มูลค่าที่ประเมินได้']:>11,.2f}"
                  f"{r['ส่วนลด (%)']:>8,.0f}%{r['โซน']:>12}"
                  f"{r['ความน่าเชื่อถือ']:>8}{r['คะแนน']:>3.0f}{r['ปีข้อมูล']:>4.0f}"
                  f"  {str(r['ชื่อบริษัท'])[:38]}")

    if not bad.empty:
        print(f"\n  วิเคราะห์ไม่สำเร็จ {len(bad)} ตัว")
        print("  " + "-" * (W - 4))
        for _, r in bad.iterrows():
            print(f"  {r['ticker']:<12} {str(r['ปัญหา'])[:80]}")

    print("\n" + "=" * W)
    print("  ⚠️ ส่วนลดมากไม่ได้แปลว่าหุ้นดี — มักมีเหตุผลที่ตลาดให้ราคาต่ำ")
    print("     ให้ดูคะแนนความน่าเชื่อถือควบคู่เสมอ และเปิดรายงานฉบับเต็มก่อนตัดสินใจ")
    print("     เอกสารนี้เพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน")
    print("=" * W)


# ---------------------------------------------------------------------------
# รันจาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="สแกนและเปรียบเทียบหุ้น",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ตัวอย่างการใช้งาน
------------------
  คัดกรองเร็วทั้งตลาดสหรัฐ (ราว 20 นาที) แล้วบันทึกไฟล์
    python3 screener.py --quick --list us-all --csv us_all.csv

  คัดกรองเร็วหุ้นไทยทั้งหมด พร้อมกรอง P/E < 15 และ ROE > 12%
    python3 screener.py --quick --list thai --max-pe 15 --min-roe 12 --rf 0.025

  วิเคราะห์ลึกเฉพาะตัวที่คัดมาแล้ว
    python3 screener.py PTT.BK KBANK.BK AOT.BK --rf 0.025

  เปรียบเทียบหุ้น 2-10 ตัว
    python3 screener.py --compare AAPL MSFT GOOGL NVDA
""")
    p.add_argument("tickers", nargs="*", help="ชื่อย่อหุ้น เว้นวรรคคั่น")
    p.add_argument("--list", choices=["thai", "set", "mai", "us", "us-all", "all"],
                   help="ใช้ชุดหุ้นสำเร็จรูป")
    p.add_argument("--quick", action="store_true",
                   help="ใช้ชั้นคัดกรองเร็ว (รองรับทั้งตลาด ไม่ทำ DCF)")
    p.add_argument("--compare", action="store_true", help="โหมดเปรียบเทียบ 2-10 ตัว")
    p.add_argument("--max", type=int, help="จำนวนสูงสุดที่จะสแกน")
    p.add_argument("--workers", type=int, default=8, help="จำนวนเส้นที่ดึงพร้อมกัน")
    p.add_argument("--rf", type=float, help="อัตราพันธบัตร (หุ้นไทยใส่ 0.025)")
    p.add_argument("--mos", type=float, help="ส่วนเผื่อความปลอดภัย")
    p.add_argument("--min-discount", type=float, default=0.0)
    # ตัวกรองของชั้นคัดกรองเร็ว
    p.add_argument("--max-pe", type=float)
    p.add_argument("--max-pbv", type=float)
    p.add_argument("--min-roe", type=float)
    p.add_argument("--min-fcf-yield", type=float)
    p.add_argument("--min-mcap", type=float, help="มูลค่าตลาดขั้นต่ำ (ล้าน)")
    p.add_argument("--min-div", type=float)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--csv", help="บันทึกผลเป็นไฟล์ CSV")
    args = p.parse_args()

    tickers = list(args.tickers)
    if args.list:
        tickers += preset(args.list)
    if not tickers:
        p.error("ต้องระบุชื่อหุ้น หรือใช้ --list")

    # ---------- โหมดเปรียบเทียบ ----------
    if args.compare:
        try:
            res = compare(tickers, rf=args.rf, mos=args.mos, refresh=args.refresh,
                          progress=lambda i, n, t: print(f"  [{i}/{n}] {t} ...", flush=True))
        except ValueError as e:
            print(f"\n[ไม่สำเร็จ] {e}\n", file=sys.stderr)
            return 1
        t = res["table"]
        if t.empty:
            print("\nวิเคราะห์ไม่สำเร็จสักตัว")
            return 1
        print("\n" + "=" * 100)
        print("  เปรียบเทียบหุ้น")
        print("=" * 100)
        with pd.option_context("display.max_columns", None, "display.width", 200):
            print(t.to_string())
        w = res.get("winner")
        if w:
            print(f"\n  ตัวเลขน่าสนใจที่สุด : {w['ticker']} "
                  f"(ส่วนลด {w['ส่วนลด (%)']:.0f}% · ความน่าเชื่อถือ {w['ความน่าเชื่อถือ']})")
            print("  หมายเหตุ : ให้น้ำหนัก 'ส่วนลด' กับ 'ความน่าเชื่อถือ' เท่ากัน")
            print("             ไม่ใช่คำแนะนำให้ซื้อ เป็นเพียงการจัดอันดับตัวเลข")
        for tk, err in res["errors"]:
            print(f"  [ไม่สำเร็จ] {tk}: {err[:70]}")
        if args.csv:
            res["raw"].to_csv(args.csv, index=False, encoding="utf-8-sig")
            print(f"\nบันทึกไฟล์แล้ว : {args.csv}")
        return 0

    if args.max:
        tickers = tickers[:args.max]

    # ---------- ชั้นที่ 1 : คัดกรองเร็ว ----------
    if args.quick:
        est = len(tickers) * 1.5 / args.workers / 60
        print(f"\nคัดกรองเร็ว {len(tickers):,} ตัว "
              f"({args.workers} เส้นพร้อมกัน) — คาดว่าราว {est:.0f} นาที\n")
        done = [0]

        def show(i, total, t):
            if i % 25 == 0 or i == total:
                print(f"  {i:,}/{total:,} ...", flush=True)

        df = quick_screen(tickers, workers=args.workers, progress=show)
        got = df[df["ปัญหา"].eq("")]
        out = quick_filter(df, max_pe=args.max_pe, max_pbv=args.max_pbv,
                           min_roe=args.min_roe, min_fcf_yield=args.min_fcf_yield,
                           min_mcap=args.min_mcap, min_div=args.min_div)
        out = out.sort_values("P/E", na_position="last")
        print(f"\n  ดึงข้อมูลได้ {len(got):,} / {len(df):,} ตัว · ผ่านเกณฑ์ {len(out):,} ตัว\n")
        cols = ["ticker", "ชื่อบริษัท", "ราคา", "P/E", "P/BV", "ROE (%)",
                "FCF Yield (%)", "ปันผล (%)", "มูลค่าตลาด (ล้าน)"]
        with pd.option_context("display.max_rows", 80, "display.width", 200):
            print(out[cols].head(60).to_string(index=False))
        print("\n  ⚠️ นี่คือการคัดกรองชั้นแรกจากตัวเลขสรุปเท่านั้น ยังไม่ได้ประเมินมูลค่า")
        print("     ขั้นต่อไป : เอารายชื่อที่ผ่านเกณฑ์ไปวิเคราะห์ลึกด้วยคำสั่ง")
        print("     python3 screener.py <ชื่อหุ้นที่ผ่าน> --rf 0.025")
        if args.csv:
            out.to_csv(args.csv, index=False, encoding="utf-8-sig")
            print(f"\nบันทึกไฟล์แล้ว : {args.csv}")
        return 0

    # ---------- ชั้นที่ 2 : วิเคราะห์ลึก ----------
    if len(tickers) > 60:
        print(f"\n[หยุด] เลือกมา {len(tickers):,} ตัว — วิเคราะห์ลึกมากขนาดนี้จะใช้เวลา "
              f"{len(tickers)*30/3600:.0f} ชั่วโมง", file=sys.stderr)
        print("  ให้ใช้ --quick คัดกรองก่อน แล้วค่อยวิเคราะห์ลึกเฉพาะตัวที่ผ่าน\n",
              file=sys.stderr)
        return 1

    est = len(tickers) * 30 / 60
    print(f"\nกำลังวิเคราะห์ลึก {len(tickers)} ตัว — คาดว่าใช้เวลาราว {est:.0f} นาที")
    print("(ตัวที่เคยวิเคราะห์แล้วภายใน 24 ชม. จะเร็วมาก)\n")

    def show(i, total, t):
        print(f"  [{i}/{total}] {t} ...", flush=True)

    df = scan(tickers, rf=args.rf, mos=args.mos,
              refresh=args.refresh, progress=show)
    print()
    print_report(df, args.min_discount)

    if args.csv:
        df.to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"\nบันทึกไฟล์แล้ว : {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
