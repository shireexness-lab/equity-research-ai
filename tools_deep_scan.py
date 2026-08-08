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


# สถิติของการรันรอบล่าสุด — ให้ผู้เรียก (เช่นปุ่มในโปรแกรม) อ่านไปแสดงต่อได้
# ใช้ตัวแปรระดับโมดูลแทนการเปลี่ยนค่าที่ run() คืน เพื่อไม่ให้โค้ดเดิมพัง
LAST_RUN: dict = {}


def _age_days(s) -> float:
    """อายุของวันที่บันทึก (วัน) — แปลงไม่ได้ถือว่าเก่ามาก จะได้ถูกดึงมาทำใหม่"""
    try:
        d = pd.to_datetime(s, errors="coerce")
        if pd.isna(d):
            return 1e9
        return (pd.Timestamp.now().normalize() - d.normalize()).days
    except Exception:
        return 1e9


# สัดส่วนของแต่ละรอบที่กันไว้ให้ "อัปเดตตัวที่เคยทำแล้ว"
#
# ทำไมต้องกันไว้ ไม่ทำตัวใหม่ให้ครบก่อน
# ---------------------------------------
# หุ้นสหรัฐ 10,398 ตัว · รอบละ 5 ชั่วโมงทำได้ราว 600 ตัว
# ถ้าทำตัวใหม่ให้ครบก่อนแล้วค่อยอัปเดต จะใช้เวลาราว 3 เดือนครึ่ง
# ระหว่างนั้นตัวที่ทำไว้ตั้งแต่เดือนแรกจะเก่ามาก และไม่มีรายงาน
# "สิ่งที่เปลี่ยนแปลง" ให้ดูเลยสักรอบ ซึ่งขัดกับที่ตั้งใจให้อัปเดตทุก 3 วัน
#
# 30% จึงเป็นการแลกที่สมเหตุสมผล — ขยายความครอบคลุมช้าลงราวหนึ่งในสาม
# แต่ได้เห็นความเคลื่อนไหวของหุ้นที่วิเคราะห์ไว้แล้วทุกรอบ
REFRESH_SHARE = 0.30


def _interleave(fresh, stale, share=REFRESH_SHARE):
    """
    สลับรายการสองชุดตามสัดส่วนที่กำหนด โดยให้ตัวใหม่ยังมาก่อนเป็นหลัก

    เช่น share = 0.3 จะได้รูปแบบ  ใหม่ ใหม่ เก่า ใหม่ ใหม่ ใหม่ เก่า ...
    ถ้าชุดใดหมดก่อน ที่เหลือของอีกชุดจะต่อท้ายทั้งหมด
    """
    if not stale:
        return list(fresh)
    if not fresh:
        return list(stale)

    out, fi, si = [], 0, 0
    while fi < len(fresh) or si < len(stale):
        # เติมของเก่าเมื่อสัดส่วนของเก่าในคิวยังต่ำกว่าเป้า
        want_stale = (si < len(stale) and
                      (fi >= len(fresh) or si < (len(out) + 1) * share))
        if want_stale:
            out.append(stale[si]); si += 1
        else:
            out.append(fresh[fi]); fi += 1
    return out


def build_queue(tickers, market: str, refresh_days=None,
                refresh_share=REFRESH_SHARE):
    """
    จัดคิวว่ารอบนี้ควรทำตัวไหนก่อน

    คิวประกอบด้วยสองชุด
    ---------------------
    1. ตัวที่ **ยังไม่เคยวิเคราะห์สำเร็จ** — เรียงตามลำดับที่ส่งเข้ามา
       (ผู้เรียกส่งมาแบบเรียงตามขนาด/คะแนนพรีสกรีนแล้ว ตัวเด่นจึงมาก่อน)
    2. ตัวที่เคยทำแล้วแต่ **เก่าเกิน refresh_days** — เรียงจากเก่าสุดไปใหม่สุด

    แล้วสลับสองชุดเข้าด้วยกันตามสัดส่วน refresh_share
    เพื่อให้ได้ทั้ง "ครอบคลุมกว้างขึ้น" และ "ข้อมูลที่มีอยู่ไม่เก่า" ไปพร้อมกัน
    """
    key = DEEP_KEY.format(market=market)
    done, _ = snapshot.info(key)

    have, n_fail_before = {}, 0
    if done is not None and not done.empty and "ticker" in done.columns:
        ok = done[done["ปัญหา"].eq("")] if "ปัญหา" in done.columns else done
        have = {r["ticker"]: r.to_dict() for _, r in ok.iterrows()}
        n_fail_before = len(done) - len(ok)

    tickers = list(dict.fromkeys(tickers))          # กันชื่อซ้ำ
    fresh = [t for t in tickers if t not in have]   # ยังไม่เคยทำ

    stale = []
    # ต้องเทียบกับ None ไม่ใช่ if refresh_days เฉย ๆ
    # เพราะ 0 แปลว่า "ถือว่าเก่าหมด ทำใหม่ทุกตัว" ซึ่งเป็นค่าที่ใช้ได้จริง
    # แต่ 0 ถูกมองว่าเป็นเท็จ ทำให้กลายเป็น "ไม่ต้องอัปเดตอะไรเลย" ซึ่งตรงข้ามกัน
    if refresh_days is not None:
        wanted = set(tickers)
        aged = [(t, _age_days(r.get("วิเคราะห์เมื่อ")))
                for t, r in have.items() if t in wanted]
        stale = [t for t, a in sorted(aged, key=lambda x: -x[1])
                 if a >= refresh_days]

    return {
        "have": have,
        "todo": _interleave(fresh, stale, refresh_share),
        "ยังไม่เคยทำ": len(fresh),
        "ถึงรอบอัปเดต": len(stale),
        "เคยพลาด": n_fail_before,
        "ทั้งหมด": len(tickers),
        "ทำแล้ว": len(have),
    }


def run(tickers, market: str, rf=None, save_every=10,
        hours=None, refresh_days=None, progress=None, quiet=False):
    """
    วิเคราะห์ทีละตัว บันทึกผลสะสม ทำงานต่อจากที่ค้างได้

    ไม่ใช้หลายเส้นพร้อมกัน เพราะการวิเคราะห์ลึกดึงข้อมูล 4-5 คำขอต่อหุ้น
    ถ้ายิงพร้อมกันจะโดน Yahoo บล็อกแน่นอน ช้าแต่ได้ครบดีกว่าเร็วแต่พัง

    พารามิเตอร์ที่เพิ่มมาเพื่อรองรับตลาดใหญ่
    -------------------------------------------
    hours         งบเวลาต่อรอบ (ชั่วโมง) หมดเวลาแล้วหยุดอย่างเรียบร้อย
                  บันทึกผลที่ได้ แล้วรอบหน้าทำต่อจากจุดเดิม
                  จำเป็นสำหรับหุ้นสหรัฐ 10,398 ตัว ซึ่งรอบเดียวทำไม่หมด
    refresh_days  ตัวที่วิเคราะห์ไว้เกินกี่วันให้ถือว่าเก่า แล้วดึงมาทำใหม่
    progress      ฟังก์ชัน progress(i, total, ticker, mark, eta_sec)
                  ใช้ตอนเรียกจากหน้าเว็บ เพื่อวาดแถบความคืบหน้า
    quiet         ไม่พิมพ์อะไรลง Terminal (ใช้ตอนเรียกจากหน้าเว็บ)
    """
    global LAST_RUN
    key = DEEP_KEY.format(market=market)

    q = build_queue(tickers, market, refresh_days=refresh_days)
    have, todo = q["have"], q["todo"]

    def say(*a):
        if not quiet:
            print(*a)

    # ---- สรุปให้ชัดว่าเลขแต่ละตัวมาจากไหน ----
    # เดิมแสดงแค่ "ต้องวิเคราะห์อีก N ตัว" ซึ่งอ่านแล้วนึกว่าทั้งหมดมีแค่ N
    # ทั้งที่ N คือส่วนที่เหลือหลังหักตัวที่เคยทำไว้แล้ว
    say(f"\n  {'รายชื่อทั้งหมด':<28}{q['ทั้งหมด']:>7,} ตัว")
    say(f"  {'เคยวิเคราะห์สำเร็จแล้ว':<28}{q['ทำแล้ว']:>7,} ตัว")
    if q["เคยพลาด"]:
        say(f"  {'เคยพลาด จะลองใหม่':<28}{q['เคยพลาด']:>7,} ตัว")
    say(f"  {'ยังไม่เคยทำ — ทำก่อน':<28}{q['ยังไม่เคยทำ']:>7,} ตัว")
    if refresh_days is not None:
        say(f"  {'เก่าเกิน ' + str(refresh_days) + ' วัน — ทำต่อ':<28}"
            f"{q['ถึงรอบอัปเดต']:>7,} ตัว")
    say(f"  {'คิวรอบนี้':<28}{len(todo):>7,} ตัว")

    if not todo:
        say("\n  ทำครบและยังไม่ถึงรอบอัปเดต — ไม่มีอะไรต้องรัน")
        LAST_RUN = {**q, "ทำไปรอบนี้": 0, "สำเร็จ": 0, "พลาด": 0,
                    "ทำครบแล้ว": True, "หมดเวลา": False, "วินาทีที่ใช้": 0}
        return pd.DataFrame(list(have.values()))

    total, t0 = len(todo), time.time()
    budget = hours * 3600 if hours else None
    if budget:
        say(f"\n  งบเวลารอบนี้ {hours:g} ชั่วโมง — "
            f"หมดเวลาแล้วจะหยุดและบันทึก รอบหน้าทำต่อ")
    say(f"  คาดว่าใช้เวลาราว {total * 30 / 3600:.1f} ชั่วโมง"
        f"{' ถ้าทำจนครบ' if budget else ''}\n")

    rows = dict(have)          # ใช้ dict เพื่อให้ตัวที่ทำใหม่ทับตัวเก่าได้
    n_ok = n_bad = 0
    stopped_by_time = False

    for i, tk in enumerate(todo, 1):
        r = analyze_one(tk, rf=rf)
        rows[tk] = r
        if r["ปัญหา"]:
            n_bad += 1
        else:
            n_ok += 1

        el = time.time() - t0
        eta = el / i * (total - i)
        mark = ("✓ " + str(r.get("คำแนะนำ", ""))) if not r["ปัญหา"] else "✗"
        say(f"  [{i:>4}/{total}] {tk:<14}{mark:<14}"
            f"เหลืออีก ~{eta/60:>5.0f} นาที")
        if progress:
            try:
                progress(i, total, tk, mark, eta)
            except Exception:
                pass

        out_of_time = budget is not None and el >= budget
        if i % save_every == 0 or i == total or out_of_time:
            df = pd.DataFrame(list(rows.values()))
            for c in KEEP:
                if c not in df.columns:
                    df[c] = None
            snapshot.save(key, df[KEEP], to_repo=True,
                          extra={"ตลาด": market, "จำนวน": len(df)})

        if out_of_time:
            stopped_by_time = True
            say(f"\n  หมดงบเวลา {hours:g} ชั่วโมง — หยุดที่ตัวที่ {i:,} "
                f"จาก {total:,}")
            say(f"  บันทึกแล้ว เหลืออีก {total - i:,} ตัว รอบหน้าทำต่อได้เลย")
            break

    LAST_RUN = {**q, "ทำไปรอบนี้": n_ok + n_bad, "สำเร็จ": n_ok, "พลาด": n_bad,
                "ทำครบแล้ว": not stopped_by_time, "หมดเวลา": stopped_by_time,
                "วินาทีที่ใช้": time.time() - t0}

    df = pd.DataFrame(list(rows.values()))
    for c in KEEP:
        if c not in df.columns:
            df[c] = None
    return df[KEEP]


def load_results(market: str):
    """อ่านผลที่บันทึกไว้ — ใช้จากหน้าเว็บด้วย"""
    return snapshot.info(DEEP_KEY.format(market=market))


# ---------------------------------------------------------------------------
# รายงาน "สิ่งที่เปลี่ยนแปลง"
#
# ทำไมต้องมี : เมื่ออัปเดตทุก 3 วัน ตารางผลจะมีหลายพันแถว
# การไล่ดูเองว่าอะไรเปลี่ยนเป็นไปไม่ได้ ระบบจึงต้องชี้ให้ดูเฉพาะจุดที่ขยับ
#
# สิ่งที่ถือว่า "เปลี่ยน" มี 3 แบบ เรียงตามความสำคัญ
#   1. คำแนะนำข้ามระดับ  เช่น Hold -> Buy  ← สำคัญที่สุด ต้องดูทันที
#   2. ส่วนลดขยับแรง     ราคาถูก/แพงขึ้นชัดเจนแม้คำแนะนำยังเท่าเดิม
#   3. หุ้นเข้าใหม่       เพิ่งวิเคราะห์ได้เป็นครั้งแรก
# ---------------------------------------------------------------------------

CHANGE_KEY = "deep-{market}-changes"

# ส่วนลดต้องขยับกี่จุดถึงจะเรียกว่า "เปลี่ยนอย่างมีนัย"
# 10 จุดเปอร์เซ็นต์ ≈ ราคาขยับ 10% เทียบมูลค่า ซึ่งมากพอที่จะเปลี่ยนการตัดสินใจ
# ต่ำกว่านี้คือความผันผวนปกติของราคารายวัน ไม่ควรรบกวน
DISCOUNT_MOVE = 10.0


def _rank(level) -> int:
    """แปลงคำแนะนำเป็นตัวเลข เพื่อบอกว่าขยับขึ้นหรือลง (0 = Strong Buy)"""
    try:
        return ORDER.index(str(level))
    except ValueError:
        return 99


def diff_results(before, after) -> pd.DataFrame:
    """
    เทียบผลสองรอบ คืนเฉพาะแถวที่เปลี่ยน เรียงตามความสำคัญ

    รับ DataFrame ก่อน/หลัง (ตัวไหนเป็น None ถือว่าไม่มีข้อมูลรอบก่อน)
    """
    cols = ["ticker", "ชื่อบริษัท", "การเปลี่ยนแปลง", "คำแนะนำเดิม",
            "คำแนะนำใหม่", "ส่วนลดเดิม (%)", "ส่วนลดใหม่ (%)", "ส่วนลดขยับ",
            "ราคา", "คะแนนเดิม", "คะแนนใหม่", "ความน่าเชื่อถือ"]
    if after is None or after.empty:
        return pd.DataFrame(columns=cols)

    def _ok(df):
        if df is None or df.empty or "ticker" not in df.columns:
            return {}
        d = df[df["ปัญหา"].eq("")] if "ปัญหา" in df.columns else df
        return {r["ticker"]: r.to_dict() for _, r in d.iterrows()}

    old, new = _ok(before), _ok(after)
    out = []

    for tk, n in new.items():
        o = old.get(tk)
        lv_new = n.get("คำแนะนำ")
        d_new = _num(n.get("ส่วนลด (%)"))

        if o is None:
            out.append({
                "ticker": tk, "ชื่อบริษัท": n.get("ชื่อบริษัท"),
                "การเปลี่ยนแปลง": "🆕 วิเคราะห์ได้ครั้งแรก",
                "คำแนะนำเดิม": "-", "คำแนะนำใหม่": lv_new,
                "ส่วนลดเดิม (%)": None, "ส่วนลดใหม่ (%)": d_new,
                "ส่วนลดขยับ": None, "ราคา": _num(n.get("ราคา")),
                "คะแนนเดิม": None, "คะแนนใหม่": _num(n.get("คะแนนรวม")),
                "ความน่าเชื่อถือ": n.get("ความน่าเชื่อถือ"),
                "_pri": 3, "_mag": 0.0})
            continue

        lv_old = o.get("คำแนะนำ")
        d_old = _num(o.get("ส่วนลด (%)"))
        move = (d_new - d_old) if (d_new is not None and d_old is not None) else None

        if lv_new != lv_old:
            # ค่า rank น้อย = ดีขึ้น (Strong Buy อยู่หัวแถว)
            up = _rank(lv_new) < _rank(lv_old)
            label = ("⬆️ ดีขึ้น " if up else "⬇️ แย่ลง ") + f"{lv_old} → {lv_new}"
            pri, mag = 1, abs(_rank(lv_new) - _rank(lv_old))
        elif move is not None and abs(move) >= DISCOUNT_MOVE:
            label = ("💰 ถูกลง" if move > 0 else "💸 แพงขึ้น") + \
                    f" {abs(move):.0f} จุด"
            pri, mag = 2, abs(move)
        else:
            continue

        out.append({
            "ticker": tk, "ชื่อบริษัท": n.get("ชื่อบริษัท"),
            "การเปลี่ยนแปลง": label,
            "คำแนะนำเดิม": lv_old, "คำแนะนำใหม่": lv_new,
            "ส่วนลดเดิม (%)": d_old, "ส่วนลดใหม่ (%)": d_new,
            "ส่วนลดขยับ": move, "ราคา": _num(n.get("ราคา")),
            "คะแนนเดิม": _num(o.get("คะแนนรวม")),
            "คะแนนใหม่": _num(n.get("คะแนนรวม")),
            "ความน่าเชื่อถือ": n.get("ความน่าเชื่อถือ"),
            "_pri": pri, "_mag": mag})

    if not out:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(out).sort_values(["_pri", "_mag"], ascending=[True, False])
    return df.drop(columns=["_pri", "_mag"])[cols].reset_index(drop=True)


def _num(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def save_changes(market: str, changes: pd.DataFrame) -> None:
    """เก็บรายงานการเปลี่ยนแปลงไว้ให้หน้าเว็บอ่าน"""
    if changes is None or changes.empty:
        return
    snapshot.save(CHANGE_KEY.format(market=market), changes, to_repo=True,
                  extra={"ตลาด": market, "จำนวนที่เปลี่ยน": len(changes)})


def load_changes(market: str):
    """อ่านรายงานการเปลี่ยนแปลงรอบล่าสุด"""
    return snapshot.info(CHANGE_KEY.format(market=market))


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
    p.add_argument("--hours", type=float, default=None,
                   help="งบเวลาต่อรอบ (ชั่วโมง) หมดเวลาแล้วหยุดและบันทึก "
                        "รอบหน้าทำต่อจากจุดเดิม — จำเป็นสำหรับหุ้นสหรัฐหมื่นตัว")
    p.add_argument("--refresh-days", type=int, default=None,
                   help="ตัวที่วิเคราะห์ไว้เกินกี่วันให้ถือว่าเก่า แล้วทำใหม่ "
                        "(ใส่ 3 = อัปเดตทุก 3 วัน)")
    p.add_argument("--show", action="store_true", help="ดูผลที่ทำไว้แล้ว")
    p.add_argument("--changes", action="store_true",
                   help="ดูรายการที่เปลี่ยนแปลงจากรอบก่อน")
    p.add_argument("--reset", action="store_true",
                   help="เริ่มนับหนึ่งใหม่ (ย้ายผลเก่าไปเป็นไฟล์สำรอง "
                        "ไม่ได้ลบทิ้ง และต้องพิมพ์ยืนยันก่อน) — "
                        "ปกติไม่ต้องใช้ เพราะระบบทำต่อจากเดิมให้อยู่แล้ว")
    a = p.parse_args()

    market = "us" if a.us else "thai"

    # ---------- ดูรายการที่เปลี่ยนแปลง ----------
    if a.changes:
        for mk in ("thai", "us"):
            ch, cmeta = load_changes(mk)
            print(f"\n{'='*72}\n  ตลาด {mk} — สิ่งที่เปลี่ยนรอบล่าสุด")
            if ch is None or ch.empty:
                print("  ยังไม่มีบันทึกการเปลี่ยนแปลง")
                continue
            print(f"  บันทึกเมื่อ {cmeta.get('บันทึกเมื่อ','-')[:16]} "
                  f"· {len(ch):,} ตัว\n{'='*72}")
            cols = ["ticker", "ชื่อบริษัท", "การเปลี่ยนแปลง",
                    "ส่วนลดใหม่ (%)", "คะแนนใหม่", "ความน่าเชื่อถือ"]
            print(ch.head(40)[[c for c in cols if c in ch.columns]]
                  .to_string(index=False))
        print()
        return 0

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
        if a.all:
            # หุ้นสหรัฐทั้งตลาด 10,398 ตัว
            #
            # เรียงตามขนาดบริษัท (NVDA, AAPL, GOOGL, ... มาก่อน) โดยตั้งใจ
            # ไม่ได้เรียงตามตัวอักษร เพราะรอบเดียวทำไม่หมดแน่นอน
            # ถ้าเรียง A-Z ตัวแรก ๆ ที่ได้คิวจะเป็นกองทุน ETF และ warrant
            # ซึ่งวิเคราะห์งบไม่ได้ เสียเวลาเปล่า
            # เรียงตามขนาดทำให้ทุกรอบได้ตัวที่มีข้อมูลครบและมีคนสนใจจริงก่อน
            from tickers import us_tickers
            universe = list(us_tickers().keys())
        else:
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

    # เก็บภาพ "ก่อนรัน" ไว้เทียบ เพื่อบอกได้ว่ารอบนี้อะไรเปลี่ยนบ้าง
    before, _ = load_results(market)

    t0 = time.time()
    df = run(universe, market, rf=a.rf, hours=a.hours,
             refresh_days=a.refresh_days)
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

    # ---------- สิ่งที่เปลี่ยนไปจากรอบก่อน ----------
    ch = diff_results(before, df)
    save_changes(market, ch)
    print(f"\n{'-'*72}")
    if ch.empty:
        print("  ไม่มีอะไรเปลี่ยนจากรอบก่อน")
    else:
        lv = ch[ch["การเปลี่ยนแปลง"].str.startswith(("⬆️", "⬇️"))]
        pr = ch[ch["การเปลี่ยนแปลง"].str.startswith(("💰", "💸"))]
        nw = ch[ch["การเปลี่ยนแปลง"].str.startswith("🆕")]
        print(f"  สิ่งที่เปลี่ยนจากรอบก่อน — {len(ch):,} ตัว")
        print(f"    คำแนะนำเปลี่ยนระดับ {len(lv):>5,} ตัว   ← ดูก่อน")
        print(f"    ส่วนลดขยับแรง       {len(pr):>5,} ตัว")
        print(f"    วิเคราะห์ได้ครั้งแรก {len(nw):>5,} ตัว")
        if len(lv):
            print(f"\n{'-'*72}")
            cols = ["ticker", "ชื่อบริษัท", "การเปลี่ยนแปลง",
                    "ส่วนลดใหม่ (%)", "คะแนนใหม่", "ความน่าเชื่อถือ"]
            print(lv.head(25)[cols].to_string(index=False))
    print(f"{'-'*72}")

    if LAST_RUN.get("หมดเวลา"):
        left = LAST_RUN["ทั้งหมด"] - LAST_RUN["ทำแล้ว"] - LAST_RUN["ทำไปรอบนี้"]
        print(f"\n  ⏱  รอบนี้หยุดเพราะหมดงบเวลา ไม่ใช่เพราะทำครบ")
        print(f"     เหลืออีกราว {max(left, 0):,} ตัว — สั่งคำสั่งเดิมซ้ำเพื่อทำต่อ")

    print("\n  ผลถูกบันทึกไว้แล้ว — เปิดเว็บแล้วดูได้ทันที")
    print("  ถ้าอยากให้เว็บบนมือถือเห็นด้วย ให้ push ขึ้น GitHub :")
    print("    git add data/snapshots && git commit -m 'ผลวิเคราะห์ลึก' && git push\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
