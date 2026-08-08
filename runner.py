"""
runner.py — สั่งงานวิเคราะห์ลึกจากหน้าเว็บ แล้วปล่อยให้ทำงานเบื้องหลัง
=====================================================================

ปัญหาที่แก้
-----------
การวิเคราะห์ลึกใช้เวลาหลายชั่วโมง ถ้าสั่งจากหน้าเว็บแบบตรง ๆ จะเจอ 3 ปัญหา

    1. หน้าเว็บค้าง กดอะไรไม่ได้เลยจนกว่าจะเสร็จ
    2. ปิดแท็บเบราว์เซอร์ = งานที่รันไป 3 ชั่วโมงหายหมด
    3. Streamlit รันสคริปต์ใหม่ทั้งไฟล์ทุกครั้งที่กดปุ่ม
       ตัวแปรที่เก็บความคืบหน้าไว้จะถูกล้าง

ทางแก้ — แยกเป็นคนละกระบวนการ
-------------------------------
โมดูลนี้ **ไม่ได้วิเคราะห์เอง** แต่สั่งให้ระบบปฏิบัติการเปิดโปรแกรมแยกออกไป
(`tools_deep_scan.py`) แล้วให้มันเขียนผลลง log ไฟล์

หน้าเว็บมีหน้าที่แค่ "อ่าน log แล้ววาดความคืบหน้า" เท่านั้น
ผลที่ได้คือ ปิดเบราว์เซอร์ ปิดหน้าเว็บ หรือ Streamlit รีสตาร์ท
งานก็ยังเดินต่อ เพราะมันคนละกระบวนการกัน

ข้อจำกัดที่ต้องรู้
-------------------
ใช้ได้เฉพาะตอนเปิดโปรแกรมบน **MacBook ของตัวเอง** เท่านั้น
บนเว็บ Streamlit Cloud ใช้ไม่ได้ เพราะ

    - Yahoo บล็อกหมายเลขเครื่องของศูนย์ข้อมูล ดึงข้อมูลไม่ได้อยู่แล้ว
    - เครื่องถูกล้างทุกครั้งที่มีการอัปเดตโค้ด งานที่ค้างจะหายไป

โปรแกรมจะตรวจให้เองว่าอยู่บนเครื่องไหน แล้วซ่อน/แสดงปุ่มให้เหมาะสม
"""

import json
import os
import platform
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JOB_DIR = ROOT / "cache" / "jobs"

# จำนวนบรรทัดท้าย log ที่ส่งให้หน้าเว็บวาด
# มากกว่านี้หน้าเว็บจะหน่วง เพราะต้องส่งข้อความข้ามเครือข่ายทุก 5 วินาที
TAIL_LINES = 40


def is_local() -> bool:
    """
    อยู่บนเครื่องตัวเองหรือบนเว็บ

    ใช้ระบบปฏิบัติการเป็นตัวแยก เพราะ MacBook คือ Darwin
    ส่วน Streamlit Cloud เป็น Linux เสมอ

    ถ้าวันหลังย้ายไปรันบนเครื่อง Linux ที่บ้าน ให้ตั้ง EQ_LOCAL=1 เอง
    """
    if os.environ.get("EQ_LOCAL") == "1":
        return True
    return platform.system() == "Darwin"


def _paths(market: str):
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    return (JOB_DIR / f"{market}.json", JOB_DIR / f"{market}.log")


def _reap():
    """
    เก็บกวาดกระบวนการลูกที่จบไปแล้ว

    ถ้าไม่ทำ กระบวนการที่ตายแล้วจะค้างเป็น "ซอมบี้" ในตาราง
    แล้ว os.kill(pid, 0) จะยังตอบว่า "ยังอยู่" ทั้งที่ตายไปแล้ว
    ทำให้หน้าเว็บแสดงว่ากำลังทำงานอยู่ตลอดไป
    """
    try:
        while os.waitpid(-1, os.WNOHANG)[0] != 0:
            pass
    except (ChildProcessError, OSError):
        pass


def _alive(pid: int) -> bool:
    """เช็กว่ากระบวนการยังทำงานอยู่จริงไหม — ส่งสัญญาณเปล่าไปถาม ไม่ได้ฆ่า"""
    if not pid:
        return False
    _reap()
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False

    # ยังต้องดูสถานะอีกชั้น เพราะซอมบี้ที่ยังไม่ถูกเก็บกวาด
    # (เกิดเมื่อ Streamlit รีสตาร์ทแล้วกระบวนการลูกถูกโอนไปให้ระบบ)
    # จะตอบว่ายังอยู่ทั้งที่จบไปแล้ว — ใช้ ps ถามสถานะจริง
    try:
        out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5)
        state = out.stdout.strip()
        if state and state[0] == "Z":     # Z = zombie คือจบแล้ว
            return False
    except Exception:
        pass
    return True


def build_command(market: str, scope: str, hours=None, refresh_days=None,
                  top=None, push=False) -> str:
    """
    ประกอบคำสั่งที่จะให้เครื่องรัน — คืนเป็นข้อความเพื่อให้แสดงให้ผู้ใช้เห็นก่อนได้

    scope : "all"     ทั้งตลาด
            "top"     เฉพาะ N ตัวที่คะแนนพรีสกรีนสูงสุด
            "refresh" อัปเดตเฉพาะตัวที่ผลเก่าเกินกำหนด
    """
    py = sys.executable or "python3"
    cmd = [py, "tools_deep_scan.py", f"--{market}"]

    if scope == "top":
        cmd += ["--top", str(int(top or 150))]
    else:
        cmd += ["--all"]
    if hours:
        cmd += ["--hours", f"{float(hours):g}"]
    if refresh_days:
        cmd += ["--refresh-days", str(int(refresh_days))]

    line = " ".join(cmd)

    if push:
        # ส่งขึ้น GitHub ต่อทันทีเมื่อวิเคราะห์เสร็จ
        #
        # ใช้ ; แทน && ตรง commit โดยตั้งใจ
        # เพราะถ้าไม่มีอะไรเปลี่ยน git commit จะคืนค่าผิดพลาด
        # ซึ่งไม่ใช่ความผิดพลาดจริง แค่ "ไม่มีอะไรใหม่" — ไม่ควรทำให้ push ไม่ทำงาน
        # ใช้ double quote ครอบข้อความ commit เพื่อให้ $(date) ทำงาน
        # ถ้าใช้ single quote ซ้อนกัน bash จะตีความผิดและคำสั่งพัง
        msg = f'"อัปเดตผลวิเคราะห์ลึก {market} $(date +%F\\ %H:%M)"'
        line += (f" && git add data/snapshots"
                 f" && (git commit -m {msg} || true) && git push")
    return line


def start(market: str, scope: str = "all", hours=None, refresh_days=None,
          top=None, push=False) -> dict:
    """สั่งเริ่มงาน — คืนสถานะทันที ไม่รอให้เสร็จ"""
    st = status(market)
    if st["กำลังทำงาน"]:
        return {**st, "ข้อความ": "มีงานของตลาดนี้กำลังทำอยู่แล้ว"}

    meta_f, log_f = _paths(market)
    cmd = build_command(market, scope, hours, refresh_days, top, push)

    log_f.write_text(
        f"เริ่ม {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"คำสั่ง : {cmd}\n" + "-" * 60 + "\n", encoding="utf-8")

    with open(log_f, "a", encoding="utf-8") as fh:
        p = subprocess.Popen(
            ["bash", "-lc", cmd], cwd=str(ROOT),
            stdout=fh, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            # แยกกลุ่มกระบวนการออกจาก Streamlit
            # ถ้าไม่ทำ พอปิด Streamlit งานที่รันอยู่จะถูกฆ่าตามไปด้วย
            start_new_session=True)

    meta = {"pid": p.pid, "ตลาด": market, "ขอบเขต": scope,
            "งบเวลา (ชม.)": hours, "อัปเดตทุก (วัน)": refresh_days,
            "ส่งขึ้นเว็บ": bool(push), "คำสั่ง": cmd,
            "เริ่มเมื่อ": datetime.now().isoformat(timespec="seconds")}
    meta_f.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return status(market)


def status(market: str) -> dict:
    """สถานะงานล่าสุดของตลาดนี้"""
    meta_f, log_f = _paths(market)
    if not meta_f.exists():
        return {"มีงาน": False, "กำลังทำงาน": False, "log": "", "meta": {}}

    try:
        meta = json.loads(meta_f.read_text(encoding="utf-8"))
    except Exception:
        return {"มีงาน": False, "กำลังทำงาน": False, "log": "", "meta": {}}

    alive = _alive(meta.get("pid", 0))
    tail = ""
    if log_f.exists():
        try:
            lines = log_f.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-TAIL_LINES:])
        except Exception:
            pass

    started = meta.get("เริ่มเมื่อ", "")
    mins = None
    try:
        mins = (datetime.now() - datetime.fromisoformat(started)).total_seconds() / 60
    except Exception:
        pass

    return {"มีงาน": True, "กำลังทำงาน": alive, "log": tail, "meta": meta,
            "นาทีที่ผ่านไป": mins}


def stop(market: str) -> bool:
    """
    สั่งหยุดงาน

    ผลที่วิเคราะห์ไปแล้ว **ไม่หาย** เพราะระบบบันทึกทุก 10 ตัวอยู่แล้ว
    รอบหน้าจะทำต่อจากจุดที่ค้าง
    """
    meta_f, _ = _paths(market)
    if not meta_f.exists():
        return False
    try:
        meta = json.loads(meta_f.read_text(encoding="utf-8"))
        pid = meta.get("pid", 0)
        if _alive(pid):
            # ฆ่าทั้งกลุ่ม เพราะคำสั่งจริงถูกห่อด้วย bash อีกชั้น
            # ถ้าฆ่าแค่ bash ตัว python ที่ทำงานอยู่จะยังรันต่อ
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            return True
    except Exception:
        pass
    return False


def progress_from_log(text: str):
    """
    อ่านความคืบหน้าจากบรรทัด log แบบ  [  12/500] AAPL  ...

    คืน (ทำไปแล้ว, ทั้งหมด) หรือ None ถ้ายังไม่เริ่มนับ
    """
    import re
    last = None
    for m in re.finditer(r"\[\s*(\d+)/(\d+)\]", text or ""):
        last = m
    if not last:
        return None
    return int(last.group(1)), int(last.group(2))
