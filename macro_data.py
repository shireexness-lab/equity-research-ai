"""
macro_data.py — ชั้นดึงข้อมูลเศรษฐกิจ (Part 18: วัฏจักรเศรษฐกิจ)
================================================================
หน้าที่ : เป็น "ประตูเดียว" ที่ทุกส่วนของหน้าวัฏจักรเศรษฐกิจใช้ดึงข้อมูล
          เหมือนที่ data_layer.py เป็นประตูเดียวของหุ้นรายตัว

แหล่งข้อมูล 3 ทาง
-----------------
1. **FRED** (ธนาคารกลางสหรัฐ สาขาเซนต์หลุยส์) — ตัวเลขเศรษฐกิจจริง
   ใช้ได้ **โดยไม่ต้องมี API key** ผ่านทาง fredgraph.csv
   ถ้ามี key จะสลับไปใช้ทางการซึ่งเสถียรกว่าให้อัตโนมัติ

2. **yfinance** — ราคาตลาด (ดัชนี ETF ทองคำ ทองแดง ค่าเงิน)
   ไม่ต้องมี key ใช้ได้ทันที และอัปเดตทุกวันไม่ต้องรอตัวเลขราชการ

3. **ธปท. / SET** — ฝั่งไทย (จะเพิ่มในรอบ 2 เมื่อมี key ธปท.)
   รอบนี้ฝั่งไทยใช้ราคาตลาดล้วน (^SET.BK, THB=X) และระบุไว้ชัดว่าอ่านแบบเบา

กฎเหล็กที่ไฟล์นี้ต้องรักษา
--------------------------
**ห้ามคืนค่าเก่าเงียบ ๆ เด็ดขาด**

FRED เลิกอัปเดตชุดข้อมูลได้โดยไม่ประกาศ เคยเกิดมาแล้วกับ USSLIND
(หยุดตั้งแต่ ก.พ. 2020 แต่หน้าเว็บยังโหลดได้ปกติ) ถ้าเอาไปใช้ต่อโดยไม่ตรวจ
จะได้หน้าเว็บที่ดูเหมือนทำงานแต่ตัดสินใจจากข้อมูลเมื่อ 6 ปีที่แล้ว

ทุก series จึงมีค่า `stale` = จำนวนวันที่ยอมให้ข้อมูลเก่าได้
เกินกว่านั้นถือว่า "ตาย" → ตัดออกจากการโหวต + รายงานขึ้นหน้าเว็บ

**วิธีตั้งค่า stale — จุดที่เคยตั้งผิดมาแล้วครั้งหนึ่ง**
-------------------------------------------------------
ข้อมูลเศรษฐกิจติดวันที่ตาม **เดือนที่วัด** ไม่ใช่วันที่ประกาศ
ตัวเลข Core PCE ของเดือนมิถุนายนติดป้าย 2026-06-01 แต่ประกาศจริง 31 กรกฎาคม
และตัวของเดือนกรกฎาคมจะประกาศ 28 สิงหาคม

ดังนั้นวันที่ 21 สิงหาคม ข้อมูลรายเดือนที่ "สดที่สุดเท่าที่มีอยู่จริงบนโลก"
ย่อมมีอายุถึง ~81 วันเป็นเรื่องปกติ ไม่ได้ค้าง

ครั้งแรกตั้งไว้ที่ 70–75 วันเหมือนกับว่าวันที่บนข้อมูลคือวันประกาศ
ผลคือระบบตัด CFNAI (น้ำหนักสูงสุดในแกนการเติบโต) และ Core PCE
(ตัวที่เฟดใช้เป็นเป้าหมาย) ทิ้งทั้งที่ทั้งคู่ปกติดี

เกณฑ์ที่ถูกต้องจึงเป็นตามความถี่ของข้อมูล :
    รายวัน 12 · รายสัปดาห์ 24 · รายเดือน 105 · รายไตรมาส 250 วัน

ยังจับของตายได้อยู่ เพราะชุดที่ตายจริงจะค้างเป็น *ปี* ไม่ใช่เดือน
(USSLIND ค้างมาแล้วกว่า 2,300 วัน)

วิธีใช้จาก Terminal
-------------------
    python3 macro_data.py --test        # ทดสอบว่าดึงข้อมูลได้ครบไหม
    python3 macro_data.py --fetch       # ดึงจริงแล้วเก็บลงแคช
    python3 macro_data.py --list        # ดูรายชื่อตัวชี้วัดทั้งหมด
"""

from __future__ import annotations

import io
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:                                    # ไม่มี certifi ก็ยังไปต่อได้
    _SSL = ssl.create_default_context()

BASE_DIR = Path(__file__).resolve().parent
MACRO_DIR = BASE_DIR / "data" / "macro"
CACHE_DIR = MACRO_DIR / "cache"
MACRO_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


# ===========================================================================
# ทะเบียนตัวชี้วัด
#
# ตรวจสอบสถานะทุกตัวเมื่อ 21 สิงหาคม 2026 โดยเปิดหน้า FRED ทีละตัว
# ตัวที่ตายแล้วไม่ได้อยู่ในนี้ (USSLIND, THALOLITOAASTSAM, THACPIALLMINMEI,
# EA19LOLITOAASTSAM, CHNCPIALLMINMEI) — ดูรายละเอียดใน 25_วัฏจักรเศรษฐกิจ.md
#
# ความหมายของแต่ละช่อง
#   th    ชื่อไทยที่จะโชว์บนหน้าเว็บ
#   grp   ใช้ในกรอบไหน  growth / inflation / credit / fed
#   freq  ความถี่จริงของข้อมูล  D=วัน W=สัปดาห์ M=เดือน Q=ไตรมาส
#   stale จำนวนวันที่ยอมให้เก่าได้ ถ้าเกิน = ถือว่าตาย ตัดออกจากการโหวต
#   unit  หน่วยสำหรับแสดงผล
#   tf    วิธีแปลงเป็นตัวเลขที่ใช้เปรียบเทียบ (ดู transform() ข้างล่าง)
#   inv   True = ค่าสูงแปลว่าแย่ (ต้องกลับด้านก่อนรวมคะแนน)
# ===========================================================================
FRED_SERIES: dict[str, dict] = {
    # ---------------- แกนการเติบโต ----------------
    "CFNAIMA3": dict(th="ดัชนีกิจกรรมเศรษฐกิจสหรัฐ (เฉลี่ย 3 เดือน)",
                     grp="growth", freq="M", stale=105, unit="", tf="level", w=0.25),
    "PAYEMS": dict(th="การจ้างงานนอกภาคเกษตร",
                   grp="growth", freq="M", stale=105, unit="พันคน", tf="mom3_vs_12", w=0.15),
    "ICSA": dict(th="ผู้ขอรับสวัสดิการว่างงานรายใหม่",
                 grp="growth", freq="W", stale=24, unit="คน", tf="yoy", inv=True, w=0.10),
    "NEWORDER": dict(th="คำสั่งซื้อสินค้าทุนหลัก",
                     grp="growth", freq="M", stale=105, unit="ล้าน$", tf="yoy", w=0.15),
    "PERMIT": dict(th="ใบอนุญาตก่อสร้างที่อยู่อาศัย",
                   grp="growth", freq="M", stale=105, unit="พันหลัง", tf="yoy", w=0.10),
    "RSAFS": dict(th="ยอดค้าปลีก",
                  grp="growth", freq="M", stale=105, unit="ล้าน$", tf="yoy_real", w=0.10),
    "INDPRO": dict(th="ผลผลิตภาคอุตสาหกรรม",
                   grp="growth", freq="M", stale=105, unit="ดัชนี", tf="yoy", w=0.10),
    "UMCSENT": dict(th="ความเชื่อมั่นผู้บริโภค",
                    grp="growth", freq="M", stale=105, unit="ดัชนี", tf="yoy", w=0.05),
    "UNRATE": dict(th="อัตราว่างงาน",
                   grp="growth", freq="M", stale=105, unit="%", tf="level", inv=True, w=0.0),
    "SAHMREALTIME": dict(th="Sahm Rule (สัญญาณถดถอย)",
                         grp="growth", freq="M", stale=105, unit="จุด", tf="level", inv=True, w=0.0),

    # ---------------- แกนเงินเฟ้อ ----------------
    "CPILFESL": dict(th="เงินเฟ้อพื้นฐาน (Core CPI)",
                     grp="inflation", freq="M", stale=105, unit="%", tf="ann3", w=0.30),
    "PCEPILFE": dict(th="เงินเฟ้อพื้นฐาน PCE (เป้าหมายของเฟด)",
                     grp="inflation", freq="M", stale=105, unit="%", tf="yoy", w=0.25),
    "T5YIFR": dict(th="เงินเฟ้อคาดการณ์ 5 ปีข้างหน้าอีก 5 ปี",
                   grp="inflation", freq="D", stale=12, unit="%", tf="level", w=0.15),
    "PPIACO": dict(th="ดัชนีราคาผู้ผลิต",
                   grp="inflation", freq="M", stale=105, unit="ดัชนี", tf="yoy", w=0.15),
    "PCOPPUSDM": dict(th="ราคาทองแดงโลก",
                      grp="inflation", freq="M", stale=105, unit="$/ตัน", tf="chg6", w=0.10),
    "DCOILWTICO": dict(th="ราคาน้ำมันดิบ WTI",
                       grp="inflation", freq="D", stale=12, unit="$/บาร์เรล", tf="chg6", w=0.05),
    "CPIAUCSL": dict(th="เงินเฟ้อทั่วไป (CPI)",
                     grp="inflation", freq="M", stale=105, unit="ดัชนี", tf="yoy", w=0.0),

    # ---------------- วัฏจักรสินเชื่อ ----------------
    # BAA10Y เป็นตัวหลักแทน ICE BofA HY OAS เพราะตั้งแต่ เม.ย. 2026
    # FRED เหลือข้อมูล ICE ย้อนหลังแค่ 3 ปี ทำเปอร์เซ็นไทล์ 10 ปีไม่ได้
    "BAA10Y": dict(th="ส่วนต่างหุ้นกู้ Baa เหนือพันธบัตร 10 ปี",
                   grp="credit", freq="D", stale=12, unit="%", tf="level", inv=True),
    "NFCI": dict(th="ดัชนีภาวะการเงินชิคาโก",
                 grp="credit", freq="W", stale=24, unit="", tf="level", inv=True),
    "ANFCI": dict(th="ดัชนีภาวะการเงินชิคาโก (ปรับผลเศรษฐกิจ)",
                  grp="credit", freq="W", stale=24, unit="", tf="level", inv=True),
    "STLFSI4": dict(th="ดัชนีความตึงเครียดการเงินเซนต์หลุยส์",
                    grp="credit", freq="W", stale=24, unit="", tf="level", inv=True),
    "DRTSCILM": dict(th="% ธนาคารที่เข้มงวดการปล่อยกู้ธุรกิจ",
                     grp="credit", freq="Q", stale=250, unit="%", tf="level", inv=True),
    "BAMLH0A0HYM2": dict(th="ส่วนต่างหุ้นกู้ผลตอบแทนสูง (ย้อนหลังแค่ 3 ปี)",
                         grp="credit", freq="D", stale=12, unit="%", tf="level",
                         inv=True, short_history=True),

    # ---------------- วัฏจักรเฟดและสภาพคล่อง ----------------
    "FEDFUNDS": dict(th="อัตราดอกเบี้ยนโยบายสหรัฐ",
                     grp="fed", freq="M", stale=105, unit="%", tf="level"),
    "REAINTRATREARAT10Y": dict(th="ดอกเบี้ยแท้จริง 10 ปี",
                               grp="fed", freq="M", stale=105, unit="%", tf="level"),
    "T10Y3M": dict(th="เส้นอัตราผลตอบแทน 10 ปี − 3 เดือน",
                   grp="fed", freq="D", stale=12, unit="%", tf="level"),
    "T10Y2Y": dict(th="เส้นอัตราผลตอบแทน 10 ปี − 2 ปี",
                   grp="fed", freq="D", stale=12, unit="%", tf="level"),
    "WALCL": dict(th="ขนาดงบดุลเฟด",
                  grp="fed", freq="W", stale=24, unit="ล้าน$", tf="level"),
    "RRPONTSYD": dict(th="เงินฝากย้อนกลับข้ามคืน",
                      grp="fed", freq="D", stale=12, unit="พันล้าน$", tf="level"),
    "WTREGEN": dict(th="บัญชีเงินคงคลังสหรัฐ",
                    grp="fed", freq="W", stale=24, unit="ล้าน$", tf="level"),
    "DTB3": dict(th="ดอกเบี้ยตั๋วเงินคลัง 3 เดือน",
                 grp="fed", freq="D", stale=12, unit="%", tf="level"),

    # ---------------- จีน / ยุโรป (อ่านแบบเบา) ----------------
    "CHNLOLITOAASTSAM": dict(th="ดัชนีชี้นำเศรษฐกิจจีน (OECD)",
                             grp="world", freq="M", stale=140, unit="ดัชนี", tf="level"),
    "ECBDFR": dict(th="ดอกเบี้ยนโยบาย ECB",
                   grp="world", freq="D", stale=12, unit="%", tf="level"),
    "CP0000EZ19M086NEST": dict(th="เงินเฟ้อยูโรโซน (HICP)",
                               grp="world", freq="M", stale=105, unit="ดัชนี", tf="yoy"),
}

# ---------------------------------------------------------------------------
# ราคาตลาด — ไม่ต้องมี key ใด ๆ และอัปเดตทุกวัน
# ใช้เป็นกรอบที่ 5 "ตลาดบอกเอง" ซึ่งเร็วกว่าตัวเลขราชการ 1-2 เดือน
# ---------------------------------------------------------------------------
MARKET_SYMBOLS: dict[str, dict] = {
    "^GSPC": dict(th="ดัชนี S&P 500", grp="us"),
    "SPY":   dict(th="กองทุน S&P 500", grp="us"),
    "RSP":   dict(th="S&P 500 แบบเท่าน้ำหนัก", grp="us"),
    "XLU":   dict(th="กลุ่มสาธารณูปโภค", grp="us"),
    "XLK":   dict(th="กลุ่มเทคโนโลยี", grp="us"),
    "XLP":   dict(th="กลุ่มสินค้าจำเป็น", grp="us"),
    "XLY":   dict(th="กลุ่มสินค้าฟุ่มเฟือย", grp="us"),
    "XLE":   dict(th="กลุ่มพลังงาน", grp="us"),
    "XLF":   dict(th="กลุ่มการเงิน", grp="us"),
    "HYG":   dict(th="กองทุนหุ้นกู้ผลตอบแทนสูง", grp="us"),
    "IEF":   dict(th="พันธบัตรรัฐบาล 7-10 ปี", grp="us"),
    "TLT":   dict(th="พันธบัตรรัฐบาล 20 ปีขึ้นไป", grp="us"),
    "^VIX":  dict(th="ดัชนีความผันผวน", grp="us"),
    "GC=F":  dict(th="ทองคำล่วงหน้า", grp="commodity"),
    "HG=F":  dict(th="ทองแดงล่วงหน้า", grp="commodity"),
    "CL=F":  dict(th="น้ำมันดิบล่วงหน้า", grp="commodity"),
    "^SET.BK": dict(th="ดัชนี SET", grp="thai"),
    "THB=X": dict(th="อัตราแลกเปลี่ยน USD/THB", grp="thai"),
    "FXI":   dict(th="กองทุนหุ้นจีน", grp="world"),
    "EZU":   dict(th="กองทุนหุ้นยูโรโซน", grp="world"),
}


# ===========================================================================
# ส่วนที่ 1 — ดึงข้อมูลจาก FRED
# ===========================================================================
def _fred_key() -> str | None:
    """
    หา API key ของ FRED จาก 3 ที่ ตามลำดับความสำคัญ

    ไม่มี key ก็ใช้งานได้ปกติ — แค่เปลี่ยนไปใช้ทาง fredgraph.csv แทน
    (ช้ากว่าเล็กน้อยและไม่มีข้อมูลกำกับ แต่ตัวเลขชุดเดียวกันเป๊ะ)
    """
    key = os.environ.get("FRED_API_KEY")
    if key:
        return key.strip()
    try:                                   # เวลารันบน Streamlit
        import streamlit as st
        return str(st.secrets["FRED_API_KEY"]).strip()
    except Exception:
        pass
    kf = BASE_DIR / ".fred_key"            # ไฟล์ธรรมดาบนเครื่องตัวเอง
    if kf.exists():
        t = kf.read_text(encoding="utf-8").strip()
        if t:
            return t
    return None


# ---------------------------------------------------------------------------
# หัวคำขอแบบเบราว์เซอร์เต็มรูปแบบ
#
# ครั้งแรกที่ทดสอบจริงบนเครื่องผู้ใช้ ทุกชุดขึ้น "read operation timed out"
# ทั้งที่เชื่อมต่อได้ — อาการแบบนี้คือเซิร์ฟเวอร์รับคำขอแล้วไม่ยอมส่งข้อมูลกลับ
# ซึ่งเกิดกับคำขอที่ "ไม่เหมือนเบราว์เซอร์จริง" (มีแต่ User-Agent อย่างเดียว)
# จึงต้องส่งหัวคำขอให้ครบชุดเหมือนเบราว์เซอร์เปิดหน้าเว็บจริง ๆ
# ---------------------------------------------------------------------------
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/csv,text/plain,application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Referer": "https://fred.stlouisfed.org/",
    "Cache-Control": "no-cache",
}

# จำไว้ว่าวิธีไหนใช้ได้ เพื่อรายงานให้ผู้ใช้เห็นและใช้วิธีนั้นก่อนในครั้งถัดไป
_WORKING_METHOD: str | None = None
_WORKING_TRANSPORT: str | None = None


def _t_requests(url: str, timeout: int) -> bytes:
    """ไลบรารี requests — จัดการ gzip · redirect · cookie ให้เอง"""
    import requests
    r = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.content


def _t_urllib(url: str, timeout: int) -> bytes:
    """urllib ที่ติดมากับ Python — ตาข่ายรองรับ ไม่ต้องลงอะไรเพิ่ม"""
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding", "") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    return raw


def _t_curl(url: str, timeout: int) -> bytes:
    """
    curl ของระบบปฏิบัติการ — **ตัวช่วยที่สำคัญที่สุดเมื่อโดนระบบกันบอท**

    ทำไมถึงได้ผลในเมื่อ requests กับ urllib ไม่ได้ผล
    -----------------------------------------------
    เว็บใหญ่ ๆ ไม่ได้ดูแค่หัวคำขอ แต่ดู "ลายนิ้วมือ TLS" ด้วย
    คือลำดับและชนิดของรหัสลับที่โปรแกรมเสนอตอนเริ่มเชื่อมต่อ
    ซึ่งของ Python (OpenSSL) ต่างจากเบราว์เซอร์อย่างเห็นได้ชัด
    ระบบกันบอทจึงจำได้และตัดสายทิ้งเงียบ ๆ แบบไม่ตอบอะไรเลย

    curl บน macOS ใช้คนละระบบเข้ารหัสกับ Python ลายนิ้วมือจึงต่างกัน
    และ curl มีติดมากับ macOS ทุกเครื่องอยู่แล้ว ไม่ต้องติดตั้งอะไร
    """
    import subprocess
    cmd = ["curl", "-sS", "-L", "--compressed", "--max-time", str(timeout)]
    for k, v in BROWSER_HEADERS.items():
        if k != "Accept-Encoding":          # --compressed จัดการให้แล้ว
            cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    if p.returncode != 0:
        raise RuntimeError((p.stderr.decode("utf-8", "replace").strip()
                            or f"curl จบด้วยรหัส {p.returncode}")[:120])
    if not p.stdout:
        raise RuntimeError("curl ได้ข้อมูลเปล่า")
    return p.stdout


TRANSPORTS = [("requests", _t_requests), ("urllib", _t_urllib), ("curl", _t_curl)]


def _http(url: str, timeout: int = 25, tries: int = 2) -> tuple[bytes, str]:
    """
    เปิด URL แล้วคืน (เนื้อหา, ชื่อวิธีที่ใช้ได้)

    ลอง 3 วิธีเรียงกัน เพราะแต่ละวิธีมีจุดอ่อนคนละแบบ
    และ **จำไว้ว่าวิธีไหนใช้ได้** เพื่อเอาวิธีนั้นขึ้นมาลองก่อนในครั้งถัดไป
    ไม่งั้นจะเสียเวลารอวิธีที่รู้อยู่แล้วว่าไม่ได้ผล ชุดละหลายสิบวินาที
    """
    global _WORKING_TRANSPORT
    order = list(TRANSPORTS)
    if _WORKING_TRANSPORT:
        order.sort(key=lambda t: t[0] != _WORKING_TRANSPORT)

    errs: list[str] = []
    for attempt in range(tries):
        for name, fn in order:
            try:
                raw = fn(url, timeout)
                if raw:
                    _WORKING_TRANSPORT = name
                    return raw, name
                errs.append(f"{name}: ได้ข้อมูลเปล่า")
            except ImportError:
                errs.append(f"{name}: ยังไม่ได้ติดตั้ง")
            except Exception as e:                            # noqa: BLE001
                errs.append(f"{name}: {type(e).__name__}: {str(e)[:80]}")
        if attempt < tries - 1:
            time.sleep(2.0 * (attempt + 1))

    raise RuntimeError(" | ".join(errs[-3:]))


def _parse_fred_csv(text: str, sid: str) -> pd.Series:
    """แปลงไฟล์ CSV ของ FRED เป็น Series"""
    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2:
        raise ValueError("รูปแบบ CSV ไม่ถูกต้อง")
    # หัวคอลัมน์วันที่เคยชื่อ DATE แล้วเปลี่ยนเป็น observation_date
    # จึงอ้างด้วยตำแหน่งแทนชื่อ เพื่อไม่ให้พังอีกถ้าเขาเปลี่ยนชื่ออีกรอบ
    return pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").to_numpy(),
                     index=pd.to_datetime(df.iloc[:, 0]), name=sid)


def _parse_fred_txt(text: str, sid: str) -> pd.Series:
    """
    แปลงไฟล์ข้อความของ FRED (https://fred.stlouisfed.org/data/XXX.txt)

    รูปแบบไฟล์ : บล็อกข้อมูลกำกับด้านบน แล้วตามด้วยตารางที่ขึ้นต้นด้วยคำว่า DATE

        Title:               Chicago Fed National Activity Index
        Series ID:           CFNAI
        ...

        DATE          VALUE
        1967-03-01    -0.12
    """
    dates, vals, started = [], [], False
    for line in text.splitlines():
        p = line.split()
        if not p:
            continue
        if not started:
            if p[0].upper() == "DATE":
                started = True
            continue
        if len(p) < 2:
            continue
        try:
            d = pd.Timestamp(p[0])
        except Exception:                                     # noqa: BLE001
            continue
        dates.append(d)
        vals.append(pd.to_numeric(p[1], errors="coerce"))
    if not dates:
        raise ValueError("ไม่พบตารางข้อมูลในไฟล์ข้อความ")
    return pd.Series(vals, index=pd.DatetimeIndex(dates), name=sid)


def fred_series(sid: str, timeout: int = 45) -> pd.Series:
    """
    ดึงข้อมูล 1 ชุดจาก FRED คืนเป็น pandas Series (index = วันที่)

    ลองหลายช่องทางเรียงกันจนกว่าจะได้ เพราะ FRED ปิดหรือหน่วงบางช่องทาง
    เป็นช่วง ๆ โดยไม่ประกาศ การมีทางสำรองจึงไม่ใช่ความหรูหรา แต่จำเป็น

      1. API ทางการ      ต้องมี key · เสถียรที่สุด · ควรใช้ถ้ามี
      2. fredgraph.csv   ไม่ต้องมี key · ช่องทางที่คนใช้กันทั่วไป
      3. data/XXX.txt    ไม่ต้องมี key · ช่องทางสำรอง คนละระบบกับข้อ 2
    """
    global _WORKING_METHOD
    key = _fred_key()
    routes: list[tuple[str, str, str]] = []

    if key:
        routes.append((
            "API ทางการ",
            "https://api.stlouisfed.org/fred/series/observations?"
            + urllib.parse.urlencode({"series_id": sid, "api_key": key,
                                      "file_type": "json"}),
            "json"))
    routes += [
        ("fredgraph.csv", f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", "csv"),
        ("data/txt", f"https://fred.stlouisfed.org/data/{sid}.txt", "txt"),
    ]

    # ถ้าเคยรู้แล้วว่าช่องทางไหนใช้ได้ ให้ลองช่องทางนั้นก่อน จะได้ไม่เสียเวลารอ
    if _WORKING_METHOD:
        routes.sort(key=lambda r: r[0] != _WORKING_METHOD)

    errs = []
    for name, url, kind in routes:
        try:
            raw, how = _http(url, timeout=timeout)
            text = raw.decode("utf-8", errors="replace")
            if kind == "json":
                obs = json.loads(text).get("observations", [])
                if not obs:
                    raise ValueError("API ไม่คืนข้อมูล")
                s = pd.Series(pd.to_numeric([o["value"] for o in obs], errors="coerce"),
                              index=pd.to_datetime([o["date"] for o in obs]), name=sid)
            elif kind == "csv":
                s = _parse_fred_csv(text, sid)
            else:
                s = _parse_fred_txt(text, sid)

            s = s[~s.index.duplicated(keep="last")].sort_index().dropna()
            if s.empty:
                raise ValueError("ได้ข้อมูลแต่ว่างเปล่า")
            _WORKING_METHOD = name
            return s
        except Exception as e:                                # noqa: BLE001
            errs.append(f"[{name}] {str(e)[:110]}")

    raise RuntimeError(" || ".join(errs))


# ===========================================================================
# ส่วนที่ 2 — ดึงราคาตลาดจาก yfinance
# ===========================================================================
def market_prices(symbols: list[str] | None = None,
                  period: str = "12y") -> pd.DataFrame:
    """
    ราคาปิดย้อนหลังของทุกสัญลักษณ์ในคราวเดียว

    ดึงรวดเดียวด้วย yf.download เพราะยิงทีละตัวจะโดน Yahoo จำกัดจำนวนคำขอ
    """
    import yfinance as yf

    syms = list(symbols or MARKET_SYMBOLS.keys())
    df = yf.download(syms, period=period, interval="1d",
                     auto_adjust=True, progress=False, threads=True)

    # yfinance คืนคอลัมน์ 2 ชั้นเมื่อขอหลายตัว และชั้นเดียวเมื่อขอตัวเดียว
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"] if "Close" in df.columns.get_level_values(0) else df
    else:
        close = df[["Close"]].rename(columns={"Close": syms[0]})

    close = close.dropna(how="all").sort_index()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


# ===========================================================================
# ส่วนที่ 3 — ตรวจว่าข้อมูล "ยังมีชีวิต" ไหม
# ===========================================================================
def check_fresh(sid: str, s: pd.Series, meta: dict) -> dict:
    """
    ตรวจว่าข้อมูลชุดนี้ยังอัปเดตอยู่ไหม

    คืน dict ที่บอก : ใช้ได้ไหม · ข้อมูลล่าสุดวันไหน · เก่ากี่วัน · เหตุผล

    **หัวใจของไฟล์นี้** — FRED เลิกอัปเดตชุดข้อมูลเงียบ ๆ ได้
    ถ้าไม่ตรวจตรงนี้ หน้าเว็บจะตัดสินใจจากตัวเลขที่ตายไปแล้วโดยไม่มีใครรู้
    """
    last = s.index[-1]
    age = (pd.Timestamp.now().normalize() - last.normalize()).days
    limit = int(meta.get("stale", 90))
    ok = age <= limit
    return {
        "series": sid,
        "ชื่อ": meta.get("th", sid),
        "ใช้ได้": ok,
        "ข้อมูลล่าสุด": last.date().isoformat(),
        "เก่ากี่วัน": age,
        "เกณฑ์วัน": limit,
        "จำนวนจุด": int(s.size),
        "เหตุผล": "" if ok else f"ข้อมูลค้างที่ {last.date()} ({age} วัน) เกินเกณฑ์ {limit} วัน",
    }


# ===========================================================================
# ส่วนที่ 4 — แปลงข้อมูลดิบเป็นตัวเลขที่เปรียบเทียบกันได้
# ===========================================================================
def _to_monthly(s: pd.Series) -> pd.Series:
    """
    ยุบทุกความถี่ให้เป็นรายเดือน (ค่าสุดท้ายของเดือน)

    จำเป็นเพราะตัวชี้วัดมีความถี่ต่างกันหมด — รายวัน รายสัปดาห์ รายเดือน
    รายไตรมาส ถ้าไม่ยุบให้เท่ากันก่อน จะเอามาบวกกันไม่ได้เลย
    """
    return s.resample("ME").last().dropna()


def transform(s: pd.Series, how: str, deflator: pd.Series | None = None) -> pd.Series:
    """
    แปลงอนุกรมดิบเป็นรูปที่ใช้ตัดสิน

    level        ใช้ค่าตรง ๆ (เช่น อัตราดอกเบี้ย ส่วนต่าง ดัชนี CFNAI)
    yoy          % เปลี่ยนแปลงเทียบปีก่อน
    yoy_real     % เปลี่ยนแปลงเทียบปีก่อน หลังหักเงินเฟ้อ (ใช้กับยอดค้าปลีก)
    ann3         อัตรารายปีที่คำนวณจาก 3 เดือนล่าสุด — จับการเปลี่ยนทิศได้เร็วกว่า YoY
    mom3_vs_12   ค่าเฉลี่ยการเปลี่ยนแปลง 3 เดือน เทียบ 12 เดือน (ใช้กับการจ้างงาน)
    chg6         % เปลี่ยนแปลง 6 เดือน (ใช้กับราคาสินค้าโภคภัณฑ์)
    """
    m = _to_monthly(s)
    if how == "level":
        return m
    if how == "yoy":
        return m.pct_change(12, fill_method=None) * 100
    if how == "yoy_real":
        r = m.pct_change(12, fill_method=None) * 100
        if deflator is not None and not deflator.empty:
            d = _to_monthly(deflator).pct_change(12, fill_method=None) * 100
            r = (r - d.reindex(r.index).ffill()).dropna()
        return r
    if how == "ann3":
        # ((ค่าเดือนนี้ / ค่า 3 เดือนก่อน) ^ 4 - 1) x 100
        return ((m / m.shift(3)) ** 4 - 1) * 100
    if how == "mom3_vs_12":
        d = m.diff()
        return d.rolling(3).mean() - d.rolling(12).mean()
    if how == "chg6":
        return m.pct_change(6, fill_method=None) * 100
    raise ValueError(f"ไม่รู้จักวิธีแปลง: {how}")


def zscore(s: pd.Series, years: int = 10) -> pd.Series:
    """
    แปลงเป็น z-score เทียบกับตัวเองย้อนหลัง N ปี

    ทำไมต้องใช้ z-score : ตัวชี้วัดแต่ละตัวหน่วยต่างกันสิ้นเชิง
    (คน · % · ดัชนี · ดอลลาร์) เอามาบวกกันตรง ๆ ไม่ได้
    z-score แปลงทุกตัวเป็นภาษาเดียวกันคือ "ห่างจากค่าปกติของตัวเองกี่เท่าของความผันผวน"

    ใช้หน้าต่างเลื่อน ไม่ใช่ค่าเฉลี่ยทั้งชุด เพราะถ้าใช้ทั้งชุด
    ค่าในอดีตจะถูกคำนวณด้วยข้อมูลอนาคต = backtest ได้ผลดีเกินจริง
    """
    win = max(24, years * 12)
    mu = s.rolling(win, min_periods=max(12, win // 3)).mean()
    sd = s.rolling(win, min_periods=max(12, win // 3)).std()
    z = (s - mu) / sd.replace(0, np.nan)
    return z.clip(-3, 3)                  # ตัดหางไม่ให้ค่าสุดโต่งค่าเดียวครอบงำ


# ===========================================================================
# ส่วนที่ 5 — ดึงทุกอย่างในคราวเดียว + แคช
# ===========================================================================
CACHE_FILE = CACHE_DIR / "macro_raw.pkl"


def fetch_all(use_cache: bool = True, max_age_hours: float = 12.0,
              verbose: bool = False) -> dict:
    """
    ดึงข้อมูลทั้งหมดที่หน้าวัฏจักรเศรษฐกิจต้องใช้

    คืน dict :
        fred     {series_id: pd.Series}   เฉพาะตัวที่ดึงสำเร็จ
        market   pd.DataFrame             ราคาปิดย้อนหลัง
        health   [dict, ...]              รายงานสุขภาพข้อมูลทุกตัว
        dead     [series_id, ...]         ตัวที่ตายหรือดึงไม่ได้ → ห้ามใช้โหวต
        เวลาที่ดึง

    แคชไว้ 12 ชม. เพราะตัวเลขเศรษฐกิจออกเดือนละครั้ง
    ดึงถี่กว่านั้นคือเปลืองเปล่าและเสี่ยงโดน Yahoo บล็อก
    """
    if use_cache and CACHE_FILE.exists():
        try:
            cached = pd.read_pickle(CACHE_FILE)
            got = cached.get("เวลาที่ดึง")
            if got:
                age = (datetime.now(timezone.utc)
                       - datetime.fromisoformat(got)).total_seconds() / 3600
                if age < max_age_hours:
                    cached["จากแคช"] = True
                    cached["อายุแคชชั่วโมง"] = round(age, 1)
                    return cached
        except Exception:                                # แคชเสียก็ดึงใหม่
            pass

    fred: dict[str, pd.Series] = {}
    health: list[dict] = []
    dead: list[str] = []
    fail_streak = 0
    aborted = False

    for sid, meta in FRED_SERIES.items():
        # ตัวตัดวงจร — ถ้า 3 ชุดแรกล้มเหลวติดกัน แปลว่าเข้า FRED ไม่ได้เลย
        # ไม่ใช่ปัญหาของข้อมูลตัวใดตัวหนึ่ง การไล่ยิงต่ออีก 30 ชุด
        # จะกินเวลาหลายสิบนาทีโดยไม่ได้อะไรเพิ่ม จึงหยุดแล้วรายงานทันที
        if fail_streak >= 3:
            aborted = True
            if verbose:
                print("  ⏹  หยุดกลางคัน — 3 ชุดแรกล้มเหลวติดกัน "
                      "แปลว่าเข้า FRED ไม่ได้เลย ไม่ใช่ปัญหาของข้อมูลตัวใดตัวหนึ่ง")
            break
        try:
            s = fred_series(sid)
            h = check_fresh(sid, s, meta)
            fred[sid] = s
            health.append(h)
            fail_streak = 0
            if not h["ใช้ได้"]:
                dead.append(sid)
            if verbose:
                mark = "✓" if h["ใช้ได้"] else "✗"
                print(f"  {mark} {sid:22} {h['ข้อมูลล่าสุด']}  n={h['จำนวนจุด']:>6}  "
                      f"{h['เหตุผล']}", flush=True)
        except Exception as e:                            # noqa: BLE001
            dead.append(sid)
            fail_streak += 1
            health.append({"series": sid, "ชื่อ": meta.get("th", sid),
                           "ใช้ได้": False, "ข้อมูลล่าสุด": "-", "เก่ากี่วัน": None,
                           "เกณฑ์วัน": meta.get("stale"), "จำนวนจุด": 0,
                           "เหตุผล": f"ดึงไม่สำเร็จ: {e}"})
            if verbose:
                print(f"  ✗ {sid:22} ดึงไม่สำเร็จ — {e}", flush=True)
        time.sleep(0.15)                                  # ถนอม FRED ไม่ยิงรัว

    try:
        mkt = market_prices()
    except Exception as e:                                # noqa: BLE001
        mkt = pd.DataFrame()
        health.append({"series": "ราคาตลาด", "ชื่อ": "ราคาตลาดจาก Yahoo",
                       "ใช้ได้": False, "ข้อมูลล่าสุด": "-", "เก่ากี่วัน": None,
                       "เกณฑ์วัน": 7, "จำนวนจุด": 0,
                       "เหตุผล": f"ดึงไม่สำเร็จ: {e}"})

    out = {"fred": fred, "market": mkt, "health": health, "dead": dead,
           "เวลาที่ดึง": datetime.now(timezone.utc).isoformat(),
           "มี_fred_key": _fred_key() is not None, "จากแคช": False,
           "ช่องทางที่ใช้ได้": _WORKING_METHOD, "หยุดกลางคัน": aborted}
    try:
        pd.to_pickle(out, CACHE_FILE)
    except Exception:
        pass
    return out


def health_frame(health: list[dict]) -> pd.DataFrame:
    """แปลงรายงานสุขภาพข้อมูลเป็นตารางสำหรับแสดงบนหน้าเว็บ"""
    if not health:
        return pd.DataFrame()
    df = pd.DataFrame(health)
    df["สถานะ"] = np.where(df["ใช้ได้"], "🟢 ใช้ได้", "🔴 ตัดออก")
    cols = ["สถานะ", "ชื่อ", "series", "ข้อมูลล่าสุด", "เก่ากี่วัน",
            "เกณฑ์วัน", "จำนวนจุด", "เหตุผล"]
    return df[[c for c in cols if c in df.columns]]


# ===========================================================================
# ส่วนที่ 6 — รันจาก Terminal เพื่อทดสอบ
# ===========================================================================
def diagnose() -> int:
    """
    ตรวจว่าเข้าแหล่งข้อมูลไหนได้บ้าง — ใช้เมื่อ --test ล้มเหลว

    ทดสอบทีละชั้น เพื่อแยกให้ออกว่าปัญหาอยู่ที่ไหน
      · เน็ตทั้งหมดใช้ไม่ได้     → ทุกอย่างล้ม
      · เน็ตดีแต่ FRED ปิดกั้น   → Yahoo ผ่าน แต่ FRED ล้ม
      · แค่บางช่องทางของ FRED   → บางแถวผ่าน บางแถวล้ม
    """
    print("=" * 68)
    print("ตรวจหาสาเหตุที่ดึงข้อมูลไม่ได้")
    print("=" * 68)

    targets = [
        ("เน็ตใช้ได้ไหม (ทดสอบกับ Yahoo)",
         "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=5d&interval=1d"),
        ("FRED หน้าเว็บธรรมดา", "https://fred.stlouisfed.org/series/CFNAI"),
        ("FRED ช่องทาง 1 — fredgraph.csv",
         "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CFNAI"),
        ("FRED ช่องทาง 2 — data/txt",
         "https://fred.stlouisfed.org/data/CFNAI.txt"),
    ]
    if _fred_key():
        targets.append(("FRED ช่องทาง 3 — API ทางการ",
                        "https://api.stlouisfed.org/fred/series/observations?"
                        + urllib.parse.urlencode(
                            {"series_id": "CFNAI", "api_key": _fred_key(),
                             "file_type": "json", "limit": "5"})))

    # แยกให้ชัดระหว่าง "ติดต่อเซิร์ฟเวอร์ไม่ได้" กับ "ติดต่อได้แต่เขาไม่ให้ข้อมูล"
    # สองอย่างนี้แก้คนละทางกันสิ้นเชิง การรวมเป็นอย่างเดียวทำให้วินิจฉัยผิด
    got_data: list[str] = []
    reached: list[str] = []          # ตอบกลับมา แม้จะเป็นรหัสข้อผิดพลาด
    blocked: list[str] = []          # ตัดสายเงียบ หรือหมดเวลารอ

    for name, url in targets:
        print(f"\n  {name}")
        best = None
        for tname, fn in TRANSPORTS:
            t0 = time.time()
            try:
                raw = fn(url, 20)
                print(f"      ✓ {tname:9} ได้ {len(raw):,} ไบต์ ใน {time.time()-t0:.1f} วิ")
                best = best or "data"
            except Exception as e:                            # noqa: BLE001
                msg = f"{type(e).__name__}: {str(e)[:95]}"
                # เฉพาะ HTTPError เท่านั้นที่แปลว่า "เซิร์ฟเวอร์ปลายทางตอบกลับมาแล้ว"
                # ส่วน URLError / ProxyError / Timeout คือไปไม่ถึงปลายทางด้วยซ้ำ
                # (เคยเขียนเป็นการค้นหาตัวเลขในข้อความ ซึ่งจับผิดเพราะรหัส 403
                #  ของพร็อกซีระหว่างทางก็เข้าเงื่อนไขด้วย)
                hit = type(e).__name__ == "HTTPError"
                mark = "◐" if hit else "✗"
                print(f"      {mark} {tname:9} {msg}")
                if hit and best != "data":
                    best = "reached"
        (got_data if best == "data" else
         reached if best == "reached" else blocked).append(name)

    print()
    print("-" * 68)
    print("สรุป")
    if got_data:
        print("  ใช้งานได้จริง : " + " · ".join(got_data))
    if reached:
        print("  ติดต่อได้แต่ถูกปฏิเสธ : " + " · ".join(reached))
    if blocked:
        print("  ถูกตัดสาย/หมดเวลารอ : " + " · ".join(blocked))
    print()

    fred_ok = any("FRED" in n for n in got_data)
    net_ok = bool(got_data or reached)

    if not net_ok:
        print("  → ออกอินเทอร์เน็ตจากโปรแกรมไม่ได้เลย")
        print("    มักเป็นเพราะ VPN · ไฟร์วอลล์ · หรือพร็อกซีของเครือข่ายที่ใช้อยู่")
        print("    ลองปิด VPN แล้วรันใหม่ หรือสลับไปใช้เน็ตมือถือดู")
    elif not fred_ok:
        print("  → เน็ตใช้ได้ แต่ FRED ไม่ยอมส่งข้อมูลให้")
        print("    ทางแก้ที่ได้ผลแน่นอนที่สุดคือสมัคร FRED API key (ฟรี ใช้เวลา 2 นาที)")
        print("    เพราะ key จะทำให้ไปใช้เซิร์ฟเวอร์คนละตัว (api.stlouisfed.org)")
        print("    ซึ่งเป็นช่องทางสำหรับโปรแกรมโดยเฉพาะ ไม่มีระบบกันบอทขวางอยู่")
    else:
        print("  → FRED ใช้งานได้ รันคำสั่งนี้ต่อได้เลย :")
        print("    python3 macro_data.py --test")
    print("-" * 68)
    print("ส่งผลทั้งหมดนี้ให้ผู้ช่วยดูได้เลย")
    return 0


def set_key(key: str) -> int:
    """
    เก็บ FRED API key ลงเครื่อง — และกันไม่ให้หลุดขึ้น GitHub

    เรื่องที่ต้องระวังที่สุด : repo ของโปรเจกต์นี้เป็นสาธารณะ
    ถ้า key ถูก commit ขึ้นไป ใครก็เอาไปใช้ได้ และการลบทีหลังไม่ช่วย
    เพราะประวัติ git ยังเก็บไว้ ฟังก์ชันนี้จึงเติม .gitignore ให้อัตโนมัติ
    ก่อนเขียนไฟล์ key ลงไป ไม่ใช่หลังจากนั้น
    """
    key = key.strip()
    if len(key) < 20:
        print("❌ key สั้นผิดปกติ — ของ FRED ยาว 32 ตัวอักษร ลองคัดลอกมาใหม่")
        return 1

    gi = BASE_DIR / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    if ".fred_key" not in [ln.strip() for ln in lines]:
        with gi.open("a", encoding="utf-8") as f:
            f.write("\n# กุญแจ FRED — ห้ามขึ้น GitHub เด็ดขาด (repo นี้เป็นสาธารณะ)\n")
            f.write(".fred_key\n")
        print("✓ เพิ่ม .fred_key เข้า .gitignore แล้ว — จะไม่ถูกอัปขึ้น GitHub")

    kf = BASE_DIR / ".fred_key"
    kf.write_text(key + "\n", encoding="utf-8")
    try:
        kf.chmod(0o600)                       # ให้เจ้าของเครื่องอ่านได้คนเดียว
    except Exception:                                         # noqa: BLE001
        pass
    print(f"✓ เก็บ key ไว้ที่ {kf.name} เรียบร้อย")
    print("\nทดสอบต่อด้วย :  python3 macro_data.py --diag")
    return 0


def _cli() -> int:
    import argparse
    p = argparse.ArgumentParser(description="ชั้นดึงข้อมูลเศรษฐกิจ")
    p.add_argument("--setkey", metavar="KEY",
                   help="ใส่ FRED API key (จะกันไม่ให้หลุดขึ้น GitHub ให้เอง)")
    p.add_argument("--test", action="store_true", help="ทดสอบว่าดึงได้ครบไหม")
    p.add_argument("--fetch", action="store_true", help="ดึงจริงแล้วเก็บลงแคช")
    p.add_argument("--list", action="store_true", help="ดูรายชื่อตัวชี้วัด")
    p.add_argument("--diag", action="store_true",
                   help="ตรวจหาสาเหตุเมื่อดึงข้อมูลไม่ได้")
    a = p.parse_args()

    if a.setkey:
        return set_key(a.setkey)
    if a.diag:
        return diagnose()

    if a.list:
        print(f"ตัวชี้วัดจาก FRED : {len(FRED_SERIES)} ตัว")
        for sid, m in FRED_SERIES.items():
            print(f"  {m['grp']:<10} {sid:<22} {m['th']}")
        print(f"\nราคาตลาดจาก Yahoo : {len(MARKET_SYMBOLS)} ตัว")
        for sym, m in MARKET_SYMBOLS.items():
            print(f"  {m['grp']:<10} {sym:<22} {m['th']}")
        return 0

    if a.test or a.fetch:
        print("=" * 68)
        print("ทดสอบการดึงข้อมูลเศรษฐกิจ")
        print(f"FRED API key : {'มี' if _fred_key() else 'ไม่มี (ใช้ทาง fredgraph.csv)'}")
        print("=" * 68)
        t0 = time.time()
        d = fetch_all(use_cache=not a.fetch, verbose=True)
        ok = len(d["fred"]) - len([x for x in d["dead"] if x in d["fred"]])
        print("-" * 68)
        print(f"ดึงสำเร็จ {len(d['fred'])}/{len(FRED_SERIES)} ชุด "
              f"· ใช้โหวตได้ {ok} ชุด · ตัดออก {len(d['dead'])} ชุด")
        if d.get("ช่องทางที่ใช้ได้"):
            print(f"ช่องทางที่ใช้ได้ : {d['ช่องทางที่ใช้ได้']}")
        if not d["market"].empty:
            print(f"ราคาตลาด {d['market'].shape[1]} ตัว "
                  f"ถึงวันที่ {d['market'].index[-1].date()}")
        else:
            print("ราคาตลาด : ดึงไม่ได้")
        print(f"ใช้เวลา {time.time() - t0:.1f} วินาที")

        if d.get("หยุดกลางคัน") or not d["fred"]:
            print()
            print("!" * 68)
            print("เข้า FRED ไม่ได้เลย — ให้รันคำสั่งนี้เพื่อหาสาเหตุ :")
            print()
            print("    python3 macro_data.py --diag")
            print()
            print("แล้วส่งผลที่ได้ให้ผู้ช่วยดู")
            print("!" * 68)
            return 1

        if d["dead"]:
            print("\nชุดที่ใช้ไม่ได้ (จะถูกตัดออกจากการโหวตอัตโนมัติ):")
            for h in d["health"]:
                if not h["ใช้ได้"]:
                    print(f"  - {h['series']}: {h['เหตุผล']}")
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
