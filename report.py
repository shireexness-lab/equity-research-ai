"""
report.py — Part 15 : Report Generator
=======================================
หน้าที่ : ประกอบทุกอย่างเป็นรายงาน PDF ภาษาไทย พร้อมกราฟ

แนวทางที่เลือกและเหตุผล
------------------------
matplotlib → รูป PNG → ฝังใน HTML → WeasyPrint → PDF

ทำไมไม่ใช้ไลบรารีสร้าง PDF ตรง ๆ (เช่น reportlab)
  • HTML/CSS จัดหน้าง่ายกว่ามาก และแก้ดีไซน์ได้โดยไม่ต้องแก้โค้ด Python
  • รองรับฟอนต์ไทยดีกว่า (สระบน-ล่างวางตำแหน่งถูก)
  • ถ้าอนาคตอยากทำเป็นหน้าเว็บ ใช้ HTML เดิมได้เลย

สิ่งที่ต้องมีก่อนใช้ : ฟอนต์ไทย
--------------------------------
ดาวน์โหลดครั้งเดียว (ฟรี จาก Google Fonts) ด้วยคำสั่งใน Terminal :

    mkdir -p fonts
    curl -L -o fonts/Sarabun-Regular.ttf \\
      https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Regular.ttf
    curl -L -o fonts/Sarabun-Bold.ttf \\
      https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Bold.ttf

ถ้าไม่มีฟอนต์ ตัวอักษรไทยใน PDF จะกลายเป็นสี่เหลี่ยม ⬛⬛⬛

วิธีใช้จาก Terminal
-------------------
    python3 report.py AAPL
    python3 report.py PTT.BK --rf 0.025
    python3 report.py AAPL --open        # สร้างเสร็จแล้วเปิดดูเลย
"""

import argparse
import base64
import io
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")          # ไม่ต้องเปิดหน้าต่าง (สำคัญตอน deploy ขึ้นเว็บ)
import matplotlib.pyplot as plt
from matplotlib import font_manager

from bands import build as build_bands
from data_layer import get_stock_data
from ratios import compute_ratios
from statements import analyze
from valuation import value_stock

BASE_DIR = Path(__file__).resolve().parent
FONT_DIR = BASE_DIR / "fonts"
OUT_DIR = BASE_DIR / "output"

# สีประจำรายงาน
C_MAIN = "#1f4e79"      # น้ำเงินเข้ม
C_ACCENT = "#c55a11"    # ส้ม
C_GOOD = "#2e7d32"      # เขียว
C_BAD = "#c62828"       # แดง
C_GREY = "#8a8a8a"


# ---------------------------------------------------------------------------
# ฟอนต์ไทย
# ---------------------------------------------------------------------------

def ensure_font() -> Path:
    """ตรวจว่ามีฟอนต์ไทยไหม ถ้าไม่มีบอกวิธีโหลดให้ชัดเจน"""
    reg = FONT_DIR / "Sarabun-Regular.ttf"
    if reg.exists():
        return reg
    raise FileNotFoundError(
        "ไม่พบฟอนต์ไทย — ถ้าไม่มี ตัวอักษรไทยใน PDF จะกลายเป็นสี่เหลี่ยม\n\n"
        "  แก้โดยพิมพ์ 3 บรรทัดนี้ใน Terminal (ทำครั้งเดียวพอ):\n\n"
        "    mkdir -p fonts\n"
        "    curl -L -o fonts/Sarabun-Regular.ttf "
        "https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Regular.ttf\n"
        "    curl -L -o fonts/Sarabun-Bold.ttf "
        "https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Bold.ttf\n"
    )


def setup_matplotlib_font():
    """บอก matplotlib ให้ใช้ฟอนต์ไทย ไม่งั้นชื่อแกนกราฟจะเป็นสี่เหลี่ยม"""
    reg = ensure_font()
    font_manager.fontManager.addfont(str(reg))
    bold = FONT_DIR / "Sarabun-Bold.ttf"
    if bold.exists():
        font_manager.fontManager.addfont(str(bold))
    # อ่านชื่อวงศ์ฟอนต์จากไฟล์จริง ไม่เดาว่าชื่อ "Sarabun"
    # (ถ้าเดาแล้วชื่อไม่ตรง matplotlib จะถอยไปใช้ฟอนต์อังกฤษเงียบ ๆ
    #  ผลคือชื่อแกนกราฟภาษาไทยกลายเป็นสี่เหลี่ยมโดยไม่มีข้อความเตือนชัดเจน)
    family = font_manager.FontProperties(fname=str(reg)).get_name()
    plt.rcParams["font.family"] = family
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 120


# ---------------------------------------------------------------------------
# ตัวช่วยสร้างกราฟ
# ---------------------------------------------------------------------------

# สีของ "ตัวกราฟ" (เส้น/แท่ง) ใช้ชุดเดียวกันทั้งสองธีม
# เปลี่ยนเฉพาะสีตัวหนังสือและเส้นตาราง เพื่อให้อ่านได้ทั้งพื้นขาวและพื้นดำ
_TXT = "#2b3440"
_GRID = "#d8dee6"
_TITLE = C_MAIN


# ---------------------------------------------------------------------------
# ชุดสี
#
# เลือกโดยยึด 2 ข้อ
#   1. อ่านได้ทั้งพื้นขาวและพื้นดำ — ค่าความสว่างของสีคู่กันต้องต่างจากพื้นพอ
#   2. **แยกกันได้แม้ตาบอดสี** ราว 8% ของผู้ชายแยกแดง-เขียวไม่ชัด
#      จึงเลี่ยงคู่แดง-เขียวเป็นตัวสื่อความหมายหลัก ใช้น้ำเงิน-ส้มเป็นคู่หลักแทน
#      (น้ำเงิน-ส้มเป็นคู่ที่คนตาบอดสีทุกแบบแยกออก)
# ---------------------------------------------------------------------------
_LIGHT = {"main": "#2563a8", "accent": "#e07b39", "good": "#2e8b57",
          "bad": "#c1442e", "grey": "#9aa5b1", "txt": "#2b3440",
          "grid": "#d8dee6", "fill": "#2563a8"}
_DARK = {"main": "#63a4e8", "accent": "#f5a05a", "good": "#5cc98a",
         "bad": "#e8705f", "grey": "#7d8896", "txt": "#dfe6ee",
         "grid": "#2f3846", "fill": "#63a4e8"}

# สัดส่วนกราฟ — กว้าง 7.6 นิ้ว สูง 3.1 นิ้ว = อัตราส่วนราว 2.45:1
#
# ทำไมขนาดนี้ : หน้าเว็บกว้างสุด 1900px ถ้ากราฟสูงเกินไปจะเลื่อนดูทีละกราฟ
# ถ้าเตี้ยเกินไปเส้นจะเบียดกันจนอ่านแนวโน้มไม่ออก
# 2.45:1 ใกล้เคียงอัตราส่วนที่ตาคนอ่านกราฟเส้นได้สบายที่สุด
FIG_W, FIG_H = 7.6, 3.1


def set_chart_theme(dark: bool = False):
    """
    สลับชุดสีของกราฟให้เข้ากับธีมสว่าง/มืด

    เคล็ดลับสำคัญ : พื้นหลังกราฟตั้งเป็น **โปร่งใส** เสมอ
    จึงกลมกลืนกับพื้นหลังของหน้าเว็บหรือ PDF โดยอัตโนมัติ
    เหลือแค่สีเส้น/แท่ง/ตัวหนังสือที่ต้องสลับ

    ทำไมต้องสลับสีเส้นด้วย ไม่ใช่แค่ตัวหนังสือ :
    น้ำเงินเข้ม #1f4e79 บนพื้นดำแทบมองไม่เห็น จึงต้องใช้น้ำเงินสว่างแทน
    """
    global C_MAIN, C_ACCENT, C_GOOD, C_BAD, C_GREY, _TXT, _TITLE, _GRID
    p = _DARK if dark else _LIGHT
    C_MAIN, C_ACCENT, C_GOOD = p["main"], p["accent"], p["good"]
    C_BAD, C_GREY, _TXT = p["bad"], p["grey"], p["txt"]
    _GRID = p["grid"]
    _TITLE = C_MAIN
    for k in ("text.color", "axes.labelcolor", "xtick.color", "ytick.color"):
        plt.rcParams[k] = _TXT

    # ---- รูปลักษณ์รวมของกราฟ ----
    # เอากรอบบนและขวาออก เหลือเฉพาะแกนที่จำเป็น
    # กรอบสี่ด้านเป็นหมึกที่ไม่ได้สื่อข้อมูลอะไร แต่แย่งความสนใจจากเส้นข้อมูล
    plt.rcParams.update({
        "axes.edgecolor": _GRID,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",           # เส้นตารางแนวนอนพอ แนวตั้งรก
        "grid.color": _GRID,
        "grid.linewidth": 0.6,
        "grid.alpha": 0.55,
        "axes.axisbelow": True,          # เส้นตารางอยู่ใต้ข้อมูลเสมอ
        "font.size": 9.5,
        "axes.titlesize": 11.5,
        "axes.titleweight": "bold",
        "axes.titlepad": 10,
        "axes.labelsize": 9.5,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "xtick.major.size": 0,           # ขีดบอกสเกลไม่จำเป็นเมื่อมีเส้นตาราง
        "ytick.major.size": 0,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "lines.linewidth": 2.2,
        "lines.markersize": 5,
        "lines.solid_capstyle": "round",
        "figure.dpi": 130,
        "savefig.dpi": 130,
    })


def _fig_b64(fig) -> str:
    """แปลงกราฟเป็นข้อความ base64 เพื่อฝังลง HTML โดยตรง (ไม่ต้องมีไฟล์แยก)"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", transparent=True)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _style(ax, title="", ylabel=""):
    """
    จัดรูปลักษณ์กราฟให้เหมือนกันทุกใบ

    หลักที่ใช้ : ลบทุกอย่างที่ไม่ได้สื่อข้อมูล
    กรอบบน-ขวา ขีดสเกล และเส้นตารางแนวตั้ง ไม่ได้ช่วยให้อ่านค่าง่ายขึ้น
    แต่แย่งความสนใจจากเส้นข้อมูลซึ่งเป็นสิ่งที่เราอยากให้ดู
    """
    ax.set_title(title, fontsize=11.5, color=_TITLE, pad=10, fontweight="bold")
    ax.set_ylabel(ylabel, fontsize=9.5, color=_TXT)
    ax.grid(axis="y", alpha=0.55, linewidth=0.6, color=_GRID)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(_GRID)
    ax.spines[["left", "bottom"]].set_linewidth(0.8)
    ax.tick_params(labelsize=9, colors=_TXT, length=0)
    # เว้นขอบบนไว้เล็กน้อย ไม่ให้เส้นหรือแท่งชนขอบกราฟ
    ax.margins(x=0.02, y=0.12)


def chart_revenue_profit(R):
    yrs = [y[:4] for y in R["years"]]
    rev = R["raw"]["revenue"] / 1e9
    ni = R["raw"]["net_income"] / 1e9
    if not (rev.notna().any() or ni.notna().any()):
        return None
    # ใช้แท่งคู่เคียงกัน ไม่ใช่แท่งซ้อนทับ
    # เหตุผล : แท่งซ้อนทับทำให้คนอ่านเข้าใจผิดว่า "รายได้ + กำไร" ต้องบวกกัน
    #          ทั้งที่กำไรเป็นส่วนหนึ่งของรายได้อยู่แล้ว
    x = np.arange(len(yrs))
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.bar(x - 0.19, rev, width=0.36, color=C_MAIN, label="รายได้รวม",
           zorder=3)
    ax.bar(x + 0.19, ni, width=0.36, color=C_ACCENT, label="กำไรสุทธิ",
           zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(yrs, rotation=45 if len(yrs) > 8 else 0)
    _style(ax, "รายได้และกำไรสุทธิ", "พันล้าน")
    ax.legend(fontsize=9, frameon=False, ncol=3,
              loc="upper left", bbox_to_anchor=(0, 1.02))
    return _fig_b64(fig)


def _line_chart(R, series, title, ylabel="%"):
    """
    วาดกราฟเส้นหลายเส้น โดย **ข้ามเส้นที่ไม่มีข้อมูลเลย**

    ทำไมสำคัญ : ธนาคารไม่มี Gross Profit / Operating Income
    ถ้าวาดเส้นว่างเปล่า จะได้กราฟเปล่า ๆ ที่แกน Y เป็น -0.04 ถึง 0.04
    ซึ่งดูเหมือนระบบพัง ทั้งที่ความจริงคือ "บริษัทประเภทนี้ไม่มีรายการนั้น"
    """
    t, yrs = R["table"], [y[:4] for y in R["years"]]
    plotted = 0
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    for name, color in series:
        if name not in t.index:
            continue
        vals = pd.to_numeric(t.loc[name], errors="coerce")
        if not vals.notna().any():        # ทั้งแถวเป็นค่าว่าง → ข้าม
            continue
        ax.plot(yrs, vals.values, marker="o", ms=3, lw=1.6, color=color, label=name)
        plotted += 1
    if plotted == 0:
        plt.close(fig)
        return None                        # ไม่มีอะไรให้วาด
    _style(ax, title, ylabel)
    ax.legend(fontsize=9, frameon=False, ncol=3,
              loc="upper left", bbox_to_anchor=(0, 1.02))
    plt.xticks(rotation=45 if len(yrs) > 8 else 0)
    return _fig_b64(fig)


def chart_margins(R):
    return _line_chart(R, [("Gross Margin", C_MAIN), ("Operating Margin", C_ACCENT),
                           ("Net Margin", C_GOOD)], "อัตรากำไร (%)")


def chart_returns(R):
    return _line_chart(R, [("ROE", C_MAIN), ("ROIC", C_ACCENT), ("ROA", C_GREY)],
                       "ผลตอบแทนต่อเงินทุน (%)")


def chart_cashflow(R):
    yrs = [y[:4] for y in R["years"]]
    raw = R["raw"]
    if not (raw["ocf"].notna().any() or raw["fcf"].notna().any()):
        return None
    x = np.arange(len(yrs))
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.bar(x - 0.19, raw["ocf"] / 1e9, width=0.36, color=C_MAIN, label="OCF",
           zorder=3)
    ax.bar(x + 0.19, raw["fcf"] / 1e9, width=0.36, color=C_GOOD, label="FCF",
           zorder=3)
    ax.plot(x, raw["capex"] / 1e9, color=C_ACCENT, lw=2.0, marker="o", ms=5,
            label="CapEx", zorder=4)
    ax.set_xticks(x)
    ax.set_xticklabels(yrs, rotation=45 if len(yrs) > 8 else 0)
    _style(ax, "กระแสเงินสด", "พันล้าน")
    ax.legend(fontsize=9, frameon=False, ncol=3,
              loc="upper left", bbox_to_anchor=(0, 1.02))
    return _fig_b64(fig)


def chart_price_bands(data, b):
    prices = data.get("prices")
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H + 0.25))
    if isinstance(prices, pd.DataFrame) and not prices.empty and "Close" in prices:
        px = prices["Close"].dropna().tail(1800)   # ~7 ปีล่าสุด
        ax.plot(px.index, px.values, lw=1.6, color=C_MAIN, label="ราคาปิด",
                zorder=3)
    colors = {"Strong Buy": C_GOOD, "Buy": "#7cb342", "Hold": C_GREY,
              "Reduce": "#ef6c00", "Sell": C_BAD}
    for name, (lo, hi) in b["bands"].items():
        if hi != float("inf"):
            ax.axhline(hi, color=colors.get(name, C_GREY), ls="--", lw=1.0, alpha=0.85)
            ax.text(1.005, hi, f" {name}", transform=ax.get_yaxis_transform(),
                    fontsize=7, color=colors.get(name, C_GREY), va="center")
    ax.axhline(b["มูลค่าที่ประเมินได้"], color=_TXT, lw=1.4,
               label="มูลค่าที่ประเมินได้")
    _style(ax, "ราคาย้อนหลังเทียบช่วงราคาที่คำนวณได้", b["สกุลเงิน"])
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    return _fig_b64(fig)


def chart_methods(v):
    items = [(k, x) for k, x in v["methods"].items()
             if x is not None and np.isfinite(x) and x > 0 and "ไม่นับ" not in k]
    if not items:
        return None
    names = [k for k, _ in items][::-1]
    vals = [x for _, x in items][::-1]
    fig, ax = plt.subplots(figsize=(FIG_W, max(2.2, 0.46 * len(names) + 1.3)))
    ax.barh(names, vals, color=C_MAIN, alpha=0.85)
    price = v["ราคาปัจจุบัน"]
    if price:
        ax.axvline(price, color=C_BAD, lw=1.6, label=f"ราคาตลาด {price:,.2f}")
        ax.legend(fontsize=9, frameon=False, ncol=3,
              loc="upper left", bbox_to_anchor=(0, 1.02))
    for i, val in enumerate(vals):
        ax.text(val, i, f" {val:,.0f}", va="center", fontsize=8, color=_TXT)
    _style(ax, "มูลค่าต่อหุ้นจากแต่ละวิธี", "")
    ax.grid(axis="x", alpha=0.25, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    return _fig_b64(fig)


def chart_pe_history(v):
    h = v.get("historical")
    if not h or not isinstance(h.get("ตาราง"), pd.DataFrame) or h["ตาราง"].empty:
        return None
    t = h["ตาราง"]
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H - 0.2))
    ax.bar(t.index, t["P/E"], color=C_MAIN, alpha=0.8)
    ax.axhline(h["P/E ค่ากลาง"], color=C_ACCENT, ls="--", lw=1.3,
               label=f"ค่ากลางทั้งช่วง {h['P/E ค่ากลาง']:.1f}x")
    ax.axhline(h["P/E ค่ากลาง 5 ปีล่าสุด"], color=C_GOOD, ls="--", lw=1.3,
               label=f"ค่ากลาง 5 ปีล่าสุด {h['P/E ค่ากลาง 5 ปีล่าสุด']:.1f}x")
    _style(ax, "P/E ย้อนหลังรายปี", "เท่า")
    ax.legend(fontsize=9, frameon=False, ncol=3,
              loc="upper left", bbox_to_anchor=(0, 1.02))
    plt.xticks(rotation=45 if len(t) > 8 else 0)
    return _fig_b64(fig)


# ---------------------------------------------------------------------------
# ตัวช่วยสร้าง HTML
# ---------------------------------------------------------------------------

def esc(x):
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt(x, dec=2, dash="—"):
    if x is None or (isinstance(x, float) and not np.isfinite(x)) or pd.isna(x):
        return dash
    return f"{x:,.{dec}f}"


def table_html(df: pd.DataFrame, units=None, first_col="รายการ", dec=2) -> str:
    """แปลง DataFrame เป็นตาราง HTML"""
    cols = [str(c)[:4] for c in df.columns]
    h = ["<table><thead><tr><th class='lbl'>" + esc(first_col) + "</th>"]
    h += [f"<th>{esc(c)}</th>" for c in cols]
    h.append("</tr></thead><tbody>")
    for name in df.index:
        u = (units or {}).get(name, "")
        h.append(f"<tr><td class='lbl'>{esc(name)}</td>")
        for c in df.columns:
            val = df.loc[name, c]
            if pd.isna(val):
                cell = "—"
            elif u == "%":
                cell = f"{val:,.1f}%"
            elif u in ("วัน", "ล้าน"):
                cell = f"{val:,.0f}"
            else:
                cell = f"{val:,.{dec}f}"
            h.append(f"<td>{cell}</td>")
        h.append("</tr>")
    h.append("</tbody></table>")
    return "".join(h)


def kv_html(pairs) -> str:
    rows = "".join(
        f"<tr><td class='lbl'>{esc(k)}</td><td class='num'>{esc(v)}</td></tr>"
        for k, v in pairs)
    return f"<table class='kv'>{rows}</table>"


def img(b64, caption="") -> str:
    if not b64:
        return ""
    cap = f"<div class='cap'>{esc(caption)}</div>" if caption else ""
    return f"<figure><img src='data:image/png;base64,{b64}'/>{cap}</figure>"


CSS = """
@font-face { font-family:'Sarabun'; src:url('FONT_REG') format('truetype');
             font-weight:400; }
@font-face { font-family:'Sarabun'; src:url('FONT_BOLD') format('truetype');
             font-weight:700; }
@page { size:A4; margin:15mm 13mm 16mm 13mm;
  @bottom-center { content:"หน้า " counter(page) " / " counter(pages);
                   font-family:'Sarabun'; font-size:8pt; color:#8a8a8a; }
  @bottom-right { content:"เอกสารเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน";
                  font-family:'Sarabun'; font-size:7pt; color:#b0b0b0; } }
body { font-family:'Sarabun'; font-size:9.5pt; color:#222; line-height:1.5; }
h1 { font-size:22pt; color:#1f4e79; margin:0 0 2mm 0; }
h2 { font-size:13pt; color:#1f4e79; margin:7mm 0 2mm 0;
     border-bottom:1.5pt solid #1f4e79; padding-bottom:1mm; }
h3 { font-size:10.5pt; color:#c55a11; margin:4mm 0 1.5mm 0; }
.sub { color:#666; font-size:9pt; }
.cover { text-align:center; padding-top:45mm; }
.cover h1 { font-size:30pt; }
.cover .tick { font-size:44pt; font-weight:700; color:#c55a11; letter-spacing:2pt; }
.badge { display:inline-block; padding:2mm 6mm; border-radius:3mm;
         font-size:15pt; font-weight:700; color:#fff; margin:3mm 0; }
.big { font-size:15pt; font-weight:700; color:#1f4e79; }
table { width:100%; border-collapse:collapse; margin:2mm 0 3mm 0; font-size:8pt; }
th { background:#1f4e79; color:#fff; padding:1.4mm 1.6mm; text-align:right;
     font-weight:400; }
th.lbl, td.lbl { text-align:left; }
td { padding:1.2mm 1.6mm; text-align:right; border-bottom:0.4pt solid #e3e3e3; }
tbody tr:nth-child(even) { background:#f7f9fb; }
table.kv td { border:none; padding:1mm 2mm; }
table.kv td.lbl { color:#555; width:55%; }
table.kv td.num { font-weight:700; color:#1f4e79; }
figure { margin:2mm 0 4mm 0; text-align:center; }
img { width:100%; }
.cap { font-size:7.5pt; color:#888; margin-top:1mm; }
.note { background:#fff8e1; border-left:2.5pt solid #c55a11;
        padding:2mm 3mm; margin:2mm 0; font-size:8.5pt; }
.warn { background:#fdecea; border-left:2.5pt solid #c62828;
        padding:2mm 3mm; margin:2mm 0; font-size:8.5pt; }
.ok { background:#edf7ed; border-left:2.5pt solid #2e7d32;
      padding:2mm 3mm; margin:2mm 0; font-size:8.5pt; }
/* กล่องเน้นคำแนะนำสรุป */
.box { background:#f7f9fc; padding:3mm 4mm; margin:2mm 0 3mm 0;
       border-radius:1mm; }
/* ตารางข้อมูลหลายคอลัมน์ (พยากรณ์ · ข่าว) */
table.data { width:100%; border-collapse:collapse; font-size:8pt;
             margin:2mm 0 3mm 0; }
table.data th { background:#eef2f7; color:#1f4e79; font-weight:700;
                padding:1.2mm 2mm; text-align:left;
                border-bottom:0.6pt solid #ccd5e0; }
table.data td { padding:1mm 2mm; border-bottom:0.4pt solid #e7ecf2; }
table.data td.num { text-align:right; }
.pagebreak { page-break-after:always; }
.two { display:flex; gap:6mm; }
.two > div { flex:1; }
ul { margin:1mm 0 2mm 4mm; padding:0; }
li { margin:0.6mm 0; }
"""

ZONE_COLOR = {"Strong Buy": "#1b5e20", "Buy": "#2e7d32", "Hold": "#757575",
              "Reduce": "#ef6c00", "Sell": "#c62828"}


# ---------------------------------------------------------------------------
# ประกอบรายงาน
# ---------------------------------------------------------------------------

def build_html(data, S, R, v, b, ext=None) -> str:
    info = data.get("info", {})
    cur = v["สกุลเงิน"]
    price = v["ราคาปัจจุบัน"]
    fair = b["มูลค่าที่ประเมินได้"]
    zone = b["โซนปัจจุบัน"]
    rel = b["ความน่าเชื่อถือ"]
    today = datetime.now().strftime("%d/%m/%Y %H:%M")
    name = info.get("longName") or info.get("shortName") or v["ticker"]

    # ---------- ปก ----------
    parts = [f"""
<div class='cover'>
  <div class='sub'>รายงานวิเคราะห์หลักทรัพย์</div>
  <div class='tick'>{esc(v['ticker'])}</div>
  <h1>{esc(name)}</h1>
  <div class='sub'>{esc(info.get('sector','-'))} · {esc(info.get('industry','-'))}
       · {esc(info.get('exchange','-'))}</div>
  <div class='badge' style='background:{ZONE_COLOR.get(zone,"#757575")}'>{esc(zone)}</div>
  <div class='big'>ราคาตลาด {fmt(price)} {esc(cur)} ·
       มูลค่าที่ประเมินได้ {fmt(fair)} {esc(cur)}</div>
  <div class='sub' style='margin-top:3mm'>
       ส่วนต่าง {fmt((fair/price-1)*100,1)}% ·
       ความน่าเชื่อถือ {esc(rel['ระดับ'])} ({rel['คะแนน']}/100)</div>
  <div class='sub' style='margin-top:14mm'>
       ข้อมูล {v['ปีข้อมูล']} ปี จาก {esc(v['แหล่งงบ'])}<br/>
       สร้างเมื่อ {esc(today)}</div>
  <div class='note' style='margin-top:14mm;text-align:left'>
    เอกสารนี้สร้างโดยระบบอัตโนมัติเพื่อการศึกษาส่วนบุคคล
    <b>ไม่ใช่คำแนะนำการลงทุน</b> ตัวเลขทั้งหมดคำนวณจากงบการเงินที่เผยแพร่ต่อสาธารณะ
    ด้วยสูตรและสมมติฐานที่ระบุไว้ในเอกสาร ผู้อ่านควรตรวจสอบด้วยตนเองก่อนตัดสินใจใด ๆ
  </div>
</div>
<div class='pagebreak'></div>
"""]

    # ---------- สรุปผู้บริหาร ----------
    sm = R["summary"]
    parts.append("<h2>1. สรุปผู้บริหาร</h2>")
    parts.append("<div class='two'><div>")
    parts.append(kv_html([
        ("ราคาตลาด", f"{fmt(price)} {cur}"),
        ("มูลค่าที่ประเมินได้", f"{fmt(fair)} {cur}"),
        ("ส่วนต่าง", f"{fmt((fair/price-1)*100,1)}%"),
        ("โซนราคา", zone),
        ("ส่วนเผื่อความปลอดภัย", f"{b['mos ที่ใช้']:.0%}"),
        ("ราคาที่เข้าโซน Buy", f"{fmt(b['ราคาที่เข้าโซน Buy'])} {cur}"),
    ]))
    parts.append("</div><div>")
    parts.append(kv_html([
        ("จำนวนปีข้อมูล", f"{sm['จำนวนปีข้อมูล']} ปี"),
        ("CAGR รายได้", f"{fmt(sm['CAGR รายได้ (%)'],1)}%"),
        ("CAGR กำไรสุทธิ", f"{fmt(sm['CAGR กำไรสุทธิ (%)'],1)}%"),
        ("CAGR FCF", f"{fmt(sm['CAGR FCF (%)'],1)}%"),
        ("ROE เฉลี่ย", f"{fmt(sm['ROE เฉลี่ย (%)'],1)}%"),
        ("ROIC เฉลี่ย", f"{fmt(sm['ROIC เฉลี่ย (%)'],1)}%"),
    ]))
    parts.append("</div></div>")

    ig = v.get("อัตราโตที่ตลาดคาดหวัง")
    if ig is not None:
        g_hist = sm.get("CAGR FCF (%)")
        parts.append(f"""<div class='note'>
        <b>ราคาวันนี้กำลังบอกอะไร (Reverse DCF)</b><br/>
        ที่ราคา {fmt(price)} {esc(cur)} ตลาดคาดว่ากระแสเงินสดอิสระจะโตปีละ
        <b>{ig:+.1%}</b> ติดต่อกัน {v['years1']} ปี<br/>
        ขณะที่ย้อนหลัง {v['ปีข้อมูล']} ปีที่ผ่านมา บริษัททำได้จริง
        <b>{fmt(g_hist,1)}%</b> ต่อปี<br/>
        คำถามที่ต้องตอบก่อนตัดสินใจ : เชื่อหรือไม่ว่าบริษัทจะทำได้ตามที่ตลาดคาด
        </div>""")

    cls = "warn" if rel["คะแนน"] < 50 else ("note" if rel["คะแนน"] < 75 else "ok")
    warns = "".join(f"<li>{esc(x)}</li>" for x in rel["คำเตือน"]) or "<li>ไม่พบข้อจำกัดสำคัญ</li>"
    parts.append(f"""<div class='{cls}'>
      <b>ความน่าเชื่อถือของการประเมิน : {esc(rel['ระดับ'])} ({rel['คะแนน']}/100)</b>
      <ul>{warns}</ul></div>""")

    # ---------- ผลประกอบการ ----------
    parts.append("<h2>2. ผลประกอบการย้อนหลัง</h2>")
    parts.append(img(chart_revenue_profit(R)))
    parts.append(img(chart_margins(R)))
    parts.append("<h3>งบกำไรขาดทุน (หน่วย: ล้าน)</h3>")
    parts.append(table_html(S["income"] / 1e6, dec=0))
    parts.append("<div class='pagebreak'></div>")

    # ---------- ผลตอบแทนและกระแสเงินสด ----------
    parts.append("<h2>3. ผลตอบแทนต่อเงินทุนและกระแสเงินสด</h2>")
    parts.append(img(chart_returns(R)))
    parts.append(img(chart_cashflow(R)))
    parts.append(f"""<div class='note'>
      <b>คุณภาพกำไร</b> — OCF ÷ กำไรสุทธิ เฉลี่ย
      <b>{fmt(sm['OCF/กำไรสุทธิ เฉลี่ย (x)'])} เท่า</b><br/>
      มากกว่า 1 เท่า = กำไรที่รายงานแปลงเป็นเงินสดจริงได้ครบ (สัญญาณดี)<br/>
      ต่ำกว่า 1 เท่าติดต่อกันหลายปี = กำไรอาจอยู่ในรูปลูกหนี้หรือสินค้าคงเหลือ ต้องระวัง
      </div>""")
    parts.append("<div class='pagebreak'></div>")

    # ---------- อัตราส่วน ----------
    parts.append("<h2>4. อัตราส่วนทางการเงิน</h2>")
    for gname, names in R["groups"].items():
        sub = R["table"].loc[[n for n in names if n in R["table"].index]]
        if sub.empty:
            continue
        parts.append(f"<h3>{esc(gname)}</h3>")
        parts.append(table_html(sub, units=R["units"]))
    parts.append("<div class='pagebreak'></div>")

    # ---------- ประเมินมูลค่า ----------
    parts.append("<h2>5. การประเมินมูลค่า</h2>")
    if v.get("หมายเหตุวิธีประเมิน"):
        li = "".join(f"<li>{esc(n)}</li>" for n in v["หมายเหตุวิธีประเมิน"])
        parts.append(f"<div class='warn'><b>หมายเหตุวิธีประเมิน</b><ul>{li}</ul></div>")
    w = v["wacc_detail"]
    i = v["inputs"]
    parts.append("<div class='two'><div><h3>อัตราคิดลด (WACC)</h3>")
    parts.append(kv_html([
        ("Beta", fmt(w["beta"])),
        ("พันธบัตร (rf)", f"{w['พันธบัตร (rf)']:.2%}"),
        ("ต้นทุนส่วนทุน (CAPM)", f"{w['ต้นทุนส่วนทุน']:.2%}"),
        ("ต้นทุนหนี้", f"{w['ต้นทุนหนี้']:.2%}"),
        ("อัตราภาษี", f"{w['อัตราภาษี']:.2%}"),
        ("น้ำหนัก ทุน / หนี้", f"{w['น้ำหนักส่วนทุน']:.0%} / {w['น้ำหนักหนี้']:.0%}"),
        ("WACC ที่ใช้", f"{v['wacc ที่ใช้']:.2%}"),
    ]))
    parts.append("</div><div><h3>สมมติฐาน DCF</h3>")
    if v.get("ใช้ DCF ได้ไหม"):
        parts.append(kv_html([
            ("FCF ปีฐาน (เฉลี่ย 3 ปี)", f"{i['fcf0 (เฉลี่ย 3 ปี)']/1e6:,.0f} ล้าน"),
            ("อัตราโตช่วงแรก (g1)", f"{v['g1 ที่ใช้']:.2%}"),
            ("อัตราโตถาวร (g2)", f"{v['g2 ที่ใช้']:.2%}"),
            ("จำนวนปีช่วงโตสูง", f"{v['years1']} ปี"),
            ("หนี้สินสุทธิ", f"{i['net_debt']/1e6:,.0f} ล้าน"),
            ("สัดส่วนมูลค่าสุดท้าย", f"{v['base_dcf']['สัดส่วนมูลค่าสุดท้าย']:.0%}"),
        ]))
    else:
        parts.append("<p class='sub'>ไม่ได้ใช้ DCF กับหุ้นตัวนี้ "
                     "(ดูเหตุผลในกล่องหมายเหตุด้านบน)</p>")
    parts.append("</div></div>")

    if v.get("ใช้ DCF ได้ไหม") and v["base_dcf"]["สัดส่วนมูลค่าสุดท้าย"] > 0.75:
        parts.append("""<div class='warn'>มูลค่าเกิน 75% มาจากช่วง
        "ปีที่ 11 เป็นต้นไป" ซึ่งเป็นช่วงที่คาดการณ์ได้ยากที่สุด
        ผลลัพธ์จึงไวต่อสมมติฐานมาก ควรอ่านคู่กับตารางความไวเสมอ</div>""")

    parts.append(img(chart_methods(v)))
    if v.get("sensitivity") is not None:
        parts.append("<h3>ตารางความไว (Sensitivity)</h3>")
        parts.append(table_html(v["sensitivity"], first_col="WACC \\ g1", dec=0))
        parts.append("""<div class='note'>อ่านตารางนี้อย่างไร : ถ้าตัวเลขกระจายกว้างมาก
        แปลว่าอย่าเชื่อ "มูลค่าตัวเดียว" ให้ใช้เป็นช่วงแทน</div>""")

    bv = v.get("book_value")
    if bv:
        parts.append("<h3>มูลค่าตามบัญชี (P/BV)</h3>")
        parts.append(kv_html([
            ("P/BV ค่ากลางทั้งช่วง", f"{fmt(bv['P/BV ค่ากลาง'])} เท่า"),
            ("P/BV ค่ากลาง 5 ปีล่าสุด", f"{fmt(bv['P/BV ค่ากลาง 5 ปีล่าสุด'])} เท่า"),
            ("มูลค่าตามบัญชีต่อหุ้นล่าสุด", f"{fmt(bv['BVPS ล่าสุด'])} {cur}"),
        ]))
    parts.append("<div class='pagebreak'></div>")

    # ---------- Multiple ย้อนหลัง ----------
    h = v.get("historical")
    if h and isinstance(h.get("ตาราง"), pd.DataFrame) and not h["ตาราง"].empty:
        parts.append("<h2>6. อัตราส่วนราคาย้อนหลัง</h2>")
        parts.append(img(chart_pe_history(v)))
        parts.append(table_html(h["ตาราง"].T, first_col="รายการ"))
        parts.append(f"""<div class='note'>
        <b>ทำไมต้องดูสองค่า</b><br/>
        ค่ากลางทั้งช่วง <b>{fmt(h['P/E ค่ากลาง'],1)} เท่า</b> =
        สมมติว่าตลาดจะกลับไปให้ราคาแบบยุคเก่า (อนุรักษ์นิยม)<br/>
        ค่ากลาง 5 ปีล่าสุด <b>{fmt(h['P/E ค่ากลาง 5 ปีล่าสุด'],1)} เท่า</b> =
        สมมติว่ามุมมองปัจจุบันของตลาดจะอยู่ต่อไป<br/>
        ทั้งสองเป็น "มุมมอง" ไม่ใช่ข้อเท็จจริง</div>""")
        parts.append("<div class='pagebreak'></div>")

    # ---------- ช่วงราคา ----------
    parts.append("<h2>7. ช่วงราคาและส่วนเผื่อความปลอดภัย</h2>")
    parts.append(img(chart_price_bands(data, b)))
    rows = []
    for bn, (lo, hi) in b["bands"].items():
        if hi == float("inf"):
            rng = f"มากกว่า {fmt(lo)}"
        elif lo == 0:
            rng = f"ต่ำกว่า {fmt(hi)}"
        else:
            rng = f"{fmt(lo)} – {fmt(hi)}"
        mark = "  ← ราคาปัจจุบัน" if bn == zone else ""
        rows.append((bn, rng + f" {cur}" + mark))
    parts.append(kv_html(rows))
    reasons = "".join(f"<li>{esc(r)}</li>" for r in b["mos_detail"]["เหตุผล"])
    parts.append(f"""<div class='note'>
      <b>ส่วนเผื่อความปลอดภัย {b['mos ที่ใช้']:.0%} — คำนวณจาก</b><ul>{reasons}</ul>
      แนวคิด : เราไม่มีวันประเมินมูลค่าได้แม่นยำ จึงต้องซื้อต่ำกว่าที่ประเมินไว้พอสมควร
      เพื่อให้ยังไม่ขาดทุนแม้ประเมินผิด</div>""")

    # =======================================================================
    # หัวข้อเพิ่มเติมจากโมดูล 2-5, 7-9, 13
    # =======================================================================
    ext = ext or {}
    n = 8

    # ---------- คำแนะนำสรุป (Module 9) ----------
    rc = ext.get("reco")
    if rc and rc.get("ใช้ได้"):
        parts.append(f"<h2>{n}. คำแนะนำสรุปพร้อมเหตุผล</h2>")
        n += 1
        parts.append(
            f"<div class='box' style='border-left:6px solid {rc['สี']}'>"
            f"<div style='font-size:20pt;font-weight:700;color:{rc['สี']}'>"
            f"{esc(rc['คำแนะนำ'])}</div>"
            f"<div>คะแนนรวม {rc['คะแนนรวม']:.1f} / 100 · "
            f"ความมั่นใจ {rc['ความมั่นใจ (%)']:.0f}%</div>"
            f"<div>{esc(rc['คำอธิบายระดับ'])}</div></div>")
        rows = [(f["ด้าน"],
                 f"{f['คะแนน']:.0f} คะแนน · น้ำหนัก {f['น้ำหนักจริง (%)']:.0f}% "
                 f"· ดันคะแนน {f['ดันคะแนน']:+.1f}")
                for f in rc["ปัจจัย"]]
        parts.append(kv_html(rows))
        ev = "".join(f"<li><b>{esc(f['ด้าน'])}</b> — {esc(f['หลักฐาน'])}</li>"
                     for f in rc["ปัจจัย"])
        parts.append(f"<div class='note'><b>หลักฐานของแต่ละด้าน</b>"
                     f"<ul>{ev}</ul></div>")
        if rc.get("อะไรจะเปลี่ยนข้อสรุป"):
            tg = "".join(f"<li>{esc(t['ถ้า'])} ({esc(t['ห่างจากราคาปัจจุบัน'])}) "
                         f"→ <b>{esc(t['จะกลายเป็น'])}</b></li>"
                         for t in rc["อะไรจะเปลี่ยนข้อสรุป"])
            parts.append(f"<div class='note'><b>อะไรจะทำให้ข้อสรุปเปลี่ยน</b>"
                         f"<ul>{tg}</ul>"
                         "ข้อสรุปนี้มาจากกฎถ่วงน้ำหนักที่เขียนไว้ชัดเจน "
                         "ไม่ใช่โมเดลภาษา จึงให้คำตอบเดิมเสมอเมื่อข้อมูลเดิม "
                         "และตรวจย้อนได้ทุกคะแนน</div>")

    # ---------- คุณภาพกิจการและคะแนนกูรู (Module 2-5) ----------
    ql = ext.get("quality")
    if ql:
        parts.append(f"<h2>{n}. คุณภาพกิจการและคะแนนแบบกูรู</h2>")
        n += 1
        sum_rows = []
        for key, label in (("Module 2", "Quality Business Engine"),
                           ("Module 3", "Buffett Score"),
                           ("Module 4", "Peter Lynch Score"),
                           ("Module 5", "Howard Marks Cycle")):
            m = ql.get(key) or {}
            sc = m.get("คะแนนรวม")
            extra = m.get("ระดับ") or m.get("ประเภทตาม Lynch") or \
                m.get("สรุปตำแหน่งวัฏจักร") or ""
            sum_rows.append((label,
                             (f"{sc:.1f} / 100" if sc is not None else "—")
                             + (f" · {extra}" if extra else "")))
        parts.append(kv_html(sum_rows))

        for key in ("Module 2", "Module 3", "Module 4", "Module 5"):
            m = ql.get(key)
            if not m:
                continue
            parts.append(f"<h3>{esc(m['ชื่อโมดูล'])}</h3>")
            parts.append(f"<div class='note'>ประเมินได้ "
                         f"{m['ให้คะแนนได้']}/{m['จำนวนหัวข้อ']} หัวข้อ · "
                         f"มาจากงบโดยตรง {m['สัดส่วนจากงบ (%)']:.0f}% · "
                         f"ต้องดูเอง {m['ต้องดูเอง']} หัวข้อ</div>")
            rr = []
            for it in m["รายการ"]:
                sc = it["คะแนน"]
                val = (f"{sc:.0f}" if sc is not None else "—") + \
                    f"  [{it['ที่มา']}]"
                if it["หลักฐาน"] and it["หลักฐาน"] != "—":
                    val += f" · {it['หลักฐาน']}"
                rr.append((it["หัวข้อ"], val))
            parts.append(kv_html(rr))

        parts.append("""<div class='warn'>
        <b>ความหมายของป้ายที่มา — อ่านก่อนเชื่อคะแนน</b>
        <ul>
          <li><b>คำนวณ</b> วัดจากงบการเงินโดยตรง ตรวจสอบย้อนได้ทุกตัว</li>
          <li><b>ตัวแทน</b> ใช้ตัวเลขอื่นแทนสิ่งที่วัดตรง ๆ ไม่ได้
              เช่น อัตรากำไรขั้นต้นสูงและนิ่ง อนุมานว่ามีแบรนด์
              <b>เป็นการอนุมาน ไม่ใช่การวัด และผิดได้</b></li>
          <li><b>ต้องดูเอง</b> ไม่มีข้อมูลให้ประเมินอัตโนมัติ</li>
        </ul></div>""")

    # ---------- พยากรณ์ 10 ปี (Module 7) ----------
    fc = ext.get("forecast")
    if fc and fc.get("ใช้ได้"):
        parts.append(f"<h2>{n}. พยากรณ์ 10 ปี × 3 ฉาก</h2>")
        n += 1
        asm = fc["ฉาก"]["Base"]["สมมติฐาน"]
        parts.append("<h3>สมมติฐานที่สกัดจากงบย้อนหลัง</h3>")
        parts.append(kv_html([
            (k, fmt(asm[k], 2)) for k in (
                "จำนวนปีข้อมูล", "อัตราโตรายได้ย้อนหลัง (%)",
                "อัตรากำไรขั้นต้น ค่ากลาง (%)", "อัตรากำไรสุทธิ ค่ากลาง (%)",
                "อัตรากำไรสุทธิ ปีล่าสุด (%)", "CapEx / รายได้ (%)",
                "OCF / รายได้ (%)", "อัตราจ่ายปันผล (%)")
            if asm.get(k) is not None]))
        for w in fc.get("คำเตือน", []):
            parts.append(f"<div class='warn'>{esc(w)}</div>")

        parts.append("<h3>เทียบ 3 ฉาก ณ ปีสุดท้าย</h3>")
        c3 = fc["เทียบ 3 ฉาก (ปีสุดท้าย)"]
        rows = []
        for idx, r in c3.iterrows():
            unit = 1 if idx in ("EPS", "เงินปันผลต่อหุ้น") else 1e6
            dec = 2 if unit == 1 else 0
            suffix = "" if unit == 1 else " ล้าน"
            rows.append((idx, " · ".join(
                f"{s} {fmt(r[s] / unit, dec)}{suffix}"
                for s in ("Bear", "Base", "Bull"))))
        parts.append(kv_html(rows))

        d = fc["ฉาก"]["Base"]["ตาราง"]
        parts.append("<h3>ฉาก Base รายปี</h3>")
        head = ("<tr><th>ปีที่</th><th>รายได้ (ล้าน)</th>"
                "<th>กำไรสุทธิ (ล้าน)</th><th>NM %</th><th>EPS</th>"
                "<th>FCF (ล้าน)</th><th>ปันผล/หุ้น</th></tr>")
        body = "".join(
            f"<tr><td>{int(r['ปีที่'])}</td>"
            f"<td class='num'>{fmt(r['รายได้'] / 1e6, 0)}</td>"
            f"<td class='num'>{fmt(r['กำไรสุทธิ'] / 1e6, 0)}</td>"
            f"<td class='num'>{fmt(r['อัตรากำไรสุทธิ (%)'], 1)}</td>"
            f"<td class='num'>{fmt(r['EPS'], 2)}</td>"
            f"<td class='num'>{fmt(r['FCF'] / 1e6, 0)}</td>"
            f"<td class='num'>{fmt(r['เงินปันผลต่อหุ้น'], 3)}</td></tr>"
            for _, r in d.iterrows())
        parts.append(f"<table class='data'>{head}{body}</table>")
        parts.append("""<div class='warn'>
        <b>นี่คือการต่อเส้นแนวโน้มจากอดีต ไม่ใช่การทำนายอนาคต</b>
        โมเดลไม่รู้ว่าบริษัทกำลังจะออกสินค้าใหม่ เสียลูกค้ารายใหญ่
        หรือโดนกฎหมายใหม่ — ปีที่ 1-3 พอใช้อ้างอิงได้
        ปีที่ 8-10 เป็นเพียงกรอบความเป็นไปได้</div>""")

    # ---------- ความเสี่ยง (Module 8) ----------
    rk = ext.get("risk")
    if rk and rk.get("คะแนนรวม") is not None:
        parts.append(f"<h2>{n}. ประเมินความเสี่ยง 12 ด้าน</h2>")
        n += 1
        parts.append(kv_html([
            ("คะแนนความเสี่ยงรวม",
             f"{rk['คะแนนรวม']:.0f} / 100  ({rk.get('ระดับ','')})"),
            ("มาจากตัวเลขจริง",
             f"{rk['สัดส่วนจากตัวเลขจริง (%)']:.0f}% ของน้ำหนักทั้งหมด"),
        ]))
        parts.append(kv_html([
            (name, (f"{d['คะแนน']:.0f}" if d.get("คะแนน") is not None else "—")
             + f"  [{d.get('ที่มา','')}]"
             + (f" · {d.get('คำอธิบาย','')}" if d.get("คำอธิบาย") else ""))
            for name, d in rk["ด้าน"].items()]))
        for name in ("Financial Risk", "Business Risk", "Competition"):
            dd = rk["ด้าน"].get(name) or {}
            if not dd.get("รายละเอียด"):
                continue
            parts.append(f"<h3>{name} — รายละเอียดที่คำนวณจากงบ</h3>")
            parts.append(kv_html([
                (it["ตัวชี้วัด"],
                 f"{fmt(it['ค่า'], 2)} · เสี่ยง {it['คะแนนเสี่ยง']:.0f} · "
                 f"{it['เกณฑ์']}")
                for it in dd["รายละเอียด"]]))
        kp = rk["ด้าน"].get("Key Person Risk") or {}
        if kp.get("คำถามที่ควรหาคำตอบ"):
            qs = "".join(f"<li>{esc(q)}</li>"
                         for q in kp["คำถามที่ควรหาคำตอบ"])
            parts.append(f"<div class='note'><b>Key Person Risk — ต้องประเมินเอง</b>"
                         f"<br>{esc(kp.get('คำอธิบาย',''))}<ul>{qs}</ul></div>")

    # ---------- ข่าว (Module 13) ----------
    nw = ext.get("news")
    if nw:
        parts.append(f"<h2>{n}. ข่าวและผลกระทบ</h2>")
        n += 1
        if nw.get("ใช้ได้"):
            parts.append(kv_html([
                ("จำนวนข่าวที่อ่าน", f"{nw['จำนวนข่าว']} ข่าว"),
                ("ช่วงเวลา", nw.get("ครอบคลุมวันที่", "-")),
                ("Positive / Negative / Neutral",
                 f"{nw['บวก']} / {nw['ลบ']} / {nw['กลาง']}"),
                ("Impact Score",
                 f"{nw['Impact Score']:+.0f} / 100  ({nw['อารมณ์ข่าว']})"),
            ]))
            head = ("<tr><th>วันที่</th><th>ประเภท</th><th>คะแนน</th>"
                    "<th>หัวข้อ</th></tr>")
            body = "".join(
                f"<tr><td>{esc(str(r['วันที่'])[:10])}</td>"
                f"<td>{esc(r['ประเภท'])}</td>"
                f"<td class='num'>{r['คะแนน']:+.1f}</td>"
                f"<td>{esc(str(r['หัวข้อ'])[:90])}</td></tr>"
                for _, r in nw["ตาราง"].iterrows())
            parts.append(f"<table class='data'>{head}{body}</table>")
        else:
            parts.append(f"<div class='note'>{esc(nw.get('เหตุผล',''))}</div>")
        parts.append("""<div class='warn'>
        <b>ข้อจำกัดของการวิเคราะห์ข่าว</b>
        <ul>
          <li>ให้คะแนนจากพจนานุกรมคำ <b>ไม่เข้าใจการประชดหรือบริบท</b></li>
          <li>อ่านได้แค่หัวข้อ ไม่ได้อ่านเนื้อข่าว</li>
          <li>แหล่งข้อมูลฟรีให้ข่าวได้ราว 10-30 หัวข้อต่อหุ้น
              การได้ 10,000 ข่าวต้องใช้บริการข่าวเชิงพาณิชย์
              ซึ่งราคาหลักหมื่นบาทต่อเดือน</li>
          <li>ข่าวหุ้นไทยส่วนใหญ่อยู่บนเว็บ SET ซึ่งไม่เปิด API สาธารณะ</li>
        </ul></div>""")

    # ---------- ที่มาข้อมูล ----------
    parts.append(f"<h2>{n}. ที่มาของข้อมูลและข้อจำกัด</h2>")
    parts.append(kv_html([
        ("งบการเงิน", v["แหล่งงบ"]),
        ("จำนวนปี", f"{v['ปีข้อมูล']} ปี"),
        ("ราคาหุ้นและข้อมูลบริษัท", "yfinance (Yahoo Finance)"),
        ("วันที่ดึงข้อมูล", data.get("fetched_at", "-")),
        ("วันที่สร้างรายงาน", today),
    ]))
    parts.append("""<div class='warn'>
    <b>ข้อจำกัดที่ต้องรู้</b>
    <ul>
      <li>ตัวเลขทั้งหมดคำนวณจากงบการเงินในอดีต ไม่รับประกันผลในอนาคต</li>
      <li>DCF ไวต่อสมมติฐานมาก เปลี่ยน WACC 1% มูลค่าอาจเปลี่ยน 20-30%</li>
      <li>อัตราส่วนราคาย้อนหลังใช้ได้ก็ต่อเมื่อลักษณะธุรกิจไม่เปลี่ยนไปจากเดิม</li>
      <li>รายงานนี้ไม่ได้พิจารณาปัจจัยเชิงคุณภาพ เช่น คุณภาพผู้บริหาร
          การแข่งขัน กฎระเบียบ หรือเหตุการณ์เฉพาะหน้า</li>
      <li>ระบบไม่ทราบข้อมูลที่เกิดขึ้นหลังวันที่ดึงข้อมูลข้างต้น</li>
    </ul>
    <b>เอกสารนี้จัดทำเพื่อการศึกษาส่วนบุคคล ไม่ใช่คำแนะนำการลงทุน</b>
    </div>""")

    body = "".join(parts)
    reg = (FONT_DIR / "Sarabun-Regular.ttf").as_uri()
    bold_p = FONT_DIR / "Sarabun-Bold.ttf"
    bold = bold_p.as_uri() if bold_p.exists() else reg
    css = CSS.replace("FONT_REG", reg).replace("FONT_BOLD", bold)
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'>" \
           f"<style>{css}</style></head><body>{body}</body></html>"


def extras(data, R, v, b, rf=None) -> dict:
    """
    คำนวณโมดูลเสริมทั้งหมดสำหรับใส่ในรายงาน

    ห่อทุกตัวด้วย try/except แยกกัน เพราะโมดูลใดพังไม่ควรทำให้รายงานทั้งฉบับพัง
    — รายงานที่ขาดหัวข้อหนึ่ง ยังมีประโยชน์กว่าไม่มีรายงานเลย
    """
    out = {}
    try:
        import forecast as FC
        out["forecast"] = FC.forecast_all(R)
    except Exception as e:
        out["forecast_error"] = f"{type(e).__name__}: {e}"
    try:
        import risk as RK
        out["risk"] = RK.assess(data, R)
    except Exception as e:
        out["risk_error"] = f"{type(e).__name__}: {e}"
    try:
        import quality as QL
        out["quality"] = QL.assess_all(data, R, v=v, rf=rf)
    except Exception as e:
        out["quality_error"] = f"{type(e).__name__}: {e}"
    try:
        import news_ai as NA
        out["news"] = NA.analyze(data.get("ticker", ""), limit=25)
    except Exception as e:
        out["news_error"] = f"{type(e).__name__}: {e}"
    try:
        import recommend as RC
        vv = dict(v)
        vv["ความน่าเชื่อถือ"] = b.get("ความน่าเชื่อถือ")
        out["reco"] = RC.build(data, R, v=vv, risk=out.get("risk"),
                               qual=out.get("quality"), fc=out.get("forecast"),
                               news=out.get("news"))
    except Exception as e:
        out["reco_error"] = f"{type(e).__name__}: {e}"
    return out


def analyze_all(ticker, wacc=None, g1=None, rf=None, mos=None, refresh=False):
    """
    คำนวณทุกอย่างครั้งเดียว คืน (data, S, R, v, b)

    แยกออกมาเป็นฟังก์ชันต่างหาก เพื่อให้หน้าเว็บ (Part 16) เรียกใช้ครั้งเดียว
    แล้วเอาผลไปทั้งแสดงบนจอและสร้าง PDF ได้ ไม่ต้องคำนวณซ้ำสองรอบ
    """
    data = get_stock_data(ticker, force_refresh=refresh)
    S = analyze(data)
    R = compute_ratios(data)
    v = value_stock(data, R, wacc=wacc, g1=g1, rf=rf)
    b = build_bands(data, R, v, mos=mos)
    return data, S, R, v, b


def render_pdf(data, S, R, v, b, out_dir=None, ext=None) -> Path:
    """สร้างไฟล์ PDF จากผลที่คำนวณไว้แล้ว"""
    setup_matplotlib_font()
    set_chart_theme(dark=False)   # PDF พิมพ์ลงกระดาษขาว จึงใช้ธีมสว่างเสมอ
    html = build_html(data, S, R, v, b, ext=ext)
    out = Path(out_dir) if out_dir else OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    pdf_path = out / f"{data['ticker'].replace('.','_')}_{stamp}.pdf"
    from weasyprint import HTML
    HTML(string=html, base_url=str(BASE_DIR)).write_pdf(str(pdf_path))
    return pdf_path


def make_report(ticker, wacc=None, g1=None, rf=None, mos=None,
                refresh=False, out_dir=None) -> Path:
    setup_matplotlib_font()
    data, S, R, v, b = analyze_all(ticker, wacc, g1, rf, mos, refresh)
    ext = extras(data, R, v, b, rf=rf)
    return render_pdf(data, S, R, v, b, out_dir, ext=ext)


# ---------------------------------------------------------------------------
# รันจาก Terminal
# ---------------------------------------------------------------------------

def _weasyprint_help() -> str:
    """
    ข้อความช่วยเหลือเมื่อ WeasyPrint หาไลบรารีระบบไม่เจอ

    สาเหตุที่พบบ่อยที่สุดบน Mac : ติดตั้ง pango ด้วย brew แล้ว แต่ Python
    ที่มาจาก python.org ไม่รู้จักโฟลเดอร์ของ Homebrew (/opt/homebrew/lib)
    จึงต้องบอกทางให้ด้วยตัวแปรระบบ DYLD_FALLBACK_LIBRARY_PATH
    """
    import platform
    brew_lib = "/opt/homebrew/lib"          # Apple Silicon (M1-M5)
    if platform.machine() != "arm64":
        brew_lib = "/usr/local/lib"         # Mac รุ่น Intel
    has_lib = Path(brew_lib).exists()

    out = ["\n[ไม่สำเร็จ] WeasyPrint หาไลบรารีระบบไม่เจอ\n"]
    if has_lib:
        out.append("  ไลบรารีติดตั้งไว้แล้ว แต่ Python หาไม่เจอ")
        out.append("  (Python จาก python.org ไม่รู้จักโฟลเดอร์ของ Homebrew)\n")
        out.append("  แก้ทันที — พิมพ์ 2 บรรทัดนี้:")
        out.append(f"    export DYLD_FALLBACK_LIBRARY_PATH={brew_lib}")
        out.append("    python3 report.py <ticker>\n")
        out.append("  แก้ถาวร — เพิ่มบรรทัดนี้ลงใน ~/.zshrc:")
        out.append(f"    echo 'export DYLD_FALLBACK_LIBRARY_PATH={brew_lib}' >> ~/.zshrc")
        out.append("    source ~/.zshrc\n")
    else:
        out.append("  ยังไม่ได้ติดตั้งไลบรารี — พิมพ์:")
        out.append("    brew install pango gdk-pixbuf libffi")
        out.append(f"    export DYLD_FALLBACK_LIBRARY_PATH={brew_lib}\n")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description="Part 15 — สร้างรายงาน PDF ภาษาไทย")
    p.add_argument("ticker")
    p.add_argument("--wacc", type=float)
    p.add_argument("--g1", type=float)
    p.add_argument("--rf", type=float, help="อัตราพันธบัตร (หุ้นไทยควรใส่ 0.025)")
    p.add_argument("--mos", type=float, help="ส่วนเผื่อความปลอดภัย เช่น 0.30")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--open", action="store_true", help="เปิดไฟล์ทันทีเมื่อสร้างเสร็จ")
    args = p.parse_args()

    try:
        path = make_report(args.ticker, wacc=args.wacc, g1=args.g1, rf=args.rf,
                           mos=args.mos, refresh=args.refresh)
    except FileNotFoundError as e:
        print(f"\n[ไม่สำเร็จ] {e}\n", file=sys.stderr)
        return 1
    except (OSError, ImportError) as e:
        msg = str(e).lower()
        if "libgobject" in msg or "cannot load library" in msg or "pango" in msg:
            print(_weasyprint_help(), file=sys.stderr)
            return 1
        print(f"\n[ไม่สำเร็จ] {type(e).__name__}: {e}\n", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n[ไม่สำเร็จ] {type(e).__name__}: {e}\n", file=sys.stderr)
        return 1

    size_kb = path.stat().st_size / 1024
    print(f"\nสร้างรายงานเสร็จแล้ว")
    print(f"  ไฟล์ : {path}")
    print(f"  ขนาด : {size_kb:,.0f} KB\n")
    if args.open:
        subprocess.run(["open", str(path)], check=False)
    else:
        print(f"  เปิดดูด้วยคำสั่ง :  open \"{path}\"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
