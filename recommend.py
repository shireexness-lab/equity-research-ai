"""
recommend.py — Module 9 + 11 : คำแนะนำพร้อมเหตุผลที่ตรวจสอบได้
=================================================================
สรุปทุกโมดูลเป็นข้อสรุปเดียว : Strong Buy / Buy / Accumulate / Hold / Reduce / Sell
พร้อม **เหตุผลละเอียดที่ย้อนกลับไปหาตัวเลขต้นทางได้ทุกข้อ**

ทำไมใช้กฎ ไม่ใช่ AI ภาษา
--------------------------
ตามกฎเหล็กข้อ 1 ของโครงการ : โค้ดคำนวณ AI เล่าเรื่อง
การตัดสินใจซื้อ-ขายเป็นเรื่องของ **ตัวเลข** ไม่ใช่เรื่องของภาษา

ระบบนี้จึงใช้กฎถ่วงน้ำหนักที่เขียนไว้ชัดเจน ซึ่งได้เปรียบ 3 ข้อ

  1. **ผลเหมือนเดิมทุกครั้ง** — ข้อมูลชุดเดิมให้คำตอบเดิมเสมอ
     ต่างจากโมเดลภาษาที่ตอบไม่เหมือนกันสองครั้งติด
  2. **ตรวจสอบย้อนได้** — ทุกคะแนนบอกได้ว่ามาจากตัวเลขไหน คูณน้ำหนักเท่าไร
  3. **ไม่มีค่าใช้จ่ายต่อครั้ง** และไม่มีทางที่ระบบจะ "มโนตัวเลข" ขึ้นมาเอง

Explainable AI (Part 11) — หัวใจอยู่ตรงนี้
--------------------------------------------
นอกจากบอกว่า "ควรทำอะไร" ระบบยังบอกด้วยว่า

    • แต่ละปัจจัยดันคะแนนขึ้นหรือลงกี่คะแนน
    • **อะไรจะทำให้ข้อสรุปเปลี่ยน** เช่น "ถ้าราคาลงถึง 38 บาท จะเป็น Buy"
    • ข้อสรุปนี้เชื่อได้แค่ไหน จากข้อมูลกี่ปีและกี่วิธีที่สอดคล้องกัน

วิธีใช้จาก Terminal
-------------------
    python3 recommend.py AAPL
    python3 recommend.py PTT.BK --rf 0.025
"""

import sys

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# ระดับคำแนะนำ — เรียงจากบวกมากไปลบมาก
#
# ใช้ 6 ระดับตามที่กำหนด โดยมี "Accumulate" คั่นระหว่าง Buy กับ Hold
# ความหมายต่างจาก Buy ตรงที่ให้ทยอยซื้อ ไม่ใช่ซื้อทีเดียว
# เหมาะกับกรณีที่ตัวเลขดีแต่ยังมีจุดที่ต้องติดตาม
# ---------------------------------------------------------------------------
LEVELS = [
    (82, "Strong Buy", "#1b6b3a",
     "ตัวเลขทุกด้านสอดคล้องกันและราคาต่ำกว่ามูลค่าอย่างมีนัย"),
    (70, "Buy", "#2e8b57",
     "คุณภาพดีและราคาน่าสนใจ แต่ยังมีบางด้านที่ต้องติดตาม"),
    (60, "Accumulate", "#6aa84f",
     "พื้นฐานใช้ได้ ราคาพอไปได้ — เหมาะกับการทยอยสะสม ไม่ใช่ซื้อทีเดียว"),
    (45, "Hold", "#c9a227",
     "ตัวเลขกลาง ๆ ไม่มีเหตุผลชัดเจนทั้งซื้อเพิ่มและขายออก"),
    (33, "Reduce", "#d1793a",
     "มีจุดอ่อนหลายด้าน หรือราคาสูงกว่ามูลค่าพอสมควร"),
    (0, "Sell", "#c1442e",
     "ราคาสูงกว่ามูลค่ามาก หรือพื้นฐานมีปัญหาชัดเจน"),
]


# ---------------------------------------------------------------------------
# น้ำหนักของแต่ละด้าน (รวม 100)
#
# ทำไมมูลค่าได้น้ำหนักสูงสุด : ธุรกิจดีแค่ไหน ถ้าจ่ายแพงเกินไปก็ขาดทุนได้
# ทำไมความน่าเชื่อถือถูกแยกออกมา : ไม่ได้ให้คะแนนหุ้น แต่ใช้ปรับ "ความมั่นใจ"
# ---------------------------------------------------------------------------
WEIGHTS = {
    "มูลค่า (ส่วนลดจากราคา)": 30,
    "คุณภาพกิจการ": 20,
    "Buffett Score": 15,
    "ความเสี่ยง": 15,
    "แนวโน้มการเติบโต": 10,
    "ตำแหน่งในวัฏจักร": 5,
    "ข่าวและเหตุการณ์": 5,
}


def _f(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _score_discount(disc):
    """
    แปลงส่วนลดจากมูลค่าเป็นคะแนน 0-100

    ไม่ใช้เส้นตรง เพราะส่วนลด 60% กับ 80% ไม่ได้ต่างกันมากในทางปฏิบัติ
    (ทั้งคู่คือ "ถูกมากจนน่าสงสัยว่ามีอะไรที่เราไม่รู้")
    แต่ส่วนลด 0% กับ 20% ต่างกันมาก
    """
    if disc is None:
        return None
    if disc >= 50:
        return 96.0
    if disc >= 30:
        return 84.0 + (disc - 30) * 0.6
    if disc >= 15:
        return 68.0 + (disc - 15) * 1.07
    if disc >= 0:
        return 50.0 + disc * 1.2
    if disc >= -20:
        return 32.0 + (disc + 20) * 0.9
    if disc >= -50:
        return 15.0 + (disc + 50) * 0.57
    return 6.0


def build(data, R, v=None, risk=None, qual=None, fc=None, news=None) -> dict:
    """
    รวมทุกโมดูลเป็นข้อสรุปเดียว

    v     : ผลจาก valuation.value_stock
    risk  : ผลจาก risk.assess
    qual  : ผลจาก quality.assess_all
    fc    : ผลจาก forecast.forecast_all
    news  : ผลจาก news_ai.analyze
    ทุกตัวไม่มีก็ได้ — ระบบจะปรับน้ำหนักตามข้อมูลที่มีจริง
    """
    factors = []          # แต่ละด้าน : ชื่อ · คะแนน · น้ำหนัก · หลักฐาน

    # ---- 1. มูลค่า ----
    disc = _f((v or {}).get("ส่วนต่างจากราคา (%)"))
    price = _f((v or {}).get("ราคาปัจจุบัน"))
    fair = _f((v or {}).get("fair_value (ค่ากลางทุกวิธี)"))
    sc = _score_discount(disc)
    if sc is not None:
        n_methods = len([x for x in (v.get("methods") or {}).values()
                         if x is not None and np.isfinite(x) and x > 0])
        factors.append({
            "ด้าน": "มูลค่า (ส่วนลดจากราคา)", "คะแนน": sc,
            "น้ำหนัก": WEIGHTS["มูลค่า (ส่วนลดจากราคา)"],
            "หลักฐาน": (f"ราคา {price:,.2f} · มูลค่าที่ประเมินได้ {fair:,.2f} "
                        f"(ค่ากลางจาก {n_methods} วิธี) · ส่วนต่าง {disc:+.1f}%"),
        })

    # ---- 2. คุณภาพกิจการ ----
    if qual and qual.get("Module 2"):
        m = qual["Module 2"]
        if m.get("คะแนนรวม") is not None:
            factors.append({
                "ด้าน": "คุณภาพกิจการ", "คะแนน": float(m["คะแนนรวม"]),
                "น้ำหนัก": WEIGHTS["คุณภาพกิจการ"],
                "หลักฐาน": (f"ประเมินได้ {m['ให้คะแนนได้']}/{m['จำนวนหัวข้อ']} หัวข้อ "
                            f"· มาจากงบโดยตรง {m['สัดส่วนจากงบ (%)']:.0f}%"),
            })

    # ---- 3. Buffett Score ----
    if qual and qual.get("Module 3"):
        m = qual["Module 3"]
        if m.get("คะแนนรวม") is not None:
            factors.append({
                "ด้าน": "Buffett Score", "คะแนน": float(m["คะแนนรวม"]),
                "น้ำหนัก": WEIGHTS["Buffett Score"],
                "หลักฐาน": f"{m['คะแนนรวม']:.0f}/100 — {m.get('ระดับ','')}",
            })

    # ---- 4. ความเสี่ยง (กลับด้าน : เสี่ยงน้อย = คะแนนสูง) ----
    if risk and risk.get("คะแนนรวม") is not None:
        rs = 100 - float(risk["คะแนนรวม"])
        top = risk.get("เสี่ยงสูงสุด") or []
        factors.append({
            "ด้าน": "ความเสี่ยง", "คะแนน": rs, "น้ำหนัก": WEIGHTS["ความเสี่ยง"],
            "หลักฐาน": (f"คะแนนเสี่ยงรวม {risk['คะแนนรวม']:.0f}/100 "
                        f"({risk.get('ระดับ','')}) · สูงสุด: "
                        + " · ".join(f"{n} {s:.0f}" for n, s in top[:2])),
        })

    # ---- 5. แนวโน้มการเติบโต ----
    if fc and fc.get("ใช้ได้"):
        base = fc["ฉาก"]["Base"]
        g0 = _f(base.get("อัตราโตปีแรก (%)"))
        if g0 is not None:
            gs = float(np.clip(50 + g0 * 2.5, 5, 95))
            d = base["ตาราง"]
            eps_now = _f(base["สมมติฐาน"].get("EPS ปีล่าสุด"))
            eps_end = _f(d["EPS"].iloc[-1]) if "EPS" in d.columns else None
            ev = f"คาดรายได้โตปีแรก {g0:+.1f}%"
            if eps_now and eps_end and eps_now > 0:
                ev += f" · EPS ปีที่ {len(d)} คาด {eps_end:,.2f} (จาก {eps_now:,.2f})"
            factors.append({"ด้าน": "แนวโน้มการเติบโต", "คะแนน": gs,
                            "น้ำหนัก": WEIGHTS["แนวโน้มการเติบโต"], "หลักฐาน": ev})

    # ---- 6. ตำแหน่งในวัฏจักร ----
    if qual and qual.get("Module 5") and qual["Module 5"].get("คะแนนรวม") is not None:
        m = qual["Module 5"]
        factors.append({
            "ด้าน": "ตำแหน่งในวัฏจักร", "คะแนน": float(m["คะแนนรวม"]),
            "น้ำหนัก": WEIGHTS["ตำแหน่งในวัฏจักร"],
            "หลักฐาน": m.get("สรุปตำแหน่งวัฏจักร", ""),
        })

    # ---- 7. ข่าว ----
    if news and news.get("ใช้ได้") and news.get("Impact Score") is not None:
        imp = float(news["Impact Score"])
        factors.append({
            "ด้าน": "ข่าวและเหตุการณ์", "คะแนน": float(np.clip(50 + imp / 2, 5, 95)),
            "น้ำหนัก": WEIGHTS["ข่าวและเหตุการณ์"],
            "หลักฐาน": (f"อ่าน {news['จำนวนข่าว']} ข่าว · "
                        f"บวก {news['บวก']} · ลบ {news['ลบ']} · "
                        f"กลาง {news['กลาง']} · Impact {imp:+.0f}"),
        })

    if not factors:
        return {"ใช้ได้": False, "เหตุผล": "ไม่มีข้อมูลพอสำหรับสรุปคำแนะนำ"}

    # ---- รวมคะแนนถ่วงน้ำหนักตามด้านที่มีจริง ----
    wsum = sum(f["น้ำหนัก"] for f in factors)
    total = sum(f["คะแนน"] * f["น้ำหนัก"] for f in factors) / wsum

    for f in factors:
        f["น้ำหนักจริง (%)"] = f["น้ำหนัก"] / wsum * 100
        # ผลต่อคะแนนรวม เทียบกับถ้าด้านนี้ได้ 50 (กลาง ๆ)
        f["ดันคะแนน"] = (f["คะแนน"] - 50) * f["น้ำหนัก"] / wsum

    # ---- ปรับด้วยความน่าเชื่อถือ ----
    # ข้อมูลน้อยหรือวิธีต่าง ๆ ขัดกัน -> ดึงข้อสรุปเข้าหากลาง (Hold)
    # เพราะความมั่นใจต่ำไม่ควรนำไปสู่คำแนะนำที่รุนแรง
    rel = _f((v or {}).get("ความน่าเชื่อถือ", {}).get("คะแนน")) if v else None
    if rel is None:
        rel = _f(((v or {}).get("bands") or {}).get("คะแนน"))
    conf = float(np.clip((rel if rel is not None else 60) / 100, 0.3, 1.0))
    adj = 50 + (total - 50) * (0.55 + 0.45 * conf)

    label = color = why = None
    for cut, name, col, desc in LEVELS:
        if adj >= cut:
            label, color, why = name, col, desc
            break

    # ---- อะไรจะทำให้ข้อสรุปเปลี่ยน (Explainable AI) ----
    triggers = []
    if price and fair and fair > 0:
        for cut, name, _, _ in LEVELS:
            if name == label:
                continue
            # หาราคาที่ทำให้คะแนนรวมข้ามไปอีกระดับ
            target = _price_for_level(factors, wsum, conf, cut, fair, price)
            if target and 0 < target < price * 5:
                triggers.append({
                    "ถ้า": f"ราคาเปลี่ยนเป็น {target:,.2f}",
                    "จะกลายเป็น": name,
                    "ห่างจากราคาปัจจุบัน": f"{(target/price - 1)*100:+.1f}%",
                })
    triggers = sorted(triggers, key=lambda t: abs(float(
        t["ห่างจากราคาปัจจุบัน"].rstrip("%"))))[:3]

    ranked = sorted(factors, key=lambda f: f["ดันคะแนน"], reverse=True)
    return {
        "ใช้ได้": True,
        "คำแนะนำ": label,
        "สี": color,
        "คำอธิบายระดับ": why,
        "คะแนนรวม": adj,
        "คะแนนก่อนปรับความมั่นใจ": total,
        "ความมั่นใจ (%)": conf * 100,
        "ปัจจัย": factors,
        "ตารางปัจจัย": pd.DataFrame(factors).set_index("ด้าน"),
        "หนุนมากที่สุด": [f for f in ranked if f["ดันคะแนน"] > 0][:3],
        "ฉุดมากที่สุด": [f for f in ranked if f["ดันคะแนน"] < 0][-3:][::-1],
        "อะไรจะเปลี่ยนข้อสรุป": triggers,
        "ราคาปัจจุบัน": price,
        "มูลค่าที่ประเมินได้": fair,
    }


def _price_for_level(factors, wsum, conf, cut, fair, price):
    """
    หาราคาที่ทำให้คะแนนรวมพอดีกับขีดแบ่งระดับหนึ่ง

    ใช้การไล่หาทีละขั้น (bisection) เพราะฟังก์ชันคะแนนส่วนลดไม่ใช่เส้นตรง
    จึงแก้สมการย้อนกลับตรง ๆ ไม่ได้
    """
    others = sum(f["คะแนน"] * f["น้ำหนัก"] for f in factors
                 if f["ด้าน"] != "มูลค่า (ส่วนลดจากราคา)")
    w_val = next((f["น้ำหนัก"] for f in factors
                  if f["ด้าน"] == "มูลค่า (ส่วนลดจากราคา)"), 0)
    if not w_val:
        return None

    def adj_at(p):
        d = (1 - p / fair) * 100
        s = _score_discount(d)
        tot = (others + s * w_val) / wsum
        return 50 + (tot - 50) * (0.55 + 0.45 * conf)

    lo, hi = fair * 0.05, fair * 4.0
    if (adj_at(lo) - cut) * (adj_at(hi) - cut) > 0:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        if (adj_at(lo) - cut) * (adj_at(mid) - cut) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# ใช้จาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="สรุปคำแนะนำพร้อมเหตุผล")
    p.add_argument("ticker")
    p.add_argument("--rf", type=float, default=None)
    a = p.parse_args()

    from data_layer import get_stock_data
    from ratios import compute_ratios
    from valuation import value_stock
    import risk as RK, quality as QL, forecast as FC, news_ai as NA

    t = a.ticker.upper()
    print(f"\nกำลังวิเคราะห์ {t} ...")
    data = get_stock_data(t)
    R = compute_ratios(data)
    v = value_stock(data, R, rf=a.rf)
    try:
        from bands import build as build_bands
        v["ความน่าเชื่อถือ"] = build_bands(data, v)["ความน่าเชื่อถือ"]
    except Exception:
        pass
    rk = RK.assess(data, R)
    ql = QL.assess_all(data, R, v=v, rf=a.rf)
    fc = FC.forecast_all(R)
    nw = NA.analyze(t)

    res = build(data, R, v=v, risk=rk, qual=ql, fc=fc, news=nw)
    if not res.get("ใช้ได้"):
        print(f"  {res.get('เหตุผล')}\n")
        return 1

    print("\n" + "=" * 76)
    print(f"  {t} — {data.get('info', {}).get('longName', '')}")
    print(f"  คำแนะนำ : {res['คำแนะนำ']}   ({res['คะแนนรวม']:.1f}/100)")
    print(f"  {res['คำอธิบายระดับ']}")
    print(f"  ความมั่นใจ {res['ความมั่นใจ (%)']:.0f}% "
          f"(คะแนนก่อนปรับ {res['คะแนนก่อนปรับความมั่นใจ']:.1f})")
    print("=" * 76)

    print(f"\n  {'ด้าน':<28}{'คะแนน':>8}{'น้ำหนัก':>9}{'ดันคะแนน':>11}")
    print("  " + "-" * 58)
    for f in res["ปัจจัย"]:
        print(f"  {f['ด้าน']:<28}{f['คะแนน']:>8.1f}"
              f"{f['น้ำหนักจริง (%)']:>8.0f}%{f['ดันคะแนน']:>+11.1f}")
        print(f"     {f['หลักฐาน']}")

    print("\n  [หนุนมากที่สุด]")
    for f in res["หนุนมากที่สุด"]:
        print(f"    + {f['ด้าน']} ({f['ดันคะแนน']:+.1f} คะแนน)")
    if res["ฉุดมากที่สุด"]:
        print("\n  [ฉุดมากที่สุด]")
        for f in res["ฉุดมากที่สุด"]:
            print(f"    − {f['ด้าน']} ({f['ดันคะแนน']:+.1f} คะแนน)")

    if res["อะไรจะเปลี่ยนข้อสรุป"]:
        print("\n  [อะไรจะทำให้ข้อสรุปเปลี่ยน]")
        for tg in res["อะไรจะเปลี่ยนข้อสรุป"]:
            print(f"    {tg['ถ้า']} ({tg['ห่างจากราคาปัจจุบัน']}) "
                  f"-> {tg['จะกลายเป็น']}")

    print("\n  ข้อสรุปนี้มาจากกฎถ่วงน้ำหนักที่เขียนไว้ชัดเจน ไม่ใช่โมเดลภาษา")
    print("  ข้อมูลชุดเดิมจะให้คำตอบเดิมเสมอ และตรวจย้อนได้ทุกคะแนน")
    print("\n  **ไม่ใช่คำแนะนำการลงทุน** — เป็นการสรุปตัวเลขเพื่อการศึกษา\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
