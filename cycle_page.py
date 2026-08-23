"""
cycle_page.py — หน้าเว็บ "วัฏจักรเศรษฐกิจ" (Part 18)
=====================================================
หน้าที่ : วาดหน้าจอทั้งหมดของโหมดวัฏจักรเศรษฐกิจ

แยกออกมาเป็นไฟล์ต่างหากแทนที่จะเขียนลง app.py โดยตรง เพราะ
app.py ยาว 7,000 บรรทัดแล้ว การเพิ่มอีก 600 บรรทัดเข้าไปจะทำให้แก้ยากขึ้นมาก
app.py จึงเรียกแค่ `cycle_page.render()` บรรทัดเดียว

โครงหน้า 3 ชั้น (ตาม 25_วัฏจักรเศรษฐกิจ.md)
  ชั้น 1  คำตอบใน 3 วินาที — นาฬิกา + ช่วงปัจจุบัน + คะแนนเห็นพ้อง
  ชั้น 2  หลักฐาน — 5 กรอบโหวตยังไง + ตารางตัวชี้วัดทุกตัว
  ชั้น 3  แล้วต้องทำอะไร — น้ำหนักเป้าหมาย + ส่วนต่างจากพอร์ตของผู้ใช้
"""

from __future__ import annotations

import base64
import io
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import allocation as AL
import cycle as CY
import macro_data as MD

BASE_DIR = Path(__file__).resolve().parent

# สีประจำแต่ละช่วง — เลือกให้สื่อความหมายทันทีโดยไม่ต้องอ่านคำอธิบาย
# เขียว = ดีต่อสินทรัพย์เสี่ยง · ส้ม = ระวัง · แดง = อันตราย · น้ำเงิน = หลบเข้าพันธบัตร
QUAD_COLOR = {
    CY.RECOVERY: "#16a34a",
    CY.OVERHEAT: "#ea580c",
    CY.STAGFLATION: "#dc2626",
    CY.REFLATION: "#2563eb",
}
QUAD_SOFT = {
    CY.RECOVERY: "#16a34a22",
    CY.OVERHEAT: "#ea580c22",
    CY.STAGFLATION: "#dc262622",
    CY.REFLATION: "#2563eb22",
}


# ===========================================================================
# ส่วนที่ 1 — รูปนาฬิกาการลงทุน
# ===========================================================================
def _ensure_thai_font() -> None:
    """
    ทำให้กราฟแสดงภาษาไทยได้

    ถ้าไม่ทำ matplotlib จะวาดตัวอักษรไทยเป็นสี่เหลี่ยมเปล่าทั้งหมด
    ลองใช้ตัวตั้งค่าเดิมของโปรเจกต์ก่อน ถ้าไม่มีค่อยลงทะเบียนฟอนต์จาก fonts/ เอง
    """
    try:
        import report as RP
        RP.setup_matplotlib_font()
        return
    except Exception:                                         # noqa: BLE001
        pass
    try:
        import matplotlib
        from matplotlib import font_manager as fm
        fdir = BASE_DIR / "fonts"
        names = []
        for f in list(fdir.glob("*.ttf")) + list(fdir.glob("*.otf")):
            try:
                fm.fontManager.addfont(str(f))
                names.append(fm.FontProperties(fname=str(f)).get_name())
            except Exception:                                 # noqa: BLE001
                continue
        if names:
            matplotlib.rcParams["font.family"] = names[0]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:                                         # noqa: BLE001
        pass


def clock_figure(growth: pd.Series, inflation: pd.Series,
                 quad: str, months: int = 24, dark: bool = False):
    """
    วาดนาฬิกาการลงทุน — แกนนอนคือการเติบโต แกนตั้งคือเงินเฟ้อ

    ที่วาด "เส้นทางย้อนหลัง 24 เดือน" ไม่ใช่แค่จุดเดียว เพราะทิศทางที่กำลังเดินไป
    มีค่ามากกว่าตำแหน่งปัจจุบัน — เห็นได้ทันทีว่ากำลังเข้าหรือกำลังออกจากช่วงนั้น
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Wedge

    _ensure_thai_font()

    fg = "#e5e7eb" if dark else "#111827"
    grid = "#4b5563" if dark else "#d1d5db"

    fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=150)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    # ---- ขนาดวงปรับตามข้อมูลจริง ----
    #
    # ตอนแรกตั้งตายตัวไว้ที่ ±3 เท่าของความผันผวน ซึ่งเป็นค่าสุดโต่ง
    # ที่เศรษฐกิจจริงแทบไม่เคยไปถึง ผลคือเส้นทางทั้ง 24 เดือนอัดกันเป็นจุดเดียว
    # กลางวง มองไม่ออกว่ากำลังเดินไปทางไหน ซึ่งคือสิ่งเดียวที่รูปนี้ต้องบอก
    #
    # จึงเปลี่ยนเป็นขยายให้พอดีข้อมูล แล้ว **เขียนกำกับว่าวงนอกเท่ากับเท่าไร**
    # เพื่อไม่ให้การซูมเข้าไปหลอกตาว่าความเคลื่อนไหวรุนแรงกว่าความจริง
    _idx0 = growth.index.intersection(inflation.index)
    _g0 = growth.reindex(_idx0).iloc[-months:]
    _i0 = inflation.reindex(_idx0).iloc[-months:]
    _peak = float(np.nanmax(np.abs(np.concatenate(
        [_g0.to_numpy(), _i0.to_numpy()])))) if _g0.size else 1.0
    if not np.isfinite(_peak):
        _peak = 1.0
    R = float(np.clip(_peak * 1.35, 1.0, 3.0))
    lim = R * 1.30                        # ขอบภาพเผื่อที่ให้ป้ายแกน
    #                                       ^ ต้องประกาศตรงนี้ ก่อนเริ่มวาด
    #  เคยไปประกาศไว้ท้ายฟังก์ชัน แล้วเรียกใช้ตั้งแต่ตอนวาดข้อความกำกับ
    #  ทำให้หน้าเว็บพังด้วย UnboundLocalError
    # 4 ควอดแรนต์ — วางตามหลักเศรษฐศาสตร์
    #   ขวาบน (โต+, เฟ้อ+) ร้อนแรง · ซ้ายบน (โต-, เฟ้อ+) เงินเฟ้อฝืด
    #   ซ้ายล่าง (โต-, เฟ้อ-) เงินฝืด · ขวาล่าง (โต+, เฟ้อ-) ฟื้นตัว
    wedges = [(0, 90, CY.OVERHEAT), (90, 180, CY.STAGFLATION),
              (180, 270, CY.REFLATION), (270, 360, CY.RECOVERY)]
    for a0, a1, q in wedges:
        ax.add_patch(Wedge((0, 0), R, a0, a1,
                           facecolor=QUAD_COLOR[q],
                           alpha=0.30 if q == quad else 0.10,
                           edgecolor="none", zorder=1))

    ax.add_patch(Circle((0, 0), R, fill=False, lw=1.6, edgecolor=grid, zorder=3))
    for r in (R / 3, R * 2 / 3):          # วงในเลื่อนตามขนาดวงนอกเสมอ
        ax.add_patch(Circle((0, 0), r, fill=False, lw=0.7, ls=":",
                            edgecolor=grid, alpha=0.7, zorder=2))
    # เส้นแบ่งแกน — วาดแค่ภายในวงกลม ไม่ใช่ axhline/axvline ที่ลากยาวเต็มกรอบ
    # เพราะเส้นที่ทะลุออกนอกวงจะไปชนกับป้ายชื่อแกนจนดูรก
    ax.plot([-R, R], [0, 0], color=grid, lw=1.1, zorder=2)
    ax.plot([0, 0], [-R, R], color=grid, lw=1.1, zorder=2)

    # ชื่อช่วงในแต่ละควอดแรนต์
    _L = R * 0.58                         # ตำแหน่งป้ายชื่อช่วง เลื่อนตามขนาดวง
    for (x, y, q) in [(_L, _L, CY.OVERHEAT), (-_L, _L, CY.STAGFLATION),
                      (-_L, -_L, CY.REFLATION), (_L, -_L, CY.RECOVERY)]:
        ax.text(x, y, q, ha="center", va="center",
                fontsize=13 if q == quad else 11,
                fontweight="bold" if q == quad else "normal",
                color=QUAD_COLOR[q],
                alpha=1.0 if q == quad else 0.65, zorder=4)

    # เส้นทางย้อนหลัง
    idx = growth.index.intersection(inflation.index)
    g = growth.reindex(idx).iloc[-months:]
    i = inflation.reindex(idx).iloc[-months:]
    # ต้องมีค่าตั้งต้นก่อนเสมอ เพราะถ้าข้อมูลสั้นเกินจะวาดเส้นทางไม่ได้
    # แล้วโค้ดข้างล่างยังเรียกใช้ตัวแปรนี้อยู่ (บทเรียนเดียวกับ lim)
    mismatch = None
    if g.size >= 2:
        lim_in = R * 0.94
        gx = np.clip(g.to_numpy(), -lim_in, lim_in)
        iy = np.clip(i.to_numpy(), -lim_in, lim_in)
        n = len(gx)
        # เส้นทางไล่จางไปหาเข้ม : จุดเก่าจาง จุดใหม่เข้ม อ่านทิศทางได้ทันที
        for k in range(n - 1):
            ax.plot(gx[k:k + 2], iy[k:k + 2], "-", lw=2.1,
                    color=fg, alpha=0.15 + 0.70 * (k / max(n - 2, 1)), zorder=5)
        ax.scatter(gx[:-1], iy[:-1], s=15, color=fg, alpha=0.45, zorder=6)
        # จุดเริ่มต้นของเส้นทาง เพื่อให้รู้ว่าเดินมาจากไหน
        ax.text(gx[0], iy[0], f"  {i.index[0].strftime('%b %y')}",
                fontsize=7.5, color=fg, alpha=0.55, va="center", zorder=7)
        # ตำแหน่งปัจจุบัน — ระบายสีตาม "ช่วงที่จุดนี้ตกอยู่จริง"
        # ไม่ใช่สีของผลโหวตรวม เพราะสองอย่างนี้ไม่จำเป็นต้องตรงกัน
        # (นาฬิกาเป็นแค่ 1 ใน 5 กรอบ) ถ้าย้อมสีตามผลรวมจะได้จุดสีน้ำเงิน
        # นั่งอยู่กลางพื้นที่สีส้ม ซึ่งดูขัดกันเองโดยไม่มีคำอธิบาย
        own = (CY.OVERHEAT if gx[-1] >= 0 and iy[-1] >= 0 else
               CY.RECOVERY if gx[-1] >= 0 else
               CY.STAGFLATION if iy[-1] >= 0 else CY.REFLATION)
        ax.scatter([gx[-1]], [iy[-1]], s=290, color=QUAD_COLOR[own],
                   edgecolors="white", linewidths=2.4, zorder=9)
        ax.scatter([gx[-1]], [iy[-1]], s=70, color="white", zorder=10)
        # ข้อความกำกับความไม่ตรงกัน เก็บไว้วาดทีหลังพร้อมคำอธิบายใต้รูป
        # เคยวาดไว้ด้านบน แล้วไปทับป้ายแกนเงินเฟ้อจนอ่านซ้อนกันเป็นก้อนเดียว
        mismatch = None if own == quad else f"นาฬิกาชี้ {own} · แต่ผลรวม 5 กรอบคือ {quad}"

    # เผื่อที่ว่างด้านล่างเพิ่มสำหรับคำอธิบาย 2 บรรทัด
    # ไม่งั้นบรรทัดล่างสุดจะถูกตัดขาดครึ่งตัวอักษร
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim * 1.17, lim)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(R + 0.12, -0.26, "การเติบโต →", ha="left", va="center",
            fontsize=9.5, color=fg)
    ax.text(-0.26, R + 0.12, "เงินเฟ้อ →", ha="center", va="bottom",
            rotation=90, fontsize=9.5, color=fg)
    ax.text(0, -lim * 1.03,
            f"จุดใหญ่ = ตอนนี้ · เส้นจาง = {months} เดือนที่ผ่านมา"
            f"  ·  ขอบวง = ±{R:.1f} เท่าของความผันผวนปกติ",
            ha="center", va="center", fontsize=8.2, color=fg, alpha=0.65)
    if mismatch:
        ax.text(0, -lim * 1.12, mismatch, ha="center", va="center",
                fontsize=8.8, color=QUAD_COLOR[quad], alpha=0.95)
    fig.tight_layout(pad=0.2)
    return fig


def clock_figure_3d(growth: pd.Series, inflation: pd.Series, quad: str,
                    months: int = 36, dark: bool = False):
    """
    นาฬิกาการลงทุนแบบ 3 มิติ — แกนที่สามคือเวลา

    ทำไมแกนที่สามต้องเป็นเวลา
    -------------------------
    กราฟ 2 มิติบอกได้แค่ "ตอนนี้อยู่ตรงไหน" แต่วัฏจักรเศรษฐกิจคือ
    **เรื่องของการเคลื่อนที่** สิ่งที่ต้องรู้จริง ๆ คือมาจากไหนและไปทางไหน

    พอยกเวลาขึ้นเป็นแกนตั้ง เส้นทางจะคลี่ออกเป็นเกลียวที่ไต่ขึ้น
    ทำให้เห็นได้ทันทีว่าวนมากี่รอบแล้ว รอบไหนเร็วรอบไหนช้า
    และช่วงไหนที่เศรษฐกิจวนอยู่กับที่ — ซึ่งกราฟ 2 มิติซ่อนไว้ทั้งหมด
    เพราะเส้นทับกันเป็นก้อนเดียว

    ยังคงวาด "เงา" ของเส้นทางลงบนพื้นด้านล่างไว้ด้วย เพื่อให้ยังอ่าน
    แบบนาฬิกา 2 มิติแบบเดิมได้พร้อมกันในรูปเดียว
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    _ensure_thai_font()
    fg = "#e8eaed" if dark else "#111827"
    grid = "#5b6472" if dark else "#c9cfd8"

    idx = growth.index.intersection(inflation.index)
    g = growth.reindex(idx).iloc[-months:]
    i = inflation.reindex(idx).iloc[-months:]
    if g.size < 3:
        return clock_figure(growth, inflation, quad, dark=dark)

    peak = float(np.nanmax(np.abs(np.concatenate([g.to_numpy(), i.to_numpy()]))))
    R = float(np.clip((peak if np.isfinite(peak) else 1.0) * 1.30, 1.0, 3.0))

    gx = np.clip(g.to_numpy(), -R, R)
    iy = np.clip(i.to_numpy(), -R, R)
    n = len(gx)
    z = np.arange(n, dtype=float)

    fig = plt.figure(figsize=(7.6, 7.2), dpi=150)
    fig.patch.set_alpha(0)
    ax = fig.add_subplot(projection="3d")
    ax.set_facecolor("none")

    # ---- พื้นด้านล่าง : 4 ควอดแรนต์ ----
    quads = [((0, R), (0, R), CY.OVERHEAT), ((-R, 0), (0, R), CY.STAGFLATION),
             ((-R, 0), (-R, 0), CY.REFLATION), ((0, R), (-R, 0), CY.RECOVERY)]
    for (x0, x1), (y0, y1), qq in quads:
        verts = [[(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)]]
        ax.add_collection3d(Poly3DCollection(
            verts, facecolor=QUAD_COLOR[qq],
            alpha=0.26 if qq == quad else 0.09, edgecolor="none", zorder=0))

    # เส้นแบ่งแกนบนพื้น
    ax.plot([-R, R], [0, 0], [0, 0], color=grid, lw=1.0, alpha=0.85)
    ax.plot([0, 0], [-R, R], [0, 0], color=grid, lw=1.0, alpha=0.85)

    # ---- ป้ายในแต่ละควอดแรนต์ : ชื่อ + 2 บรรทัด + สินทรัพย์เด่น ----
    try:
        import cycle_knowledge as CK
        has_kb = True
    except Exception:                                         # noqa: BLE001
        has_kb = False

    # ข้อความทั้งก้อนวางที่ระดับพื้น (z=0) เป็นบล็อกเดียวหลายบรรทัด
    # เคยแยกเป็น 3 ก้อนที่ z = 0.15 / −0.9 / −1.9 ซึ่ง z ติดลบอยู่ใต้พื้น
    # และอยู่นอกช่วงแกน จึงถูกดันไปกองผิดตำแหน่งจนล้นออกนอกช่อง
    _L = R * 0.52
    for (x, y, qq) in [(_L, _L, CY.OVERHEAT), (-_L, _L, CY.STAGFLATION),
                       (-_L, -_L, CY.REFLATION), (_L, -_L, CY.RECOVERY)]:
        here = qq == quad
        block = qq
        if has_kb:
            block += "\n" + CK.two_line(qq)
            best = CK.top_assets(qq)
            if best:
                block += f"\n→ {best}"
        ax.text(x, y, 0.02, block, color=QUAD_COLOR[qq], ha="center",
                va="center", multialignment="center",
                fontsize=6.9 if here else 6.2,
                fontweight="bold" if here else "normal",
                alpha=1.0 if here else 0.62, zorder=6, linespacing=1.45)

    # ---- เงาของเส้นทางบนพื้น (อ่านแบบนาฬิกา 2 มิติเดิมได้) ----
    ax.plot(gx, iy, np.zeros(n), color=fg, lw=1.0, alpha=0.22, zorder=1)

    # ---- เส้นทางจริงในมิติเวลา ----
    # ระบายสีทีละท่อนตามควอดแรนต์ที่จุดนั้นตกอยู่ เพื่อให้เห็นว่า
    # เศรษฐกิจข้ามจากโซนไหนไปโซนไหนเมื่อไร โดยไม่ต้องไล่อ่านแกน
    def _q(a, b):
        return (CY.OVERHEAT if a >= 0 and b >= 0 else CY.RECOVERY if a >= 0
                else CY.STAGFLATION if b >= 0 else CY.REFLATION)

    for k in range(n - 1):
        c = QUAD_COLOR[_q(gx[k], iy[k])]
        ax.plot(gx[k:k + 2], iy[k:k + 2], z[k:k + 2], color=c,
                lw=2.6, alpha=0.35 + 0.6 * (k / max(n - 2, 1)), zorder=4)
    ax.scatter(gx[:-1], iy[:-1], z[:-1], s=11,
               c=[QUAD_COLOR[_q(a, b)] for a, b in zip(gx[:-1], iy[:-1])],
               alpha=0.65, zorder=5, depthshade=False)

    # ---- ตำแหน่งปัจจุบัน + เสาดิ่งลงพื้น ----
    own = _q(gx[-1], iy[-1])
    ax.plot([gx[-1], gx[-1]], [iy[-1], iy[-1]], [0, z[-1]],
            color=QUAD_COLOR[own], lw=1.1, ls=":", alpha=0.75, zorder=5)
    ax.scatter([gx[-1]], [iy[-1]], [z[-1]], s=210, color=QUAD_COLOR[own],
               edgecolors="white", linewidths=2.0, zorder=9, depthshade=False)
    ax.text(gx[-1], iy[-1], z[-1] + max(1.5, n * 0.05), "ตอนนี้",
            color=QUAD_COLOR[own], ha="center", fontsize=9, fontweight="bold")

    # ---- แกนและมุมมอง ----
    ax.set_xlim(-R, R)
    ax.set_ylim(-R, R)
    ax.set_zlim(0, n * 1.12)
    ax.set_xlabel("การเติบโต →", fontsize=8.5, color=fg, labelpad=-4)
    ax.set_ylabel("เงินเฟ้อ →", fontsize=8.5, color=fg, labelpad=-4)
    ax.set_zlabel("เวลา →", fontsize=8.5, color=fg, labelpad=-6)
    ax.set_xticks([])
    ax.set_yticks([])

    # แกนเวลาใส่ป้ายเดือนจริงไม่กี่จุด ไม่งั้นจะรกจนอ่านไม่ออก
    ticks = [0, n // 3, 2 * n // 3, n - 1]
    ax.set_zticks(ticks)
    ax.set_zticklabels([i.index[t].strftime("%b %y") for t in ticks],
                       fontsize=6.8, color=fg)
    ax.tick_params(colors=fg, pad=-1)

    for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
        pane.pane.fill = False
        pane.pane.set_edgecolor((0, 0, 0, 0))
        pane._axinfo["grid"]["color"] = grid
        pane._axinfo["grid"]["linewidth"] = 0.35
        pane._axinfo["grid"]["alpha"] = 0.35

    ax.view_init(elev=24, azim=-58)
    try:
        ax.set_box_aspect((1, 1, 0.95))
    except Exception:                                         # noqa: BLE001
        pass

    fig.subplots_adjust(left=0.02, right=0.98, top=1.02, bottom=0.02)
    return fig


def _fig_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight")
    return buf.getvalue()


# ===========================================================================
# ส่วนที่ 2 — ตารางหลักฐาน
# ===========================================================================
def evidence_table(fw: CY.Framework) -> pd.DataFrame:
    """แปลงหลักฐานของกรอบหนึ่งเป็นตารางที่อ่านง่าย"""
    if not fw.evidence:
        return pd.DataFrame()
    df = pd.DataFrame(fw.evidence)

    def arrow(v):
        if pd.isna(v):
            return ""
        return "↑" if v > 0 else ("↓" if v < 0 else "→")

    def zmark(z):
        if pd.isna(z):
            return ""
        if z >= 1.0:
            return f"🟢 สูงกว่าปกติมาก ({z:+.1f})"
        if z >= 0.3:
            return f"🟢 สูงกว่าปกติ ({z:+.1f})"
        if z > -0.3:
            return f"⚪ ใกล้ค่าปกติ ({z:+.1f})"
        if z > -1.0:
            return f"🟠 ต่ำกว่าปกติ ({z:+.1f})"
        return f"🔴 ต่ำกว่าปกติมาก ({z:+.1f})"

    out = pd.DataFrame({
        "ตัวชี้วัด": df["ตัวชี้วัด"],
        "ค่าล่าสุด": [f"{v:,.2f} {u}".strip() for v, u in
                      zip(df["ค่าล่าสุด"], df.get("หน่วย", ""))],
        "3 เดือน": [arrow(v) for v in df.get("เปลี่ยน 3 เดือน", pd.Series(dtype=float))],
        "เทียบตัวเองย้อนหลัง": [zmark(z) for z in df.get("z (10 ปี)", pd.Series(dtype=float))],
        "ณ วันที่": df["ณ วันที่"],
        "รหัสข้อมูล": df["รหัส"],
    })
    return out


def vote_bar(v: dict, dark: bool = False):
    """แถบแสดงว่าคะแนนโหวตกระจายไปช่วงไหนบ้าง"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _ensure_thai_font()
    fg = "#e5e7eb" if dark else "#111827"
    sc = v["คะแนนแต่ละช่วง"]
    order = sorted(CY.QUADS, key=lambda q: -sc.get(q, 0))
    vals = [sc.get(q, 0) for q in order]

    fig, ax = plt.subplots(figsize=(6.4, 2.1), dpi=150)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    bars = ax.barh(range(len(order)), vals,
                   color=[QUAD_COLOR[q] for q in order], height=0.62)
    bars[0].set_alpha(1.0)
    for b in bars[1:]:
        b.set_alpha(0.45)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=10, color=fg)
    ax.invert_yaxis()
    ax.set_xlim(0, max(100, max(vals) * 1.15))
    for k, val in enumerate(vals):
        ax.text(val + 1.5, k, f"{val:.0f}%", va="center", fontsize=9.5, color=fg)
    ax.set_xticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    fig.tight_layout(pad=0.2)
    return fig


# ===========================================================================
# ส่วนที่ 3 — รายงาน PDF
# ===========================================================================
def _font_face_css() -> str:
    """
    ฝังฟอนต์ไทยลงใน PDF

    ถ้าไม่ฝัง WeasyPrint จะวาดภาษาไทยเป็นกล่องสี่เหลี่ยม
    เพราะเครื่องเซิร์ฟเวอร์ไม่มีฟอนต์ไทยติดตั้งไว้
    """
    fdir = BASE_DIR / "fonts"
    if not fdir.exists():
        return ""
    faces = []
    for f in sorted(fdir.glob("*.ttf")) + sorted(fdir.glob("*.otf")):
        name = f.stem.lower()
        weight = "700" if ("bold" in name or "semibold" in name) else "400"
        faces.append(f"@font-face{{font-family:'ThaiApp';"
                     f"src:url('file://{f}');font-weight:{weight};}}")
        if len(faces) >= 4:
            break
    return "".join(faces)


def _prepare_weasyprint() -> None:
    """
    บอกทาง Python ให้หาไลบรารีระบบของ Homebrew เจอ — ก่อนเรียก WeasyPrint

    ปัญหา : WeasyPrint ไม่ได้วาด PDF เอง แต่เรียกไลบรารีของระบบ (pango · cairo ·
    gobject) ซึ่งบน Mac ติดตั้งผ่าน Homebrew ลงที่ /opt/homebrew/lib
    ส่วน Python ที่มาจาก python.org ไม่รู้จักโฟลเดอร์นั้น จึงขึ้นว่า
    "cannot load library 'libgobject-2.0-0'" ทั้งที่ไลบรารีมีอยู่จริง

    ฟังก์ชันนี้เติมเส้นทางนั้นเข้าไปให้เอง จึงมักแก้ได้โดยผู้ใช้ไม่ต้องทำอะไร
    ถ้ายังไม่ได้ (เช่น ยังไม่ได้ brew install) จะไปแสดงวิธีแก้บนหน้าเว็บแทน
    """
    import ctypes.util
    import os
    import platform
    import sys

    if sys.platform != "darwin":
        return
    if ctypes.util.find_library("gobject-2.0"):
        return                                    # หาเจออยู่แล้ว ไม่ต้องทำอะไร

    cands = ["/opt/homebrew/lib"] if platform.machine() == "arm64" else []
    cands += ["/usr/local/lib", "/opt/homebrew/lib"]
    cur = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    parts = [p for p in cur.split(":") if p]
    for p in cands:
        if os.path.isdir(p) and p not in parts:
            parts.append(p)
    if parts:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(parts)


def weasyprint_help_html() -> str:
    """วิธีแก้แบบอ่านบนหน้าเว็บได้ — ไม่ใช่ซ่อนไว้ใน Terminal"""
    import platform
    from pathlib import Path as _P
    lib = "/opt/homebrew/lib" if platform.machine() == "arm64" else "/usr/local/lib"
    installed = _P(lib).exists()
    head = ("**WeasyPrint หาไลบรารีระบบไม่เจอ** — ตัวสร้าง PDF ไม่ได้วาดเอง "
            "แต่เรียกไลบรารีของระบบ (pango · cairo · gobject) ซึ่งยังไม่พร้อม\n\n"
            "ปัญหานี้กระทบ **ปุ่ม PDF ทุกปุ่มในโปรแกรม** ไม่ใช่เฉพาะหน้านี้\n\n")
    if installed:
        return head + (
            "ไลบรารีติดตั้งไว้แล้ว แต่ Python หาไม่เจอ — เปิด Terminal แล้วพิมพ์\n\n"
            f"```\necho 'export DYLD_FALLBACK_LIBRARY_PATH={lib}' >> ~/.zshrc\n"
            "source ~/.zshrc\n```\n\n"
            "แล้วปิด streamlit (Ctrl+C) เปิดใหม่อีกครั้ง")
    return head + (
        "ยังไม่ได้ติดตั้งไลบรารี — เปิด Terminal **แท็บใหม่** แล้วพิมพ์ทีละบรรทัด\n\n"
        "```\nbrew install pango gdk-pixbuf libffi\n"
        f"echo 'export DYLD_FALLBACK_LIBRARY_PATH={lib}' >> ~/.zshrc\n"
        "source ~/.zshrc\n```\n\n"
        "ใช้เวลาราว 2–5 นาที แล้วปิด streamlit (Ctrl+C) เปิดใหม่อีกครั้ง\n\n"
        "ถ้ายังไม่มี Homebrew ให้ติดตั้งก่อนที่ https://brew.sh")


def make_pdf(res: dict, plan: dict, clock_png: bytes) -> bytes:
    """สร้าง PDF สรุปภาวะวัฏจักรเศรษฐกิจ ณ เวลานั้น"""
    _prepare_weasyprint()
    from weasyprint import HTML

    v = res["ผลโหวต"]
    b64 = base64.b64encode(clock_png).decode()
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    fw_rows = "".join(
        f"<tr><td>{f.name}</td><td>{f.latest_label() or '—'}</td>"
        f"<td style='text-align:right'>"
        f"{(f.conf.iloc[-1]*100):.0f}%</td></tr>"
        if f.usable else
        f"<tr><td>{f.name}</td><td colspan='2' class='mute'>ใช้ไม่ได้ — {f.note}</td></tr>"
        for f in res["กรอบทั้งหมด"])

    # ตารางมีสองรูปแบบ : กรอกพอร์ตแล้ว (6 คอลัมน์) กับยังไม่กรอก (2 คอลัมน์)
    # PDF จึงต้องอ่านแบบไม่ยึดชื่อคอลัมน์ตายตัว ไม่งั้นจะพังเมื่อยังไม่ได้กรอกพอร์ต
    tbl = plan["ตาราง"]
    has_pf = "ส่วนต่าง (%)" in tbl.columns
    tgt_col = ("เป้าหมายที่แนะนำ (%)" if has_pf
               else "น้ำหนักเป้าหมายของช่วงนี้ (%)")
    alloc_rows = ""
    for _, r in tbl.iterrows():
        cur = r["พอร์ตตอนนี้ (%)"] if has_pf else None
        cur_txt = "—" if cur is None or pd.isna(cur) else f"{float(cur):.0f}%"
        act = r["ทำอะไร"] if has_pf else "—"
        alloc_rows += (f"<tr><td>{r['สินทรัพย์']}</td>"
                       f"<td style='text-align:right'>{cur_txt}</td>"
                       f"<td style='text-align:right'>{float(r[tgt_col]):.0f}%</td>"
                       f"<td style='text-align:right'>{act}</td></tr>")

    # ---- คลังความรู้ : ตารางเทียบ 4 ช่วง + รายละเอียดของช่วงปัจจุบัน ----
    # ไม่ใส่รายละเอียดครบทั้ง 4 ช่วง เพราะจะยาวเกิน 10 หน้าและกลบเนื้อหาหลัก
    # ผู้ที่อยากอ่านครบดูได้บนหน้าเว็บ
    try:
        import cycle_knowledge as CK
        q = v["ช่วงปัจจุบัน"]
        k = CK.KNOWLEDGE[q]
        kb_rows = "".join(
            f"<tr{' class=here' if r['ช่วง'] == q else ''}>"
            f"<td>{r['ลำดับ']}</td><td><b>{r['ช่วง']}</b><br/>"
            f"<span class=mute>{r['อังกฤษ']}</span></td>"
            f"<td>{r['ลักษณะสำคัญ']}</td><td>{r['สินทรัพย์ที่นำ']}</td>"
            f"<td>{r['สินทรัพย์ที่ควรเลี่ยง']}</td>"
            f"<td>{r['ระยะเวลาในอดีต']}</td></tr>"
            for _, r in CK.summary_table().iterrows())
        kb_assets = "".join(
            f"<tr><td style='white-space:nowrap'>{rt}</td>"
            f"<td><b>{nm}</b><br/><span class=mute>{why}</span></td></tr>"
            for rt, nm, why in k["สินทรัพย์"])
        kb_chars = "".join(f"<li>{x}</li>" for x in k["ลักษณะเศรษฐกิจ"])
        knowledge_html = f"""
<h2>ความรู้ — วัฏจักรเดินตามลำดับนี้</h2>
<table><tr><th>#</th><th>ช่วง</th><th>ลักษณะสำคัญ</th>
<th>สินทรัพย์ที่นำ</th><th>ที่ควรเลี่ยง</th><th>ระยะเวลาในอดีต</th></tr>
{kb_rows}</table>
<div class="mute" style="margin-top:2mm">แถวที่เน้นคือช่วงที่ประเมินว่าอยู่ตอนนี้
· ช่วงถัดไปตามลำดับมักเป็น <b>{k['ช่วงถัดไป']}</b></div>

<h2>รายละเอียดของช่วง {q}</h2>
<p><b>{k['หัวใจ']}</b></p>
<b>ลักษณะเศรษฐกิจ</b><ul>{kb_chars}</ul>
<div class="mute">ระยะเวลาในอดีต {k['ระยะเวลาในอดีต']}
· เคยเกิดเมื่อ {k['ตัวอย่างในประวัติศาสตร์']}</div>
<b style="display:block;margin-top:3mm">ควรลงทุนอะไร</b>
<table>{kb_assets}</table>
<p><b>ค่าเงิน</b> — {k['ค่าเงิน']}</p>
<p><b>คริปโต</b> — {k['คริปโต']}</p>
<div class="warn"><b>ควรเลี่ยง</b> — {' · '.join(k['ควรเลี่ยง'])}<br/>
<b>ความเสี่ยงหลัก</b> — {k['ความเสี่ยงหลัก']}</div>
<div class="mute" style="margin-top:3mm">{CK.LEGEND}</div>
"""
    except Exception:                                         # noqa: BLE001
        knowledge_html = ""

    warns = "".join(f"<li>{w}</li>" for w in plan["คำเตือน"])
    ev_rows = ""
    for f in res["กรอบทั้งหมด"]:
        t = evidence_table(f)
        if t.empty:
            continue
        ev_rows += f"<tr class='grp'><td colspan='4'>{f.name}</td></tr>"
        for _, r in t.iterrows():
            ev_rows += (f"<tr><td>{r['ตัวชี้วัด']}</td>"
                        f"<td style='text-align:right'>{r['ค่าล่าสุด']}</td>"
                        f"<td>{r['เทียบตัวเองย้อนหลัง']}</td>"
                        f"<td class='mute'>{r['ณ วันที่']}</td></tr>")

    html = f"""
<style>
  {_font_face_css()}
  @page {{ size: A4; margin: 16mm 14mm; }}
  body {{ font-family:'ThaiApp','Noto Sans Thai','Sarabun',sans-serif;
          font-size:10.5pt; color:#111827; line-height:1.5; }}
  h1 {{ font-size:18pt; margin:0 0 2mm; }}
  h2 {{ font-size:12.5pt; margin:7mm 0 2mm; border-bottom:1.5px solid #e5e7eb;
        padding-bottom:1.5mm; }}
  .sub {{ color:#6b7280; font-size:9pt; margin-bottom:4mm; }}
  .badge {{ display:inline-block; padding:2mm 5mm; border-radius:3mm;
            background:{QUAD_COLOR[v['ช่วงปัจจุบัน']]}; color:#fff;
            font-size:15pt; font-weight:bold; }}
  .kv {{ margin:3mm 0; }}
  .kv span {{ display:inline-block; margin-right:9mm; }}
  table {{ width:100%; border-collapse:collapse; margin-top:2mm; font-size:9.5pt; }}
  th,td {{ border-bottom:1px solid #eceff3; padding:1.6mm 2mm; text-align:left; }}
  th {{ background:#f8fafc; font-weight:600; }}
  tr.grp td {{ background:#f1f5f9; font-weight:600; }}
  tr.here td {{ background:#eef4ff; }}
  ul {{ margin:1mm 0 2mm 5mm; padding:0; }}
  li {{ margin:0.6mm 0; }}
  .mute {{ color:#6b7280; }}
  .warn {{ background:#fffbeb; border-left:3px solid #f59e0b;
           padding:3mm 4mm; margin-top:3mm; font-size:9.5pt; }}
  .disc {{ margin-top:8mm; font-size:8.5pt; color:#6b7280;
           border-top:1px solid #e5e7eb; padding-top:3mm; }}
  img {{ width:88mm; display:block; margin:3mm auto; }}
</style>

<h1>รายงานวัฏจักรเศรษฐกิจ</h1>
<div class="sub">สร้างเมื่อ {now} · Equity Research AI Pro</div>

<div class="badge">{v['ช่วงปัจจุบัน']} ({v['ช่วงอังกฤษ']})</div>
<div class="kv">
  <span><b>คะแนนเห็นพ้อง</b> {v['คะแนนเห็นพ้อง']:.0f}% — {v['ระดับความชัด']}</span>
  <span><b>อยู่ช่วงนี้มาแล้ว</b> {v['อยู่ช่วงนี้มากี่เดือน']} เดือน</span>
</div>
<p>{v['คำอธิบายช่วง']}</p>
<img src="data:image/png;base64,{b64}"/>

<h2>5 กรอบโหวตอย่างไร</h2>
<table><tr><th>กรอบวิเคราะห์</th><th>อ่านได้ว่า</th><th style="text-align:right">ความมั่นใจ</th></tr>
{fw_rows}</table>

<h2>น้ำหนักพอร์ตที่แนะนำ</h2>
<table><tr><th>สินทรัพย์</th><th style="text-align:right">ตอนนี้</th>
<th style="text-align:right">เป้าหมาย</th><th style="text-align:right">ทำอะไร</th></tr>
{alloc_rows}</table>
<div class="warn"><b>ข้อควรระวัง</b><ul>{warns or '<li>ไม่มี</li>'}</ul>
{plan['ที่มาของน้ำหนัก']}</div>

{knowledge_html}

<h2>หลักฐานที่ใช้ตัดสิน</h2>
<table><tr><th>ตัวชี้วัด</th><th style="text-align:right">ค่าล่าสุด</th>
<th>เทียบตัวเองย้อนหลัง</th><th>ณ วันที่</th></tr>
{ev_rows}</table>

<div class="disc">
<b>ไม่ใช่คำแนะนำการลงทุน</b> — รายงานนี้เป็นผลการคำนวณจากข้อมูลเศรษฐกิจสาธารณะ
เพื่อการศึกษาเท่านั้น ไม่ใช่การให้คำแนะนำและไม่ใช่การชักชวนให้ซื้อขายหลักทรัพย์<br/>
วัฏจักรเศรษฐกิจรู้แน่ชัดได้เฉพาะตอนมองย้อนหลัง รายงานนี้เป็นการประมาณแบบเรียลไทม์
ซึ่งจะมีการอ่านผิดบ้าง · ผลตอบแทนในอดีตไม่รับประกันอนาคต<br/>
แหล่งข้อมูล: Federal Reserve Economic Data (FRED) · Yahoo Finance
</div>
"""
    return HTML(string=html, base_url=str(BASE_DIR)).write_pdf()


# ===========================================================================
# ส่วนที่ 4 — หน้าเว็บ
# ===========================================================================
@st.cache_data(show_spinner=False, ttl=6 * 3600)
def _analyze(fresh: bool):
    """คำนวณทั้งหมด — แคช 6 ชม. เพราะตัวเลขเศรษฐกิจออกเดือนละครั้ง"""
    return CY.analyze(use_cache=not fresh)


def render(dark: bool = False) -> None:
    """วาดหน้าวัฏจักรเศรษฐกิจทั้งหมด — app.py เรียกฟังก์ชันนี้ตัวเดียว"""

    c1, c2 = st.columns([1, 3])
    if c1.button("🔄 ดึงข้อมูลใหม่", use_container_width=True,
                 help="ข้ามแคชแล้วดึงตัวเลขล่าสุดจาก FRED และ Yahoo ทันที"):
        _analyze.clear()
        st.session_state["_cycle_fresh"] = True
        st.rerun()

    fresh = st.session_state.pop("_cycle_fresh", False)
    try:
        with st.spinner("กำลังดึงและคำนวณข้อมูลเศรษฐกิจ ..."):
            res = _analyze(fresh)
    except Exception as e:                                    # noqa: BLE001
        st.error(f"ดึงข้อมูลไม่สำเร็จ: {type(e).__name__}: {e}")
        st.info("สาเหตุที่พบบ่อยคือเครือข่ายเข้า FRED หรือ Yahoo ไม่ได้ชั่วคราว "
                "ลองกดปุ่มดึงข้อมูลใหม่อีกครั้งในอีกสักครู่")
        return

    v = res["ผลโหวต"]
    if not v.get("ใช้ได้"):
        st.error(f"ยังตัดสินไม่ได้ — {v.get('เหตุผล')}")
        _health_panel(res)
        return

    quad = v["ช่วงปัจจุบัน"]

    # ---------------- ชั้น 1 : คำตอบใน 3 วินาที ----------------
    left, right = st.columns([1.05, 1])
    with left:
        view = st.radio("มุมมองกราฟ", ["🧊 3 มิติ (มีแกนเวลา)", "⭕ 2 มิติ"],
                        horizontal=True, label_visibility="collapsed",
                        key="cycle_view",
                        help="3 มิติ ยกเวลาขึ้นเป็นแกนตั้ง จึงเห็นว่าวนมากี่รอบแล้ว "
                             "และช่วงไหนวนอยู่กับที่ · 2 มิติ อ่านตำแหน่งปัจจุบันได้เร็วกว่า")
        if view.startswith("🧊"):
            fig = clock_figure_3d(res["แกนการเติบโต"], res["แกนเงินเฟ้อ"],
                                  quad, dark=dark)
        else:
            fig = clock_figure(res["แกนการเติบโต"], res["แกนเงินเฟ้อ"],
                               quad, dark=dark)
        st.pyplot(fig, use_container_width=True)

        # รายงาน PDF ใช้ภาพ 2 มิติเสมอ เพราะบนกระดาษ A4 ที่หมุนดูไม่ได้
        # มุมมองเอียงของภาพ 3 มิติกินพื้นที่มากแต่อ่านตำแหน่งได้ยากกว่า
        clock_png = _fig_png(clock_figure(res["แกนการเติบโต"],
                                          res["แกนเงินเฟ้อ"], quad))

    with right:
        st.markdown(
            f"<div style='background:{QUAD_SOFT[quad]};border-left:6px solid "
            f"{QUAD_COLOR[quad]};border-radius:10px;padding:18px 20px;'>"
            f"<div style='font-size:0.85rem;opacity:.75;'>ตอนนี้เศรษฐกิจอยู่ช่วง</div>"
            f"<div style='font-size:2.1rem;font-weight:700;line-height:1.25;"
            f"color:{QUAD_COLOR[quad]};'>{quad}</div>"
            f"<div style='font-size:.95rem;opacity:.7;'>{v['ช่วงอังกฤษ']}</div>"
            f"</div>", unsafe_allow_html=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("คะแนนเห็นพ้อง", f"{v['คะแนนเห็นพ้อง']:.0f}%", v["ระดับความชัด"],
                  delta_color="off",
                  help="5 กรอบเห็นตรงกันแค่ไหน — ยิ่งสูงยิ่งเชื่อได้")
        m2.metric("อยู่ช่วงนี้มาแล้ว", f"{v['อยู่ช่วงนี้มากี่เดือน']} เดือน")
        m3.metric("ปรับพอร์ตได้", f"{v['ตัวคูณการปรับพอร์ต']*100:.0f}%",
                  help="ของส่วนต่างเต็ม — กรอบเห็นไม่ตรงกันเมื่อไร ควรขยับน้อยลง")

        st.caption(v["คำอธิบายช่วง"])

        if v["คะแนนเห็นพ้อง"] < 50:
            st.warning("**กรอบวิเคราะห์ยังเห็นไม่ตรงกัน** — ช่วงนี้มักเป็นรอยต่อ "
                       "ระหว่างสองช่วง การรอให้สัญญาณชัดขึ้นมักดีกว่าการรีบปรับพอร์ต")

        di = res.get("เส้นอัตราผลตอบแทนคลายกลับ")
        if di and di.get("เกิดขึ้น"):
            st.error(
                f"⚠️ **เส้นอัตราผลตอบแทนคลายกลับแล้ว** — เคยกลับด้านล่าสุดเมื่อ "
                f"{di['กลับด้านครั้งล่าสุด']} ตอนนี้กลับมาเป็นบวก "
                f"({di['ค่าปัจจุบัน']:+.2f}) ในอดีตภาวะถดถอยมักเริ่มหลังจุดนี้ไม่กี่เดือน "
                "และสัญญาณนี้แรงกว่าตอนที่มันกลับด้านครั้งแรกเสียอีก")

    st.caption(_stamp(res))
    st.divider()

    # ---------------- ชั้น 2 : หลักฐาน ----------------
    st.markdown("### หลักฐานและความรู้")
    tabs = st.tabs(["5 กรอบโหวตยังไง", "ตัวชี้วัดทุกตัว", "🇹🇭 ฝั่งไทย",
                    "สุขภาพข้อมูล", "📚 ความรู้วัฏจักร"])

    with tabs[0]:
        vb1, vb2 = st.columns([1, 1])
        with vb1:
            st.pyplot(vote_bar(v, dark=dark), use_container_width=True)
            st.caption("คะแนนโหวตกระจายไปแต่ละช่วงเท่าไร — "
                       "ถ้าแท่งบนสุดไม่ทิ้งห่างแท่งอื่นชัดเจน แปลว่ายังไม่ควรเชื่อมาก")
        with vb2:
            for f in res["กรอบทั้งหมด"]:
                if not f.usable:
                    st.markdown(f"**{f.name}** &nbsp; :gray[ใช้ไม่ได้]  \n"
                                f":gray[{f.note}]")
                    continue
                lq = f.latest_quad()
                agree_mark = "✅" if lq == quad else "⚠️"
                st.markdown(
                    f"{agree_mark} **{f.name}** — {f.latest_label()}  \n"
                    f":gray[น้ำหนักโหวต {f.weight*100:.0f}% · "
                    f"ความมั่นใจ {f.conf.iloc[-1]*100:.0f}% · "
                    f"โหวตให้ช่วง {lq}]")
                if f.note:
                    st.caption(f.note)
        st.info("**ทำไมต้องใช้ 5 กรอบ** — ไม่มีกรอบไหนถูกตลอด "
                "วัฏจักรธุรกิจแม่นแต่ช้า · วัฏจักรสินเชื่อเตือนล่วงหน้าดีแต่เตือนผิดบ่อย · "
                "ตลาดเร็วที่สุดแต่หลอกบ่อยที่สุด "
                "การให้โหวตกันแล้วรายงานว่าโหวตแตกแค่ไหน "
                "ให้ทั้งคำตอบและความน่าเชื่อถือของคำตอบไปพร้อมกัน")

    with tabs[1]:
        for f in res["กรอบทั้งหมด"]:
            t = evidence_table(f)
            if t.empty:
                continue
            st.markdown(f"**{f.name}**")
            st.dataframe(t, use_container_width=True, hide_index=True)
        st.caption("คอลัมน์ \"เทียบตัวเองย้อนหลัง\" คือ z-score 10 ปี — "
                   "บอกว่าค่าปัจจุบันห่างจากค่าปกติของตัวชี้วัดตัวนั้นกี่เท่าของความผันผวน "
                   "จำเป็นเพราะแต่ละตัวหน่วยต่างกันสิ้นเชิง เอามาบวกกันตรง ๆ ไม่ได้")

    with tabs[2]:
        th = res["ฝั่งไทย"]
        if not th.get("ใช้ได้"):
            st.warning(f"อ่านฝั่งไทยไม่ได้ — {th.get('เหตุผล')}")
        else:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("สถานะตลาดไทย", th["สถานะตลาด"])
            k2.metric("SET เทียบเส้น 200 วัน", f"{th['SET เทียบเส้น 200 วัน']:+.1f}%")
            if th.get("SET 12 เดือน") is not None:
                k3.metric("SET 12 เดือน", f"{th['SET 12 เดือน']:+.1f}%")
            k4.metric("ค่าเงินบาท", th["บาทอ่อนหรือแข็ง"],
                      f"{th['USDTHB 3 เดือน']:+.1f}%"
                      if th.get("USDTHB 3 เดือน") is not None else None,
                      delta_color="off")
            st.caption(f"ข้อมูลถึงวันที่ {th['ณ วันที่']}")
            st.warning(f"**ข้อจำกัด** — {th['ข้อจำกัด']}")

    with tabs[3]:
        _health_panel(res)

    with tabs[4]:
        _knowledge_panel(quad)

    st.divider()

    # ---------------- ชั้น 3 : แล้วต้องทำอะไร ----------------
    st.markdown("### แล้วควรจัดพอร์ตอย่างไร")

    saved = AL.load_portfolio()
    with st.expander("📝 กรอกพอร์ตปัจจุบันของคุณ (กรอกครั้งเดียว ระบบจำไว้ให้)",
                     expanded=not saved["น้ำหนัก"]):
        st.caption("กรอกเป็น % ของพอร์ตทั้งหมด ให้รวมกันได้ 100 — "
                   "ระบบเก็บเฉพาะสัดส่วน ไม่เก็บจำนวนเงิน")
        cols = st.columns(3)
        vals: dict[str, float] = {}
        for k, (b, hint) in enumerate(AL.BUCKETS):
            vals[b] = cols[k % 3].number_input(
                b, min_value=0.0, max_value=100.0, step=1.0,
                value=float(saved["น้ำหนัก"].get(b, 0.0)),
                key=f"pf_{b}", help=hint)
        total = sum(vals.values())
        st.markdown(f"รวม **{total:.1f}%**"
                    + ("" if abs(total - 100) < 1 else " :red[— ยังไม่ครบ 100%]"))
        b1, b2 = st.columns([1, 1])
        if b1.button("💾 บันทึกพอร์ต", use_container_width=True):
            AL.save_portfolio(vals)
            st.success("บันทึกแล้ว")
            st.rerun()
        if b2.button("✅ ปรับพอร์ตตามนี้แล้ว", use_container_width=True,
                     help="กดเมื่อคุณปรับพอร์ตจริงเสร็จแล้ว "
                          "ระบบจะเตือนไม่ให้ปรับซ้ำเร็วเกินไป"):
            AL.save_portfolio(vals, mark_rebalanced=True)
            st.success("บันทึกแล้ว และจะเตือนไม่ให้ปรับซ้ำภายใน 30 วัน")
            st.rerun()

    pl = AL.plan(quad, v["คะแนนเห็นพ้อง"], saved["น้ำหนัก"])
    st.dataframe(pl["ตาราง"], use_container_width=True, hide_index=True)

    for w in pl["คำเตือน"]:
        st.warning(w)
    if not pl["มีพอร์ต"]:
        st.info("ยังไม่ได้กรอกพอร์ต — ตารางจึงแสดงเฉพาะน้ำหนักเป้าหมาย "
                "กรอกพอร์ตด้านบนแล้วระบบจะคำนวณส่วนต่างและบอกว่าต้องปรับอะไรบ้าง")

    s1, s2 = st.columns(2)
    s1.success("**กลุ่มที่มักนำในช่วงนี้**  \n" + " · ".join(pl["กลุ่มที่เน้น"]))
    s2.warning("**กลุ่มที่มักตามหลังในช่วงนี้**  \n" + " · ".join(pl["กลุ่มที่เลี่ยง"]))

    st.caption(f"⚠️ ที่มาของน้ำหนัก — {pl['ที่มาของน้ำหนัก']}")

    with st.expander("ดูน้ำหนักเป้าหมายของทั้ง 4 ช่วง"):
        st.dataframe(AL.theory_table(), use_container_width=True, hide_index=True)

    st.divider()

    # ---------------- ปุ่มรายงาน PDF ----------------
    p1, p2 = st.columns([1, 3])
    with p1:
        if st.button("📄 สร้างรายงาน PDF", use_container_width=True,
                     help="สรุปภาวะวัฏจักรเศรษฐกิจ ณ เวลานี้เป็นไฟล์เก็บไว้"):
            try:
                with st.spinner("กำลังสร้าง PDF ..."):
                    pdf = make_pdf(res, pl, clock_png)
                st.session_state["cycle_pdf"] = (
                    pdf, f"วัฏจักรเศรษฐกิจ_{datetime.now():%Y%m%d}.pdf")
            except (OSError, ImportError) as e:
                # ข้อความดิบของ WeasyPrint ยาวและอ่านไม่รู้เรื่องสำหรับคนทั่วไป
                # จึงแปลเป็นวิธีแก้ที่ทำตามได้จริง แล้วซ่อนข้อความดิบไว้ให้ดูได้
                msg = str(e)
                if any(k in msg for k in ("libgobject", "cannot load library",
                                          "pango", "cairo", "libffi")):
                    st.error(weasyprint_help_html())
                    with st.expander("ดูข้อความผิดพลาดต้นฉบับ"):
                        st.code(msg)
                else:
                    st.error(f"สร้าง PDF ไม่สำเร็จ: {type(e).__name__}: {e}")
            except Exception as e:                            # noqa: BLE001
                st.error(f"สร้าง PDF ไม่สำเร็จ: {type(e).__name__}: {e}")
    with p2:
        if "cycle_pdf" in st.session_state:
            pdf, fn = st.session_state["cycle_pdf"]
            st.download_button(f"⬇️ ดาวน์โหลด {fn}", pdf, fn,
                               mime="application/pdf", use_container_width=True)

    st.caption("⚠️ ไม่ใช่คำแนะนำการลงทุน — เครื่องมือคำนวณเพื่อการศึกษา · "
               "วัฏจักรเศรษฐกิจรู้แน่ชัดได้เฉพาะตอนมองย้อนหลัง "
               "หน้านี้เป็นการประมาณแบบเรียลไทม์ซึ่งจะมีการอ่านผิดบ้าง")


def _knowledge_panel(quad: str) -> None:
    """
    แท็บความรู้ — ตารางสรุปทั้ง 4 ช่วงและรายละเอียดรายช่วง

    วางลำดับตามที่วัฏจักรเดินจริง ไม่ใช่ตามตำแหน่งบนกราฟ
    เพราะคำถามที่คนอ่านหน้านี้อยากรู้คือ "ตอนนี้อยู่ตรงไหน แล้วถัดไปคืออะไร"
    """
    import cycle_knowledge as CK

    st.markdown("#### วัฏจักรเดินตามลำดับนี้")
    cols = st.columns(4)
    for c, (q, k) in zip(cols, CK.ordered()):
        here = q == quad
        with c:
            st.markdown(
                f"<div style='border-radius:10px;padding:12px 14px;"
                f"background:{QUAD_SOFT[q]};"
                f"border:{'2px solid ' + QUAD_COLOR[q] if here else '1px solid #8883'};'>"
                f"<div style='font-size:.72rem;opacity:.65;'>ช่วงที่ {k['ลำดับ']}"
                f"{' · ตอนนี้อยู่ตรงนี้' if here else ''}</div>"
                f"<div style='font-size:1.15rem;font-weight:700;"
                f"color:{QUAD_COLOR[q]};'>{q}</div>"
                f"<div style='font-size:.72rem;opacity:.6;'>{k['อังกฤษ']}</div>"
                f"<div style='font-size:.78rem;margin-top:6px;'>"
                f"{k['สองบรรทัด'].replace(chr(10), '<br>')}</div>"
                f"<div style='font-size:.76rem;margin-top:8px;"
                f"color:{QUAD_COLOR[q]};'>→ {CK.top_assets(q)}</div>"
                f"</div>", unsafe_allow_html=True)

    nxt = CK.KNOWLEDGE[quad]["ช่วงถัดไป"]
    st.info(f"**ตอนนี้อยู่ช่วง {quad}** ตามลำดับของวัฏจักร ช่วงถัดไปมักเป็น "
            f"**{nxt}** — แต่วัฏจักรจริงข้ามช่วงหรือถอยกลับได้ "
            f"จึงควรใช้เป็นแผนที่ ไม่ใช่ตารางเดินรถ")

    st.markdown("#### เปรียบเทียบทั้ง 4 ช่วง")
    st.dataframe(CK.summary_table(), use_container_width=True, hide_index=True)

    st.markdown("#### สินทรัพย์ไหนดีในช่วงไหน")
    st.caption("อ่านตามแถวเพื่อตอบว่า \"ทองคำควรถือมากตอนไหน\" "
               "อ่านตามคอลัมน์เพื่อตอบว่า \"ช่วงนี้ควรถืออะไร\"")
    mat = CK.asset_matrix()
    st.dataframe(
        mat.style.map(lambda v: f"color:{QUAD_COLOR[quad]};font-weight:700"
                      if v in (CK.BEST,) else "", subset=[quad]),
        use_container_width=True, hide_index=True)
    st.caption(CK.LEGEND)

    st.markdown("#### รายละเอียดแต่ละช่วง")
    for q, k in CK.ordered():
        with st.expander(f"ช่วงที่ {k['ลำดับ']} · {q} ({k['อังกฤษ']})"
                         + ("  ← ตอนนี้อยู่ตรงนี้" if q == quad else ""),
                         expanded=(q == quad)):
            st.markdown(f"**{k['หัวใจ']}**")

            a, b = st.columns([1, 1])
            with a:
                st.markdown("**ลักษณะเศรษฐกิจในช่วงนี้**")
                for line in k["ลักษณะเศรษฐกิจ"]:
                    st.markdown(f"- {line}")
                st.caption(f"ระยะเวลาในอดีต : {k['ระยะเวลาในอดีต']}")
                st.caption(f"เคยเกิดเมื่อ : {k['ตัวอย่างในประวัติศาสตร์']}")
            with b:
                st.markdown("**ควรลงทุนอะไร**")
                for rating, name, why in k["สินทรัพย์"]:
                    st.markdown(f"**{rating} {name}**  \n:gray[{why}]")

            st.markdown(f"**ค่าเงิน** — {k['ค่าเงิน']}")
            st.markdown(f"**คริปโต** — {k['คริปโต']}")
            st.warning(f"**ควรเลี่ยง** — {' · '.join(k['ควรเลี่ยง'])}")
            st.error(f"**ความเสี่ยงหลักของช่วงนี้** — {k['ความเสี่ยงหลัก']}")

    st.divider()
    st.caption(CK.DISCLAIMER)


def _stamp(res: dict) -> str:
    """บรรทัดบอกที่มาและความสดของข้อมูล"""
    t = res.get("เวลาที่ดึงข้อมูล")
    when = "-"
    if t:
        try:
            dt = datetime.fromisoformat(t).astimezone()
            when = dt.strftime("%d/%m/%Y %H:%M น.")
        except Exception:                                     # noqa: BLE001
            when = str(t)
    key = "ใช้ FRED API key" if res.get("มี_fred_key") else "ใช้ FRED แบบไม่ต้องมี key"
    cache = " · จากแคช" if res.get("จากแคช") else ""
    dead = res.get("ข้อมูลที่ตัดออก") or []
    dtxt = f" · ตัดข้อมูลที่ใช้ไม่ได้ออก {len(dead)} ชุด" if dead else ""
    return f"ข้อมูลดึงเมื่อ {when} · {key}{cache}{dtxt}"


def _health_panel(res: dict) -> None:
    """ตารางสุขภาพข้อมูล — ตัวไหนสด ตัวไหนตาย และถูกตัดออกเพราะอะไร"""
    st.markdown("**ข้อมูลทุกชุดที่ระบบดึงมา และสถานะของมัน**")
    st.caption("FRED เลิกอัปเดตชุดข้อมูลเงียบ ๆ ได้ (เคยเกิดกับ USSLIND "
               "ที่หยุดตั้งแต่ ก.พ. 2020 แต่หน้าเว็บยังโหลดได้ปกติ) "
               "ระบบจึงตรวจอายุข้อมูลทุกครั้งและตัดตัวที่ค้างออกจากการโหวต "
               "แทนที่จะใช้ค่าเก่าเงียบ ๆ")
    h = res.get("สุขภาพข้อมูล")
    if isinstance(h, pd.DataFrame) and not h.empty:
        bad = h[~h["ใช้ได้"]] if "ใช้ได้" in h.columns else pd.DataFrame()
        if not bad.empty:
            st.error(f"ตัดออกจากการโหวต {len(bad)} ชุด")
        st.dataframe(h.drop(columns=[c for c in ["ใช้ได้"] if c in h.columns]),
                     use_container_width=True, hide_index=True)
    else:
        st.info("ยังไม่มีรายงานสุขภาพข้อมูล")
