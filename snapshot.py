"""
snapshot.py — เก็บผลคัดกรองไว้ใช้ซ้ำ
======================================
ปัญหาที่แก้
-----------
1. คัดกรองหุ้นไทยทั้งตลาด 866 ตัว ใช้เวลา 6–10 นาที
   ปิดหน้าเว็บแล้วเปิดใหม่ ต้องรอใหม่ทั้งหมด

2. Streamlit Cloud "หลับ" เมื่อไม่มีคนใช้ราว 30 นาที
   พอตื่นขึ้นมา เครื่องเป็นเครื่องใหม่ — ไฟล์ที่เขียนไว้หายหมด

3. Yahoo Finance บล็อกคำขอจากศูนย์ข้อมูล (ซึ่งรวม Streamlit Cloud)
   ทำให้กดคัดกรองบนเว็บได้ 0 ตัว ทั้งที่รันบน MacBook แล้วได้ครบ

ทางแก้ทั้งสามข้อคือทางเดียวกัน — **ดึงบน Mac แล้วส่งผลไปให้เว็บอ่าน**

เก็บอะไรบ้าง
------------
**เฉพาะตัวเลขที่ใช้คำนวณ** ไม่เก็บรายละเอียดอื่น
คือคอลัมน์ชุดเดียวกับตารางคัดกรอง (ticker, ราคา, P/E, P/BV, ROE, D/E,
อัตรากำไร, FCF Yield, ปันผล, มูลค่าตลาด, กลุ่ม)

ขนาดจริง : หุ้นไทย 866 ตัว = ราว 60 KB เมื่อบีบอัดแล้ว
ทั้งหมดเป็นข้อมูลสาธารณะของบริษัทจดทะเบียน ไม่มีข้อมูลส่วนตัวของผู้ใช้

ที่เก็บ 3 ชั้น
--------------
| ชั้น | ที่อยู่ | อยู่รอดเมื่อ Streamlit รีสตาร์ท | ต้องตั้งค่า |
|------|--------|--------------------------------|-------------|
| เครื่อง | cache/snapshots/       | ไม่ | ไม่ต้อง |
| โปรเจกต์ | data/snapshots/      | **ใช่** | ไม่ต้อง (git push) |
| Drive   | Google Drive          | **ใช่** | ต้องตั้งค่า |

ชั้น "โปรเจกต์" คือวิธีหลักที่ใช้อยู่ — ไฟล์เดินทางไปพร้อมโค้ดผ่าน git
ไม่ต้องมีกุญแจ ไม่ต้องสมัครบริการอะไรเพิ่ม

การอ่าน : อ่านทุกชั้นแล้ว **เลือกอันที่ใหม่ที่สุด**
ไม่ใช่ไล่ตามลำดับ เพราะถ้าไล่ตามลำดับแล้วในเครื่องมีของเก่าค้างอยู่
จะได้ข้อมูลเก่าทั้งที่ในโปรเจกต์มีของใหม่กว่า — ผู้ใช้จะไม่มีทางรู้เลย

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

# ที่เก็บชั่วคราวของเครื่องที่รันอยู่ — .gitignore กันไว้ ไม่ขึ้น git
LOCAL_DIR = BASE_DIR / "cache" / "snapshots"

# ที่เก็บที่เดินทางไปพร้อมโค้ด — อยู่ใน git จริง จึงตามไปถึง Streamlit Cloud ด้วย
REPO_DIR = BASE_DIR / "data" / "snapshots"

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

    # ---- คืนสภาพคอลัมน์ข้อความ ----
    # CSV ไม่แยกระหว่าง "ข้อความว่าง" กับ "ไม่มีค่า" — ทั้งคู่เขียนออกมาเป็นช่องว่าง
    # ตอนอ่านกลับ pandas จึงแปลงเป็น NaN ทั้งหมด
    #
    # ทำไมเรื่องนี้สำคัญมาก : คอลัมน์ "ปัญหา" ใช้ค่าว่าง "" แปลว่า "ดึงข้อมูลสำเร็จ"
    # ถ้ากลายเป็น NaN เงื่อนไข df["ปัญหา"] == "" จะเป็นเท็จทุกแถว
    # ผลคือหุ้นที่ดึงสำเร็จ 807 ตัวถูกนับเป็น 0 ตัว — ตารางว่างเปล่าทั้งที่ข้อมูลครบ
    text_cols = meta.get("คอลัมน์ข้อความ")
    if text_cols is None:                       # ไฟล์เก่าที่บันทึกก่อนแก้บั๊กนี้
        text_cols = [c for c in df.columns
                     if df[c].dtype == object and df[c].notna().any()]
        for c in ("ปัญหา", "ชื่อบริษัท", "กลุ่ม", "⚠️"):
            if c in df.columns and c not in text_cols:
                text_cols.append(c)
    for c in text_cols:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str)
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
# ชั้นที่ 2 — ในโปรเจกต์ (เดินทางไปกับ git)
# ---------------------------------------------------------------------------

def _repo_save(name: str, blob: bytes) -> bool:
    try:
        REPO_DIR.mkdir(parents=True, exist_ok=True)
        (REPO_DIR / _fname(name)).write_bytes(blob)
        return True
    except Exception:
        return False


def _repo_load(name: str):
    p = REPO_DIR / _fname(name)
    if not p.exists():
        return None
    try:
        return p.read_bytes()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ชั้นที่ 3 — Google Drive (ไม่บังคับ)
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

def save(name: str, df: pd.DataFrame, extra: dict = None,
         to_repo: bool = False) -> dict:
    """
    เก็บตารางตัวเลขไว้ใช้ซ้ำ

    to_repo=True  เขียนลง data/snapshots/ ด้วย เพื่อให้ git พาไปถึงเว็บ
                  ใช้เมื่อรันบน MacBook เท่านั้น
                  เว็บไม่ควรเขียนชั้นนี้ เพราะเขียนแล้วก็หายตอนรีสตาร์ท
                  และเราไม่อยากให้เว็บไปแก้ไฟล์ที่อยู่ในการควบคุมของ git

    คืน dict บอกว่าเก็บสำเร็จที่ไหนบ้าง
    """
    if df is None or df.empty:
        return {"local": False, "repo": False, "drive": False}

    # จำไว้ว่าคอลัมน์ไหนเป็นข้อความ เพื่อคืนค่าว่างให้ถูกตอนอ่านกลับ (ดู _unpack)
    #
    # ต้องเช็กว่า "มีข้อความจริงอย่างน้อย 1 ช่อง" ไม่ใช่ดูแค่ dtype
    # เพราะคอลัมน์ตัวเลขที่ดึงไม่ได้เลยสักตัว (เช่น EV/EBITDA ของหุ้นไทย)
    # pandas จะให้ dtype เป็น object ทั้งที่ควรเป็นตัวเลข
    # ถ้าเหมาว่าเป็นข้อความ ค่าว่างจะกลายเป็น "" แล้วคำนวณต่อไม่ได้
    def _is_text(s):
        v = s.dropna()
        return len(v) > 0 and isinstance(v.iloc[0], str)

    text_cols = [c for c in df.columns if _is_text(df[c])]

    meta = {"ชื่อชุดข้อมูล": name,
            "บันทึกเมื่อ": _now(),
            "จำนวนแถว": int(len(df)),
            "คอลัมน์": list(df.columns),
            "คอลัมน์ข้อความ": text_cols}
    if extra:
        meta.update(extra)

    blob = _pack(df, meta)
    out = {"local": _local_save(name, blob),
           "repo": _repo_save(name, blob) if to_repo else False,
           "drive": _drive_save(name, blob),
           "ขนาด (KB)": round(len(blob) / 1024, 1)}
    return out


SOURCE_LABEL = {"local": "เครื่องนี้", "repo": "ในโปรเจกต์", "drive": "Google Drive"}


def load(name: str, max_age_hours: float = 24.0):
    """
    อ่านตารางที่เก็บไว้ — ดูทุกชั้นแล้วเลือก **อันที่ใหม่ที่สุด**

    คืน (df, meta) — meta มี "อายุ (ชม.)" และ "ที่มา"
    คืน (None, None) ถ้าไม่มีเลย หรือของที่ใหม่ที่สุดยังเก่าเกิน max_age_hours

    ทำไมต้องเลือกอันใหม่สุด ไม่ใช่ไล่ตามลำดับชั้น
    ------------------------------------------------
    ถ้าไล่ตามลำดับ (เครื่อง → โปรเจกต์ → Drive) จะเกิดกรณีนี้ :
      - อาจารย์คัดกรองบน Mac เมื่อวาน  -> เก็บในเครื่อง
      - วันนี้ push ของใหม่ขึ้น git      -> โปรเจกต์มีของใหม่กว่า
      - เปิดเว็บบน Mac                  -> เจอของในเครื่องก่อน เลยได้ของเมื่อวาน
    ผู้ใช้จะไม่มีทางรู้เลยว่ากำลังดูข้อมูลเก่า ซึ่งอันตรายกว่าการช้าไปนิดหน่อย
    """
    found = []
    for where, fn in (("local", _local_load), ("repo", _repo_load),
                      ("drive", _drive_load)):
        raw = fn(name)
        if not raw:
            continue
        try:
            df, meta = _unpack(raw)
        except Exception:
            continue
        found.append((_age_hours(meta.get("บันทึกเมื่อ", "")), where, df, meta, raw))

    if not found:
        return None, None

    found.sort(key=lambda x: x[0])                  # อายุน้อย = ใหม่ที่สุด
    age, where, df, meta, raw = found[0]
    if max_age_hours is not None and age > max_age_hours:
        return None, None

    meta["อายุ (ชม.)"] = round(age, 1)
    meta["ที่มา"] = where
    meta["ที่มา (ไทย)"] = SOURCE_LABEL.get(where, where)
    meta["พบทั้งหมด"] = [SOURCE_LABEL.get(w, w) for _, w, _, _, _ in found]
    if where != "local":
        _local_save(name, raw)                      # ดึงมาแล้วเก็บไว้ในเครื่องด้วย
    return df, meta


def info(name: str):
    """ดูข้อมูลของชุดที่เก็บไว้โดยไม่สนใจอายุ — ใช้บอกผู้ใช้ว่ามีของเก่าอยู่"""
    return load(name, max_age_hours=None)


# ---------------------------------------------------------------------------
# รวมผลหลายรอบให้ครบขึ้นเรื่อย ๆ
# ---------------------------------------------------------------------------

STAMP_COL = "ข้อมูล ณ"


def merge(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """
    รวมผลรอบใหม่เข้ากับรอบเก่า — ยึด "แถวที่ดึงสำเร็จ" เป็นหลัก

    ทำไมต้องรวม
    ------------
    ไม่มีรอบไหนดึงได้ครบ 100% เพราะ Yahoo ปฏิเสธคำขอเป็นครั้งคราว
    รอบหนึ่งอาจได้ 856/866 อีกรอบได้ 850/866 แต่ **ตัวที่พลาดไม่ใช่ตัวเดียวกัน**

    ถ้าเขียนทับกันตรง ๆ รอบที่ได้ 850 จะลบข้อมูลดี 6 ตัวของรอบก่อนทิ้ง
    ยิ่งดึงยิ่งอาจได้น้อยลง ซึ่งขัดกับสัญชาตญาณและทำให้ผู้ใช้ไม่ไว้ใจระบบ

    การรวมทำให้ความครบถ้วนมีแต่เพิ่มขึ้น ไม่มีวันลดลง

    กติกาตัดสินทีละ ticker
    -----------------------
    รอบใหม่สำเร็จ            -> ใช้รอบใหม่ (ข้อมูลสดกว่า)
    รอบใหม่พลาด รอบเก่าสำเร็จ -> ใช้รอบเก่า พร้อมทำเครื่องหมายว่าเป็นข้อมูลวันเก่า
    พลาดทั้งคู่               -> ใช้รอบใหม่ (ข้อความผิดพลาดที่ตรงกับสถานการณ์ล่าสุด)

    ยึด ticker ตามรอบใหม่เท่านั้น — ถ้าหุ้นถูกเพิกถอนไปแล้วจะไม่ค้างอยู่ในตาราง
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    new = new.copy()
    if STAMP_COL not in new.columns:
        new[STAMP_COL] = today

    if old is None or old.empty or "ticker" not in old.columns:
        return new

    old = old.copy()
    if STAMP_COL not in old.columns:
        # ไฟล์เก่าที่ยังไม่มีคอลัมน์นี้ — ใช้เวลาที่บันทึกไฟล์เป็นตัวแทน
        old[STAMP_COL] = old.attrs.get("บันทึกเมื่อ", "")[:10] or "ก่อนหน้านี้"

    new_ok = new["ปัญหา"].eq("") if "ปัญหา" in new.columns else pd.Series(True, index=new.index)
    old_ok = old["ปัญหา"].eq("") if "ปัญหา" in old.columns else pd.Series(True, index=old.index)

    # ตัวที่รอบใหม่พลาด แต่รอบเก่ามีของดี
    rescue = old[old_ok].set_index("ticker")
    need = set(new.loc[~new_ok, "ticker"]) & set(rescue.index)
    if not need:
        return new

    new = new.set_index("ticker")
    cols = [c for c in new.columns if c in rescue.columns]
    new.loc[list(need), cols] = rescue.loc[list(need), cols]
    return new.reset_index()


def merge_stats(df: pd.DataFrame) -> dict:
    """สรุปว่าตารางที่รวมแล้วมีข้อมูลของวันไหนบ้าง — ใช้บอกผู้ใช้ตามตรง"""
    if df is None or df.empty or STAMP_COL not in df.columns:
        return {}
    ok = df[df["ปัญหา"].eq("")] if "ปัญหา" in df.columns else df
    return {"สำเร็จ": int(len(ok)),
            "ทั้งหมด": int(len(df)),
            "แยกตามวัน": ok[STAMP_COL].value_counts().sort_index(ascending=False).to_dict()}


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
            print("  วิธีตั้งค่า : อ่านไฟล์ 19_ทางเลือก_Google_Drive.md\n")
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

    any_found = False
    for label, d in (("ในโปรเจกต์ (ขึ้น git · เว็บอ่านได้)", REPO_DIR),
                     ("ในเครื่องนี้ (ชั่วคราว)", LOCAL_DIR)):
        print(f"\n{label}")
        print(f"  {d}")
        files = sorted(d.glob("snap_*.csv.gz")) if d.exists() else []
        if not files:
            print("  (ว่าง)")
            continue
        any_found = True
        print(f"  {'ชุดข้อมูล':<30}{'แถว':>8}{'อายุ (ชม.)':>12}{'ขนาด (KB)':>12}")
        print("  " + "-" * 62)
        for f in files:
            try:
                _, meta = _unpack(f.read_bytes())
                print(f"  {meta.get('ชื่อชุดข้อมูล',''):<30}"
                      f"{meta.get('จำนวนแถว',0):>8,}"
                      f"{_age_hours(meta.get('บันทึกเมื่อ','')):>12.1f}"
                      f"{f.stat().st_size/1024:>12.1f}")
            except Exception as e:
                print(f"  {f.name:<30}  อ่านไม่ได้: {e}")

    print(f"\nGoogle Drive : {'ตั้งค่าแล้ว' if drive_ready() else 'ยังไม่ได้ตั้งค่า (ไม่บังคับ)'}")
    if not any_found:
        print("\n  ยังไม่มีข้อมูล — สร้างด้วย:")
        print("    python3 tools_snapshot_build.py --thai")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
