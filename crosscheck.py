"""
crosscheck.py — ตรวจสอบว่าตัวเลขสรุปตรงกับงบการเงินจริงไหม
==============================================================
คำถามที่ตอบ : "ข้อมูลจาก Yahoo ผิดได้ไหม แล้วเราจะรู้ได้ยังไง"

คำตอบสั้น ๆ : ผิดได้ และผิดจริงเป็นประจำ

Yahoo ผิดได้อย่างไรบ้าง (พบจริงทั้งหมด)
----------------------------------------
1. **ตัวเลขค้างจากงวดเก่า** — ราคาอัปเดตทุกวินาที แต่ EPS อาจยังเป็นของไตรมาสก่อน
   ผลคือ P/E ที่ได้เป็นการเอาราคาใหม่หารกำไรเก่า
2. **หน่วยผิด** — บางบริษัทรายงานเป็นพันหน่วย บางบริษัทเป็นล้าน ถ้าแปลงพลาดจะเพี้ยน 1,000 เท่า
3. **ยังไม่ปรับการแตกพาร์** — หุ้นแตกพาร์แล้วราคาลดครึ่ง แต่ EPS ยังเป็นค่าเดิม P/E จึงต่ำผิดปกติ
4. **นับรายการพิเศษรวมเข้าไป** — กำไรจากการขายที่ดินก้อนเดียวทำให้ P/E ดูถูกมาก
5. **สกุลเงินปน** — บริษัทไทยที่รายงานเป็น USD แต่ราคาซื้อขายเป็นบาท
6. **หุ้นเล็กที่ไม่มีคนดูแลข้อมูล** — ยิ่งบริษัทเล็ก ข้อมูลยิ่งขาดและยิ่งเก่า

วิธีป้องกัน — คำนวณเองแล้วเทียบ
--------------------------------
Yahoo ส่งข้อมูลมา 2 ชุดที่ **มาจากคนละท่อ**

    ท่อที่ 1  info          = ตัวเลขสรุปสำเร็จรูป (P/E, ROE, D/E)
    ท่อที่ 2  financials    = งบการเงินดิบรายปี/รายไตรมาส

ถ้าเราเอางบดิบมาคำนวณ P/E เองแล้วได้ตรงกับที่ Yahoo สรุปให้
แปลว่าตัวเลขนั้น **ผ่านการตรวจสอบจากสองทาง** ความมั่นใจสูงขึ้นมาก

ถ้าไม่ตรง แปลว่ามีอย่างน้อยหนึ่งชุดผิด — และนั่นคือสิ่งที่เราต้องรู้ก่อนตัดสินใจ

ข้อจำกัดที่ต้องยอมรับ
---------------------
วิธีนี้ตรวจได้แค่ "สองท่อของ Yahoo ตรงกันไหม" ไม่ได้ยืนยันว่าตรงกับงบที่บริษัทยื่นจริง
ถ้าต้นทางป้อนข้อมูลผิดตั้งแต่แรก ทั้งสองท่อก็ผิดเหมือนกัน

การยืนยันขั้นสุดท้ายต้องเทียบกับต้นฉบับ :
    หุ้นสหรัฐ  ->  SEC EDGAR (ทำแล้วใน edgar_layer.py — เป็นงบที่ยื่นจริงตามกฎหมาย)
    หุ้นไทย    ->  แบบ 56-1 One Report บนเว็บ SET (ยังต้องเปิดดูเอง)

วิธีใช้
-------
    python3 crosscheck.py PTT.BK ADVANC.BK
    python3 crosscheck.py AAPL --json
"""

import argparse
import json
import sys

import numpy as np
import pandas as pd

# ยอมให้ต่างกันได้กี่ % ก่อนถือว่า "ไม่ตรงกัน"
#
# ทำไมไม่ใช้ 0% : งบที่ Yahoo ใช้สรุปเป็นแบบ 12 เดือนล่าสุด (TTM)
# ส่วนงบรายปีที่เราดึงมาเป็นปีบัญชี จึงคนละช่วงเวลากันเล็กน้อยเป็นเรื่องปกติ
TOL_OK = 5.0        # ต่างไม่เกิน 5%  = ตรงกัน
TOL_WARN = 20.0     # ต่าง 5-20%     = ต่างช่วงเวลา พออธิบายได้
                    # ต่างเกิน 20%   = น่าสงสัย ต้องเปิดงบดูเอง


def _f(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _pick(df, *names):
    """หาค่าล่าสุดจากงบ โดยลองหลายชื่อบรรทัด — yfinance ตั้งชื่อไม่เหมือนกันทุกตัว"""
    if df is None or getattr(df, "empty", True):
        return None
    for n in names:
        if n in df.index:
            s = df.loc[n].dropna()
            if len(s):
                return _f(s.iloc[0])
    return None


def _diff_pct(mine, theirs):
    """ต่างกันกี่ % — ใช้ค่าที่ Yahoo ให้เป็นฐาน"""
    if mine is None or theirs is None or theirs == 0:
        return None
    return abs(mine - theirs) / abs(theirs) * 100


def _verdict(d):
    if d is None:
        return "เทียบไม่ได้"
    if d <= TOL_OK:
        return "ตรงกัน"
    if d <= TOL_WARN:
        return "ต่างเล็กน้อย"
    return "ไม่ตรงกัน"


def crosscheck_one(ticker: str) -> dict:
    """
    ตรวจหุ้น 1 ตัว — คืน dict ที่มีรายการเทียบทีละตัวเลข

    ใช้เวลาราว 2-4 วินาทีต่อหุ้น เพราะต้องดึงงบเพิ่มจากที่ดึงตอนคัดกรอง
    จึงเหมาะกับ "หุ้นที่คัดมาแล้วหลักสิบตัว" ไม่ใช่ทั้งตลาด
    """
    import yfinance as yf

    out = {"ticker": ticker, "รายการ": [], "ปัญหา": ""}
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        inc = t.income_stmt
        bs = t.balance_sheet
    except Exception as e:
        out["ปัญหา"] = f"{type(e).__name__}: {str(e)[:70]}"
        return out

    out["ชื่อบริษัท"] = info.get("longName") or ticker
    out["สกุลเงิน"] = info.get("currency") or ""

    price = _f(info.get("currentPrice") or info.get("regularMarketPrice")
               or info.get("previousClose"))
    shares = _f(info.get("sharesOutstanding"))

    rev = _pick(inc, "Total Revenue", "Operating Revenue")
    net = _pick(inc, "Net Income", "Net Income Common Stockholders",
                "Net Income Including Noncontrolling Interests")
    eq = _pick(bs, "Stockholders Equity", "Total Stockholder Equity",
               "Common Stock Equity")
    liab = _pick(bs, "Total Liabilities Net Minority Interest", "Total Liab")
    debt = _pick(bs, "Total Debt")
    if debt is None:
        sd = _pick(bs, "Current Debt", "Current Debt And Capital Lease Obligation") or 0
        ld = _pick(bs, "Long Term Debt", "Long Term Debt And Capital Lease Obligation") or 0
        debt = sd + ld if (sd or ld) else None

    if inc is not None and not getattr(inc, "empty", True) and len(inc.columns):
        out["งบปีล่าสุด"] = str(inc.columns[0])[:10]

    def add(name, mine, theirs, note=""):
        d = _diff_pct(mine, theirs)
        out["รายการ"].append({
            "ตัวเลข": name,
            "คำนวณเอง": mine,
            "Yahoo สรุป": theirs,
            "ต่างกัน (%)": round(d, 1) if d is not None else None,
            "ผล": _verdict(d),
            "หมายเหตุ": note,
        })

    # ---- P/E : ราคา / กำไรต่อหุ้น ----
    eps_calc = (net / shares) if (net and shares) else None
    add("P/E",
        (price / eps_calc) if (price and eps_calc and eps_calc > 0) else None,
        _f(info.get("trailingPE")),
        "ราคา ÷ (กำไรสุทธิ ÷ จำนวนหุ้น)")

    # ---- P/BV : ราคา / มูลค่าทางบัญชีต่อหุ้น ----
    bvps = (eq / shares) if (eq and shares) else None
    add("P/BV",
        (price / bvps) if (price and bvps and bvps > 0) else None,
        _f(info.get("priceToBook")),
        "ราคา ÷ (ส่วนของผู้ถือหุ้น ÷ จำนวนหุ้น)")

    # ---- อัตรากำไรสุทธิ ----
    add("อัตรากำไรสุทธิ (%)",
        (net / rev * 100) if (net is not None and rev) else None,
        (_f(info.get("profitMargins")) * 100
         if _f(info.get("profitMargins")) is not None else None),
        "กำไรสุทธิ ÷ รายได้")

    # ---- ROE ----
    add("ROE (%)",
        (net / eq * 100) if (net is not None and eq) else None,
        (_f(info.get("returnOnEquity")) * 100
         if _f(info.get("returnOnEquity")) is not None else None),
        "กำไรสุทธิ ÷ ส่วนของผู้ถือหุ้น")

    # ---- D/E : ตรวจทั้งสองนิยาม ----
    yf_de = _f(info.get("debtToEquity"))
    yf_de = yf_de / 100 if yf_de is not None else None
    add("D/E (หนี้มีดอกเบี้ย)",
        (debt / eq) if (debt is not None and eq) else None, yf_de,
        "เงินกู้ระยะสั้น+ยาว ÷ ส่วนทุน — นิยามที่ตารางใช้")
    out["D/E แบบหนี้สินรวม"] = round(liab / eq, 2) if (liab and eq) else None

    ok = sum(1 for r in out["รายการ"] if r["ผล"] == "ตรงกัน")
    bad = sum(1 for r in out["รายการ"] if r["ผล"] == "ไม่ตรงกัน")
    n = sum(1 for r in out["รายการ"] if r["ผล"] != "เทียบไม่ได้")
    out["สรุป"] = {"ตรวจได้": n, "ตรงกัน": ok, "ไม่ตรงกัน": bad,
                   "คะแนนความน่าเชื่อถือ": round(ok / n * 100) if n else None}
    return out


def crosscheck(tickers, progress=None) -> pd.DataFrame:
    """ตรวจหลายตัว — คืนตารางสรุปหนึ่งแถวต่อหุ้น"""
    rows = []
    tickers = list(dict.fromkeys(tickers))
    for i, t in enumerate(tickers, 1):
        if progress:
            progress(i, len(tickers), t)
        r = crosscheck_one(t)
        s = r.get("สรุป") or {}
        row = {"ticker": t, "ชื่อบริษัท": r.get("ชื่อบริษัท", ""),
               "ตรวจได้": s.get("ตรวจได้"), "ตรงกัน": s.get("ตรงกัน"),
               "ไม่ตรงกัน": s.get("ไม่ตรงกัน"),
               "ความน่าเชื่อถือ (%)": s.get("คะแนนความน่าเชื่อถือ"),
               "ปัญหา": r.get("ปัญหา", "")}
        for item in r.get("รายการ", []):
            row[item["ตัวเลข"]] = item["ผล"]
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# ใช้จาก Terminal
# ---------------------------------------------------------------------------

def _print(r: dict):
    print("\n" + "=" * 78)
    print(f"  {r['ticker']}  —  {r.get('ชื่อบริษัท','')}")
    if r.get("งบปีล่าสุด"):
        print(f"  งบปีล่าสุดที่ใช้เทียบ: {r['งบปีล่าสุด']}  ·  "
              f"สกุลเงิน: {r.get('สกุลเงิน','-')}")
    print("=" * 78)
    if r.get("ปัญหา"):
        print(f"  ดึงข้อมูลไม่สำเร็จ: {r['ปัญหา']}\n")
        return

    print(f"\n  {'ตัวเลข':<26}{'คำนวณเอง':>12}{'Yahoo':>12}{'ต่าง %':>9}  ผล")
    print("  " + "-" * 74)
    for it in r["รายการ"]:
        def fmt(v):
            return f"{v:,.2f}" if isinstance(v, (int, float)) and v is not None else "—"
        mark = {"ตรงกัน": "  ", "ต่างเล็กน้อย": "~ ", "ไม่ตรงกัน": "! ",
                "เทียบไม่ได้": "? "}[it["ผล"]]
        d = it["ต่างกัน (%)"]
        d_txt = f"{d:.1f}" if d is not None else "—"
        print(f"  {mark}{it['ตัวเลข']:<24}{fmt(it['คำนวณเอง']):>12}"
              f"{fmt(it['Yahoo สรุป']):>12}{d_txt:>9}  {it['ผล']}")

    for it in r["รายการ"]:
        if it["ผล"] in ("ไม่ตรงกัน", "เทียบไม่ได้"):
            print(f"\n  [{it['ตัวเลข']}] {it['หมายเหตุ']}")

    if r.get("D/E แบบหนี้สินรวม") is not None:
        print(f"\n  D/E ถ้าใช้หนี้สินรวมทั้งงบดุล = {r['D/E แบบหนี้สินรวม']:,.2f} เท่า")
        print("  (ตารางคัดกรองใช้เฉพาะหนี้ที่มีดอกเบี้ย จึงได้ค่าต่ำกว่านี้)")

    s = r["สรุป"]
    print(f"\n  สรุป : ตรวจได้ {s['ตรวจได้']} รายการ · ตรงกัน {s['ตรงกัน']} · "
          f"ไม่ตรงกัน {s['ไม่ตรงกัน']}")
    score = s["คะแนนความน่าเชื่อถือ"]
    if score is not None:
        note = ("เชื่อถือได้" if score >= 80 else
                "ใช้ได้แต่ควรเปิดงบดูประกอบ" if score >= 50 else
                "ไม่ควรใช้ตัดสินใจ — เปิดงบจริงก่อน")
        print(f"  ความน่าเชื่อถือ : {score}%  ({note})")
    print()


def main() -> int:
    p = argparse.ArgumentParser(
        description="ตรวจว่าตัวเลขสรุปของ Yahoo ตรงกับงบการเงินจริงไหม")
    p.add_argument("tickers", nargs="+", help="ชื่อย่อหุ้น เช่น PTT.BK AAPL")
    p.add_argument("--json", action="store_true", help="แสดงผลเป็น JSON")
    a = p.parse_args()

    results = []
    for t in a.tickers:
        r = crosscheck_one(t.upper())
        results.append(r)
        if not a.json:
            _print(r)

    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=1, default=str))
    else:
        print("=" * 78)
        print("  วิธีอ่านผล")
        print("=" * 78)
        print("  ตรงกัน        ตัวเลขผ่านการตรวจจากสองทาง เชื่อถือได้")
        print("  ต่างเล็กน้อย   มักเป็นเพราะ Yahoo ใช้ 12 เดือนล่าสุด แต่งบเป็นรายปี")
        print("  ไม่ตรงกัน     ต้องเปิดงบจริงดูก่อนใช้ตัดสินใจ")
        print("  เทียบไม่ได้    งบขาดบรรทัดที่ต้องใช้ — พบบ่อยในหุ้นเล็กและกลุ่มการเงิน\n")
        print("  ข้อจำกัด : วิธีนี้ตรวจได้แค่ว่าข้อมูลสองชุดของ Yahoo ตรงกันไหม")
        print("  ไม่ได้ยืนยันว่าตรงกับงบที่บริษัทยื่นจริง")
        print("  หุ้นสหรัฐยืนยันได้ด้วย SEC EDGAR (โหมดวิเคราะห์รายตัวใช้อยู่แล้ว)")
        print("  หุ้นไทยต้องเปิดแบบ 56-1 One Report บนเว็บ SET ประกอบ\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
