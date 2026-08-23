"""
cycle.py — เครื่องยนต์วัฏจักรเศรษฐกิจ (Part 18)
================================================
หน้าที่ : รับตัวเลขดิบจาก macro_data.py แล้วตอบว่า
          "ตอนนี้เศรษฐกิจอยู่ช่วงไหนของวัฏจักร และอะไรบอกแบบนั้น"

**ไฟล์นี้ไม่เรียก AI แม้แต่บรรทัดเดียว** ทุกอย่างเป็นสูตรและกฎที่เขียนไว้ตายตัว
ตรวจสอบย้อนกลับได้ทุกตัวเลข (กฎเหล็กข้อ 1)

แนวคิดหลัก — ทำไมต้องใช้ 5 กรอบไม่ใช่กรอบเดียว
------------------------------------------------
ไม่มีกรอบไหนถูกตลอด แต่ละกรอบมีจุดบอดคนละที่ :

  · นาฬิกาการลงทุน  อ่านภาพรวมดี แต่คาบเส้นบ่อยตอนเปลี่ยนผ่าน
  · วัฏจักรธุรกิจ    แม่นแต่ช้า (ยืนยันตอนที่ตลาดลงไปแล้ว)
  · วัฏจักรสินเชื่อ  เตือนล่วงหน้าดีที่สุด แต่เตือนผิดบ่อย
  · วัฏจักรเฟด      ชัดเจน แต่นโยบายกับเศรษฐกิจจริงมีดีเลย์ 6-12 เดือน
  · ตลาดบอกเอง      เร็วที่สุด แต่หลอกบ่อยที่สุด

เอาทั้ง 5 มาโหวตกัน แล้ว **รายงานว่าโหวตแตกแค่ไหน** จึงได้ทั้งคำตอบ
และความน่าเชื่อถือของคำตอบไปพร้อมกัน ซึ่งมีค่ากว่าการฟันธงด้วยกรอบเดียว

โครงสร้างคำตอบของแต่ละกรอบ
--------------------------
ทุกกรอบคืน "การกระจายน้ำหนัก" ไม่ใช่คำตอบเดียว
เช่น ช่วงกลางวัฏจักรอาจเป็นได้ทั้งฟื้นตัวและร้อนแรง → {ฟื้นตัว: 0.5, ร้อนแรง: 0.5}
วิธีนี้ทำให้ความไม่แน่นอนไหลผ่านเข้าไปในการโหวตอย่างซื่อสัตย์
แทนที่จะถูกปัดทิ้งตั้งแต่ต้นทาง

วิธีใช้จาก Terminal
-------------------
    python3 cycle.py            # วิเคราะห์จากข้อมูลจริง
    python3 cycle.py --selftest # ทดสอบตรรกะด้วยข้อมูลจำลอง (ไม่ต้องต่อเน็ต)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import macro_data as MD

# ---------------------------------------------------------------------------
# 4 ช่วงของวัฏจักร — ใช้เป็น "ภาษากลาง" ที่ทุกกรอบต้องแปลงมาลง
# ---------------------------------------------------------------------------
RECOVERY = "ฟื้นตัว"          # เติบโตขึ้น เงินเฟ้อลง — ช่วงที่ดีที่สุดของหุ้น
OVERHEAT = "ร้อนแรง"          # เติบโตขึ้น เงินเฟ้อขึ้น — สินค้าโภคภัณฑ์นำ
STAGFLATION = "เงินเฟ้อฝืด"    # เติบโตลง เงินเฟ้อขึ้น — ช่วงที่แย่ที่สุด เงินสด/ทองนำ
REFLATION = "เงินฝืด"         # เติบโตลง เงินเฟ้อลง — พันธบัตรนำ

QUADS = [RECOVERY, OVERHEAT, STAGFLATION, REFLATION]

QUAD_EN = {RECOVERY: "Recovery", OVERHEAT: "Overheat",
           STAGFLATION: "Stagflation", REFLATION: "Reflation"}

QUAD_DESC = {
    RECOVERY: "เศรษฐกิจกำลังเร่งขึ้นโดยที่เงินเฟ้อยังไม่เป็นปัญหา "
              "เป็นช่วงที่หุ้นให้ผลตอบแทนดีที่สุดในประวัติศาสตร์",
    OVERHEAT: "เศรษฐกิจโตเร็วจนเริ่มดันราคาสินค้าขึ้น "
              "สินค้าโภคภัณฑ์และหุ้นกลุ่มพลังงาน/วัสดุมักนำ ส่วนพันธบัตรเสียเปรียบ",
    STAGFLATION: "เศรษฐกิจชะลอแต่ราคาสินค้ายังขึ้น เป็นช่วงที่ยากที่สุด "
                 "เพราะทั้งหุ้นและพันธบัตรเสียพร้อมกัน เงินสดและทองคำมักรอดที่สุด",
    REFLATION: "ทั้งเศรษฐกิจและเงินเฟ้อชะลอ ธนาคารกลางมักเริ่มลดดอกเบี้ย "
               "พันธบัตรระยะยาวมักให้ผลตอบแทนดีที่สุด",
}

# น้ำหนักโหวตของแต่ละกรอบ — เหตุผลอยู่ใน 25_วัฏจักรเศรษฐกิจ.md ส่วนที่ 5.1
FRAMEWORK_WEIGHTS = {
    "นาฬิกาการลงทุน": 0.25,
    "วัฏจักรธุรกิจ": 0.25,
    "วัฏจักรสินเชื่อ": 0.20,
    "วัฏจักรเฟด": 0.15,
    "ตลาดบอกเอง": 0.15,
}


# ===========================================================================
# โครงเก็บผลของแต่ละกรอบ
# ===========================================================================
@dataclass
class Framework:
    """ผลของกรอบวิเคราะห์ 1 กรอบ ตลอดช่วงเวลา"""
    name: str
    weight: float
    dist: pd.DataFrame              # index=เดือน · columns=4 ช่วง · แต่ละแถวรวม 1
    conf: pd.Series                 # ความมั่นใจ 0–1 รายเดือน
    label: pd.Series                # ชื่อช่วงในภาษาของกรอบนั้นเอง
    evidence: list = field(default_factory=list)   # ตัวชี้วัดที่ใช้ + ค่าล่าสุด
    note: str = ""                  # คำเตือน เช่น ข้อมูลหายไปกี่ตัว
    usable: bool = True             # False = ข้อมูลไม่พอ ตัดออกจากการโหวต

    def latest_quad(self) -> str:
        if self.dist.empty:
            return ""
        return str(self.dist.iloc[-1].idxmax())

    def latest_label(self) -> str:
        return "" if self.label.empty else str(self.label.iloc[-1])


def _blank(name: str, why: str) -> Framework:
    """กรอบที่ใช้ไม่ได้เพราะข้อมูลไม่พอ — คืนกล่องเปล่าพร้อมเหตุผล"""
    return Framework(name=name, weight=FRAMEWORK_WEIGHTS.get(name, 0.0),
                     dist=pd.DataFrame(columns=QUADS), conf=pd.Series(dtype=float),
                     label=pd.Series(dtype=object), note=why, usable=False)


def _dist_row(mapping: dict[str, float]) -> dict[str, float]:
    """เติมช่วงที่ไม่ได้ระบุให้เป็น 0 แล้วปรับให้รวมกันได้ 1"""
    row = {q: float(mapping.get(q, 0.0)) for q in QUADS}
    tot = sum(row.values())
    return {q: (v / tot if tot else 0.25) for q, v in row.items()}


# ===========================================================================
# ส่วนที่ 1 — สร้างแกนการเติบโตและแกนเงินเฟ้อ
# ===========================================================================
def _composite(data: dict, group: str) -> tuple[pd.Series, list, list]:
    """
    รวมตัวชี้วัดในกลุ่มเดียวกันเป็นคะแนนเดียว

    ขั้นตอน : แปลงรูป → z-score 10 ปี → กลับด้านถ้าจำเป็น → ถ่วงน้ำหนักรวม

    **ตัวที่ตายจะถูกตัดออกและน้ำหนักถูกเกลี่ยใหม่**
    ไม่ใช่ปล่อยให้ค่าเก่าถ่วงคะแนนอยู่เงียบ ๆ
    """
    fred = data.get("fred", {})
    dead = set(data.get("dead", []))
    deflator = fred.get("CPIAUCSL")

    parts: list[tuple[pd.Series, float]] = []
    evidence: list[dict] = []
    skipped: list[str] = []

    for sid, meta in MD.FRED_SERIES.items():
        if meta.get("grp") != group:
            continue
        w = float(meta.get("w", 0.0))
        if w <= 0:                       # w=0 คือดึงไว้ใช้ที่อื่น ไม่ร่วมคะแนนรวม
            continue
        if sid in dead or sid not in fred:
            skipped.append(sid)
            continue
        try:
            t = MD.transform(fred[sid], meta["tf"], deflator=deflator).dropna()
            z = MD.zscore(t).dropna()
            if z.empty:
                skipped.append(sid)
                continue
            if meta.get("inv"):
                z = -z
            parts.append((z, w))
            evidence.append({
                "ตัวชี้วัด": meta["th"], "รหัส": sid,
                "ค่าล่าสุด": float(t.iloc[-1]),
                "หน่วย": meta.get("unit", ""),
                "เปลี่ยน 3 เดือน": float(t.iloc[-1] - t.iloc[-4]) if t.size > 3 else np.nan,
                "z (10 ปี)": float(z.iloc[-1]),
                "ณ วันที่": t.index[-1].date().isoformat(),
                "น้ำหนัก": w,
            })
        except Exception:                                  # noqa: BLE001
            skipped.append(sid)

    if not parts:
        return pd.Series(dtype=float), evidence, skipped

    idx = parts[0][0].index
    for s, _ in parts[1:]:
        idx = idx.union(s.index)
    idx = idx.sort_values()

    # รวมแบบถ่วงน้ำหนัก โดย "หารด้วยน้ำหนักที่มีข้อมูลจริงเท่านั้น"
    # ตัวไหนขาดข้อมูลเดือนนั้น น้ำหนักจะถูกเกลี่ยไปให้ตัวที่เหลือโดยอัตโนมัติ
    # ไม่ใช่นับเป็นศูนย์ ซึ่งจะลากคะแนนรวมให้เพี้ยนลงทุกครั้งที่ข้อมูลมาไม่ครบ
    num = pd.Series(0.0, index=idx)
    den = pd.Series(0.0, index=idx)
    for s, w in parts:
        a = s.reindex(idx).ffill(limit=3)
        ok = a.notna().to_numpy()
        num.loc[ok] = num.loc[ok] + a.loc[ok] * w
        den.loc[ok] = den.loc[ok] + w
    comp = (num / den.replace(0, np.nan)).dropna()
    return comp, evidence, skipped


def growth_inflation(data: dict) -> dict:
    """คะแนนการเติบโตและเงินเฟ้อรายเดือน พร้อมหลักฐานที่ใช้"""
    g, ge, gs = _composite(data, "growth")
    i, ie, is_ = _composite(data, "inflation")
    return {"growth": g, "inflation": i,
            "หลักฐานการเติบโต": ge, "หลักฐานเงินเฟ้อ": ie,
            "ตัดออกการเติบโต": gs, "ตัดออกเงินเฟ้อ": is_}


# ===========================================================================
# ส่วนที่ 2 — กรอบที่ 1 : นาฬิกาการลงทุน
# ===========================================================================
def f1_clock(gi: dict) -> Framework:
    """
    การเติบโต × เงินเฟ้อ = 4 ควอดแรนต์

    **จุดที่คนเข้าใจผิดบ่อยที่สุด** : ไม่ได้ดูว่าเงินเฟ้อ "สูงหรือต่ำ"
    แต่ดูว่าอยู่เหนือหรือใต้ค่าปกติของตัวเอง (z-score) และกำลังไปทางไหน
    เงินเฟ้อ 5% ที่กำลังลดเร็ว = เย็นลง ไม่ใช่ร้อน
    """
    name = "นาฬิกาการลงทุน"
    g, i = gi["growth"], gi["inflation"]
    if g.empty or i.empty:
        return _blank(name, "ไม่มีข้อมูลพอสร้างแกนการเติบโตหรือแกนเงินเฟ้อ")

    idx = g.index.intersection(i.index)
    if idx.size < 6:
        return _blank(name, "ข้อมูลสองแกนซ้อนทับกันน้อยเกินไป")
    g, i = g.reindex(idx), i.reindex(idx)

    rows, confs, labels = [], [], []
    for d in idx:
        gv, iv = float(g[d]), float(i[d])
        if gv >= 0 and iv < 0:
            q = RECOVERY
        elif gv >= 0 and iv >= 0:
            q = OVERHEAT
        elif gv < 0 and iv >= 0:
            q = STAGFLATION
        else:
            q = REFLATION
        # ยิ่งห่างจากเส้นแบ่ง (0,0) ยิ่งมั่นใจ — คาบเส้นแปลว่ากำลังเปลี่ยนผ่าน
        dist_from_edge = min(abs(gv), abs(iv))
        conf = float(np.clip(dist_from_edge / 1.0, 0.15, 1.0))
        # ถ้าคาบเส้นมาก ให้กระจายน้ำหนักไปควอดแรนต์ข้างเคียงด้วย
        if dist_from_edge < 0.35:
            nb = _neighbours(q, gv, iv)
            rows.append(_dist_row(nb))
        else:
            rows.append(_dist_row({q: 1.0}))
        confs.append(conf)
        labels.append(q)

    ev = list(gi["หลักฐานการเติบโต"]) + list(gi["หลักฐานเงินเฟ้อ"])
    skipped = list(gi["ตัดออกการเติบโต"]) + list(gi["ตัดออกเงินเฟ้อ"])
    note = f"ตัดตัวชี้วัดที่ใช้ไม่ได้ออก {len(skipped)} ตัว: {', '.join(skipped)}" if skipped else ""
    return Framework(name=name, weight=FRAMEWORK_WEIGHTS[name],
                     dist=pd.DataFrame(rows, index=idx),
                     conf=pd.Series(confs, index=idx),
                     label=pd.Series(labels, index=idx),
                     evidence=ev, note=note)


def _neighbours(q: str, gv: float, iv: float) -> dict[str, float]:
    """เมื่อคะแนนคาบเส้น ให้แบ่งน้ำหนักไปช่วงข้างเคียงตามแกนที่คาบ"""
    out = {q: 0.6}
    if abs(gv) <= abs(iv):        # คาบแกนการเติบโต → ช่วงที่ต่างกันที่การเติบโต
        pair = {RECOVERY: REFLATION, REFLATION: RECOVERY,
                OVERHEAT: STAGFLATION, STAGFLATION: OVERHEAT}
    else:                         # คาบแกนเงินเฟ้อ
        pair = {RECOVERY: OVERHEAT, OVERHEAT: RECOVERY,
                STAGFLATION: REFLATION, REFLATION: STAGFLATION}
    out[pair[q]] = 0.4
    return out


# ===========================================================================
# ส่วนที่ 3 — กรอบที่ 2 : วัฏจักรธุรกิจ
# ===========================================================================
BC_MAP = {
    "ต้นวัฏจักร": {RECOVERY: 1.0},
    "กลางวัฏจักร": {RECOVERY: 0.5, OVERHEAT: 0.5},
    "ปลายวัฏจักร": {OVERHEAT: 0.5, STAGFLATION: 0.5},
    "ถดถอย": {REFLATION: 1.0},
}


def f2_business(data: dict, gi: dict) -> Framework:
    """
    กฎตายตัว ไล่ตรวจจากบนลงล่าง เจอข้อไหนก่อนหยุดที่ข้อนั้น

    Sahm Rule เป็น *ตัวยืนยัน* ไม่ใช่ตัวเตือนล่วงหน้า
    ตอนมันเตือน ตลาดหุ้นมักลงไปแล้ว — จึงต้องมีกรอบ 3-5 ที่เร็วกว่าคอยถ่วง
    """
    name = "วัฏจักรธุรกิจ"
    fred, dead = data.get("fred", {}), set(data.get("dead", []))

    def get(sid):
        return None if (sid in dead or sid not in fred) else MD._to_monthly(fred[sid])

    sahm, cfnai = get("SAHMREALTIME"), get("CFNAIMA3")
    pay, unrate = get("PAYEMS"), get("UNRATE")
    core = get("PCEPILFE")
    curve = get("T10Y3M")

    if cfnai is None or unrate is None:
        return _blank(name, "ขาด CFNAIMA3 หรือ UNRATE ซึ่งเป็นแกนหลักของกรอบนี้")

    idx = cfnai.index
    for s in (sahm, pay, unrate, core, curve):
        if s is not None:
            idx = idx.union(s.index)
    idx = idx.sort_values()

    def al(s):
        return None if s is None else s.reindex(idx).ffill(limit=6)

    sahm, cfnai, pay, unrate, core, curve = map(al, (sahm, cfnai, pay, unrate, core, curve))
    pay_d3 = pay.diff(3) if pay is not None else None
    core_yoy = core.pct_change(12, fill_method=None) * 100 if core is not None else None
    # "ต้นวัฏจักร" = เพิ่งออกจากภาวะถดถอย → อัตราว่างงานลดลงจาก **จุดสูงสุด**
    # ไม่ใช่อยู่ที่จุดต่ำสุด (ซึ่งเป็นลักษณะของช่วงกลางถึงปลายวัฏจักร)
    ur_max12 = unrate.rolling(12, min_periods=6).max()
    ur_q25 = unrate.rolling(120, min_periods=36).quantile(0.25)

    rows, confs, labels = [], [], []
    for d in idx:
        hits = 0
        # --- 1. ถดถอย ---
        rec = []
        if sahm is not None and pd.notna(sahm.get(d)) and sahm[d] >= 0.50:
            rec.append("Sahm Rule ≥ 0.50")
        if pd.notna(cfnai.get(d)) and cfnai[d] < -0.70:
            rec.append("CFNAI-MA3 < −0.70")
        if pay_d3 is not None and pd.notna(pay_d3.get(d)) and pay_d3[d] < 0:
            rec.append("การจ้างงาน 3 เดือนติดลบ")
        if rec:
            lab, hits = "ถดถอย", len(rec)
        else:
            # --- 2. ต้นวัฏจักร : ว่างงานลดลงจากจุดสูงสุด + กิจกรรมกลับมาเป็นบวก ---
            early = (pd.notna(unrate.get(d)) and pd.notna(ur_max12.get(d))
                     and (ur_max12[d] - unrate[d]) >= 0.30
                     and pd.notna(cfnai.get(d)) and cfnai[d] > -0.20)
            # --- 3. ปลายวัฏจักร : ต้องเข้าเกณฑ์อย่างน้อย 2 ใน 3 ข้อ ---
            late_hits = []
            if core_yoy is not None and pd.notna(core_yoy.get(d)) and core_yoy[d] > 2.5:
                late_hits.append("เงินเฟ้อพื้นฐาน > 2.5%")
            if curve is not None and pd.notna(curve.get(d)) and curve[d] < 0:
                late_hits.append("เส้นอัตราผลตอบแทนกลับด้าน")
            if (pd.notna(unrate.get(d)) and pd.notna(ur_q25.get(d))
                    and unrate[d] <= ur_q25[d]):
                late_hits.append("อัตราว่างงานต่ำสุดในรอบ 10 ปี")
            # ลำดับการตรวจตามเอกสาร : ถดถอย → ต้น → ปลาย → กลาง
            if early:
                lab, hits = "ต้นวัฏจักร", 2
            elif len(late_hits) >= 2:
                lab, hits = "ปลายวัฏจักร", len(late_hits)
            else:
                lab, hits = "กลางวัฏจักร", 1

        rows.append(_dist_row(BC_MAP[lab]))
        confs.append(float(np.clip(0.35 + 0.22 * hits, 0.35, 1.0)))
        labels.append(lab)

    ev = _ev_rows(data, ["SAHMREALTIME", "CFNAIMA3", "UNRATE", "PAYEMS",
                         "PCEPILFE", "T10Y3M"])
    return Framework(name=name, weight=FRAMEWORK_WEIGHTS[name],
                     dist=pd.DataFrame(rows, index=idx),
                     conf=pd.Series(confs, index=idx),
                     label=pd.Series(labels, index=idx), evidence=ev)


# ===========================================================================
# ส่วนที่ 4 — กรอบที่ 3 : วัฏจักรสินเชื่อ
# ===========================================================================
CR_MAP = {
    "ซ่อมแซม": {RECOVERY: 0.7, REFLATION: 0.3},
    "ขยายตัว": {RECOVERY: 0.5, OVERHEAT: 0.5},
    "ประมาท": {OVERHEAT: 0.6, STAGFLATION: 0.4},
    "ทรุด": {REFLATION: 0.6, STAGFLATION: 0.4},
}


def f3_credit(data: dict) -> Framework:
    """
    กรอบที่เตือนล่วงหน้าได้ดีที่สุด เพราะเงินตึงก่อนเศรษฐกิจพังเสมอ

    ใช้ BAA10Y (ส่วนต่าง Baa ของ Moody's มีตั้งแต่ปี 1986) เป็นตัวหลัก
    ไม่ใช่ ICE BofA HY OAS เพราะตั้งแต่ เม.ย. 2026 FRED เหลือข้อมูลแค่ 3 ปี
    ซึ่งคำนวณเปอร์เซ็นไทล์ 10 ปีไม่ได้
    """
    name = "วัฏจักรสินเชื่อ"
    fred, dead = data.get("fred", {}), set(data.get("dead", []))

    def get(sid):
        return None if (sid in dead or sid not in fred) else MD._to_monthly(fred[sid])

    baa, nfci, tight = get("BAA10Y"), get("NFCI"), get("DRTSCILM")
    if baa is None:
        return _blank(name, "ขาด BAA10Y ซึ่งเป็นตัวหลักของกรอบสินเชื่อ")

    idx = baa.index
    for s in (nfci, tight):
        if s is not None:
            idx = idx.union(s.index)
    idx = idx.sort_values()
    baa = baa.reindex(idx).ffill(limit=3)
    nfci = nfci.reindex(idx).ffill(limit=3) if nfci is not None else None
    tight = tight.reindex(idx).ffill(limit=9) if tight is not None else None

    pct = baa.rolling(120, min_periods=36).rank(pct=True) * 100
    chg2 = baa.diff(2)                    # เปลี่ยนแปลง ~60 วัน (2 เดือน)
    tight_d = tight.diff() if tight is not None else None

    rows, confs, labels = [], [], []
    for d in idx:
        p, c = pct.get(d), chg2.get(d)
        n = nfci.get(d) if nfci is not None else np.nan
        n_up = (nfci.diff().get(d) if nfci is not None else np.nan)
        hits = 1
        if (pd.notna(c) and c >= 0.50) or (pd.notna(n) and n > 0
                                           and pd.notna(n_up) and n_up > 0):
            lab, hits = "ทรุด", 3
        elif pd.notna(p) and p > 70 and pd.notna(c) and c < 0:
            lab, hits = "ซ่อมแซม", 2
        elif (pd.notna(p) and p < 15
              and (tight_d is None or (pd.notna(tight_d.get(d)) and tight_d[d] < 0))):
            lab, hits = "ประมาท", 3
        else:
            lab, hits = "ขยายตัว", 1
        rows.append(_dist_row(CR_MAP[lab]))
        confs.append(float(np.clip(0.35 + 0.20 * hits, 0.35, 1.0)))
        labels.append(lab)

    ev = _ev_rows(data, ["BAA10Y", "NFCI", "ANFCI", "STLFSI4", "DRTSCILM",
                         "BAMLH0A0HYM2"])
    note = ""
    if "BAMLH0A0HYM2" in fred and "BAMLH0A0HYM2" not in dead:
        note = ("ส่วนต่างหุ้นกู้ผลตอบแทนสูงแสดงไว้ประกอบเท่านั้น "
                "ไม่ร่วมตัดสิน เพราะ FRED เหลือข้อมูลย้อนหลังแค่ 3 ปี")
    return Framework(name=name, weight=FRAMEWORK_WEIGHTS[name],
                     dist=pd.DataFrame(rows, index=idx),
                     conf=pd.Series(confs, index=idx),
                     label=pd.Series(labels, index=idx), evidence=ev, note=note)


# ===========================================================================
# ส่วนที่ 5 — กรอบที่ 4 : วัฏจักรเฟดและสภาพคล่อง
# ===========================================================================
FED_MAP = {
    "ตึงตัว": {OVERHEAT: 0.4, STAGFLATION: 0.6},
    "ถึงจุดสูงสุด": {STAGFLATION: 0.5, REFLATION: 0.5},
    "ผ่อนคลาย": {REFLATION: 0.6, RECOVERY: 0.4},
    "ท่วม": {RECOVERY: 0.8, OVERHEAT: 0.2},
}


def f4_fed(data: dict) -> Framework:
    """ดอกเบี้ยนโยบาย + ดอกเบี้ยแท้จริง + สภาพคล่องสุทธิ"""
    name = "วัฏจักรเฟด"
    fred, dead = data.get("fred", {}), set(data.get("dead", []))

    def get(sid):
        return None if (sid in dead or sid not in fred) else MD._to_monthly(fred[sid])

    ff, real = get("FEDFUNDS"), get("REAINTRATREARAT10Y")
    walcl, rrp, tga = get("WALCL"), get("RRPONTSYD"), get("WTREGEN")
    if ff is None:
        return _blank(name, "ขาด FEDFUNDS ซึ่งเป็นตัวหลักของกรอบนี้")

    idx = ff.index
    for s in (real, walcl, rrp, tga):
        if s is not None:
            idx = idx.union(s.index)
    idx = idx.sort_values()
    ff = ff.reindex(idx).ffill(limit=3)
    real = real.reindex(idx).ffill(limit=3) if real is not None else None

    # สภาพคล่องสุทธิ = งบดุลเฟด − เงินฝากย้อนกลับ − บัญชีคลัง
    # หน่วยไม่ตรงกัน : WALCL/WTREGEN เป็นล้าน$ · RRPONTSYD เป็นพันล้าน$
    netliq = None
    if walcl is not None:
        nl = walcl.reindex(idx).ffill(limit=2)
        if rrp is not None:
            nl = nl - rrp.reindex(idx).ffill(limit=2) * 1000.0
        if tga is not None:
            nl = nl - tga.reindex(idx).ffill(limit=2)
        netliq = nl.dropna()

    ff_d6 = ff.diff(6)
    nl_d3 = (netliq.pct_change(3, fill_method=None) * 100) if netliq is not None else None

    rows, confs, labels = [], [], []
    for d in idx:
        dr = ff_d6.get(d)
        rr = real.get(d) if real is not None else np.nan
        lq = nl_d3.get(d) if nl_d3 is not None else np.nan
        hits = 1
        if pd.notna(dr) and dr <= -0.25:
            lab, hits = "ผ่อนคลาย", 2
            if pd.notna(ff.get(d)) and ff[d] < 1.0:
                lab, hits = "ท่วม", 3
        elif pd.notna(dr) and dr >= 0.25:
            lab, hits = "ตึงตัว", 2
            if pd.notna(lq) and lq < 0:
                hits = 3
        else:
            if pd.notna(rr) and rr > 1.5:
                lab, hits = "ถึงจุดสูงสุด", 2
            elif pd.notna(ff.get(d)) and ff[d] < 1.0:
                lab, hits = "ท่วม", 2
            else:
                lab, hits = "ถึงจุดสูงสุด", 1
        rows.append(_dist_row(FED_MAP[lab]))
        confs.append(float(np.clip(0.35 + 0.20 * hits, 0.35, 1.0)))
        labels.append(lab)

    ev = _ev_rows(data, ["FEDFUNDS", "REAINTRATREARAT10Y", "T10Y3M", "T10Y2Y",
                         "WALCL", "RRPONTSYD", "WTREGEN"])
    return Framework(name=name, weight=FRAMEWORK_WEIGHTS[name],
                     dist=pd.DataFrame(rows, index=idx),
                     conf=pd.Series(confs, index=idx),
                     label=pd.Series(labels, index=idx), evidence=ev)


def curve_disinversion(data: dict) -> dict | None:
    """
    จับ "การคลายกลับ" ของเส้นอัตราผลตอบแทน

    เส้น 10 ปี − 3 เดือน ที่กลับด้าน (ติดลบ) แล้วกลับมาเป็นบวก
    เป็นสัญญาณเตือนที่แรงกว่าตอนกลับด้านครั้งแรกเสียอีก
    ในอดีตภาวะถดถอยมักเริ่มหลังจากจุดนี้ไม่กี่เดือน
    """
    fred, dead = data.get("fred", {}), set(data.get("dead", []))
    if "T10Y3M" in dead or "T10Y3M" not in fred:
        return None
    s = fred["T10Y3M"].dropna()
    if s.size < 400:
        return None
    # ย้อนดู 18 เดือนล่าสุด — ตัดด้วยวันที่ ไม่ใช่จำนวนแถว
    # เพราะข้อมูลรายวันมีวันหยุดคั่น จำนวนแถวจึงไม่เท่ากับจำนวนวันจริง
    cutoff = s.index[-1] - pd.Timedelta(days=540)
    recent = s[s.index >= cutoff]
    was_inverted = bool((recent < 0).any())
    now_positive = bool(s.iloc[-1] > 0)
    if was_inverted and now_positive:
        neg = recent[recent < 0]
        return {"เกิดขึ้น": True,
                "กลับด้านครั้งล่าสุด": neg.index[-1].date().isoformat(),
                "ค่าปัจจุบัน": float(s.iloc[-1])}
    return {"เกิดขึ้น": False, "ค่าปัจจุบัน": float(s.iloc[-1])}


# ===========================================================================
# ส่วนที่ 6 — กรอบที่ 5 : ตลาดบอกเอง
# ===========================================================================
MK_MAP = {
    "เชิงรุก": {RECOVERY: 0.6, OVERHEAT: 0.4},
    "ระวังตัว": {OVERHEAT: 0.7, STAGFLATION: 0.3},
    "ตั้งรับ": {STAGFLATION: 0.5, REFLATION: 0.5},
    "ตื่นตระหนก": {REFLATION: 1.0},
}


def _ratio(px: pd.DataFrame, a: str, b: str) -> pd.Series | None:
    if a not in px.columns or b not in px.columns:
        return None
    r = (px[a] / px[b]).dropna()
    return r if r.size > 80 else None


def f5_market(data: dict) -> Framework:
    """
    ราคาตลาดออกทุกวินาที ส่วนตัวเลขราชการออกช้า 1-2 เดือน

    กรอบนี้จึงเป็น "ตัวชี้นำ" — เมื่อมันแยกจากกรอบ 1-2 ชัดเจน
    นั่นคือสัญญาณว่ากำลังจะเปลี่ยนช่วง ซึ่งมีค่ามาก
    แต่มันก็หลอกบ่อยที่สุดเช่นกัน จึงให้น้ำหนักโหวตต่ำ
    """
    name = "ตลาดบอกเอง"
    px = data.get("market")
    if px is None or px.empty or "SPY" not in px.columns:
        return _blank(name, "ไม่มีราคาตลาด (ดึงจาก Yahoo ไม่สำเร็จ)")

    pxm = px.resample("ME").last()
    sig: dict[str, pd.Series] = {}
    for key, (a, b, flip) in {
        "สาธารณูปโภค/เทคโนโลยี": ("XLU", "XLK", True),
        "สินค้าจำเป็น/ฟุ่มเฟือย": ("XLP", "XLY", True),
        "หุ้นกู้เสี่ยง/พันธบัตร": ("HYG", "IEF", False),
        "ทองแดง/ทองคำ": ("HG=F", "GC=F", False),
        "หุ้นเท่าน้ำหนัก/ตามมูลค่า": ("RSP", "SPY", False),
    }.items():
        r = _ratio(pxm, a, b)
        if r is None:
            continue
        m = r.pct_change(3, fill_method=None) * 100
        sig[key] = -m if flip else m

    # SPY เทียบเส้น 200 วัน (ประมาณด้วยเฉลี่ย 10 เดือน ซึ่งเทียบเท่ากัน)
    ma10 = pxm["SPY"].rolling(10, min_periods=10).mean()
    above = ((pxm["SPY"] / ma10 - 1) * 100).dropna()
    vix = pxm["^VIX"] if "^VIX" in pxm.columns else None

    if not sig:
        return _blank(name, "ราคาตลาดไม่ครบพอคำนวณอัตราส่วน")

    idx = above.index
    for s in sig.values():
        idx = idx.union(s.index)
    idx = idx.sort_values()

    zs = [MD.zscore(s.reindex(idx).ffill(limit=1), years=5) for s in sig.values()]
    riskon = pd.concat(zs, axis=1).mean(axis=1).dropna()
    above = above.reindex(idx).ffill(limit=1)

    rows, confs, labels = [], [], []
    for d in riskon.index:
        r, ab = float(riskon[d]), above.get(d, np.nan)
        v = float(vix.get(d, np.nan)) if vix is not None else np.nan
        if pd.notna(v) and v >= 30:
            lab, hits = "ตื่นตระหนก", 3
        elif pd.notna(ab) and ab < 0:
            lab, hits = ("ตื่นตระหนก", 3) if r < -0.8 else ("ตั้งรับ", 2)
        elif r >= 0.30:
            lab, hits = "เชิงรุก", 2
        else:
            lab, hits = "ระวังตัว", 1
        rows.append(_dist_row(MK_MAP[lab]))
        confs.append(float(np.clip(0.30 + 0.20 * hits, 0.30, 0.90)))
        labels.append(lab)

    ev = []
    for k, s in sig.items():
        sv = s.dropna()
        if sv.empty:
            continue
        zv = MD.zscore(s, years=5).dropna()
        ev.append({"ตัวชี้วัด": k, "รหัส": "ราคาตลาด",
                   "ค่าล่าสุด": float(sv.iloc[-1]), "หน่วย": "% 3 เดือน",
                   "เปลี่ยน 3 เดือน": np.nan,
                   "z (10 ปี)": float(zv.iloc[-1]) if zv.size else np.nan,
                   "ณ วันที่": sv.index[-1].date().isoformat(), "น้ำหนัก": 1.0})
    if not above.dropna().empty:
        ev.append({"ตัวชี้วัด": "S&P 500 เทียบเส้น 200 วัน", "รหัส": "SPY",
                   "ค่าล่าสุด": float(above.dropna().iloc[-1]), "หน่วย": "%",
                   "เปลี่ยน 3 เดือน": np.nan, "z (10 ปี)": np.nan,
                   "ณ วันที่": above.dropna().index[-1].date().isoformat(), "น้ำหนัก": 1.0})
    if vix is not None and not vix.dropna().empty:
        ev.append({"ตัวชี้วัด": "ดัชนีความผันผวน VIX", "รหัส": "^VIX",
                   "ค่าล่าสุด": float(vix.dropna().iloc[-1]), "หน่วย": "",
                   "เปลี่ยน 3 เดือน": np.nan, "z (10 ปี)": np.nan,
                   "ณ วันที่": vix.dropna().index[-1].date().isoformat(), "น้ำหนัก": 1.0})

    return Framework(name=name, weight=FRAMEWORK_WEIGHTS[name],
                     dist=pd.DataFrame(rows, index=riskon.index),
                     conf=pd.Series(confs, index=riskon.index),
                     label=pd.Series(labels, index=riskon.index), evidence=ev)


# ===========================================================================
# ส่วนที่ 7 — การโหวต
# ===========================================================================
def vote(frameworks: list[Framework]) -> dict:
    """
    รวมโหวตของทุกกรอบ

        คะแนนช่วง X = Σ (น้ำหนักกรอบ × ความมั่นใจกรอบ × น้ำหนักที่กรอบให้ X)
        คะแนนเห็นพ้อง = คะแนนผู้ชนะ ÷ คะแนนรวม × 100

    **กรอบที่ใช้ไม่ได้จะถูกตัดออกและน้ำหนักถูกเกลี่ยใหม่โดยอัตโนมัติ**
    ไม่ใช่ปล่อยให้กรอบที่ข้อมูลตายแล้วมาถ่วงผล
    """
    usable = [f for f in frameworks if f.usable and not f.dist.empty]
    if not usable:
        return {"ใช้ได้": False, "เหตุผล": "ไม่มีกรอบไหนมีข้อมูลพอตัดสิน"}

    idx = usable[0].dist.index
    for f in usable[1:]:
        idx = idx.union(f.dist.index)
    idx = idx.sort_values()

    wsum = sum(f.weight for f in usable)
    score = pd.DataFrame(0.0, index=idx, columns=QUADS)
    for f in usable:
        d = f.dist.reindex(idx).ffill(limit=3)
        c = f.conf.reindex(idx).ffill(limit=3).fillna(0.0)
        w = f.weight / wsum
        for q in QUADS:
            score[q] += d[q].fillna(0.0) * c * w

    tot = score.sum(axis=1).replace(0, np.nan)
    share = score.div(tot, axis=0).dropna(how="all")
    if share.empty:
        return {"ใช้ได้": False, "เหตุผล": "คำนวณคะแนนโหวตไม่ได้"}

    winner = share.idxmax(axis=1)
    agree = (share.max(axis=1) * 100).round(1)

    cur_q = str(winner.iloc[-1])
    cur_agree = float(agree.iloc[-1])

    # อยู่ช่วงนี้มาแล้วกี่เดือนติดต่อกัน
    months = 1
    for k in range(len(winner) - 2, -1, -1):
        if winner.iloc[k] == cur_q:
            months += 1
        else:
            break

    return {
        "ใช้ได้": True,
        "ช่วงปัจจุบัน": cur_q,
        "ช่วงอังกฤษ": QUAD_EN[cur_q],
        "คำอธิบายช่วง": QUAD_DESC[cur_q],
        "คะแนนเห็นพ้อง": cur_agree,
        "ระดับความชัด": clarity(cur_agree),
        "ตัวคูณการปรับพอร์ต": rebalance_factor(cur_agree),
        "อยู่ช่วงนี้มากี่เดือน": months,
        "คะแนนแต่ละช่วง": {q: round(float(share[q].iloc[-1]) * 100, 1) for q in QUADS},
        "ประวัติช่วง": winner,
        "ประวัติคะแนนเห็นพ้อง": agree,
        "ประวัติส่วนแบ่ง": share,
        "กรอบที่ใช้": [f.name for f in usable],
        "กรอบที่ตัดออก": [(f.name, f.note) for f in frameworks if not f.usable],
    }


def clarity(agree: float) -> str:
    if agree >= 70:
        return "ชัดเจน"
    if agree >= 50:
        return "ค่อนข้างชัด แต่มีเสียงค้าน"
    if agree >= 35:
        return "กำลังเปลี่ยนผ่าน"
    return "ไม่ชัดเจน"


def rebalance_factor(agree: float) -> float:
    """
    ปรับพอร์ตได้กี่ส่วนของส่วนต่างที่คำนวณได้

    ยิ่งกรอบเห็นไม่ตรงกัน ยิ่งควรขยับน้อย — ต้นทุนที่กินผลตอบแทน
    นักลงทุนรายย่อยมากที่สุดคือการปรับพอร์ตบ่อยเกินไปตามสัญญาณที่ยังไม่ชัด
    """
    if agree >= 70:
        return 1.00
    if agree >= 50:
        return 0.50
    if agree >= 35:
        return 0.25
    return 0.0


# ===========================================================================
# ส่วนที่ 8 — ฝั่งไทย (รอบนี้อ่านแบบเบาจากราคาตลาด)
# ===========================================================================
def thai_read(data: dict) -> dict:
    """
    อ่านฝั่งไทยจากราคาตลาดล้วน

    **ยอมรับตรง ๆ ว่านี่คือการอ่านแบบเบา** — ยังไม่มีตัวเลขเศรษฐกิจไทยจริง
    (เงินเฟ้อ ดอกเบี้ยนโยบาย ผลผลิตอุตสาหกรรม) จนกว่าจะต่อ API ธปท. ในรอบ 2
    ข้อมูลไทยใน FRED ถูกถอดออกหมดแล้ว จึงไม่มีทางลัด
    """
    px = data.get("market")
    if px is None or px.empty or "^SET.BK" not in px.columns:
        return {"ใช้ได้": False, "เหตุผล": "ดึงดัชนี SET ไม่สำเร็จ"}

    set_ = px["^SET.BK"].dropna()
    if set_.size < 220:
        return {"ใช้ได้": False, "เหตุผล": "ข้อมูล SET สั้นเกินไป"}

    ma200 = set_.rolling(200, min_periods=200).mean()
    above = float(set_.iloc[-1] / ma200.iloc[-1] - 1) * 100
    r3 = float(set_.iloc[-1] / set_.iloc[-64] - 1) * 100 if set_.size > 64 else np.nan
    r12 = float(set_.iloc[-1] / set_.iloc[-252] - 1) * 100 if set_.size > 252 else np.nan

    thb = px["THB=X"].dropna() if "THB=X" in px.columns else None
    thb_r3 = (float(thb.iloc[-1] / thb.iloc[-64] - 1) * 100
              if thb is not None and thb.size > 64 else np.nan)

    if above > 0 and (pd.isna(r3) or r3 > 0):
        phase = "ขาขึ้น"
    elif above > 0:
        phase = "พักตัวในขาขึ้น"
    elif pd.notna(r3) and r3 < -5:
        phase = "ขาลง"
    else:
        phase = "ฐานราคาไม่ชัด"

    return {
        "ใช้ได้": True, "สถานะตลาด": phase,
        "SET เทียบเส้น 200 วัน": round(above, 2),
        "SET 3 เดือน": round(r3, 2) if pd.notna(r3) else None,
        "SET 12 เดือน": round(r12, 2) if pd.notna(r12) else None,
        "USDTHB 3 เดือน": round(thb_r3, 2) if pd.notna(thb_r3) else None,
        "บาทอ่อนหรือแข็ง": ("อ่อนค่า" if pd.notna(thb_r3) and thb_r3 > 1
                            else "แข็งค่า" if pd.notna(thb_r3) and thb_r3 < -1
                            else "ทรงตัว"),
        "ณ วันที่": set_.index[-1].date().isoformat(),
        "ข้อจำกัด": ("รอบนี้อ่านจากราคาตลาดล้วน ยังไม่มีตัวเลขเศรษฐกิจไทยจริง "
                     "(เงินเฟ้อ ดอกเบี้ยนโยบาย ผลผลิตอุตสาหกรรม) "
                     "ซึ่งจะเพิ่มเมื่อต่อ API ธปท. ในรอบถัดไป"),
    }


# ===========================================================================
# ส่วนที่ 9 — ประกอบทั้งหมด
# ===========================================================================
def _ev_rows(data: dict, sids: list[str]) -> list[dict]:
    """ดึงค่าล่าสุดของตัวชี้วัดที่ระบุ มาแสดงเป็นหลักฐาน"""
    fred, dead = data.get("fred", {}), set(data.get("dead", []))
    out = []
    for sid in sids:
        if sid in dead or sid not in fred:
            continue
        meta = MD.FRED_SERIES.get(sid, {})
        s = MD._to_monthly(fred[sid]).dropna()
        if s.empty:
            continue
        out.append({
            "ตัวชี้วัด": meta.get("th", sid), "รหัส": sid,
            "ค่าล่าสุด": float(s.iloc[-1]), "หน่วย": meta.get("unit", ""),
            "เปลี่ยน 3 เดือน": float(s.iloc[-1] - s.iloc[-4]) if s.size > 3 else np.nan,
            "z (10 ปี)": float(MD.zscore(s).dropna().iloc[-1])
            if MD.zscore(s).dropna().size else np.nan,
            "ณ วันที่": s.index[-1].date().isoformat(), "น้ำหนัก": 1.0,
        })
    return out


def analyze(data: dict | None = None, use_cache: bool = True) -> dict:
    """
    ฟังก์ชันหลัก — เรียกตัวเดียวได้ผลครบ

    คืน dict ที่หน้าเว็บเอาไปแสดงได้ทันที โดยไม่ต้องคำนวณอะไรเพิ่ม
    """
    if data is None:
        data = MD.fetch_all(use_cache=use_cache)

    gi = growth_inflation(data)
    fws = [f1_clock(gi), f2_business(data, gi), f3_credit(data),
           f4_fed(data), f5_market(data)]
    v = vote(fws)

    return {
        "ผลโหวต": v,
        "กรอบทั้งหมด": fws,
        "แกนการเติบโต": gi["growth"],
        "แกนเงินเฟ้อ": gi["inflation"],
        "ฝั่งไทย": thai_read(data),
        "เส้นอัตราผลตอบแทนคลายกลับ": curve_disinversion(data),
        "สุขภาพข้อมูล": MD.health_frame(data.get("health", [])),
        "ข้อมูลที่ตัดออก": data.get("dead", []),
        "เวลาที่ดึงข้อมูล": data.get("เวลาที่ดึง"),
        "จากแคช": data.get("จากแคช", False),
        "มี_fred_key": data.get("มี_fred_key", False),
    }


# ===========================================================================
# ส่วนที่ 10 — ทดสอบตรรกะโดยไม่ต้องต่อเน็ต
# ===========================================================================
def _synthetic(n_years: int = 20, seed: int = 7) -> dict:
    """
    สร้างข้อมูลจำลองที่มีวัฏจักรชัดเจน เพื่อทดสอบว่าตรรกะทำงานถูก

    ทำไมต้องมี : ถ้าทดสอบด้วยข้อมูลจริงอย่างเดียว จะแยกไม่ออกว่า
    "ผลแปลก" เกิดจากบั๊กในโค้ด หรือเศรษฐกิจมันแปลกจริง ๆ
    ข้อมูลจำลองมีคำตอบที่รู้ล่วงหน้า จึงชี้บั๊กได้ตรงจุด
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n_years * 12,
                        freq="ME")
    t = np.arange(len(idx))
    cyc = np.sin(2 * np.pi * t / 84)                    # วัฏจักร 7 ปี
    infl_cyc = np.sin(2 * np.pi * (t - 12) / 84)        # เงินเฟ้อตามหลัง 1 ปี

    def mk(base, amp, noise=0.15, cycle=cyc):
        return pd.Series(base + amp * cycle + rng.normal(0, noise, len(idx)), index=idx)

    fred = {
        "CFNAIMA3": mk(0.0, 0.8),
        "PAYEMS": pd.Series(np.cumsum(150 + 120 * cyc), index=idx),
        "ICSA": mk(230000, -40000, 8000),
        "NEWORDER": pd.Series(np.cumprod(1 + (0.003 + 0.004 * cyc)) * 60000, index=idx),
        "PERMIT": mk(1400, 300, 40),
        "RSAFS": pd.Series(np.cumprod(1 + (0.003 + 0.003 * cyc)) * 400000, index=idx),
        "INDPRO": pd.Series(np.cumprod(1 + (0.001 + 0.003 * cyc)) * 100, index=idx),
        "UMCSENT": mk(80, 15, 3),
        "UNRATE": mk(5.0, -1.5, 0.2),
        "SAHMREALTIME": mk(0.1, -0.45, 0.08),
        "CPIAUCSL": pd.Series(np.cumprod(1 + (0.002 + 0.0015 * infl_cyc)) * 250, index=idx),
        "CPILFESL": pd.Series(np.cumprod(1 + (0.002 + 0.0012 * infl_cyc)) * 250, index=idx),
        "PCEPILFE": pd.Series(np.cumprod(1 + (0.0018 + 0.001 * infl_cyc)) * 100, index=idx),
        "T5YIFR": mk(2.2, 0.5, 0.1, infl_cyc),
        "PPIACO": pd.Series(np.cumprod(1 + (0.002 + 0.004 * infl_cyc)) * 200, index=idx),
        "PCOPPUSDM": mk(8000, 1800, 200, infl_cyc),
        "DCOILWTICO": mk(70, 20, 4, infl_cyc),
        "BAA10Y": mk(2.0, -0.7, 0.12),
        "NFCI": mk(-0.3, -0.4, 0.08),
        "ANFCI": mk(-0.1, -0.3, 0.08),
        "STLFSI4": mk(-0.4, -0.5, 0.1),
        "DRTSCILM": mk(10, -25, 4),
        "FEDFUNDS": mk(2.5, 2.0, 0.1),
        "REAINTRATREARAT10Y": mk(1.2, 0.9, 0.1),
        "T10Y3M": mk(0.8, -1.2, 0.12),
        "T10Y2Y": mk(0.6, -0.9, 0.1),
        "WALCL": mk(8_000_000, -900_000, 40_000),
        "RRPONTSYD": mk(500, -400, 30).clip(lower=0),
        "WTREGEN": mk(600_000, 100_000, 30_000),
        "DTB3": mk(2.4, 2.0, 0.1),
    }

    didx = pd.date_range(end=idx[-1], periods=n_years * 252, freq="B")
    dt = np.arange(len(didx))
    dcyc = np.sin(2 * np.pi * dt / (84 * 21))
    market = pd.DataFrame({
        "SPY": np.cumprod(1 + (0.0004 + 0.0006 * dcyc + rng.normal(0, 0.008, len(didx)))) * 300,
        "RSP": np.cumprod(1 + (0.0004 + 0.0005 * dcyc + rng.normal(0, 0.008, len(didx)))) * 150,
        "XLU": np.cumprod(1 + (0.0003 - 0.0003 * dcyc + rng.normal(0, 0.007, len(didx)))) * 60,
        "XLK": np.cumprod(1 + (0.0006 + 0.0008 * dcyc + rng.normal(0, 0.011, len(didx)))) * 100,
        "XLP": np.cumprod(1 + (0.0003 - 0.0002 * dcyc + rng.normal(0, 0.006, len(didx)))) * 60,
        "XLY": np.cumprod(1 + (0.0005 + 0.0007 * dcyc + rng.normal(0, 0.010, len(didx)))) * 130,
        "HYG": np.cumprod(1 + (0.0002 + 0.0004 * dcyc + rng.normal(0, 0.004, len(didx)))) * 80,
        "IEF": np.cumprod(1 + (0.0001 - 0.0002 * dcyc + rng.normal(0, 0.003, len(didx)))) * 95,
        "GC=F": np.cumprod(1 + (0.0003 - 0.0002 * dcyc + rng.normal(0, 0.008, len(didx)))) * 1800,
        "HG=F": np.cumprod(1 + (0.0002 + 0.0006 * dcyc + rng.normal(0, 0.010, len(didx)))) * 4,
        "^VIX": np.clip(18 - 6 * dcyc + rng.normal(0, 2.5, len(didx)), 9, 60),
        "^SET.BK": np.cumprod(1 + (0.0002 + 0.0005 * dcyc + rng.normal(0, 0.008, len(didx)))) * 1500,
        "THB=X": np.clip(34 - 1.5 * dcyc + rng.normal(0, 0.15, len(didx)), 28, 39),
    }, index=didx)

    health = [MD.check_fresh(k, v, MD.FRED_SERIES.get(k, {})) for k, v in fred.items()]
    return {"fred": fred, "market": market, "health": health, "dead": [],
            "เวลาที่ดึง": pd.Timestamp.now(tz="UTC").isoformat(), "จากแคช": False,
            "มี_fred_key": False}


def selftest() -> int:
    """ทดสอบตรรกะทั้งหมดด้วยข้อมูลจำลอง — ไม่ต้องต่ออินเทอร์เน็ต"""
    print("=" * 68)
    print("ทดสอบตรรกะวัฏจักรเศรษฐกิจด้วยข้อมูลจำลอง (ไม่ต่อเน็ต)")
    print("=" * 68)
    fails = 0

    data = _synthetic()
    r = analyze(data)
    v = r["ผลโหวต"]

    def chk(cond, msg):
        nonlocal fails
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            fails += 1

    chk(v.get("ใช้ได้"), "การโหวตทำงานได้")
    chk(v.get("ช่วงปัจจุบัน") in QUADS, f"ช่วงที่ได้อยู่ใน 4 ช่วง: {v.get('ช่วงปัจจุบัน')}")
    chk(0 <= v.get("คะแนนเห็นพ้อง", -1) <= 100,
        f"คะแนนเห็นพ้องอยู่ในช่วง 0-100: {v.get('คะแนนเห็นพ้อง')}")
    tot = sum(v.get("คะแนนแต่ละช่วง", {}).values())
    chk(abs(tot - 100) < 0.5, f"คะแนนทั้ง 4 ช่วงรวมกันได้ 100: {tot:.1f}")

    print(f"\n  กรอบที่ใช้ได้ {len([f for f in r['กรอบทั้งหมด'] if f.usable])}/5")
    for f in r["กรอบทั้งหมด"]:
        if f.usable:
            rowsum = f.dist.sum(axis=1)
            ok = bool(((rowsum - 1).abs() < 1e-9).all())
            chk(ok, f"{f.name}: น้ำหนักทุกแถวรวมได้ 1 — ล่าสุดว่า \"{f.latest_label()}\"")
            ok2 = bool(f.conf.between(0, 1).all())
            chk(ok2, f"{f.name}: ความมั่นใจอยู่ในช่วง 0-1")
        else:
            print(f"  · {f.name}: ใช้ไม่ได้ — {f.note}")

    # ตัวคูณการปรับพอร์ตต้องลดลงเมื่อคะแนนเห็นพ้องต่ำ
    chk(rebalance_factor(80) == 1.0 and rebalance_factor(60) == 0.5
        and rebalance_factor(40) == 0.25 and rebalance_factor(20) == 0.0,
        "ตัวคูณการปรับพอร์ตลดลงตามคะแนนเห็นพ้องอย่างถูกต้อง")

    # ตัดข้อมูลบางตัวออก แล้วดูว่าระบบยังทำงานและรายงานว่าตัดอะไรออก
    d2 = {**data, "dead": ["BAA10Y", "CFNAIMA3"]}
    r2 = analyze(d2)
    v2 = r2["ผลโหวต"]
    chk(v2.get("ใช้ได้"), "ยังตัดสินได้แม้ข้อมูลบางตัวตาย")
    dropped = [n for n, _ in v2.get("กรอบที่ตัดออก", [])]
    chk("วัฏจักรสินเชื่อ" in dropped,
        f"ตัดกรอบที่ขาดข้อมูลหลักออกจากการโหวตจริง: {dropped}")

    # ฝั่งไทย
    th = r["ฝั่งไทย"]
    chk(th.get("ใช้ได้"), f"อ่านฝั่งไทยได้: {th.get('สถานะตลาด')}")

    print("-" * 68)
    print(f"ผลลัพธ์จำลอง : {v.get('ช่วงปัจจุบัน')} "
          f"({v.get('ช่วงอังกฤษ')}) · เห็นพ้อง {v.get('คะแนนเห็นพ้อง')}% "
          f"· {v.get('ระดับความชัด')}")
    print(f"คะแนนแต่ละช่วง : {v.get('คะแนนแต่ละช่วง')}")
    print("-" * 68)
    print("ผ่านทั้งหมด ✅" if fails == 0 else f"ไม่ผ่าน {fails} ข้อ ❌")
    return 1 if fails else 0


def _cli() -> int:
    import argparse
    p = argparse.ArgumentParser(description="เครื่องยนต์วัฏจักรเศรษฐกิจ")
    p.add_argument("--selftest", action="store_true",
                   help="ทดสอบตรรกะด้วยข้อมูลจำลอง ไม่ต้องต่อเน็ต")
    p.add_argument("--fresh", action="store_true", help="ไม่ใช้แคช ดึงใหม่")
    a = p.parse_args()

    if a.selftest:
        return selftest()

    r = analyze(use_cache=not a.fresh)
    v = r["ผลโหวต"]
    if not v.get("ใช้ได้"):
        print("ตัดสินไม่ได้:", v.get("เหตุผล"))
        return 1
    print("=" * 68)
    print(f"ตอนนี้ : {v['ช่วงปัจจุบัน']} ({v['ช่วงอังกฤษ']})")
    print(f"คะแนนเห็นพ้อง {v['คะแนนเห็นพ้อง']}%  ·  {v['ระดับความชัด']}")
    print(f"อยู่ช่วงนี้มาแล้ว {v['อยู่ช่วงนี้มากี่เดือน']} เดือน")
    print("=" * 68)
    for f in r["กรอบทั้งหมด"]:
        if f.usable:
            print(f"  {f.name:<16} → {f.latest_label():<14} "
                  f"(มั่นใจ {f.conf.iloc[-1]*100:.0f}%)")
        else:
            print(f"  {f.name:<16} → ใช้ไม่ได้ ({f.note})")
    print("-" * 68)
    print("คะแนนแต่ละช่วง:", v["คะแนนแต่ละช่วง"])
    if r["ข้อมูลที่ตัดออก"]:
        print("ข้อมูลที่ถูกตัดออก:", ", ".join(r["ข้อมูลที่ตัดออก"]))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
