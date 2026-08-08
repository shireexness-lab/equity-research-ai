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
from html.parser import HTMLParser
from pathlib import Path

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


class _TableParser(HTMLParser):
    """
    ตัวแกะตาราง HTML แบบง่าย ๆ ใช้เครื่องมือที่ Python มีมาให้อยู่แล้ว

    ทำไมไม่ใช้ pandas.read_html : ฟังก์ชันนั้นต้องติดตั้ง lxml เพิ่ม
    ซึ่งเป็นภาระเกินจำเป็นสำหรับเครื่องมือที่ใช้ปีละ 2 ครั้ง
    ไฟล์ของ SET เป็นตาราง HTML ธรรมดามาก แกะเองได้ในไม่กี่บรรทัด
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self._row, self._cell, self._in = [], None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._in, self._cell = True, []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._in = False
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._in:
            self._cell.append(data)


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

    p = _TableParser()
    p.feed(txt)
    if not p.rows:
        raise ValueError("ไม่พบตารางในไฟล์ — รูปแบบไฟล์ของ SET อาจเปลี่ยนไป")

    widest = max(len(r) for r in p.rows)
    if widest < len(COLS):
        raise ValueError(f"ตารางมีอย่างมาก {widest} คอลัมน์ แต่คาดว่าจะมี {len(COLS)} "
                         "— รูปแบบไฟล์ของ SET อาจเปลี่ยนไป")

    rows, meta_date = [], ""
    for r in p.rows:
        if len(r) < len(COLS):
            continue                                # แถวหัวเรื่องที่รวมช่อง
        sym = r[0].strip().upper()
        if not sym or sym in ("หลักทรัพย์", "SYMBOL"):
            continue
        if not re.fullmatch(r"[A-Z0-9&.\-]{1,15}", sym):
            continue                                # ไม่ใช่ชื่อย่อหลักทรัพย์
        rows.append({"sym": sym, "name": _clean(r[1]),
                     "market": r[2].strip(),
                     "industry": r[3].strip(),
                     "sector": r[4].strip(),
                     "kind": _kind(r[1])})

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
