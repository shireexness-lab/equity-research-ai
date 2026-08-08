"""
tools_verify.py — ตรวจสอบว่าตัวเลขในตารางคัดกรองตรงกับแหล่งข้อมูลจริงไหม
==========================================================================
ใช้เมื่อไร : เมื่อเห็นตัวเลขในตารางแล้วรู้สึกว่า "ไม่น่าจะใช่"

สิ่งที่ทำ
---------
1. ดึงค่าดิบจาก yfinance ของหุ้นที่ระบุ แสดงให้เห็นทุกตัวก่อนแปลง
2. แสดงค่าที่ตารางคัดกรองคำนวณออกมา วางคู่กัน
3. **คำนวณ D/E จากงบดุลจริง 2 แบบ** แล้วเทียบกับที่ yfinance ให้มา
   - แบบที่ 1 หนี้ที่มีดอกเบี้ย ÷ ส่วนของผู้ถือหุ้น   (ที่ตารางใช้)
   - แบบที่ 2 หนี้สินรวม ÷ ส่วนของผู้ถือหุ้น          (ตามตำรา)

ทำไมต้องมีเครื่องมือนี้
------------------------
เวลาสงสัยว่าตัวเลขผิด มีความเป็นไปได้ 3 ทาง และต้องแยกให้ออก
  ก. โค้ดคำนวณผิด            -> เราแก้ได้
  ข. แหล่งข้อมูลให้มาผิด      -> เราแก้ไม่ได้ แต่ติดธงเตือนได้
  ค. ตัวเลขถูก แต่นิยามต่าง   -> ต้องอธิบายให้ชัด ไม่ใช่แก้โค้ด
การเดาโดยไม่ดูค่าดิบทำให้แก้ผิดจุด

วิธีใช้
-------
    python3 tools_verify.py HANA.BK TVO.BK BAM.BK
    python3 tools_verify.py --de          # ตรวจเฉพาะกลุ่มที่ D/E = 0
"""

import argparse
import sys

import pandas as pd

# ตัวอย่างที่น่าสงสัยจากหน้าจอจริง — ใช้เป็นค่าเริ่มต้นเวลาไม่ระบุหุ้น
SUSPECT_ZERO_DE = ["HANA.BK", "TVO.BK", "UTP.BK", "TNH.BK", "CM.BK", "BCT.BK"]
SUSPECT_MARGIN = ["WAVE.BK", "CMR.BK", "BAM.BK", "THANI.BK", "TCAP.BK"]


def _f(x, dec=2):
    if x is None:
        return "—"
    try:
        return f"{float(x):,.{dec}f}"
    except (TypeError, ValueError):
        return str(x)


def _row(bs, *names):
    """หาค่าจากงบดุล โดยลองหลายชื่อบรรทัด (yfinance ตั้งชื่อไม่เหมือนกันทุกตัว)"""
    if bs is None or bs.empty:
        return None
    for n in names:
        if n in bs.index:
            s = bs.loc[n].dropna()
            if len(s):
                return float(s.iloc[0])
    return None


def check(ticker: str):
    import yfinance as yf
    from screener import is_financial_sector, quick_one

    print("\n" + "=" * 74)
    print(f"  {ticker}")
    print("=" * 74)

    t = yf.Ticker(ticker)
    try:
        info = t.info or {}
    except Exception as e:
        print(f"  ดึงข้อมูลไม่สำเร็จ: {type(e).__name__}: {e}")
        return

    print(f"  {info.get('longName', ticker)}")
    print(f"  กลุ่ม: {info.get('sector','-')}"
          + ("   << กลุ่มการเงิน" if is_financial_sector(info.get('sector')) else ""))

    # ---------- ค่าดิบจาก Yahoo ----------
    print("\n  [1] ค่าดิบที่ Yahoo ส่งมา (ยังไม่แปลงหน่วย)")
    for k in ("debtToEquity", "grossMargins", "profitMargins", "returnOnEquity",
              "trailingPE", "priceToBook", "totalDebt", "totalRevenue",
              "grossProfits", "netIncomeToCommon"):
        v = info.get(k)
        print(f"      {k:<22} {v if v is not None else '(ไม่มี)'}")

    # ---------- ค่าที่ตารางแสดง ----------
    r = quick_one(ticker)
    print("\n  [2] ค่าที่ตารางคัดกรองแสดง")
    if r.get("ปัญหา"):
        print(f"      ปัญหา: {r['ปัญหา']}")
    else:
        for k in ("ราคา", "P/E", "P/BV", "D/E", "ROE (%)",
                  "อัตรากำไรขั้นต้น (%)", "อัตรากำไรสุทธิ (%)"):
            print(f"      {k:<22} {_f(r.get(k))}")

    # ---------- คำนวณเองจากงบดุล ----------
    print("\n  [3] คำนวณเองจากงบดุลจริง (ตรวจว่านิยามตรงกันไหม)")
    try:
        bs = t.balance_sheet
    except Exception as e:
        print(f"      ดึงงบดุลไม่สำเร็จ: {e}")
        return
    if bs is None or bs.empty:
        print("      ไม่มีงบดุล")
        return

    eq = _row(bs, "Stockholders Equity", "Total Stockholder Equity",
              "Common Stock Equity")
    liab = _row(bs, "Total Liabilities Net Minority Interest", "Total Liab")
    sd = _row(bs, "Current Debt", "Short Long Term Debt", "Current Debt And Capital Lease Obligation") or 0
    ld = _row(bs, "Long Term Debt", "Long Term Debt And Capital Lease Obligation") or 0
    td = _row(bs, "Total Debt")
    if td is None:
        td = sd + ld

    print(f"      งบ ณ วันที่           {bs.columns[0].date() if len(bs.columns) else '-'}")
    print(f"      ส่วนของผู้ถือหุ้น      {_f(eq, 0)}")
    print(f"      หนี้สินรวม            {_f(liab, 0)}")
    print(f"      หนี้ที่มีดอกเบี้ย      {_f(td, 0)}")

    de_debt = td / eq if eq else None
    de_liab = liab / eq if (eq and liab is not None) else None
    yf_de = info.get("debtToEquity")
    yf_de = yf_de / 100 if yf_de is not None else None

    print()
    print(f"      D/E แบบหนี้มีดอกเบี้ย  {_f(de_debt)}   <- นิยามที่ตารางใช้")
    print(f"      D/E แบบหนี้สินรวม     {_f(de_liab)}   <- นิยามตามตำรา")
    print(f"      D/E ที่ Yahoo ให้มา    {_f(yf_de)}")

    if de_debt is not None and yf_de is not None:
        gap = abs(de_debt - yf_de)
        verdict = ("ตรงกัน — ยืนยันว่า Yahoo ใช้หนี้ที่มีดอกเบี้ย"
                   if gap < 0.05 else
                   f"ต่างกัน {gap:.2f} — ต้องตรวจสอบเพิ่ม")
        print(f"      ผลเทียบ               {verdict}")
    if de_debt is not None and de_liab is not None:
        print(f"      สองนิยามต่างกัน        {_f(de_liab - de_debt)} เท่า"
              "   <- นี่คือเหตุผลที่ตัวเลขดูต่ำกว่าที่คาด")


def main() -> int:
    p = argparse.ArgumentParser(
        description="ตรวจว่าตัวเลขในตารางตรงกับงบการเงินจริงไหม")
    p.add_argument("tickers", nargs="*", help="ชื่อย่อหุ้น เช่น HANA.BK")
    p.add_argument("--de", action="store_true",
                   help=f"ตรวจกลุ่มที่ D/E = 0 ({', '.join(SUSPECT_ZERO_DE)})")
    p.add_argument("--margin", action="store_true",
                   help=f"ตรวจกลุ่มที่อัตรากำไรผิดปกติ ({', '.join(SUSPECT_MARGIN)})")
    a = p.parse_args()

    tickers = list(a.tickers)
    if a.de:
        tickers += SUSPECT_ZERO_DE
    if a.margin:
        tickers += SUSPECT_MARGIN
    if not tickers:
        tickers = SUSPECT_ZERO_DE[:3] + SUSPECT_MARGIN[:2]
        print("\n(ไม่ได้ระบุหุ้น — ใช้ตัวอย่างที่น่าสงสัยจากหน้าจอ)")

    for t in dict.fromkeys(tickers):
        try:
            check(t.upper())
        except KeyboardInterrupt:
            return 1
        except Exception as e:
            print(f"\n  [ผิดพลาด] {t}: {type(e).__name__}: {e}")

    print("\n" + "=" * 74)
    print("  วิธีอ่านผล")
    print("=" * 74)
    print("  ถ้า [2] ตรงกับ [1] ที่แปลงหน่วยแล้ว  -> โค้ดคำนวณถูก")
    print("  ถ้า D/E สองนิยามต่างกันมาก           -> ตัวเลขถูก แต่นิยามไม่ใช่ที่คิด")
    print("  ถ้า [1] ว่างแต่ [2] มีตัวเลข          -> โค้ดเดาค่าแทน = บั๊ก ต้องแจ้ง\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
