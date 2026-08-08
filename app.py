"""
app.py — Part 16 : Web App (Streamlit)
=======================================
หน้าที่ : ห่อทุก Part เป็นหน้าเว็บ พิมพ์ ticker → กดปุ่ม → ได้ผลวิเคราะห์ + PDF

ทำไมใช้ Streamlit
  เขียน Python ล้วน ไม่ต้องรู้ HTML/CSS/JavaScript
  ได้หน้าเว็บที่เปิดได้ทั้ง iPhone / Android / Mac ด้วยลิงก์เดียว

วิธีรันบนเครื่องตัวเอง
    streamlit run app.py
  แล้วเบราว์เซอร์จะเปิดขึ้นมาเองที่ http://localhost:8501

วิธีเปิดจากมือถือในบ้านเดียวกัน (ยังไม่ต้อง deploy)
    streamlit run app.py --server.address 0.0.0.0
  แล้วเปิดมือถือไปที่ http://<ไอพีของ Mac>:8501
  (ดูไอพีด้วยคำสั่ง : ipconfig getifaddr en0)
"""

import base64
import io
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# ตั้งค่าอีเมลติดต่อ SEC ก่อน import ส่วนอื่น
# (บน Streamlit Cloud ให้ใส่ใน Settings → Secrets แทนการเขียนลงโค้ด)
# ---------------------------------------------------------------------------
try:
    if "SEC_CONTACT_EMAIL" in st.secrets:
        os.environ["SEC_CONTACT_EMAIL"] = st.secrets["SEC_CONTACT_EMAIL"]
except Exception:
    pass

st.set_page_config(page_title="Equity Research AI Pro",
                   page_icon="📊", layout="wide",
                   initial_sidebar_state="collapsed")

ZONE_COLOR = {"Strong Buy": "#1b5e20", "Buy": "#2e7d32", "Hold": "#757575",
              "Reduce": "#ef6c00", "Sell": "#c62828"}


# ---------------------------------------------------------------------------
# ปุ่มสลับธีม
#
# ทำไมต้องเขียน CSS เอง ไม่ใช้ของ Streamlit :
#   Streamlit อ่านธีมจากไฟล์ config.toml ตอนเปิดแอป และมีปุ่มสลับซ่อนอยู่ในเมนู ⋮
#   ซึ่งหายาก โดยเฉพาะบนมือถือ เราจึงกำหนดสีเองทั้งหมด
#   เพื่อให้ปุ่มในหน้าเว็บเป็นตัวตัดสิน ไม่ว่าผู้ใช้จะตั้งค่าอะไรไว้ในเมนู
# ---------------------------------------------------------------------------

THEMES = {
    "dark":  {"bg": "#0e1117", "bg2": "#1a1f2b", "txt": "#e8eaed",
              "dim": "#9aa4b2", "line": "rgba(255,255,255,.14)", "pri": "#5b9bd5"},
    "light": {"bg": "#ffffff", "bg2": "#f2f5f9", "txt": "#1a1a1a",
              "dim": "#5f6b7a", "line": "rgba(0,0,0,.12)", "pri": "#1f4e79"},
}

if "theme" not in st.session_state:
    st.session_state["theme"] = "dark"


def apply_theme(name: str):
    """ฉีด CSS ตามธีมที่เลือก — ครอบทั้งพื้นหลัง ตัวหนังสือ ช่องกรอก และตาราง"""
    c = THEMES[name]
    st.markdown(f"""
<style>
  /* พื้นหลังหลักและแถบบน */
  .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
      background-color:{c['bg']} !important; color:{c['txt']}; }}
  [data-testid="stHeader"] {{ background-color:{c['bg']} !important; }}
  [data-testid="stSidebar"] {{ background-color:{c['bg2']} !important; }}

  /* ตัวหนังสือทั่วไป — ไม่ใส่ !important เพื่อให้สีเฉพาะจุดที่เรากำหนดเองยังชนะ */
  h1,h2,h3,h4,h5,h6,p,li,label,summary,
  [data-testid="stMarkdownContainer"],
  [data-testid="stCaptionContainer"] {{ color:{c['txt']}; }}
  [data-testid="stCaptionContainer"], .muted {{ color:{c['dim']}; }}

  /* ช่องกรอกและช่องเลือก */
  input, textarea, [data-baseweb="select"] > div,
  [data-baseweb="popover"] li {{
      background-color:{c['bg2']} !important; color:{c['txt']} !important; }}
  [data-baseweb="popover"] div {{ background-color:{c['bg2']} !important; }}

  /* แท็บ */
  [data-testid="stTabs"] button p {{ color:{c['txt']}; }}

  /* ส่วนประกอบที่เราสร้างเอง */
  /* พื้นที่แสดงผล — ใช้ความกว้างจอเกือบเต็ม เพื่อให้ตารางหลายคอลัมน์อ่านได้ในหน้าเดียว
     min() = เอาค่าที่น้อยกว่าระหว่าง 97% ของจอ กับ 1900px
     (กันไม่ให้ยืดเกินไปบนจอกว้างมากจนตาต้องกวาดไกล) */
  .block-container {{ padding-top:1.2rem; padding-left:1.2rem; padding-right:1.2rem;
                     max-width:min(97vw, 1900px) !important; }}
  .zone {{ display:inline-block; padding:.4rem 1.4rem; border-radius:.5rem;
          color:#fff !important; font-size:1.4rem; font-weight:700; }}
  .zone * {{ color:#fff !important; }}
  .t {{ color:{c['txt']}; }}
  /* ตรึงหัวตารางไว้ด้านบนเวลาเลื่อนลงดูรายการยาว ๆ */
  .t thead th {{ background:{c['bg2']} !important; color:{c['txt']} !important;
                position:sticky; top:0; z-index:2; }}
  .t td {{ border-bottom:1px solid {c['line']}; }}
  .t tbody tr:nth-child(even) {{ background:rgba(128,128,128,.10); }}
  .mc {{ border:1px solid {c['line']}; border-radius:.5rem; padding:.6rem .8rem; }}
  .mc .k {{ color:{c['dim']}; font-size:.78rem; }}
  .mc .v {{ color:{c['txt']}; font-size:1.3rem; font-weight:700; line-height:1.3; }}
  .mc .d {{ font-size:.78rem; }}
  .tw {{ overflow-x:auto; }}
  /* ชื่อหุ้นที่กดได้ในตารางคัดกรอง */
  a.tk {{ color:{c['pri']} !important; font-weight:700; text-decoration:none;
         border-bottom:1px dashed {c['pri']}; }}
  a.tk:hover {{ opacity:.75; }}
  /* หัวตารางที่กดเพื่อจัดเรียงได้ */
  a.sh {{ color:{c['txt']} !important; text-decoration:none; cursor:pointer;
         white-space:nowrap; }}
  a.sh:hover {{ color:{c['pri']} !important; }}
  a.sh.cur {{ color:{c['pri']} !important; font-weight:700; }}
</style>
""", unsafe_allow_html=True)


def toggle_theme():
    st.session_state["theme"] = "light" if st.session_state["theme"] == "dark" else "dark"


apply_theme(st.session_state["theme"])
DARK = st.session_state["theme"] == "dark"


# ---------------------------------------------------------------------------
# ส่วนคำนวณ (เก็บผลไว้ 1 ชั่วโมง เพื่อไม่ให้ยิงขอข้อมูลซ้ำ ๆ)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=3600)
def run_analysis(ticker, wacc, g1, rf, mos, refresh):
    from report import analyze_all
    return analyze_all(ticker, wacc=wacc, g1=g1, rf=rf, mos=mos, refresh=refresh)


@st.cache_data(show_spinner=False, ttl=3600)
def make_pdf_bytes(ticker, wacc, g1, rf, mos, refresh):
    from report import analyze_all, render_pdf
    import tempfile
    data, S, R, v, b = analyze_all(ticker, wacc=wacc, g1=g1, rf=rf,
                                   mos=mos, refresh=refresh)
    with tempfile.TemporaryDirectory() as td:
        p = render_pdf(data, S, R, v, b, out_dir=td)
        return Path(p).read_bytes(), Path(p).name


def show_chart(b64, empty_msg="ไม่มีข้อมูลเพียงพอสำหรับกราฟนี้"):
    if b64:
        st.image(io.BytesIO(base64.b64decode(b64)), use_container_width=True)
    else:
        st.caption(f"— {empty_msg}")


# ---------------------------------------------------------------------------
# ตารางแบบ HTML ธรรมดา
#
# ทำไมไม่ใช้ st.dataframe / st.metric :
#   คอมโพเนนต์เหล่านั้นต้องโหลดไฟล์ JavaScript เพิ่มจากเซิร์ฟเวอร์
#   ถ้าโหลดไม่สำเร็จ (เน็ตสะดุด, ส่วนขยายเบราว์เซอร์บล็อก, มือถือสัญญาณอ่อน)
#   จะขึ้น "Importing a module script failed" แทนที่จะเห็นตัวเลข
#   ตาราง HTML ธรรมดาไม่มีปัญหานี้ และแสดงผลบนมือถือได้ดีกว่า
# ---------------------------------------------------------------------------

# โครงสร้างตาราง (ระยะห่าง/การจัดชิด) — ส่วนที่เป็น "สี" อยู่ใน apply_theme()
st.markdown("""
<style>
 .t { width:100%; border-collapse:collapse; font-size:.82rem; margin:.3rem 0 .9rem 0; }
 .t th { padding:.35rem .5rem; text-align:right; font-weight:600; white-space:nowrap; }
 .t th.l, .t td.l { text-align:left; }
 .t td { padding:.3rem .5rem; text-align:right; white-space:nowrap; }
</style>
""", unsafe_allow_html=True)


def _cell(x, dec=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)) or pd.isna(x):
        return "—"
    if isinstance(x, (int, float, np.floating, np.integer)):
        return f"{x:,.{dec}f}"
    return str(x)


def html_table(df: pd.DataFrame, first_col="รายการ", dec=2, trim_year=True,
               max_height=None, link_cols=(), sort_cols=(),
               cur_sort=None, cur_asc=True):
    """
    แสดง DataFrame เป็นตาราง HTML

    max_height : ถ้าใส่ (เช่น 520) ตารางจะสูงไม่เกินนั้นแล้ว **เลื่อนลงดูได้**
                 พร้อมตรึงหัวตารางไว้ด้านบน — ใช้กับรายการหุ้นยาว ๆ
    sort_cols  : ชื่อคอลัมน์ที่ "กดหัวตารางแล้วเรียงได้"
                 ▲ = เรียงน้อยไปมาก · ▼ = มากไปน้อย · ⇅ = กดเพื่อเรียง
    link_cols  : ชื่อคอลัมน์ที่จะทำเป็นลิงก์กดได้ (เช่น "ticker")
                 กดแล้วจะพาไปวิเคราะห์รายตัวของหุ้นตัวนั้น
                 กลไก : ลิงก์ใส่พารามิเตอร์ ?t=AAPL ต่อท้าย URL
                        แอปอ่านค่านี้ตอนโหลดใหม่แล้วสลับโหมดให้เอง
    """
    from urllib.parse import quote
    cols = [str(c)[:4] if trim_year else str(c) for c in df.columns]
    style = f" style='max-height:{max_height}px;overflow-y:auto'" if max_height else ""
    h = [f"<div class='tw'{style}><table class='t'><thead><tr>"
         f"<th class='l'>{first_col}</th>"]
    for c in cols:
        if c in sort_cols:
            # กดหัวตาราง = ส่ง ?sort=<คอลัมน์>&order=... กลับมาที่แอป
            # กดคอลัมน์เดิมซ้ำ = สลับทิศทางการเรียง
            is_cur = (c == cur_sort)
            nxt = "desc" if (is_cur and cur_asc) else "asc"
            arrow = (" ▲" if cur_asc else " ▼") if is_cur else " ⇅"
            cls = "sh cur" if is_cur else "sh"
            h.append(f"<th><a class='{cls}' target='_self' "
                     f"href='?sort={quote(str(c))}&order={nxt}'>{c}{arrow}</a></th>")
        else:
            h.append(f"<th>{c}</th>")
    h.append("</tr></thead><tbody>")
    for name in df.index:
        h.append(f"<tr><td class='l'>{name}</td>")
        for c in df.columns:
            val = _cell(df.loc[name, c], dec)
            if c in link_cols and val != "—":
                # target="_self" = เปิดในแท็บเดิม ไม่เด้งแท็บใหม่
                # เปิดแท็บใหม่ เพื่อไม่ให้ผลคัดกรองในแท็บเดิมหายไป
                val = (f"<a class='tk' target='_blank' rel='noopener' "
                       f"href='?t={str(df.loc[name, c]).strip()}'>{val}</a>")
            h.append(f"<td>{val}</td>")
        h.append("</tr>")
    h.append("</tbody></table></div>")
    st.markdown("".join(h), unsafe_allow_html=True)


def kv_table(pairs, dec=2):
    """ตารางสองคอลัมน์ : ชื่อรายการ / ค่า"""
    rows = "".join(
        f"<tr><td class='l'>{k}</td><td><b>{_cell(v, dec)}</b></td></tr>"
        for k, v in pairs)
    st.markdown(f"<div class='tw'><table class='t'>{rows}</table></div>",
                unsafe_allow_html=True)


def metric_card(col, label, value, delta=None, color=None):
    d = (f"<div class='d' style='color:{color}'>{delta}</div>"
         if delta and color else
         (f"<div class='d' style='opacity:.7'>{delta}</div>" if delta else ""))
    col.markdown(f"<div class='mc'><div class='k'>{label}</div>"
                 f"<div class='v'>{value}</div>{d}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# หน้าเว็บ
# ---------------------------------------------------------------------------

tt1, tt2 = st.columns([5, 1])
with tt1:
    st.title("📊 Equity Research AI Pro")
    st.caption("วิเคราะห์หุ้นจากงบการเงินจริง · หุ้นสหรัฐใช้ SEC EDGAR ย้อนหลัง 15 ปี · "
               "หุ้นไทยใส่ .BK ต่อท้าย")
with tt2:
    st.write("")
    st.button("☀️ ธีมสว่าง" if DARK else "🌙 ธีมมืด",
              on_click=toggle_theme, use_container_width=True,
              help="สลับระหว่างธีมมืดและธีมสว่าง กราฟจะเปลี่ยนสีตามอัตโนมัติ")

MODES = ["วิเคราะห์รายตัว", "คัดกรองทั้งตลาด", "วิเคราะห์ลึกหลายตัว",
         "เปรียบเทียบ 2–10 ตัว"]

# ---------------------------------------------------------------------------
# รับคำสั่ง "กดชื่อหุ้นในตารางแล้วมาวิเคราะห์รายตัว"
#
# ลิงก์ในตารางจะพาไปที่ URL เดิมแต่ต่อท้ายด้วย ?t=AAPL
# ตรงนี้อ่านค่านั้น สลับโหมดให้ แล้วล้างพารามิเตอร์ทิ้ง
# (ต้องล้าง มิฉะนั้นกดปุ่มอื่นทีหลังจะเด้งกลับมาหุ้นตัวเดิมตลอด)
# ---------------------------------------------------------------------------
_qp = st.query_params
if "t" in _qp:
    st.session_state["mode"] = MODES[0]
    st.session_state["jump"] = str(_qp["t"]).strip().upper()
    st.session_state["ran"] = True
    st.query_params.clear()
elif "sort" in _qp:
    # กดหัวตารางเพื่อจัดเรียง — เก็บลง session แล้วล้าง URL
    from urllib.parse import unquote
    st.session_state["sort_col"] = unquote(str(_qp["sort"]))
    st.session_state["sort_dir"] = ("น้อย → มาก"
                                    if str(_qp.get("order", "asc")) == "asc"
                                    else "มาก → น้อย")
    st.query_params.clear()

if "mode" not in st.session_state:
    st.session_state["mode"] = MODES[0]

MODE = st.radio("โหมด", MODES, horizontal=True,
                label_visibility="collapsed", key="mode")


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def ticker_options():
    """รายชื่อหุ้นสำหรับช่องค้นหา — เก็บไว้ 24 ชม. เพราะแทบไม่เปลี่ยน"""
    from tickers import build_options
    return build_options()


try:
    OPTIONS, LOOKUP = ticker_options()
except Exception:
    OPTIONS, LOOKUP = [], {}

# ---------------------------------------------------------------------------
# โหมดคัดกรองทั้งตลาด (ชั้นที่ 1 — เร็ว)
# ---------------------------------------------------------------------------
if MODE.startswith("คัดกรอง"):
    from screener import preset, quality_flags, quick_filter, quick_screen

    st.info("**ชั้นคัดกรองเร็ว** — ดึงเฉพาะตัวเลขสรุป (P/E, P/BV, ROE) "
            "ไม่ทำ DCF จึงเร็วกว่าราว 20 เท่า ใช้ได้กับทั้งตลาด\n\n"
            "หลังคัดได้แล้ว ให้เอารายชื่อไปวิเคราะห์ลึกในโหมดถัดไป")

    uni = st.radio("ตลาด",
                   ["🇺🇸 หุ้นสหรัฐทั้งตลาด (เร็ว)", "🇹🇭 หุ้นไทย",
                    "หุ้นสหรัฐยอดนิยม 39 ตัว"],
                   horizontal=True)

    if uni.startswith("🇺🇸"):
        st.success("**วิธีเร็ว** — ดึงงบการเงินของทุกบริษัทในตลาดจาก SEC "
                   "ด้วยเพียง **8 คำขอ** (แทนที่จะเป็น 10,000 คำขอ) "
                   "แล้วดึงราคาทีละ 180 ตัว\n\n"
                   "⏱️ ทั้งตลาด ~10,000 บริษัท ใช้เวลาราว **3–6 นาที**")
        universe, key, bulk = None, "us-all", True
    elif uni.startswith("🇹🇭"):
        bulk, key = False, "thai"
        from tickers import load_set, thai_industries, thai_universe
        meta = load_set()["meta"]
        st.caption(f"ทะเบียนบริษัทจดทะเบียน · {meta.get('ที่มา','-')} "
                   f"· ข้อมูล ณ {meta.get('ข้อมูล ณ','-')} · {meta.get('จำนวน',0):,} รายการ")
        t1, t2, t3 = st.columns([1, 2, 1])
        with t1:
            mkt = st.radio("ตลาด", ["ทั้งหมด", "SET", "mai"], horizontal=True)
        with t2:
            ind = st.selectbox("กลุ่มอุตสาหกรรม", ["ทุกกลุ่ม"] + thai_industries())
        universe = thai_universe(market=None if mkt == "ทั้งหมด" else mkt,
                                 industry=None if ind == "ทุกกลุ่ม" else ind)
        with t3:
            cap = st.number_input("จำกัดจำนวน (0 = ไม่จำกัด)", 0, max(len(universe), 1),
                                  0, 25)
        universe = universe[:cap] if cap else universe
        mins = len(universe) * 1.5 / 8 / 60
        st.caption(f"จะคัดกรอง **{len(universe):,} ตัว** — คาดว่าราว {mins:.1f} นาที "
                   "· นับเฉพาะหุ้นสามัญ (ตัดกองทุนรวมและ REIT ออก "
                   "เพราะไม่มีงบแบบบริษัท จึงคิด P/E, ROE ไม่ได้)")
    else:
        bulk, key = False, "us"
        full = preset(key)
        cap = st.number_input("จำกัดจำนวน (0 = ไม่จำกัด)", 0, len(full), 0, 5)
        universe = full[:cap] if cap else full
        st.caption(f"จะคัดกรอง {len(universe):,} ตัว")

    # ---------- ชื่อชุดข้อมูลสำหรับเก็บไว้ใช้ซ้ำ ----------
    # ต้องผูกกับ "ขอบเขตที่คัดกรอง" ไม่ใช่แค่ชื่อตลาด
    # ไม่อย่างนั้นข้อมูลของกลุ่มธนาคารจะไปทับข้อมูลของทั้งตลาด
    snap_key = key if bulk else f"{key}-{len(universe)}"
    if key == "thai":
        snap_key = f"thai-{mkt}-{ind}-{len(universe)}"

    qa1, qa2 = st.columns([2, 1])
    with qa1:
        qmode = st.radio(
            "หุ้นที่มีจุดต้องระวัง (ขาดทุน · ส่วนทุนติดลบ · ตัวเลขผิดปกติ)",
            ["⚠️ แสดงพร้อมติดธงเตือน", "🛡️ ตัดออกจากตาราง", "แสดงทั้งหมด ไม่ติดธง"],
            horizontal=True,
            help="ค่าตัวเลขในตารางเป็นค่าจริงของหุ้นแต่ละตัวเสมอ "
                 "ไม่ว่าจะเลือกแบบไหน — ตัวเลือกนี้กำหนดแค่ว่าจะ "
                 "แสดง ซ่อน หรือติดธงเตือนหุ้นที่มีจุดต้องระวัง")
    quality = not qmode.startswith("แสดงทั้งหมด")
    with qa2:
        q_cap = st.number_input("มูลค่าตลาดขั้นต่ำ (ล้าน)", 0.0, 1e6, 1000.0, 250.0,
                                disabled=not quality)
    if quality:
        q_fcy = st.slider(
            "เพดาน FCF Yield ที่ยอมรับได้ (%)", 10, 200, 50, 5,
            help="กิจการปกติมี FCF Yield ราว 3-15%\n\n"
                 "ถ้าเกิน 50% มักเป็นเงินสดก้อนเดียวที่ไม่เกิดซ้ำ เช่น "
                 "อสังหาฯ ขายคอนโดค้างสต็อก หรือธุรกิจรถเช่าขายรถเก่าออก "
                 "— เป็นเงินสดจริงแต่ปีหน้าไม่มีอีก")
    else:
        q_fcy = 1000

    st.markdown("**เกณฑ์คัดกรอง** (ปล่อยเป็น 0 = ไม่ใช้เกณฑ์นั้น)")
    g = st.columns(9)
    f_pe = g[0].number_input("P/E ไม่เกิน", 0.0, 200.0, 0.0, 1.0)
    f_pbv = g[1].number_input("P/BV ไม่เกิน", 0.0, 50.0, 0.0, 0.5)
    f_roe = g[2].number_input("ROE ขั้นต่ำ (%)", 0.0, 100.0, 0.0, 1.0)
    f_fcf = g[3].number_input("FCF Yield ขั้นต่ำ (%)", 0.0, 50.0, 0.0, 0.5)
    f_div = g[4].number_input("ปันผลขั้นต่ำ (%)", 0.0, 20.0, 0.0, 0.5)
    f_de = g[5].number_input("D/E ไม่เกิน (เท่า)", 0.0, 20.0, 0.0, 0.25,
                             help="หนี้สินรวม ÷ ส่วนของผู้ถือหุ้น "
                                  "ยิ่งต่ำยิ่งปลอดภัย · ธนาคารจะสูงเป็นปกติ")
    f_gm = g[6].number_input("กำไรขั้นต้นขั้นต่ำ (%)", 0.0, 100.0, 0.0, 1.0,
                             help="อัตรากำไรขั้นต้นสูง = สินค้ามีอำนาจตั้งราคา "
                                  "หรือมีความได้เปรียบด้านต้นทุน")
    f_nm = g[7].number_input("กำไรสุทธิขั้นต่ำ (%)", 0.0, 100.0, 0.0, 1.0)
    f_cap = g[8].number_input("มูลค่าตลาดขั้นต่ำ (ล้าน)", 0.0, 1e7, 0.0, 1000.0)

    # ---------- ปุ่มดึงข้อมูล ----------
    # มี 2 ทาง : ดึงใหม่ (ช้า แต่สด) หรือ ใช้ที่บันทึกไว้ (เร็วทันที)
    import snapshot

    # ห่อด้วย cache เพราะทุกครั้งที่กดปุ่มใด ๆ Streamlit จะรันไฟล์นี้ใหม่ทั้งหมด
    # ถ้าไม่ห่อ จะยิงไป Google Drive ทุกครั้งที่ขยับหน้าจอ ทำให้หน่วง
    @st.cache_data(show_spinner=False, ttl=300)
    def _peek(k):
        return snapshot.info(k)

    _saved, _smeta = _peek(snap_key)
    r1, r2 = st.columns([2, 3])
    run_fresh = r1.button("เริ่มคัดกรอง (ดึงข้อมูลใหม่)", type="primary",
                          use_container_width=True)
    use_saved = False
    if _saved is not None:
        age = _smeta.get("อายุ (ชม.)", 0)
        age_txt = f"{age:.0f} ชม.ที่แล้ว" if age >= 1 else "เมื่อสักครู่"
        n_ok_saved = int(_saved["ปัญหา"].eq("").sum()) if "ปัญหา" in _saved else 0
        use_saved = r2.button(
            f"⚡ ใช้ข้อมูลที่บันทึกไว้ ({n_ok_saved:,} ตัว · {age_txt})",
            use_container_width=True,
            help=f"อ่านจาก{_smeta.get('ที่มา (ไทย)', '-')} "
                 "— ได้ผลทันทีไม่ต้องรอดึงใหม่")
    else:
        r2.caption("ยังไม่มีข้อมูลที่บันทึกไว้สำหรับขอบเขตนี้ · "
                   "ถ้าดึงบนเว็บไม่สำเร็จ ให้รันบน MacBook แล้ว push ขึ้นมา "
                   "(`python3 tools_snapshot_build.py --thai`)")

    if use_saved:
        st.session_state["quick_df"] = _saved
        st.caption(f"ใช้ข้อมูลที่บันทึกไว้เมื่อ {_smeta.get('บันทึกเมื่อ','-')} "
                   f"· จาก**{_smeta.get('ที่มา (ไทย)','-')}**")

    if run_fresh:
        bar, note = st.progress(0.0), st.empty()

        def on_q(i, total, t):
            bar.progress(min(i / total, 1.0))
            note.caption(f"{t} — {i:,}/{total:,}")

        try:
            if bulk:
                from market import us_market_snapshot
                fresh = us_market_snapshot(progress=on_q)
            else:
                fresh = quick_screen(universe, progress=on_q)
            st.session_state["quick_df"] = fresh
            # เก็บไว้ใช้ครั้งหน้า — เฉพาะตัวเลขในตาราง ไม่มีรายละเอียดอื่น
            #
            # แต่ **ห้ามทับของเดิมด้วยรอบที่ดึงไม่สำเร็จ**
            # ถ้า Yahoo บล็อกจนได้ 0 ตัว แล้วเราบันทึกทับ ของดีที่มีอยู่จะหายไปด้วย
            n_ok = int(fresh["ปัญหา"].eq("").sum())
            if n_ok >= max(1, len(fresh) * 0.3):
                r = snapshot.save(snap_key, fresh,
                                  extra={"ขอบเขต": snap_key, "ตลาด": key,
                                         "ดึงสำเร็จ": n_ok})
                _peek.clear()                 # ให้ปุ่ม ⚡ เห็นของใหม่ทันที
                where = " + ".join([w for w, ok in
                                    (("เครื่องนี้", r["local"]),
                                     ("Google Drive", r["drive"])) if ok]) or "ไม่ได้บันทึก"
                st.caption(f"บันทึกผลไว้แล้ว : {where} · {r.get('ขนาด (KB)', 0)} KB "
                           "— ครั้งหน้ากดปุ่ม ⚡ เรียกได้ทันที")
            else:
                st.caption(f"รอบนี้ดึงสำเร็จเพียง {n_ok:,} ตัว — **ไม่บันทึกทับของเดิม** "
                           "เพื่อไม่ให้ข้อมูลที่ดีอยู่แล้วหายไป")
        except Exception as e:
            st.error(f"ดึงข้อมูลไม่สำเร็จ — {type(e).__name__}: {e}\n\n"
                     "ถ้าเป็นการคัดกรองทั้งตลาด ลองรันบน MacBook แทน:\n\n"
                     "```\npython3 market.py --csv us_market.csv\n```")
        bar.progress(1.0)
        note.empty()

    qdf = st.session_state.get("quick_df")
    if qdf is not None and not qdf.empty:
        got = qdf[qdf["ปัญหา"].eq("")]
        # ติดธงเตือนเสมอ — ค่าตัวเลขไม่ถูกแตะต้อง
        qdf = qdf.copy()
        qdf["⚠️"] = quality_flags(qdf, min_mcap=q_cap, max_fcf_yield=q_fcy) if quality else ""
        if qmode.startswith("🛡️"):
            base = qdf[qdf["⚠️"].eq("") & qdf["ปัญหา"].eq("")].reset_index(drop=True)
        else:
            base = qdf[qdf["ปัญหา"].eq("")].reset_index(drop=True)
        res = quick_filter(base, max_pe=f_pe or None, max_pbv=f_pbv or None,
                           min_roe=f_roe or None, min_fcf_yield=f_fcf or None,
                           min_div=f_div or None, min_mcap=f_cap or None,
                           max_de=f_de or None, min_gross_margin=f_gm or None,
                           min_net_margin=f_nm or None)

        # ---------- จัดเรียงตามหัวข้อที่เลือก ----------
        # ค่าเริ่มต้นของแต่ละหัวข้อตั้งให้ "ตัวที่น่าสนใจอยู่บน" โดยอัตโนมัติ
        #   P/E, P/BV, P/S, D/E  → น้อยไปมาก (ยิ่งต่ำยิ่งน่าสนใจ)
        #   ROE, FCF Yield, ปันผล, มูลค่าตลาด → มากไปน้อย
        SORTABLE = ["P/E", "P/BV", "P/S", "D/E", "ROE (%)", "FCF Yield (%)",
                    "อัตรากำไรขั้นต้น (%)", "อัตรากำไรสุทธิ (%)", "ปันผล (%)",
                    "มูลค่าตลาด (ล้าน)", "ราคา", "ticker"]
        ASC_BY_DEFAULT = {"P/E", "P/BV", "P/S", "D/E", "ticker"}
        # ---------- แถวปุ่มจัดเรียง ----------
        # ใช้ปุ่มของ Streamlit ไม่ใช่ลิงก์ HTML
        # เหตุผล : ลิงก์ทำให้เบราว์เซอร์โหลดหน้าใหม่ -> Streamlit สร้าง session ใหม่
        #          -> ผลคัดกรองที่ใช้เวลาดึงมาหลายนาทีหายหมด ต้องเริ่มใหม่
        #          ปุ่มทำงานภายในหน้าเดิม ข้อมูลจึงอยู่ครบ
        st.session_state.setdefault("sort_col", "P/E")
        st.session_state.setdefault("sort_asc", True)

        def _sort_by(c):
            """กดคอลัมน์เดิมซ้ำ = สลับทิศทาง · กดคอลัมน์ใหม่ = ใช้ทิศทางที่เหมาะกับตัวเลขนั้น"""
            if st.session_state["sort_col"] == c:
                st.session_state["sort_asc"] = not st.session_state["sort_asc"]
            else:
                st.session_state["sort_col"] = c
                st.session_state["sort_asc"] = c in ASC_BY_DEFAULT

        st.markdown("**จัดเรียงตาม** (กดซ้ำที่ปุ่มเดิมเพื่อสลับทิศทาง)")
        for row in (SORTABLE[:6], SORTABLE[6:]):
            bc = st.columns(len(row))
            for col, c in zip(bc, row):
                cur = st.session_state["sort_col"] == c
                mark = ("  ▲" if st.session_state["sort_asc"] else "  ▼") if cur else ""
                col.button(f"{c}{mark}", key=f"sb_{c}", on_click=_sort_by, args=(c,),
                           type="primary" if cur else "secondary",
                           use_container_width=True)

        sort_col = st.session_state["sort_col"]
        asc = st.session_state["sort_asc"]
        order = "น้อย → มาก" if asc else "มาก → น้อย"

        # อัตราส่วนราคาที่ "ติดลบ" ไม่ได้แปลว่าถูก
        #   P/E ติดลบ  = ขาดทุน
        #   P/BV ติดลบ = ส่วนของผู้ถือหุ้นติดลบ (ขาดทุนสะสมจนทุนหมด)
        #   P/S ติดลบ  = รายได้ติดลบ
        # ถ้าปล่อยให้เรียงตามค่าจริง บริษัทที่มีปัญหาหนักที่สุดจะลอยขึ้นอันดับ 1
        # จึงผลักค่าที่ไม่เป็นบวกไปท้ายตารางเหมือนค่าว่าง
        POSITIVE_ONLY = {"P/E", "P/BV", "P/S", "EV/EBITDA"}
        if sort_col in res.columns:
            key = pd.to_numeric(res[sort_col], errors="coerce")
            if sort_col in POSITIVE_ONLY:
                key = key.where(key > 0)          # ค่า <= 0 ถือเป็น "ไม่มีข้อมูล"
            res = (res.assign(_k=key)
                      .sort_values("_k", ascending=asc, na_position="last")
                      .drop(columns="_k").reset_index(drop=True))
        k = st.columns(4)
        rate = len(got) / len(qdf) * 100 if len(qdf) else 0
        metric_card(k[0], "ดึงข้อมูลได้", f"{len(got):,} / {len(qdf):,}",
                    f"{rate:.0f}%", "#2e7d32" if rate >= 85 else "#ef6c00")
        n_flag = int((base["⚠️"] != "").sum()) if "⚠️" in base.columns else 0
        metric_card(k[1], "มีจุดต้องระวัง",
                    f"{n_flag:,} ตัว" if quality else "ไม่ได้ตรวจ",
                    "ซ่อนไว้" if qmode.startswith("🛡️") else
                    ("ติดธงไว้" if quality else None))
        metric_card(k[2], "ผ่านเกณฑ์", f"{len(res):,} ตัว")
        # ใช้ "ค่ากลาง" ไม่ใช่ "ต่ำสุด" — ค่าต่ำสุดมักเป็นข้อมูลเสียเพียงตัวเดียว
        pe_pos = pd.to_numeric(res.get("P/E"), errors="coerce")
        pe_pos = pe_pos[pe_pos > 0] if pe_pos is not None else pd.Series(dtype=float)
        metric_card(k[3], "P/E ค่ากลางของกลุ่มที่ผ่าน",
                    f"{pe_pos.median():,.1f}" if len(pe_pos) else "—",
                    "(ตารางแสดงค่าจริงรายตัว)")

        # ---------- บอกสาเหตุเมื่อดึงข้อมูลไม่สำเร็จ ----------
        # ถ้าไม่แสดงสาเหตุ ผู้ใช้จะเห็นแค่ "0 ตัว" แล้วเดาไม่ออกว่าเป็นที่เกณฑ์
        # หรือที่แหล่งข้อมูล ซึ่งเป็นคนละปัญหาและแก้คนละวิธี
        if len(got) < len(qdf) * 0.5:
            errs = qdf.loc[~qdf["ปัญหา"].eq(""), "ปัญหา"].value_counts()
            with st.expander(f"⚠️ ดึงข้อมูลไม่สำเร็จ {len(qdf)-len(got):,} ตัว "
                             "— กดดูสาเหตุ", expanded=len(got) == 0):
                for msg, n in errs.head(6).items():
                    st.markdown(f"- **{n:,} ตัว** — `{msg}`")
                st.markdown(
                    "---\n"
                    "**ถ้าเจอ `429` หรือ `Too Many Requests`** = Yahoo ปฏิเสธคำขอ  \n"
                    "Yahoo บล็อกเครื่องในศูนย์ข้อมูล (ซึ่งรวมถึง Streamlit Cloud) "
                    "แต่ไม่บล็อกเครื่องบ้าน — วิธีแก้ที่ได้ผลแน่นอนคือ "
                    "**รันบน MacBook แล้วส่งผลขึ้น Google Drive** "
                    "จากนั้นกดปุ่ม ⚡ บนเว็บหรือมือถือได้ทันที\n\n"
                    "```\neq\npython3 tools_snapshot_build.py --thai\n```")

        if res.empty:
            st.warning("ไม่มีหุ้นตัวใดผ่านเกณฑ์ — ลองผ่อนเกณฑ์ลง")
        else:
            # ธงเตือนไว้ท้ายตาราง — ตัวเลขที่ใช้ตัดสินใจควรอยู่ใกล้ชื่อหุ้นมากกว่า
            cols = ["ticker", "ชื่อบริษัท", "ราคา", "P/E", "P/BV", "P/S", "D/E",
                    "ROE (%)", "อัตรากำไรขั้นต้น (%)", "อัตรากำไรสุทธิ (%)",
                    "FCF Yield (%)", "ปันผล (%)", "มูลค่าตลาด (ล้าน)", "กลุ่ม", "⚠️"]
            # จำนวนแถวที่แสดง — ค่าเริ่มต้นคือ "ทั้งหมด"
            # เหตุผล : การตัดที่ 200 ทำให้หุ้นที่ผ่านเกณฑ์อีก 600 ตัวหายไปเงียบ ๆ
            #          ผู้ใช้ควรเห็นทุกตัวที่ผ่านเกณฑ์ ไม่ใช่แค่ส่วนบน
            n_show = st.selectbox(
                "จำนวนแถวที่แสดง", ["ทั้งหมด", 100, 300, 500],
                index=0,
                help="ตารางเลื่อนดูได้ในตัวเอง — เลือกน้อยลงได้ถ้าเครื่องหน่วง")
            show = res[[c for c in cols if c in res.columns]]
            if n_show != "ทั้งหมด":
                show = show.head(int(n_show))
            show = show.copy()
            show.index = [str(i) for i in range(1, len(show) + 1)]
            # หุ้นเป็น "แถว" (ไม่ใส่ .T) จึงเลื่อนลงดูตัวถัดไปได้ตามปกติ
            # link_cols = ทำชื่อหุ้นให้กดได้ → เด้งไปวิเคราะห์รายตัวทันที
            html_table(show, first_col="อันดับ", trim_year=False,
                       max_height=640, link_cols=("ticker",))
            if quality:
                st.caption("**ความหมายของธง ⚠️** — `ขาดทุน` กำไรสุทธิติดลบ · "
                           "`ทุนติดลบ` ส่วนของผู้ถือหุ้นติดลบ · "
                           "`เล็ก` มูลค่าตลาดต่ำกว่าเกณฑ์ · "
                           "`FCF?` FCF Yield สูงผิดปกติ · `P/E?` P/E ต่ำผิดปกติ  \n"
                           "ตัวเลขทุกช่องเป็นค่าจริงของหุ้นตัวนั้น ธงเป็นเพียงข้อสังเกตเพิ่มเติม")
            _n = ("ครบทั้ง" if len(show) == len(res) else "แสดง")
            st.caption(f"เรียงตาม **{sort_col}** ({order}) · "
                       f"{_n} {len(show):,} ตัวจาก {len(res):,} ตัวที่ผ่านเกณฑ์ "
                       "· **กดที่ชื่อหุ้น** เพื่อดูการวิเคราะห์รายตัวทันที "
                       "· เลื่อนลงในตารางเพื่อดูตัวถัดไป")
            st.download_button("ดาวน์โหลดผลทั้งหมด (CSV)",
                               res.to_csv(index=False).encode("utf-8-sig"),
                               "ผลคัดกรอง.csv", "text/csv")

            # ---------- ช่องติ๊กเลือกหุ้นทีละตัว ----------
            st.markdown("---")
            st.markdown("### ☑️ ติ๊กเลือกหุ้นไปวิเคราะห์ลึกหรือเปรียบเทียบ")
            st.caption("ชั้นคัดกรองบอกได้แค่ว่า 'ตัวเลขสรุปดูน่าสนใจ' "
                       "ยังไม่ได้ประเมินมูลค่า — เลือกตัวที่สนใจส่งไปวิเคราะห์เต็มรูปแบบ")

            picked = st.session_state.setdefault("picked", set())
            PER_PAGE = 25
            n_pages = max(1, (len(res) + PER_PAGE - 1) // PER_PAGE)
            pg = st.number_input(f"หน้า (ทั้งหมด {n_pages} หน้า · {len(res):,} ตัว)",
                                 1, n_pages, 1, 1)
            page = res.iloc[(pg - 1) * PER_PAGE: pg * PER_PAGE]

            HEADS = ["เลือก", "หุ้น", "ชื่อบริษัท", "P/E", "P/BV", "D/E",
                     "ROE %", "GM %", "NM %"]
            WIDTHS = [0.6, 1.4, 2.6, 0.9, 0.9, 0.9, 1.0, 1.0, 1.0]
            hd = st.columns(WIDTHS)
            for col, txt in zip(hd, HEADS):
                col.markdown(f"<span class='muted'><b>{txt}</b></span>",
                             unsafe_allow_html=True)

            for _, r in page.iterrows():
                t = r["ticker"]
                cc = st.columns(WIDTHS)
                on = cc[0].checkbox(" ", value=t in picked, key=f"cb_{t}",
                                    label_visibility="collapsed")
                picked.add(t) if on else picked.discard(t)
                cc[1].markdown(f"<a class='tk' target='_blank' rel='noopener' "
                               f"href='?t={t}'>{t}</a>", unsafe_allow_html=True)
                cc[2].caption(str(r["ชื่อบริษัท"])[:34])
                cc[3].caption(_cell(r.get("P/E"), 1))
                cc[4].caption(_cell(r.get("P/BV"), 2))
                cc[5].caption(_cell(r.get("D/E"), 2))
                cc[6].caption(_cell(r.get("ROE (%)"), 1))
                cc[7].caption(_cell(r.get("อัตรากำไรขั้นต้น (%)"), 1))
                cc[8].caption(_cell(r.get("อัตรากำไรสุทธิ (%)"), 1))

            sel = [t for t in res["ticker"] if t in picked]
            st.markdown(f"**เลือกไว้ {len(sel)} ตัว** "
                        + (f"— {', '.join(sel[:15])}" + (" ..." if len(sel) > 15 else "")
                           if sel else "— ยังไม่ได้เลือก"))

            b1, b2, b3, b4 = st.columns(4)
            with b1:
                st.button("เลือกทั้งหน้านี้", use_container_width=True,
                          on_click=lambda p=list(page["ticker"]): [
                              st.session_state["picked"].add(x) for x in p])
            with b2:
                st.button("ล้างที่เลือก", use_container_width=True,
                          on_click=lambda: st.session_state["picked"].clear())
            with b3:
                st.button(f"วิเคราะห์ลึก ({len(sel)})",
                          type="primary", use_container_width=True,
                          disabled=len(sel) == 0,
                          on_click=lambda: st.session_state.update(
                              {"handoff": sel, "mode": MODES[2]}))
            with b4:
                st.button(f"เปรียบเทียบ ({len(sel)})", use_container_width=True,
                          disabled=not (2 <= len(sel) <= 10),
                          help="เลือก 2–10 ตัวจึงจะเปรียบเทียบได้",
                          on_click=lambda: st.session_state.update(
                              {"handoff": sel, "mode": MODES[3]}))
            if len(sel) > 20:
                st.warning(f"เลือกมา {len(sel)} ตัว — วิเคราะห์ลึกจะใช้เวลาราว "
                           f"{len(sel)*30/60:.0f} นาที แนะนำไม่เกิน 20 ตัวต่อครั้ง")

        st.error("⚠️ **ชั้นนี้ยังไม่ได้ประเมินมูลค่า** — P/E ต่ำไม่ได้แปลว่าถูก "
                 "อาจเป็นเพราะกำไรปีล่าสุดสูงผิดปกติ หรือธุรกิจกำลังถดถอย\n\n"
                 "ตัวเลขทั้งหมดในตารางนี้มาจาก yfinance ซึ่งคำนวณจากงบ 12 เดือนล่าสุด "
                 "ไม่ได้ผ่านการตรวจสอบเหมือนชั้นวิเคราะห์ลึก")
    st.stop()


# ---------------------------------------------------------------------------
# โหมดเปรียบเทียบ 2–10 ตัว
# ---------------------------------------------------------------------------
if MODE.startswith("เปรียบเทียบ"):
    from screener import MAX_COMPARE, MIN_COMPARE, compare

    st.info(f"เลือกหุ้น {MIN_COMPARE}–{MAX_COMPARE} ตัว "
            "ระบบจะวิเคราะห์ลึกทุกตัวแล้ววางเทียบกันให้เห็นชัด ๆ\n\n"
            "⏱️ ราว 30 วินาทีต่อตัว")

    handoff = st.session_state.pop("handoff", None)
    if handoff:
        st.success(f"รับรายชื่อจากหน้าคัดกรองแล้ว {len(handoff)} ตัว")

    picks = st.multiselect("เลือกหุ้นที่จะเปรียบเทียบ", OPTIONS,
                           max_selections=MAX_COMPARE,
                           placeholder="พิมพ์ชื่อย่อหรือชื่อบริษัท")
    cmp_list = [LOOKUP.get(p, str(p).split(" ")[0]) for p in picks]

    extra = st.text_input("หรือพิมพ์เพิ่มเอง (คั่นด้วยเว้นวรรค)",
                          value=" ".join(handoff) if handoff else "",
                          placeholder="เช่น AAPL MSFT PTT.BK")
    cmp_list += [x.strip().upper() for x in extra.split() if x.strip()]
    cmp_list = list(dict.fromkeys(cmp_list))[:MAX_COMPARE]

    c_rf = st.number_input("อัตราพันธบัตร (หุ้นไทยใส่ 0.025)", 0.0, 0.15, 0.0, 0.005,
                           format="%.3f")

    if cmp_list:
        st.caption(f"จะเปรียบเทียบ {len(cmp_list)} ตัว : {', '.join(cmp_list)}")

    if st.button("เปรียบเทียบ", type="primary", use_container_width=True,
                 disabled=len(cmp_list) < MIN_COMPARE):
        bar, note = st.progress(0.0), st.empty()

        def on_c(i, total, t):
            bar.progress((i - 1) / total)
            note.caption(f"กำลังวิเคราะห์ {t} ... ({i}/{total})")

        try:
            st.session_state["cmp"] = compare(cmp_list, rf=c_rf or None, progress=on_c)
        except ValueError as e:
            st.error(str(e))
        bar.progress(1.0)
        note.empty()

    res = st.session_state.get("cmp")
    if res and not res["table"].empty:
        w = res.get("winner")
        if w:
            st.success(f"**ตัวเลขน่าสนใจที่สุด : {w['ticker']}** — "
                       f"ส่วนลด {w['ส่วนลด (%)']:.0f}% · "
                       f"ความน่าเชื่อถือ {w['ความน่าเชื่อถือ']}  \n"
                       "จัดอันดับโดยให้น้ำหนัก *ส่วนลด* กับ *ความน่าเชื่อถือ* **เท่ากัน** — "
                       "เป็นการจัดอันดับตัวเลข ไม่ใช่คำแนะนำให้ซื้อ")
        html_table(res["table"], first_col="หัวข้อ", trim_year=False)
        for tk, err in res["errors"]:
            st.caption(f"⚠️ {tk} — {err}")
        st.download_button("ดาวน์โหลดผลเปรียบเทียบ (CSV)",
                           res["raw"].to_csv(index=False).encode("utf-8-sig"),
                           "เปรียบเทียบหุ้น.csv", "text/csv")
    elif len(cmp_list) < MIN_COMPARE:
        st.caption(f"เลือกอย่างน้อย {MIN_COMPARE} ตัวจึงจะเปรียบเทียบได้")
    st.stop()


# ---------------------------------------------------------------------------
# โหมดวิเคราะห์ลึกหลายตัว (ชั้นที่ 2)
# ---------------------------------------------------------------------------
if MODE.startswith("วิเคราะห์ลึก"):
    from screener import preset, scan, undervalued

    st.info("**วิธีทำงาน** — ระบบจะวิเคราะห์หุ้นทีละตัวแบบเต็มรูปแบบ "
            "แล้วเรียงลำดับตามส่วนลดจากมูลค่าที่ประเมินได้\n\n"
            "⏱️ ใช้เวลาราว **30 วินาทีต่อหุ้น 1 ตัว** ในครั้งแรก "
            "(ตัวที่เคยวิเคราะห์แล้วจะเร็วมาก) — แนะนำให้เริ่มที่ 10–15 ตัวก่อน")

    handoff = st.session_state.pop("handoff", None)
    if handoff:
        st.session_state["deep_text"] = " ".join(handoff)
        st.success(f"รับรายชื่อจากหน้าคัดกรองแล้ว {len(handoff)} ตัว — "
                   "กด **เริ่มวิเคราะห์ลึก** ได้เลย")

    s1, s2 = st.columns([3, 2])
    with s1:
        group = st.radio("ชุดหุ้น",
                         ["รายชื่อที่ส่งมา / พิมพ์เอง", "หุ้นไทย",
                          "หุ้นสหรัฐยอดนิยม", "เลือกจากรายชื่อ"],
                         horizontal=True,
                         index=0 if st.session_state.get("deep_text") else 1)
    with s2:
        n_max = st.slider("จำนวนสูงสุด", 3, 40, 10)

    if group.startswith("รายชื่อที่ส่งมา"):
        txt = st.text_area("รายชื่อหุ้น (คั่นด้วยเว้นวรรคหรือขึ้นบรรทัดใหม่)",
                           key="deep_text", height=90,
                           placeholder="เช่น AAPL MSFT PTT.BK KBANK.BK")
        scan_list = [x.strip().upper() for x in txt.replace(",", " ").split()][:n_max]
    elif group == "เลือกจากรายชื่อ":
        picks = st.multiselect("เลือกหุ้นที่ต้องการวิเคราะห์", OPTIONS, max_selections=40)
        scan_list = [LOOKUP.get(p, str(p).split(" ")[0]) for p in picks]
    else:
        scan_list = preset("thai" if group == "หุ้นไทย" else "us")[:n_max]
    if scan_list:
        st.caption(f"จะวิเคราะห์ {len(scan_list)} ตัว : {', '.join(scan_list[:12])}"
                   + (" ..." if len(scan_list) > 12 else "")
                   + f" · คาดว่าราว {len(scan_list)*30/60:.0f} นาที")

    f1, f2, f3 = st.columns(3)
    with f1:
        s_rf = st.number_input("อัตราพันธบัตร", 0.0, 0.15,
                               0.025 if group == "หุ้นไทย" else 0.042, 0.005,
                               format="%.3f")
    with f2:
        min_disc = st.slider("ส่วนลดขั้นต่ำ (%)", -50, 80, 0, 5)
    with f3:
        min_score = st.slider("คะแนนความน่าเชื่อถือขั้นต่ำ", 0, 100, 0, 5)

    if st.button("เริ่มวิเคราะห์ลึก", type="primary", use_container_width=True):
        if not scan_list:
            st.warning("ยังไม่ได้เลือกหุ้น")
            st.stop()
        bar = st.progress(0.0)
        note = st.empty()

        def on_progress(i, total, t):
            bar.progress((i - 1) / total)
            note.caption(f"กำลังวิเคราะห์ {t} ... ({i}/{total})")

        df = scan(scan_list, rf=s_rf or None, progress=on_progress)
        bar.progress(1.0)
        note.empty()
        st.session_state["scan_df"] = df

    df = st.session_state.get("scan_df")
    if df is not None and not df.empty:
        ok = df[df["ปัญหา"].eq("")]
        under = undervalued(df, min_disc, min_score)
        k = st.columns(3)
        metric_card(k[0], "วิเคราะห์สำเร็จ", f"{len(ok)} / {len(df)}")
        metric_card(k[1], "ราคาต่ำกว่ามูลค่า", f"{len(under)} ตัว")
        best = under["ส่วนลด (%)"].max() if not under.empty else None
        metric_card(k[2], "ส่วนลดสูงสุด",
                    f"{best:,.0f}%" if best is not None else "—")

        if under.empty:
            st.warning("ไม่มีหุ้นตัวใดผ่านเกณฑ์ที่ตั้งไว้ — ลองลดส่วนลดขั้นต่ำลง")
        else:
            DEEP_SORT = ["ส่วนลด (%)", "คะแนน", "ROE เฉลี่ย (%)", "D/E",
                         "CAGR รายได้ (%)", "ปีข้อมูล", "ราคา", "ticker"]
            DEEP_ASC = {"D/E", "ticker", "ราคา"}
            z1, z2 = st.columns([2, 1])
            with z1:
                d_sort = st.selectbox("จัดเรียงตาม", DEEP_SORT, index=0,
                                      key="deep_sort")
            with z2:
                d_ord = st.radio("ลำดับ", ["น้อย → มาก", "มาก → น้อย"],
                                 index=0 if d_sort in DEEP_ASC else 1,
                                 horizontal=True, label_visibility="collapsed",
                                 key="deep_order")
            if d_sort in under.columns:
                under = under.sort_values(d_sort, ascending=d_ord.startswith("น้อย"),
                                          na_position="last").reset_index(drop=True)

            cols = ["ticker", "ชื่อบริษัท", "ราคา", "มูลค่าที่ประเมินได้",
                    "ส่วนลด (%)", "โซน", "ความน่าเชื่อถือ", "คะแนน", "ปีข้อมูล",
                    "ROE เฉลี่ย (%)", "D/E", "Net Debt/EBITDA",
                    "CAGR รายได้ (%)", "ตลาดคาดโต (%)", "ใช้ DCF"]
            show = under[[c for c in cols if c in under.columns]].copy()
            show.index = [str(i) for i in range(1, len(show) + 1)]
            html_table(show, first_col="อันดับ", trim_year=False,
                       max_height=520, link_cols=("ticker",))
            st.caption("**กดที่ชื่อหุ้น** เพื่อเปิดการวิเคราะห์รายตัวพร้อมรายงาน PDF")

        bad = df[~df["ปัญหา"].eq("")]
        if not bad.empty:
            with st.expander(f"วิเคราะห์ไม่สำเร็จ {len(bad)} ตัว"):
                for _, r in bad.iterrows():
                    st.caption(f"**{r['ticker']}** — {r['ปัญหา']}")

        st.error("⚠️ **ส่วนลดมากไม่ได้แปลว่าหุ้นดี** — หุ้นที่ราคาต่ำกว่ามูลค่ามาก "
                 "มักมีเหตุผลที่ตลาดให้ราคาต่ำ เช่น กำไรกำลังถดถอยหรือธุรกิจถูกแทนที่ "
                 "ระบบนี้บอกได้แค่ว่า *ตัวเลขในอดีตกับราคาวันนี้ไม่ตรงกัน* ไม่ได้บอกว่าทำไม\n\n"
                 "ให้เปิดวิเคราะห์รายตัวและอ่านรายงานฉบับเต็มก่อนตัดสินใจเสมอ")
    st.stop()


# หุ้นที่ถูกกดมาจากตารางคัดกรอง (ถ้ามี)
JUMP = st.session_state.pop("jump", None)
if JUMP:
    st.success(f"เปิดจากตารางคัดกรอง : **{JUMP}**")

manual = st.toggle("พิมพ์ ticker เอง (สำหรับหุ้นที่ไม่มีในรายชื่อ)",
                   value=bool(JUMP) or not OPTIONS,
                   help="รายชื่อหุ้นไทยเป็นรายชื่อตั้งต้น ไม่ครบทุกตัว "
                        "ถ้าหาไม่เจอให้เปิดสวิตช์นี้แล้วพิมพ์เอง")

c1, c2 = st.columns([3, 1])
with c1:
    if manual or not OPTIONS:
        ticker = st.text_input("ใส่ชื่อย่อหุ้น", value=JUMP or "AAPL",
                               key=f"tk_{JUMP or 'default'}",
                               placeholder="เช่น AAPL, MSFT, PTT.BK",
                               label_visibility="collapsed").strip().upper()
    else:
        # selectbox ของ Streamlit กรองรายชื่อให้ทันทีที่พิมพ์
        # (ค้นได้ทั้งชื่อย่อและชื่อบริษัท เช่น พิมพ์ "ปตท" หรือ "Apple")
        default = OPTIONS.index("AAPL — Apple Inc.") if "AAPL — Apple Inc." in OPTIONS else 0
        pick = st.selectbox("เลือกหุ้น", OPTIONS, index=default,
                            label_visibility="collapsed",
                            placeholder="พิมพ์ชื่อย่อหรือชื่อบริษัท เช่น AAPL, ปตท, ธนาคาร")
        ticker = LOOKUP.get(pick, str(pick).split(" ")[0]).upper()
with c2:
    go = st.button("วิเคราะห์", type="primary", use_container_width=True)

if OPTIONS and not manual:
    st.caption(f"ค้นหาได้ {len(OPTIONS):,} ตัว — พิมพ์ชื่อย่อหรือชื่อบริษัทเพื่อกรอง")

with st.expander("ตั้งค่าขั้นสูง (ไม่กรอกก็ได้ ระบบจะประมาณให้เอง)"):
    a1, a2, a3, a4 = st.columns(4)
    with a1:
        wacc = st.number_input("อัตราคิดลด WACC", 0.0, 0.30, 0.0, 0.005,
                               format="%.3f",
                               help="0 = ให้ระบบคำนวณจาก beta และต้นทุนหนี้จริง")
    with a2:
        g1 = st.number_input("อัตราโตช่วงแรก g1", 0.0, 0.30, 0.0, 0.005,
                             format="%.3f", help="0 = ใช้ CAGR ย้อนหลัง")
    with a3:
        rf = st.number_input("อัตราพันธบัตร", 0.0, 0.15, 0.0, 0.005,
                             format="%.3f",
                             help="หุ้นไทยควรใส่ ~0.025 (พันธบัตรไทย) "
                                  "ถ้าใส่ 0 จะใช้ของสหรัฐ 4.2%")
    with a4:
        mos = st.number_input("ส่วนเผื่อความปลอดภัย", 0.0, 0.60, 0.0, 0.05,
                              format="%.2f",
                              help="0 = ให้ระบบปรับตามความไม่แน่นอนอัตโนมัติ")
    refresh = st.checkbox("ดึงข้อมูลใหม่ ไม่ใช้ที่เก็บไว้")

if not go and "ran" not in st.session_state:
    st.info("พิมพ์ชื่อย่อหุ้นแล้วกด **วิเคราะห์** — ครั้งแรกของแต่ละตัวใช้เวลาราว 20–40 วินาที "
            "เพราะต้องดึงงบย้อนหลัง 15 ปี ครั้งต่อไปจะเร็วมาก")
    st.stop()

if go:
    st.session_state["ran"] = True

# แปลง 0 เป็น None (= ให้ระบบตัดสินใจเอง)
kw = dict(wacc=wacc or None, g1=g1 or None, rf=rf or None,
          mos=mos or None, refresh=refresh)

try:
    with st.spinner(f"กำลังวิเคราะห์ {ticker} ..."):
        data, S, R, v, b = run_analysis(ticker, kw["wacc"], kw["g1"],
                                        kw["rf"], kw["mos"], kw["refresh"])
except Exception as e:
    st.error(f"วิเคราะห์ไม่สำเร็จ\n\n{type(e).__name__}: {e}")
    st.stop()

info = data.get("info", {})
cur = v["สกุลเงิน"]
price = v["ราคาปัจจุบัน"]
fair = b["มูลค่าที่ประเมินได้"]
zone = b["โซนปัจจุบัน"]
rel = b["ความน่าเชื่อถือ"]

# ---------- หัวเรื่อง ----------
st.markdown("---")
h1, h2 = st.columns([2, 1])
with h1:
    st.subheader(info.get("longName") or ticker)
    st.caption(f"{info.get('sector','-')} · {info.get('industry','-')} · "
               f"{info.get('exchange','-')} · ข้อมูล {v['ปีข้อมูล']} ปี จาก {v['แหล่งงบ']}")
with h2:
    st.markdown(f"<div style='text-align:right'><span class='zone' "
                f"style='background:{ZONE_COLOR.get(zone,'#757575')}'>{zone}</span></div>",
                unsafe_allow_html=True)

m = st.columns(4)
gap = (fair / price - 1) * 100
metric_card(m[0], "ราคาตลาด", f"{price:,.2f} {cur}")
metric_card(m[1], "มูลค่าที่ประเมินได้", f"{fair:,.2f} {cur}",
            f"{gap:+.1f}%", "#2e7d32" if gap > 0 else "#c62828")
metric_card(m[2], "ส่วนเผื่อความปลอดภัย", f"{b['mos ที่ใช้']:.0%}")
metric_card(m[3], "ความน่าเชื่อถือ", rel["ระดับ"], f"{rel['คะแนน']}/100", "#666")

# คำเตือนความน่าเชื่อถือ — แสดงเด่นเพราะสำคัญพอ ๆ กับตัวเลข
if rel["คำเตือน"]:
    box = st.error if rel["คะแนน"] < 50 else st.warning
    box("**ข้อจำกัดของการประเมินครั้งนี้**\n\n"
        + "\n".join(f"- {x}" for x in rel["คำเตือน"]))

if v.get("หมายเหตุวิธีประเมิน"):
    st.warning("**หมายเหตุวิธีประเมิน**\n\n"
               + "\n".join(f"- {n}" for n in v["หมายเหตุวิธีประเมิน"]))

ig = v.get("อัตราโตที่ตลาดคาดหวัง")
if ig is not None:
    g_hist = R["summary"].get("CAGR FCF (%)")
    st.info(f"**ราคาวันนี้กำลังบอกอะไร** — ที่ราคา {price:,.2f} {cur} "
            f"ตลาดคาดว่ากระแสเงินสดอิสระจะโตปีละ **{ig:+.1%}** ติดต่อกัน "
            f"{v['years1']} ปี  \nขณะที่ย้อนหลัง {v['ปีข้อมูล']} ปี "
            f"บริษัททำได้จริง **{g_hist:.1f}%** ต่อปี")

# ---------- ปุ่มดาวน์โหลด PDF ----------
d1, d2 = st.columns([1, 3])
with d1:
    if st.button("สร้างรายงาน PDF", use_container_width=True):
        try:
            with st.spinner("กำลังสร้าง PDF ..."):
                pdf, fname = make_pdf_bytes(ticker, kw["wacc"], kw["g1"],
                                            kw["rf"], kw["mos"], kw["refresh"])
            st.session_state["pdf"] = (pdf, fname)
        except FileNotFoundError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"สร้าง PDF ไม่สำเร็จ: {type(e).__name__}: {e}")
with d2:
    if "pdf" in st.session_state:
        pdf, fname = st.session_state["pdf"]
        st.download_button(f"ดาวน์โหลด {fname}", pdf, fname,
                           mime="application/pdf", use_container_width=True)

# ---------- เนื้อหาแยกแท็บ ----------
import report as RP
RP.setup_matplotlib_font()
# กราฟใช้พื้นหลังโปร่งใส เปลี่ยนแค่สีเส้นและตัวหนังสือให้เข้ากับธีม
RP.set_chart_theme(dark=DARK)

t1, t2, t3, t4, t5 = st.tabs(
    ["ภาพรวม", "ผลประกอบการ", "อัตราส่วน", "ประเมินมูลค่า", "ช่วงราคา"])

with t1:
    a, bb = st.columns(2)
    sm = R["summary"]
    with a:
        st.markdown("**อัตราการเติบโต (%)**")
        kv_table([("CAGR รายได้", sm["CAGR รายได้ (%)"]),
                  ("CAGR กำไรสุทธิ", sm["CAGR กำไรสุทธิ (%)"]),
                  ("CAGR EPS", sm["CAGR EPS (%)"]),
                  ("CAGR FCF", sm["CAGR FCF (%)"])])
    with bb:
        st.markdown("**คุณภาพกิจการ**")
        kv_table([("ROE เฉลี่ย (%)", sm["ROE เฉลี่ย (%)"]),
                  ("ROIC เฉลี่ย (%)", sm["ROIC เฉลี่ย (%)"]),
                  ("Gross Margin เฉลี่ย (%)", sm["Gross Margin เฉลี่ย (%)"]),
                  ("OCF/กำไรสุทธิ เฉลี่ย (เท่า)", sm["OCF/กำไรสุทธิ เฉลี่ย (x)"])])
    show_chart(RP.chart_revenue_profit(R))

with t2:
    show_chart(RP.chart_margins(R))
    show_chart(RP.chart_returns(R))
    show_chart(RP.chart_cashflow(R))
    st.markdown("**งบกำไรขาดทุน (ล้าน)**")
    html_table(S["income"] / 1e6, dec=0)

with t3:
    st.caption("บรรทัดที่ขึ้น — แปลว่างบของบริษัทนี้ไม่มีรายการนั้น "
               "(เช่น ธนาคารไม่มีสินค้าคงเหลือหรือกำไรขั้นต้น)")
    for gname, names in R["groups"].items():
        rows = [n for n in names if n in R["table"].index]
        if not rows:
            continue
        sub = R["table"].loc[rows]
        st.markdown(f"**{gname}**")
        if sub.notna().sum().sum() == 0:
            st.caption("— ไม่มีข้อมูลหมวดนี้สำหรับบริษัทนี้")
            continue
        html_table(sub)

with t4:
    q1, q2 = st.columns(2)
    w = v["wacc_detail"]
    with q1:
        st.markdown("**อัตราคิดลด (WACC)**")
        kv_table([("Beta", f"{w['beta']:.2f}"),
                  ("พันธบัตร", f"{w['พันธบัตร (rf)']:.2%}"),
                  ("ต้นทุนส่วนทุน", f"{w['ต้นทุนส่วนทุน']:.2%}"),
                  ("ต้นทุนหนี้", f"{w['ต้นทุนหนี้']:.2%}"),
                  ("อัตราภาษี", f"{w['อัตราภาษี']:.2%}"),
                  ("WACC ที่ใช้", f"{v['wacc ที่ใช้']:.2%}")])
    with q2:
        st.markdown("**สมมติฐาน DCF**")
        if v.get("ใช้ DCF ได้ไหม"):
            i = v["inputs"]
            kv_table([("FCF ปีฐาน (ล้าน)", f"{i['fcf0 (เฉลี่ย 3 ปี)']/1e6:,.0f}"),
                      ("อัตราโต g1", f"{v['g1 ที่ใช้']:.2%}"),
                      ("อัตราโตถาวร g2", f"{v['g2 ที่ใช้']:.2%}"),
                      ("ปีช่วงโตสูง", f"{v['years1']} ปี"),
                      ("สัดส่วนมูลค่าสุดท้าย",
                       f"{v['base_dcf']['สัดส่วนมูลค่าสุดท้าย']:.0%}")])
        else:
            st.caption("ไม่ได้ใช้ DCF กับหุ้นตัวนี้ — ดูเหตุผลด้านบน")

    show_chart(RP.chart_methods(v), "ไม่มีวิธีใดประเมินมูลค่าได้สำเร็จ")

    if v.get("sensitivity") is not None:
        st.markdown("**ตารางความไว (Sensitivity)** — แถว = WACC, คอลัมน์ = g1")
        html_table(v["sensitivity"], first_col="WACC \\ g1", dec=0, trim_year=False)
        st.caption("ถ้าตัวเลขในตารางกระจายกว้างมาก แปลว่าอย่าเชื่อมูลค่าตัวเดียว "
                   "ให้ใช้เป็นช่วงแทน")

    bv = v.get("book_value")
    if bv:
        st.markdown("**มูลค่าตามบัญชี (P/BV)**")
        kv_table([("P/BV ค่ากลางทั้งช่วง", f"{bv['P/BV ค่ากลาง']:.2f} เท่า"),
                  ("P/BV ค่ากลาง 5 ปีล่าสุด",
                   f"{bv['P/BV ค่ากลาง 5 ปีล่าสุด']:.2f} เท่า"),
                  ("มูลค่าตามบัญชีต่อหุ้นล่าสุด", f"{bv['BVPS ล่าสุด']:,.2f} {cur}")])

    if v.get("historical"):
        show_chart(RP.chart_pe_history(v))

with t5:
    show_chart(RP.chart_price_bands(data, b))
    rows = []
    for n, (lo, hi) in b["bands"].items():
        rng = (f"มากกว่า {lo:,.2f}" if hi == float("inf")
               else f"ต่ำกว่า {hi:,.2f}" if lo == 0 else f"{lo:,.2f} – {hi:,.2f}")
        mark = "  ◀ ราคาปัจจุบัน" if n == zone else ""
        rows.append((n, f"{rng} {cur}{mark}"))
    kv_table(rows)
    st.markdown(f"**ส่วนเผื่อความปลอดภัย {b['mos ที่ใช้']:.0%} — คำนวณจาก**")
    for r in b["mos_detail"]["เหตุผล"]:
        st.markdown(f"- {r}")

st.markdown("---")
st.caption(f"ข้อมูลดึงเมื่อ {data.get('fetched_at','-')} · "
           f"งบการเงินจาก {v['แหล่งงบ']} · ราคาจาก yfinance · "
           f"สร้างหน้านี้เมื่อ {datetime.now().strftime('%d/%m/%Y %H:%M')}")
st.warning("เอกสารและตัวเลขทั้งหมดในหน้านี้จัดทำโดยระบบอัตโนมัติเพื่อการศึกษา "
           "**ไม่ใช่คำแนะนำการลงทุน** ผู้ใช้ควรตรวจสอบด้วยตนเองก่อนตัดสินใจใด ๆ")
