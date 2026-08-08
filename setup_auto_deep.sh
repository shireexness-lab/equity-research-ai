#!/bin/bash
# setup_auto_deep.sh — ตั้งให้ MacBook วิเคราะห์ลึกเองทุก 3 วัน
# ==============================================================
# ทำครั้งเดียวพอ หลังจากนี้เครื่องจะทำเองโดยไม่ต้องสั่ง
#
# ใช้ launchd ซึ่งเป็นระบบตั้งเวลาในตัวของ macOS
# (ไม่ใช้ cron เพราะ cron บน Mac รุ่นใหม่ถูกจำกัดสิทธิ์และมักไม่ทำงาน)
#
# พฤติกรรมที่ควรรู้
# -----------------
#   - ถ้าถึงเวลาแล้วเครื่องหลับอยู่ macOS จะรันให้ทันทีที่ตื่น ไม่ข้ามรอบ
#   - ถ้าปิดเครื่องสนิท จะรันรอบถัดไปตอนเปิดเครื่อง
#   - งานรันเบื้องหลัง ไม่มีหน้าต่างเด้ง ใช้เครื่องทำอย่างอื่นได้ตามปกติ
#
# ใช้ยังไง
# ---------
#   ติดตั้ง   ./setup_auto_deep.sh
#   ถอนออก    ./setup_auto_deep.sh --ถอน
#   ดูสถานะ   ./setup_auto_deep.sh --สถานะ

set -eu

cd "$(dirname "$0")"
ROOT="$(pwd)"
LABEL="com.equityresearch.deepscan"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# ทุก 3 วัน = 259200 วินาที
INTERVAL=259200

case "${1:-}" in
  --ถอน|--uninstall)
      launchctl unload "$PLIST" 2>/dev/null || true
      rm -f "$PLIST"
      echo "ถอนการตั้งเวลาอัตโนมัติแล้ว — จากนี้ต้องกดปุ่มอัปเดตเอง"
      exit 0
      ;;
  --สถานะ|--status)
      if [ -f "$PLIST" ]; then
          echo "ติดตั้งไว้แล้ว : $PLIST"
          launchctl list | grep "$LABEL" \
              && echo "   ^ คอลัมน์แรกคือ PID (- = ไม่ได้รันอยู่ตอนนี้ ถือว่าปกติ)" \
              || echo "   ยังไม่ถูกโหลด — สั่ง ./setup_auto_deep.sh อีกครั้ง"
          echo
          echo "log ล่าสุด :"
          ls -t "$ROOT/cache/logs"/auto-deep-*.log 2>/dev/null | head -3 || echo "   ยังไม่มี"
      else
          echo "ยังไม่ได้ตั้งเวลาอัตโนมัติ — สั่ง ./setup_auto_deep.sh เพื่อติดตั้ง"
      fi
      exit 0
      ;;
esac

chmod +x "$ROOT/auto_deep.sh"
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/cache/logs"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$ROOT/auto_deep.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$ROOT</string>

    <!-- ทุก 3 วัน -->
    <key>StartInterval</key>
    <integer>$INTERVAL</integer>

    <!-- ถ้าเลยเวลาไปแล้วเพราะเครื่องหลับ ให้รันทันทีที่ตื่น -->
    <key>RunAtLoad</key>
    <false/>

    <key>StandardOutPath</key>
    <string>$ROOT/cache/logs/launchd-out.log</string>
    <key>StandardErrorPath</key>
    <string>$ROOT/cache/logs/launchd-err.log</string>

    <!-- ให้รันด้วยความสำคัญต่ำ จะได้ไม่แย่งเครื่องตอนใช้งานอยู่ -->
    <key>Nice</key>
    <integer>10</integer>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
PLISTEOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "======================================================================"
echo "  ตั้งเรียบร้อย — MacBook จะวิเคราะห์ลึกเองทุก 3 วัน"
echo "======================================================================"
echo
echo "  ทำอะไร   : สลับตลาดไทย/สหรัฐไปเรื่อย ๆ รอบละไม่เกิน 5 ชั่วโมง"
echo "             ตัวที่ทำแล้วไม่ทำซ้ำ · ตัวที่ผลเก่าเกิน 3 วันจะทำใหม่"
echo "             เสร็จแล้วส่งขึ้น GitHub ให้เอง"
echo
echo "  ดูสถานะ  : ./setup_auto_deep.sh --สถานะ"
echo "  ถอนออก   : ./setup_auto_deep.sh --ถอน"
echo "  ดู log   : ls -t cache/logs/"
echo
echo "  รอบแรกจะเริ่มในอีก 3 วัน — ถ้าอยากรันเลยตอนนี้ให้สั่ง :"
echo "      ./auto_deep.sh"
echo
