"""
tools_deep_scan.py — หา Strong Buy ทั้งตลาด (รันข้ามคืนบน MacBook)
=====================================================================
ปัญหา
-----
คำแนะนำ Strong Buy รู้ได้จากการวิเคราะห์ลึกเท่านั้น ซึ่งใช้เวลาราว 30 วินาที/ตัว

    หุ้นไทย  866 ตัว   = 7 ชั่วโมง
    หุ้นสหรัฐ 6,000 ตัว = 50 ชั่วโมง

กดปุ่มบนเว็บแล้วรอไม่ได้แน่นอน และ Streamlit Cloud จะตัดการเชื่อมต่อก่อน

วิธีแก้ — แยกเป็น 2 จังหวะ
---------------------------
    [ กลางคืน ]  MacBook รันไฟล์นี้ วิเคราะห์ลึกทีละตัว บันทึกผลสะสม
    [ กลางวัน ]  เปิดเว็บ กดดูรายการ Strong Buy ได้ทันทีใน 2 วินาที

ทำงานต่อจากที่ค้างไว้ได้
-------------------------
ถ้าปิดเครื่องกลางคัน หรือเน็ตหลุด รันใหม่แล้วมันจะ **ข้ามตัวที่ทำไปแล้ว**
ไม่ต้องเริ่มนับหนึ่ง เพราะบันทึกผลทุก 10 ตัว

ลดเวลาด้วยการคัดก่อน
---------------------
    --top 150   เอาเฉพาะ 150 ตัวที่คะแนนพรีสกรีนสูงสุด (7 ชม. -> 1.2 ชม.)
    --all       วิเคราะห์ทุกตัวจริง ๆ (แม่นที่สุด แต่ใช้เวลาเต็ม)

วิธีใช้
-------
    # แนะนำ : คัดให้เหลือ 150 ตัวก่อน แล้ววิเคราะห์
    python3 tools_deep_scan.py --thai --top 150

    # เอาให้ครบทุกตัว รันข้ามคืน
    python3 tools_deep_scan.py --thai --all

    # หุ้นสหรัฐยอดนิยม
    python3 tools_deep_scan.py --us --top 100

    # ดูผลที่ทำไว้แล้ว
    python3 tools_deep_scan.py --show
"""

import argparse
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd

import snapshot

# ชื่อชุดข้อมูลที่เก็บผลวิเคราะห์ลึก แยกจากผลคัดกรองเร็ว
DEEP_KEY = "deep-{market}"

# คอลัมน์ที่เก็บ — เฉพาะที่ใช้แสดงรายการ Strong Buy
KEEP = ["ticker", "ชื่อบริษัท", "คำแนะนำ", "คะแนนรวม", "ความมั่นใจ (%)",
        "ราคา", "มูลค่าที่ประเมินได้", "ส่วนลด (%)", "โซน",
        "ความน่าเชื่อถือ", "คะแนนความน่าเชื่อถือ", "ปีข้อมูล",
        "Buffett", "คุณภาพ", "ความเสี่ยง", "กลุ่ม", "วิเคราะห์เมื่อ", "ปัญหา"]


def analyze_one(ticker: str, rf=None) -> dict:
    """วิเคราะห์ลึก 1 ตัว แล้วสรุปเป็นคำแนะนำ — คืนแถวเดียว"""
    row = {"ticker": ticker, "วิเคราะห์เมื่อ": datetime.now().strftime("%Y-%m-%d"),
           "ปัญหา": ""}
    try:
        from bands import build as build_bands
        from data_layer import get_stock_data
        from ratios import compute_ratios
        from valuation import value_stock
        import forecast as FC
        import news_ai as NA
        import quality as QL
        import recommend as RC
        import risk as RK

        data = get_stock_data(ticker)
        R = compute_ratios(data)
        v = value_stock(data, R, rf=rf)
        b = build_bands(data, R, v)
        v2 = dict(v)
        v2["ความน่าเชื่อถือ"] = b.get("ความน่าเชื่อถือ")

        rk = RK.assess(data, R)
        ql = QL.assess_all(data, R, v=v, rf=rf)
        fc = FC.forecast_all(R)
        nw = NA.analyze(ticker, limit=15)
        rc = RC.build(data, R, v=v2, risk=rk, qual=ql, fc=fc, news=nw)

        if not rc.get("ใช้ได้"):
            row["ปัญหา"] = rc.get("เหตุผล", "สรุปคำแนะนำไม่ได้")
            return row

        rel = b.get("ความน่าเชื่อถือ") or {}
        row.update({
            "ชื่อบริษัท": (data.get("info", {}) or {}).get("longName", ticker),
            "คำแนะนำ": rc["คำแนะนำ"],
            "คะแนนรวม": rc["คะแนนรวม"],
            "ความมั่นใจ (%)": rc["ความมั่นใจ (%)"],
            "ราคา": v["ราคาปัจจุบัน"],
            "มูลค่าที่ประเมินได้": b.get("มูลค่าที่ประเมินได้"),
            "ส่วนลด (%)": v.get("ส่วนต่างจากราคา (%)"),
            "โซน": b.get("โซนปัจจุบัน"),
            "ความน่าเชื่อถือ": rel.get("ระดับ"),
            "คะแนนความน่าเชื่อถือ": rel.get("คะแนน"),
            "ปีข้อมูล": v.get("ปีข้อมูล"),
            "Buffett": (ql.get("Module 3") or {}).get("คะแนนรวม"),
            "คุณภาพ": (ql.get("Module 2") or {}).get("คะแนนรวม"),
            "ความเสี่ยง": rk.get("คะแนนรวม"),
            "กลุ่ม": (data.get("info", {}) or {}).get("sector", "-"),
        })
    except Exception as e:
        row["ปัญหา"] = f"{type(e).__name__}: {str(e)[:70]}"
    return row


def run(tickers, market: str, rf=None, save_every=10):
    """
    วิเคราะห์ทีละตัว บันทึกผลสะสม ทำงานต่อจากที่ค้างได้

    ไม่ใช้หลายเส้นพร้อมกัน เพราะการวิเคราะห์ลึกดึงข้อมูล 4-5 คำขอต่อหุ้น
    ถ้ายิงพร้อมกันจะโดน Yahoo บล็อกแน่นอน ช้าแต่ได้ครบดีกว่าเร็วแต่พัง
    """
    key = DEEP_KEY.format(market=market)
    done, meta = snapshot.info(key)
    have, n_fail_before = {}, 0
    if done is not None and not done.empty and "ticker" in done.columns:
        # เก็บเฉพาะตัวที่สำเร็จ ตัวที่พังให้ลองใหม่
        ok = done[done["ปัญหา"].eq("")] if "ปัญหา" in done.columns else done
        have = {r["ticker"]: r.to_dict() for _, r in ok.iterrows()}
        n_fail_before = len(done) - len(ok)

    tickers = list(dict.fromkeys(tickers))     # กันชื่อซ้ำ
    todo = [t for t in tickers if t not in have]
    reuse = len(tickers) - len(todo)

    # ---- สรุปให้ชัดว่าเลขแต่ละตัวมาจากไหน ----
    # เดิมแสดงแค่ "ต้องวิเคราะห์อีก N ตัว" ซึ่งอ่านแล้วนึกว่าทั้งหมดมีแค่ N
    # ทั้งที่ N คือส่วนที่เหลือหลังหักตัวที่เคยทำไว้แล้ว
    print(f"\n  {'รายชื่อทั้งหมด':<28}{len(tickers):>7,} ตัว")
    print(f"  {'เคยวิเคราะห์สำเร็จแล้ว':<28}{reuse:>7,} ตัว   (จะข้าม ไม่ทำซ้ำ)")
    if n_fail_before:
        print(f"  {'เคยพลาด จะลองใหม่':<28}{n_fail_before:>7,} ตัว")
    print(f"  {'ต้องวิเคราะห์รอบนี้':<28}{len(todo):>7,} ตัว")
    print(f"  {'':>28}{'':>7}     รวมเมื่อเสร็จ = {len(tickers):,} ตัว")

    if not todo:
        print("\n  ทำครบทุกตัวแล้ว ไม่มีอะไรต้องรันเพิ่ม")
        print("  ถ้าต้องการวิเคราะห์ใหม่ทั้งหมด ให้ลบไฟล์ผลเก่าก่อน :")
        print(f"    rm cache/snapshots/{snapshot._fname(key)}")
        print(f"    rm data/snapshots/{snapshot._fname(key)}")
        return pd.DataFrame(list(have.values()))

    total, t0 = len(todo), time.time()
    print(f"\n  คาดว่าใช้เวลาราว {total * 30 / 3600:.1f} ชั่วโมง\n")

    rows = list(have.values())
    for i, tk in enumerate(todo, 1):
        r = analyze_one(tk, rf=rf)
        rows.append(r)

        el = time.time() - t0
        eta = el / i * (total - i)
        mark = ("✓ " + str(r.get("คำแนะนำ", ""))) if not r["ปัญหา"] else "✗"
        print(f"  [{i:>4}/{total}] {tk:<14}{mark:<14}"
              f"เหลืออีก ~{eta/60:>5.0f} นาที")

        if i % save_every == 0 or i == total:
            df = pd.DataFrame(rows)
            for c in KEEP:
                if c not in df.columns:
                    df[c] = None
            snapshot.save(key, df[KEEP], to_repo=True,
                          extra={"ตลาด": market, "จำนวน": len(df)})

    df = pd.DataFrame(rows)
    for c in KEEP:
        if c not in df.columns:
            df[c] = None
    return df[KEEP]


def load_results(market: str):
    """อ่านผลที่บันทึกไว้ — ใช้จากหน้าเว็บด้วย"""
    return snapshot.info(DEEP_KEY.format(market=market))


ORDER = ["Strong Buy", "Buy", "Accumulate", "Hold", "Reduce", "Sell"]

# ส่วนลดที่สูงจนไม่น่าเชื่อ
#
# ส่วนลด 100% แปลว่ามูลค่าที่ประเมินได้เป็น 2 เท่าของราคา
# ส่วนลด 300% แปลว่าเป็น 4 เท่า — ตลาดทั้งตลาดคงไม่พลาดขนาดนั้นพร้อมกัน
# เมื่อเห็นตัวเลขแบบนี้ สาเหตุที่เป็นไปได้มากกว่าคือ **โมเดลของเราเพี้ยน**
# ซึ่งเกิดจากข้อมูลย้อนหลังสั้นเกินไปจนต่อแนวโน้มผิด
ABSURD_DISCOUNT = 100.0


def diagnose(df: pd.DataFrame) -> dict:
    """
    ตรวจสุขภาพของผลวิเคราะห์ทั้งชุด

    ทำไมต้องมี : ถ้าหุ้นครึ่งตลาดขึ้นว่า "ถูกกว่ามูลค่า 300%"
    สิ่งที่ควรสงสัยคือโมเดล ไม่ใช่ตลาด
    """
    if df is None or df.empty:
        return {}
    ok = df[df["ปัญหา"].eq("")] if "ปัญหา" in df.columns else df
    if ok.empty:
        return {}
    d = pd.to_numeric(ok.get("ส่วนลด (%)"), errors="coerce")
    yr = pd.to_numeric(ok.get("ปีข้อมูล"), errors="coerce")
    rel = pd.to_numeric(ok.get("คะแนนความน่าเชื่อถือ"), errors="coerce")
    sc = pd.to_numeric(ok.get("คะแนนรวม"), errors="coerce")
    return {
        "วิเคราะห์สำเร็จ": int(len(ok)),
        "ส่วนลดเกิน 100%": int((d > ABSURD_DISCOUNT).sum()),
        "ส่วนลดเกิน 200%": int((d > 200).sum()),
        "ส่วนลดค่ากลาง (%)": float(d.median()) if d.notna().any() else None,
        "ปีข้อมูลค่ากลาง": float(yr.median()) if yr.notna().any() else None,
        "ความน่าเชื่อถือค่ากลาง": float(rel.median()) if rel.notna().any() else None,
        "คะแนนรวมสูงสุด": float(sc.max()) if sc.notna().any() else None,
        "ความน่าเชื่อถือ >= 70": int((rel >= 70).sum()),
    }


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """นับจำนวนหุ้นในแต่ละคำแนะนำ"""
    if df is None or df.empty or "คำแนะนำ" not in df.columns:
        return pd.DataFrame()
    ok = df[df["ปัญหา"].eq("")] if "ปัญหา" in df.columns else df
    c = ok["คำแนะนำ"].value_counts()
    return pd.DataFrame({"คำแนะนำ": ORDER,
                         "จำนวน": [int(c.get(k, 0)) for k in ORDER]}
                        ).set_index("คำแนะนำ")


# ---------------------------------------------------------------------------
# ใช้จาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="วิเคราะห์ลึกทั้งตลาดเพื่อหา Strong Buy (รันข้ามคืน)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--thai", action="store_true", help="หุ้นไทย")
    g.add_argument("--us", action="store_true", help="หุ้นสหรัฐยอดนิยม")
    p.add_argument("--top", type=int, default=150,
                   help="เอาเฉพาะ N ตัวที่คะแนนพรีสกรีนสูงสุด (ค่าเริ่มต้น 150)")
    p.add_argument("--all", action="store_true", help="วิเคราะห์ทุกตัว ไม่คัดก่อน")
    p.add_argument("--rf", type=float, default=None, help="อัตราพันธบัตร")
    p.add_argument("--show", action="store_true", help="ดูผลที่ทำไว้แล้ว")
    p.add_argument("--reset", action="store_true",
                   help="เริ่มนับหนึ่งใหม่ (ย้ายผลเก่าไปเป็นไฟล์สำรอง "
                        "ไม่ได้ลบทิ้ง และต้องพิมพ์ยืนยันก่อน) — "
                        "ปกติไม่ต้องใช้ เพราะระบบทำต่อจากเดิมให้อยู่แล้ว")
    a = p.parse_args()

    market = "us" if a.us else "thai"

    # ---------- ดูผลเก่า ----------
    if a.show:
        for mk in ("thai", "us"):
            df, meta = load_results(mk)
            print(f"\n{'='*72}\n  ตลาด {mk}")
            if df is None or df.empty:
                print("  ยังไม่มีผล — รัน python3 tools_deep_scan.py "
                      f"--{'thai' if mk=='thai' else 'us'} ก่อน")
                continue
            print(f"  วิเคราะห์ไว้ {len(df):,} ตัว · "
                  f"บันทึกเมื่อ {meta.get('บันทึกเมื่อ','-')[:16]}")
            print("="*72)
            print(summarize(df).to_string())
            sb = df[df["คำแนะนำ"].eq("Strong Buy")] if "คำแนะนำ" in df else pd.DataFrame()
            if len(sb):
                print(f"\n  Strong Buy {len(sb)} ตัว")
                cols = ["ticker", "ชื่อบริษัท", "ราคา", "มูลค่าที่ประเมินได้",
                        "ส่วนลด (%)", "คะแนนรวม", "ความน่าเชื่อถือ", "ปีข้อมูล"]
                print(sb[[c for c in cols if c in sb.columns]]
                      .to_string(index=False))
        print()
        return 0

    # ---------- เตรียมรายชื่อ ----------
    if a.thai:
        from tickers import thai_universe
        universe = thai_universe()
    elif a.us:
        from screener import preset
        universe = preset("us")
    else:
        p.error("ต้องระบุ --thai หรือ --us (หรือ --show เพื่อดูผลเก่า)")

    print(f"\n{'='*72}")
    print(f"  วิเคราะห์ลึกเพื่อหา Strong Buy — ตลาด {market}")
    print(f"{'='*72}")

    if a.reset:
        # -------------------------------------------------------------------
        # --reset เคยลบไฟล์ทิ้งจริง ๆ ทั้งสำเนาในเครื่องและสำเนาในโปรเจกต์
        # ผลคือผลวิเคราะห์ที่ใช้เวลารันหลายชั่วโมงหายไปทั้งหมดในพริบตา
        #
        # ตอนนี้เปลี่ยนเป็น "ย้ายไปเก็บเป็นไฟล์สำรอง" ไม่ลบทิ้ง
        # และต้องพิมพ์ยืนยันก่อน เพราะการสั่งผิดมีต้นทุนสูงมาก
        # -------------------------------------------------------------------
        key = DEEP_KEY.format(market=market)
        targets = [d / snapshot._fname(key)
                   for d in (snapshot.LOCAL_DIR, snapshot.REPO_DIR)]
        found = [f for f in targets if f.exists()]

        if not found:
            print("  ไม่มีผลเก่าอยู่แล้ว — เริ่มนับหนึ่งได้เลย\n")
        else:
            n_rows = 0
            try:
                df_old, _ = load_results(market)
                n_rows = 0 if df_old is None else len(df_old)
            except Exception:
                pass

            print(f"\n  ⚠️  กำลังจะล้างผลวิเคราะห์เดิมของตลาด {market}")
            print(f"     มีอยู่ {n_rows:,} ตัว · {len(found)} ไฟล์")
            print("     การรันใหม่ทั้งตลาดใช้เวลาหลายชั่วโมง")
            print("     ถ้าไม่ล้าง ระบบจะ 'ทำต่อจากเดิม' ให้อยู่แล้ว "
                  "(ไม่ต้องใช้ --reset)")
            ans = input("\n     พิมพ์  ล้าง  แล้วกด Enter เพื่อยืนยัน : ").strip()
            if ans not in ("ล้าง", "reset", "yes"):
                print("  ยกเลิก — ไม่มีอะไรถูกลบ ระบบจะทำต่อจากผลเดิม\n")
            else:
                stamp = datetime.now().strftime("%Y%m%d-%H%M")
                for f in found:
                    bak = f.with_name(f"{f.stem}.สำรอง-{stamp}{f.suffix}")
                    f.rename(bak)
                    print(f"     ย้ายไปเก็บที่ {bak}")
                print("  ล้างแล้ว (ไฟล์เดิมยังอยู่ในชื่อ .สำรอง- "
                      "ถ้าต้องการคืนให้เปลี่ยนชื่อกลับ)\n")

    if not a.all:
        # คัดก่อนด้วยข้อมูลชั้นคัดกรอง เพื่อลดเวลา
        from screener import prescreen_rank, quick_screen
        print(f"\n  ขั้นที่ 1 — คัดกรองเร็วเพื่อจัดอันดับ "
              f"(ราว {len(universe)*1.5/8/60:.0f} นาที)")

        def bar(i, total, msg=""):
            w = 30
            f = int(w * min(i / total, 1.0))
            sys.stdout.write(f"\r  [{'█'*f}{'·'*(w-f)}] {i:,}/{total:,}  "
                             f"{str(msg)[:20]:<20}")
            sys.stdout.flush()

        qdf = quick_screen(universe, progress=bar)
        print()
        ranked = prescreen_rank(qdf[qdf["ปัญหา"].eq("")])
        universe = list(ranked["ticker"].head(a.top))
        print(f"\n  คัดเหลือ {len(universe)} ตัวที่คะแนนพรีสกรีนสูงสุด")
        print(f"  {'อันดับ':<7}{'ticker':<13}{'คะแนน':>7}  โอกาส")
        for i, r in ranked.head(10).iterrows():
            print(f"  {i+1:<7}{r['ticker']:<13}{r['คะแนนพรีสกรีน']:>7.1f}  "
                  f"{r['โอกาสเป็น Strong Buy']}")
        print(f"  ... (แสดง 10 จาก {len(universe)})")
        print("\n  หมายเหตุ : การคัดก่อนเป็นการจัดลำดับความน่าจะเป็น "
              "ไม่ใช่การพิสูจน์")
        print("  อาจพลาดหุ้นที่คะแนนพรีสกรีนกลาง ๆ แต่ดีจริงตอนวิเคราะห์ลึก")
        print("  ถ้าต้องการครบจริง ๆ ใช้ --all แล้วรันข้ามคืน")

    print(f"\n  ขั้นที่ 2 — วิเคราะห์ลึก {len(universe):,} ตัว\n")
    t0 = time.time()
    df = run(universe, market, rf=a.rf)
    mins = (time.time() - t0) / 60

    print(f"\n{'='*72}")
    print(f"  เสร็จแล้ว — ใช้เวลา {mins:.0f} นาที")
    print("="*72)
    print(summarize(df).to_string())

    ok = df[df["ปัญหา"].eq("")]
    sb = ok[ok["คำแนะนำ"].eq("Strong Buy")]
    print(f"\n  วิเคราะห์สำเร็จ {len(ok):,}/{len(df):,} ตัว")

    # ---------- ตรวจสุขภาพของผลทั้งชุด ----------
    dg = diagnose(df)
    if dg:
        print(f"\n{'-'*72}")
        print("  ตรวจสุขภาพผลลัพธ์ — อ่านก่อนเชื่อตัวเลข")
        print(f"{'-'*72}")
        print(f"    ปีข้อมูลค่ากลาง        {dg['ปีข้อมูลค่ากลาง']:>6.0f} ปี")
        print(f"    ความน่าเชื่อถือค่ากลาง {dg['ความน่าเชื่อถือค่ากลาง']:>6.0f} / 100")
        print(f"    ตัวที่น่าเชื่อถือ >=70  {dg['ความน่าเชื่อถือ >= 70']:>6,} ตัว")
        print(f"    คะแนนรวมสูงสุดที่ทำได้ {dg['คะแนนรวมสูงสุด']:>6.1f} / 100"
              "   (Strong Buy ต้อง 82)")
        print(f"    ส่วนลดค่ากลาง          {dg['ส่วนลดค่ากลาง (%)']:>6.0f}%")
        print(f"    ส่วนลดเกิน 100%        {dg['ส่วนลดเกิน 100%']:>6,} ตัว")
        print(f"    ส่วนลดเกิน 200%        {dg['ส่วนลดเกิน 200%']:>6,} ตัว")

        if dg["ส่วนลดเกิน 100%"] > len(ok) * 0.15:
            print("\n    ⚠️  ส่วนลดสูงผิดปกติเป็นจำนวนมาก")
            print("        ส่วนลด 100% = มูลค่าที่ประเมินได้เป็น 2 เท่าของราคา")
            print("        ส่วนลด 300% = เป็น 4 เท่า")
            print("        ตลาดทั้งตลาดคงไม่พลาดขนาดนั้นพร้อมกัน")
            print("        สาเหตุที่เป็นไปได้มากกว่าคือ **โมเดลเพี้ยนจากข้อมูลสั้น**")
            print("        หุ้นไทยมีงบแค่ 4 ปี ซึ่งไม่พอให้ DCF ต่อแนวโน้มได้แม่น")
            print("        -> ให้ใช้คอลัมน์ 'คะแนนรวม' และ 'ความน่าเชื่อถือ'")
            print("           ตัดสินแทน 'ส่วนลด' ซึ่งเชื่อถือได้น้อยกว่ามาก")

        if dg["คะแนนรวมสูงสุด"] and dg["คะแนนรวมสูงสุด"] < 82:
            gap = 82 - dg["คะแนนรวมสูงสุด"]
            print(f"\n    หมายเหตุ : ทั้งตลาดไม่มีตัวใดถึง 82 "
                  f"(สูงสุด {dg['คะแนนรวมสูงสุด']:.1f} ห่างอีก {gap:.1f})")
            print("        เพราะระบบดึงข้อสรุปเข้าหากลางเมื่อความน่าเชื่อถือต่ำ")
            print("        ซึ่งเป็นพฤติกรรมที่ตั้งใจ — ข้อมูล 4 ปีไม่ควรนำไปสู่")
            print("        คำแนะนำที่หนักแน่นระดับ Strong Buy")
            print("        **หุ้นสหรัฐมีโอกาสถึงมากกว่า** เพราะได้ 15 ปีจาก SEC EDGAR")
    if len(sb):
        print(f"\n  🏆 Strong Buy {len(sb)} ตัว")
        cols = ["ticker", "ชื่อบริษัท", "ราคา", "มูลค่าที่ประเมินได้",
                "ส่วนลด (%)", "คะแนนรวม", "ความน่าเชื่อถือ", "ปีข้อมูล"]
        print(sb[[c for c in cols if c in sb.columns]].to_string(index=False))
    else:
        print("\n  ไม่พบ Strong Buy ในรอบนี้")
        print("  **นี่เป็นเรื่องปกติ** — Strong Buy ต้องได้คะแนนรวม 82/100")
        print("  ซึ่งเกิดได้ก็ต่อเมื่อราคาถูก คุณภาพดี ความเสี่ยงต่ำ")
        print("  และข้อมูลน่าเชื่อถือ พร้อมกันทั้งสี่อย่าง")
        buy = ok[ok["คำแนะนำ"].isin(["Buy", "Accumulate"])]
        if len(buy):
            print(f"\n  ตัวที่ใกล้เคียงที่สุด — Buy/Accumulate {len(buy)} ตัว")
            print(buy.nlargest(10, "คะแนนรวม")[
                ["ticker", "ชื่อบริษัท", "คำแนะนำ", "คะแนนรวม",
                 "ส่วนลด (%)"]].to_string(index=False))

    print("\n  ผลถูกบันทึกไว้แล้ว — เปิดเว็บแล้วดูได้ทันที")
    print("  ถ้าอยากให้เว็บบนมือถือเห็นด้วย ให้ push ขึ้น GitHub :")
    print("    git add data/snapshots && git commit -m 'ผลวิเคราะห์ลึก' && git push\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
