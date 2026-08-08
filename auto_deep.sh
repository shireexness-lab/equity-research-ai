#!/bin/bash
# auto_deep.sh — วิเคราะห์ลึกอัตโนมัติบน MacBook แล้วส่งขึ้นเว็บ
# ===============================================================
# ตัวสำรองของ GitHub Actions
#
# ทำไมต้องมีตัวสำรอง
# -------------------
# GitHub Actions ทำงานบนเครื่องของศูนย์ข้อมูล ซึ่ง Yahoo อาจปิดกั้น
# ถ้าโดนปิดกั้น การอัปเดตอัตโนมัติบนคลาวด์จะไม่ได้ข้อมูลเลย
# แต่ MacBook ต่อเน็ตบ้าน ไม่โดนปิดกั้น จึงใช้เป็นทางหลักได้เสมอ
#
# ข้อแลกเปลี่ยน : ต้องเปิดเครื่องทิ้งไว้ (หรืออย่างน้อยไม่ปิดสนิท)
# ถ้าเครื่องหลับอยู่ macOS จะรันให้ทันทีที่ตื่น
#
# ใช้ยังไง
# ---------
#   รันมือครั้งเดียว   ./auto_deep.sh
#   ตั้งให้รันเอง      ./setup_auto_deep.sh   (ทำครั้งเดียวพอ)

set -u

cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"

# ---- เตรียม Python ----
# ใช้ห้องแยก (.venv) ถ้ามี เพราะไลบรารีทั้งหมดติดตั้งไว้ในนั้น
if [ -x "$ROOT/.venv/bin/python3" ]; then
    PY="$ROOT/.venv/bin/python3"
else
    PY="$(command -v python3)"
fi

LOG_DIR="$ROOT/cache/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/auto-deep-$(date +%F).log"

say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# ---- เลือกตลาดของรอบนี้ ----
# สลับไทย/สหรัฐตามวันที่ เพื่อให้ทั้งสองตลาดได้อัปเดตพอ ๆ กัน
# และรอบเดียวไม่กินเวลาทั้งคืน
DAY=$(date +%-d)
if [ $(( DAY % 2 )) -eq 1 ]; then
    MARKET=thai
else
    MARKET=us
fi

# งบเวลาต่อรอบ (ชั่วโมง) — ตั้ง 5 เพื่อให้จบก่อนเช้า
HOURS="${EQ_HOURS:-5}"
# ผลเก่าเกินกี่วันให้ทำใหม่
DAYS="${EQ_REFRESH_DAYS:-3}"

say "========================================================"
say "เริ่มวิเคราะห์ลึกอัตโนมัติ — ตลาด $MARKET"
say "งบเวลา $HOURS ชม. · ผลเก่าเกิน $DAYS วันจะทำใหม่"
say "========================================================"

"$PY" tools_deep_scan.py --"$MARKET" --all \
      --hours "$HOURS" --refresh-days "$DAYS" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}

if [ "$RC" -ne 0 ]; then
    say "โปรแกรมวิเคราะห์จบด้วยรหัสผิดพลาด $RC — ไม่ส่งขึ้นเว็บ"
    exit "$RC"
fi

# ---- ส่งขึ้นเว็บ ----
if [ -z "$(git status --porcelain data/snapshots)" ]; then
    say "ไม่มีผลใหม่ — ไม่ต้องส่งขึ้นเว็บ"
    exit 0
fi

say "ส่งผลขึ้น GitHub"
git add data/snapshots
git commit -m "วิเคราะห์ลึกอัตโนมัติ $MARKET $(date '+%Y-%m-%d %H:%M')" >>"$LOG" 2>&1

# ดึงของคนอื่นมารวมก่อน กัน push ไม่ผ่านเพราะมีคนแก้ระหว่างที่เรารัน 5 ชม.
git pull --rebase --autostash >>"$LOG" 2>&1 || true

if git push >>"$LOG" 2>&1; then
    say "ส่งขึ้นเว็บเรียบร้อย — เปิดเว็บแล้วกด 'โหลดข้อมูลใหม่' ได้เลย"
else
    say "ส่งขึ้นเว็บไม่สำเร็จ — ผลยังอยู่ในเครื่องครบ ลอง git push เองภายหลัง"
fi

# ---- เก็บ log ไว้ 30 วันพอ ----
find "$LOG_DIR" -name 'auto-deep-*.log' -mtime +30 -delete 2>/dev/null

say "จบรอบ"
