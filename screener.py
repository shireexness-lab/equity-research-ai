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
        row.update({
            "ชื่อบริษัท": info.get("longName") or ticker,
            "กลุ่ม": info.get("sector") or "-",
            "สกุลเงิน": v["สกุลเงิน"],
            "ราคา": price,
            "มูลค่าที่ประเมินได้": fair,
            "ส่วนลด (%)": (1 - price / fair) * 100 if fair and price else np.nan,
            "โซน": b["โซนปัจจุบัน"],
            "ความน่าเชื่อถือ": rel["ระดับ"],
            "คะแนน": rel["คะแนน"],
            "ปีข้อมูล": v["ปีข้อมูล"],
            "ROE เฉลี่ย (%)": R["summary"].get("ROE เฉลี่ย (%)"),
            "CAGR รายได้ (%)": R["summary"].get("CAGR รายได้ (%)"),
            "ตลาดคาดโต (%)": (v["อัตราโตที่ตลาดคาดหวัง"] * 100
                              if v.get("อัตราโตที่ตลาดคาดหวัง") is not None else None),
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
    """คัดเฉพาะหุ้นที่ราคาต่ำกว่ามูลค่าที่ประเมินได้"""
    if df.empty or "ส่วนลด (%)" not in df.columns:
        return df
    m = (df["ส่วนลด (%)"] >= min_discount) & df["ปัญหา"].eq("")
    if min_score:
        m &= df["คะแนน"].fillna(0) >= min_score
    return df[m].reset_index(drop=True)


# ---------------------------------------------------------------------------
# ชุดหุ้นสำเร็จรูป
# ---------------------------------------------------------------------------

def preset(name: str, limit=None):
    """ชุดหุ้นตั้งต้น — thai / us"""
    from tickers import POPULAR_US, THAI_STOCKS
    if name == "thai":
        out = [f"{s}.BK" for s in THAI_STOCKS]
    elif name == "us":
        out = list(POPULAR_US)
    else:
        raise ValueError("ชุดหุ้นมีให้เลือก : thai หรือ us")
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
    p = argparse.ArgumentParser(description="สแกนหาหุ้นที่ราคาต่ำกว่ามูลค่าที่ประเมินได้")
    p.add_argument("tickers", nargs="*", help="ชื่อย่อหุ้น เว้นวรรคคั่น")
    p.add_argument("--list", choices=["thai", "us"], help="ใช้ชุดหุ้นสำเร็จรูป")
    p.add_argument("--max", type=int, default=20, help="จำนวนสูงสุดที่จะสแกน")
    p.add_argument("--rf", type=float, help="อัตราพันธบัตร (หุ้นไทยใส่ 0.025)")
    p.add_argument("--mos", type=float, help="ส่วนเผื่อความปลอดภัย")
    p.add_argument("--min-discount", type=float, default=0.0,
                   help="แสดงเฉพาะที่ส่วนลดมากกว่ากี่ % (ค่าเริ่มต้น 0)")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--csv", help="บันทึกผลเป็นไฟล์ CSV")
    args = p.parse_args()

    tickers = list(args.tickers)
    if args.list:
        tickers += preset(args.list)
    if not tickers:
        p.error("ต้องระบุชื่อหุ้น หรือใช้ --list thai / --list us")
    tickers = tickers[:args.max]

    est = len(tickers) * 30 / 60
    print(f"\nกำลังสแกน {len(tickers)} ตัว — คาดว่าใช้เวลาราว {est:.0f} นาที")
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
