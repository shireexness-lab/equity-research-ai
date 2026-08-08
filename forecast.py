"""
forecast.py — Module 7 : Forecast Engine
=========================================
พยากรณ์ 10 ปีข้างหน้า × 3 ฉาก (Bull / Base / Bear)

พยากรณ์อะไรบ้าง
----------------
    รายได้ · ต้นทุนขาย · อัตรากำไรขั้นต้น · อัตรากำไรดำเนินงาน · กำไรสุทธิ
    EPS · กระแสเงินสดอิสระ (FCF) · เงินปันผลต่อหุ้น

หลักคิด — ทุกตัวเลขมาจากพฤติกรรมในอดีตของบริษัทเอง
---------------------------------------------------
ระบบนี้ **ไม่เดาตัวเลขขึ้นมาเอง** ทุกสมมติฐานมาจากงบย้อนหลังของหุ้นตัวนั้น
แล้วปรับด้วยหลักเศรษฐศาสตร์ 2 ข้อที่พิสูจน์แล้วในงานวิจัย

**ข้อ 1 — การเติบโตจางลงเสมอ (growth fade)**
บริษัทที่โต 20% ต่อปีจะโตแบบนั้นตลอดไปไม่ได้ ถ้าโตได้จริงจะใหญ่กว่า
เศรษฐกิจทั้งประเทศในไม่กี่สิบปี ระบบจึงให้อัตราโตค่อย ๆ ลดจาก
อัตราปัจจุบันไปหาอัตราโตระยะยาว (2.5%) ภายใน 10 ปี

**ข้อ 2 — อัตรากำไรกลับสู่ค่าเฉลี่ย (margin mean reversion)**
ปีที่กำไรดีผิดปกติจะดึงคู่แข่งเข้ามา ปีที่แย่ผิดปกติจะทำให้คู่แข่งถอนตัว
ระบบจึงให้อัตรากำไรค่อย ๆ เคลื่อนจากค่าปีล่าสุดไปหาค่ากลางย้อนหลัง

ทำไมสองข้อนี้สำคัญ
-------------------
โมเดลที่ต่ออัตราโตปีล่าสุดออกไป 10 ปีตรง ๆ คือสาเหตุที่ DCF ของ BCP
ให้มูลค่า 190 บาททั้งที่ราคาจริง 45 บาท เพราะเอาปีที่ค่าการกลั่นดีที่สุด
ไปคาดว่าจะดีแบบนั้นตลอดไป

3 ฉาก
------
    Bear  โตช้ากว่าฐาน · อัตรากำไรหดกว่าค่าเฉลี่ย
    Base  ตามพฤติกรรมในอดีต + การจางตามธรรมชาติ
    Bull  โตเร็วกว่าฐาน · รักษาอัตรากำไรได้ดีกว่าค่าเฉลี่ย

ข้อจำกัดที่ต้องบอกให้ชัด
-------------------------
**นี่คือการต่อเส้นแนวโน้ม ไม่ใช่การทำนายอนาคต**
โมเดลไม่รู้ว่าบริษัทกำลังจะออกสินค้าใหม่ เสียลูกค้ารายใหญ่ หรือโดนกฎหมายใหม่
ยิ่งปีไกลออกไปยิ่งเชื่อได้น้อยลง — ปีที่ 1-3 พอใช้ได้ ปีที่ 8-10 เป็นเพียงกรอบ

และถ้าข้อมูลย้อนหลังสั้น (หุ้นไทยมักมี 4 ปี) ค่าเฉลี่ยที่ได้จะไม่เสถียร
ระบบจะเตือนเมื่อข้อมูลไม่พอ

วิธีใช้จาก Terminal
-------------------
    python3 forecast.py AAPL
    python3 forecast.py PTT.BK --years 10 --scenario base
"""

import sys

import numpy as np
import pandas as pd

# อัตราโตระยะยาวที่การเติบโตจะจางลงไปหา
# ใช้ 2.5% ซึ่งใกล้เคียงอัตราโตของเศรษฐกิจโลกระยะยาว
# ไม่มีบริษัทใดโตเร็วกว่าเศรษฐกิจที่ตัวเองอยู่ได้ตลอดกาล
TERMINAL_G = 0.025

# จำนวนปีที่ให้การเติบโตจางลงจนถึงอัตราระยะยาว
FADE_YEARS = 10

# ---------------------------------------------------------------------------
# ปรับแต่งแต่ละฉาก
#
#   g_add     บวก/ลบจากอัตราโตฐาน (จุดทศนิยม เช่น 0.03 = +3%)
#   margin    ตัวคูณอัตรากำไรเป้าหมาย
#   fade      ความเร็วในการจาง (1.0 = ปกติ · >1 จางเร็วขึ้น)
#
# ตัวเลขเหล่านี้เป็นการตัดสินใจเชิงนโยบาย ไม่ใช่ผลจากข้อมูล
# จึงเปิดให้ผู้ใช้แก้ได้ และแสดงไว้ในรายงานเสมอเพื่อความโปร่งใส
# ---------------------------------------------------------------------------
SCENARIOS = {
    "Bear": {"g_add": -0.04, "margin": 0.85, "fade": 1.4,
             "คำอธิบาย": "โตช้ากว่าอดีต 4% ต่อปี · อัตรากำไรหดเหลือ 85% ของค่าเฉลี่ย "
                         "· การเติบโตจางเร็วกว่าปกติ"},
    "Base": {"g_add": 0.0, "margin": 1.0, "fade": 1.0,
             "คำอธิบาย": "ต่อจากพฤติกรรมในอดีต พร้อมการจางตามธรรมชาติ"},
    "Bull": {"g_add": 0.04, "margin": 1.12, "fade": 0.7,
             "คำอธิบาย": "โตเร็วกว่าอดีต 4% ต่อปี · รักษาอัตรากำไรได้ 112% ของค่าเฉลี่ย "
                         "· การเติบโตจางช้ากว่าปกติ"},
}


def _s(raw, key):
    """ดึงอนุกรมตัวเลขจาก raw แล้วทำความสะอาด"""
    v = raw.get(key)
    if v is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(pd.Series(v), errors="coerce").dropna()


def _cagr(s: pd.Series):
    """
    อัตราโตเฉลี่ยทบต้น

    ใช้ได้เฉพาะเมื่อค่าแรกและค่าสุดท้ายเป็นบวก
    ถ้าค่าแรกติดลบ สูตรจะให้ผลที่ไม่มีความหมายทางคณิตศาสตร์
    """
    s = s.dropna()
    if len(s) < 2:
        return None
    first, last = float(s.iloc[0]), float(s.iloc[-1])
    n = len(s) - 1
    if first <= 0 or last <= 0 or n <= 0:
        return None
    return (last / first) ** (1 / n) - 1


def _ratio_median(num: pd.Series, den: pd.Series):
    """ค่ากลางของอัตราส่วน — ใช้ค่ากลางเพราะทนต่อปีที่ผิดปกติกว่าค่าเฉลี่ย"""
    n = min(len(num), len(den))
    if n < 1:
        return None
    a = num.iloc[-n:].values
    b = den.iloc[-n:].values
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(b != 0, a / b, np.nan)
    r = r[np.isfinite(r)]
    return float(np.median(r)) if len(r) else None


def base_assumptions(R: dict) -> dict:
    """
    สกัดสมมติฐานจากงบย้อนหลังของบริษัทเอง

    ทุกค่าที่คืนมาต้องอธิบายได้ว่ามาจากตัวเลขไหนในงบ
    ไม่มีค่าใดที่ "ตั้งขึ้นมาเอง" นอกจากค่าสำรองเมื่อคำนวณไม่ได้จริง ๆ
    """
    raw = R.get("raw", {})
    rev = _s(raw, "revenue")
    net = _s(raw, "net_income")
    ebit = _s(raw, "ebit")
    ocf = _s(raw, "ocf")
    capex = _s(raw, "capex")
    fcf = _s(raw, "fcf")
    eps = _s(raw, "eps")
    div = _s(raw, "dividends_paid")
    shares = _s(raw, "shares_diluted")

    n_years = len(rev)
    warn = []
    if n_years < 5:
        warn.append(f"มีข้อมูลเพียง {n_years} ปี — ค่าเฉลี่ยที่ได้ไม่เสถียร "
                    "และอาจอยู่ในช่วงเดียวของวัฏจักรทั้งหมด")

    # อัตรากำไรขั้นต้น — จากตารางอัตราส่วนถ้ามี
    gm_hist = None
    try:
        gm = pd.to_numeric(R["table"].loc["Gross Margin"], errors="coerce").dropna()
        gm_hist = float(gm.median()) / 100 if len(gm) else None
        gm_last = float(gm.iloc[-1]) / 100 if len(gm) else None
    except Exception:
        gm_last = None
    if gm_hist is None:
        warn.append("ไม่มีอัตรากำไรขั้นต้นในงบ (พบในธนาคารและบริษัทที่ไม่แยกต้นทุนขาย) "
                    "— จะพยากรณ์เฉพาะระดับกำไรสุทธิ")

    om_hist = _ratio_median(ebit, rev)
    nm_hist = _ratio_median(net, rev)
    nm_last = float(net.iloc[-1] / rev.iloc[-1]) if len(net) and len(rev) else None

    capex_ratio = _ratio_median(capex.abs(), rev)
    ocf_ratio = _ratio_median(ocf, rev)

    # อัตราจ่ายปันผล — ใช้ค่ากลาง เพราะบางปีบริษัทจ่ายพิเศษ
    payout = None
    if len(div) and len(net):
        n = min(len(div), len(net))
        p = np.abs(div.iloc[-n:].values) / np.where(
            net.iloc[-n:].values != 0, net.iloc[-n:].values, np.nan)
        p = p[np.isfinite(p) & (p >= 0) & (p <= 2)]
        payout = float(np.median(p)) if len(p) else None

    g_rev = _cagr(rev)
    if g_rev is None:
        g_rev = 0.03
        warn.append("คำนวณอัตราโตรายได้ย้อนหลังไม่ได้ (รายได้ปีแรกติดลบหรือเป็นศูนย์) "
                    "— ใช้ 3% เป็นค่าเริ่มต้น")
    # กันค่าสุดโต่ง : บริษัทที่โต 80% ต่อปีจาก 2 ปีข้อมูล ไม่ควรถูกต่อออกไป 10 ปี
    g_rev = float(np.clip(g_rev, -0.15, 0.35))

    # จำนวนหุ้น — ดูว่าบริษัทซื้อหุ้นคืนหรือเพิ่มทุนเป็นปกติไหม
    g_shares = _cagr(shares) if len(shares) >= 2 else 0.0
    g_shares = float(np.clip(g_shares or 0.0, -0.05, 0.10))

    return {
        "จำนวนปีข้อมูล": n_years,
        "รายได้ปีล่าสุด": float(rev.iloc[-1]) if len(rev) else None,
        "อัตราโตรายได้ย้อนหลัง (%)": g_rev * 100,
        "อัตรากำไรขั้นต้น ค่ากลาง (%)": gm_hist * 100 if gm_hist else None,
        "อัตรากำไรขั้นต้น ปีล่าสุด (%)": gm_last * 100 if gm_last else None,
        "อัตรากำไรดำเนินงาน ค่ากลาง (%)": om_hist * 100 if om_hist else None,
        "อัตรากำไรสุทธิ ค่ากลาง (%)": nm_hist * 100 if nm_hist else None,
        "อัตรากำไรสุทธิ ปีล่าสุด (%)": nm_last * 100 if nm_last else None,
        "CapEx / รายได้ (%)": capex_ratio * 100 if capex_ratio else None,
        "OCF / รายได้ (%)": ocf_ratio * 100 if ocf_ratio else None,
        "อัตราจ่ายปันผล (%)": payout * 100 if payout else None,
        "จำนวนหุ้นล่าสุด": float(shares.iloc[-1]) if len(shares) else None,
        "อัตราเปลี่ยนจำนวนหุ้น (%)": g_shares * 100,
        "FCF ปีล่าสุด": float(fcf.iloc[-1]) if len(fcf) else None,
        "EPS ปีล่าสุด": float(eps.iloc[-1]) if len(eps) else None,
        "_g_rev": g_rev, "_gm": gm_hist, "_gm_last": gm_last,
        "_om": om_hist, "_nm": nm_hist, "_nm_last": nm_last,
        "_capex": capex_ratio, "_ocf": ocf_ratio, "_payout": payout,
        "_g_shares": g_shares,
        "คำเตือน": warn,
    }


def _fade_path(g0, years, fade=1.0, g_end=TERMINAL_G):
    """
    เส้นทางอัตราโตที่จางจาก g0 ไปหา g_end

    ใช้การจางแบบเรขาคณิต ไม่ใช่เส้นตรง เพราะการชะลอตัวจริงมักเร็วในช่วงต้น
    แล้วค่อย ๆ ราบลง — สอดคล้องกับงานวิจัยเรื่อง growth persistence
    """
    out = []
    for t in range(1, years + 1):
        w = (1 - t / (FADE_YEARS + 1)) ** max(fade, 0.1)
        out.append(g_end + (g0 - g_end) * w)
    return out


def forecast(R: dict, years=10, scenario="Base", custom=None) -> dict:
    """
    สร้างตารางพยากรณ์ 1 ฉาก

    custom : dict ทับค่าที่ระบบสกัดมาได้ เช่น {"g_rev": 0.08, "nm": 0.12}
             ใช้เมื่อผู้ใช้มีข้อมูลที่ระบบไม่รู้ (เช่น บริษัทประกาศแผนขยายกำลังผลิต)
    """
    a = base_assumptions(R)
    sc = dict(SCENARIOS.get(scenario, SCENARIOS["Base"]))
    c = custom or {}

    rev0 = c.get("rev0", a["รายได้ปีล่าสุด"])
    if not rev0 or rev0 <= 0:
        return {"ใช้ได้": False, "เหตุผล": "ไม่มีรายได้ปีล่าสุด จึงพยากรณ์ไม่ได้"}

    g0 = c.get("g_rev", a["_g_rev"]) + sc["g_add"]
    g0 = float(np.clip(g0, -0.20, 0.40))
    path = _fade_path(g0, years, fade=sc["fade"])

    # อัตรากำไรเป้าหมาย = ค่ากลางย้อนหลัง x ตัวคูณของฉาก
    gm_t = (c.get("gm", a["_gm"]) or 0) * sc["margin"] if a["_gm"] else None
    nm_t = (c.get("nm", a["_nm"]) or 0) * sc["margin"] if a["_nm"] else None
    om_t = (c.get("om", a["_om"]) or 0) * sc["margin"] if a["_om"] else None

    gm_now = a["_gm_last"] if a["_gm_last"] is not None else gm_t
    nm_now = a["_nm_last"] if a["_nm_last"] is not None else nm_t

    capex_r = c.get("capex", a["_capex"]) or 0.05
    ocf_r = c.get("ocf", a["_ocf"])
    payout = c.get("payout", a["_payout"])
    payout = float(np.clip(payout if payout is not None else 0.3, 0.0, 1.0))
    sh = a["จำนวนหุ้นล่าสุด"] or 1.0
    g_sh = a["_g_shares"]

    rows = []
    rev = float(rev0)
    for t, g in enumerate(path, 1):
        rev *= (1 + g)

        # อัตรากำไรเคลื่อนจากค่าปัจจุบันไปหาเป้าหมายภายใน 5 ปี
        # ใช้ 5 ปีเพราะงานวิจัยพบว่าอัตรากำไรกลับสู่ค่าเฉลี่ยภายใน 3-7 ปี
        w = min(t / 5.0, 1.0)
        gm = (gm_now + (gm_t - gm_now) * w) if (gm_t is not None and gm_now is not None) else None
        nm = (nm_now + (nm_t - nm_now) * w) if (nm_t is not None and nm_now is not None) else None
        om = om_t

        cogs = rev * (1 - gm) if gm is not None else None
        gross = rev * gm if gm is not None else None
        ebit_v = rev * om if om is not None else None
        net = rev * nm if nm is not None else None

        sh_t = sh * ((1 + g_sh) ** t)
        eps = net / sh_t if (net is not None and sh_t) else None
        dps = (net * payout / sh_t) if (net is not None and sh_t) else None

        # FCF : ถ้ามีอัตรา OCF/รายได้ ใช้ตัวนั้น ไม่งั้นประมาณจากกำไรสุทธิ
        ocf_v = rev * ocf_r if ocf_r else (net * 1.25 if net is not None else None)
        capex_v = rev * capex_r
        fcf_v = (ocf_v - capex_v) if ocf_v is not None else None

        rows.append({
            "ปีที่": t,
            "รายได้": rev,
            "ต้นทุนขาย": cogs,
            "กำไรขั้นต้น": gross,
            "อัตรากำไรขั้นต้น (%)": gm * 100 if gm is not None else None,
            "กำไรดำเนินงาน": ebit_v,
            "อัตรากำไรดำเนินงาน (%)": om * 100 if om is not None else None,
            "กำไรสุทธิ": net,
            "อัตรากำไรสุทธิ (%)": nm * 100 if nm is not None else None,
            "EPS": eps,
            "FCF": fcf_v,
            "เงินปันผลต่อหุ้น": dps,
            "อัตราโตรายได้ (%)": g * 100,
            "จำนวนหุ้น": sh_t,
        })

    df = pd.DataFrame(rows)
    return {
        "ใช้ได้": True,
        "ฉาก": scenario,
        "คำอธิบายฉาก": sc["คำอธิบาย"],
        "ตาราง": df,
        "สมมติฐาน": a,
        "ตัวปรับของฉาก": {k: sc[k] for k in ("g_add", "margin", "fade")},
        "อัตราโตปีแรก (%)": path[0] * 100,
        "อัตราโตปีสุดท้าย (%)": path[-1] * 100,
        "คำเตือน": a["คำเตือน"],
    }


def forecast_all(R: dict, years=10, custom=None) -> dict:
    """สร้างครบทั้ง 3 ฉาก + ตารางสรุปเปรียบเทียบ"""
    out = {"ฉาก": {}, "คำเตือน": []}
    for name in ("Bear", "Base", "Bull"):
        f = forecast(R, years=years, scenario=name, custom=custom)
        out["ฉาก"][name] = f
        if not f.get("ใช้ได้"):
            out["ใช้ได้"] = False
            out["เหตุผล"] = f.get("เหตุผล")
            return out
    out["ใช้ได้"] = True
    out["คำเตือน"] = out["ฉาก"]["Base"].get("คำเตือน", [])

    # ตารางเทียบ 3 ฉากในตัวชี้วัดสำคัญ
    cmp_rows = []
    for metric in ("รายได้", "กำไรสุทธิ", "EPS", "FCF", "เงินปันผลต่อหุ้น"):
        row = {"รายการ": metric}
        for name in ("Bear", "Base", "Bull"):
            d = out["ฉาก"][name]["ตาราง"]
            v = d[metric].iloc[-1] if metric in d.columns else None
            row[name] = v
        cmp_rows.append(row)
    out["เทียบ 3 ฉาก (ปีสุดท้าย)"] = pd.DataFrame(cmp_rows).set_index("รายการ")
    return out


def to_dcf_inputs(fc: dict) -> dict:
    """
    แปลงผลพยากรณ์เป็นข้อมูลเข้าสำหรับ DCF

    ใช้ FCF ที่พยากรณ์ไว้แทนการต่อ FCF ปีฐานด้วยอัตราโตคงที่
    ซึ่งสะท้อนการเปลี่ยนแปลงของอัตรากำไรและ CapEx ได้ละเอียดกว่า
    """
    if not fc.get("ใช้ได้"):
        return {}
    df = fc["ตาราง"]
    return {"FCF รายปี": df["FCF"].tolist(),
            "ปี": int(len(df)),
            "อัตราโตปีสุดท้าย": float(df["อัตราโตรายได้ (%)"].iloc[-1]) / 100}


# ---------------------------------------------------------------------------
# ใช้จาก Terminal
# ---------------------------------------------------------------------------

def _nm_txt(r):
    v = r["อัตรากำไรสุทธิ (%)"]
    return f"{v:.1f}" if pd.notna(v) else "—"


def _fmt(v, unit=1e6, dec=0):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v / unit:,.{dec}f}"


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="พยากรณ์ 10 ปี × 3 ฉาก")
    p.add_argument("ticker")
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--scenario", default="all",
                   choices=["all", "bear", "base", "bull"])
    a = p.parse_args()

    from data_layer import get_stock_data
    from ratios import compute_ratios

    t = a.ticker.upper()
    print(f"\nกำลังดึงข้อมูล {t} ...")
    data = get_stock_data(t)
    R = compute_ratios(data)
    cur = data.get("info", {}).get("currency", "")

    res = forecast_all(R, years=a.years)
    if not res.get("ใช้ได้"):
        print(f"\n  พยากรณ์ไม่ได้ : {res.get('เหตุผล')}\n")
        return 1

    asm = res["ฉาก"]["Base"]["สมมติฐาน"]
    print("\n" + "=" * 78)
    print(f"  {t} — {data.get('info', {}).get('longName', '')}")
    print("=" * 78)
    print("\n  [สมมติฐานที่สกัดจากงบย้อนหลัง]")
    for k in ("จำนวนปีข้อมูล", "อัตราโตรายได้ย้อนหลัง (%)",
              "อัตรากำไรขั้นต้น ค่ากลาง (%)", "อัตรากำไรสุทธิ ค่ากลาง (%)",
              "อัตรากำไรสุทธิ ปีล่าสุด (%)", "CapEx / รายได้ (%)",
              "OCF / รายได้ (%)", "อัตราจ่ายปันผล (%)",
              "อัตราเปลี่ยนจำนวนหุ้น (%)"):
        v = asm.get(k)
        s = f"{v:,.2f}" if isinstance(v, float) else str(v)
        print(f"    {k:<32}{s:>12}")

    for w in res["คำเตือน"]:
        print(f"\n  [เตือน] {w}")

    want = ["Bear", "Base", "Bull"] if a.scenario == "all" else [a.scenario.capitalize()]
    for name in want:
        f = res["ฉาก"][name]
        print(f"\n{'-' * 78}")
        print(f"  ฉาก {name} — {f['คำอธิบายฉาก']}")
        print(f"  อัตราโตปีแรก {f['อัตราโตปีแรก (%)']:.1f}% "
              f"-> ปีสุดท้าย {f['อัตราโตปีสุดท้าย (%)']:.1f}%")
        print(f"{'-' * 78}")
        d = f["ตาราง"]
        print(f"  {'ปี':>3}{'รายได้(ล.)':>13}{'กำไรสุทธิ(ล.)':>15}"
              f"{'NM%':>7}{'EPS':>9}{'FCF(ล.)':>12}{'ปันผล/หุ้น':>11}")
        for _, r in d.iterrows():
            print(f"  {int(r['ปีที่']):>3}{_fmt(r['รายได้']):>13}"
                  f"{_fmt(r['กำไรสุทธิ']):>15}"
                  f"{_nm_txt(r):>7}"
                  f"{_fmt(r['EPS'], 1, 2):>9}{_fmt(r['FCF']):>12}"
                  f"{_fmt(r['เงินปันผลต่อหุ้น'], 1, 3):>11}")

    print(f"\n{'=' * 78}")
    print(f"  เทียบ 3 ฉาก ณ ปีที่ {a.years}  (สกุลเงิน {cur})")
    print("=" * 78)
    c = res["เทียบ 3 ฉาก (ปีสุดท้าย)"]
    print(f"  {'รายการ':<20}{'Bear':>16}{'Base':>16}{'Bull':>16}")
    for idx, r in c.iterrows():
        unit = 1 if idx in ("EPS", "เงินปันผลต่อหุ้น") else 1e6
        dec = 2 if unit == 1 else 0
        print(f"  {idx:<20}{_fmt(r['Bear'], unit, dec):>16}"
              f"{_fmt(r['Base'], unit, dec):>16}{_fmt(r['Bull'], unit, dec):>16}")

    print("\n  หมายเหตุ : ตัวเลขในหน่วยล้าน ยกเว้น EPS และเงินปันผลต่อหุ้น")
    print("  นี่คือการต่อเส้นแนวโน้มจากอดีต **ไม่ใช่การทำนายอนาคต**")
    print("  ปีที่ 1-3 พอใช้อ้างอิงได้ · ปีที่ 8-10 เป็นเพียงกรอบความเป็นไปได้\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
