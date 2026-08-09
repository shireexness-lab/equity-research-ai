"""
archive.py — คลังงบการเงินที่สะสมเพิ่มขึ้นเรื่อย ๆ
=====================================================

ปัญหาที่แก้
-----------
yfinance ให้งบย้อนหลังแค่ **4 ปีล่าสุด** เท่านั้น ปีที่ 5 ขึ้นไปหายไป
ซึ่งเป็นสาเหตุหลักที่หุ้นไทยได้คะแนนความน่าเชื่อถือแค่ 40/100
และทำให้ DCF ต่อแนวโน้มจากข้อมูลสั้นจนได้ส่วนลด 300%

แนวคิด — เก็บสะสมเอง แล้วเวลาทำงานให้เรา
------------------------------------------
Yahoo ให้ "4 ปีล่าสุด" เสมอ แต่ 4 ปีนั้นเลื่อนไปข้างหน้าทุกปี

    ดึงปี 2026  ได้ 2022 2023 2024 2025
    ดึงปี 2027  ได้ 2023 2024 2025 2026     <- 2022 หายจาก Yahoo แล้ว
    ดึงปี 2028  ได้ 2024 2025 2026 2027

ถ้าเก็บทุกครั้งที่ดึงไว้ในคลังของเราเอง แล้วเอามารวมกัน

    คลังปี 2028 = 2022 2023 2024 2025 2026 2027   -> **6 ปี**

ยิ่งใช้ระบบนานยิ่งมีข้อมูลลึกขึ้น โดยไม่ต้องจ่ายเงินซื้อฐานข้อมูล
ปีที่ 2031 จะมี 9 ปี ซึ่งพอสำหรับ DCF และครอบคลุมวัฏจักรธุรกิจหนึ่งรอบ

**เริ่มเก็บวันนี้ดีที่สุด** เพราะเวลาเป็นวัตถุดิบที่ซื้อย้อนหลังไม่ได้

โครงสร้างการเก็บ — แบ่งไฟล์ตาม "ปีงบ"
--------------------------------------
    data/archive/thai/2024.parquet
    data/archive/thai/2025.parquet
    data/archive/us/2025.parquet

ทำไมแบ่งตามปีงบ ไม่ใช่ตามตัวอักษรของ ticker

    งบของปี 2024 เมื่อปิดปีแล้วจะ **ไม่เปลี่ยนอีก** (ยกเว้นการปรับปรุงย้อนหลัง)
    ไฟล์ปีเก่าจึงถูกเขียนครั้งเดียวแล้วนิ่งตลอดไป
    git จึงไม่ต้องเก็บไฟล์เดิมซ้ำทุกครั้งที่อัปเดต — ขนาด repo โตแบบมีขอบเขต

    ถ้าแบ่งตามตัวอักษร ทุกครั้งที่บริษัทใดบริษัทหนึ่งประกาศงบ
    ไฟล์ทั้งก้อนจะถูกเขียนใหม่ และ git จะเก็บสำเนาเดิมไว้ทุกเวอร์ชัน

ขนาดจริงที่วัดได้ : หุ้นไทย 865 ตัว × 4 ปี = 3.3 MB
ประมาณการเมื่อครบสองตลาด × 20 ปี ราว 210 MB หรือ **ราว 11 MB ต่อปี**

รูปแบบข้อมูล — long format
---------------------------
    ticker · งบ · งวด · บรรทัด · ค่า · บันทึกเมื่อ

เก็บแบบยาว (แถวละหนึ่งค่า) ไม่ใช่แบบตาราง เพราะ

    1. บริษัทแต่ละแห่งมีบรรทัดในงบไม่เหมือนกัน ตารางกว้างจะเต็มไปด้วยช่องว่าง
    2. เพิ่มบรรทัดใหม่ที่ไม่เคยมีได้โดยไม่ต้องแก้โครงสร้างไฟล์เดิม
    3. รองรับจำนวนหุ้นที่เพิ่มขึ้นได้เอง — หุ้นใหม่คือแถวใหม่ ไม่ใช่คอลัมน์ใหม่

การปรับปรุงงบย้อนหลัง (restatement)
------------------------------------
บริษัทแก้ตัวเลขปีเก่าได้ เช่น เปลี่ยนวิธีบัญชีหรือพบข้อผิดพลาด
ระบบจะ **ใช้ค่าใหม่** แต่บันทึกไว้ว่ามีการเปลี่ยน (ดู `restatements()`)
เพราะการที่บริษัทแก้ตัวเลขย้อนหลังบ่อยเป็นสัญญาณคุณภาพงบที่ควรรู้

วิธีใช้จาก Terminal
--------------------
    python3 archive.py --สร้างจากแคช        สร้างคลังจากไฟล์ที่ดึงไว้แล้ว
    python3 archive.py --สถานะ              ดูว่ามีกี่ตัว กี่ปี ขนาดเท่าไร
    python3 archive.py --ดู PTT.BK          ดูว่าหุ้นตัวนี้มีข้อมูลกี่ปี
    python3 archive.py --การแก้ไขงบ         ดูบริษัทที่แก้ตัวเลขย้อนหลัง
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
ARCHIVE_DIR = BASE_DIR / "data" / "archive"

# ชื่อคอลัมน์ในคลัง
COLS = ["ticker", "งบ", "งวด", "บรรทัด", "ค่า", "บันทึกเมื่อ"]

KINDS = ("income", "balance", "cashflow")

# ค่าที่ต่างจากเดิมเกินกี่ส่วน ถึงจะนับว่า "บริษัทแก้งบย้อนหลัง"
#
# ใช้ 0.5% เพราะการปัดเศษและการแปลงหน่วยทำให้ค่าขยับเล็กน้อยได้เป็นปกติ
# ถ้าตั้งไว้ 0 จะขึ้นเตือนทุกแถวจนไม่มีประโยชน์
RESTATE_TOL = 0.005


def _year_of(period: str) -> str:
    """ปีงบจากวันที่สิ้นงวด — ใช้เป็นชื่อไฟล์"""
    s = str(period)[:4]
    return s if s.isdigit() else "ไม่ทราบปี"


def _dir(market: str) -> Path:
    d = ARCHIVE_DIR / market
    d.mkdir(parents=True, exist_ok=True)
    return d


def market_of(ticker: str) -> str:
    """หุ้นไทยลงท้ายด้วย .BK — ที่เหลือถือเป็นสหรัฐ/สากล"""
    return "thai" if str(ticker).upper().endswith(".BK") else "us"


# ---------------------------------------------------------------------------
# 1) แปลงงบเป็นรูปแบบยาว
# ---------------------------------------------------------------------------

def to_long(ticker: str, data: dict) -> pd.DataFrame:
    """แปลงงบ 3 ตัวจาก data_layer ให้เป็นตารางยาวพร้อมเก็บลงคลัง"""
    stamp = datetime.now().strftime("%Y-%m-%d")
    out = []
    for kind in KINDS:
        df = data.get(kind)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            continue
        for period in df.columns:
            col = pd.to_numeric(df[period], errors="coerce").dropna()
            for line, val in col.items():
                if not np.isfinite(val):
                    continue
                out.append((str(ticker).upper(), kind, str(period)[:10],
                            str(line), float(val), stamp))
    return pd.DataFrame(out, columns=COLS)


# ---------------------------------------------------------------------------
# 1.5) ชั้นอ่าน-เขียนที่กันข้อมูลหาย
#
# ความเสี่ยงที่ต้องกันมี 3 อย่าง เรียงตามโอกาสเกิดจริง
#
#   1. เครื่องดับ / กด Ctrl-C ระหว่างเขียนไฟล์
#      -> ไฟล์เหลือครึ่งเดียว อ่านไม่ออก ข้อมูลทั้งปีหายทันที
#      แก้ด้วย : เขียนลงไฟล์ชั่วคราวก่อน เสร็จแล้วค่อยสลับชื่อ
#                การสลับชื่อเป็นการกระทำเดียวที่ระบบไฟล์รับประกันว่าไม่ขาดครึ่ง
#
#   2. บั๊กในโค้ดทำให้แถวหายโดยไม่มีใครรู้
#      -> แก้ด้วย : นับแถวก่อนและหลังทุกครั้ง ถ้าลดลงให้ยกเลิกการเขียน
#
#   3. ไฟล์เสียหายภายหลังโดยไม่รู้ตัว
#      -> แก้ด้วย : เก็บบัญชีคุม (จำนวนแถว + ลายนิ้วมือ) ไว้ตรวจย้อนหลังได้
# ---------------------------------------------------------------------------

import hashlib
import os

LEDGER = "บัญชีคุมคลัง.json"
JOURNAL = "สมุดบันทึกการเขียน.csv"


def _read_shard(f: Path) -> pd.DataFrame:
    """อ่านไฟล์ปีหนึ่ง — ถ้าไฟล์เสียให้แจ้งชัดเจน ไม่ใช่คืนตารางว่างเงียบ ๆ"""
    if not f.exists():
        return pd.DataFrame(columns=COLS)
    try:
        return pd.read_parquet(f)
    except Exception as e:
        raise RuntimeError(
            f"ไฟล์คลังเสียหาย : {f}\n"
            f"  ({type(e).__name__}: {e})\n"
            f"  หยุดทำงานเพื่อไม่ให้เขียนทับข้อมูลที่ยังกู้ได้\n"
            f"  ให้กู้จาก git ด้วย :  git checkout -- {f}") from e


def _digest(df: pd.DataFrame) -> str:
    """ลายนิ้วมือของข้อมูล — ใช้ตรวจว่าถูกแก้โดยไม่ผ่านระบบไหม"""
    s = df.sort_values(COLS[:4]).to_csv(index=False).encode("utf-8")
    return hashlib.sha256(s).hexdigest()[:16]


def _write_shard(f: Path, df: pd.DataFrame, before: int = 0):
    """
    เขียนไฟล์ปีหนึ่งแบบปลอดภัย

    before = จำนวนแถวเดิม ใช้ตรวจว่าไม่มีแถวหายไป
    """
    if len(df) < before:
        raise RuntimeError(
            f"ยกเลิกการเขียน {f.name} — แถวจะลดจาก {before:,} เหลือ {len(df):,}\n"
            f"  คลังนี้ห้ามข้อมูลหาย ถ้าเกิดกรณีนี้แปลว่ามีบั๊ก")

    tmp = f.with_suffix(f.suffix + ".กำลังเขียน")
    df.to_parquet(tmp, compression="zstd", index=False)
    # os.replace เป็นการสลับชื่อแบบ atomic
    # ถ้าไฟดับกลางคัน จะได้ไฟล์เดิมทั้งไฟล์ หรือไฟล์ใหม่ทั้งไฟล์ ไม่มีครึ่ง ๆ
    os.replace(tmp, f)

    _update_ledger(f, df)
    _journal(f, before, len(df))


def _ledger_path(market_dir: Path) -> Path:
    return market_dir / LEDGER


def _update_ledger(f: Path, df: pd.DataFrame):
    """บันทึกจำนวนแถวและลายนิ้วมือไว้ตรวจสอบภายหลัง"""
    import json
    p = _ledger_path(f.parent)
    book = {}
    if p.exists():
        try:
            book = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            book = {}
    book[f.name] = {
        "แถว": int(len(df)),
        "หุ้น": int(df["ticker"].nunique()) if len(df) else 0,
        "ลายนิ้วมือ": _digest(df),
        "อัปเดตเมื่อ": datetime.now().isoformat(timespec="seconds"),
    }
    p.write_text(json.dumps(book, ensure_ascii=False, indent=1),
                 encoding="utf-8")


def _journal(f: Path, before: int, after: int):
    """สมุดบันทึกว่าเขียนอะไรไปบ้าง — ไล่ย้อนได้ว่าข้อมูลเปลี่ยนตอนไหน"""
    p = f.parent / JOURNAL
    new = not p.exists()
    with open(p, "a", encoding="utf-8") as fh:
        if new:
            fh.write("เวลา,ไฟล์,แถวก่อน,แถวหลัง,เพิ่ม\n")
        fh.write(f"{datetime.now().isoformat(timespec='seconds')},"
                 f"{f.name},{before},{after},{after - before}\n")


def verify(market: str = None) -> pd.DataFrame:
    """
    ตรวจว่าคลังยังครบถ้วนตรงกับบัญชีคุมไหม

    ใช้ตอบคำถาม "ข้อมูลหายไปไหมโดยที่เราไม่รู้ตัว"
    """
    import json
    mks = [market] if market else ["thai", "us"]
    rows = []
    for m in mks:
        d = ARCHIVE_DIR / m
        if not d.exists():
            continue
        p = _ledger_path(d)
        book = {}
        if p.exists():
            try:
                book = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass

        for f in sorted(d.glob("*.parquet")):
            if "การแก้ไข" in f.name:
                continue
            rec = book.get(f.name)
            try:
                df = pd.read_parquet(f)
                ok_read = True
            except Exception:
                df, ok_read = pd.DataFrame(columns=COLS), False

            if not ok_read:
                status = "❌ ไฟล์เสียหาย อ่านไม่ได้"
            elif rec is None:
                status = "⚠️ ไม่มีในบัญชีคุม (เพิ่งสร้างหรือแก้นอกระบบ)"
            elif len(df) < rec["แถว"]:
                status = f"❌ แถวหาย {rec['แถว'] - len(df):,} แถว"
            elif _digest(df) != rec["ลายนิ้วมือ"]:
                status = "⚠️ เนื้อหาต่างจากบัญชีคุม"
            else:
                status = "✅ ครบถ้วน"

            rows.append({"ตลาด": m, "ไฟล์": f.name,
                         "แถวจริง": len(df),
                         "แถวตามบัญชี": rec["แถว"] if rec else None,
                         "สถานะ": status})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2) เขียนลงคลัง — รวมของใหม่เข้าของเก่า ไม่ลบ
# ---------------------------------------------------------------------------

# จำนวนปีที่ยังยอมให้แก้ไขได้หลังจบปีงบ
#
# ทำไมไม่ล็อกทันทีที่ปีจบ
# ------------------------
# บริษัทประกาศงบปี 2025 ในช่วงต้นปี 2026 และช่วงแรกตัวเลขที่ Yahoo ให้
# มักไม่ครบ (บางบรรทัดยังว่าง) ถ้าล็อกทันทีที่ 1 ม.ค. 2026
# ค่าที่ไม่ครบจะถูกตรึงไว้ตลอดกาล ซึ่งแย่กว่าปัญหาที่พยายามแก้
#
# ให้เวลา 1 ปีเต็มเพื่อให้ตัวเลขนิ่ง แล้วค่อยล็อกถาวร
# ในปี 2026 : ปี 2024 และก่อนหน้า = ล็อกแล้ว · ปี 2025 = ยังแก้ได้ · 2026 = เปิด
LOCK_AFTER_YEARS = 1


def is_locked(period_or_year, today=None) -> bool:
    """
    งวดนี้ถูกล็อกถาวรแล้วหรือยัง

    ล็อกแล้ว = ห้ามแก้ ห้ามทับ ห้ามลบ ไม่ว่าข้อมูลใหม่จะบอกอะไรก็ตาม
    """
    y = _year_of(period_or_year)
    if not y.isdigit():
        return False
    now = (today or datetime.now()).year
    return int(y) < now - LOCK_AFTER_YEARS


def put(ticker: str, data: dict, market: str = None) -> dict:
    """
    เก็บงบของหุ้นตัวหนึ่งลงคลัง

    กฎเหล็กของคลังนี้
    ------------------
    1. **ไม่ลบ** ค่าที่เคยเก็บไว้ ไม่ว่ากรณีใด
    2. **ไม่แก้** ค่าของงวดที่ถูกล็อกแล้ว (ปีที่ผ่านไปเกิน 1 ปี)
    3. ค่าที่บริษัทแก้ย้อนหลัง เก็บแยกไว้เป็นประวัติ ไม่ทับของเดิม

    ทำไมยึด "ค่าแรกที่บันทึก" เป็นค่าจริง
    --------------------------------------
    เพราะเป็นตัวเลขที่นักลงทุนเห็นจริงตอนนั้น
    ถ้าเอาตัวเลขที่แก้ภายหลังมาแทน จะเกิดสิ่งที่เรียกว่า look-ahead bias
    คือย้อนกลับไปทดสอบกลยุทธ์ด้วยข้อมูลที่ตอนนั้นยังไม่มีใครรู้
    ผลทดสอบจะดูดีเกินจริง แล้วพอใช้กับของจริงจะไม่ได้ผลตามนั้น

    ฐานข้อมูลระดับสถาบันเรียกวิธีนี้ว่า point-in-time database
    และเป็นมาตรฐานสำหรับการทดสอบย้อนหลังที่เชื่อถือได้

    คืน dict สรุปว่าเพิ่มกี่ค่า ปฏิเสธการแก้กี่ค่า และพบการแก้งบย้อนหลังไหม
    """
    market = market or market_of(ticker)
    fresh = to_long(ticker, data)
    if fresh.empty:
        return {"เพิ่ม": 0, "ปฏิเสธการแก้": 0, "แก้งบย้อนหลัง": 0, "ปีในคลัง": 0}

    added = blocked = restated = updated = 0
    restate_rows = []
    key = ["ticker", "งบ", "งวด", "บรรทัด"]

    for year, part in fresh.groupby(fresh["งวด"].map(_year_of)):
        f = _dir(market) / f"{year}.parquet"
        old = _read_shard(f)

        # แยกเฉพาะหุ้นตัวนี้ออกมาเทียบ ตัวอื่นในไฟล์ไม่ต้องแตะ
        mine = old[old["ticker"] == str(ticker).upper()] if len(old) \
            else pd.DataFrame(columns=COLS)
        others = old[old["ticker"] != str(ticker).upper()] if len(old) \
            else pd.DataFrame(columns=COLS)

        locked = is_locked(year)

        if mine.empty:
            merged = part
            added += len(part)
        else:
            cmp_ = mine.merge(part, on=key, how="outer",
                              suffixes=("_เดิม", "_ใหม่"), indicator=True)

            added += int(cmp_["_merge"].eq("right_only").sum())

            # ---- ตรวจว่าค่าเปลี่ยนไปจากที่เคยเก็บไหม ----
            both = cmp_["_merge"].eq("both")
            a = pd.to_numeric(cmp_.loc[both, "ค่า_เดิม"], errors="coerce")
            b = pd.to_numeric(cmp_.loc[both, "ค่า_ใหม่"], errors="coerce")
            denom = a.abs().where(a.abs() > 0, 1.0)
            diff = ((b - a).abs() / denom) > RESTATE_TOL

            if diff.any():
                restated += int(diff.sum())
                rr = cmp_.loc[both][diff.values]
                for _, r in rr.iterrows():
                    restate_rows.append({
                        "ticker": r["ticker"], "งบ": r["งบ"], "งวด": r["งวด"],
                        "บรรทัด": r["บรรทัด"], "ค่าเดิม": r["ค่า_เดิม"],
                        "ค่าใหม่": r["ค่า_ใหม่"],
                        "งวดถูกล็อก": bool(locked),
                        "พบเมื่อ": datetime.now().strftime("%Y-%m-%d")})

            # ---- ตัดสินว่าจะใช้ค่าไหน ----
            #
            # งวดที่ล็อกแล้ว  -> ใช้ค่าเดิมเสมอ ค่าใหม่แค่บันทึกไว้เป็นประวัติ
            # งวดที่ยังไม่ล็อก -> ใช้ค่าใหม่ เพราะตัวเลขอาจยังไม่ครบตอนแรก
            #
            # ทั้งสองกรณี ค่าที่เคยมีแต่รอบใหม่ไม่มี จะถูกเก็บไว้เหมือนเดิม
            # นี่คือหัวใจของทั้งระบบ — ปีที่ Yahoo เลิกให้แล้วต้องไม่หายไป
            if locked:
                blocked += int(diff.sum())
                use_new = cmp_["_merge"].eq("right_only")
            else:
                updated += int(diff.sum())
                use_new = cmp_["_merge"].ne("left_only")

            take_old = ~use_new
            merged = pd.concat([
                cmp_.loc[take_old, key].assign(
                    **{"ค่า": cmp_.loc[take_old, "ค่า_เดิม"],
                       "บันทึกเมื่อ": cmp_.loc[take_old, "บันทึกเมื่อ_เดิม"]}),
                cmp_.loc[use_new, key].assign(
                    **{"ค่า": cmp_.loc[use_new, "ค่า_ใหม่"],
                       "บันทึกเมื่อ": cmp_.loc[use_new, "บันทึกเมื่อ_ใหม่"]}),
            ], ignore_index=True)[COLS]

        # กรองตารางว่างออกก่อนรวม — pandas เตือนว่าอนาคตจะเปลี่ยนพฤติกรรม
        # การรวมตารางว่างเข้าไปด้วย ซึ่งอาจทำให้ชนิดข้อมูลเพี้ยน
        keep = [t for t in (others, merged) if t is not None and len(t)]
        out = pd.concat(keep, ignore_index=True) if keep else merged

        # ห้ามแถวหายเด็ดขาด — ถ้าจำนวนลดลงแปลว่ามีบั๊ก ให้ยกเลิกการเขียน
        _write_shard(f, out[COLS], before=len(old))

    if restate_rows:
        _log_restatements(market, pd.DataFrame(restate_rows))

    return {"เพิ่ม": added, "ปฏิเสธการแก้": blocked, "อัปเดตงวดที่ยังไม่ล็อก": updated,
            "แก้งบย้อนหลัง": restated, "ปีในคลัง": len(years_of(ticker, market))}


def _log_restatements(market: str, df: pd.DataFrame):
    f = _dir(market) / "การแก้ไขงบย้อนหลัง.parquet"
    n_before = 0
    if f.exists():
        old = pd.read_parquet(f)
        n_before = len(old)
        df = pd.concat([old, df], ignore_index=True)
        df = df.drop_duplicates(["ticker", "งบ", "งวด", "บรรทัด", "ค่าใหม่"])
    # ประวัติการแก้งบก็ห้ามหายเช่นกัน
    tmp = f.with_suffix(f.suffix + ".กำลังเขียน")
    df.to_parquet(tmp, compression="zstd", index=False)
    os.replace(tmp, f)


# ---------------------------------------------------------------------------
# 3) อ่านจากคลัง
# ---------------------------------------------------------------------------

def _read_market(market: str) -> pd.DataFrame:
    d = ARCHIVE_DIR / market
    if not d.exists():
        return pd.DataFrame(columns=COLS)
    files = [p for p in sorted(d.glob("*.parquet"))
             if "การแก้ไข" not in p.name]
    if not files:
        return pd.DataFrame(columns=COLS)
    return pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)


def get(ticker: str, market: str = None) -> dict:
    """
    คืนงบทั้ง 3 ของหุ้นตัวหนึ่งจากคลัง เป็น DataFrame แบบตารางกว้าง
    (บรรทัด × งวด) เรียงงวดจากเก่าไปใหม่ — รูปแบบเดียวกับที่ data_layer ให้
    """
    market = market or market_of(ticker)
    tk = str(ticker).upper()
    d = ARCHIVE_DIR / market
    if not d.exists():
        return {k: pd.DataFrame() for k in KINDS}

    parts = []
    for p in sorted(d.glob("*.parquet")):
        if "การแก้ไข" in p.name:
            continue
        try:
            # อ่านเฉพาะแถวของหุ้นตัวนี้ ไม่ต้องโหลดทั้งไฟล์เข้าหน่วยความจำ
            t = pd.read_parquet(p, filters=[("ticker", "==", tk)])
        except Exception:
            t = pd.read_parquet(p)
            t = t[t["ticker"] == tk]
        if len(t):
            parts.append(t)

    if not parts:
        return {k: pd.DataFrame() for k in KINDS}

    long = pd.concat(parts, ignore_index=True)
    out = {}
    for kind in KINDS:
        s = long[long["งบ"] == kind]
        if s.empty:
            out[kind] = pd.DataFrame()
            continue
        w = s.pivot_table(index="บรรทัด", columns="งวด", values="ค่า",
                          aggfunc="last")
        out[kind] = w[sorted(w.columns)]
    return out


def years_of(ticker: str, market: str = None):
    """งวดทั้งหมดที่คลังมีของหุ้นตัวนี้"""
    g = get(ticker, market)
    inc = g.get("income")
    if inc is None or inc.empty:
        for k in KINDS:
            if g.get(k) is not None and not g[k].empty:
                return list(g[k].columns)
        return []
    return list(inc.columns)


def merge_into(data: dict) -> dict:
    """
    รวมงบจากคลังเข้ากับงบที่เพิ่งดึงมา แล้วคืน data ที่ปีครบที่สุด

    ใช้ตอนท้ายของ data_layer.get_stock_data
    ผลคือทุกโมดูลที่เรียกใช้ข้อมูลจะได้จำนวนปีมากที่สุดเท่าที่เคยเก็บไว้
    โดยไม่ต้องแก้โค้ดโมดูลเหล่านั้นเลยแม้แต่บรรทัดเดียว
    """
    tk = data.get("ticker")
    if not tk:
        return data
    try:
        arc = get(tk)
    except Exception:
        return data

    # ทำสำเนาก่อนแก้ — ถ้าแก้ของเดิมโดยตรง ผู้เรียกที่เก็บ reference ไว้
    # จะเห็นข้อมูลเปลี่ยนไปเองโดยไม่รู้ตัว ซึ่งหาสาเหตุยากมากเวลาเกิดปัญหา
    data = dict(data)

    n_before = 0
    n_after = 0
    for kind in KINDS:
        cur = data.get(kind)
        old = arc.get(kind)
        if old is None or old.empty:
            continue
        if cur is None or not isinstance(cur, pd.DataFrame) or cur.empty:
            data[kind] = old
            continue

        n_before = max(n_before, len(cur.columns))
        # งวดที่คลังมีแต่รอบนี้ไม่มี = ปีที่ Yahoo เลิกให้แล้ว
        extra = [c for c in old.columns if c not in cur.columns]
        if extra:
            merged = pd.concat([old[extra], cur], axis=1)
            data[kind] = merged[sorted(merged.columns)]
        n_after = max(n_after, len(data[kind].columns))

    if n_after > n_before:
        data["ปีจากคลัง"] = n_after - n_before
    return data


def restatements(market: str = None) -> pd.DataFrame:
    """รายการที่บริษัทแก้ตัวเลขงบย้อนหลัง"""
    mks = [market] if market else ["thai", "us"]
    parts = []
    for m in mks:
        f = ARCHIVE_DIR / m / "การแก้ไขงบย้อนหลัง.parquet"
        if f.exists():
            t = pd.read_parquet(f)
            t["ตลาด"] = m
            parts.append(t)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def stats(market: str = None) -> pd.DataFrame:
    """สรุปว่าคลังมีอะไรอยู่บ้าง"""
    mks = [market] if market else ["thai", "us"]
    rows = []
    for m in mks:
        d = ARCHIVE_DIR / m
        if not d.exists():
            continue
        for p in sorted(d.glob("*.parquet")):
            if "การแก้ไข" in p.name:
                continue
            t = pd.read_parquet(p, columns=["ticker", "งวด"])
            rows.append({"ตลาด": m, "ปีงบ": p.stem,
                         "จำนวนหุ้น": t["ticker"].nunique(),
                         "จำนวนค่า": len(t),
                         "ขนาด (MB)": round(p.stat().st_size / 1e6, 2)})
    return pd.DataFrame(rows)


def coverage(market: str) -> pd.DataFrame:
    """หุ้นแต่ละตัวมีกี่ปีในคลัง — ใช้ดูว่าคลังเริ่มมีประโยชน์แล้วหรือยัง"""
    long = _read_market(market)
    if long.empty:
        return pd.DataFrame(columns=["ticker", "จำนวนงวด", "งวดแรก", "งวดล่าสุด"])
    g = long.groupby("ticker")["งวด"]
    return pd.DataFrame({
        "ticker": g.nunique().index,
        "จำนวนงวด": g.nunique().values,
        "งวดแรก": g.min().values,
        "งวดล่าสุด": g.max().values,
    }).sort_values("จำนวนงวด", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4) สร้างคลังจากแคชที่ดึงไว้แล้ว
# ---------------------------------------------------------------------------

def build_from_cache(progress=None) -> dict:
    """
    สร้างคลังจากไฟล์แคชที่มีอยู่ในเครื่อง — ไม่ต้องดึงข้อมูลใหม่

    เป็นการ "เริ่มนับหนึ่ง" ของคลัง ใช้ข้อมูลที่ดึงมาแล้วให้เป็นประโยชน์
    """
    import pickle
    cache = BASE_DIR / "cache"
    files = sorted(cache.glob("*.pkl"))
    total = len(files)

    # ทำทีละตลาดและรวมทีเดียว เร็วกว่าเรียก put() ทีละตัวมาก
    # เพราะ put() ต้องเปิด-ปิดไฟล์ parquet ทุกครั้ง
    bucket = {}
    n_ok = 0
    for i, p in enumerate(files, 1):
        tk = p.stem
        try:
            d = pickle.load(open(p, "rb"))
            long = to_long(tk, d)
            if len(long):
                bucket.setdefault(market_of(tk), []).append(long)
                n_ok += 1
        except Exception:
            pass
        if progress:
            progress(i, total, tk)

    summary = {}
    for m, parts in bucket.items():
        allrows = pd.concat(parts, ignore_index=True)
        for year, part in allrows.groupby(allrows["งวด"].map(_year_of)):
            f = _dir(m) / f"{year}.parquet"
            old = _read_shard(f)
            n_before = len(old)
            if n_before:
                part = pd.concat([old, part], ignore_index=True)
                # ค่าที่เก็บไว้ก่อนชนะเสมอ (keep="first")
                # เพราะคลังนี้ยึดหลัก "ค่าแรกที่บันทึกคือค่าจริง"
                part = part.drop_duplicates(
                    ["ticker", "งบ", "งวด", "บรรทัด"], keep="first")
            _write_shard(f, part[COLS], before=n_before)
        summary[m] = {"หุ้น": allrows["ticker"].nunique(),
                      "ค่า": len(allrows),
                      "ปีงบ": sorted(allrows["งวด"].map(_year_of).unique())}
    summary["อ่านแคชสำเร็จ"] = n_ok
    summary["แคชทั้งหมด"] = total
    return summary


# ---------------------------------------------------------------------------
# 5) เรียกจาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="คลังงบการเงินที่สะสมเพิ่มขึ้นทุกปี")
    p.add_argument("--สร้างจากแคช", dest="build", action="store_true",
                   help="สร้างคลังจากไฟล์ที่ดึงไว้แล้วในเครื่อง")
    p.add_argument("--สถานะ", dest="status", action="store_true")
    p.add_argument("--ดู", dest="show", metavar="TICKER")
    p.add_argument("--ความครอบคลุม", dest="cov", metavar="MARKET",
                   choices=["thai", "us"])
    p.add_argument("--การแก้ไขงบ", dest="rest", action="store_true")
    p.add_argument("--ตรวจสอบ", dest="verify", action="store_true",
                   help="ตรวจว่าข้อมูลยังครบถ้วน ไม่มีอะไรหายหรือถูกแก้")
    p.add_argument("--สำรอง", dest="backup", metavar="ปลายทาง",
                   help="คัดลอกคลังไปเก็บที่อื่น เช่น ~/Library/CloudStorage/...")
    a = p.parse_args()

    if a.verify:
        v = verify()
        print(f"\n{'='*72}\n  ตรวจสอบความครบถ้วนของคลัง\n{'='*72}")
        if v.empty:
            print("  ยังไม่มีคลัง")
        else:
            print(v.to_string(index=False))
            bad = v[v["สถานะ"].str.startswith(("❌", "⚠️"))]
            print(f"\n  ครบถ้วน {len(v)-len(bad)}/{len(v)} ไฟล์")
            if len(bad):
                print("\n  ⚠️ มีไฟล์ที่ต้องดู — ถ้าเป็น 'แถวหาย' หรือ 'ไฟล์เสียหาย'")
                print("     ให้กู้จาก git ทันที :  git checkout -- data/archive")
            else:
                print("  ไม่มีข้อมูลหายหรือถูกแก้นอกระบบ")
        print()
        return 0

    if a.backup:
        import shutil
        dest = Path(a.backup).expanduser() / "คลังงบการเงิน"
        dest.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d")
        target = dest / stamp
        print(f"\n  สำรองคลังไปที่ {target}")
        shutil.copytree(ARCHIVE_DIR, target, dirs_exist_ok=True)
        n = sum(1 for _ in target.rglob("*.parquet"))
        mb = sum(f.stat().st_size for f in target.rglob("*")) / 1e6
        print(f"  คัดลอกแล้ว {n} ไฟล์ · {mb:.1f} MB")
        print("  สำเนาเก่าไม่ถูกลบ — เก็บไว้เป็นชั้นย้อนกลับ\n")
        return 0

    if a.build:
        print("\n  สร้างคลังจากแคชที่มีอยู่ในเครื่อง\n")

        def bar(i, total, tk):
            w = 30
            f = int(w * i / total)
            sys.stdout.write(f"\r  [{'█'*f}{'·'*(w-f)}] {i:,}/{total:,}  {tk:<14}")
            sys.stdout.flush()

        s = build_from_cache(progress=bar)
        print("\n")
        for m in ("thai", "us"):
            if m in s:
                v = s[m]
                print(f"  ตลาด {m:<5} : {v['หุ้น']:,} ตัว · {v['ค่า']:,} ค่า "
                      f"· ปีงบ {v['ปีงบ'][0]}–{v['ปีงบ'][-1]}")
        print(f"\n  อ่านแคชสำเร็จ {s['อ่านแคชสำเร็จ']:,}/{s['แคชทั้งหมด']:,} ไฟล์")
        print("\n  ต่อไปทุกครั้งที่ดึงข้อมูล ระบบจะเก็บเข้าคลังให้เอง")
        print("  ปีที่ Yahoo เลิกให้แล้วจะยังอยู่ในคลังตลอดไป\n")
        a.status = True

    if a.status:
        st = stats()
        print(f"\n{'='*66}\n  สถานะคลังงบการเงิน\n{'='*66}")
        if st.empty:
            print("  ยังไม่มีข้อมูล — สั่ง python3 archive.py --สร้างจากแคช")
        else:
            print(st.to_string(index=False))
            print(f"\n  รวม {st['จำนวนค่า'].sum():,} ค่า · "
                  f"{st['ขนาด (MB)'].sum():.1f} MB")
            for m in st["ตลาด"].unique():
                c = coverage(m)
                if len(c):
                    print(f"\n  ตลาด {m} — จำนวนงวดต่อหุ้น : "
                          f"ค่ากลาง {c['จำนวนงวด'].median():.0f} · "
                          f"มากสุด {c['จำนวนงวด'].max():.0f} · "
                          f"หุ้นทั้งหมด {len(c):,} ตัว")
        print()
        return 0

    if a.show:
        tk = a.show.upper()
        g = get(tk)
        print(f"\n  {tk} ในคลัง")
        for k in KINDS:
            df = g.get(k)
            if df is None or df.empty:
                print(f"    {k:<10} ไม่มีข้อมูล")
            else:
                print(f"    {k:<10} {df.shape[0]:>3} บรรทัด × "
                      f"{df.shape[1]} งวด : {list(df.columns)}")
        print()
        return 0

    if a.cov:
        c = coverage(a.cov)
        print(f"\n  ความครอบคลุมของตลาด {a.cov} — {len(c):,} ตัว\n")
        print(c.head(25).to_string(index=False))
        print(f"\n  จำนวนงวดต่อหุ้น : ค่ากลาง {c['จำนวนงวด'].median():.0f} · "
              f"มากสุด {c['จำนวนงวด'].max():.0f}\n")
        return 0

    if a.rest:
        r = restatements()
        print(f"\n  บริษัทที่แก้ตัวเลขงบย้อนหลัง : {len(r):,} รายการ\n")
        if len(r):
            print(r.head(30).to_string(index=False))
            print("\n  การแก้งบย้อนหลังบ่อยเป็นสัญญาณคุณภาพงบที่ควรระวัง")
        print()
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
