"""
bands.py — Part 6 : Fair Price & Recommendation Bands
======================================================
หน้าที่ : แปลง "มูลค่าที่ประเมินได้" จาก Part 4 → ช่วงราคาที่ใช้ตัดสินใจได้จริง

แนวคิด Margin of Safety (ส่วนเผื่อความปลอดภัย)
-----------------------------------------------
เบนจามิน เกรแฮม : เราไม่มีวันประเมินมูลค่าได้แม่นยำ จึงต้อง **ซื้อต่ำกว่าที่ประเมินไว้มาก**
เพื่อให้ยังกำไรได้แม้ประเมินผิด

ตัวอย่าง : ประเมินได้ 100 บาท ถ้าใช้ MoS 25% จะซื้อเมื่อราคาต่ำกว่า 75 บาท
→ ถ้าเราประเมินสูงไป 20% (มูลค่าจริง 80) ซื้อที่ 75 ก็ยังไม่ขาดทุน

**MoS ควรกว้างขึ้นเมื่อไร**
  • ข้อมูลย้อนหลังน้อย (ประเมินไม่แม่น)
  • ผลลัพธ์แต่ละวิธีต่างกันมาก (ไม่แน่ใจ)
  • กำไร/กระแสเงินสดผันผวนสูง
ระบบนี้จึง **ปรับ MoS อัตโนมัติตามความไม่แน่นอนที่วัดได้จริง**

วิธีใช้จาก Terminal
-------------------
    python3 bands.py AAPL
    python3 bands.py AAPL --mos 0.35        # กำหนดส่วนเผื่อเอง 35%
"""

import argparse
import sys

import numpy as np
import pandas as pd

from data_layer import get_stock_data
from ratios import compute_ratios
from valuation import value_stock

BASE_MOS = 0.25          # ส่วนเผื่อพื้นฐาน 25%
MAX_MOS = 0.50           # ไม่ให้เกิน 50% (ไม่งั้นแทบไม่มีหุ้นให้ซื้อ)
MIN_MOS = 0.15


# ---------------------------------------------------------------------------
# คำนวณส่วนเผื่อความปลอดภัยตามความไม่แน่นอนจริง
# ---------------------------------------------------------------------------

def adaptive_mos(v: dict, R: dict) -> dict:
    """
    ปรับ MoS ตาม 3 สัญญาณที่วัดได้ — ไม่ใช้ความรู้สึก

    1. ข้อมูลน้อย       : < 10 ปี  → +5%   (ประเมินจากข้อมูลสั้นเชื่อได้น้อยกว่า)
    2. วิธีต่าง ๆ ขัดกัน : ค่าสูงสุด/ต่ำสุด ต่างเกิน 2 เท่า → +10%
    3. กระแสเงินสดผันผวน: ส่วนเบี่ยงเบน FCF Margin สูง → +5%
    """
    reasons = []
    mos = BASE_MOS

    n_years = v.get("ปีข้อมูล", 0)
    if n_years < 10:
        mos += 0.05
        reasons.append(f"ข้อมูลย้อนหลังเพียง {n_years} ปี (ต่ำกว่า 10 ปี) → +5%")

    vals = [x for k, x in v["methods"].items()
            if x is not None and np.isfinite(x) and x > 0 and "ไม่นับ" not in k]
    spread = (max(vals) / min(vals)) if len(vals) >= 2 and min(vals) > 0 else 1.0
    if spread > 2.0:
        mos += 0.10
        reasons.append(f"ผลแต่ละวิธีต่างกัน {spread:.1f} เท่า (เกิน 2 เท่า) → +10%")

    fcf_margin = R["table"].loc["FCF Margin"].dropna() if "FCF Margin" in R["table"].index else pd.Series(dtype=float)
    vol = float(fcf_margin.std()) if len(fcf_margin) > 2 else np.nan
    if pd.notna(vol) and vol > 5.0:
        mos += 0.05
        reasons.append(f"FCF Margin ผันผวน (ส่วนเบี่ยงเบน {vol:.1f}%) → +5%")

    mos = float(min(max(mos, MIN_MOS), MAX_MOS))
    if not reasons:
        reasons.append("ไม่พบสัญญาณความไม่แน่นอนพิเศษ → ใช้ค่าพื้นฐาน 25%")

    return {"mos": mos, "เหตุผล": reasons,
            "ความต่างระหว่างวิธี (เท่า)": spread,
            "FCF Margin ผันผวน (%)": vol}


def reliability(v: dict, m: dict) -> dict:
    """
    ให้ระดับความน่าเชื่อถือของการประเมิน — สำคัญพอ ๆ กับตัวเลขเอง

    ทำไมต้องมี : ระบบสามารถให้ตัวเลข "มูลค่า 31.87 บาท" ออกมาได้เสมอ
    แต่ถ้าวิธีต่าง ๆ ให้ผลต่างกัน 46 เท่า ตัวเลขนั้นแทบไม่มีความหมาย
    การรายงานตัวเลขโดยไม่บอกว่าเชื่อได้แค่ไหน = การหลอกตัวเอง
    """
    spread = m.get("ความต่างระหว่างวิธี (เท่า)", 1.0)
    years = v.get("ปีข้อมูล", 0)
    tv_share = v.get("base_dcf", {}).get("สัดส่วนมูลค่าสุดท้าย", np.nan)

    warns = []
    score = 100
    if spread > 5:
        score -= 40
        warns.append(f"วิธีต่าง ๆ ให้ผลต่างกัน {spread:.0f} เท่า — ค่ากลางแทบไม่มีความหมาย")
    elif spread > 2.5:
        score -= 20
        warns.append(f"วิธีต่าง ๆ ให้ผลต่างกัน {spread:.1f} เท่า — ควรดูเป็นช่วง ไม่ใช่ตัวเลขเดียว")
    if years < 6:
        score -= 25
        warns.append(f"ข้อมูลเพียง {years} ปี — สั้นเกินกว่าจะเห็นวัฏจักรธุรกิจ")
    elif years < 10:
        score -= 10
        warns.append(f"ข้อมูล {years} ปี — ยังไม่ครบ 1 รอบวัฏจักรเศรษฐกิจเต็ม")
    if pd.notna(tv_share) and tv_share > 0.75:
        score -= 15
        warns.append(f"มูลค่า {tv_share:.0%} มาจากปีที่ 11 เป็นต้นไป ซึ่งเดายากที่สุด")

    score = max(score, 0)
    level = "สูง" if score >= 75 else ("ปานกลาง" if score >= 50 else "ต่ำ")
    return {"คะแนน": score, "ระดับ": level, "คำเตือน": warns}


# ---------------------------------------------------------------------------
# สร้างช่วงราคา
# ---------------------------------------------------------------------------

def price_bands(fair_value: float, mos: float = BASE_MOS) -> dict:
    """
    แบ่งช่วงราคา 5 ระดับจากมูลค่าที่ประเมินได้

        Strong Buy : ต่ำกว่ามูลค่าเกินส่วนเผื่อ        (ปลอดภัยมาก)
        Buy        : ต่ำกว่ามูลค่า 10% ถึงส่วนเผื่อ
        Hold       : ใกล้มูลค่า (−10% ถึง +5%)
        Reduce     : สูงกว่ามูลค่า 5–20%
        Sell       : สูงกว่ามูลค่าเกิน 20%
    """
    if fair_value is None or not np.isfinite(fair_value) or fair_value <= 0:
        raise ValueError("ไม่มีมูลค่าที่ประเมินได้ จึงสร้างช่วงราคาไม่ได้")
    strong = fair_value * (1 - mos)
    buy_hi = fair_value * 0.90
    hold_hi = fair_value * 1.05
    reduce_hi = fair_value * 1.20
    return {
        "Strong Buy": (0.0, strong),
        "Buy": (strong, buy_hi),
        "Hold": (buy_hi, hold_hi),
        "Reduce": (hold_hi, reduce_hi),
        "Sell": (reduce_hi, float("inf")),
    }


def classify(price: float, bands: dict) -> str:
    """ราคาปัจจุบันตกอยู่ช่วงไหน"""
    for name, (lo, hi) in bands.items():
        if lo <= price < hi:
            return name
    return "Sell"


def build(data, R=None, v=None, mos=None) -> dict:
    """รวมทุกอย่าง : ประเมินมูลค่า → หา MoS → สร้างช่วง → บอกว่าราคาวันนี้อยู่ตรงไหน"""
    R = R or compute_ratios(data)
    v = v or value_stock(data, R)

    fair = v["fair_value (ค่ากลางทุกวิธี)"]
    if fair is None:
        raise ValueError("ประเมินมูลค่าไม่ได้ จึงสร้างช่วงราคาไม่ได้")

    m = adaptive_mos(v, R)
    used_mos = float(mos) if mos is not None else m["mos"]
    rel = reliability(v, m)
    bands = price_bands(fair, used_mos)
    price = v["ราคาปัจจุบัน"]
    zone = classify(price, bands) if price else None

    # ราคาที่ต้องรอ ถ้ายังไม่ถึงโซนซื้อ
    buy_trigger = bands["Buy"][1]      # ขอบบนของโซน Buy
    wait_pct = ((buy_trigger / price - 1) * 100) if price else None

    return {
        "ticker": v["ticker"], "สกุลเงิน": v["สกุลเงิน"],
        "ราคาปัจจุบัน": price,
        "มูลค่าที่ประเมินได้": fair,
        "mos ที่ใช้": used_mos,
        "mos_detail": m,
        "bands": bands,
        "ความน่าเชื่อถือ": rel,
        "โซนปัจจุบัน": zone,
        "ราคาที่เข้าโซน Buy": buy_trigger,
        "ต้องลดลงอีก (%)": -wait_pct if wait_pct is not None and wait_pct < 0 else None,
        "อัตราโตที่ตลาดคาดหวัง": v.get("อัตราโตที่ตลาดคาดหวัง"),
        "ปีข้อมูล": v.get("ปีข้อมูล"),
        "แหล่งงบ": v.get("แหล่งงบ"),
        "valuation": v,
    }


# ---------------------------------------------------------------------------
# แสดงผล
# ---------------------------------------------------------------------------

ZONE_NOTE = {
    "Strong Buy": "ราคาต่ำกว่ามูลค่าที่ประเมินมาก เกินส่วนเผื่อความปลอดภัย",
    "Buy": "ราคาต่ำกว่ามูลค่าที่ประเมิน แต่ยังไม่ถึงระดับส่วนเผื่อเต็ม",
    "Hold": "ราคาใกล้เคียงมูลค่าที่ประเมิน ไม่มีส่วนเผื่อความปลอดภัย",
    "Reduce": "ราคาสูงกว่ามูลค่าที่ประเมิน",
    "Sell": "ราคาสูงกว่ามูลค่าที่ประเมินมาก",
}


def print_report(b: dict) -> None:
    cur, price = b["สกุลเงิน"], b["ราคาปัจจุบัน"]
    W = 74
    print("=" * W)
    print(f"  Part 6 — ช่วงราคาและส่วนเผื่อความปลอดภัย : {b['ticker']}")
    print(f"  ข้อมูล {b['ปีข้อมูล']} ปี จาก {b['แหล่งงบ']}")
    print("=" * W)

    print(f"\n  มูลค่าที่ประเมินได้ (ค่ากลางทุกวิธี) : {b['มูลค่าที่ประเมินได้']:,.2f} {cur}")
    print(f"  ราคาตลาดวันนี้                        : {price:,.2f} {cur}")

    print(f"\n  ส่วนเผื่อความปลอดภัยที่ใช้ : {b['mos ที่ใช้']:.0%}")
    print("  " + "-" * (W - 4))
    for r in b["mos_detail"]["เหตุผล"]:
        print(f"    • {r}")

    print("\n  ช่วงราคา")
    print("  " + "-" * (W - 4))
    for name, (lo, hi) in b["bands"].items():
        if hi == float("inf"):
            rng = f"มากกว่า {lo:,.2f}"
        elif lo == 0:
            rng = f"ต่ำกว่า {hi:,.2f}"
        else:
            rng = f"{lo:,.2f} – {hi:,.2f}"
        mark = "  ◀━━ ราคาวันนี้อยู่ตรงนี้" if name == b["โซนปัจจุบัน"] else ""
        print(f"  {name:<12}{rng:>28} {cur}{mark}")

    rel = b["ความน่าเชื่อถือ"]
    print(f"\n  ความน่าเชื่อถือของการประเมิน : {rel['ระดับ']} ({rel['คะแนน']}/100)")
    print("  " + "-" * (W - 4))
    if rel["คำเตือน"]:
        for wmsg in rel["คำเตือน"]:
            print(f"    ⚠️ {wmsg}")
    else:
        print("    ไม่พบข้อจำกัดสำคัญ")
    if rel["คะแนน"] < 50:
        print("    → ความน่าเชื่อถือต่ำ ควรใช้ตัวเลขนี้เป็นเพียงจุดตั้งต้นในการค้นคว้าต่อ")
        print("      ไม่ควรใช้ตัดสินใจโดยลำพัง")

    print("\n  สรุป")
    print("  " + "-" * (W - 4))
    print(f"  โซนปัจจุบัน : {b['โซนปัจจุบัน']}")
    print(f"  {ZONE_NOTE.get(b['โซนปัจจุบัน'], '')}")
    if b["ต้องลดลงอีก (%)"]:
        print(f"  ราคาต้องลดลงอีก {b['ต้องลดลงอีก (%)']:.1f}% "
              f"(ถึง {b['ราคาที่เข้าโซน Buy']:,.2f} {cur}) จึงเข้าโซน Buy")

    ig = b.get("อัตราโตที่ตลาดคาดหวัง")
    if ig is not None:
        print(f"\n  ราคาวันนี้ตลาดคาดว่า FCF จะโตปีละ {ig:+.1%} เป็นเวลา 10 ปี")
        print("  คำถามที่ต้องตอบก่อนตัดสินใจ : เชื่อไหมว่าบริษัททำได้จริง")

    print("\n" + "=" * W)
    print("  ⚠️ ช่วงราคานี้คำนวณจากสูตรและสมมติฐานที่ตั้งไว้เท่านั้น")
    print("     เป็นเครื่องมือช่วยคิด ไม่ใช่คำแนะนำการลงทุน")
    print("=" * W)


# ---------------------------------------------------------------------------
# รันจาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Part 6 — ช่วงราคาซื้อขาย")
    p.add_argument("ticker")
    p.add_argument("--mos", type=float, help="กำหนดส่วนเผื่อความปลอดภัยเอง เช่น 0.30")
    p.add_argument("--wacc", type=float)
    p.add_argument("--g1", type=float)
    p.add_argument("--rf", type=float)
    p.add_argument("--refresh", action="store_true")
    args = p.parse_args()

    try:
        data = get_stock_data(args.ticker, force_refresh=args.refresh)
        R = compute_ratios(data)
        v = value_stock(data, R, wacc=args.wacc, g1=args.g1, rf=args.rf)
        b = build(data, R, v, mos=args.mos)
    except Exception as e:
        print(f"\n[ไม่สำเร็จ] {type(e).__name__}: {e}\n", file=sys.stderr)
        return 1

    print_report(b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
