"""
quality.py — Module 2-5 : คุณภาพกิจการและการให้คะแนนแบบกูรู
==============================================================
    Module 2  Quality Business Engine  (25 หัวข้อ)
    Module 3  Buffett Score            (100 คะแนน)
    Module 4  Peter Lynch Score
    Module 5  Howard Marks Cycle Analysis

กฎเหล็กของไฟล์นี้ — ต้องบอกเสมอว่าคะแนนมาจากไหน
--------------------------------------------------
หัวข้ออย่าง "Brand" "Network Effect" "Corporate Governance" **วัดจากงบไม่ได้**
ระบบที่ให้คะแนน Brand = 78 โดยไม่บอกที่มา คือระบบที่แต่งตัวเลขให้ดูน่าเชื่อถือ

ทุกหัวข้อจึงติดป้าย 3 แบบ

    [คำนวณ]     วัดจากงบการเงินโดยตรง — ตรวจสอบย้อนได้ทุกตัว
    [ตัวแทน]    ใช้ตัวเลขอื่นแทนสิ่งที่วัดตรง ๆ ไม่ได้
                เช่น อัตรากำไรขั้นต้นสูงและนิ่ง = มีอำนาจตั้งราคา = น่าจะมีแบรนด์
                เป็นการอนุมาน ไม่ใช่การวัด — ผิดได้
    [ต้องดูเอง] ไม่มีข้อมูลให้ประเมิน ระบบให้เพียงคำถามที่ควรถาม

คะแนนรวมนับเฉพาะหัวข้อที่ [คำนวณ] และ [ตัวแทน] เท่านั้น
และรายงานเสมอว่าคะแนนนั้นมาจากหลักฐานกี่เปอร์เซ็นต์

วิธีใช้จาก Terminal
-------------------
    python3 quality.py AAPL
    python3 quality.py PTT.BK --module buffett
"""

import sys

import numpy as np
import pandas as pd

CALC = "คำนวณ"
PROXY = "ตัวแทน"
MANUAL = "ต้องดูเอง"


# ---------------------------------------------------------------------------
# ตัวช่วย
# ---------------------------------------------------------------------------

def _row(R, name):
    try:
        return pd.to_numeric(R["table"].loc[name], errors="coerce").dropna()
    except Exception:
        return pd.Series(dtype=float)


def _last(R, name):
    s = _row(R, name)
    return float(s.iloc[-1]) if len(s) else None


def _ser(R, key):
    v = (R.get("raw") or {}).get(key)
    if v is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(pd.Series(v), errors="coerce").dropna()


def _grade(v, bands):
    """
    แปลงค่าเป็นคะแนน 0-100

    bands : list ของ (ขีดแบ่ง, คะแนน) เรียงจากค่าน้อยไปมาก
            ค่าที่ <= ขีดแบ่งแรกได้คะแนนแรก
    """
    if v is None or not np.isfinite(v):
        return None
    for cut, sc in bands:
        if v <= cut:
            return float(sc)
    return float(bands[-1][1])


def _pctile(s: pd.Series, v):
    """ค่าปัจจุบันอยู่เปอร์เซ็นไทล์ที่เท่าไรของประวัติตัวเอง"""
    s = s.dropna()
    if len(s) < 3 or v is None:
        return None
    return float((s <= v).mean() * 100)


def _trend_pct(s: pd.Series):
    """ความชันของแนวโน้มเป็น % ต่อปี เทียบกับค่าเฉลี่ยของตัวเอง"""
    s = s.dropna()
    if len(s) < 3:
        return None
    slope = float(np.polyfit(np.arange(len(s)), s.values, 1)[0])
    base = abs(float(s.mean())) or 1.0
    return slope / base * 100


def _item(name, score, src, evidence="", note=""):
    return {"หัวข้อ": name, "คะแนน": score, "ที่มา": src,
            "หลักฐาน": evidence, "หมายเหตุ": note}


# ===========================================================================
# Module 2 — Quality Business Engine (25 หัวข้อ)
# ===========================================================================

# อุตสาหกรรมที่มีลักษณะเฉพาะบางอย่างโดยธรรมชาติ
# ใช้เป็นค่าตั้งต้นของหัวข้อที่วัดจากงบไม่ได้
_SECTOR_TRAITS = {
    #                          network subscription asset_light
    "technology":              (75,     70,          80),
    "communication services":  (80,     75,          55),
    "financial services":      (60,     45,          75),
    "healthcare":              (35,     40,          55),
    "consumer defensive":      (30,     25,          45),
    "consumer cyclical":       (35,     30,          50),
    "industrials":             (25,     25,          35),
    "energy":                  (15,     15,          15),
    "utilities":               (20,     55,          10),
    "basic materials":         (15,     10,          15),
    "real estate":             (20,     45,          10),
}
_TRAIT_DEFAULT = (30, 30, 45)


def quality_engine(data, R) -> dict:
    """คุณภาพกิจการ 25 หัวข้อ"""
    info = data.get("info", {}) or {}
    sector = str(info.get("sector") or "").lower()
    net_eff, subs, asset_light = _SECTOR_TRAITS.get(sector, _TRAIT_DEFAULT)
    items = []

    gm = _row(R, "Gross Margin")
    om = _row(R, "Operating Margin")
    nm = _row(R, "Net Margin")
    roic = _row(R, "ROIC")
    roe = _row(R, "ROE")
    rev = _ser(R, "revenue")
    shares = _ser(R, "shares_diluted")

    # ---- 1. Moat (รวม) ----
    parts = []
    if len(roic) >= 3:
        parts.append(_grade(-float(roic.mean()),
                            [(-25, 95), (-18, 82), (-12, 65), (-8, 45), (0, 20)]))
    if len(gm) >= 3:
        parts.append(_grade(float(gm.std()),
                            [(2, 90), (4, 75), (7, 55), (12, 35), (99, 15)]))
    if len(roe) >= 3:
        parts.append(_grade(float(roe.std()),
                            [(3, 90), (6, 72), (10, 52), (18, 30), (999, 12)]))
    parts = [p for p in parts if p is not None]
    moat = float(np.mean(parts)) if parts else None
    items.append(_item(
        "Moat (คูเมืองรวม)", moat, CALC,
        f"ROIC เฉลี่ย {roic.mean():.1f}% · GM แกว่ง {gm.std():.1f}% · "
        f"ROE แกว่ง {roe.std():.1f}%" if len(roic) and len(gm) and len(roe) else "",
        "ROIC สูงและสม่ำเสมอ + อัตรากำไรนิ่ง = มีอะไรกันคู่แข่งไว้ได้จริง"))

    # ---- 2. Brand ----
    b = None
    if len(gm) >= 3:
        lvl = _grade(-float(gm.mean()),
                     [(-55, 95), (-40, 80), (-30, 62), (-20, 42), (0, 20)])
        stab = _grade(float(gm.std()), [(2, 90), (4, 72), (8, 50), (99, 25)])
        b = float(np.mean([x for x in (lvl, stab) if x is not None]))
    items.append(_item(
        "Brand", b, PROXY,
        f"อัตรากำไรขั้นต้นเฉลี่ย {gm.mean():.1f}% แกว่ง {gm.std():.1f}%"
        if len(gm) else "",
        "แบรนด์แข็งทำให้ตั้งราคาสูงกว่าคู่แข่งได้โดยลูกค้าไม่หนี "
        "จึงเห็นเป็นอัตรากำไรขั้นต้นที่สูงและนิ่ง — **เป็นการอนุมาน ไม่ใช่การวัด** "
        "โรงงานที่ต้นทุนต่ำมากก็มี GM สูงได้โดยไม่มีแบรนด์"))

    # ---- 3. Switching Cost ----
    sw = None
    if len(rev) >= 4:
        g = rev.pct_change().dropna()
        sw = _grade(float(g.std()), [(0.03, 92), (0.07, 78), (0.15, 55),
                                     (0.30, 30), (9, 12)])
    items.append(_item(
        "Switching Cost", sw, PROXY,
        f"ความผันผวนอัตราโตรายได้ {g.std()*100:.1f}%" if len(rev) >= 4 else "",
        "ถ้าลูกค้าย้ายไปคู่แข่งได้ง่าย รายได้จะเหวี่ยง "
        "รายได้ที่นิ่งมากจึงบ่งชี้ว่าย้ายยาก"))

    # ---- 4. Network Effect ----
    items.append(_item(
        "Network Effect", float(net_eff), PROXY,
        f"กลุ่ม {info.get('sector') or '-'}",
        "ยิ่งมีผู้ใช้มาก ยิ่งมีค่ากับผู้ใช้รายถัดไป — วัดจากงบไม่ได้ "
        "ใช้ลักษณะอุตสาหกรรมเป็นค่าตั้งต้น"))

    # ---- 5. Patent / R&D ----
    rd = _row(R, "R&D / รายได้")
    pat = _grade(-float(rd.mean()), [(-12, 92), (-7, 78), (-3, 58),
                                     (-1, 38), (0, 20)]) if len(rd) else None
    items.append(_item(
        "Patent / R&D", pat, PROXY,
        f"R&D {rd.mean():.1f}% ของรายได้" if len(rd) else "งบไม่แยกค่า R&D",
        "ลงทุนวิจัยมาก = มีโอกาสมีสิทธิบัตรกันคู่แข่ง "
        "แต่ลงทุนมากไม่ได้แปลว่าได้ผล"))

    # ---- 6. Economies of Scale ----
    eos, cor = None, None
    if len(rev) >= 4 and len(om) >= 4:
        n = min(len(rev), len(om))
        a = np.log(rev.iloc[-n:].values.clip(1))
        c_ = om.iloc[-n:].values
        # ต้องมีความแปรปรวนทั้งสองชุด ไม่งั้นสหสัมพันธ์เป็น 0/0
        # (อัตรากำไรที่คงที่เป๊ะทุกปีเกิดได้จริงในข้อมูลที่ปัดเศษมาแล้ว)
        if a.std() > 0 and c_.std() > 0:
            # ถ้ารายได้โตแล้วอัตรากำไรดำเนินงานดีขึ้น = ประหยัดต่อขนาดจริง
            cor = float(np.corrcoef(a, c_)[0, 1])
            eos = _grade(-cor, [(-0.7, 92), (-0.4, 76), (-0.1, 55),
                                (0.3, 32), (2, 15)])
    items.append(_item(
        "Economies of Scale", eos, PROXY,
        f"สหสัมพันธ์ระหว่างขนาดรายได้กับอัตรากำไรดำเนินงาน {cor:+.2f}"
        if eos is not None else "",
        "ยิ่งขายมากยิ่งกำไรดีขึ้น = ต้นทุนคงที่ถูกกระจาย"))

    # ---- 7. Cost Advantage ----
    ca = _grade(-float(om.mean()), [(-25, 92), (-15, 78), (-10, 58),
                                    (-5, 38), (0, 18)]) if len(om) else None
    items.append(_item(
        "Cost Advantage", ca, PROXY,
        f"อัตรากำไรดำเนินงานเฉลี่ย {om.mean():.1f}%" if len(om) else "",
        "อัตรากำไรดำเนินงานสูงกว่าอุตสาหกรรมมัก มาจากต้นทุนที่ต่ำกว่า"))

    # ---- 8. Distribution ----
    items.append(_item(
        "Distribution", None, MANUAL, "",
        "ต้องดูจำนวนสาขา ช่องทางขาย และพันธมิตร ในรายงานประจำปี"))

    # ---- 9. Customer Loyalty ----
    cl = None
    if len(rev) >= 4:
        down = float((rev.pct_change().dropna() < 0).mean())
        cl = _grade(down, [(0.0, 90), (0.15, 72), (0.30, 50), (0.5, 28), (1, 12)])
    items.append(_item(
        "Customer Loyalty", cl, PROXY,
        f"สัดส่วนปีที่รายได้ลดลง {down*100:.0f}%" if cl is not None else "",
        "ลูกค้าที่ภักดีทำให้รายได้ไม่ตกแม้เศรษฐกิจไม่ดี"))

    # ---- 10-11. Recurring Revenue / Subscription ----
    items.append(_item(
        "Recurring Revenue", None, MANUAL, "",
        "งบรวมไม่แยกรายได้ประจำกับรายได้ครั้งเดียว "
        "ต้องอ่านหมายเหตุประกอบงบหรือคำบรรยายผลประกอบการ"))
    items.append(_item(
        "Subscription", float(subs), PROXY,
        f"กลุ่ม {info.get('sector') or '-'}",
        "สัดส่วนรายได้แบบสมาชิกโดยทั่วไปของอุตสาหกรรมนี้"))

    # ---- 12. Pricing Power ----
    pp = None
    tr = _trend_pct(gm)
    if tr is not None:
        pp = _grade(-tr, [(-1.5, 90), (-0.3, 75), (0.3, 55), (1.5, 32), (99, 15)])
    items.append(_item(
        "Pricing Power", pp, PROXY,
        f"แนวโน้มอัตรากำไรขั้นต้น {tr:+.2f}% ต่อปี" if tr is not None else "",
        "ถ้าขึ้นราคาตามต้นทุนได้ อัตรากำไรขั้นต้นจะไม่ลดแม้เงินเฟ้อสูง"))

    # ---- 13-14. Capital Intensity / Asset Light ----
    cx = _row(R, "CapEx / OCF")
    at = _row(R, "Asset Turnover")
    ci = _grade(float(cx.mean()) if len(cx) else None,
                [(0.15, 92), (0.30, 76), (0.50, 55), (0.75, 32), (99, 12)])
    items.append(_item(
        "Capital Intensity", ci, CALC,
        f"CapEx / OCF เฉลี่ย {cx.mean():.2f}" if len(cx) else "",
        "ยิ่งต้องเอาเงินสดไปลงทุนซ้ำมาก ยิ่งเหลือให้ผู้ถือหุ้นน้อย "
        "(คะแนนสูง = ใช้เงินลงทุนน้อย = ดี)"))
    al = None
    if len(at):
        al = _grade(-float(at.mean()), [(-1.5, 90), (-1.0, 75), (-0.7, 55),
                                        (-0.4, 35), (0, 18)])
        al = float(np.mean([al, asset_light]))
    items.append(_item(
        "Asset Light", al, PROXY,
        f"Asset Turnover เฉลี่ย {at.mean():.2f}" if len(at) else "",
        "หมุนสินทรัพย์ได้เร็ว = ใช้ทรัพย์สินน้อยต่อรายได้หนึ่งบาท"))

    # ---- 15-18. เจ้าของและธรรมาภิบาล ----
    insiders = info.get("heldPercentInsiders")
    ins_sc = None
    if insiders is not None:
        p = float(insiders) * 100
        # 5-40% คือช่วงที่ดี : เจ้าของมีส่วนได้เสียแต่ไม่ผูกขาดจนรายย่อยไร้เสียง
        ins_sc = _grade(abs(p - 22), [(8, 92), (15, 75), (25, 55), (35, 32), (99, 15)])
    items.append(_item(
        "Insider Ownership", ins_sc, CALC,
        f"ผู้บริหารและผู้ก่อตั้งถือ {float(insiders)*100:.1f}%"
        if insiders is not None else "ไม่มีข้อมูล",
        "5-40% เหมาะที่สุด — มีส่วนได้เสียร่วมกับรายย่อย "
        "แต่ถ้าถือเกิน 60% รายย่อยแทบไม่มีเสียงในที่ประชุม"))
    items.append(_item(
        "Founder-led", None, MANUAL, "",
        "ผู้ก่อตั้งยังบริหารอยู่ไหม อายุเท่าไร มีแผนสืบทอดหรือยัง"))
    items.append(_item(
        "Family Business", None, MANUAL, "",
        "ครอบครัวถือหุ้นใหญ่หรือไม่ · มีรายการเกี่ยวโยงกับบริษัทในเครือไหม"))
    items.append(_item(
        "Corporate Governance", None, MANUAL, "",
        "หุ้นไทยดูคะแนน CGR ของ IOD ได้ · ดูสัดส่วนกรรมการอิสระ "
        "และประวัติการถูก ก.ล.ต. ลงโทษ"))
    items.append(_item(
        "ESG", None, MANUAL, "",
        "หุ้นไทยดูรายชื่อ SET ESG Ratings · หุ้นสหรัฐดู MSCI/Sustainalytics"))

    # ---- 19-20. ผู้บริหารและการจัดสรรเงินทุน ----
    ca_sc = None
    ev = []
    if len(roic):
        ca_sc = _grade(-float(roic.mean()),
                       [(-20, 92), (-14, 78), (-10, 58), (-6, 35), (0, 15)])
        ev.append(f"ROIC เฉลี่ย {roic.mean():.1f}%")
    g_sh = None
    if len(shares) >= 3:
        g_sh = (float(shares.iloc[-1]) / float(shares.iloc[0])) ** (
            1 / (len(shares) - 1)) - 1
        ev.append(f"จำนวนหุ้นเปลี่ยน {g_sh*100:+.1f}%/ปี")
        sh_sc = _grade(g_sh * 100, [(-2, 92), (0, 75), (1.5, 52), (4, 28), (99, 10)])
        ca_sc = float(np.mean([x for x in (ca_sc, sh_sc) if x is not None]))
    items.append(_item(
        "Capital Allocation", ca_sc, CALC, " · ".join(ev),
        "ลงทุนแล้วได้ ROIC สูง + ลดจำนวนหุ้น = จัดสรรเงินเก่ง  \n"
        "เพิ่มทุนบ่อยโดย ROIC ต่ำ = ทำลายมูลค่าผู้ถือหุ้น"))
    items.append(_item(
        "Management Quality", ca_sc, PROXY,
        "อนุมานจากผลงานการจัดสรรเงินทุน",
        "ผลงานตัวเลขบอกได้แค่ส่วนหนึ่ง — ความซื่อสัตย์และวิสัยทัศน์ "
        "ต้องอ่านจดหมายถึงผู้ถือหุ้นย้อนหลังหลายปีเอง"))
    items.append(_item(
        "Share Buyback",
        _grade(g_sh * 100 if g_sh is not None else None,
               [(-3, 95), (-1, 82), (0.5, 60), (3, 30), (99, 10)]),
        CALC,
        f"จำนวนหุ้นเปลี่ยน {g_sh*100:+.2f}% ต่อปี" if g_sh is not None else "",
        "ซื้อหุ้นคืนตอนราคาถูก = คืนมูลค่าให้ผู้ถือหุ้น "
        "· ซื้อตอนแพงหรือเพื่อชดเชย ESOP = ทำลายมูลค่า"))
    items.append(_item(
        "Compensation", None, MANUAL, "",
        "ค่าตอบแทนผู้บริหารผูกกับผลงานระยะยาวหรือแค่ราคาหุ้นระยะสั้น "
        "· ดูในแบบ 56-1 หรือ DEF 14A"))

    # ---- 21-22. คุณภาพบัญชีและกำไร ----
    ocf_ni = _row(R, "OCF / กำไรสุทธิ")
    acc = _row(R, "Accrual Ratio")
    aq = None
    ev = []
    if len(ocf_ni):
        aq = _grade(-float(ocf_ni.mean()),
                    [(-1.4, 92), (-1.1, 80), (-0.9, 58), (-0.7, 32), (0, 12)])
        ev.append(f"OCF/กำไรสุทธิ เฉลี่ย {ocf_ni.mean():.2f} เท่า")
    if len(acc):
        a2 = _grade(abs(float(acc.mean())),
                    [(0.03, 92), (0.07, 76), (0.12, 52), (0.20, 28), (9, 10)])
        aq = float(np.mean([x for x in (aq, a2) if x is not None]))
        ev.append(f"Accrual Ratio เฉลี่ย {acc.mean():+.3f}")
    items.append(_item(
        "Accounting Quality", aq, CALC, " · ".join(ev),
        "กำไรที่แปลงเป็นเงินสดได้จริงคือกำไรที่เชื่อได้ "
        "· Accrual สูง = กำไรทางบัญชีมากกว่าเงินสดที่เข้าจริง"))
    fcf_ni = _row(R, "FCF / กำไรสุทธิ")
    eq_sc = _grade(-float(fcf_ni.mean()) if len(fcf_ni) else None,
                   [(-1.0, 92), (-0.7, 78), (-0.5, 55), (-0.2, 30), (99, 10)])
    items.append(_item(
        "Earnings Quality", eq_sc, CALC,
        f"FCF/กำไรสุทธิ เฉลี่ย {fcf_ni.mean():.2f} เท่า" if len(fcf_ni) else "",
        "กำไรที่เหลือเป็นเงินสดอิสระจริงหลังลงทุนแล้ว"))

    return _summarize("Quality Business Engine", items)


def _summarize(title, items):
    scored = [i for i in items if i["คะแนน"] is not None]
    calc = [i for i in scored if i["ที่มา"] == CALC]
    total = float(np.mean([i["คะแนน"] for i in scored])) if scored else None
    return {
        "ชื่อโมดูล": title,
        "คะแนนรวม": total,
        "จำนวนหัวข้อ": len(items),
        "ให้คะแนนได้": len(scored),
        "จากงบโดยตรง": len(calc),
        "ต้องดูเอง": len([i for i in items if i["ที่มา"] == MANUAL]),
        "สัดส่วนจากงบ (%)": len(calc) / len(scored) * 100 if scored else 0.0,
        "รายการ": items,
        "ตาราง": pd.DataFrame(items).set_index("หัวข้อ"),
    }


# ===========================================================================
# Module 3 — Buffett Score (100 คะแนน)
# ===========================================================================

# น้ำหนักรวม 100 พอดี
BUFFETT_WEIGHTS = {
    "Owner Earnings": 12,
    "ROE Consistency": 12,
    "ROIC": 12,
    "Margin Stability": 10,
    "Debt": 10,
    "FCF": 10,
    "Intrinsic Value (ส่วนเผื่อความปลอดภัย)": 10,
    "Capital Allocation": 8,
    "Management": 6,
    "Predictability": 6,
    "Moat": 4,
}


def buffett_score(data, R, v=None, q=None) -> dict:
    """
    ให้คะแนนตามหลัก 11 ข้อของ Warren Buffett เต็ม 100

    v : ผลจาก valuation.value_stock (ใช้หา Intrinsic Value) — ไม่มีก็ได้
    q : ผลจาก quality_engine (ใช้หา Moat) — ไม่มีก็คำนวณใหม่
    """
    q = q or quality_engine(data, R)
    qmap = {i["หัวข้อ"]: i["คะแนน"] for i in q["รายการ"]}
    items = []

    roe = _row(R, "ROE")
    roic = _row(R, "ROIC")
    gm = _row(R, "Gross Margin")
    fcf = _ser(R, "fcf")
    own = _row(R, "Owner Earnings")
    rev = _ser(R, "revenue")
    eps = _ser(R, "eps")

    # 1. Owner Earnings — เงินสดที่เจ้าของเอาออกได้จริงโดยธุรกิจไม่ทรุด
    oe = None
    ev = ""
    if len(own):
        pos = float((own > 0).mean())
        grow = None
        if len(own) >= 3 and float(own.iloc[0]) > 0 and float(own.iloc[-1]) > 0:
            grow = (float(own.iloc[-1]) / float(own.iloc[0])) ** (
                1 / (len(own) - 1)) - 1
        s1 = _grade(-pos, [(-1.0, 95), (-0.8, 75), (-0.6, 50), (-0.4, 28), (0, 8)])
        s2 = _grade(-(grow * 100) if grow is not None else None,
                    [(-12, 95), (-7, 78), (-3, 58), (0, 38), (99, 15)])
        oe = float(np.mean([x for x in (s1, s2) if x is not None]))
        ev = f"เป็นบวก {pos*100:.0f}% ของปี"
        if grow is not None:
            ev += f" · โตเฉลี่ย {grow*100:+.1f}%/ปี"
    items.append(_item("Owner Earnings", oe, CALC, ev,
                       "Buffett : กำไรสุทธิ + ค่าเสื่อม − ค่าลงทุนที่จำเป็น"
                       "เพื่อรักษาความสามารถแข่งขัน"))

    # 2. ROE Consistency
    rc = None
    ev = ""
    if len(roe) >= 3:
        hi = float((roe >= 15).mean())
        sd = float(roe.std())
        s1 = _grade(-hi, [(-1.0, 95), (-0.8, 80), (-0.5, 55), (-0.2, 30), (0, 10)])
        s2 = _grade(sd, [(3, 92), (6, 75), (10, 52), (18, 28), (999, 10)])
        rc = float(np.mean([s1, s2]))
        ev = f"ROE ≥15% ใน {hi*100:.0f}% ของปี · ส่วนเบี่ยงเบน {sd:.1f}%"
    items.append(_item("ROE Consistency", rc, CALC, ev,
                       "Buffett มองความสม่ำเสมอสำคัญกว่าค่าสูงสุด "
                       "เพราะพยากรณ์อนาคตได้ดีกว่า"))

    # 3. ROIC
    ri = _grade(-float(roic.mean()) if len(roic) else None,
                [(-20, 95), (-15, 82), (-11, 62), (-8, 40), (0, 15)])
    items.append(_item("ROIC", ri, CALC,
                       f"เฉลี่ย {roic.mean():.1f}%" if len(roic) else "",
                       "ผลตอบแทนจากเงินทุนทั้งหมด — ต้องสูงกว่าต้นทุนเงินทุน"
                       "จึงจะสร้างมูลค่า"))

    # 4. Margin Stability
    ms = _grade(float(gm.std()) if len(gm) >= 3 else None,
                [(2, 95), (4, 80), (7, 58), (12, 32), (99, 12)])
    items.append(_item("Margin Stability", ms, CALC,
                       f"อัตรากำไรขั้นต้นแกว่ง {gm.std():.1f}%" if len(gm) >= 3 else "",
                       "อัตรากำไรที่นิ่งแปลว่าควบคุมราคาขายและต้นทุนได้"))

    # 5. Debt
    de = _last(R, "D/E (หนี้มีดอกเบี้ย)")
    ic = _last(R, "Interest Coverage")
    s1 = _grade(de, [(0.2, 95), (0.5, 80), (1.0, 55), (2.0, 28), (99, 8)])
    s2 = _grade(-ic if ic is not None else None,
                [(-20, 95), (-10, 80), (-5, 55), (-2.5, 28), (0, 8)])
    dsc = [x for x in (s1, s2) if x is not None]
    items.append(_item("Debt", float(np.mean(dsc)) if dsc else None, CALC,
                       f"D/E {de:.2f} · Interest Coverage {ic:.1f} เท่า"
                       if de is not None and ic is not None else "",
                       "Buffett หลีกเลี่ยงบริษัทที่ต้องพึ่งหนี้ "
                       "เพราะหนี้ทำให้เสียอิสระในการตัดสินใจตอนวิกฤต"))

    # 6. FCF
    fs = None
    ev = ""
    if len(fcf):
        pos = float((fcf > 0).mean())
        fs = _grade(-pos, [(-1.0, 95), (-0.85, 78), (-0.6, 52), (-0.4, 28), (0, 8)])
        ev = f"FCF เป็นบวก {pos*100:.0f}% ของปี"
    items.append(_item("FCF", fs, CALC, ev,
                       "ธุรกิจที่ดีต้องสร้างเงินสดได้เองทุกปี ไม่ต้องพึ่งการกู้"))

    # 7. Intrinsic Value — ส่วนเผื่อความปลอดภัย
    iv = None
    ev = "ยังไม่ได้ประเมินมูลค่า"
    if v and v.get("ส่วนต่างจากราคา (%)") is not None:
        d = float(v["ส่วนต่างจากราคา (%)"])
        iv = _grade(-d, [(-50, 98), (-30, 88), (-15, 70), (0, 48), (99, 15)])
        ev = f"ราคาต่ำกว่ามูลค่าที่ประเมินได้ {d:+.0f}%"
    items.append(_item("Intrinsic Value (ส่วนเผื่อความปลอดภัย)", iv, CALC, ev,
                       "Buffett : ธุรกิจดีแต่ราคาแพงเกินไป ก็ไม่ใช่การลงทุนที่ดี"))

    # 8-9. Capital Allocation / Management
    items.append(_item("Capital Allocation", qmap.get("Capital Allocation"), CALC,
                       "จาก Module 2", "ROIC สูง + ลดจำนวนหุ้น"))
    items.append(_item("Management", qmap.get("Management Quality"), PROXY,
                       "อนุมานจากผลงานการจัดสรรเงินทุน",
                       "ความซื่อสัตย์ประเมินจากตัวเลขไม่ได้ "
                       "ต้องอ่านจดหมายถึงผู้ถือหุ้นย้อนหลังเอง"))

    # 10. Predictability
    pr = None
    ev = ""
    if len(rev) >= 4:
        gr = float(rev.pct_change().dropna().std())
        se = float(eps.pct_change().dropna().std()) if len(eps) >= 4 else None
        s1 = _grade(gr, [(0.04, 95), (0.08, 80), (0.15, 55), (0.30, 28), (9, 8)])
        s2 = _grade(se, [(0.10, 95), (0.20, 78), (0.40, 52), (0.80, 26), (99, 8)])
        pr = float(np.mean([x for x in (s1, s2) if x is not None]))
        ev = f"รายได้แกว่ง {gr*100:.0f}%"
        if se is not None:
            ev += f" · EPS แกว่ง {se*100:.0f}%"
    items.append(_item("Predictability", pr, CALC, ev,
                       "Buffett ลงทุนเฉพาะธุรกิจที่คาดการณ์ 10 ปีข้างหน้าได้"))

    # 11. Moat
    items.append(_item("Moat", qmap.get("Moat (คูเมืองรวม)"), CALC,
                       "จาก Module 2", ""))

    # รวมคะแนนถ่วงน้ำหนักเป็น 100
    got = wsum = 0.0
    for it in items:
        w = BUFFETT_WEIGHTS.get(it["หัวข้อ"], 0)
        if it["คะแนน"] is not None and w:
            got += it["คะแนน"] / 100 * w
            wsum += w
        it["น้ำหนัก"] = w

    total = got / wsum * 100 if wsum else None
    out = _summarize("Buffett Score", items)
    out["คะแนนรวม"] = total
    out["น้ำหนักที่ประเมินได้"] = wsum
    out["ระดับ"] = ("เข้าเกณฑ์ Buffett ชัดเจน" if (total or 0) >= 80 else
                    "เข้าเกณฑ์หลายข้อ" if (total or 0) >= 65 else
                    "เข้าเกณฑ์บางข้อ" if (total or 0) >= 50 else
                    "ไม่ตรงแนวทาง Buffett")
    return out


# ===========================================================================
# Module 4 — Peter Lynch Score
# ===========================================================================

LYNCH_TYPES = [
    ("Slow Grower", "โตช้ากว่า 5% ต่อปี — ซื้อเพื่อปันผล ไม่ใช่เพื่อการเติบโต"),
    ("Stalwart", "โต 5-12% — บริษัทใหญ่มั่นคง Lynch ถือเพื่อกันพอร์ตตกตอนตลาดแย่"),
    ("Fast Grower", "โตเกิน 20% — Lynch ชอบที่สุด แต่ต้องดูว่าโตแบบยั่งยืนไหม"),
    ("Cyclical", "กำไรขึ้นลงตามวัฏจักร — จังหวะซื้อขายสำคัญกว่าคุณภาพ"),
    ("Turnaround", "เคยขาดทุนแล้วกำลังฟื้น — เสี่ยงสูง ผลตอบแทนสูง"),
]


def lynch_score(data, R) -> dict:
    items = []
    rev = _ser(R, "revenue")
    eps = _ser(R, "eps")
    net = _ser(R, "net_income")
    inv = _row(R, "Inventory Turnover")
    info = data.get("info", {}) or {}

    # อัตราโต EPS
    g_eps = None
    if len(eps) >= 3 and float(eps.iloc[0]) > 0 and float(eps.iloc[-1]) > 0:
        g_eps = ((float(eps.iloc[-1]) / float(eps.iloc[0])) ** (
            1 / (len(eps) - 1)) - 1) * 100

    # ---- 1. PEG ----
    pe = (R.get("valuation") or {}).get("P/E")
    peg = None
    if pe and g_eps and g_eps > 0:
        peg = pe / g_eps
    items.append(_item(
        "PEG", _grade(peg, [(0.5, 98), (1.0, 85), (1.5, 62), (2.5, 35), (99, 12)]),
        CALC,
        f"P/E {pe:.1f} ÷ อัตราโต EPS {g_eps:.1f}% = {peg:.2f}"
        if peg else "คำนวณไม่ได้ (ขาดทุนหรือ EPS ไม่โต)",
        "Lynch : PEG ต่ำกว่า 1 คือของถูก · เกิน 2 คือแพงเกินการเติบโต  \n"
        "**ตัวเลข 1 ไม่มีทฤษฎีรองรับ** เป็นกฎง่าย ๆ ที่ Lynch เผยแพร่"))

    # ---- 2. Growth + จัดประเภท ----
    items.append(_item(
        "Growth", _grade(-(g_eps or 0),
                         [(-25, 95), (-15, 82), (-8, 62), (-3, 40), (99, 18)]),
        CALC, f"EPS โตเฉลี่ย {g_eps:+.1f}% ต่อปี" if g_eps is not None else "",
        "Lynch แบ่งหุ้นเป็น 6 ประเภท และใช้กลยุทธ์ต่างกันในแต่ละประเภท"))

    # จัดประเภทตาม Lynch
    loss_years = float((net <= 0).mean()) if len(net) else 0
    vol = float(rev.pct_change().dropna().std()) if len(rev) >= 4 else 0
    if loss_years >= 0.2:
        kind = "Turnaround"
    elif vol > 0.25:
        kind = "Cyclical"
    elif g_eps is None:
        kind = "ไม่ระบุ"
    elif g_eps >= 20:
        kind = "Fast Grower"
    elif g_eps >= 5:
        kind = "Stalwart"
    else:
        kind = "Slow Grower"

    # ---- 3. Store Expansion ----
    g_rev = None
    if len(rev) >= 3 and float(rev.iloc[0]) > 0:
        g_rev = ((float(rev.iloc[-1]) / float(rev.iloc[0])) ** (
            1 / (len(rev) - 1)) - 1) * 100
    items.append(_item(
        "Store Expansion", None, MANUAL,
        f"รายได้โต {g_rev:+.1f}%/ปี (ไม่แยกว่ามาจากสาขาใหม่หรือสาขาเดิม)"
        if g_rev is not None else "",
        "Lynch ชอบร้านที่พิสูจน์โมเดลในเมืองหนึ่งแล้วขยายไปเมืองอื่นได้  \n"
        "**ต้องดู ยอดขายสาขาเดิม (same-store sales) เอง** ซึ่งงบรวมไม่แยกไว้ "
        "— รายได้โตจากการเปิดสาขาใหม่ กับโตเพราะสาขาเดิมขายดีขึ้น ต่างกันมาก"))

    # ---- 4. Market Opportunity ----
    items.append(_item(
        "Market Opportunity", None, MANUAL, "",
        "ตลาดยังเหลือให้โตอีกเท่าไร — ต้องประเมินจากส่วนแบ่งตลาดปัจจุบัน "
        "และขนาดตลาดรวม ซึ่งไม่มีในงบการเงิน"))

    # ---- 5. Inventory ----
    inv_sc = None
    ev = ""
    if len(rev) >= 3:
        inv_lvl = _ser(R, "revenue")  # เผื่อไม่มี inventory ตรง ๆ
        turn = float(inv.iloc[-1]) if len(inv) else None
        tr = _trend_pct(inv) if len(inv) >= 3 else None
        s1 = _grade(-turn if turn else None,
                    [(-12, 92), (-8, 78), (-5, 58), (-3, 35), (0, 15)])
        s2 = _grade(-tr if tr is not None else None,
                    [(-3, 90), (-1, 72), (1, 52), (3, 30), (99, 12)])
        parts = [x for x in (s1, s2) if x is not None]
        inv_sc = float(np.mean(parts)) if parts else None
        if turn:
            ev = f"Inventory Turnover {turn:.1f} รอบ/ปี"
        if tr is not None:
            ev += f" · แนวโน้ม {tr:+.1f}%/ปี"
    items.append(_item(
        "Inventory", inv_sc, CALC, ev,
        "**สัญญาณเตือนของ Lynch** — ถ้าสินค้าคงเหลือโตเร็วกว่ายอดขาย "
        "แปลว่าของขายไม่ออกและกำลังจะต้องลดราคาล้างสต็อก"))

    # ---- 6. Debt ----
    de = _last(R, "D/E (หนี้มีดอกเบี้ย)")
    items.append(_item(
        "Debt", _grade(de, [(0.2, 95), (0.5, 80), (0.8, 58), (1.5, 30), (99, 10)]),
        CALC, f"D/E {de:.2f}" if de is not None else "",
        "Lynch : บริษัทที่ไม่มีหนี้ล้มยาก · หนี้เยอะทำให้หมดโอกาสฟื้นตอนธุรกิจสะดุด"))

    # ---- 7. Growth Consistency ----
    gc = None
    ev = ""
    if len(eps) >= 4:
        up = float((eps.pct_change().dropna() > 0).mean())
        gc = _grade(-up, [(-1.0, 95), (-0.8, 80), (-0.6, 55), (-0.4, 30), (0, 10)])
        ev = f"EPS เพิ่มขึ้น {up*100:.0f}% ของปี"
    items.append(_item("Growth Consistency", gc, CALC, ev,
                       "โตทุกปีอย่างสม่ำเสมอ ดีกว่าโตกระโดดสลับหดตัว"))

    out = _summarize("Peter Lynch Score", items)
    out["ประเภทตาม Lynch"] = kind
    out["คำอธิบายประเภท"] = dict(LYNCH_TYPES).get(kind, "จัดประเภทไม่ได้")
    out["PEG"] = peg
    out["อัตราโต EPS (%)"] = g_eps
    return out


# ===========================================================================
# Module 5 — Howard Marks Cycle Analysis
# ===========================================================================

def marks_cycle(data, R, v=None, rf=None) -> dict:
    """
    วิเคราะห์ว่า "ตอนนี้เราอยู่ตรงไหนของวัฏจักร"

    แนวคิดหลักของ Howard Marks
    ----------------------------
    เขาย้ำเสมอว่า **เราพยากรณ์อนาคตไม่ได้ แต่รู้ได้ว่าตอนนี้ยืนอยู่ตรงไหน**
    และการรู้ตำแหน่งในวัฏจักรมีค่ามากกว่าการพยายามทำนายจุดกลับตัว

    ระบบนี้จึงไม่ทำนายอะไรเลย แต่บอกว่าตัวเลขปัจจุบันอยู่เปอร์เซ็นไทล์ที่เท่าไร
    ของประวัติตัวเอง — เป็นการวัดตำแหน่ง ไม่ใช่การพยากรณ์
    """
    items = []
    gm = _row(R, "Gross Margin")
    nm = _row(R, "Net Margin")
    roe = _row(R, "ROE")

    # ---- 1. Cycle Analysis : อัตรากำไรอยู่ตรงไหนของประวัติ ----
    cyc, ev = None, ""
    if len(nm) >= 4:
        p = _pctile(nm, float(nm.iloc[-1]))
        # อยู่จุดสูงของวัฏจักร = เสี่ยงกว่า เพราะมีที่ให้ลงมากกว่าที่ให้ขึ้น
        cyc = _grade(p, [(20, 85), (40, 70), (60, 50), (80, 32), (101, 15)])
        ev = (f"อัตรากำไรสุทธิปัจจุบัน {nm.iloc[-1]:.1f}% "
              f"อยู่เปอร์เซ็นไทล์ที่ {p:.0f} ของประวัติตัวเอง")
    items.append(_item(
        "Cycle Analysis", cyc, CALC, ev,
        "คะแนนสูง = อยู่จุดต่ำของวัฏจักร (โอกาสดีกว่า)  \n"
        "คะแนนต่ำ = อยู่จุดสูง กำไรอาจกำลังจะกลับสู่ค่าเฉลี่ย"))

    # ---- 2. Market Sentiment : P/E เทียบประวัติตัวเอง ----
    sent, ev = None, ""
    if v and v.get("historical"):
        h = v["historical"]
        pe_now = (R.get("valuation") or {}).get("P/E")
        pe_hist = h.get("P/E ย้อนหลัง")
        if pe_now and pe_hist is not None:
            s = pd.to_numeric(pd.Series(pe_hist), errors="coerce").dropna()
            s = s[s > 0]
            p = _pctile(s, pe_now)
            if p is not None:
                sent = _grade(p, [(20, 88), (40, 72), (60, 52), (80, 30), (101, 12)])
                ev = (f"P/E ปัจจุบัน {pe_now:.1f} อยู่เปอร์เซ็นไทล์ที่ {p:.0f} "
                      f"ของ P/E ย้อนหลังตัวเอง")
    items.append(_item(
        "Market Sentiment", sent, CALC, ev or "ไม่มีประวัติ P/E ให้เทียบ",
        "Marks : ตลาดแกว่งระหว่างความกลัวสุดขั้วกับความโลภสุดขั้ว  \n"
        "P/E ที่เปอร์เซ็นไทล์สูง = ตลาดกำลังมองโลกสวยกับหุ้นตัวนี้"))

    # ---- 3. Credit Cycle : ต้นทุนหนี้และภาระหนี้ของบริษัท ----
    cc, ev = None, ""
    nd = _row(R, "Net Debt / EBITDA")
    if len(nd) >= 3:
        tr = _trend_pct(nd)
        cc = _grade(tr, [(-5, 88), (-1, 72), (1, 52), (5, 30), (999, 12)])
        ev = (f"Net Debt/EBITDA ปัจจุบัน {nd.iloc[-1]:.2f} เท่า "
              f"· แนวโน้ม {tr:+.1f}%/ปี")
    items.append(_item(
        "Credit Cycle", cc, CALC, ev,
        "หนี้ที่เพิ่มเร็วในช่วงดอกเบี้ยต่ำ มักกลายเป็นปัญหาตอนดอกเบี้ยขึ้น  \n"
        "Marks : วิกฤตส่วนใหญ่เริ่มจากการปล่อยกู้ที่หละหลวมในช่วงที่ทุกอย่างดูดี"))

    # ---- 4. Interest Rate ----
    rf_now = rf if rf is not None else (
        (v or {}).get("wacc_detail", {}).get("พันธบัตร (rf)"))
    items.append(_item(
        "Interest Rate",
        _grade(rf_now * 100 if rf_now else None,
               [(1.5, 30), (3.0, 45), (4.5, 60), (6.0, 75), (99, 88)]),
        CALC,
        f"อัตราพันธบัตรที่ใช้ {rf_now*100:.2f}%" if rf_now else "",
        "ดอกเบี้ยสูงกดมูลค่าหุ้นทุกตัวผ่านอัตราคิดลดที่สูงขึ้น  \n"
        "คะแนนสูง = ดอกเบี้ยสูงอยู่แล้ว มีโอกาสลดลงมากกว่าขึ้นต่อ"))

    # ---- 5. Macro / Inflation ----
    items.append(_item(
        "Macro", None, MANUAL, "",
        "GDP อัตราว่างงาน นโยบายการคลัง — ไม่มีในงบการเงิน  \n"
        "Marks เตือนว่าอย่าลงทุนโดยอิงการทำนายเศรษฐกิจ "
        "แต่ให้เตรียมพร้อมรับหลายสถานการณ์"))
    items.append(_item(
        "Inflation", None, MANUAL, "",
        "ดูว่าบริษัทขึ้นราคาตามเงินเฟ้อได้ไหม (ดู Pricing Power ใน Module 2) "
        "· ธุรกิจที่ขึ้นราคาไม่ได้จะโดนบีบอัตรากำไรตอนเงินเฟ้อสูง"))

    out = _summarize("Howard Marks Cycle", items)
    out["สรุปตำแหน่งวัฏจักร"] = (
        "อยู่ช่วงที่ตัวเลขต่ำกว่าค่าเฉลี่ยของตัวเอง — โอกาสมากกว่าความเสี่ยง"
        if (out["คะแนนรวม"] or 0) >= 65 else
        "อยู่ช่วงกลาง ๆ ของวัฏจักร"
        if (out["คะแนนรวม"] or 0) >= 45 else
        "อยู่ช่วงที่ตัวเลขสูงกว่าค่าเฉลี่ยของตัวเอง — ความเสี่ยงมากกว่าโอกาส")
    return out


# ===========================================================================
# รวมทุกโมดูล
# ===========================================================================

def assess_all(data, R, v=None, rf=None) -> dict:
    q = quality_engine(data, R)
    return {
        "Module 2": q,
        "Module 3": buffett_score(data, R, v=v, q=q),
        "Module 4": lynch_score(data, R),
        "Module 5": marks_cycle(data, R, v=v, rf=rf),
    }


# ---------------------------------------------------------------------------
# ใช้จาก Terminal
# ---------------------------------------------------------------------------

def _print_module(m):
    print("\n" + "=" * 78)
    tot = m["คะแนนรวม"]
    print(f"  {m['ชื่อโมดูล']} — {tot:.1f} / 100" if tot is not None
          else f"  {m['ชื่อโมดูล']} — ประเมินไม่ได้")
    print(f"  ให้คะแนนได้ {m['ให้คะแนนได้']}/{m['จำนวนหัวข้อ']} หัวข้อ "
          f"· มาจากงบโดยตรง {m['สัดส่วนจากงบ (%)']:.0f}% "
          f"· ต้องดูเอง {m['ต้องดูเอง']} หัวข้อ")
    if m.get("ระดับ"):
        print(f"  ระดับ : {m['ระดับ']}")
    if m.get("ประเภทตาม Lynch"):
        print(f"  ประเภท : {m['ประเภทตาม Lynch']} — {m['คำอธิบายประเภท']}")
    if m.get("สรุปตำแหน่งวัฏจักร"):
        print(f"  ตำแหน่ง : {m['สรุปตำแหน่งวัฏจักร']}")
    print("=" * 78)
    for it in m["รายการ"]:
        sc = it["คะแนน"]
        s = f"{sc:5.0f}" if sc is not None else "    —"
        w = f" (น้ำหนัก {it['น้ำหนัก']})" if it.get("น้ำหนัก") else ""
        print(f"\n  {it['หัวข้อ']:<34}{s}  [{it['ที่มา']}]{w}")
        if it["หลักฐาน"]:
            print(f"     หลักฐาน : {it['หลักฐาน']}")


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="คุณภาพกิจการและคะแนนแบบกูรู")
    p.add_argument("ticker")
    p.add_argument("--module", default="all",
                   choices=["all", "quality", "buffett", "lynch", "marks"])
    p.add_argument("--rf", type=float, default=None)
    a = p.parse_args()

    from data_layer import get_stock_data
    from ratios import compute_ratios

    t = a.ticker.upper()
    print(f"\nกำลังดึงข้อมูล {t} ...")
    data = get_stock_data(t)
    R = compute_ratios(data)

    v = None
    try:
        from valuation import value_stock
        v = value_stock(data, R, rf=a.rf)
    except Exception as e:
        print(f"  (ประเมินมูลค่าไม่สำเร็จ : {e} — บางหัวข้อจะประเมินไม่ได้)")

    res = assess_all(data, R, v=v, rf=a.rf)
    pick = {"quality": ["Module 2"], "buffett": ["Module 3"],
            "lynch": ["Module 4"], "marks": ["Module 5"]}.get(
                a.module, ["Module 2", "Module 3", "Module 4", "Module 5"])
    for k in pick:
        _print_module(res[k])

    print("\n" + "=" * 78)
    print("  ความหมายของป้ายที่มา")
    print("=" * 78)
    print("  [คำนวณ]     วัดจากงบการเงินโดยตรง ตรวจสอบย้อนได้ทุกตัว")
    print("  [ตัวแทน]    ใช้ตัวเลขอื่นแทนสิ่งที่วัดตรง ๆ ไม่ได้ — เป็นการอนุมาน ผิดได้")
    print("  [ต้องดูเอง] ไม่มีข้อมูลให้ประเมิน ระบบให้เพียงคำถามที่ควรถาม\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
