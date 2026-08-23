"""
apply_cycle_patch.py — เพิ่มโหมด "วัฏจักรเศรษฐกิจ" เข้าไปใน app.py
==================================================================
ทำไมต้องใช้สคริปต์แทนการแก้มือ
------------------------------
app.py ยาว 268 KB (ราว 7,000 บรรทัด) การแก้ด้วยมือหลายจุดพร้อมกัน
เสี่ยงพิมพ์ผิดจนทั้งเว็บพัง สคริปต์นี้แก้ 6 จุดให้อัตโนมัติ
สำรองไฟล์เดิมไว้ก่อนเสมอ และ **รันซ้ำได้ไม่เสียหาย** (ถ้าแก้ไปแล้วจะข้าม)

วิธีใช้
-------
    cd "โฟลเดอร์โปรเจกต์"
    python3 apply_cycle_patch.py           # ดูก่อนว่าจะแก้อะไรบ้าง
    python3 apply_cycle_patch.py --apply   # แก้จริง
    python3 apply_cycle_patch.py --undo    # ย้อนกลับเป็นไฟล์ก่อนแก้
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
APP = BASE / "app.py"
BACKUP = BASE / "app.py.ก่อนเพิ่มวัฏจักร.bak"

MARK = "M_CYCLE"          # ถ้าเจอคำนี้ใน app.py แปลว่าแก้ไปแล้ว

# ---------------------------------------------------------------------------
# 6 จุดที่ต้องแก้ — แต่ละจุดคือ (ชื่อจุด, ข้อความที่ต้องหาเจอ, ข้อความใหม่)
# ---------------------------------------------------------------------------
PATCHES: list[tuple[str, str, str]] = [

    ("1. ประกาศชื่อโหมด",
     'M_BUY = "🏆 รายการ Strong Buy"',
     'M_BUY = "🏆 รายการ Strong Buy"\n'
     'M_CYCLE = "🌍 วัฏจักรเศรษฐกิจ"'),

    ("2. เพิ่มเข้ารายการโหมด",
     '         "เปรียบเทียบ 2–10 ตัว", M_BUY, "💰 หุ้นปันผล"]',
     '         "เปรียบเทียบ 2–10 ตัว", M_BUY, "💰 หุ้นปันผล", M_CYCLE]'),

    ("3. คำอธิบายใต้เมนู",
     '    "💰 หุ้นปันผล": "หุ้นที่ใกล้ขึ้น XD · จ่ายเท่าไร · กี่ %",',
     '    "💰 หุ้นปันผล": "หุ้นที่ใกล้ขึ้น XD · จ่ายเท่าไร · กี่ %",\n'
     '    M_CYCLE: "ตอนนี้เศรษฐกิจอยู่ช่วงไหน · ควรถือสินทรัพย์อะไร",'),

    ("4. จัดกลุ่มเมนู",
     '    ("", [HOME]),',
     '    ("", [HOME]),\n'
     '    ("🌍 ภาพใหญ่", [M_CYCLE]),'),

    ("5. การ์ดหน้าแรก",
     'CARDS = [\n',
     'CARDS = [\n'
     '    {"mode": M_CYCLE, "icon": "🌍",\n'
     '     "title": "ตอนนี้เศรษฐกิจอยู่ช่วงไหน",\n'
     '     "desc": "5 กรอบวิเคราะห์โหวตกันว่าอยู่ช่วงไหนของวัฏจักร '
     'พร้อมหลักฐานทุกตัวเลข และน้ำหนักพอร์ตที่เหมาะกับช่วงนั้น",\n'
     '     "ask": "อยากรู้ว่าภาพใหญ่ตอนนี้ควรเอียงไปทางไหน"},\n'),

    ("6. เนื้อหาของโหมด",
     "try:\n    OPTIONS, LOOKUP = ticker_options()\nexcept Exception:\n"
     "    OPTIONS, LOOKUP = [], {}\n",
     "try:\n    OPTIONS, LOOKUP = ticker_options()\nexcept Exception:\n"
     "    OPTIONS, LOOKUP = [], {}\n"
     "\n"
     "# ---------------------------------------------------------------------------\n"
     "# โหมดวัฏจักรเศรษฐกิจ (Part 18)\n"
     "#\n"
     "# วางไว้ตรงนี้เพราะต้องอยู่หลังจากที่ MODE ถูกกำหนดแล้ว\n"
     "# แต่ก่อนโหมดที่ต้องใช้ชื่อหุ้น — หน้านี้ไม่ผูกกับหุ้นตัวไหน\n"
     "# จึงเปิดดูได้ทันทีโดยไม่ต้องพิมพ์ ticker ก่อน\n"
     "#\n"
     "# เนื้อหาทั้งหมดอยู่ใน cycle_page.py เพื่อไม่ให้ app.py ยาวขึ้นอีก 600 บรรทัด\n"
     "# ---------------------------------------------------------------------------\n"
     "if MODE == M_CYCLE:\n"
     "    import cycle_page as CP\n"
     "    CP.render(dark=bool(globals().get('DARK', False)))\n"
     "    st.stop()\n"),
]

NEEDED_FILES = ["macro_data.py", "cycle.py", "allocation.py", "cycle_page.py"]


def check_files() -> list[str]:
    return [f for f in NEEDED_FILES if not (BASE / f).exists()]


def run(apply: bool) -> int:
    if not APP.exists():
        print(f"❌ ไม่พบ {APP} — ต้องรันสคริปต์นี้ในโฟลเดอร์โปรเจกต์")
        return 1

    missing = check_files()
    if missing:
        print("❌ ยังขาดไฟล์ที่ต้องใช้: " + ", ".join(missing))
        print("   คัดลอกไฟล์เหล่านี้เข้าโฟลเดอร์โปรเจกต์ก่อน แล้วรันใหม่")
        return 1

    src = APP.read_text(encoding="utf-8")

    if MARK in src:
        print("✅ app.py ถูกแก้ไปแล้ว (พบ M_CYCLE) — ไม่ต้องทำอะไรอีก")
        return 0

    print(f"ตรวจสอบ {APP.name} ({len(src):,} ตัวอักษร)")
    print("-" * 62)

    problems = []
    for name, find, _ in PATCHES:
        n = src.count(find)
        if n == 1:
            print(f"  ✓ {name}")
        elif n == 0:
            print(f"  ✗ {name} — หาจุดที่จะแก้ไม่เจอ")
            problems.append(name)
        else:
            print(f"  ✗ {name} — เจอ {n} จุด ไม่รู้จะแก้จุดไหน")
            problems.append(name)

    if problems:
        print("-" * 62)
        print("❌ แก้ไม่ได้ เพราะ app.py ต่างจากที่คาดไว้ในจุดต่อไปนี้:")
        for p in problems:
            print(f"   - {p}")
        print("\nอาจเป็นเพราะ app.py ถูกแก้ไปแล้วหลังจากที่เขียนสคริปต์นี้")
        print("ให้บอกผู้ช่วยว่าเจอปัญหานี้ พร้อมข้อความข้างบน")
        return 1

    if not apply:
        print("-" * 62)
        print("ทุกจุดพร้อมแก้ ✅")
        print("สั่งแก้จริงด้วย :  python3 apply_cycle_patch.py --apply")
        return 0

    shutil.copy2(APP, BACKUP)
    out = src
    for _, find, repl in PATCHES:
        out = out.replace(find, repl, 1)

    # ตรวจว่าไฟล์ที่แก้แล้วยังเป็น Python ที่ถูกไวยากรณ์
    # ถ้าพังต้องคืนไฟล์เดิมทันที ไม่ปล่อยให้เว็บล่ม
    try:
        compile(out, str(APP), "exec")
    except SyntaxError as e:
        print(f"❌ ไฟล์ที่แก้แล้วมีปัญหาไวยากรณ์ที่บรรทัด {e.lineno}: {e.msg}")
        print("   ไม่ได้เขียนทับไฟล์เดิม — app.py ยังเหมือนเดิมทุกอย่าง")
        return 1

    APP.write_text(out, encoding="utf-8")
    print("-" * 62)
    print(f"✅ แก้เรียบร้อย · สำรองไฟล์เดิมไว้ที่ {BACKUP.name}")
    print(f"   เวลา {datetime.now():%d/%m/%Y %H:%M}")
    print("\nขั้นต่อไป :")
    print("  1. python3 cycle.py --selftest      ทดสอบตรรกะ (ไม่ต้องต่อเน็ต)")
    print("  2. python3 macro_data.py --test     ทดสอบการดึงข้อมูลจริง")
    print("  3. streamlit run app.py             เปิดเว็บ แล้วกดเมนู 🌍 วัฏจักรเศรษฐกิจ")
    return 0


def undo() -> int:
    if not BACKUP.exists():
        print(f"❌ ไม่พบไฟล์สำรอง {BACKUP.name}")
        return 1
    shutil.copy2(BACKUP, APP)
    print(f"✅ คืนค่า app.py จาก {BACKUP.name} เรียบร้อย")
    return 0


if __name__ == "__main__":
    if "--undo" in sys.argv:
        sys.exit(undo())
    sys.exit(run(apply="--apply" in sys.argv))
