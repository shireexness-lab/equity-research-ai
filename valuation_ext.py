"""
valuation_ext.py — วิธีประเมินมูลค่าเฉพาะกลุ่มธุรกิจ
========================================================
ต่อยอดจาก valuation.py ซึ่งทำ DCF / DDM / EPV / Reverse DCF / P-BV ไว้แล้ว

ปัญหาที่แก้
-----------
วิธีเดียวใช้กับทุกกลุ่มไม่ได้ ตัวอย่างที่เจอจริงในระบบนี้

  BCP (โรงกลั่น)  DCF บนข้อมูล 4 ปี ให้มูลค่า 190 บาท ราคาจริง 45 บาท
                  เพราะ 4 ปีนั้นบังเอิญเป็นช่วงค่าการกลั่นสูง
                  -> ต้องใช้ "กำไรกลางวัฏจักร" ไม่ใช่กำไรปีล่าสุด

  ธนาคาร          DCF ใช้ไม่ได้เลยเพราะเงินฝากคือวัตถุดิบ ไม่ใช่หนี้
                  -> ต้องใช้ Residual Income ซึ่งเป็นมาตรฐานสากล

  REIT            ค่าเสื่อมอาคารกดกำไรสุทธิให้ต่ำกว่าความจริงมาก
                  -> ต้องใช้ FFO ที่บวกค่าเสื่อมกลับเข้าไป

วิธีที่เพิ่มในไฟล์นี้
---------------------
| วิธี                | เหมาะกับ                     | คำนวณอัตโนมัติได้ไหม |
|---------------------|------------------------------|----------------------|
| Residual Income     | ธนาคาร ประกัน                | ได้                  |
| กำไรกลางวัฏจักร/CAPE| โรงกลั่น เหมือง เดินเรือ     | ได้                  |
| P/FFO               | REIT กองทุนโครงสร้างพื้นฐาน  | ได้                  |
| Monte Carlo         | ทุกกลุ่มที่ใช้ DCF ได้        | ได้                  |
| RNAV                | อสังหาริมทรัพย์               | ต้องกรอกมือ          |
| SOTP                | โฮลดิ้ง กลุ่มบริษัท           | ต้องกรอกมือ          |

RNAV กับ SOTP ทำอัตโนมัติไม่ได้จริง ๆ เพราะต้องใช้ข้อมูลรายโครงการ
และรายบริษัทย่อย ซึ่งไม่มีในงบการเงินรวม จึงทำเป็นเครื่องคิดเลขให้กรอกเอง
ดีกว่าเดาตัวเลขแล้วแสดงผลเหมือนเป็นของจริง

วิธีใช้จาก Terminal
-------------------
    python3 valuation_ext.py KBANK.BK
    python3 valuation_ext.py BCP.BK --mc 5000
"""

import sys

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 0) จัดกลุ่มธุรกิจ เพื่อเลือกวิธีที่เหมาะ
# ---------------------------------------------------------------------------

# คำที่ใช้ตรวจกลุ่ม — ดูทั้ง sector และ industry เพราะ yfinance ใส่มาไม่เหมือนกัน
# เช่น ธนาคารไทยบางตัว sector = "Financial Services" แต่ industry = "Banks—Regional"
_RULES = [
    ("ธนาคาร/การเงิน", ("bank", "financial", "insurance", "capital markets",
                        "credit services", "asset management", "mortgage")),
    ("REIT/กองทุน", ("reit", "real estate investment trust", "infrastructure fund")),
    ("อสังหาริมทรัพย์", ("real estate", "property", "homebuilding",
                         "residential construction")),
    ("วัฏจักร", ("oil", "gas", "refin", "petro", "chemical", "steel", "mining",
                 "metals", "copper", "coal", "shipping", "marine", "airlines",
                 "aluminum", "semiconductor equipment", "auto manufacturers",
                 "agricultural inputs", "lumber", "paper")),
    ("โฮลดิ้ง", ("conglomerate", "holding", "shell companies")),
]


def classify(data) -> str:
    """
    บอกว่าหุ้นตัวนี้อยู่กลุ่มไหน เพื่อเลือกวิธีประเมินที่เหมาะ

    คืนหนึ่งใน : ธนาคาร/การเงิน · REIT/กองทุน · อสังหาริมทรัพย์ ·
                 วัฏจักร · โฮลดิ้ง · ทั่วไป
    """
    info = data.get("info", {}) if isinstance(data, dict) else {}
    text = f"{info.get('sector') or ''} {info.get('industry') or ''}".lower()
    name = str(info.get("longName") or "").lower()
    for label, words in _RULES:
        if any(w in text for w in words):
            return label
    # กองทุนไทยมักไม่ระบุ sector แต่ชื่อบอกชัด
    if any(w in name for w in ("reit", "leasehold", "freehold", "infrastructure fund")):
        return "REIT/กองทุน"
    return "ทั่วไป"


# วิธีที่ "ควรใช้" และ "ห้ามใช้" ของแต่ละกลุ่ม — อ้างอิงคู่มือไฟล์ 20
PLAYBOOK = {
    "ธนาคาร/การเงิน": {
        "ควรใช้": ["Residual Income", "P/BV คู่กับ ROE", "DDM"],
        "ห้ามใช้": ["DCF (FCFF)", "EV/EBITDA"],
        "เหตุผล": "เงินฝากคือวัตถุดิบของธุรกิจ ไม่ใช่แหล่งเงินทุน "
                  "แนวคิดหนี้สินสุทธิและ CapEx จึงไม่มีความหมาย",
    },
    "REIT/กองทุน": {
        "ควรใช้": ["P/FFO", "DDM", "P/NAV"],
        "ห้ามใช้": ["P/E", "DCF ปกติ"],
        "เหตุผล": "ค่าเสื่อมอาคารเป็นรายการทางบัญชีที่ไม่ใช่เงินสด "
                  "และกดกำไรสุทธิให้ต่ำกว่าความสามารถจ่ายปันผลจริงมาก",
    },
    "อสังหาริมทรัพย์": {
        "ควรใช้": ["RNAV", "P/BV"],
        "ห้ามใช้": ["P/E ปีเดียว"],
        "เหตุผล": "รับรู้รายได้เป็นก้อนตอนโอนโครงการ กำไรรายปีจึงกระโดด "
                  "และที่ดินในงบยังเป็นราคาทุนเดิม",
    },
    "วัฏจักร": {
        "ควรใช้": ["กำไรกลางวัฏจักร", "P/BV", "EPV"],
        "ห้ามใช้": ["P/E ปีเดียว", "DCF จากข้อมูลสั้น"],
        "เหตุผล": "P/E ต่ำสุดตอนใกล้จุดพีคของวัฏจักร ตรงข้ามกับสัญชาตญาณ "
                  "ต้องใช้กำไรเฉลี่ยทั้งรอบ ไม่ใช่กำไรปีล่าสุด",
    },
    "โฮลดิ้ง": {
        "ควรใช้": ["SOTP", "P/NAV พร้อมส่วนลดโฮลดิ้ง"],
        "ห้ามใช้": ["P/E รวม"],
        "เหตุผล": "แต่ละธุรกิจย่อยควรใช้วิธีที่เหมาะกับตัวเอง "
                  "การรวมกำไรแล้วคูณ P/E เดียวทำให้มองไม่เห็นว่าส่วนไหนสร้างมูลค่า",
    },
    "ทั่วไป": {
        "ควรใช้": ["DCF", "EPV", "Reverse DCF", "P/E ย้อนหลัง"],
        "ห้ามใช้": [],
        "เหตุผล": "กระแสเงินสดคาดการณ์ได้พอสมควร ใช้วิธีมาตรฐานได้",
    },
}


def _f(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _last(s):
    if s is None:
        return None
    s = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
    return float(s.iloc[-1]) if len(s) else None


# ---------------------------------------------------------------------------
# 1) Residual Income — มาตรฐานสำหรับธนาคาร
# ---------------------------------------------------------------------------

def residual_income(R, cost_equity, shares, years=10, persistence=0.0) -> dict:
    """
    มูลค่า = มูลค่าทางบัญชีวันนี้ + กำไรส่วนเกินในอนาคตที่คิดลดกลับมา

        กำไรส่วนเกินปีที่ t = (ROE ปีนั้น − ต้นทุนส่วนทุน) x มูลค่าทางบัญชีต้นปี

    ทำไมเหมาะกับธนาคาร
    --------------------
    มูลค่าส่วนใหญ่มาจาก **งบดุลที่ตรวจสอบได้** ไม่ใช่จากการเดาอนาคต
    ต่างจาก DCF ที่ 60-80% ของมูลค่ามาจาก terminal value ซึ่งเป็นการเดาล้วน
    และสินทรัพย์ของธนาคารเป็นการเงินที่ตีมูลค่าตามตลาดอยู่แล้ว
    มูลค่าทางบัญชีจึงใกล้เคียงความจริงมากกว่าบริษัททั่วไป

    สมมติฐานสำคัญ — ROE จะจางลงหาต้นทุนส่วนทุน
    ---------------------------------------------
    ธนาคารที่ทำ ROE 15% ได้ตอนนี้ จะไม่ทำได้ตลอดไป เพราะคู่แข่งจะเข้ามา
    โมเดลนี้จึงให้ ROE ค่อย ๆ ลดลงเป็นเส้นตรงจนเท่าต้นทุนส่วนทุนในปีที่ N
    หลังจากนั้นกำไรส่วนเกิน = 0 (กำไรพอดีกับที่ผู้ถือหุ้นเรียกร้อง)

    นี่เป็นสมมติฐานที่ **อนุรักษ์นิยม** ถ้าธนาคารมีคูเมืองจริงจะประเมินต่ำไป
    ปรับได้ด้วย persistence (0 = จางหมด · 0.5 = เหลือครึ่งหนึ่งตลอดไป)
    """
    raw = R.get("raw", {})
    eq = _last(raw.get("equity"))
    net = _last(raw.get("net_income"))
    if not eq or eq <= 0 or net is None or not shares or shares <= 0:
        return {"ใช้ได้": False,
                "เหตุผล": "ต้องมีส่วนของผู้ถือหุ้นเป็นบวกและมีกำไรสุทธิ"}

    r = float(cost_equity)
    if r <= 0:
        return {"ใช้ได้": False, "เหตุผล": "ต้นทุนส่วนทุนต้องเป็นบวก"}

    # ROE เริ่มต้น — ใช้ค่ากลาง 3 ปีล่าสุด ไม่ใช่ปีเดียว เพื่อลดผลของปีผิดปกติ
    try:
        roe_s = pd.to_numeric(R["table"].loc["ROE"], errors="coerce").dropna()
        roe0 = float(roe_s.tail(3).median()) / 100 if len(roe_s) else net / eq
    except Exception:
        roe0 = net / eq

    # อัตราจ่ายปันผล -> ส่วนที่เก็บไว้ทำให้ทุนโต
    div = _last(raw.get("dividends_paid"))
    payout = min(max(abs(div) / net, 0.0), 0.95) if (div and net > 0) else 0.4
    retention = 1 - payout

    bv = eq
    pv = 0.0
    rows = []
    for t in range(1, int(years) + 1):
        # ROE จางลงเป็นเส้นตรงจาก roe0 -> r
        roe_t = roe0 + (r - roe0) * (t / years)
        ri = (roe_t - r) * bv
        pv += ri / ((1 + r) ** t)
        rows.append({"ปีที่": t, "ROE (%)": roe_t * 100,
                     "ทุนต้นปี": bv, "กำไรส่วนเกิน": ri,
                     "มูลค่าปัจจุบัน": ri / ((1 + r) ** t)})
        bv = bv * (1 + roe_t * retention)

    # กำไรส่วนเกินที่ยังเหลืออยู่หลังปีที่ N (ถ้าเชื่อว่ามีคูเมือง)
    tv = 0.0
    if persistence > 0:
        ri_last = rows[-1]["กำไรส่วนเกิน"]
        tv = (ri_last * persistence / r) / ((1 + r) ** years)

    equity_value = eq + pv + tv
    return {
        "ใช้ได้": True,
        "มูลค่าต่อหุ้น": equity_value / shares,
        "มูลค่าทางบัญชีต่อหุ้น": eq / shares,
        "PV กำไรส่วนเกิน ต่อหุ้น": pv / shares,
        "PV ส่วนที่คงอยู่ ต่อหุ้น": tv / shares,
        "ROE เริ่มต้น (%)": roe0 * 100,
        "ต้นทุนส่วนทุน (%)": r * 100,
        "อัตราจ่ายปันผล (%)": payout * 100,
        "ตารางรายปี": pd.DataFrame(rows),
        # สัดส่วนที่มาจากงบดุล = ตัวชี้ว่าผลนี้พึ่งการเดาอนาคตแค่ไหน
        "สัดส่วนจากงบดุล (%)": eq / equity_value * 100 if equity_value else np.nan,
    }


# ---------------------------------------------------------------------------
# 2) กำไรกลางวัฏจักร / CAPE — สำหรับหุ้นวัฏจักร
# ---------------------------------------------------------------------------

def mid_cycle_earnings(R, shares, ref_pe=None) -> dict:
    """
    ประเมินหุ้นวัฏจักรด้วย "กำไรเฉลี่ยทั้งรอบ" แทนกำไรปีล่าสุด

    ปัญหาของหุ้นวัฏจักร
    --------------------
    โรงกลั่น เหมือง เดินเรือ มีกำไรแกว่งเป็นรอบ 5-10 ปี
    ปีที่ค่าการกลั่นดี กำไรอาจสูงกว่าปีแย่ 10 เท่า
    ผลคือ P/E **ต่ำสุดตอนใกล้จุดพีค** และ **สูงสุดตอนใกล้จุดต่ำสุด**
    ซึ่งตรงข้ามกับสัญชาตญาณโดยสิ้นเชิง ใครซื้อเพราะเห็น P/E 3 เท่ามักเจ็บหนัก

    วิธีแก้ 2 ทาง ที่ทำในฟังก์ชันนี้
    ---------------------------------
    1. **CAPE** = ราคา / EPS เฉลี่ยทั้งช่วง
       ตรงไปตรงมา แต่ไม่ปรับขนาดกิจการที่โตขึ้นตามเวลา

    2. **กำไรปรับฐาน** = อัตรากำไรสุทธิเฉลี่ยทั้งช่วง x รายได้ปีล่าสุด
       ดีกว่าข้อ 1 เพราะใช้ "ขนาดกิจการวันนี้" คูณ "ความสามารถทำกำไรโดยเฉลี่ย"
       บริษัทที่ขยายกำลังการผลิตไปแล้วจะไม่ถูกประเมินต่ำเกินจริง

    ข้อจำกัดที่ต้องรู้
    -------------------
    ต้องมีข้อมูลครอบคลุมอย่างน้อย 1 รอบวัฏจักรเต็ม (7-10 ปี)
    **หุ้นไทยที่มีข้อมูลแค่ 4 ปีใช้วิธีนี้ได้ผลจำกัดมาก** เพราะ 4 ปีนั้น
    อาจอยู่ในช่วงขาขึ้นทั้งหมด ค่าเฉลี่ยที่ได้ก็ยังเป็นค่าเฉลี่ยของช่วงดี
    ฟังก์ชันนี้จะเตือนเมื่อข้อมูลสั้นเกินไป
    """
    raw = R.get("raw", {})
    rev = pd.to_numeric(pd.Series(raw.get("revenue")), errors="coerce").dropna()
    net = pd.to_numeric(pd.Series(raw.get("net_income")), errors="coerce").dropna()
    eps = pd.to_numeric(pd.Series(raw.get("eps")), errors="coerce").dropna()
    price = _f(raw.get("ราคาปัจจุบัน"))

    n = int(min(len(rev), len(net)))
    if n < 3 or not price:
        return {"ใช้ได้": False, "เหตุผล": "ต้องมีข้อมูลอย่างน้อย 3 ปีและมีราคา"}

    warn = []
    if n < 7:
        warn.append(f"มีข้อมูล {n} ปี — สั้นกว่า 1 รอบวัฏจักร (7-10 ปี) "
                    "ค่าเฉลี่ยที่ได้อาจยังเป็นค่าเฉลี่ยของช่วงดีทั้งหมด")

    # อัตรากำไรสุทธิเฉลี่ย — ใช้ค่ากลาง ทนต่อปีที่ผิดปกติกว่าค่าเฉลี่ย
    margins = (net.values / rev.values) * 100
    margins = margins[np.isfinite(margins)]
    if not len(margins):
        return {"ใช้ได้": False, "เหตุผล": "คำนวณอัตรากำไรไม่ได้"}
    med_margin = float(np.median(margins))

    rev_now = float(rev.iloc[-1])
    norm_net = rev_now * med_margin / 100
    norm_eps = norm_net / shares if shares else None

    cape = price / float(eps.mean()) if len(eps) and eps.mean() > 0 else None

    # P/E อ้างอิง : ถ้าไม่ระบุ ใช้ค่ากลางย้อนหลังของหุ้นตัวเอง
    if ref_pe is None:
        try:
            pe_hist = price / eps
            pe_hist = pe_hist[(pe_hist > 0) & np.isfinite(pe_hist)]
            ref_pe = float(np.median(pe_hist)) if len(pe_hist) else 12.0
        except Exception:
            ref_pe = 12.0
    ref_pe = float(min(max(ref_pe, 5.0), 25.0))     # กันค่าสุดโต่ง

    value = norm_eps * ref_pe if norm_eps and norm_eps > 0 else None

    return {
        "ใช้ได้": value is not None,
        "มูลค่าต่อหุ้น": value,
        "จำนวนปีที่ใช้": n,
        "อัตรากำไรสุทธิเฉลี่ย (%)": med_margin,
        "อัตรากำไรสุทธิปีล่าสุด (%)": float(net.iloc[-1] / rev.iloc[-1] * 100),
        "กำไรปรับฐาน (ล้าน)": norm_net / 1e6,
        "EPS ปรับฐาน": norm_eps,
        "EPS ปีล่าสุด": float(eps.iloc[-1]) if len(eps) else None,
        "P/E อ้างอิง": ref_pe,
        "CAPE": cape,
        "คำเตือน": warn,
    }


# ---------------------------------------------------------------------------
# 3) P/FFO — สำหรับ REIT และกองทุนโครงสร้างพื้นฐาน
# ---------------------------------------------------------------------------

def ffo_value(R, shares, ref_pffo=None) -> dict:
    """
    FFO (Funds From Operations) = กำไรสุทธิ + ค่าเสื่อมและค่าตัดจำหน่าย

    ทำไม REIT ต้องใช้ FFO ไม่ใช่กำไรสุทธิ
    ---------------------------------------
    มาตรฐานบัญชีบังคับให้ตัดค่าเสื่อมอาคารทุกปี ราวกับว่าอาคารเสื่อมค่าลง
    แต่ในความเป็นจริง **อสังหาริมทรัพย์ที่ดูแลดีมักมีมูลค่าเพิ่มขึ้นตามเวลา**
    ค่าเสื่อมจึงเป็นรายการทางบัญชีที่ไม่ตรงกับความจริงทางเศรษฐกิจ
    และไม่ใช่เงินสดที่จ่ายออกไปจริง

    ผลคือกำไรสุทธิของ REIT ต่ำกว่าเงินสดที่จ่ายปันผลได้จริงมาก
    ถ้าดู P/E จะเห็นเป็น 30-40 เท่าและคิดว่าแพง ทั้งที่ P/FFO อาจแค่ 12 เท่า

    ข้อจำกัด
    ---------
    FFO มาตรฐานต้องหักกำไรจากการขายทรัพย์สินออกด้วย
    แต่งบรวมของ yfinance ไม่ได้แยกรายการนั้นไว้ ตัวเลขที่ได้จึงอาจสูงเกินจริง
    ในปีที่ REIT ขายทรัพย์สินออก — ต้องเปิดงบดูประกอบ

    AFFO (ที่หักค่าใช้จ่ายบำรุงรักษาประจำ) แม่นกว่า FFO แต่ต้องใช้ข้อมูล
    ที่ไม่มีในงบรวม จึงทำอัตโนมัติไม่ได้
    """
    raw = R.get("raw", {})
    net = _last(raw.get("net_income"))
    da = _last(raw.get("d_and_a"))
    price = _f(raw.get("ราคาปัจจุบัน"))

    if net is None or price is None or not shares:
        return {"ใช้ได้": False, "เหตุผล": "ต้องมีกำไรสุทธิ ราคา และจำนวนหุ้น"}
    if da is None:
        return {"ใช้ได้": False,
                "เหตุผล": "ไม่มีค่าเสื่อมและค่าตัดจำหน่ายในงบ จึงคำนวณ FFO ไม่ได้"}

    ffo = net + abs(da)
    ffo_ps = ffo / shares
    if ffo_ps <= 0:
        return {"ใช้ได้": False, "เหตุผล": "FFO ต่อหุ้นติดลบ"}

    pffo_now = price / ffo_ps
    # P/FFO อ้างอิง : REIT ไทยซื้อขายกันราว 10-16 เท่า ใช้ 13 เป็นกลาง
    ref = float(ref_pffo) if ref_pffo else 13.0

    return {
        "ใช้ได้": True,
        "มูลค่าต่อหุ้น": ffo_ps * ref,
        "FFO (ล้าน)": ffo / 1e6,
        "FFO ต่อหุ้น": ffo_ps,
        "กำไรสุทธิต่อหุ้น": net / shares,
        "ค่าเสื่อมที่บวกกลับ (ล้าน)": abs(da) / 1e6,
        "P/FFO ปัจจุบัน": pffo_now,
        "P/FFO อ้างอิง": ref,
        # ตัวเลขนี้บอกว่าค่าเสื่อมกดกำไรไปมากแค่ไหน
        "FFO สูงกว่ากำไรสุทธิ (เท่า)": ffo / net if net > 0 else np.nan,
    }


# ---------------------------------------------------------------------------
# 4) Monte Carlo — แสดงความไม่แน่นอนเป็นช่วง ไม่ใช่ตัวเลขเดียว
# ---------------------------------------------------------------------------

def monte_carlo(fcf0, years1, shares, net_debt,
                wacc_mid, g1_mid, g2_mid=0.025,
                wacc_sd=0.015, g1_sd=0.04, g2_sd=0.005,
                n=5000, seed=42) -> dict:
    """
    สุ่มค่า WACC / g1 / g2 หลายพันรอบ แล้วดูว่ามูลค่าที่ได้กระจายอย่างไร

    ทำไมมีประโยชน์
    ----------------
    DCF ปกติให้ตัวเลขเดียว เช่น "มูลค่า 185 บาท" ซึ่งดูแม่นยำเกินความจริง
    ทั้งที่ถ้าขยับ WACC ไป 1% ตัวเลขอาจเปลี่ยนเป็น 140 หรือ 250

    Monte Carlo ตอบคำถามที่มีประโยชน์กว่า :
      "ราคาปัจจุบันอยู่ตรงไหนของการกระจาย"
      "มีโอกาสกี่ % ที่มูลค่าจริงจะต่ำกว่าราคาที่จ่าย"

    ข้อควรระวังที่สำคัญที่สุด
    --------------------------
    **ความแม่นยำที่ดูน่าเชื่อถืออาจหลอกตัวเอง** ตัวเลข "โอกาส 73%"
    ดูเป็นวิทยาศาสตร์มาก แต่มันเป็นจริงก็ต่อเมื่อสมมติฐานเรื่องการกระจาย
    (ว่า WACC แจกแจงแบบปกติ ส่วนเบี่ยงเบน 1.5%) ถูกต้อง ซึ่งเราไม่มีทางรู้

    ให้อ่านผลนี้เป็น "ความไวต่อสมมติฐาน" ไม่ใช่ "ความน่าจะเป็นจริง"
    """
    from valuation import MIN_WACC_GAP, dcf_2stage

    rng = np.random.default_rng(seed)
    wacc = rng.normal(wacc_mid, wacc_sd, n)
    g1 = rng.normal(g1_mid, g1_sd, n)
    g2 = rng.normal(g2_mid, g2_sd, n)

    # บังคับให้อยู่ในกรอบที่มีความหมายทางการเงิน
    wacc = np.clip(wacc, 0.03, 0.30)
    g1 = np.clip(g1, -0.20, 0.40)
    g2 = np.clip(g2, -0.01, 0.04)
    g2 = np.minimum(g2, wacc - MIN_WACC_GAP)     # g2 ต้องน้อยกว่า WACC เสมอ

    vals = []
    for w, a, b in zip(wacc, g1, g2):
        try:
            v = dcf_2stage(fcf0, float(a), years1, float(b), float(w),
                           shares, net_debt)["มูลค่าต่อหุ้น"]
            if np.isfinite(v) and v > 0:
                vals.append(v)
        except Exception:
            continue

    if len(vals) < n * 0.5:
        return {"ใช้ได้": False,
                "เหตุผล": f"คำนวณสำเร็จเพียง {len(vals):,} จาก {n:,} รอบ "
                          "— สมมติฐานอาจไม่สมเหตุสมผล"}

    a = np.array(vals)
    pct = {f"P{p}": float(np.percentile(a, p)) for p in (5, 10, 25, 50, 75, 90, 95)}
    return {
        "ใช้ได้": True,
        "จำนวนรอบที่สำเร็จ": len(a),
        "มูลค่าต่อหุ้น": float(np.median(a)),      # ใช้ค่ากลางเป็นตัวแทน
        "ค่าเฉลี่ย": float(a.mean()),
        "ส่วนเบี่ยงเบน": float(a.std()),
        "เปอร์เซ็นไทล์": pct,
        "ค่าที่สุ่มได้": a,
        "สมมติฐาน": {"WACC": (wacc_mid, wacc_sd), "g1": (g1_mid, g1_sd),
                     "g2": (g2_mid, g2_sd)},
    }


def mc_probability(mc: dict, price: float) -> dict:
    """โอกาสที่มูลค่าจะสูงกว่าราคาปัจจุบัน (อ่านเป็นความไว ไม่ใช่ความน่าจะเป็นจริง)"""
    if not mc.get("ใช้ได้") or not price:
        return {}
    a = mc["ค่าที่สุ่มได้"]
    return {
        "โอกาสมูลค่า > ราคา (%)": float((a > price).mean() * 100),
        "โอกาสมูลค่า > ราคา 1.3 เท่า (%)": float((a > price * 1.3).mean() * 100),
        "โอกาสมูลค่า < ราคา 0.7 เท่า (%)": float((a < price * 0.7).mean() * 100),
    }


# ---------------------------------------------------------------------------
# 5) RNAV — ต้องกรอกข้อมูลเอง
# ---------------------------------------------------------------------------

def rnav(book_equity, shares, revaluations=None, net_debt_adj=0.0,
         discount=0.0) -> dict:
    """
    RNAV = มูลค่าทางบัญชี + ส่วนเพิ่มจากการตีราคาสินทรัพย์ใหม่ − หนี้เพิ่มเติม

    revaluations : list ของ (ชื่อรายการ, ส่วนเพิ่ม/ลดเป็นเงิน)
                   เช่น [("ที่ดินย่านสุขุมวิท", 4_500_000_000),
                         ("โครงการรอโอน", 1_200_000_000)]

    discount     : ส่วนลดที่ตลาดให้ (0.20 = 20%) — อสังหาฯ ไทยมักซื้อขาย
                   ต่ำกว่า RNAV เพราะสภาพคล่องต่ำและความไม่แน่นอนของการขาย

    ทำไมต้องกรอกเอง
    -----------------
    งบการเงินบันทึกที่ดินด้วย **ราคาทุนตอนซื้อ** ที่ดินที่ซื้อเมื่อ 30 ปีก่อน
    ยังอยู่ในงบด้วยราคาเดิม ทั้งที่ราคาตลาดวันนี้อาจต่างกัน 10 เท่า
    ส่วนต่างนี้ไม่มีในงบการเงินใด ๆ ต้องหาจากรายงานประจำปี รายงานผู้ประเมินอิสระ
    หรือบทวิเคราะห์ — จึงเป็นตัวเลขที่ระบบดึงอัตโนมัติไม่ได้จริง ๆ

    การเดาตัวเลขนี้แล้วแสดงผลเหมือนเป็นของจริง อันตรายกว่าการไม่แสดงเลย
    """
    if not shares or shares <= 0:
        return {"ใช้ได้": False, "เหตุผล": "ต้องระบุจำนวนหุ้น"}
    items = list(revaluations or [])
    surplus = sum(float(v) for _, v in items)
    value = float(book_equity) + surplus - float(net_debt_adj)
    per_share = value / shares
    return {
        "ใช้ได้": True,
        "มูลค่าต่อหุ้น": per_share * (1 - float(discount)),
        "RNAV ต่อหุ้น (ก่อนส่วนลด)": per_share,
        "มูลค่าทางบัญชี": float(book_equity),
        "ส่วนเพิ่มจากการตีราคา": surplus,
        "รายการที่ตีราคาใหม่": items,
        "ส่วนลด (%)": float(discount) * 100,
    }


# ---------------------------------------------------------------------------
# 6) SOTP — ต้องกรอกข้อมูลเอง
# ---------------------------------------------------------------------------

def sotp(segments, net_debt=0.0, shares=None, holding_discount=0.15) -> dict:
    """
    ประเมินแต่ละธุรกิจย่อยด้วยวิธีที่เหมาะกับธุรกิจนั้น แล้วรวมกัน

    segments : list ของ dict
        {"ชื่อ": "โรงพยาบาล", "ตัวเลข": 3_000_000_000,
         "ตัวคูณ": 12, "ฐาน": "EBITDA", "สัดส่วนถือหุ้น": 0.7}

    holding_discount : ส่วนลดโฮลดิ้ง (ปกติ 10-30%)

    ทำไมต้องมีส่วนลดโฮลดิ้ง
    -------------------------
    ผู้ถือหุ้นบริษัทแม่ไม่ได้ถือธุรกิจย่อยโดยตรง จึงมีต้นทุนแฝง :
      - ค่าใช้จ่ายสำนักงานใหญ่ที่ไม่ได้สร้างรายได้
      - ภาษีซ้อนตอนจ่ายเงินปันผลขึ้นมาบริษัทแม่
      - ผู้ถือหุ้นเลือกไม่ได้ว่าจะถือธุรกิจไหน ต้องรับมาทั้งกระบิ
    ตลาดจึงให้ราคาโฮลดิ้งต่ำกว่าผลรวมของส่วนย่อยเสมอ ทั่วโลกเป็นแบบนี้
    """
    rows = []
    total = 0.0
    for s in segments or []:
        v = float(s.get("ตัวเลข", 0)) * float(s.get("ตัวคูณ", 0))
        stake = float(s.get("สัดส่วนถือหุ้น", 1.0))
        v_own = v * stake
        total += v_own
        rows.append({"ธุรกิจ": s.get("ชื่อ", "-"),
                     "ฐานที่ใช้": s.get("ฐาน", "EBITDA"),
                     "ตัวเลข (ล้าน)": float(s.get("ตัวเลข", 0)) / 1e6,
                     "ตัวคูณ (เท่า)": float(s.get("ตัวคูณ", 0)),
                     "มูลค่าเต็ม (ล้าน)": v / 1e6,
                     "สัดส่วนถือหุ้น (%)": stake * 100,
                     "มูลค่าตามสัดส่วน (ล้าน)": v_own / 1e6})

    equity_value = total - float(net_debt)
    after = equity_value * (1 - float(holding_discount))
    out = {
        "ใช้ได้": bool(rows),
        "มูลค่ารวมทุกธุรกิจ": total,
        "หนี้สินสุทธิ": float(net_debt),
        "มูลค่าส่วนผู้ถือหุ้น": equity_value,
        "หลังส่วนลดโฮลดิ้ง": after,
        "ส่วนลดโฮลดิ้ง (%)": float(holding_discount) * 100,
        "ตารางธุรกิจย่อย": pd.DataFrame(rows),
    }
    if shares:
        out["มูลค่าต่อหุ้น"] = after / shares
        out["ก่อนส่วนลด ต่อหุ้น"] = equity_value / shares
    return out


# ---------------------------------------------------------------------------
# 7) รวมทุกวิธีที่เหมาะกับกลุ่มของหุ้นตัวนั้น
# ---------------------------------------------------------------------------

def extra_methods(data, R, wacc_detail, shares, price=None,
                  run_mc=True, mc_n=3000, inputs=None) -> dict:
    """
    เลือกและคำนวณวิธีที่เหมาะกับกลุ่มธุรกิจของหุ้นตัวนี้

    คืน dict :
        กลุ่ม        : ชื่อกลุ่มที่จัดได้
        แนวทาง       : ควรใช้/ห้ามใช้/เหตุผล
        methods      : {ชื่อวิธี: มูลค่าต่อหุ้น}
        รายละเอียด   : ผลเต็มของแต่ละวิธี
        ต้องกรอกเอง  : รายชื่อวิธีที่ทำอัตโนมัติไม่ได้
    """
    group = classify(data)
    play = PLAYBOOK.get(group, PLAYBOOK["ทั่วไป"])
    ce = wacc_detail.get("ต้นทุนส่วนทุน") if wacc_detail else None

    out = {"กลุ่ม": group, "แนวทาง": play, "methods": {}, "รายละเอียด": {},
           "ต้องกรอกเอง": [], "หมายเหตุ": []}

    # ---- Residual Income : ธนาคาร/การเงิน (และใช้เสริมได้กับทุกกลุ่ม) ----
    if ce:
        ri = residual_income(R, ce, shares)
        out["รายละเอียด"]["Residual Income"] = ri
        if ri.get("ใช้ได้"):
            out["methods"]["Residual Income"] = ri["มูลค่าต่อหุ้น"]
        elif group == "ธนาคาร/การเงิน":
            out["หมายเหตุ"].append(f"Residual Income ใช้ไม่ได้ : {ri.get('เหตุผล')}")

    # ---- กำไรกลางวัฏจักร : หุ้นวัฏจักร ----
    if group == "วัฏจักร":
        mc_e = mid_cycle_earnings(R, shares)
        out["รายละเอียด"]["กำไรกลางวัฏจักร"] = mc_e
        if mc_e.get("ใช้ได้"):
            out["methods"]["กำไรกลางวัฏจักร"] = mc_e["มูลค่าต่อหุ้น"]
            out["หมายเหตุ"] += mc_e.get("คำเตือน", [])
        else:
            out["หมายเหตุ"].append(f"กำไรกลางวัฏจักรใช้ไม่ได้ : {mc_e.get('เหตุผล')}")

    # ---- P/FFO : REIT ----
    if group == "REIT/กองทุน":
        ff = ffo_value(R, shares)
        out["รายละเอียด"]["P/FFO"] = ff
        if ff.get("ใช้ได้"):
            out["methods"]["P/FFO"] = ff["มูลค่าต่อหุ้น"]
        else:
            out["หมายเหตุ"].append(f"P/FFO ใช้ไม่ได้ : {ff.get('เหตุผล')}")

    # ---- Monte Carlo : ทุกกลุ่มที่ทำ DCF ได้ ----
    if run_mc and inputs and inputs.get("fcf0") and inputs["fcf0"] > 0:
        m = monte_carlo(inputs["fcf0"], inputs.get("years1", 10), shares,
                        inputs.get("net_debt", 0.0),
                        wacc_mid=inputs["wacc"], g1_mid=inputs["g1"],
                        g2_mid=inputs.get("g2", 0.025), n=mc_n)
        out["รายละเอียด"]["Monte Carlo"] = m
        if m.get("ใช้ได้"):
            out["methods"]["Monte Carlo (ค่ากลาง)"] = m["มูลค่าต่อหุ้น"]
            if price:
                m.update(mc_probability(m, price))

    # ---- วิธีที่ต้องกรอกเอง ----
    if group == "อสังหาริมทรัพย์":
        out["ต้องกรอกเอง"].append(
            ("RNAV", "ต้องมีราคาประเมินที่ดินและโครงการรายแปลง "
                     "ซึ่งอยู่ในรายงานประจำปี ไม่ได้อยู่ในงบการเงิน"))
    if group == "โฮลดิ้ง":
        out["ต้องกรอกเอง"].append(
            ("SOTP", "ต้องมีตัวเลขรายธุรกิจย่อยและสัดส่วนการถือหุ้น "
                     "ซึ่งงบรวมไม่ได้แยกไว้"))
    return out


# ---------------------------------------------------------------------------
# ใช้จาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="วิธีประเมินมูลค่าเฉพาะกลุ่มธุรกิจ")
    p.add_argument("ticker")
    p.add_argument("--rf", type=float, default=None, help="อัตราพันธบัตร")
    p.add_argument("--mc", type=int, default=3000, help="จำนวนรอบ Monte Carlo")
    a = p.parse_args()

    from data_layer import get_stock_data
    from ratios import compute_ratios
    from valuation import (estimate_inputs, estimate_wacc, get_current_price,
                           get_shares_outstanding)

    t = a.ticker.upper()
    print(f"\nกำลังดึงข้อมูล {t} ...")
    data = get_stock_data(t)
    R = compute_ratios(data)
    price = get_current_price(data)
    shares = get_shares_outstanding(data)
    w = estimate_wacc(data, R, rf=a.rf)

    try:
        inp = estimate_inputs(data, R)
        mc_in = {"fcf0": inp["fcf0 (เฉลี่ย 3 ปี)"], "net_debt": inp["net_debt"],
                 "wacc": w["wacc"], "g1": inp["g1 ที่ประมาณได้"], "years1": 10}
    except Exception:
        mc_in = None

    res = extra_methods(data, R, w, shares, price=price, inputs=mc_in, mc_n=a.mc)

    print("\n" + "=" * 72)
    print(f"  {t} — {data.get('info',{}).get('longName','')}")
    print(f"  จัดอยู่กลุ่ม : {res['กลุ่ม']}")
    print("=" * 72)

    play = res["แนวทาง"]
    print(f"\n  ควรใช้  : {', '.join(play['ควรใช้'])}")
    if play["ห้ามใช้"]:
        print(f"  ห้ามใช้ : {', '.join(play['ห้ามใช้'])}")
    print(f"  เหตุผล  : {play['เหตุผล']}")

    if res["methods"]:
        print(f"\n  ราคาปัจจุบัน {price:,.2f}")
        print(f"\n  {'วิธี':<26}{'มูลค่าต่อหุ้น':>16}{'ส่วนต่าง':>12}")
        print("  " + "-" * 56)
        for k, v in res["methods"].items():
            d = (v / price - 1) * 100 if price else np.nan
            print(f"  {k:<26}{v:>16,.2f}{d:>11.1f}%")
    else:
        print("\n  ไม่มีวิธีเพิ่มเติมที่ใช้ได้กับหุ้นตัวนี้")

    ri = res["รายละเอียด"].get("Residual Income")
    if ri and ri.get("ใช้ได้"):
        print(f"\n  [Residual Income]")
        print(f"    มูลค่าทางบัญชีต่อหุ้น   {ri['มูลค่าทางบัญชีต่อหุ้น']:>10,.2f}")
        print(f"    + กำไรส่วนเกินคิดลด     {ri['PV กำไรส่วนเกิน ต่อหุ้น']:>10,.2f}")
        print(f"    ROE เริ่มต้น            {ri['ROE เริ่มต้น (%)']:>10,.1f}%")
        print(f"    ต้นทุนส่วนทุน           {ri['ต้นทุนส่วนทุน (%)']:>10,.1f}%")
        print(f"    สัดส่วนที่มาจากงบดุล    {ri['สัดส่วนจากงบดุล (%)']:>10,.0f}%"
              "   <- ยิ่งสูงยิ่งพึ่งการเดาน้อย")

    mid = res["รายละเอียด"].get("กำไรกลางวัฏจักร")
    if mid and mid.get("ใช้ได้"):
        print(f"\n  [กำไรกลางวัฏจักร]")
        print(f"    อัตรากำไรเฉลี่ย {mid['จำนวนปีที่ใช้']} ปี "
              f"{mid['อัตรากำไรสุทธิเฉลี่ย (%)']:>8,.2f}%")
        print(f"    อัตรากำไรปีล่าสุด          {mid['อัตรากำไรสุทธิปีล่าสุด (%)']:>8,.2f}%")
        print(f"    EPS ปรับฐาน                {mid['EPS ปรับฐาน']:>8,.2f}")
        print(f"    EPS ปีล่าสุด               {mid['EPS ปีล่าสุด']:>8,.2f}")

    ff = res["รายละเอียด"].get("P/FFO")
    if ff and ff.get("ใช้ได้"):
        print(f"\n  [P/FFO]")
        print(f"    FFO ต่อหุ้น         {ff['FFO ต่อหุ้น']:>10,.2f}")
        print(f"    กำไรสุทธิต่อหุ้น    {ff['กำไรสุทธิต่อหุ้น']:>10,.2f}")
        print(f"    P/FFO ปัจจุบัน      {ff['P/FFO ปัจจุบัน']:>10,.1f} เท่า")

    m = res["รายละเอียด"].get("Monte Carlo")
    if m and m.get("ใช้ได้"):
        print(f"\n  [Monte Carlo {m['จำนวนรอบที่สำเร็จ']:,} รอบ]")
        for k, v in m["เปอร์เซ็นไทล์"].items():
            print(f"    {k:<6}{v:>12,.2f}")
        if "โอกาสมูลค่า > ราคา (%)" in m:
            print(f"    โอกาสมูลค่า > ราคาปัจจุบัน : "
                  f"{m['โอกาสมูลค่า > ราคา (%)']:.0f}%")
            print("    (อ่านเป็นความไวต่อสมมติฐาน ไม่ใช่ความน่าจะเป็นจริง)")

    for note in res["หมายเหตุ"]:
        print(f"\n  หมายเหตุ : {note}")
    for name, why in res["ต้องกรอกเอง"]:
        print(f"\n  {name} ต้องกรอกข้อมูลเอง — {why}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
