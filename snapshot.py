"""
snapshot.py — เก็บผลคัดกรองไว้ใช้ซ้ำ (จานในเครื่อง + Google Drive)
====================================================================
ปัญหาที่แก้
-----------
คัดกรองหุ้นไทยทั้งตลาด 866 ตัว ใช้เวลา 6–10 นาที
ถ้าปิดหน้าเว็บแล้วเปิดใหม่ ต้องรอใหม่ทั้งหมด

ที่แย่กว่านั้น : Streamlit Cloud จะ "หลับ" เมื่อไม่มีคนใช้ราว 30 นาที
พอตื่นขึ้นมา เครื่องเป็นเครื่องใหม่ — ไฟล์ที่เขียนไว้ในเครื่องหายหมด
จึงต้องมีที่เก็บนอกเครื่อง และ Google Drive เป็นตัวเลือกที่ฟรีและง่ายที่สุด

เก็บอะไรบ้าง
------------
**เฉพาะตัวเลขที่ใช้คำนวณ** ไม่เก็บรายละเอียดอื่น
คือคอลัมน์ชุดเดียวกับตารางคัดกรอง (ticker, ราคา, P/E, P/BV, ROE, D/E,
อัตรากำไร, FCF Yield, ปันผล, มูลค่าตลาด, กลุ่ม)

ขนาดจริง : หุ้นไทย 866 ตัว = ราว 60 KB เมื่อบีบอัดแล้ว
เทียบกับการเก็บงบการเงินเต็ม ๆ ซึ่งจะเป็นหลักร้อย MB

ที่เก็บ 2 ชั้น
--------------
ชั้นที่ 1  จานในเครื่อง  cache/snapshots/   เร็วที่สุด แต่หายเมื่อเครื่องรีสตาร์ท
ชั้นที่ 2  Google Drive                     ช้ากว่าเล็กน้อย แต่อยู่ถาวร

อ่าน : ลองชั้น 1 ก่อน ถ้าไม่มีหรือเก่าเกินไปค่อยลงไปชั้น 2
เขียน : เขียนทั้ง 2 ชั้น (ถ้าตั้งค่า Drive ไว้)

ถ้าไม่ตั้งค่า Google Drive ระบบยังทำงานได้ปกติ แค่ใช้ชั้นที่ 1 อย่างเดียว
วิธีตั้งค่าดูได้ที่ไฟล์ 18_เก็บข้อมูลไว้ที่_Google_Drive.md

วิธีใช้จาก Terminal
-------------------
    python3 snapshot.py --list              # ดูว่ามีอะไรเก็บไว้บ้าง
    python3 snapshot.py --test              # ทดสอบว่าต่อ Google Drive ได้ไหม
"""

import gzip
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
LOCAL_DIR = BASE_DIR / "cache" / "snapshots"

# ชื่อโฟลเดอร์ที่จะสร้างใน Google Drive ถ้าไม่ได้ระบุ folder id ไว้
DRIVE_FOLDER_NAME = "EquityResearchAI"


# ---------------------------------------------------------------------------
# ตัวช่วยทั่วไป
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _age_hours(iso: str) -> float:
    """อายุของข้อมูลเป็นชั่วโมง — คืน inf ถ้าอ่านเวลาไม่ได้ (ถือว่าเก่ามาก)"""
    try:
        t = datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600
    except Exception:
        return float("inf")


def _pack(df: pd.DataFrame, meta: dict) -> bytes:
    """
    รวม meta + ตาราง ไว้ในไฟล์เดียวแล้วบีบอัด

    รูปแบบ : บรรทัดแรกเป็น JSON ของ meta · ที่เหลือเป็น CSV
    ทำแบบนี้เพราะอ่านง่ายด้วยตาเปล่าถ้าต้องตรวจสอบ และไม่ต้องมี 2 ไฟล์ให้หลุดกัน
    """
    buf = io.StringIO()
    buf.write(json.dumps(meta, ensure_ascii=False) + "\n")
    df.to_csv(buf, index=False)
    return gzip.compress(buf.getvalue().encode("utf-8"))


def _unpack(raw: bytes):
    txt = gzip.decompress(raw).decode("utf-8")
    head, _, body = txt.partition("\n")
    meta = json.loads(head)
    df = pd.read_csv(io.StringIO(body))
    return df, meta


def _fname(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(name))
    return f"snap_{safe}.csv.gz"


# ---------------------------------------------------------------------------
# ชั้นที่ 1 — จานในเครื่อง
# ---------------------------------------------------------------------------

def _local_save(name: str, blob: bytes) -> bool:
    try:
        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        (LOCAL_DIR / _fname(name)).write_bytes(blob)
        return True
    except Exception:
        return False


def _local_load(name: str):
    p = LOCAL_DIR / _fname(name)
    if not p.exists():
        return None
    try:
        return p.read_bytes()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ชั้นที่ 2 — Google Drive
# ---------------------------------------------------------------------------

def _credentials():
    """
    หากุญแจของ service account จาก 3 ที่ ตามลำดับ

    1. Streamlit Secrets  st.secrets["gdrive"]        <- ใช้ตอน deploy
    2. ตัวแปรสภาพแวดล้อม  GDRIVE_SERVICE_ACCOUNT_JSON  <- ใช้ตอนรันบนเครื่อง
    3. ไฟล์               gdrive_service_account.json  <- ใช้ตอนทดลอง

    คืน None ถ้าไม่พบ — ระบบจะทำงานต่อโดยใช้เฉพาะจานในเครื่อง
    """
    info = None

    try:                                            # 1
        import streamlit as st
        if "gdrive" in st.secrets:
            info = dict(st.secrets["gdrive"])
    except Exception:
        pass

    if info is None:                                # 2
        raw = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip()
        if raw:
            try:
                info = json.loads(raw)
            except Exception:
                info = None

    if info is None:                                # 3
        f = BASE_DIR / "gdrive_service_account.json"
        if f.exists():
            try:
                info = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                info = None

    if not info or "private_key" not in info:
        return None

    # Streamlit Secrets เก็บ \n ในกุญแจเป็นตัวอักษรสองตัว ต้องแปลงกลับเป็นขึ้นบรรทัด
    info = dict(info)
    info["private_key"] = str(info["private_key"]).replace("\\n", "\n")

    try:
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive.file"])
    except Exception:
        return None


_drive_cache = {"service": None, "folder": None, "tried": False}


def _drive():
    """คืน (service, folder_id) หรือ (None, None) ถ้าใช้ Drive ไม่ได้"""
    if _drive_cache["tried"]:
        return _drive_cache["service"], _drive_cache["folder"]
    _drive_cache["tried"] = True

    creds = _credentials()
    if creds is None:
        return None, None
    try:
        from googleapiclient.discovery import build
        svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        return None, None

    folder = os.environ.get("GDRIVE_FOLDER_ID", "").strip()
    if not folder:
        try:
            import streamlit as st
            folder = str(st.secrets.get("gdrive_folder_id", "")).strip()
        except Exception:
            folder = ""

    if not folder:
        # ยังไม่ได้ระบุโฟลเดอร์ — หาโฟลเดอร์ชื่อเดิม ถ้าไม่มีก็สร้างใหม่
        try:
            q = (f"name='{DRIVE_FOLDER_NAME}' and "
                 "mimeType='application/vnd.google-apps.folder' and trashed=false")
            r = svc.files().list(q=q, fields="files(id)", pageSize=1).execute()
            files = r.get("files", [])
            if files:
                folder = files[0]["id"]
            else:
                meta = {"name": DRIVE_FOLDER_NAME,
                        "mimeType": "application/vnd.google-apps.folder"}
                folder = svc.files().create(body=meta, fields="id").execute()["id"]
        except Exception:
            return None, None

    _drive_cache["service"], _drive_cache["folder"] = svc, folder
    return svc, folder


def _drive_find(svc, folder: str, fname: str):
    try:
        q = f"name='{fname}' and '{folder}' in parents and trashed=false"
        r = svc.files().list(q=q, fields="files(id)", pageSize=1).execute()
        files = r.get("files", [])
        return files[0]["id"] if files else None
    except Exception:
        return None


def _drive_save(name: str, blob: bytes) -> bool:
    svc, folder = _drive()
    if svc is None:
        return False
    fname = _fname(name)
    try:
        from googleapiclient.http import MediaIoBaseUpload
        media = MediaIoBaseUpload(io.BytesIO(blob),
                                  mimetype="application/gzip", resumable=False)
        fid = _drive_find(svc, folder, fname)
        if fid:                                     # ทับไฟล์เดิม ไม่สร้างซ้ำ
            svc.files().update(fileId=fid, media_body=media).execute()
        else:
            svc.files().create(body={"name": fname, "parents": [folder]},
                               media_body=media, fields="id").execute()
        return True
    except Exception:
        return False


def _drive_load(name: str):
    svc, folder = _drive()
    if svc is None:
        return None
    fid = _drive_find(svc, folder, _fname(name))
    if not fid:
        return None
    try:
        from googleapiclient.http import MediaIoBaseDownload
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=fid))
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue()
    except Exception:
        return None


def drive_ready() -> bool:
    """ตั้งค่า Google Drive เรียบร้อยหรือยัง — ใช้แสดงสถานะในหน้าเว็บ"""
    svc, _ = _drive()
    return svc is not None


# ---------------------------------------------------------------------------
# หน้าบ้าน — ใช้แค่ 2 ฟังก์ชันนี้
# ---------------------------------------------------------------------------

def save(name: str, df: pd.DataFrame, extra: dict = None) -> dict:
    """
    เก็บตารางตัวเลขไว้ใช้ซ้ำ

    คืน dict บอกว่าเก็บสำเร็จที่ไหนบ้าง เช่น {"local": True, "drive": False}
    """
    if df is None or df.empty:
        return {"local": False, "drive": False}

    meta = {"ชื่อชุดข้อมูล": name,
            "บันทึกเมื่อ": _now(),
            "จำนวนแถว": int(len(df)),
            "คอลัมน์": list(df.columns)}
    if extra:
        meta.update(extra)

    blob = _pack(df, meta)
    out = {"local": _local_save(name, blob),
           "drive": _drive_save(name, blob),
           "ขนาด (KB)": round(len(blob) / 1024, 1)}
    return out


def load(name: str, max_age_hours: float = 24.0):
    """
    อ่านตารางที่เก็บไว้

    คืน (df, meta) — meta มี "อายุ (ชม.)" และ "ที่มา" (local / drive)
    คืน (None, None) ถ้าไม่มีหรือเก่าเกิน max_age_hours

    ลำดับ : จานในเครื่องก่อน (เร็วกว่า) ถ้าไม่ได้ค่อยไป Google Drive
    """
    for where, fn in (("local", _local_load), ("drive", _drive_load)):
        raw = fn(name)
        if not raw:
            continue
        try:
            df, meta = _unpack(raw)
        except Exception:
            continue
        age = _age_hours(meta.get("บันทึกเมื่อ", ""))
        if max_age_hours is not None and age > max_age_hours:
            continue
        meta["อายุ (ชม.)"] = round(age, 1)
        meta["ที่มา"] = where
        if where == "drive":
            _local_save(name, raw)                  # ดึงมาแล้วเก็บไว้ในเครื่องด้วย
        return df, meta
    return None, None


def info(name: str):
    """ดูข้อมูลของชุดที่เก็บไว้โดยไม่สนใจอายุ — ใช้บอกผู้ใช้ว่ามีของเก่าอยู่"""
    return load(name, max_age_hours=None)


# ---------------------------------------------------------------------------
# ใช้จาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="ที่เก็บผลคัดกรองไว้ใช้ซ้ำ")
    p.add_argument("--list", action="store_true", help="ดูของที่เก็บไว้ในเครื่อง")
    p.add_argument("--test", action="store_true", help="ทดสอบการต่อ Google Drive")
    a = p.parse_args()

    if a.test:
        print("\nทดสอบการต่อ Google Drive")
        print("-" * 46)
        if _credentials() is None:
            print("  กุญแจ      : ไม่พบ")
            print("\n  ระบบยังใช้งานได้ตามปกติ แต่จะเก็บไว้ในเครื่องอย่างเดียว")
            print("  วิธีตั้งค่า : อ่านไฟล์ 18_เก็บข้อมูลไว้ที่_Google_Drive.md\n")
            return 1
        print("  กุญแจ      : พบแล้ว")
        svc, folder = _drive()
        if svc is None:
            print("  เชื่อมต่อ   : ไม่สำเร็จ (กุญแจอาจหมดอายุ หรือยังไม่เปิด Drive API)\n")
            return 1
        print(f"  เชื่อมต่อ   : สำเร็จ")
        print(f"  โฟลเดอร์   : {folder}")

        df = pd.DataFrame({"ทดสอบ": [1, 2, 3]})
        r = save("_ทดสอบ", df)
        print(f"  เขียนไฟล์  : {'สำเร็จ' if r['drive'] else 'ไม่สำเร็จ'}")
        back, meta = load("_ทดสอบ", max_age_hours=1)
        print(f"  อ่านกลับ   : {'สำเร็จ' if back is not None else 'ไม่สำเร็จ'}")
        print()
        return 0 if r["drive"] else 1

    print(f"\nโฟลเดอร์ในเครื่อง : {LOCAL_DIR}")
    if not LOCAL_DIR.exists():
        print("  (ยังไม่มีข้อมูลที่เก็บไว้)\n")
        return 0
    files = sorted(LOCAL_DIR.glob("snap_*.csv.gz"))
    if not files:
        print("  (ยังไม่มีข้อมูลที่เก็บไว้)\n")
        return 0
    print(f"{'ชุดข้อมูล':<24}{'แถว':>8}{'อายุ (ชม.)':>12}{'ขนาด (KB)':>12}")
    print("-" * 56)
    for f in files:
        try:
            _, meta = _unpack(f.read_bytes())
            print(f"{meta.get('ชื่อชุดข้อมูล',''):<24}"
                  f"{meta.get('จำนวนแถว',0):>8,}"
                  f"{_age_hours(meta.get('บันทึกเมื่อ','')):>12.1f}"
                  f"{f.stat().st_size/1024:>12.1f}")
        except Exception as e:
            print(f"{f.name:<24}  อ่านไม่ได้: {e}")
    print(f"\nGoogle Drive : {'ตั้งค่าแล้ว' if drive_ready() else 'ยังไม่ได้ตั้งค่า'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
