"""
risk.py — Module 8 : Risk Engine
=================================
ประเมินความเสี่ยง 12 ด้าน

หลักการที่สำคัญที่สุดของไฟล์นี้ — แยกให้ชัดว่าอะไรคำนวณได้ อะไรเดา
--------------------------------------------------------------------
ความเสี่ยงบางด้านวัดจากงบการเงินได้ตรง ๆ บางด้านวัดไม่ได้เลย
ระบบที่ให้คะแนนทั้ง 12 ด้านออกมาเป็นตัวเลขสวย ๆ โดยไม่บอกที่มา
คือระบบที่หลอกผู้ใช้ให้เชื่อในสิ่งที่ไม่มีหลักฐาน

ทุกด้านจึงติดป้ายชัดเจนว่ามาจากไหน :

    [คำนวณ]   วัดจากตัวเลขในงบการเงินโดยตรง — ตรวจสอบย้อนได้ทุกตัว
    [กลุ่ม]   ประเมินจากลักษณะของอุตสาหกรรม — เป็นจุดตั้งต้น ไม่ใช่ข้อสรุป
    [ต้องดูเอง] ไม่มีข้อมูลให้ประเมินอัตโนมัติ — ระบบให้เพียงคำถามที่ควรถาม

12 ด้าน
--------
  1. Financial Risk    [คำนวณ]   หนี้ ความสามารถจ่ายดอกเบี้ย สภาพคล่อง
  2. Business Risk     [คำนวณ]   ความผันผวนของรายได้และกำไร
  3. Competition       [คำนวณ]   แนวโน้มอัตรากำไรและ ROIC
  4. Country Risk      [กลุ่ม]   ประเทศที่จดทะเบียน
  5. Currency Risk     [กลุ่ม]   ความเสี่ยงอัตราแลกเปลี่ยน
  6. Legal/Regulatory  [กลุ่ม]   ระดับการกำกับดูแลของอุตสาหกรรม
  7. Technology Risk   [กลุ่ม]   ความเร็วการเปลี่ยนเทคโนโลยี
  8. Disruption Risk   [กลุ่ม]   โอกาสถูกโมเดลธุรกิจใหม่แทนที่
  9. Key Person Risk   [ต้องดูเอง] การพึ่งพาบุคคลสำคัญ
 10. AI Risk           [กลุ่ม]   ผลกระทบจากปัญญาประดิษฐ์ (ทั้งบวกและลบ)
 11. Cyber Risk        [กลุ่ม]   ความเสี่ยงภัยไซเบอร์
 12. Climate Risk      [กลุ่ม]   ความเสี่ยงจากสภาพภูมิอากาศและกฎเกณฑ์คาร์บอน

การให้คะแนน
------------
0 = ไม่มีความเสี่ยง · 100 = เสี่ยงสูงสุด
คะแนนรวมถ่วงน้ำหนักตามความสำคัญ โดยด้านที่ [คำนวณ] ได้น้ำหนักมากกว่า
เพราะมีหลักฐานรองรับ

วิธีใช้จาก Terminal
-------------------
    python3 risk.py PTT.BK
    python3 risk.py AAPL --json
"""

import json
import sys

import numpy as np
import pandas as pd

SRC_CALC = "คำนวณ"
SRC_GROUP = "กลุ่ม"
SRC_MANUAL = "ต้องดูเอง"

LEVELS = [(20, "ต่ำ"), (40, "ค่อนข้างต่ำ"), (60, "ปานกลาง"),
          (80, "ค่อนข้างสูง"), (101, "สูง")]


def level(score):
    if score is None:
        return "ประเมินไม่ได้"
    for cut, name in LEVELS:
        if score < cut:
            return name
    return "สูง"


def _s(raw, key):
    v = raw.get(key)
    if v is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(pd.Series(v), errors="coerce").dropna()


def _last(tbl, name):
    try:
        s = pd.to_numeric(tbl.loc[name], errors="coerce").dropna()
        return float(s.iloc[-1]) if len(s) else None
    except Exception:
        return None


def _series(tbl, name):
    try:
        return pd.to_numeric(tbl.loc[name], errors="coerce").dropna()
    except Exception:
        return pd.Series(dtype=float)


def _score_from(value, bands):
    """
    แปลงค่าเป็นคะแนน 0-100 ตามช่วงที่กำหนด

    bands : list ของ (ค่าขีดแบ่ง, คะแนน) เรียงจากดีไปแย่
    """
    if value is None or not np.isfinite(value):
        return None
    for cut, sc in bands:
        if value <= cut:
            return sc
    return bands[-1][1]


# ===========================================================================
# 1) Financial Risk — คำนวณจากงบล้วน
# ===========================================================================

def financial_risk(R) -> dict:
    tbl = R.get("table")
    detail, scores = [], []

    de = _last(tbl, "D/E (หนี้มีดอกเบี้ย)")
    s = _score_from(de, [(0.3, 10), (0.7, 25), (1.2, 45), (2.0, 70), (99, 90)])
    if s is not None:
        scores.append(s)
        detail.append({"ตัวชี้วัด": "D/E (หนี้มีดอกเบี้ย)", "ค่า": de,
                       "คะแนนเสี่ยง": s,
                       "เกณฑ์": "≤0.3 ต่ำมาก · ≤0.7 ปกติ · ≤1.2 เริ่มสูง · >2 อันตราย"})

    ic = _last(tbl, "Interest Coverage")
    s = _score_from(-ic if ic is not None else None,
                    [(-15, 5), (-8, 20), (-4, 45), (-2, 75), (0, 95)])
    if s is not None:
        scores.append(s)
        detail.append({"ตัวชี้วัด": "Interest Coverage", "ค่า": ic, "คะแนนเสี่ยง": s,
                       "เกณฑ์": "≥15 เท่า ปลอดภัยมาก · <2 เท่า เสี่ยงผิดนัดชำระ"})

    nd = _last(tbl, "Net Debt / EBITDA")
    s = _score_from(nd, [(0, 5), (1.5, 20), (3.0, 45), (4.5, 70), (99, 90)])
    if s is not None:
        scores.append(s)
        detail.append({"ตัวชี้วัด": "Net Debt / EBITDA", "ค่า": nd, "คะแนนเสี่ยง": s,
                       "เกณฑ์": "ติดลบ = เงินสดมากกว่าหนี้ · >3 เท่า เริ่มตึง"})

    cr = _last(tbl, "Current Ratio")
    s = _score_from(-cr if cr is not None else None,
                    [(-2.0, 10), (-1.5, 25), (-1.0, 50), (-0.8, 75), (0, 90)])
    if s is not None:
        scores.append(s)
        detail.append({"ตัวชี้วัด": "Current Ratio", "ค่า": cr, "คะแนนเสี่ยง": s,
                       "เกณฑ์": "≥2 สบาย · <1 สินทรัพย์หมุนเวียนไม่พอจ่ายหนี้ระยะสั้น"})

    # ความสม่ำเสมอของ FCF — ปีที่ FCF ติดลบคือปีที่ต้องหาเงินจากที่อื่น
    fcf = _s(R.get("raw", {}), "fcf")
    if len(fcf):
        neg = float((fcf <= 0).mean())
        s = _score_from(neg, [(0.0, 5), (0.2, 25), (0.4, 50), (0.6, 75), (1.0, 95)])
        scores.append(s)
        detail.append({"ตัวชี้วัด": "สัดส่วนปีที่ FCF ติดลบ", "ค่า": neg * 100,
                       "คะแนนเสี่ยง": s,
                       "เกณฑ์": "0% = สร้างเงินสดได้ทุกปี · >40% = พึ่งการกู้หรือเพิ่มทุน"})

    return {"คะแนน": float(np.mean(scores)) if scores else None,
            "ที่มา": SRC_CALC, "รายละเอียด": detail}


# ===========================================================================
# 2) Business Risk — ความผันผวนของผลประกอบการ
# ===========================================================================

def business_risk(R) -> dict:
    raw = R.get("raw", {})
    rev = _s(raw, "revenue")
    net = _s(raw, "net_income")
    detail, scores = [], []

    if len(rev) >= 3:
        # ค่าสัมประสิทธิ์ความผันผวนของอัตราโตรายได้
        g = rev.pct_change().dropna()
        cv = float(g.std()) if len(g) > 1 else None
        s = _score_from(cv, [(0.05, 10), (0.12, 30), (0.25, 55), (0.40, 78), (9, 92)])
        if s is not None:
            scores.append(s)
            detail.append({"ตัวชี้วัด": "ความผันผวนของอัตราโตรายได้",
                           "ค่า": cv * 100 if cv else None, "คะแนนเสี่ยง": s,
                           "เกณฑ์": "ยิ่งต่ำยิ่งคาดการณ์ได้ · >25% = รายได้เหวี่ยงแรง"})

    nm = _series(R.get("table"), "Net Margin")
    if len(nm) >= 3:
        sd = float(nm.std())
        s = _score_from(sd, [(1.5, 10), (3.0, 30), (6.0, 55), (10.0, 78), (99, 92)])
        scores.append(s)
        detail.append({"ตัวชี้วัด": "ส่วนเบี่ยงเบนอัตรากำไรสุทธิ (%)", "ค่า": sd,
                       "คะแนนเสี่ยง": s,
                       "เกณฑ์": "แกว่งน้อย = ควบคุมต้นทุนและราคาขายได้"})

    if len(net) >= 3:
        loss = float((net <= 0).mean())
        s = _score_from(loss, [(0.0, 5), (0.15, 35), (0.3, 60), (0.5, 82), (1.0, 96)])
        scores.append(s)
        detail.append({"ตัวชี้วัด": "สัดส่วนปีที่ขาดทุน", "ค่า": loss * 100,
                       "คะแนนเสี่ยง": s, "เกณฑ์": "ยิ่งมีปีขาดทุนบ่อย ยิ่งเปราะ"})

    return {"คะแนน": float(np.mean(scores)) if scores else None,
            "ที่มา": SRC_CALC, "รายละเอียด": detail}


# ===========================================================================
# 3) Competition Risk — ดูจากแนวโน้มอัตรากำไรและผลตอบแทน
# ===========================================================================

def competition_risk(R) -> dict:
    tbl = R.get("table")
    detail, scores = [], []

    def _trend(name, label, good_up=True):
        s = _series(tbl, name)
        if len(s) < 3:
            return
        # ความชันของเส้นแนวโน้มเทียบกับค่าเฉลี่ย — บอกทิศทางแบบไม่ขึ้นกับหน่วย
        x = np.arange(len(s))
        slope = float(np.polyfit(x, s.values, 1)[0])
        base = abs(float(s.mean())) or 1.0
        rel = slope / base * 100          # % ต่อปี
        sc = _score_from(-rel if good_up else rel,
                         [(-2, 15), (-0.5, 30), (0.5, 50), (2, 72), (99, 88)])
        if sc is not None:
            scores.append(sc)
            detail.append({"ตัวชี้วัด": label, "ค่า": rel, "คะแนนเสี่ยง": sc,
                           "เกณฑ์": "แนวโน้มลด = คูเมืองกำลังถูกกัดกร่อน"})

    _trend("Gross Margin", "แนวโน้มอัตรากำไรขั้นต้น (% ต่อปี)")
    _trend("Net Margin", "แนวโน้มอัตรากำไรสุทธิ (% ต่อปี)")
    _trend("ROIC", "แนวโน้ม ROIC (% ต่อปี)")

    # ระดับ ROIC เทียบต้นทุนเงินทุนคร่าว ๆ — ต่ำกว่า 8% แปลว่าแทบไม่สร้างมูลค่า
    roic = _last(tbl, "ROIC")
    sc = _score_from(-roic if roic is not None else None,
                     [(-20, 10), (-12, 28), (-8, 50), (-4, 72), (0, 90)])
    if sc is not None:
        scores.append(sc)
        detail.append({"ตัวชี้วัด": "ROIC ปีล่าสุด (%)", "ค่า": roic, "คะแนนเสี่ยง": sc,
                       "เกณฑ์": "≥20% มีคูเมืองแข็ง · <8% แข่งขันรุนแรง"})

    return {"คะแนน": float(np.mean(scores)) if scores else None,
            "ที่มา": SRC_CALC, "รายละเอียด": detail}


# ===========================================================================
# 4-12) ความเสี่ยงที่ประเมินจากลักษณะอุตสาหกรรม
# ===========================================================================

# คะแนนตั้งต้นรายอุตสาหกรรม
# ตัวเลขเหล่านี้เป็น **การประเมินเชิงคุณภาพ** ไม่ได้มาจากข้อมูลของบริษัท
# จึงเป็นจุดตั้งต้นให้ผู้ใช้ปรับ ไม่ใช่ข้อสรุป
_SECTOR_RISK = {
    #                        legal tech disr  ai cyber climate
    "technology":            (45,  80,  70,  65,  75,  25),
    "communication services":(55,  65,  60,  70,  65,  25),
    "financial services":    (85,  55,  60,  60,  90,  30),
    "healthcare":            (80,  55,  45,  45,  70,  25),
    "energy":                (75,  45,  60,  25,  55,  95),
    "utilities":             (85,  35,  35,  20,  70,  75),
    "basic materials":       (65,  30,  30,  20,  40,  85),
    "industrials":           (55,  45,  40,  40,  50,  60),
    "consumer cyclical":     (45,  50,  55,  45,  55,  40),
    "consumer defensive":    (55,  30,  30,  30,  45,  45),
    "real estate":           (60,  25,  30,  25,  35,  55),
}
_DEFAULT_RISK = (55, 45, 45, 40, 55, 45)

# ความเสี่ยงประเทศ — สะท้อนเสถียรภาพการเมือง กฎหมาย และสภาพคล่องตลาด
_COUNTRY_RISK = {
    "TH": (55, "ตลาดเกิดใหม่ · การเมืองมีความไม่แน่นอนเป็นระยะ "
                "· สภาพคล่องหุ้นเล็กต่ำ"),
    "US": (20, "ตลาดพัฒนาแล้ว · กฎหมายคุ้มครองผู้ถือหุ้นแข็งแรง · สภาพคล่องสูง"),
    "SG": (25, "ตลาดพัฒนาแล้ว · ธรรมาภิบาลดี"),
    "JP": (25, "ตลาดพัฒนาแล้ว · เศรษฐกิจโตช้า"),
    "CN": (70, "ความเสี่ยงเชิงนโยบายรัฐสูง · ความโปร่งใสจำกัด"),
    "HK": (50, "เชื่อมโยงกับนโยบายจีน"),
    "VN": (65, "ตลาดชายขอบ · สภาพคล่องและการเข้าถึงจำกัด"),
}


def _sector_key(data):
    s = str((data.get("info", {}) or {}).get("sector") or "").lower()
    return s if s in _SECTOR_RISK else None


def qualitative_risks(data, R) -> dict:
    """
    ความเสี่ยง 9 ด้านที่ประเมินจากกลุ่มธุรกิจและประเทศ

    ย้ำอีกครั้ง : ตัวเลขเหล่านี้ **ไม่ได้มาจากงบการเงินของบริษัท**
    เป็นค่าตั้งต้นตามลักษณะอุตสาหกรรม ผู้ใช้ควรปรับตามความรู้ที่มี
    """
    info = data.get("info", {}) or {}
    key = _sector_key(data)
    legal, tech, disr, ai, cyber, climate = _SECTOR_RISK.get(key, _DEFAULT_RISK)
    sector_name = info.get("sector") or "ไม่ระบุ"

    # ประเทศ — ดูจาก ticker ก่อน แล้วค่อยดู info
    tk = str(data.get("ticker") or "")
    cc = "TH" if tk.upper().endswith(".BK") else (info.get("country") or "US")
    cc = {"Thailand": "TH", "United States": "US", "Singapore": "SG",
          "Japan": "JP", "China": "CN", "Hong Kong": "HK",
          "Vietnam": "VN"}.get(cc, cc if len(str(cc)) == 2 else "US")
    c_score, c_note = _COUNTRY_RISK.get(cc, (50, "ไม่มีข้อมูลประเทศนี้"))

    # ความเสี่ยงค่าเงิน — บริษัทไทยที่รายงานเป็นสกุลอื่น หรือพึ่งการส่งออก
    cur = str(info.get("currency") or "")
    fx = 35
    fx_note = "รายได้และต้นทุนอยู่ในสกุลเงินเดียวกันเป็นหลัก"
    if cc == "TH" and cur and cur != "THB":
        fx, fx_note = 70, f"รายงานเป็น {cur} แต่ซื้อขายเป็นบาท — มีความเสี่ยงอัตราแลกเปลี่ยน"
    elif key in ("energy", "basic materials", "technology"):
        fx = 60
        fx_note = ("อุตสาหกรรมนี้อ้างอิงราคาสินค้าโภคภัณฑ์หรือส่งออกเป็นหลัก "
                   "รายได้จึงผูกกับค่าเงิน")

    return {
        "Country Risk": {"คะแนน": c_score, "ที่มา": SRC_GROUP,
                         "คำอธิบาย": f"{cc} — {c_note}"},
        "Currency Risk": {"คะแนน": fx, "ที่มา": SRC_GROUP, "คำอธิบาย": fx_note},
        "Legal/Regulatory": {"คะแนน": legal, "ที่มา": SRC_GROUP,
                             "คำอธิบาย": f"อุตสาหกรรม {sector_name} — "
                                          "ยิ่งถูกกำกับมาก กฎใหม่ยิ่งกระทบแรง"},
        "Technology Risk": {"คะแนน": tech, "ที่มา": SRC_GROUP,
                            "คำอธิบาย": "ความเร็วที่เทคโนโลยีในอุตสาหกรรมนี้เปลี่ยน"},
        "Disruption Risk": {"คะแนน": disr, "ที่มา": SRC_GROUP,
                            "คำอธิบาย": "โอกาสถูกโมเดลธุรกิจใหม่เข้ามาแทนที่"},
        "AI Risk": {"คะแนน": ai, "ที่มา": SRC_GROUP,
                    "คำอธิบาย": "ปัญญาประดิษฐ์อาจทั้งลดต้นทุนและทำลายความได้เปรียบ "
                                "— คะแนนสูงแปลว่ากระทบแรง ไม่ได้แปลว่าแย่เสมอไป"},
        "Cyber Risk": {"คะแนน": cyber, "ที่มา": SRC_GROUP,
                       "คำอธิบาย": "ยิ่งถือข้อมูลลูกค้าหรือเงินมาก ยิ่งเป็นเป้าหมาย"},
        "Climate Risk": {"คะแนน": climate, "ที่มา": SRC_GROUP,
                         "คำอธิบาย": "ทั้งความเสี่ยงทางกายภาพและกฎเกณฑ์คาร์บอนที่กำลังมา"},
    }


def key_person_risk(data) -> dict:
    """
    ความเสี่ยงจากการพึ่งพาบุคคลสำคัญ — ไม่มีข้อมูลให้ประเมินอัตโนมัติ

    งบการเงินไม่บอกว่าใครเป็นคนสำคัญ หรือถ้าคนนั้นออกไปจะเกิดอะไรขึ้น
    ระบบจึงให้เพียงคำถามที่ควรหาคำตอบ ไม่ให้คะแนนลอย ๆ
    """
    return {
        "คะแนน": None,
        "ที่มา": SRC_MANUAL,
        "คำอธิบาย": "งบการเงินไม่มีข้อมูลด้านนี้ — ต้องอ่านรายงานประจำปีเอง",
        "คำถามที่ควรหาคำตอบ": [
            "ผู้ก่อตั้งยังบริหารอยู่ไหม และอายุเท่าไร",
            "มีแผนสืบทอดตำแหน่งที่ประกาศชัดเจนหรือยัง",
            "ครอบครัวถือหุ้นเกิน 50% หรือไม่ — ถ้าใช่ ผลประโยชน์ตรงกับรายย่อยไหม",
            "ผู้บริหารระดับสูงเปลี่ยนบ่อยผิดปกติหรือไม่ในช่วง 3 ปี",
            "รายได้พึ่งลูกค้ารายใหญ่ไม่กี่รายหรือเปล่า (ดูหมายเหตุประกอบงบ)",
        ],
    }


# ===========================================================================
# รวมทุกด้าน
# ===========================================================================

# น้ำหนัก — ด้านที่คำนวณจากงบได้น้ำหนักมากกว่า เพราะมีหลักฐานรองรับ
WEIGHTS = {
    "Financial Risk": 3.0,
    "Business Risk": 2.5,
    "Competition": 2.0,
    "Country Risk": 1.5,
    "Currency Risk": 1.0,
    "Legal/Regulatory": 1.0,
    "Technology Risk": 1.0,
    "Disruption Risk": 1.0,
    "AI Risk": 0.8,
    "Cyber Risk": 0.7,
    "Climate Risk": 0.7,
    "Key Person Risk": 0.0,      # ไม่ให้คะแนน จึงไม่ถ่วงน้ำหนัก
}


def assess(data, R) -> dict:
    """ประเมินความเสี่ยงครบ 12 ด้าน"""
    out = {"ticker": data.get("ticker"), "ด้าน": {}}

    out["ด้าน"]["Financial Risk"] = financial_risk(R)
    out["ด้าน"]["Business Risk"] = business_risk(R)
    out["ด้าน"]["Competition"] = competition_risk(R)
    out["ด้าน"].update(qualitative_risks(data, R))
    out["ด้าน"]["Key Person Risk"] = key_person_risk(data)

    # คะแนนรวมถ่วงน้ำหนัก
    num = den = 0.0
    for name, d in out["ด้าน"].items():
        sc, wt = d.get("คะแนน"), WEIGHTS.get(name, 1.0)
        if sc is not None and wt > 0:
            num += sc * wt
            den += wt
    total = num / den if den else None

    out["คะแนนรวม"] = total
    out["ระดับ"] = level(total)

    # แยกให้เห็นว่าคะแนนรวมมาจากหลักฐานแค่ไหน
    calc_w = sum(WEIGHTS[n] for n, d in out["ด้าน"].items()
                 if d.get("ที่มา") == SRC_CALC and d.get("คะแนน") is not None)
    out["สัดส่วนจากตัวเลขจริง (%)"] = calc_w / den * 100 if den else 0.0

    # 3 ด้านที่เสี่ยงที่สุด
    ranked = sorted(((n, d["คะแนน"]) for n, d in out["ด้าน"].items()
                     if d.get("คะแนน") is not None),
                    key=lambda x: x[1], reverse=True)
    out["เสี่ยงสูงสุด"] = ranked[:3]
    out["เสี่ยงต่ำสุด"] = ranked[-3:][::-1]

    out["ตารางสรุป"] = pd.DataFrame([
        {"ด้าน": n, "คะแนน": d.get("คะแนน"), "ระดับ": level(d.get("คะแนน")),
         "ที่มา": d.get("ที่มา"), "น้ำหนัก": WEIGHTS.get(n, 1.0)}
        for n, d in out["ด้าน"].items()
    ]).set_index("ด้าน")
    return out


# ---------------------------------------------------------------------------
# ใช้จาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="ประเมินความเสี่ยง 12 ด้าน")
    p.add_argument("ticker")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()

    from data_layer import get_stock_data
    from ratios import compute_ratios

    t = a.ticker.upper()
    print(f"\nกำลังดึงข้อมูล {t} ...")
    data = get_stock_data(t)
    R = compute_ratios(data)
    res = assess(data, R)

    if a.json:
        clean = {k: v for k, v in res.items() if k != "ตารางสรุป"}
        print(json.dumps(clean, ensure_ascii=False, indent=1, default=str))
        return 0

    print("\n" + "=" * 76)
    print(f"  {t} — {data.get('info', {}).get('longName', '')}")
    print(f"  คะแนนความเสี่ยงรวม : {res['คะแนนรวม']:.0f} / 100  ({res['ระดับ']})")
    print(f"  มาจากตัวเลขจริง {res['สัดส่วนจากตัวเลขจริง (%)']:.0f}% "
          "ของน้ำหนักทั้งหมด")
    print("=" * 76)

    print(f"\n  {'ด้าน':<22}{'คะแนน':>8}{'ระดับ':>14}{'ที่มา':>14}")
    print("  " + "-" * 58)
    for n, d in res["ด้าน"].items():
        sc = d.get("คะแนน")
        s = f"{sc:.0f}" if sc is not None else "—"
        print(f"  {n:<22}{s:>8}{level(sc):>14}{d.get('ที่มา',''):>14}")

    print("\n  [รายละเอียดด้านที่คำนวณจากงบ]")
    for n in ("Financial Risk", "Business Risk", "Competition"):
        d = res["ด้าน"][n]
        if not d.get("รายละเอียด"):
            continue
        print(f"\n  {n}")
        for it in d["รายละเอียด"]:
            v = it["ค่า"]
            vs = f"{v:,.2f}" if isinstance(v, float) else str(v)
            print(f"    {it['ตัวชี้วัด']:<34}{vs:>10}  เสี่ยง {it['คะแนนเสี่ยง']:.0f}")
            print(f"      {it['เกณฑ์']}")

    kp = res["ด้าน"]["Key Person Risk"]
    print(f"\n  [Key Person Risk — {kp['ที่มา']}]")
    print(f"    {kp['คำอธิบาย']}")
    for q in kp["คำถามที่ควรหาคำตอบ"]:
        print(f"      · {q}")

    print("\n  [3 ด้านที่เสี่ยงที่สุด]")
    for n, sc in res["เสี่ยงสูงสุด"]:
        print(f"    {n:<22}{sc:>6.0f}  ({level(sc)})")

    print("\n  หมายเหตุสำคัญ")
    print("    [คำนวณ]     วัดจากงบการเงินโดยตรง ตรวจสอบย้อนได้")
    print("    [กลุ่ม]     ประเมินจากลักษณะอุตสาหกรรม เป็นจุดตั้งต้นให้ปรับ")
    print("    [ต้องดูเอง] ไม่มีข้อมูลให้ประเมินอัตโนมัติ\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
