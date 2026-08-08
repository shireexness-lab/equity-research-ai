"""
statements.py — Part 2 : Financial Statement Analyzer
======================================================
หน้าที่ : วิเคราะห์งบ 3 ตัว → YoY, CAGR, Common Size (แนวตั้ง/แนวนอน)

ศัพท์ที่ต้องเข้าใจก่อน
----------------------
YoY (Year over Year)  = โตกี่ % เทียบกับปีก่อนหน้า
CAGR                  = อัตราโตทบต้นเฉลี่ยต่อปี ตลอดช่วงที่ดู
                        **ระวัง** 4 ปีข้อมูล = ช่วงเวลา 3 ปี (ไม่ใช่ 4)
Common Size แนวตั้ง   = ทุกบรรทัดคิดเป็น % ของยอดฐาน
                        งบกำไรขาดทุน ใช้ "รายได้รวม" เป็นฐาน
                        งบดุล ใช้ "สินทรัพย์รวม" เป็นฐาน
                        → ใช้ดูโครงสร้าง เช่น ต้นทุนกินรายได้กี่ % และเปลี่ยนไปไหม
Common Size แนวนอน    = ตั้งปีแรก = 100 แล้วดูปีอื่นเทียบ
                        → ใช้ดูว่าอะไรโตเร็วกว่าอะไร เช่น ค่าใช้จ่ายโตเร็วกว่ารายได้ไหม

วิธีใช้จาก Terminal
-------------------
    python3 statements.py AAPL
    python3 statements.py PTT.BK
"""

import argparse
import sys

import pandas as pd

from data_layer import find_row, get_stock_data, get_years

# ---------------------------------------------------------------------------
# ชื่อบรรทัดสำคัญ — เขียนหลายชื่อเผื่อ yfinance ตั้งชื่อต่างกันในแต่ละหุ้น
# ---------------------------------------------------------------------------

# บรรทัดที่เป็น "ต่อหุ้น" — ห้ามหารด้วยล้านเหมือนบรรทัดอื่น
#
# ทำไมต้องมีรายชื่อนี้ : ตารางงบแสดงหน่วยเป็นล้านบาท จึงหารทั้งตารางด้วย 1e6
# แต่กำไรต่อหุ้นเป็นบาทต่อหุ้นอยู่แล้ว ถ้าหารด้วยล้านซ้ำ EPS 0.42 บาท
# จะกลายเป็น 0.00000042 แล้วปัดแสดงเป็น 0 หรือ "<1" ซึ่งอ่านผิดความหมายทั้งหมด
PER_SHARE_LINES = {
    "กำไรต่อหุ้น (Diluted)",
    "กำไรต่อหุ้น (Basic)",
    "เงินปันผลต่อหุ้น",
    "มูลค่าทางบัญชีต่อหุ้น",
}


def scale_for_display(df, unit=1e6, dec_normal=0, dec_per_share=2):
    """
    เตรียมงบให้พร้อมแสดงผล — หารเฉพาะบรรทัดที่เป็นจำนวนเงิน

    คืน (DataFrame ที่ปรับหน่วยแล้ว, dict ทศนิยมรายบรรทัด)
    """
    import pandas as _pd
    out = df.copy()
    dec_rows = {}
    for name in out.index:
        if name in PER_SHARE_LINES:
            dec_rows[name] = dec_per_share          # ไม่หาร เก็บค่าเดิม
        else:
            out.loc[name] = _pd.to_numeric(out.loc[name], errors="coerce") / unit
            dec_rows[name] = dec_normal
    return out, dec_rows


KEY_INCOME_LINES = [
    ("รายได้รวม",            ["Total Revenue", "Operating Revenue"]),
    ("ต้นทุนขาย",            ["Cost Of Revenue", "Reconciled Cost Of Revenue"]),
    ("กำไรขั้นต้น",           ["Gross Profit"]),
    ("ค่าใช้จ่ายดำเนินงาน",   ["Operating Expense"]),
    ("วิจัยและพัฒนา",        ["Research And Development"]),
    ("กำไรจากการดำเนินงาน",  ["Operating Income", "Total Operating Income As Reported"]),
    ("EBITDA",               ["EBITDA", "Normalized EBITDA"]),
    ("EBIT",                 ["EBIT"]),
    ("กำไรก่อนภาษี",         ["Pretax Income"]),
    ("กำไรสุทธิ",            ["Net Income", "Net Income Common Stockholders"]),
    ("กำไรต่อหุ้น (Diluted)", ["Diluted EPS"]),
]

KEY_BALANCE_LINES = [
    ("สินทรัพย์รวม",         ["Total Assets"]),
    ("สินทรัพย์หมุนเวียน",    ["Current Assets"]),
    ("เงินสด",               ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]),
    ("สินค้าคงเหลือ",        ["Inventory"]),
    ("ลูกหนี้การค้า",         ["Accounts Receivable", "Receivables"]),
    ("หนี้สินรวม",           ["Total Liabilities Net Minority Interest"]),
    ("หนี้สินหมุนเวียน",      ["Current Liabilities"]),
    ("หนี้สินมีดอกเบี้ยรวม",  ["Total Debt"]),
    ("หนี้สินสุทธิ",          ["Net Debt"]),
    ("ส่วนของผู้ถือหุ้น",     ["Stockholders Equity", "Total Equity Gross Minority Interest"]),
    ("เงินลงทุนในกิจการ",     ["Invested Capital"]),
]

KEY_CASHFLOW_LINES = [
    ("กระแสเงินสดดำเนินงาน", ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]),
    ("ค่าเสื่อม+ตัดจำหน่าย",  ["Depreciation And Amortization", "Depreciation Amortization Depletion"]),
    ("เงินลงทุนในสินทรัพย์",  ["Capital Expenditure", "Purchase Of PPE"]),
    ("กระแสเงินสดอิสระ",     ["Free Cash Flow"]),
    ("เงินปันผลจ่าย",        ["Cash Dividends Paid", "Common Stock Dividend Paid"]),
    ("ซื้อหุ้นคืน",           ["Repurchase Of Capital Stock", "Common Stock Payments"]),
]


# ---------------------------------------------------------------------------
# สูตรพื้นฐาน
# ---------------------------------------------------------------------------

def cagr(series: pd.Series):
    """
    อัตราโตทบต้นเฉลี่ยต่อปี (%) จาก Series ที่เรียงปีเก่า→ใหม่

    สูตร : (ค่าปีสุดท้าย / ค่าปีแรก) ^ (1 / จำนวนช่วงปี) − 1

    เงื่อนไขที่คืน None (คำนวณไม่ได้หรือไม่มีความหมาย)
      • มีข้อมูลน้อยกว่า 2 ปี
      • ค่าปีแรก ≤ 0  (เช่นเคยขาดทุน — คิด CAGR ไม่ได้ทางคณิตศาสตร์)
      • ค่าปีสุดท้าย ≤ 0
    """
    if series is None:
        return None
    s = pd.Series(series).dropna()
    if len(s) < 2:
        return None
    first, last = float(s.iloc[0]), float(s.iloc[-1])
    periods = len(s) - 1          # ← จุดที่คนพลาดบ่อยที่สุด
    if first <= 0 or last <= 0:
        return None
    return ((last / first) ** (1.0 / periods) - 1.0) * 100.0


def yoy(series: pd.Series) -> pd.Series:
    """เปลี่ยนแปลง % เทียบปีก่อนหน้า — ปีแรกจะเป็นค่าว่างเสมอ"""
    if series is None:
        return pd.Series(dtype=float)
    s = pd.Series(series).astype(float)
    return s.pct_change(fill_method=None) * 100.0


def common_size_vertical(df: pd.DataFrame, base_names) -> pd.DataFrame:
    """
    ทุกบรรทัด ÷ บรรทัดฐาน × 100
      งบกำไรขาดทุน → ฐานคือ "รายได้รวม"
      งบดุล        → ฐานคือ "สินทรัพย์รวม"
    """
    if df is None or df.empty:
        return pd.DataFrame()
    base = find_row(df, base_names)
    if base is None:
        return pd.DataFrame()
    base = base.replace(0, pd.NA)
    return df.div(base, axis=1) * 100.0


def common_size_horizontal(df: pd.DataFrame) -> pd.DataFrame:
    """ตั้งปีแรก = 100 แล้วเทียบปีอื่น (ดูว่าอะไรโตเร็วกว่าอะไร)"""
    if df is None or df.empty:
        return pd.DataFrame()
    base = df.iloc[:, 0].replace(0, pd.NA)
    return df.div(base, axis=0) * 100.0


# ---------------------------------------------------------------------------
# ประกอบตารางสรุป
# ---------------------------------------------------------------------------

def _extract(df: pd.DataFrame, line_defs, years):
    """ดึงบรรทัดสำคัญออกมาเป็นตารางเดียว (แถว = ชื่อไทย, คอลัมน์ = ปี)"""
    rows = {}
    for thai_name, candidates in line_defs:
        row = find_row(df, candidates)
        if row is None:
            rows[thai_name] = pd.Series([float("nan")] * len(years), index=years)
        else:
            rows[thai_name] = row.reindex(years)
    return pd.DataFrame(rows).T


def analyze(data: dict) -> dict:
    """
    วิเคราะห์งบทั้งหมด คืน dict ที่มี

        years        : รายชื่อปี
        income/balance/cashflow : ตารางบรรทัดสำคัญ (ค่าดิบ)
        yoy_*        : ตาราง YoY %
        cagr_*       : dict {ชื่อบรรทัด: CAGR %}
        vertical_income  : common size แนวตั้งของงบกำไรขาดทุน
        vertical_balance : common size แนวตั้งของงบดุล
        horizontal_income: common size แนวนอนของงบกำไรขาดทุน
    """
    years = get_years(data)
    if not years:
        raise ValueError("ไม่มีข้อมูลงบการเงินให้วิเคราะห์")

    inc = _extract(data["income"], KEY_INCOME_LINES, years)
    bal = _extract(data["balance"], KEY_BALANCE_LINES, years)
    cfs = _extract(data["cashflow"], KEY_CASHFLOW_LINES, years)

    result = {
        "ticker": data.get("ticker"),
        "years": years,
        "income": inc,
        "balance": bal,
        "cashflow": cfs,
        "yoy_income": inc.apply(yoy, axis=1),
        "yoy_balance": bal.apply(yoy, axis=1),
        "yoy_cashflow": cfs.apply(yoy, axis=1),
        "cagr_income": {k: cagr(inc.loc[k]) for k in inc.index},
        "cagr_balance": {k: cagr(bal.loc[k]) for k in bal.index},
        "cagr_cashflow": {k: cagr(cfs.loc[k]) for k in cfs.index},
        "vertical_income": common_size_vertical(
            data["income"], ["Total Revenue", "Operating Revenue"]),
        "vertical_balance": common_size_vertical(
            data["balance"], ["Total Assets"]),
        "horizontal_income": common_size_horizontal(inc),
    }
    return result


# ---------------------------------------------------------------------------
# แสดงผล
# ---------------------------------------------------------------------------

def _fmt_money(v, scale=1e6):
    if pd.isna(v):
        return "-"
    return f"{v/scale:,.0f}"


def _fmt_pct(v):
    if v is None or pd.isna(v):
        return "-"
    return f"{v:+.1f}%"


def _print_block(title, table, yoy_table, cagr_map, years, unit_note="หน่วย: ล้าน"):
    print()
    print(f"  {title}  ({unit_note})")
    print("  " + "-" * (24 + 11 * len(years) + 9))
    header = "  {:<24}".format("") + "".join(f"{y[:4]:>11}" for y in years) + f"{'CAGR':>9}"
    print(header)
    for name in table.index:
        # บรรทัดค่าดิบ
        line = f"  {name:<24}"
        for y in years:
            v = table.loc[name, y]
            # EPS เป็นหน่วยบาท/ดอลลาร์ต่อหุ้น ไม่ต้องหารล้าน
            scale = 1.0 if "ต่อหุ้น" in name else 1e6
            line += f"{_fmt_money(v, scale):>11}"
        c = cagr_map.get(name)
        line += f"{(_fmt_pct(c) if c is not None else '-'):>9}"
        print(line)
        # บรรทัด YoY (เยื้องเข้าไป)
        yline = f"  {'  ↳ YoY':<24}"
        for y in years:
            yline += f"{_fmt_pct(yoy_table.loc[name, y]):>11}"
        print(yline + " " * 9)


def print_report(res: dict) -> None:
    years = res["years"]
    print("=" * (26 + 11 * len(years) + 9))
    print(f"  Part 2 — วิเคราะห์งบการเงิน : {res['ticker']}")
    print("=" * (26 + 11 * len(years) + 9))

    _print_block("งบกำไรขาดทุน", res["income"], res["yoy_income"],
                 res["cagr_income"], years)
    _print_block("งบดุล", res["balance"], res["yoy_balance"],
                 res["cagr_balance"], years)
    _print_block("งบกระแสเงินสด", res["cashflow"], res["yoy_cashflow"],
                 res["cagr_cashflow"], years)

    # Common size แนวตั้ง — เลือกเฉพาะบรรทัดที่ดูแล้วเข้าใจง่าย
    print()
    print("  โครงสร้างงบกำไรขาดทุน (% ของรายได้รวม)")
    print("  " + "-" * (24 + 11 * len(years)))
    print("  {:<24}".format("") + "".join(f"{y[:4]:>11}" for y in years))
    vi = res["vertical_income"]
    for thai, cands in [("ต้นทุนขาย", ["Cost Of Revenue"]),
                        ("กำไรขั้นต้น", ["Gross Profit"]),
                        ("ค่าใช้จ่ายดำเนินงาน", ["Operating Expense"]),
                        ("วิจัยและพัฒนา", ["Research And Development"]),
                        ("กำไรดำเนินงาน", ["Operating Income"]),
                        ("กำไรสุทธิ", ["Net Income"])]:
        row = find_row(vi, cands)
        line = f"  {thai:<24}"
        if row is None:
            line += "".join(f"{'-':>11}" for _ in years)
        else:
            for y in years:
                v = row.get(y)
                line += f"{v:>10.1f}%" if pd.notna(v) else f"{'-':>11}"
        print(line)

    print()
    print("  หมายเหตุ: CAGR คำนวณจาก", len(years), "ปีข้อมูล =", len(years) - 1, "ช่วงปี")
    print("            ค่า '-' ในช่อง CAGR แปลว่าปีแรกหรือปีสุดท้ายติดลบ/เป็นศูนย์ จึงคิดไม่ได้")
    print("=" * (26 + 11 * len(years) + 9))


# ---------------------------------------------------------------------------
# รันจาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Part 2 — วิเคราะห์งบการเงิน")
    p.add_argument("ticker")
    p.add_argument("--refresh", action="store_true", help="ดึงข้อมูลใหม่ ไม่ใช้ cache")
    args = p.parse_args()

    try:
        data = get_stock_data(args.ticker, force_refresh=args.refresh)
        res = analyze(data)
    except Exception as e:
        print(f"\n[ไม่สำเร็จ] {type(e).__name__}: {e}\n", file=sys.stderr)
        return 1

    print_report(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
