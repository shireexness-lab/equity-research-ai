"""
tools_update_set.py — อัปเดตทะเบียนบริษัทจดทะเบียนไทย
========================================================
ใช้เมื่อไร : ทุก 3–6 เดือน เพราะมีบริษัทเข้าใหม่และเพิกถอนอยู่เรื่อย ๆ

ขั้นตอน
-------
1. เปิดเว็บตลาดหลักทรัพย์ → หัวข้อ "รายชื่อบริษัทจดทะเบียน"
   https://www.set.or.th/th/market/product/stock/quotation
   แล้วกดดาวน์โหลดเป็นไฟล์ (จะได้ชื่อประมาณ listedCompanies_th_TH.xls)

2. รันคำสั่ง
       python3 tools_update_set.py ~/Downloads/listedCompanies_th_TH.xls

3. ไฟล์ data/set_listed.json จะถูกเขียนทับด้วยข้อมูลใหม่

หมายเหตุทางเทคนิค
-----------------
ไฟล์จาก SET ตั้งชื่อเป็น .xls แต่ข้างในเป็น **HTML** และเข้ารหัสภาษาไทยแบบ
TIS-620 (ไม่ใช่ UTF-8) ถ้าเปิดด้วยโปรแกรมทั่วไปจะเห็นภาษาไทยเป็นตัวยึกยือ
สคริปต์นี้จัดการเรื่องนี้ให้เอง
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
OUT = BASE_DIR / "data" / "set_listed.json"

COLS = ["sym", "name", "market", "industry", "sector",
        "addr", "zip", "tel", "fax", "web"]


def _clean(n: str) -> str:
    """ตัดคำว่า 'บริษัท' และ 'จำกัด (มหาชน)' ออก ให้ชื่อสั้นลงอ่านง่าย"""
    n = str(n).strip()
    n = re.sub(r"^บริษัท\s*", "", n)
    n = re.sub(r"\s*จำกัด\s*\(มหาชน\)\s*$", "", n)
    return n.strip()


def _kind(name: str) -> str:
    """
    แยกประเภทหลักทรัพย์

    ทำไมต้องแยก : กองทุนรวมและ REIT ไม่มีงบการเงินแบบบริษัท
    การคำนวณ P/E, ROE, DCF จึงไม่มีความหมาย ต้องคัดออกจากการวิเคราะห์
    """
    n = str(name)
    if "กองทุนรวมโครงสร้างพื้นฐาน" in n:
        return "กองทุนโครงสร้างพื้นฐาน"
    if "ทรัสต์เพื่อการลงทุน" in n or "กองทรัสต์" in n:
        return "REIT"
    if "กองทุนรวม" in n:
        return "กองทุนรวม"
    return "หุ้นสามัญ"


def convert(path: Path) -> dict:
    raw = Path(path).read_bytes()

    # ลองถอดรหัสหลายแบบ — ไฟล์จาก SET เป็น TIS-620
    txt = None
    for enc in ("tis-620", "cp874", "utf-8"):
        try:
            txt = raw.decode(enc)
            break
        except Exception:
            continue
    if txt is None:
        raise ValueError("ถอดรหัสไฟล์ไม่สำเร็จ — ไม่ใช่ไฟล์จาก SET หรือรูปแบบเปลี่ยนไป")

    import io
    tables = pd.read_html(io.StringIO(txt))
    if not tables:
        raise ValueError("ไม่พบตารางในไฟล์")
    t = max(tables, key=lambda x: x.shape[0])
    if t.shape[1] < len(COLS):
        raise ValueError(f"ตารางมี {t.shape[1]} คอลัมน์ แต่คาดว่าจะมี {len(COLS)} "
                         "— รูปแบบไฟล์ของ SET อาจเปลี่ยนไป")
    t = t.iloc[:, :len(COLS)]
    t.columns = COLS
    t = t.iloc[2:].reset_index(drop=True)          # ข้ามหัวเรื่องกับหัวตาราง

    rows, meta_date = [], ""
    for _, r in t.iterrows():
        sym = str(r["sym"]).strip().upper()
        if not sym or sym in ("NAN", "หลักทรัพย์"):
            continue
        rows.append({"sym": sym, "name": _clean(r["name"]),
                     "market": str(r["market"]).strip(),
                     "industry": str(r["industry"]).strip(),
                     "sector": str(r["sector"]).strip(),
                     "kind": _kind(r["name"])})

    m = re.search(r"ข้อมูล ณ วันที่\s*([^<]+)", txt)
    if m:
        meta_date = m.group(1).strip()

    return {"meta": {"ที่มา": "ตลาดหลักทรัพย์แห่งประเทศไทย — รายชื่อบริษัทจดทะเบียน",
                     "ข้อมูล ณ": meta_date or "-", "จำนวน": len(rows)},
            "companies": rows}


def main() -> int:
    p = argparse.ArgumentParser(description="แปลงไฟล์รายชื่อบริษัทจดทะเบียนจาก SET")
    p.add_argument("path", help="ไฟล์ที่ดาวน์โหลดจากเว็บ SET")
    args = p.parse_args()

    try:
        js = convert(Path(args.path).expanduser())
    except Exception as e:
        print(f"\n[ไม่สำเร็จ] {type(e).__name__}: {e}\n", file=sys.stderr)
        return 1

    rows = js["companies"]
    if len(rows) < 300:
        print(f"\n[หยุด] ได้เพียง {len(rows)} รายการ ซึ่งน้อยผิดปกติ "
              "(ปกติมีราว 900) — ไม่เขียนทับไฟล์เดิมเพื่อความปลอดภัย\n",
              file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    old = 0
    if OUT.exists():
        try:
            old = len(json.loads(OUT.read_text(encoding="utf-8"))["companies"])
        except Exception:
            pass
    OUT.write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nอัปเดตแล้ว : {OUT}")
    print(f"  ข้อมูล ณ : {js['meta']['ข้อมูล ณ']}")
    print(f"  จำนวน    : {len(rows):,} รายการ" + (f" (เดิม {old:,})" if old else ""))
    print("\n  แยกตามประเภท:")
    for k, v in Counter(r["kind"] for r in rows).most_common():
        print(f"    {k:<26}{v:>5}")
    print("\n  แยกตามตลาด:")
    for k, v in Counter(r["market"] for r in rows).most_common():
        print(f"    {k:<26}{v:>5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
