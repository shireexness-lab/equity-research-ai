"""
ratios.py — Part 3 : Ratio Engine
==================================
หน้าที่ : คำนวณอัตราส่วนทางการเงินทุกตัว แบ่งเป็น 8 หมวด

หลักการสำคัญ 3 ข้อ
------------------
1. **ตัวหารเป็น 0 หรือติดลบ → คืนค่าว่าง ไม่ใช่ crash**
   เช่น บริษัทที่ส่วนของผู้ถือหุ้นติดลบ ROE จะไม่มีความหมาย จึงเว้นว่าง

2. **รายการในงบดุลใช้ "ค่าเฉลี่ยต้นปี-ปลายปี"**
   เพราะงบดุลเป็นภาพ ณ วันสิ้นปี แต่รายได้/กำไรเป็นยอดสะสมทั้งปี
   เช่น Inventory Turnover = ต้นทุนขาย ÷ สินค้าคงเหลือ**เฉลี่ย**
   (ปีแรกไม่มีข้อมูลปีก่อน จึงใช้ค่าสิ้นปีแทน)

3. **อัตราส่วนราคา (PE, PBV ฯลฯ) คำนวณเฉพาะปีล่าสุด**
   เพราะเราใช้ "ราคาวันนี้" ถ้าเอาราคาวันนี้ไปหารกำไรปี 2022 จะไม่มีความหมาย

วิธีใช้จาก Terminal
-------------------
    python3 ratios.py AAPL
    python3 ratios.py PTT.BK
"""

import argparse
import sys

import numpy as np
import pandas as pd

from data_layer import (find_row, get_current_price, get_shares_outstanding,
                        get_stock_data, get_years)

DAYS_PER_YEAR = 365


# ---------------------------------------------------------------------------
# ตัวช่วยคำนวณที่ปลอดภัย
# ---------------------------------------------------------------------------

def _blank(years) -> pd.Series:
    """แถวว่างเปล่า (ใช้เมื่อหาบรรทัดในงบไม่เจอ)"""
    return pd.Series([np.nan] * len(years), index=years, dtype=float)


def _row(df, names, years) -> pd.Series:
    """ดึงบรรทัดจากงบ แล้วจัดให้ตรงกับรายชื่อปี — ถ้าไม่เจอคืนแถวว่าง"""
    r = find_row(df, names)
    if r is None:
        return _blank(years)
    return pd.to_numeric(r.reindex(years), errors="coerce")


def _div(a: pd.Series, b: pd.Series) -> pd.Series:
    """
    หารแบบปลอดภัย : ถ้าตัวหารเป็น 0 หรือค่าว่าง → ได้ค่าว่าง (ไม่ crash)
    """
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    b = b.replace(0, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = a / b
    return out.replace([np.inf, -np.inf], np.nan)


def _avg(series: pd.Series) -> pd.Series:
    """
    ค่าเฉลี่ยต้นปี-ปลายปี ของรายการในงบดุล
    ปีแรกไม่มีปีก่อนหน้า จึงใช้ค่าสิ้นปีแทน
    """
    s = pd.to_numeric(series, errors="coerce")
    return ((s + s.shift(1)) / 2.0).fillna(s)


def _safe_cagr(series: pd.Series):
    """CAGR (%) — คืน None ถ้าปีแรกหรือปีสุดท้าย ≤ 0"""
    s = pd.Series(series).dropna()
    if len(s) < 2:
        return None
    first, last = float(s.iloc[0]), float(s.iloc[-1])
    if first <= 0 or last <= 0:
        return None
    return ((last / first) ** (1.0 / (len(s) - 1)) - 1.0) * 100.0


# ---------------------------------------------------------------------------
# ตัวเก็บผลลัพธ์
# ---------------------------------------------------------------------------

class _Collector:
    """เก็บอัตราส่วนพร้อมหมวดและหน่วย เพื่อเอาไปแสดงผล/ทำรายงานต่อ"""

    def __init__(self, years):
        self.years = years
        self.rows = {}     # ชื่อ -> Series
        self.groups = {}   # หมวด -> [ชื่อ, ...]
        self.units = {}    # ชื่อ -> หน่วย ('%', 'x', 'วัน', 'ล้าน')

    def add(self, group, name, series, unit="x"):
        if isinstance(series, (int, float)):
            series = pd.Series([series] * len(self.years), index=self.years)
        self.rows[name] = pd.to_numeric(
            pd.Series(series).reindex(self.years), errors="coerce")
        self.groups.setdefault(group, []).append(name)
        self.units[name] = unit

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows).T.reindex(
            [n for g in self.groups.values() for n in g])


# ---------------------------------------------------------------------------
# ฟังก์ชันหลัก
# ---------------------------------------------------------------------------

def compute_ratios(data: dict) -> dict:
    """
    คำนวณอัตราส่วนทั้งหมด คืน dict

        years      : รายชื่อปี
        table      : DataFrame (แถว = อัตราส่วน, คอลัมน์ = ปี)
        groups     : dict หมวด -> รายชื่ออัตราส่วน
        units      : dict ชื่อ -> หน่วย
        valuation  : dict อัตราส่วนราคา (ปีล่าสุดเท่านั้น)
        summary    : dict ค่าสรุป (CAGR, ความสม่ำเสมอ) สำหรับ Part 9
        raw        : dict ค่าดิบที่ใช้บ่อย เอาไปใช้ต่อใน Part 4 (DCF)
    """
    years = get_years(data)
    if not years:
        raise ValueError("ไม่มีข้อมูลงบการเงินให้คำนวณ")

    inc, bal, cf = data["income"], data["balance"], data["cashflow"]
    C = _Collector(years)

    # ===== ดึงค่าดิบที่ต้องใช้ =====
    revenue   = _row(inc, ["Total Revenue", "Operating Revenue"], years)
    cogs      = _row(inc, ["Cost Of Revenue", "Reconciled Cost Of Revenue"], years)
    gross     = _row(inc, ["Gross Profit"], years)
    opinc     = _row(inc, ["Operating Income", "Total Operating Income As Reported"], years)
    ebit      = _row(inc, ["EBIT"], years)
    ebitda    = _row(inc, ["EBITDA", "Normalized EBITDA"], years)
    pretax    = _row(inc, ["Pretax Income"], years)
    taxprov   = _row(inc, ["Tax Provision"], years)
    netinc    = _row(inc, ["Net Income", "Net Income Common Stockholders"], years)
    eps       = _row(inc, ["Diluted EPS", "Basic EPS"], years)
    dil_sh    = _row(inc, ["Diluted Average Shares", "Basic Average Shares"], years)
    rnd       = _row(inc, ["Research And Development"], years)
    sga       = _row(inc, ["Selling General And Administration"], years)
    int_exp   = _row(inc, ["Interest Expense", "Interest Expense Non Operating"], years)

    assets    = _row(bal, ["Total Assets"], years)
    cur_asset = _row(bal, ["Current Assets"], years)
    cash      = _row(bal, ["Cash And Cash Equivalents",
                           "Cash Cash Equivalents And Short Term Investments"], years)
    sti       = _row(bal, ["Other Short Term Investments"], years)
    inventory = _row(bal, ["Inventory"], years)
    ar        = _row(bal, ["Accounts Receivable", "Receivables"], years)
    ap        = _row(bal, ["Accounts Payable", "Payables"], years)
    cur_liab  = _row(bal, ["Current Liabilities"], years)
    tot_liab  = _row(bal, ["Total Liabilities Net Minority Interest"], years)
    tot_debt  = _row(bal, ["Total Debt"], years)
    net_debt  = _row(bal, ["Net Debt"], years)
    equity    = _row(bal, ["Stockholders Equity", "Total Equity Gross Minority Interest"], years)
    invested  = _row(bal, ["Invested Capital"], years)
    net_ppe   = _row(bal, ["Net PPE"], years)

    ocf       = _row(cf, ["Operating Cash Flow",
                          "Cash Flow From Continuing Operating Activities"], years)
    da        = _row(cf, ["Depreciation And Amortization",
                          "Depreciation Amortization Depletion"], years)
    capex_raw = _row(cf, ["Capital Expenditure", "Purchase Of PPE"], years)
    capex     = capex_raw.abs()          # yfinance เก็บเป็นค่าติดลบ → ทำให้เป็นบวก
    div_paid  = _row(cf, ["Cash Dividends Paid", "Common Stock Dividend Paid"], years).abs()
    buyback   = _row(cf, ["Repurchase Of Capital Stock", "Common Stock Payments"], years).abs()

    # ถ้างบดุลไม่มี Net Debt ให้คำนวณเอง
    if net_debt.isna().all():
        net_debt = tot_debt.fillna(0) - cash.fillna(0) - sti.fillna(0)

    # กระแสเงินสดอิสระ — คำนวณเองเสมอ ไม่พึ่งค่าที่ yfinance ให้มา
    fcf = ocf - capex

    # อัตราภาษีที่แท้จริง (จำกัดไว้ 0-50% กันค่าประหลาดจากปีที่มีรายการพิเศษ)
    tax_rate = _div(taxprov, pretax).clip(lower=0.0, upper=0.5)

    # ===== หมวด 1 : สภาพคล่อง =====
    G = "1. สภาพคล่อง (Liquidity)"
    C.add(G, "Current Ratio", _div(cur_asset, cur_liab), "x")
    C.add(G, "Quick Ratio", _div(cur_asset - inventory.fillna(0), cur_liab), "x")
    C.add(G, "Cash Ratio", _div(cash.fillna(0) + sti.fillna(0), cur_liab), "x")
    C.add(G, "Working Capital", (cur_asset - cur_liab) / 1e6, "ล้าน")
    C.add(G, "WC / รายได้", _div(cur_asset - cur_liab, revenue) * 100, "%")

    # ===== หมวด 2 : ประสิทธิภาพ =====
    G = "2. ประสิทธิภาพ (Efficiency)"
    inv_turn = _div(cogs, _avg(inventory))
    ar_turn = _div(revenue, _avg(ar))
    ap_turn = _div(cogs, _avg(ap))
    dio = DAYS_PER_YEAR / inv_turn.replace(0, np.nan)
    dso = DAYS_PER_YEAR / ar_turn.replace(0, np.nan)
    dpo = DAYS_PER_YEAR / ap_turn.replace(0, np.nan)
    C.add(G, "Inventory Turnover", inv_turn, "x")
    C.add(G, "Receivable Turnover", ar_turn, "x")
    C.add(G, "Payable Turnover", ap_turn, "x")
    C.add(G, "วันขายสินค้า (DIO)", dio, "วัน")
    C.add(G, "วันเก็บหนี้ (DSO)", dso, "วัน")
    C.add(G, "วันจ่ายหนี้ (DPO)", dpo, "วัน")
    C.add(G, "วงจรเงินสด (CCC)", dio + dso - dpo, "วัน")
    C.add(G, "Asset Turnover", _div(revenue, _avg(assets)), "x")
    C.add(G, "Fixed Asset Turnover", _div(revenue, _avg(net_ppe)), "x")

    # ===== หมวด 3 : ความสามารถทำกำไร =====
    G = "3. ความสามารถทำกำไร (Profitability)"
    C.add(G, "Gross Margin", _div(gross, revenue) * 100, "%")
    C.add(G, "Operating Margin", _div(opinc, revenue) * 100, "%")
    C.add(G, "EBITDA Margin", _div(ebitda, revenue) * 100, "%")
    C.add(G, "Net Margin", _div(netinc, revenue) * 100, "%")
    C.add(G, "ROE", _div(netinc, _avg(equity)) * 100, "%")
    C.add(G, "ROA", _div(netinc, _avg(assets)) * 100, "%")
    nopat = ebit * (1 - tax_rate)
    C.add(G, "ROIC", _div(nopat, _avg(invested)) * 100, "%")
    C.add(G, "ROCE", _div(ebit, _avg(assets) - _avg(cur_liab)) * 100, "%")
    C.add(G, "R&D / รายได้", _div(rnd, revenue) * 100, "%")
    C.add(G, "SG&A / รายได้", _div(sga, revenue) * 100, "%")

    # ===== หมวด 4 : กระแสเงินสด =====
    G = "4. กระแสเงินสด (Cash Flow)"
    C.add(G, "OCF", ocf / 1e6, "ล้าน")
    C.add(G, "CapEx", capex / 1e6, "ล้าน")
    C.add(G, "FCF (OCF - CapEx)", fcf / 1e6, "ล้าน")
    C.add(G, "FCF Margin", _div(fcf, revenue) * 100, "%")
    C.add(G, "OCF / กำไรสุทธิ", _div(ocf, netinc), "x")
    C.add(G, "FCF / กำไรสุทธิ", _div(fcf, netinc), "x")
    C.add(G, "CapEx / OCF", _div(capex, ocf) * 100, "%")
    C.add(G, "Owner Earnings", (netinc + da.fillna(0) - capex) / 1e6, "ล้าน")
    C.add(G, "FCF ต่อหุ้น", _div(fcf, dil_sh), "x")

    # ===== หมวด 5 : หนี้สิน =====
    G = "5. หนี้สิน (Debt)"
    C.add(G, "D/E (หนี้มีดอกเบี้ย)", _div(tot_debt, equity), "x")
    C.add(G, "D/E (หนี้สินรวม)", _div(tot_liab, equity), "x")
    C.add(G, "หนี้สิน / สินทรัพย์", _div(tot_liab, assets) * 100, "%")
    C.add(G, "Net Debt", net_debt / 1e6, "ล้าน")
    C.add(G, "Net Debt / EBITDA", _div(net_debt, ebitda), "x")
    C.add(G, "Interest Coverage", _div(ebit, int_exp.abs()), "x")
    C.add(G, "Equity Multiplier", _div(_avg(assets), _avg(equity)), "x")

    # ===== หมวด 6 : เงินปันผล =====
    G = "6. เงินปันผล (Dividend)"
    C.add(G, "เงินปันผลจ่าย", div_paid / 1e6, "ล้าน")
    C.add(G, "Payout Ratio", _div(div_paid, netinc) * 100, "%")
    C.add(G, "เงินปันผล / FCF", _div(div_paid, fcf) * 100, "%")
    C.add(G, "เงินปันผลต่อหุ้น", _div(div_paid, dil_sh), "x")
    C.add(G, "ซื้อหุ้นคืน", buyback / 1e6, "ล้าน")
    C.add(G, "(ปันผล+ซื้อคืน) / FCF", _div(div_paid + buyback.fillna(0), fcf) * 100, "%")

    # ===== หมวด 7 : คุณภาพกำไร (QoE) =====
    G = "7. คุณภาพกำไร (Quality of Earnings)"
    C.add(G, "Accrual Ratio", _div(netinc - ocf, _avg(assets)) * 100, "%")
    C.add(G, "D&A / รายได้", _div(da, revenue) * 100, "%")
    C.add(G, "อัตราภาษีที่แท้จริง", tax_rate * 100, "%")

    table = C.to_frame()

    # ===== หมวด 8 : อัตราส่วนราคา (ปีล่าสุดเท่านั้น) =====
    valuation = _compute_valuation(
        data, years, revenue, netinc, eps, ebit, ebitda, equity, fcf, net_debt)

    # ===== ค่าสรุปสำหรับ Part 9 (Buffett Score ฯลฯ) =====
    roe = table.loc["ROE"]
    gm = table.loc["Gross Margin"]
    summary = {
        "จำนวนปีข้อมูล": len(years),
        "CAGR รายได้ (%)": _safe_cagr(revenue),
        "CAGR กำไรสุทธิ (%)": _safe_cagr(netinc),
        "CAGR EPS (%)": _safe_cagr(eps),
        "CAGR FCF (%)": _safe_cagr(fcf),
        "CAGR OCF (%)": _safe_cagr(ocf),
        "ROE เฉลี่ย (%)": float(roe.mean()) if roe.notna().any() else None,
        "ROE ต่ำสุด (%)": float(roe.min()) if roe.notna().any() else None,
        "ROE ส่วนเบี่ยงเบน (%)": float(roe.std()) if roe.notna().sum() > 1 else None,
        "ROIC เฉลี่ย (%)": float(table.loc["ROIC"].mean()),
        "Gross Margin เฉลี่ย (%)": float(gm.mean()) if gm.notna().any() else None,
        "Gross Margin ส่วนเบี่ยงเบน (%)": float(gm.std()) if gm.notna().sum() > 1 else None,
        "ปีที่ FCF เป็นบวก": int((fcf > 0).sum()),
        "OCF/กำไรสุทธิ เฉลี่ย (x)": float(table.loc["OCF / กำไรสุทธิ"].mean()),
    }

    return {
        "ticker": data.get("ticker"),
        "years": years,
        "table": table,
        "groups": C.groups,
        "units": C.units,
        "valuation": valuation,
        "summary": summary,
        "raw": {
            "revenue": revenue, "net_income": netinc, "eps": eps,
            "ebit": ebit, "ebitda": ebitda, "ocf": ocf, "capex": capex,
            "fcf": fcf, "equity": equity, "net_debt": net_debt,
            "shares_diluted": dil_sh, "tax_rate": tax_rate,
            "dividends_paid": div_paid, "d_and_a": da,
        },
    }


def _compute_valuation(data, years, revenue, netinc, eps, ebit, ebitda,
                       equity, fcf, net_debt) -> dict:
    """อัตราส่วนราคา — ใช้ราคาปัจจุบัน จึงมีความหมายเฉพาะปีล่าสุด"""
    price = get_current_price(data)
    shares = get_shares_outstanding(data)
    last = years[-1]

    def L(s):
        v = s.get(last)
        return float(v) if pd.notna(v) else None

    out = {
        "ราคาปัจจุบัน": price,
        "จำนวนหุ้น": shares,
        "ปีที่ใช้เทียบ": last[:4],
    }
    if price is None or not shares:
        out["หมายเหตุ"] = "ไม่มีราคาหรือจำนวนหุ้น จึงคำนวณอัตราส่วนราคาไม่ได้"
        return out

    mcap = price * shares
    nd = L(net_debt) or 0.0
    ev = mcap + nd

    def r(num, den):
        if den in (None, 0) or num is None:
            return None
        return num / den

    out.update({
        "มูลค่าตลาด (ล้าน)": mcap / 1e6,
        "Enterprise Value (ล้าน)": ev / 1e6,
        "P/E": r(price, L(eps)),
        "P/BV": r(mcap, L(equity)),
        "P/S": r(mcap, L(revenue)),
        "P/FCF": r(mcap, L(fcf)),
        "EV/EBITDA": r(ev, L(ebitda)),
        "EV/EBIT": r(ev, L(ebit)),
        "Earnings Yield (%)": (r(L(netinc), mcap) or 0) * 100 if L(netinc) else None,
        "FCF Yield (%)": (r(L(fcf), mcap) or 0) * 100 if L(fcf) else None,
    })
    return out


# ---------------------------------------------------------------------------
# แสดงผล
# ---------------------------------------------------------------------------

def _fmt(v, unit):
    if v is None or pd.isna(v):
        return "-"
    if unit == "%":
        return f"{v:,.1f}%"
    if unit == "วัน":
        return f"{v:,.0f}"
    if unit == "ล้าน":
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def print_report(res: dict) -> None:
    years = res["years"]
    table, units = res["table"], res["units"]
    w = 26 + 12 * len(years)

    print("=" * w)
    print(f"  Part 3 — อัตราส่วนทางการเงิน : {res['ticker']}")
    print("=" * w)

    for group, names in res["groups"].items():
        print()
        print(f"  {group}")
        print("  " + "-" * (w - 4))
        print("  {:<24}".format("") + "".join(f"{y[:4]:>12}" for y in years))
        for name in names:
            line = f"  {name:<24}"
            for y in years:
                line += f"{_fmt(table.loc[name, y], units[name]):>12}"
            print(line)

    print()
    print(f"  8. อัตราส่วนราคา (ใช้ราคาปัจจุบันเทียบงบปี {res['valuation'].get('ปีที่ใช้เทียบ','-')})")
    print("  " + "-" * (w - 4))
    for k, v in res["valuation"].items():
        if isinstance(v, float):
            print(f"  {k:<28}{v:>14,.2f}")
        else:
            print(f"  {k:<28}{str(v):>14}")

    print()
    print("  สรุปสำหรับให้คะแนนคุณภาพ (จะใช้ใน Part 9)")
    print("  " + "-" * (w - 4))
    for k, v in res["summary"].items():
        s = "-" if v is None else (f"{v:,.2f}" if isinstance(v, float) else f"{v}")
        print(f"  {k:<32}{s:>12}")
    print("=" * w)


# ---------------------------------------------------------------------------
# รันจาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Part 3 — คำนวณอัตราส่วนทางการเงิน")
    p.add_argument("ticker")
    p.add_argument("--refresh", action="store_true")
    args = p.parse_args()

    try:
        data = get_stock_data(args.ticker, force_refresh=args.refresh)
        res = compute_ratios(data)
    except Exception as e:
        print(f"\n[ไม่สำเร็จ] {type(e).__name__}: {e}\n", file=sys.stderr)
        return 1

    print_report(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
