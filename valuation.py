"""
valuation.py — Part 4 : Valuation Engine
=========================================
หน้าที่ : ประเมิน "มูลค่าที่แท้จริง" ของหุ้น ด้วย 5 วิธี แล้วเทียบกับราคาตลาด

วิธีที่ใช้ (แต่ละวิธีมองคนละมุม จงใจให้ผลไม่เท่ากัน)
---------------------------------------------------
1. DCF 2-Stage     — คิดลดกระแสเงินสดอนาคต  ← วิธีหลัก
2. EPV             — มูลค่าจากกำไรปัจจุบัน ถ้าไม่โตเลย  ← ขอบล่างที่อนุรักษ์นิยม
3. Multiple ย้อนหลัง — ถ้าตลาดให้ราคาเท่าค่ากลาง 10 ปีของตัวเอง จะได้เท่าไร
4. DDM             — สำหรับหุ้นปันผล (ใช้ได้เมื่อจ่ายปันผลสม่ำเสมอ)
5. Reverse DCF     — **ราคาวันนี้กำลังบอกว่าตลาดคาดให้โตกี่ %**  ← ตัวที่มีประโยชน์ที่สุด

ปรัชญาสำคัญ
-----------
DCF **ไม่ใช่** เครื่องทำนายราคา แต่เป็นเครื่องมือตอบว่า
"ถ้าจะซื้อที่ราคานี้ เราต้องเชื่ออะไรบ้าง — และความเชื่อนั้นสมเหตุสมผลไหม"

ตัวเลขทุกตัวคำนวณด้วย Python ทั้งหมด ไม่มี AI เข้ามาเกี่ยวข้อง (กฎเหล็กข้อ 1)

วิธีใช้จาก Terminal
-------------------
    python3 valuation.py AAPL
    python3 valuation.py AAPL --wacc 0.09 --g1 0.08
"""

import argparse
import sys

import numpy as np
import pandas as pd

from data_layer import get_current_price, get_shares_outstanding, get_stock_data
from ratios import compute_ratios

# ---------------------------------------------------------------------------
# ค่าตั้งต้น (ปรับได้จาก Terminal)
# ---------------------------------------------------------------------------

DEFAULT_STAGE1_YEARS = 10      # ช่วงโตสูง 10 ปี
DEFAULT_TERMINAL_G = 0.025     # โตถาวร 2.5% ≈ เงินเฟ้อ + GDP โลกระยะยาว
DEFAULT_ERP = 0.05             # ส่วนชดเชยความเสี่ยงตลาดหุ้น (Equity Risk Premium)
DEFAULT_RF = 0.042             # อัตราผลตอบแทนพันธบัตรรัฐบาลสหรัฐ 10 ปี (ค่าสำรอง)
MAX_G1 = 0.15                  # เพดานอัตราโตช่วงแรก — กันไม่ให้ประมาณเวอร์เกินจริง
MIN_WACC_GAP = 0.01            # WACC ต้องมากกว่า g2 อย่างน้อย 1% ไม่งั้นสูตรระเบิด


# ---------------------------------------------------------------------------
# 1) หัวใจ : DCF 2-Stage
# ---------------------------------------------------------------------------

def dcf_2stage(fcf0, g1, years1, g2, wacc, shares, net_debt=0.0):
    """
    คิดลดกระแสเงินสดอิสระ 2 ช่วง

    พารามิเตอร์
        fcf0     : กระแสเงินสดอิสระปีฐาน (บาท/ดอลลาร์ ไม่ใช่ล้าน)
        g1       : อัตราโตช่วงแรก เช่น 0.08 = 8%
        years1   : จำนวนปีช่วงโตสูง
        g2       : อัตราโตถาวรหลังจากนั้น (ต้องน้อยกว่า wacc)
        wacc     : อัตราคิดลด
        shares   : จำนวนหุ้น
        net_debt : หนี้สินสุทธิ (หนี้ − เงินสด) ถ้าเงินสดมากกว่าหนี้จะติดลบ

    คืน dict : มูลค่าต่อหุ้น + รายละเอียดให้ตรวจสอบย้อนกลับได้ทุกขั้น
    """
    if shares in (None, 0) or not np.isfinite(shares):
        raise ValueError("ไม่มีจำนวนหุ้น จึงคำนวณมูลค่าต่อหุ้นไม่ได้")
    if fcf0 is None or not np.isfinite(fcf0) or fcf0 <= 0:
        raise ValueError("กระแสเงินสดอิสระปีฐานต้องเป็นบวก จึงจะทำ DCF ได้")
    if wacc - g2 < MIN_WACC_GAP:
        raise ValueError(
            f"อัตราคิดลด ({wacc:.1%}) ต้องมากกว่าอัตราโตถาวร ({g2:.1%}) "
            f"อย่างน้อย {MIN_WACC_GAP:.0%}\n"
            "  ถ้าไม่เช่นนั้น สูตร Gordon Growth จะให้มูลค่าเป็นอนันต์หรือติดลบ"
        )

    rows, pv_sum, fcf = [], 0.0, float(fcf0)
    for y in range(1, int(years1) + 1):
        fcf *= (1 + g1)
        discount = (1 + wacc) ** y
        pv = fcf / discount
        pv_sum += pv
        rows.append({"ปีที่": y, "FCF": fcf, "ตัวคิดลด": discount, "มูลค่าปัจจุบัน": pv})

    # มูลค่าสุดท้าย (Terminal Value) ด้วยสูตร Gordon Growth
    terminal = fcf * (1 + g2) / (wacc - g2)
    pv_terminal = terminal / ((1 + wacc) ** years1)

    ev = pv_sum + pv_terminal
    equity = ev - (net_debt or 0.0)
    per_share = equity / shares

    return {
        "มูลค่าต่อหุ้น": per_share,
        "มูลค่ากิจการ (EV)": ev,
        "มูลค่าส่วนผู้ถือหุ้น": equity,
        "PV ช่วงโตสูง": pv_sum,
        "PV มูลค่าสุดท้าย": pv_terminal,
        "สัดส่วนมูลค่าสุดท้าย": pv_terminal / ev if ev else np.nan,
        "ตารางรายปี": pd.DataFrame(rows),
        "สมมติฐาน": {"fcf0": fcf0, "g1": g1, "years1": years1,
                     "g2": g2, "wacc": wacc, "shares": shares, "net_debt": net_debt},
    }


# ---------------------------------------------------------------------------
# 2) ประมาณ WACC จากข้อมูลจริงของบริษัท
# ---------------------------------------------------------------------------

def estimate_wacc(data, R, rf=None, erp=DEFAULT_ERP) -> dict:
    """
    ประมาณอัตราคิดลด (WACC) จากตัวเลขจริง ไม่ใช่เดาเอา

    สูตร  WACC = (E/V × ต้นทุนทุน) + (D/V × ต้นทุนหนี้ × (1 − อัตราภาษี))

        ต้นทุนทุน (CAPM) = พันธบัตร + beta × ส่วนชดเชยความเสี่ยงตลาด
        ต้นทุนหนี้        = ดอกเบี้ยจ่าย ÷ หนี้เฉลี่ย  (ถ้าคำนวณไม่ได้ใช้ พันธบัตร + 1%)

    หมายเหตุ : ค่าพันธบัตรเริ่มต้นเป็นของสหรัฐ ถ้าวิเคราะห์หุ้นไทย
               ควรใส่ --rf ด้วยอัตราพันธบัตรไทยแทน
    """
    info = data.get("info", {})
    raw = R["raw"]
    years = R["years"]

    beta = info.get("beta")
    beta = float(beta) if beta not in (None, 0) and np.isfinite(float(beta or 0)) else 1.0
    beta = min(max(beta, 0.5), 2.0)      # ตัดค่าสุดโต่งทิ้ง

    rf = float(rf) if rf is not None else DEFAULT_RF
    cost_equity = rf + beta * erp

    # ต้นทุนหนี้จากดอกเบี้ยที่จ่ายจริง = ดอกเบี้ยจ่าย ÷ หนี้เฉลี่ย
    debt = _series(data, "balance", ["Total Debt"], years)
    ie = _series(data, "income", ["Interest Expense"], years).abs()
    cost_debt = np.nan
    if ie.notna().any() and debt.notna().any():
        avg_debt = ((debt + debt.shift(1)) / 2).fillna(debt)
        ratio = (ie / avg_debt.replace(0, np.nan)).dropna()
        if len(ratio):
            cost_debt = float(ratio.tail(3).median())
    if not np.isfinite(cost_debt) or not (0.001 < cost_debt < 0.25):
        cost_debt = rf + 0.01           # ค่าสำรองเมื่อคำนวณไม่ได้

    tax = raw["tax_rate"].dropna()
    tax_rate = float(tax.tail(3).median()) if len(tax) else 0.21
    tax_rate = min(max(tax_rate, 0.0), 0.5)

    price = get_current_price(data)
    shares = get_shares_outstanding(data)
    e_val = (price or 0) * (shares or 0)
    d_val = float(debt.dropna().iloc[-1]) if debt.notna().any() else 0.0
    v = e_val + d_val
    we, wd = (e_val / v, d_val / v) if v > 0 else (1.0, 0.0)

    wacc = we * cost_equity + wd * cost_debt * (1 - tax_rate)
    # กันค่าผิดปกติ — WACC ในโลกจริงแทบไม่เคยต่ำกว่า 4% หรือเกิน 20%
    wacc = min(max(wacc, 0.04), 0.20)

    return {
        "wacc": wacc,
        "ต้นทุนส่วนทุน": cost_equity,
        "ต้นทุนหนี้": cost_debt,
        "beta": beta,
        "พันธบัตร (rf)": rf,
        "ส่วนชดเชยความเสี่ยง": erp,
        "อัตราภาษี": tax_rate,
        "น้ำหนักส่วนทุน": we,
        "น้ำหนักหนี้": wd,
    }


def _series(data, statement: str, names, years) -> pd.Series:
    """ดึงบรรทัดจากงบที่ระบุ ('income' / 'balance' / 'cashflow') ให้ตรงกับรายชื่อปี"""
    from data_layer import find_row
    r = find_row(data.get(statement), names)
    if r is None:
        return pd.Series([np.nan] * len(years), index=years, dtype=float)
    return pd.to_numeric(r.reindex(years), errors="coerce")


# ---------------------------------------------------------------------------
# 3) ประมาณค่าตั้งต้นอื่น ๆ จากข้อมูลจริง
# ---------------------------------------------------------------------------

def estimate_inputs(data, R) -> dict:
    """
    หาค่า fcf0 และ g1 จากประวัติจริง

    fcf0 : ใช้ **ค่าเฉลี่ย 3 ปีล่าสุด** ไม่ใช่ปีล่าสุดปีเดียว
           เหตุผล : ปีเดียวอาจมีรายการพิเศษ ทำให้มูลค่าเพี้ยนทั้งโมเดล
    g1   : ใช้ CAGR ของ FCF ย้อนหลัง แต่ตัดเพดานไว้ที่ 15%
           เหตุผล : ไม่มีบริษัทไหนโต 25% ต่อปีได้ 10 ปีติด การใส่ตัวเลขสวย ๆ
                    เข้าไปคือวิธีที่คนหลอกตัวเองบ่อยที่สุดในการทำ DCF
    """
    raw = R["raw"]
    fcf = raw["fcf"].dropna()
    if len(fcf) == 0:
        raise ValueError("ไม่มีข้อมูลกระแสเงินสดอิสระ")

    fcf0 = float(fcf.tail(3).mean())
    fcf_latest = float(fcf.iloc[-1])

    # อัตราโต : ลองจาก FCF ก่อน ถ้าคำนวณไม่ได้ใช้รายได้
    g_fcf = R["summary"].get("CAGR FCF (%)")
    g_rev = R["summary"].get("CAGR รายได้ (%)")
    g_ni = R["summary"].get("CAGR กำไรสุทธิ (%)")
    candidates = [g for g in (g_fcf, g_ni, g_rev) if g is not None]
    g_raw = (sum(candidates) / len(candidates) / 100.0) if candidates else 0.03
    g1 = min(max(g_raw, 0.0), MAX_G1)

    net_debt = raw["net_debt"].dropna()
    net_debt0 = float(net_debt.iloc[-1]) if len(net_debt) else 0.0

    return {
        "fcf0 (เฉลี่ย 3 ปี)": fcf0,
        "fcf ปีล่าสุด": fcf_latest,
        "g1 ที่ประมาณได้": g1,
        "g1 ก่อนตัดเพดาน": g_raw,
        "ถูกตัดเพดานไหม": g_raw > MAX_G1,
        "net_debt": net_debt0,
        "ที่มาของ g1": {"CAGR FCF (%)": g_fcf, "CAGR กำไรสุทธิ (%)": g_ni,
                        "CAGR รายได้ (%)": g_rev},
    }


# ---------------------------------------------------------------------------
# 4) Sensitivity — ตารางความไว
# ---------------------------------------------------------------------------

def sensitivity(fcf0, years1, g2, shares, net_debt, wacc_center, g1_center,
                steps=2, wacc_step=0.01, g1_step=0.02) -> pd.DataFrame:
    """
    รัน DCF ซ้ำหลายรอบ ปรับ WACC และ g1 ทีละนิด

    ทำไมสำคัญ : ถ้าเปลี่ยน WACC 1% แล้วมูลค่าเปลี่ยน 40% แปลว่าโมเดลนี้
    "เปราะ" มาก ไม่ควรเชื่อตัวเลขเดียวจาก DCF
    """
    waccs = [wacc_center + i * wacc_step for i in range(-steps, steps + 1)]
    g1s = [g1_center + i * g1_step for i in range(-steps, steps + 1)]
    out = pd.DataFrame(index=[f"{w:.1%}" for w in waccs],
                       columns=[f"{g:.1%}" for g in g1s], dtype=float)
    for w in waccs:
        for g in g1s:
            try:
                out.loc[f"{w:.1%}", f"{g:.1%}"] = dcf_2stage(
                    fcf0, g, years1, g2, w, shares, net_debt)["มูลค่าต่อหุ้น"]
            except Exception:
                out.loc[f"{w:.1%}", f"{g:.1%}"] = np.nan
    out.index.name = "WACC \\ g1"
    return out


# ---------------------------------------------------------------------------
# 5) Reverse DCF — ราคาตลาดกำลังคาดหวังอะไร
# ---------------------------------------------------------------------------

def reverse_dcf(price, fcf0, years1, g2, wacc, shares, net_debt):
    """
    หาว่า "ต้องโตกี่ % ต่อปี 10 ปี ราคาวันนี้ถึงจะสมเหตุสมผล"

    วิธี : ค่อย ๆ ขยับ g1 แล้วดูว่ามูลค่าเท่าราคาตลาดที่ค่าไหน (bisection)
    นี่คือคำถามที่มีประโยชน์กว่า "หุ้นนี้ควรราคาเท่าไร" มาก
    เพราะเปลี่ยนจากการทำนาย → เป็นการตรวจสอบสมมติฐานของตลาด
    """
    lo, hi = -0.30, 0.60

    def val(g):
        try:
            return dcf_2stage(fcf0, g, years1, g2, wacc, shares, net_debt)["มูลค่าต่อหุ้น"]
        except Exception:
            return np.nan

    if not np.isfinite(val(lo)) or not np.isfinite(val(hi)):
        return None
    if val(lo) > price:
        return lo      # แม้ไม่โตเลยก็ยังแพงกว่าราคาตลาด = ถูกมาก
    if val(hi) < price:
        return hi      # ต้องโตเกิน 60%/ปี ถึงจะคุ้ม = แพงมาก

    for _ in range(80):
        mid = (lo + hi) / 2
        if val(mid) < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# 6) EPV — มูลค่าถ้าไม่โตเลย
# ---------------------------------------------------------------------------

def earnings_power_value(R, wacc, shares, net_debt):
    """
    Earnings Power Value (แนวคิดของ Bruce Greenwald)

    สมมติว่าบริษัท **หยุดโตตั้งแต่วันนี้** แต่ยังทำกำไรเท่าเดิมได้ตลอดไป
        EPV = NOPAT เฉลี่ย ÷ WACC

    ใช้เป็น "ขอบล่าง" — ถ้าราคาตลาดต่ำกว่า EPV แปลว่าตลาดคิดว่าบริษัทจะแย่ลง
    """
    raw = R["raw"]
    ebit = raw["ebit"].dropna()
    tax = raw["tax_rate"].dropna()
    if len(ebit) == 0:
        return None
    t = float(tax.tail(3).median()) if len(tax) else 0.21
    nopat = float(ebit.tail(3).mean()) * (1 - t)
    if nopat <= 0 or wacc <= 0:
        return None
    return (nopat / wacc - (net_debt or 0.0)) / shares


# ---------------------------------------------------------------------------
# 7) Multiple ย้อนหลังของตัวเอง
# ---------------------------------------------------------------------------

def historical_multiple_value(data, R):
    """
    ถ้าตลาดให้ P/E เท่ากับ "ค่ากลางย้อนหลังของหุ้นตัวเอง" ราคาควรเป็นเท่าไร

    ข้อดี : ไม่ต้องหาข้อมูลคู่แข่ง และเทียบกับตัวเองยุติธรรมกว่า
    ข้อควรระวัง : ถ้าธุรกิจเปลี่ยนไปจริง ค่ากลางในอดีตอาจไม่มีความหมายแล้ว
    (ต้องมีข้อมูล ≥ 5 ปีถึงจะน่าเชื่อ — เป็นเหตุผลที่เราเพิ่ม SEC EDGAR เข้ามา)
    """
    prices = data.get("prices")
    if not isinstance(prices, pd.DataFrame) or prices.empty or "Close" not in prices:
        return None
    px = prices["Close"].dropna()
    try:
        idx = px.index.tz_localize(None)
    except (TypeError, AttributeError):
        idx = px.index
    px = pd.Series(px.values, index=pd.DatetimeIndex(idx))

    years = R["years"]
    raw = R["raw"]
    eps, fcf, shares_h = raw["eps"], raw["fcf"], raw["shares_diluted"]

    rows = []
    for y in years:
        try:
            t = pd.Timestamp(y)
        except Exception:
            continue
        window = px[px.index <= t]
        if window.empty:
            continue
        p = float(window.iloc[-1])
        e = eps.get(y)
        f = fcf.get(y)
        s = shares_h.get(y)
        rows.append({
            "ปี": y[:4], "ราคาสิ้นปีงบ": p,
            "EPS": float(e) if pd.notna(e) else np.nan,
            "P/E": p / e if pd.notna(e) and e > 0 else np.nan,
            "P/FCF": (p * s) / f if pd.notna(f) and pd.notna(s) and f > 0 else np.nan,
        })
    if not rows:
        return None
    hist = pd.DataFrame(rows).set_index("ปี")

    pe_med = hist["P/E"].median()
    pfcf_med = hist["P/FCF"].median()
    # ค่ากลาง 5 ปีล่าสุด — สะท้อนว่าตลาดให้ราคาหุ้นตัวนี้อย่างไรใน "ยุคปัจจุบัน"
    # ถ้าธุรกิจหรือมุมมองตลาดเปลี่ยนไปถาวร ตัวเลขนี้ตรงความจริงกว่าค่ากลางทั้งช่วง
    pe_med5 = hist["P/E"].tail(5).median()
    pfcf_med5 = hist["P/FCF"].tail(5).median()

    last = years[-1]
    e_last, f_last, s_last = eps.get(last), fcf.get(last), shares_h.get(last)

    def v_pe(m):
        return m * e_last if pd.notna(m) and pd.notna(e_last) else None

    def v_pfcf(m):
        return (m * f_last / s_last) if pd.notna(m) and pd.notna(f_last) and pd.notna(s_last) else None

    return {
        "ตาราง": hist,
        "P/E ค่ากลาง": pe_med,
        "P/FCF ค่ากลาง": pfcf_med,
        "P/E ค่ากลาง 5 ปีล่าสุด": pe_med5,
        "P/FCF ค่ากลาง 5 ปีล่าสุด": pfcf_med5,
        "มูลค่าจาก P/E": v_pe(pe_med),
        "มูลค่าจาก P/FCF": v_pfcf(pfcf_med),
        "มูลค่าจาก P/E 5 ปี": v_pe(pe_med5),
        "มูลค่าจาก P/FCF 5 ปี": v_pfcf(pfcf_med5),
    }


# ---------------------------------------------------------------------------
# 7b) P/BV — วิธีมาตรฐานสำหรับสถาบันการเงิน
# ---------------------------------------------------------------------------

def book_value_method(data, R):
    """
    ประเมินจากมูลค่าตามบัญชี (Book Value)

    เหมาะกับใคร : ธนาคาร ประกัน และธุรกิจที่สินทรัพย์เป็นตัวเงินเกือบทั้งหมด
    เพราะมูลค่าตามบัญชีใกล้เคียงมูลค่าที่ขายได้จริง (ต่างจากโรงงานหรือแบรนด์)

    วิธี : ดู P/BV ที่ตลาดเคยให้หุ้นตัวนี้ย้อนหลัง แล้วคูณกับส่วนของผู้ถือหุ้นต่อหุ้นวันนี้
    """
    prices = data.get("prices")
    if not isinstance(prices, pd.DataFrame) or prices.empty or "Close" not in prices:
        return None
    px = prices["Close"].dropna()
    try:
        idx = px.index.tz_localize(None)
    except (TypeError, AttributeError):
        idx = px.index
    px = pd.Series(px.values, index=pd.DatetimeIndex(idx))

    years = R["years"]
    equity = R["raw"]["equity"]
    shares_h = R["raw"]["shares_diluted"]

    rows = []
    for y in years:
        try:
            t = pd.Timestamp(y)
        except Exception:
            continue
        win = px[px.index <= t]
        e, s = equity.get(y), shares_h.get(y)
        if win.empty or pd.isna(e) or pd.isna(s) or s == 0 or e <= 0:
            continue
        bvps = e / s
        rows.append({"ปี": y[:4], "BVPS": bvps, "P/BV": float(win.iloc[-1]) / bvps})
    if len(rows) < 3:
        return None

    hist = pd.DataFrame(rows).set_index("ปี")
    med = hist["P/BV"].median()
    med5 = hist["P/BV"].tail(5).median()
    last = years[-1]
    e_last, s_last = equity.get(last), shares_h.get(last)
    bvps_now = (e_last / s_last) if pd.notna(e_last) and pd.notna(s_last) and s_last else None

    return {
        "ตาราง": hist,
        "P/BV ค่ากลาง": med,
        "P/BV ค่ากลาง 5 ปีล่าสุด": med5,
        "BVPS ล่าสุด": bvps_now,
        "มูลค่าจาก P/BV": (med * bvps_now) if bvps_now and pd.notna(med) else None,
    }


# ---------------------------------------------------------------------------
# 8) DDM
# ---------------------------------------------------------------------------

def ddm(R, wacc, g2):
    """Dividend Discount Model — ใช้ได้เฉพาะหุ้นที่จ่ายปันผลสม่ำเสมอ"""
    raw = R["raw"]
    div = raw["dividends_paid"].dropna()
    sh = raw["shares_diluted"]
    if len(div) < 3:
        return None
    dps = (div / sh.reindex(div.index)).dropna()
    if len(dps) < 3 or dps.iloc[-1] <= 0:
        return None
    d0 = float(dps.tail(3).mean())
    if wacc - g2 < MIN_WACC_GAP:
        return None
    return d0 * (1 + g2) / (wacc - g2)


# ---------------------------------------------------------------------------
# ฟังก์ชันรวม
# ---------------------------------------------------------------------------

def is_financial(data) -> bool:
    """
    ตรวจว่าเป็นธนาคารหรือสถาบันการเงินไหม

    ทำไมต้องแยก : DCF บนฐานกระแสเงินสดอิสระ **ใช้กับสถาบันการเงินไม่ได้**
    เพราะหนี้สินของธนาคาร (เงินฝาก) คือ "วัตถุดิบ" ในการทำธุรกิจ ไม่ใช่แหล่งเงินทุน
    การหัก CapEx และคิด Net Debt จึงไม่มีความหมายทางเศรษฐศาสตร์
    ตำราการเงินใช้ P/BV คู่กับ ROE หรือ DDM แทน
    """
    info = data.get("info", {})
    sector = str(info.get("sector") or "").lower()
    industry = str(info.get("industry") or "").lower()
    keys = ("financial", "bank", "insurance", "capital markets", "credit")
    return any(k in sector or k in industry for k in keys)


def value_stock(data, R=None, wacc=None, g1=None, g2=DEFAULT_TERMINAL_G,
                years1=DEFAULT_STAGE1_YEARS, rf=None) -> dict:
    """ประเมินมูลค่าด้วยทุกวิธี คืนผลรวมทั้งหมด"""
    R = R or compute_ratios(data)
    price = get_current_price(data)
    shares = get_shares_outstanding(data)

    w = estimate_wacc(data, R, rf=rf)
    wacc = float(wacc) if wacc is not None else w["wacc"]

    # --- ตัดสินใจว่าจะใช้ DCF ได้ไหม ---
    notes = []
    fin = is_financial(data)
    try:
        inp = estimate_inputs(data, R)
        fcf_ok = inp["fcf0 (เฉลี่ย 3 ปี)"] > 0
        if not fcf_ok:
            notes.append("กระแสเงินสดอิสระเฉลี่ยติดลบ จึงทำ DCF ไม่ได้")
    except ValueError as e:
        inp, fcf_ok = None, False
        notes.append(f"ทำ DCF ไม่ได้ : {e}")

    if fin:
        notes.append(
            "หุ้นกลุ่มสถาบันการเงิน — ไม่ใช้ DCF บนฐานกระแสเงินสดอิสระ "
            "เพราะเงินฝากคือวัตถุดิบของธุรกิจ ไม่ใช่แหล่งเงินทุน "
            "การหัก CapEx และคิดหนี้สินสุทธิจึงไม่มีความหมาย "
            "ระบบจะใช้ P/BV, P/E และเงินปันผลแทน")

    use_dcf = fcf_ok and not fin

    base = bear = bull = None
    fcf0 = net_debt = None
    methods = {}

    if use_dcf:
        g1 = float(g1) if g1 is not None else inp["g1 ที่ประมาณได้"]
        fcf0 = inp["fcf0 (เฉลี่ย 3 ปี)"]
        net_debt = inp["net_debt"]

        base = dcf_2stage(fcf0, g1, years1, g2, wacc, shares, net_debt)
        # 3 ฉาก : แย่ / กลาง / ดี
        bear = dcf_2stage(fcf0, max(g1 - 0.04, -0.02), years1, g2,
                          wacc + 0.01, shares, net_debt)
        bull = dcf_2stage(fcf0, min(g1 + 0.04, MAX_G1 + 0.05), years1, g2,
                          max(wacc - 0.01, g2 + MIN_WACC_GAP), shares, net_debt)

        # --- แยก "วิธีประเมิน" ออกจาก "ฉากจำลอง" ---
        # ฉากแย่/ดี คือ DCF ตัวเดิมที่เปลี่ยนสมมติฐาน ไม่ใช่วิธีใหม่
        # ถ้านับรวมในค่ากลาง = ให้น้ำหนัก DCF ถึง 3 เท่า ทำให้วิธีอื่นแทบไม่มีผล
        methods["DCF 2-Stage"] = base["มูลค่าต่อหุ้น"]
        methods["EPV (ไม่โตเลย)"] = earnings_power_value(R, wacc, shares, net_debt)
    else:
        g1 = float(g1) if g1 is not None else None
    hist = historical_multiple_value(data, R)
    if hist:
        # แสดงทั้ง 2 ยุค เพราะตลาดอาจเปลี่ยนมุมมองต่อหุ้นตัวนี้ไปถาวร
        methods["P/E ค่ากลางทั้งช่วง"] = hist["มูลค่าจาก P/E"]
        methods["P/E ค่ากลาง 5 ปีล่าสุด"] = hist["มูลค่าจาก P/E 5 ปี"]
        if use_dcf:      # P/FCF ไม่มีความหมายถ้าคำนวณ FCF ไม่ได้
            methods["P/FCF ค่ากลางทั้งช่วง"] = hist["มูลค่าจาก P/FCF"]
            methods["P/FCF ค่ากลาง 5 ปีล่าสุด"] = hist["มูลค่าจาก P/FCF 5 ปี"]

    # P/BV — วิธีมาตรฐานสำหรับสถาบันการเงิน
    # เหตุผล : ธนาคารมีสินทรัพย์เป็นตัวเงินเกือบทั้งหมด มูลค่าตามบัญชีจึงใกล้เคียงมูลค่าจริง
    pbv = book_value_method(data, R)
    if pbv:
        methods["P/BV ค่ากลางย้อนหลัง"] = pbv["มูลค่าจาก P/BV"]

    # DDM ใช้ได้เฉพาะหุ้นที่จ่ายปันผลเป็นเนื้อเป็นหนัง
    # หุ้นที่จ่ายปันผลน้อย (เช่น Apple จ่าย ~15% ของกำไร) DDM จะให้ค่าต่ำเตี้ยจนไร้ความหมาย
    payout = R["table"].loc["Payout Ratio"].tail(3).mean() if "Payout Ratio" in R["table"].index else np.nan
    d = ddm(R, wacc, g2)
    # ถ้าใช้ DCF ไม่ได้ DDM กลายเป็นวิธีหลัก จึงลดเกณฑ์ลงเหลือ 20%
    threshold = 30 if use_dcf else 20
    ddm_used = bool(d and pd.notna(payout) and payout >= threshold)
    if d:
        label = "DDM (ปันผล)" if ddm_used else "DDM (ปันผล) — ไม่นับ: จ่ายปันผลน้อย"
        methods[label] = d

    scenarios = {}
    if use_dcf:
        scenarios = {
            "ฉากแย่ (g1 −4%, WACC +1%)": bear["มูลค่าต่อหุ้น"],
            "ฉากกลาง": base["มูลค่าต่อหุ้น"],
            "ฉากดี (g1 +4%, WACC −1%)": bull["มูลค่าต่อหุ้น"],
        }

    implied_g = (reverse_dcf(price, fcf0, years1, g2, wacc, shares, net_debt)
                 if (use_dcf and price) else None)
    sens = (sensitivity(fcf0, years1, g2, shares, net_debt, wacc, g1)
            if use_dcf else None)

    valid = [v for k, v in methods.items()
             if v is not None and np.isfinite(v) and v > 0 and "ไม่นับ" not in k]
    fair = float(np.median(valid)) if valid else None

    return {
        "ticker": data.get("ticker"),
        "ราคาปัจจุบัน": price,
        "สกุลเงิน": data.get("info", {}).get("currency", ""),
        "wacc_detail": w,
        "inputs": inp,
        "wacc ที่ใช้": wacc, "g1 ที่ใช้": g1, "g2 ที่ใช้": g2, "years1": years1,
        "base_dcf": base,
        "methods": methods,
        "scenarios": scenarios,
        "payout เฉลี่ย 3 ปี (%)": float(payout) if pd.notna(payout) else None,
        "fair_value (ค่ากลางทุกวิธี)": fair,
        "ส่วนต่างจากราคา (%)": ((fair / price - 1) * 100) if fair and price else None,
        "อัตราโตที่ตลาดคาดหวัง": implied_g,
        "sensitivity": sens,
        "historical": hist,
        "book_value": pbv,
        "ใช้ DCF ได้ไหม": use_dcf,
        "เป็นสถาบันการเงิน": fin,
        "หมายเหตุวิธีประเมิน": notes,
        "ปีข้อมูล": len(R["years"]),
        "แหล่งงบ": data.get("statements_source", "yfinance"),
    }


# ---------------------------------------------------------------------------
# แสดงผล
# ---------------------------------------------------------------------------

def _print_methods_only(v: dict) -> None:
    """แสดงผลแบบย่อ สำหรับหุ้นที่ทำ DCF ไม่ได้ (ธนาคาร หรือ FCF ติดลบ)"""
    cur, price, W = v["สกุลเงิน"], v["ราคาปัจจุบัน"], 74
    print("\n  มูลค่าต่อหุ้นจากแต่ละวิธี (ใช้หาค่ากลาง)")
    print("  " + "-" * (W - 4))
    for k, val in v["methods"].items():
        if val is None or not np.isfinite(val):
            print(f"  {k:<34}{'คำนวณไม่ได้':>12}")
            continue
        gap = (val / price - 1) * 100 if price else np.nan
        print(f"  {k:<34}{val:>12,.2f} {cur}  ({gap:+.0f}%)")
    print("  " + "-" * (W - 4))
    fair = v["fair_value (ค่ากลางทุกวิธี)"]
    print(f"  {'ราคาตลาดวันนี้':<34}{price:>12,.2f} {cur}")
    if fair:
        print(f"  {'มูลค่าที่ประเมินได้ (ค่ากลาง)':<34}{fair:>12,.2f} {cur}")
        print(f"  {'ส่วนต่าง':<34}{v['ส่วนต่างจากราคา (%)']:>12,.1f} %")
    else:
        print("  ประเมินมูลค่าไม่ได้เลย — ไม่มีวิธีใดใช้ได้กับหุ้นตัวนี้")

    bv = v.get("book_value")
    if bv:
        print(f"\n  P/BV ย้อนหลัง : ค่ากลาง {bv['P/BV ค่ากลาง']:.2f} เท่า"
              f" | 5 ปีล่าสุด {bv['P/BV ค่ากลาง 5 ปีล่าสุด']:.2f} เท่า"
              f" | มูลค่าตามบัญชีต่อหุ้นล่าสุด {bv['BVPS ล่าสุด']:,.2f} {cur}")
    print("\n" + "=" * W)
    print("  เอกสารนี้สร้างโดยระบบอัตโนมัติเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน")
    print("=" * W)


def print_report(v: dict) -> None:
    cur = v["สกุลเงิน"]
    price = v["ราคาปัจจุบัน"]
    W = 74
    print("=" * W)
    print(f"  Part 4 — ประเมินมูลค่า : {v['ticker']}")
    print(f"  ข้อมูล {v['ปีข้อมูล']} ปี จาก {v['แหล่งงบ']}")
    print("=" * W)

    w = v["wacc_detail"]
    print("\n  อัตราคิดลด (WACC) — คำนวณจากตัวเลขจริงของบริษัท")
    print("  " + "-" * (W - 4))
    print(f"  {'beta':<26}{w['beta']:>12.2f}")
    print(f"  {'พันธบัตร (rf)':<26}{w['พันธบัตร (rf)']:>11.2%}")
    print(f"  {'ต้นทุนส่วนทุน (CAPM)':<26}{w['ต้นทุนส่วนทุน']:>11.2%}")
    print(f"  {'ต้นทุนหนี้':<26}{w['ต้นทุนหนี้']:>11.2%}")
    print(f"  {'อัตราภาษี':<26}{w['อัตราภาษี']:>11.2%}")
    print(f"  {'น้ำหนัก ทุน / หนี้':<26}{w['น้ำหนักส่วนทุน']:>6.0%} /{w['น้ำหนักหนี้']:>5.0%}")
    print(f"  {'>> WACC ที่ใช้':<26}{v['wacc ที่ใช้']:>11.2%}")

    if v.get("หมายเหตุวิธีประเมิน"):
        print("\n  หมายเหตุวิธีประเมิน")
        print("  " + "-" * (W - 4))
        for n in v["หมายเหตุวิธีประเมิน"]:
            print(f"  ⚠️ {n}")

    if not v.get("ใช้ DCF ได้ไหม"):
        _print_methods_only(v)
        return

    i = v["inputs"]
    print("\n  สมมติฐานตั้งต้น")
    print("  " + "-" * (W - 4))
    print(f"  {'FCF ปีฐาน (เฉลี่ย 3 ปี)':<30}{i['fcf0 (เฉลี่ย 3 ปี)']/1e6:>14,.0f} ล้าน")
    print(f"  {'FCF ปีล่าสุดปีเดียว':<30}{i['fcf ปีล่าสุด']/1e6:>14,.0f} ล้าน")
    print(f"  {'อัตราโตช่วงแรก (g1)':<30}{v['g1 ที่ใช้']:>14.2%}")
    if i["ถูกตัดเพดานไหม"]:
        print(f"  {'  ↳ ตัดเพดานจาก':<30}{i['g1 ก่อนตัดเพดาน']:>14.2%}  (เพดาน {MAX_G1:.0%})")
    print(f"  {'อัตราโตถาวร (g2)':<30}{v['g2 ที่ใช้']:>14.2%}")
    print(f"  {'จำนวนปีช่วงโตสูง':<30}{v['years1']:>14} ปี")
    print(f"  {'หนี้สินสุทธิ':<30}{i['net_debt']/1e6:>14,.0f} ล้าน")

    b = v["base_dcf"]
    print("\n  โครงสร้างมูลค่า (ฉากกลาง)")
    print("  " + "-" * (W - 4))
    print(f"  {'PV ช่วงโตสูง 10 ปี':<30}{b['PV ช่วงโตสูง']/1e6:>14,.0f} ล้าน")
    print(f"  {'PV มูลค่าสุดท้าย':<30}{b['PV มูลค่าสุดท้าย']/1e6:>14,.0f} ล้าน")
    print(f"  {'  ↳ คิดเป็นสัดส่วน':<30}{b['สัดส่วนมูลค่าสุดท้าย']:>14.0%}")
    if b["สัดส่วนมูลค่าสุดท้าย"] > 0.75:
        print("     ⚠️ มูลค่าเกิน 75% มาจาก 'ปีที่ 11 เป็นต้นไป' ซึ่งเดายากที่สุด")
        print("        แปลว่าผลลัพธ์ไวต่อสมมติฐานมาก ควรดูตาราง Sensitivity ประกอบ")

    print("\n  ช่วงมูลค่าจาก DCF (เปลี่ยนสมมติฐาน)")
    print("  " + "-" * (W - 4))
    for k, val in v["scenarios"].items():
        gap = (val / price - 1) * 100 if price else np.nan
        print(f"  {k:<34}{val:>12,.2f} {cur}  ({gap:+.0f}%)")

    print("\n  มูลค่าต่อหุ้นจากแต่ละวิธี (ใช้หาค่ากลาง)")
    print("  " + "-" * (W - 4))
    for k, val in v["methods"].items():
        if val is None or not np.isfinite(val):
            print(f"  {k:<34}{'คำนวณไม่ได้':>12}")
            continue
        gap = (val / price - 1) * 100 if price else np.nan
        print(f"  {k:<34}{val:>12,.2f} {cur}  ({gap:+.0f}%)")
    po = v.get("payout เฉลี่ย 3 ปี (%)")
    if po is not None:
        print(f"  (Payout Ratio เฉลี่ย 3 ปี = {po:.0f}% — ต่ำกว่า 30% จะไม่นับ DDM)")

    print("  " + "-" * (W - 4))
    fair = v["fair_value (ค่ากลางทุกวิธี)"]
    print(f"  {'ราคาตลาดวันนี้':<30}{price:>14,.2f} {cur}")
    if fair:
        print(f"  {'มูลค่าที่ประเมินได้ (ค่ากลาง)':<30}{fair:>14,.2f} {cur}")
        print(f"  {'ส่วนต่าง':<30}{v['ส่วนต่างจากราคา (%)']:>14,.1f} %")

    ig = v["อัตราโตที่ตลาดคาดหวัง"]
    if ig is not None:
        print("\n  Reverse DCF — ราคาวันนี้กำลังบอกอะไร")
        print("  " + "-" * (W - 4))
        print(f"  ที่ราคา {price:,.2f} {cur} ตลาดกำลังคาดว่า FCF จะโตปีละ "
              f"{ig:+.1%} ติดต่อกัน {v['years1']} ปี")
        hist_g = i["ที่มาของ g1"]
        gs = [f"{k} = {val:.1f}%" for k, val in hist_g.items() if val is not None]
        print(f"  เทียบกับที่ทำได้จริงย้อนหลัง : {' | '.join(gs) if gs else 'ไม่มีข้อมูล'}")
        print("  → ถ้าตัวเลขที่ตลาดคาด สูงกว่าที่บริษัทเคยทำได้มาก = ราคาแพง")

    # --- ตาราง multiple ย้อนหลัง : แสดงให้ตรวจสอบด้วยตาได้ ---
    h = v.get("historical")
    if h and isinstance(h.get("ตาราง"), pd.DataFrame) and not h["ตาราง"].empty:
        t = h["ตาราง"]
        print("\n  P/E และ P/FCF ย้อนหลังรายปี (ตรวจสอบได้ด้วยตา)")
        print("  " + "-" * (W - 4))
        def cell(x, dec=1):
            return f"{x:>10,.{dec}f}" if pd.notna(x) else f"{'-':>10}"

        print(f"  {'ปี':<8}{'ราคาสิ้นปีงบ':>14}{'EPS':>10}{'P/E':>10}{'P/FCF':>10}")
        for y, r in t.iterrows():
            print(f"  {y:<8}{r['ราคาสิ้นปีงบ']:>14,.2f}"
                  + cell(r.get("EPS"), 2) + cell(r["P/E"]) + cell(r["P/FCF"]))
        print("  " + "-" * (W - 4))
        print(f"  {'ค่ากลางทั้งช่วง':<22}{'':>10}{h['P/E ค่ากลาง']:>10,.1f}"
              f"{h['P/FCF ค่ากลาง']:>10,.1f}")
        print(f"  {'ค่ากลาง 5 ปีล่าสุด':<22}{'':>10}"
              f"{h['P/E ค่ากลาง 5 ปีล่าสุด']:>10,.1f}"
              f"{h['P/FCF ค่ากลาง 5 ปีล่าสุด']:>10,.1f}")
        print(f"  {'ต่ำสุด – สูงสุด':<22}{'':>10}"
              f"{t['P/E'].min():>5,.1f}–{t['P/E'].max():<4,.1f}"
              f"{t['P/FCF'].min():>6,.1f}–{t['P/FCF'].max():<4,.1f}")
        print()
        print("  ⚠️ ทำไมต้องดู 2 ค่า : ถ้าตลาดเปลี่ยนมุมมองต่อหุ้นตัวนี้ไปถาวร")
        print("     ค่ากลางทั้งช่วง = สมมติว่าตลาดจะกลับไปให้ราคาแบบยุคเก่า (อนุรักษ์นิยม)")
        print("     ค่ากลาง 5 ปีล่าสุด = สมมติว่ามุมมองใหม่ของตลาดจะอยู่ต่อไป")
        print("     ทั้งสองเป็น 'มุมมอง' ไม่ใช่ข้อเท็จจริง — ดูตัวเลขรายปีประกอบเสมอ")

    print("\n  Sensitivity — มูลค่าต่อหุ้นเมื่อเปลี่ยนสมมติฐาน")
    print("  " + "-" * (W - 4))
    s = v["sensitivity"]
    print("  WACC\\g1 " + "".join(f"{c:>11}" for c in s.columns))
    for idx, row in s.iterrows():
        print(f"  {idx:<8}" + "".join(
            f"{val:>11,.0f}" if pd.notna(val) else f"{'-':>11}" for val in row))
    print()
    print("  อ่านตารางนี้อย่างไร : ถ้าตัวเลขในตารางกระจายกว้างมาก")
    print("  แปลว่าอย่าเชื่อ 'มูลค่าตัวเดียว' ให้ใช้เป็นช่วงแทน")

    print("\n" + "=" * W)
    print("  เอกสารนี้สร้างโดยระบบอัตโนมัติเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน")
    print("=" * W)


# ---------------------------------------------------------------------------
# รันจาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Part 4 — ประเมินมูลค่าหุ้น")
    p.add_argument("ticker")
    p.add_argument("--wacc", type=float, help="กำหนดอัตราคิดลดเอง เช่น 0.09")
    p.add_argument("--g1", type=float, help="กำหนดอัตราโตช่วงแรกเอง เช่น 0.08")
    p.add_argument("--g2", type=float, default=DEFAULT_TERMINAL_G, help="อัตราโตถาวร")
    p.add_argument("--years", type=int, default=DEFAULT_STAGE1_YEARS, help="ปีช่วงโตสูง")
    p.add_argument("--rf", type=float, help="อัตราพันธบัตร (หุ้นไทยควรใส่ของไทย)")
    p.add_argument("--refresh", action="store_true")
    args = p.parse_args()

    try:
        data = get_stock_data(args.ticker, force_refresh=args.refresh)
        R = compute_ratios(data)
        v = value_stock(data, R, wacc=args.wacc, g1=args.g1, g2=args.g2,
                        years1=args.years, rf=args.rf)
    except Exception as e:
        print(f"\n[ไม่สำเร็จ] {type(e).__name__}: {e}\n", file=sys.stderr)
        return 1

    print_report(v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
