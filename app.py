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
                   initial_sidebar_state="auto")

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

# pri = สีสำหรับ "ตัวหนังสือ" เช่น ลิงก์ หัวตาราง — ต้องอ่านออกบนพื้นหลังของธีม
# btn = สีสำหรับ "พื้นปุ่มหลัก" ซึ่งมีตัวหนังสือสีขาวทับอยู่ — ต้องเข้มพอ
#
# ทำไมต้องแยกสองค่า : ธีมมืดใช้ฟ้าสว่าง #5b9bd5 เป็นสีลิงก์เพราะอ่านง่ายบนพื้นดำ
# แต่ถ้าเอาสีนั้นมาเป็นพื้นปุ่มแล้วใส่ตัวหนังสือขาว ความต่างเหลือ 2.96
# ซึ่งต่ำกว่าเกณฑ์อ่านง่าย (4.5) — ตัวหนังสือจะจางจนอ่านลำบาก
THEMES = {
    "dark":  {"bg": "#0e1117", "bg2": "#1a1f2b", "txt": "#e8eaed",
              "dim": "#9aa4b2", "line": "rgba(255,255,255,.14)",
              "pri": "#5b9bd5", "btn": "#2f6fae"},
    "light": {"bg": "#ffffff", "bg2": "#f2f5f9", "txt": "#1a1a1a",
              "dim": "#5f6b7a", "line": "rgba(0,0,0,.12)",
              "pri": "#1f4e79", "btn": "#1f4e79"},
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

  /* ---------- ปุ่ม ----------
     ต้องกำหนดเองทั้งหมด เพราะ Streamlit ใช้สีจาก config.toml ซึ่งตั้งเป็นธีมมืด
     พอผู้ใช้สลับเป็นธีมสว่าง ปุ่มยังเป็นกล่องสีเข้มตัวหนังสือสีเข้ม = มองไม่เห็น
     เลือกเจาะจงหลายชื่อ เพราะ Streamlit เปลี่ยนชื่อ data-testid ตามรุ่น */
  .stButton > button,
  .stDownloadButton > button,
  [data-testid="stBaseButton-secondary"],
  [data-testid="stBaseButton-secondaryFormSubmit"],
  [data-testid="stDownloadButton"] button {{
      background-color:{c['bg2']} !important;
      color:{c['txt']} !important;
      border:1px solid {c['line']} !important;
      font-weight:600;
      transition:border-color .12s, background-color .12s;
  }}
  .stButton > button *,
  .stDownloadButton > button *,
  [data-testid="stBaseButton-secondary"] * {{ color:{c['txt']} !important; }}

  .stButton > button:hover,
  .stDownloadButton > button:hover,
  [data-testid="stBaseButton-secondary"]:hover {{
      border-color:{c['pri']} !important;
      background-color:{c['pri']}22 !important;
  }}

  /* ปุ่มหลัก — พื้นสีเน้น ตัวหนังสือขาวเสมอทั้งสองธีม */
  .stButton > button[kind="primary"],
  [data-testid="stBaseButton-primary"],
  [data-testid="stBaseButton-primaryFormSubmit"] {{
      background-color:{c['btn']} !important;
      color:#ffffff !important;
      border:1px solid {c['btn']} !important;
  }}
  .stButton > button[kind="primary"] *,
  [data-testid="stBaseButton-primary"] * {{ color:#ffffff !important; }}
  .stButton > button[kind="primary"]:hover,
  [data-testid="stBaseButton-primary"]:hover {{ opacity:.88; }}

  /* ปุ่มที่กดไม่ได้ — ต้องดูจางแต่ยังอ่านออก */
  .stButton > button:disabled,
  .stButton > button:disabled * {{
      opacity:.45 !important; color:{c['dim']} !important; }}

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
  .tw {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
  .chart {{ text-align:center; margin:.4rem 0 .8rem; }}

  /* ---------- การ์ดหน้าแรก ---------- */
  .home {{ display:grid; gap:.9rem;
          grid-template-columns:repeat(auto-fit, minmax(270px, 1fr)); }}
  .card {{ border:1px solid {c['line']}; border-radius:.7rem; padding:1rem 1.1rem;
          background:{c['bg2']}; height:100%; }}
  .card .ic {{ font-size:1.6rem; line-height:1; }}
  .card .ti {{ color:{c['txt']}; font-size:1.05rem; font-weight:700;
              margin:.4rem 0 .25rem; }}
  .card .de {{ color:{c['dim']}; font-size:.86rem; line-height:1.5; }}
  .card .st {{ color:{c['pri']}; font-size:.8rem; font-weight:700;
              margin-top:.5rem; }}

  /* ---------- จอแคบ (มือถือ) ---------- */
  /*
     ปัญหาที่แก้บนมือถือ
       1. ขอบซ้ายขวา 1.2rem กินพื้นที่ไปมากเมื่อจอกว้างแค่ 390px
       2. ตัวเลขในการ์ด 1.3rem ทำให้ตัวเลข 6 หลักตกบรรทัด
       3. ปุ่มเตี้ยเกินกว่าจะกดด้วยนิ้วโป้งได้แม่น (มาตรฐานคือสูงอย่างน้อย 44px)
       4. ตารางเลื่อนซ้ายขวาแล้วหัวตารางหาย ไม่รู้ว่าตัวเลขคือคอลัมน์อะไร
  */
  @media (max-width: 640px) {{
      .block-container {{ padding-left:.6rem !important;
                         padding-right:.6rem !important;
                         padding-top:.6rem !important;
                         max-width:100vw !important; }}
      .mc {{ padding:.5rem .6rem; }}
      .mc .v {{ font-size:1.05rem; }}
      .mc .k {{ font-size:.72rem; }}
      /* ปุ่มต้องสูงพอให้นิ้วกดโดนแน่ ๆ */
      .stButton > button {{ min-height:2.7rem; font-size:.95rem; }}
      .t {{ font-size:.82rem; }}
      .t td, .t th {{ padding:.3rem .45rem !important; }}
      /* ตรึงคอลัมน์แรก (ชื่อหุ้น) ไว้ตอนเลื่อนซ้ายขวา
         ถ้าไม่ตรึง พอเลื่อนไปดูคอลัมน์ขวาจะไม่รู้ว่าแถวนี้คือหุ้นตัวไหน */
      .t tbody td:first-child, .t thead th:first-child {{
          position:sticky; left:0; z-index:1;
          background:{c['bg']} !important; }}
      .t tbody tr:nth-child(even) td:first-child {{
          background:{c['bg2']} !important; }}
      .home {{ grid-template-columns:1fr; }}
      h1 {{ font-size:1.5rem !important; }}
      h2 {{ font-size:1.25rem !important; }}
      h3 {{ font-size:1.1rem !important; }}
  }}
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
    from report import analyze_all, extras, render_pdf
    import tempfile
    data, S, R, v, b = analyze_all(ticker, wacc=wacc, g1=g1, rf=rf,
                                   mos=mos, refresh=refresh)
    # ต้องเรียก extras ด้วย ไม่งั้น PDF จะขาดหัวข้อคำแนะนำ พยากรณ์
    # ความเสี่ยง คุณภาพกิจการ และข่าว — ซึ่งเป็นครึ่งหนึ่งของรายงาน
    ext = extras(data, R, v, b, rf=rf)
    with tempfile.TemporaryDirectory() as td:
        p = render_pdf(data, S, R, v, b, out_dir=td, ext=ext)
        return Path(p).read_bytes(), Path(p).name


def show_chart(b64, empty_msg="ไม่มีข้อมูลเพียงพอสำหรับกราฟนี้", width=980):
    """
    แสดงกราฟด้วยความกว้างคงที่ ไม่ยืดเต็มจอ

    ทำไมไม่ใช้ use_container_width=True :
    หน้าเว็บกว้างได้ถึง 1900px ถ้ายืดกราฟเต็มความกว้าง ตัวหนังสือในกราฟ
    (ซึ่งถูกวาดด้วยขนาดคงที่ตอนสร้างรูป) จะถูกขยายจนดูเบลอและใหญ่เกินสัดส่วน
    980px ตรงกับขนาดที่ matplotlib วาดไว้จริง จึงคมที่สุด
    """
    if b64:
        # ---- ทำไมไม่ใช้ width=980 ตรง ๆ แล้ว ----
        #
        # จอมือถือกว้างราว 390px เมื่อสั่งรูปกว้าง 980px
        # เบราว์เซอร์จะทำให้ทั้งหน้าเลื่อนซ้ายขวาได้ ซึ่งพังทั้งหน้าไม่ใช่แค่กราฟ
        #
        # ใส่ไว้ในกล่องที่จำกัดความกว้างไม่ให้เกินทั้ง 980px และไม่เกินจอ
        # บนคอมได้ 980px คมเหมือนเดิม บนมือถือย่อพอดีจอ ไม่ล้น
        st.markdown(
            f"<div class='chart'><img src='data:image/png;base64,{b64}' "
            f"style='max-width:min({width}px, 100%);width:100%;height:auto;'/>"
            "</div>", unsafe_allow_html=True)
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
 .t th { padding:.35rem .75rem; text-align:right; font-weight:600; white-space:nowrap; }
 .t th.l, .t td.l { text-align:left; }
 .t td { padding:.3rem .75rem; text-align:right; white-space:nowrap; }
 /* ตารางแคบ — กว้างเท่าเนื้อหาจริง ไม่ยืดเต็มจอ
    ใช้กับตารางไม่กี่คอลัมน์ เช่น ประวัติปันผล ถ้ายืดเต็มจอตัวเลขจะห่างกันจน
    สายตาลากจากคอลัมน์ซ้ายไปขวาไม่ติด อ่านผิดบรรทัดได้ง่าย */
 .fit .t { width:auto; min-width:min(420px, 100%); }
 .fit { display:block; overflow-x:auto; }
 /* ราคาต่ำกว่ามูลค่า = เขียว · สูงกว่า = แดงจาง
    ใช้สีพื้นอ่อน ๆ ไม่ใช่สีเข้ม เพื่อไม่ให้กลบตัวเลขในคอลัมน์ข้างเคียง */
 .t td.pos { color:#2e9e5b; background:rgba(46,158,91,.10); font-weight:600; }
 .t td.neg { color:#c2564f; }
 /* แถบคั่นหมวดในตารางเดียวยาว ๆ */
 .t tr.sec td { padding:.55rem .75rem .3rem .75rem; font-weight:700;
                font-size:.78rem; letter-spacing:.03em; opacity:.85;
                border-bottom:none; }
</style>
""", unsafe_allow_html=True)


def _cell(x, dec=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)) or pd.isna(x):
        return "—"
    if isinstance(x, (int, float, np.floating, np.integer)):
        # ค่าที่เล็กมากแต่ไม่ใช่ศูนย์ ต้องไม่แสดงเป็น 0.00
        # ตัวอย่าง : D/E = 0.0035 (มีหนี้นิดหน่อย) ถ้าปัดเป็น 0.00
        # จะอ่านได้ว่า "ไม่มีหนี้เลย" ซึ่งไม่จริง
        step = 10 ** (-dec)
        if 0 < abs(x) < step:
            return f"<{step:.{dec}f}" if x > 0 else f">-{step:.{dec}f}"
        return f"{x:,.{dec}f}"
    return str(x)


# เครื่องหมายนำหน้าแถว "หัวหมวด" ในตารางเดียวยาว ๆ
# ต้องตรงกับ screener.SECTION_MARK — ไม่ import ตรง ๆ เพราะ app.py จงใจ
# เลื่อนการโหลด screener ไปทำตอนเข้าโหมดนั้นจริง เพื่อให้หน้าแรกขึ้นเร็ว
SECTION_MARK = "§ "


def html_table(df: pd.DataFrame, first_col="รายการ", dec=2, trim_year=True,
               max_height=None, link_cols=(), link_target="_blank",
               link_headers=False, sort_cols=(),
               cur_sort=None, cur_asc=True, fit=False, left_cols=(),
               dec_cols=None, sign_cols=(), sign_mask=None, dec_rows=None):
    """
    แสดง DataFrame เป็นตาราง HTML

    fit        : True = ตารางกว้างเท่าเนื้อหา ไม่ยืดเต็มจอ
                 ใช้กับตารางไม่กี่คอลัมน์ (ปันผล แตกพาร์ ช่วงราคา)
    left_cols  : คอลัมน์ที่ให้ชิดซ้าย — ใช้กับวันที่และข้อความ
                 ตัวเลขชิดขวาเพื่อให้หลักตรงกันอ่านง่าย
                 แต่วันที่ชิดขวาจะดูเหมือนตัวเลขจนสับสน
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
    klass = "tw fit" if fit else "tw"
    h = [f"<div class='{klass}'{style}><table class='t'><thead><tr>"
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
        elif link_headers:
            # ---- หัวตารางเป็นชื่อหุ้น กดแล้วไปวิเคราะห์รายตัว ----
            #
            # ใช้กับตารางเปรียบเทียบ ซึ่งวางหุ้นเป็น "คอลัมน์" ไม่ใช่ "แถว"
            # link_cols ใช้ไม่ได้ เพราะมันทำลิงก์ให้เฉพาะค่าในช่องข้อมูล
            h.append(f"<th><a class='tk' target='_blank' rel='noopener' "
                     f"href='?t={quote(str(c))}'>{c}</a></th>")
        else:
            h.append(f"<th{' class=l' if c in left_cols else ''}>{c}</th>")
    h.append("</tr></thead><tbody>")
    ncol = len(df.columns) + 1
    for name in df.index:
        # แถวหัวหมวด — วาดเป็นแถบเดียวพาดทั้งความกว้าง ไม่มีช่องข้อมูล
        # ทำให้ตารางยาว ๆ อ่านเป็นเรื่อง ๆ ได้ โดยหัวตารางยังตรึงอยู่บนสุดที่เดียว
        if str(name).startswith(SECTION_MARK):
            h.append(f"<tr class='sec'><td class='l' colspan='{ncol}'>"
                     f"{str(name)[len(SECTION_MARK):]}</td></tr>")
            continue
        h.append(f"<tr><td class='l'>{name}</td>")
        for c in df.columns:
            # จำนวนทศนิยมรายคอลัมน์ — คะแนนกับจำนวนปีเป็นจำนวนเต็ม
            # ถ้าแสดง 40.00 หรือ 4.00 จะดูเหมือนค่าที่วัดละเอียด ทั้งที่เป็นการนับ
            # ลำดับความสำคัญ : ทศนิยมรายบรรทัด > รายคอลัมน์ > ค่าเริ่มต้น
            # บรรทัดต่อหุ้นต้องการทศนิยม 2 ตำแหน่ง ขณะที่ทั้งตารางใช้ 0
            _d = (dec_rows or {}).get(name, (dec_cols or {}).get(c, dec))
            val = _cell(df.loc[name, c], _d)
            if c in left_cols:
                h.append(f"<td class='l'>{val}</td>")
                continue
            # คอลัมน์ที่ "บวก = ราคาต่ำกว่ามูลค่า" ให้ระบายสีตามเครื่องหมาย
            # ใส่สัญลักษณ์ ▲ ควบคู่กับสีเสมอ ไม่สื่อด้วยสีอย่างเดียว
            # เพราะคนตาบอดสีเขียว-แดงจะอ่านตารางไม่ได้เลยถ้าใช้แต่สี
            # sign_mask = แถวที่ "เชื่อถือพอจะระบายสีเขียว" เท่านั้น
            # แถวที่ไม่ผ่านยังแสดงตัวเลขจริงครบ แค่ไม่ได้รับการเน้น
            ok_sign = True if sign_mask is None else bool(sign_mask.get(name, False))
            if c in sign_cols and val != "—" and ok_sign:
                try:
                    fv = float(df.loc[name, c])
                    if fv > 0:
                        h.append(f"<td class='pos'>▲ {val}</td>")
                        continue
                    if fv < 0:
                        h.append(f"<td class='neg'>{val}</td>")
                        continue
                except (TypeError, ValueError):
                    pass
            if c in link_cols and val != "—":
                # ---- เปิดแท็บเดิม หรือแท็บใหม่ ----
                #
                # การกดลิงก์ทำให้เบราว์เซอร์โหลดหน้าใหม่เสมอ = session เดิมถูกทิ้ง
                #
                #   ตารางที่อ่านจากไฟล์ (Strong Buy · ปันผล · ผลคัดกรองที่บันทึกไว้)
                #     -> เปิดแท็บเดิมได้ เพราะกดกลับมาแล้วระบบอ่านไฟล์ใหม่ให้เอง
                #
                #   ตารางที่คำนวณสด ๆ ในหน่วยความจำ (ผลวิเคราะห์ลึกรอบนี้)
                #     -> ต้องเปิดแท็บใหม่ ไม่งั้นผลที่รอมาหลายนาทีหายทันที
                _tgt = ("_self" if link_target == "_self"
                        else "_blank' rel='noopener")
                val = (f"<a class='tk' target='{_tgt}' "
                       f"href='?t={str(df.loc[name, c]).strip()}'>{val}</a>")
            h.append(f"<td>{val}</td>")
        h.append("</tr>")
    h.append("</tbody></table></div>")
    st.markdown("".join(h), unsafe_allow_html=True)


def kv_table(pairs, dec=2, fit=False):
    """ตารางสองคอลัมน์ : ชื่อรายการ / ค่า"""
    rows = "".join(
        f"<tr><td class='l'>{k}</td><td><b>{_cell(v, dec)}</b></td></tr>"
        for k, v in pairs)
    st.markdown(f"<div class='{'tw fit' if fit else 'tw'}'><table class='t'>{rows}"
                "</table></div>", unsafe_allow_html=True)


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

HOME = "🏠 หน้าแรก"

# อ้างชื่อโหมดด้วยตัวแปร ไม่ใช่หมายเลขในรายการ
# เพราะทุกครั้งที่เพิ่มหน้าใหม่ หมายเลขจะเลื่อน แล้วปุ่มเดิมจะพาไปผิดหน้า
# (เคยเกิดมาแล้วตอนเพิ่มหน้าปันผล)
M_ONE = "วิเคราะห์รายตัว"
M_SCREEN = "คัดกรองทั้งตลาด"
M_DEEP = "วิเคราะห์ลึกหลายตัว"

MODES = [HOME, "วิเคราะห์รายตัว", "คัดกรองทั้งตลาด", "วิเคราะห์ลึกหลายตัว",
         "เปรียบเทียบ 2–10 ตัว", "🏆 รายการ Strong Buy", "💰 หุ้นปันผล"]

# คำอธิบายสั้น ๆ ใต้แต่ละเมนู — ช่วยให้เลือกถูกโดยไม่ต้องลองกดทีละอัน
MODE_HELP = {
    HOME: "รวมทุกความสามารถไว้ที่เดียว",
    "วิเคราะห์รายตัว": "งบ · อัตราส่วน · มูลค่า · กราฟ ของหุ้นตัวเดียว",
    "คัดกรองทั้งตลาด": "ตั้งเกณฑ์แล้วกรองหาหุ้นที่เข้าข่าย",
    "วิเคราะห์ลึกหลายตัว": "วิเคราะห์เต็มรูปแบบ 3–40 ตัวพร้อมกัน",
    "เปรียบเทียบ 2–10 ตัว": "วางตัวเลขเรียงกันให้เห็นความต่าง",
    "🏆 รายการ Strong Buy": "ผลวิเคราะห์ลึกทั้งตลาดที่ทำไว้แล้ว",
    "💰 หุ้นปันผล": "หุ้นที่ใกล้ขึ้น XD · จ่ายเท่าไร · กี่ %",
}

# จัดเมนูเป็นหัวข้อหลัก เพื่อให้หาง่ายเมื่อหน้าเพิ่มขึ้นเรื่อย ๆ
MODE_GROUPS = [
    ("", [HOME]),
    ("🔎 ค้นหาหุ้น", ["คัดกรองทั้งตลาด", "🏆 รายการ Strong Buy", "💰 หุ้นปันผล"]),
    ("📊 วิเคราะห์", ["วิเคราะห์รายตัว", "วิเคราะห์ลึกหลายตัว",
                      "เปรียบเทียบ 2–10 ตัว"]),
]

# ---------------------------------------------------------------------------
# เนื้อหาการ์ดหน้าแรก
#
# เขียนให้คนที่ไม่เคยเห็นระบบนี้มาก่อนอ่านแล้วรู้ทันทีว่า
# "หน้านี้ตอบคำถามอะไรให้ฉันได้"
# ไม่ใช่ชื่อฟังก์ชันทางเทคนิคที่ต้องเดาเอาเอง
# ---------------------------------------------------------------------------
CARDS = [
    {"mode": "🏆 รายการ Strong Buy", "icon": "🏆",
     "title": "หุ้นน่าสนใจที่วิเคราะห์ไว้แล้ว",
     "desc": "ดูผลวิเคราะห์เชิงลึกทั้งตลาดที่ทำไว้ล่วงหน้า "
             "เรียงตามคะแนน กรองตามคำแนะนำและความน่าเชื่อถือได้",
     "ask": "อยากรู้ว่าตอนนี้มีหุ้นตัวไหนคะแนนดีบ้าง"},
    {"mode": "💰 หุ้นปันผล", "icon": "💰",
     "title": "หุ้นที่ใกล้จ่ายปันผล",
     "desc": "ตัวไหนใกล้ขึ้น XD · จ่ายกี่บาทต่อหุ้น · คิดเป็นกี่ % "
             "ของราคาวันนี้ · ปีหนึ่งจ่ายกี่ครั้ง",
     "ask": "อยากได้หุ้นปันผล ตัวไหนกำลังจะจ่าย"},
    {"mode": "คัดกรองทั้งตลาด", "icon": "🔎",
     "title": "คัดกรองหาหุ้นตามเกณฑ์",
     "desc": "ตั้งเงื่อนไขเอง เช่น P/E ต่ำกว่า 15 · ROE เกิน 15% · "
             "หนี้ต่ำ แล้วให้ระบบกรองทั้งตลาดให้",
     "ask": "อยากหาหุ้นที่เข้าเกณฑ์ของตัวเอง"},
    {"mode": "วิเคราะห์รายตัว", "icon": "📊",
     "title": "เจาะลึกหุ้นทีละตัว",
     "desc": "งบการเงินย้อนหลัง · อัตราส่วน 150+ ตัว · การประเมินมูลค่า "
             "หลายวิธี · กราฟ · ดาวน์โหลดรายงาน PDF",
     "ask": "รู้ชื่อหุ้นอยู่แล้ว อยากดูละเอียด"},
    {"mode": "เปรียบเทียบ 2–10 ตัว", "icon": "⚖️",
     "title": "เทียบหุ้นหลายตัวพร้อมกัน",
     "desc": "วางตัวเลขเรียงข้างกันให้เห็นว่าตัวไหนดีกว่าตรงไหน "
             "54 หัวข้อใน 9 หมวด",
     "ask": "ตัดสินใจไม่ได้ว่าจะเลือกตัวไหน"},
    {"mode": "วิเคราะห์ลึกหลายตัว", "icon": "🔬",
     "title": "วิเคราะห์ลึกชุดที่สนใจ",
     "desc": "เลือกหุ้น 3–40 ตัวแล้วให้ระบบวิเคราะห์เต็มรูปแบบทีเดียว "
             "พร้อมจัดอันดับให้",
     "ask": "มีรายชื่อหุ้นในใจอยู่แล้ว อยากวิเคราะห์ทั้งชุด"},
]

# ---------------------------------------------------------------------------
# รับคำสั่ง "กดชื่อหุ้นในตารางแล้วมาวิเคราะห์รายตัว"
#
# ลิงก์ในตารางจะพาไปที่ URL เดิมแต่ต่อท้ายด้วย ?t=AAPL
# ตรงนี้อ่านค่านั้น สลับโหมดให้ แล้วล้างพารามิเตอร์ทิ้ง
# (ต้องล้าง มิฉะนั้นกดปุ่มอื่นทีหลังจะเด้งกลับมาหุ้นตัวเดิมตลอด)
# ---------------------------------------------------------------------------
_qp = st.query_params
if "t" in _qp:
    st.session_state["mode"] = M_ONE
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

# ---------------------------------------------------------------------------
# เมนูด้านซ้าย
#
# ใช้ปุ่มแทน radio โดยตั้งใจ เพราะ radio วางหัวข้อคั่นกลางไม่ได้
# และปุ่มทำงานผ่านการเชื่อมต่อเดิม ไม่โหลดหน้าใหม่ ผลที่ทำไว้จึงไม่หาย
# ---------------------------------------------------------------------------
def _go_mode(m):
    st.session_state["mode"] = m


with st.sidebar:
    st.markdown("## Equity Research AI Pro")
    st.caption("วิเคราะห์หุ้นจากงบการเงินจริง")
    st.divider()

    _cur = st.session_state.get("mode", MODES[0])
    for _gname, _items in MODE_GROUPS:
        if _gname:
            st.markdown(f"**{_gname}**")
        for _m in _items:
            st.button(_m, key=f"nav_{_m}", use_container_width=True,
                      type="primary" if _m == _cur else "secondary",
                      help=MODE_HELP.get(_m), on_click=_go_mode, args=(_m,))
        st.write("")

    st.divider()

    # ---- ข้อกำหนดการใช้งาน ----
    #
    # เว็บนี้เปิดสาธารณะ ใครก็เข้าได้ จึงต้องมีข้อความนี้ให้เห็นได้ทุกหน้า
    # ไม่ใช่แค่หน้าแรก เพราะคนอาจเข้ามาที่หน้าใดหน้าหนึ่งโดยตรงจากลิงก์ที่แชร์กัน
    #
    # ประเทศไทยกำกับ "การให้คำแนะนำการลงทุน" โดย ก.ล.ต.
    # เครื่องมือคำนวณเพื่อการศึกษาไม่เข้าข่าย แต่ต้องระบุให้ชัดว่าไม่ใช่คำแนะนำ
    # และไม่ได้ชักชวนให้ซื้อขาย
    with st.expander("⚠️ ข้อกำหนดการใช้งาน"):
        st.markdown(
            "**ไม่ใช่คำแนะนำการลงทุน**\n\n"
            "เว็บนี้เป็นเครื่องมือคำนวณและสรุปตัวเลขจากงบการเงินสาธารณะ "
            "เพื่อการศึกษาเท่านั้น ไม่ใช่การให้คำแนะนำ ไม่ใช่การชักชวน "
            "ให้ซื้อขายหลักทรัพย์ใด ๆ\n\n"
            "ผู้จัดทำไม่ได้เป็นผู้แนะนำการลงทุนที่ได้รับความเห็นชอบจาก ก.ล.ต.\n\n"
            "**แหล่งข้อมูล** — SEC EDGAR และ Yahoo Finance "
            "ซึ่งอาจมีความคลาดเคลื่อน ผู้ใช้ควรตรวจสอบกับงบการเงินฉบับจริง\n\n"
            "**ความเสี่ยง** — การลงทุนมีความเสี่ยง ผลการดำเนินงานในอดีต "
            "ไม่ได้รับประกันผลในอนาคต ผู้ลงทุนควรตัดสินใจด้วยตนเอง "
            "หรือปรึกษาผู้แนะนำการลงทุนที่ได้รับใบอนุญาต")
    st.caption("⚠️ ไม่ใช่คำแนะนำการลงทุน — เครื่องมือคำนวณเพื่อการศึกษา")

MODE = st.session_state.get("mode", MODES[0])
if MODE not in MODES:
    MODE = MODES[0]
    st.session_state["mode"] = MODE

# ---------------------------------------------------------------------------
# แถบหัวหน้า
#
# บนมือถือ Streamlit จะพับเมนูซ้ายเก็บไว้หลังปุ่มขีดสามขีดเสมอ
# ซึ่งผู้ใช้ใหม่มักหาไม่เจอ จึงต้องมีปุ่มกลับหน้าแรกอยู่ในหน้าตลอด
# หน้าแรกเป็นทางเข้าถึงทุกอย่างอยู่แล้ว มีปุ่มเดียวนี้ก็ไม่มีทางหลงทาง
# ---------------------------------------------------------------------------
if MODE != HOME:
    tb1, tb2 = st.columns([1, 5])
    tb1.button("🏠 หน้าแรก", use_container_width=True,
               on_click=_go_mode, args=(HOME,),
               help="กลับไปดูว่าระบบทำอะไรได้บ้าง")
    with tb2:
        st.markdown(f"#### {MODE}")
        st.caption(MODE_HELP.get(MODE, ""))


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
# โหมดรายการ Strong Buy — อ่านผลที่วิเคราะห์ลึกไว้แล้ว
# ---------------------------------------------------------------------------
def sort_controls(df, key: str, default=None, asc=False, exclude=()):
    """
    แถบเลือกว่าจะเรียงตารางตามคอลัมน์ไหน — คืน DataFrame ที่เรียงแล้ว

    ทำไมไม่ใช้ "กดที่หัวตาราง"
    ---------------------------
    การกดหัวตารางต้องทำเป็นลิงก์ `<a href="?sort=...">` ซึ่งทำให้เบราว์เซอร์
    **โหลดหน้าใหม่ทั้งหน้า** = Streamlit เริ่ม session ใหม่ = ผลคัดกรองที่ทำไว้หายหมด
    (เป็นบั๊กเดียวกับที่เคยทำให้กดดูหุ้นรายตัวแล้วกลับมาต้องคัดกรองใหม่)

    ตัวควบคุมแบบนี้ทำงานผ่านการเชื่อมต่อเดิม ไม่โหลดหน้าใหม่ ข้อมูลจึงไม่หาย
    """
    cols = [c for c in df.columns if c not in exclude]
    if not cols:
        return df

    if default not in cols:
        default = cols[0]

    c1, c2 = st.columns([3, 2])
    col = c1.selectbox("เรียงตาม", cols, index=cols.index(default),
                       key=f"sortcol_{key}")
    order = c2.radio("ลำดับ", ["มาก → น้อย", "น้อย → มาก"],
                     index=0 if not asc else 1,
                     horizontal=True, key=f"sortdir_{key}",
                     help="ข้อความจะเรียงตามตัวอักษร ตัวเลขเรียงตามค่า")

    s = df[col]
    num = pd.to_numeric(s, errors="coerce")
    # ใช้การเรียงแบบตัวเลขเมื่อคอลัมน์นั้นเป็นตัวเลขเกินครึ่ง
    # ถ้าเรียงตัวเลขแบบตัวอักษร 100 จะมาก่อน 9 ซึ่งผิด
    if num.notna().sum() >= max(1, len(s) // 2):
        keyser = num
    else:
        keyser = s.astype(str)

    ascending = (order == "น้อย → มาก")
    out = df.assign(_k=keyser).sort_values(
        "_k", ascending=ascending, na_position="last").drop(columns=["_k"])
    return out


# ---------------------------------------------------------------------------
# แผงสั่งอัปเดตผลวิเคราะห์ลึก
#
# หลักคิด : หน้าเว็บ **ไม่วิเคราะห์เอง**
# มันแค่สั่งให้เครื่องเปิดโปรแกรมแยกออกไปทำ แล้วคอยอ่านความคืบหน้า
# เพราะงานนี้ใช้เวลาหลายชั่วโมง ถ้าทำในหน้าเว็บตรง ๆ จะค้างและปิดแท็บไม่ได้เลย
# ---------------------------------------------------------------------------

# หุ้นแต่ละตัวใช้เวลาวิเคราะห์ราวเท่าไร — ใช้ประมาณเวลาให้ผู้ใช้ตัดสินใจ
SEC_PER_STOCK = 30

MARKET_SIZE = {"thai": 866, "us": 10398}


def _fmt_hours(n_stocks: int) -> str:
    h = n_stocks * SEC_PER_STOCK / 3600
    if h < 1:
        return f"{h*60:.0f} นาที"
    return f"{h:.1f} ชั่วโมง"


@st.fragment(run_every=5)
def _job_progress(market: str):
    """วาดความคืบหน้าของงานที่กำลังทำ — รีเฟรชเองทุก 5 วินาที

    ใช้ fragment เพื่อให้รีเฟรชเฉพาะกล่องนี้ ไม่ต้องวาดทั้งหน้าใหม่
    ถ้าวาดทั้งหน้า ตารางหลายพันแถวจะกระพริบทุก 5 วินาที
    """
    import runner as RUN
    s = RUN.status(market)
    if not s["มีงาน"]:
        return

    log = s.get("log", "")
    pg = RUN.progress_from_log(log)
    mins = s.get("นาทีที่ผ่านไป") or 0

    if s["กำลังทำงาน"]:
        if pg:
            i, total = pg
            st.progress(min(i / max(total, 1), 1.0),
                        text=f"วิเคราะห์แล้ว {i:,} จาก {total:,} ตัว "
                             f"· ผ่านไป {mins:.0f} นาที")
        else:
            st.progress(0.0, text=f"กำลังเตรียมรายชื่อ · ผ่านไป {mins:.0f} นาที")
        st.caption("ปิดแท็บนี้ได้ งานจะเดินต่อเอง — กลับมาเปิดใหม่แล้วดูได้")
    else:
        done = "git push" in log and "error" not in log.lower()
        st.success(f"งานรอบล่าสุดจบแล้ว (ใช้เวลา {mins:.0f} นาที)"
                   + ("  ส่งขึ้นเว็บเรียบร้อย" if done else ""))

    with st.expander("ดูรายละเอียดที่โปรแกรมกำลังทำ", expanded=False):
        st.code(log or "(ยังไม่มีข้อความ)", language=None)


def deep_update_panel(market: str):
    """ปุ่มสั่งอัปเดตผลวิเคราะห์ลึกแบบกดเอง"""
    import runner as RUN
    import tools_deep_scan as DS

    total = MARKET_SIZE.get(market, 0)
    name_th = "หุ้นไทย" if market == "thai" else "หุ้นสหรัฐ"

    if not RUN.is_local():
        # อยู่บนเว็บ — สั่งดึงข้อมูลไม่ได้ ต้องบอกให้ชัดว่าทำไม
        with st.expander(f"⚙️ อัปเดตผลวิเคราะห์ {name_th}", expanded=False):
            st.warning(
                "**สั่งอัปเดตจากหน้าเว็บนี้ไม่ได้**  \n"
                "Yahoo ปิดกั้นการดึงข้อมูลจากเครื่องของศูนย์ข้อมูล "
                "(ซึ่งเว็บนี้ทำงานอยู่) และเครื่องจะถูกล้างทุกครั้งที่อัปเดตโค้ด "
                "งานที่รันค้างไว้จะหายหมด\n\n"
                "**ให้เปิดโปรแกรมบน MacBook แล้วกดปุ่มจากตรงนั้นแทน** :\n\n"
                "```\neq\nstreamlit run app.py\n```\n"
                "หรือสั่งจาก Terminal ตรง ๆ :\n\n"
                f"```\npython3 tools_deep_scan.py --{market} --all "
                f"--hours 6 --refresh-days 3\n```")
        return

    st.markdown("")
    with st.expander(f"⚙️ อัปเดตผลวิเคราะห์ {name_th}  (กดเอง)", expanded=False):
        s = RUN.status(market)
        busy = s["กำลังทำงาน"]

        c1, c2 = st.columns([3, 2])
        scope_lbl = c1.radio(
            "จะอัปเดตแค่ไหน",
            [f"ทั้งตลาด {total:,} ตัว",
             "เฉพาะตัวที่ผลเก่าแล้ว",
             "เฉพาะตัวคะแนนสูง 300 ตัวแรก"],
            key=f"scope_{market}", disabled=busy,
            captions=[
                f"ทำต่อจากที่ค้างไว้ ตัวที่เคยทำแล้วจะไม่ทำซ้ำ "
                f"(ถ้าเริ่มจากศูนย์ใช้เวลาราว {_fmt_hours(total)})",
                "ตัวที่วิเคราะห์ไว้เกินจำนวนวันที่กำหนด จะถูกดึงมาทำใหม่",
                "คัดกรองเร็วทั้งตลาดก่อน แล้ววิเคราะห์ลึกเฉพาะหัวตาราง"])

        hours = c2.slider("หยุดเองเมื่อครบกี่ชั่วโมง", 0.5, 12.0, 6.0, 0.5,
                          key=f"hrs_{market}", disabled=busy,
                          help="หมดเวลาแล้วโปรแกรมจะบันทึกผลที่ทำได้แล้วหยุด "
                               "กดใหม่รอบหน้าจะทำต่อจากจุดเดิม ไม่เริ่มใหม่")
        days = c2.number_input("ถือว่าผลเก่าเมื่อเกินกี่วัน", 1, 30, 3,
                               key=f"days_{market}", disabled=busy)
        push = c2.checkbox("เสร็จแล้วส่งขึ้นเว็บให้เลย", value=True,
                           key=f"push_{market}", disabled=busy,
                           help="commit + push ให้อัตโนมัติ "
                                "เพื่อให้เปิดดูจากมือถือได้")

        scope = ("refresh" if scope_lbl.startswith("เฉพาะตัวที่ผลเก่า")
                 else "top" if scope_lbl.startswith("เฉพาะตัวคะแนน") else "all")

        # ---- บอกล่วงหน้าว่ารอบนี้จะทำกี่ตัว ----
        # ผู้ใช้ควรรู้ก่อนกดว่าจะได้อะไร ไม่ใช่กดแล้วรอลุ้น
        try:
            uni = (list(__import__("tickers").thai_universe()) if market == "thai"
                   else list(__import__("tickers").us_tickers().keys()))
            q = DS.build_queue(uni, market,
                               refresh_days=days if scope == "refresh" else None)
            if scope == "top":
                st.caption("จะคัดกรองเร็วทั้งตลาดก่อน แล้ววิเคราะห์ลึก 300 ตัวแรก")
            elif not q["todo"]:
                st.success("ครบและยังไม่ถึงรอบอัปเดต — ยังไม่ต้องรันก็ได้")
            else:
                st.caption(
                    f"รอบนี้มีคิว **{len(q['todo']):,} ตัว** "
                    f"(ทำไปแล้ว {q['ทำแล้ว']:,} จาก {q['ทั้งหมด']:,}) "
                    f"· ทำจนครบใช้เวลาราว {_fmt_hours(len(q['todo']))} "
                    f"· งบเวลารอบนี้ {hours:g} ชม. "
                    f"จะได้ราว {int(hours*3600/SEC_PER_STOCK):,} ตัว")
        except Exception as e:
            st.caption(f"(ประมาณจำนวนคิวไม่ได้ : {type(e).__name__})")

        b1, b2 = st.columns([1, 1])
        if b1.button("▶️ เริ่มอัปเดต", type="primary", disabled=busy,
                     use_container_width=True, key=f"go_{market}"):
            RUN.start(market, scope=scope, hours=hours,
                      refresh_days=days if scope == "refresh" else None,
                      top=300, push=push)
            st.rerun()
        if b2.button("⏹ หยุดงานนี้", disabled=not busy,
                     use_container_width=True, key=f"stop_{market}",
                     help="ผลที่ทำไปแล้วไม่หาย รอบหน้าทำต่อจากจุดที่ค้าง"):
            RUN.stop(market)
            st.rerun()

        _job_progress(market)


def deep_changes_panel(market: str):
    """แสดงว่ารอบล่าสุดมีอะไรเปลี่ยนไปบ้าง"""
    import tools_deep_scan as DS
    try:
        ch, cmeta = DS.load_changes(market)
    except Exception:
        return
    if ch is None or ch.empty:
        return

    lv = ch[ch["การเปลี่ยนแปลง"].str.startswith(("⬆️", "⬇️"))]
    pr = ch[ch["การเปลี่ยนแปลง"].str.startswith(("💰", "💸"))]
    nw = ch[ch["การเปลี่ยนแปลง"].str.startswith("🆕")]

    head = (f"🔔 เปลี่ยนจากรอบก่อน {len(ch):,} ตัว"
            f"   —   คำแนะนำเปลี่ยนระดับ {len(lv):,} · "
            f"ราคาขยับแรง {len(pr):,} · เข้าใหม่ {len(nw):,}")

    with st.expander(head, expanded=bool(len(lv))):
        st.caption(f"เทียบกับผลรอบก่อนหน้า · บันทึกเมื่อ "
                   f"{cmeta.get('บันทึกเมื่อ','-')[:16]}  \n"
                   "**คำแนะนำเปลี่ยนระดับ** คือสิ่งที่ควรดูก่อน — "
                   "ราคาขยับเฉย ๆ อาจเป็นความผันผวนปกติ")
        pick = st.radio("ดูกลุ่มไหน",
                        [f"เปลี่ยนระดับ ({len(lv):,})",
                         f"ราคาขยับแรง ({len(pr):,})",
                         f"เข้าใหม่ ({len(nw):,})",
                         f"ทั้งหมด ({len(ch):,})"],
                        horizontal=True, key=f"chpick_{market}")
        sel = (lv if pick.startswith("เปลี่ยนระดับ") else
               pr if pick.startswith("ราคาขยับ") else
               nw if pick.startswith("เข้าใหม่") else ch)
        if sel.empty:
            st.info("ไม่มีรายการในกลุ่มนี้")
            return
        show = sel.copy()
        show.index = [str(i) for i in range(1, len(show) + 1)]
        html_table(show, first_col="ลำดับ", trim_year=False, fit=True,
                   max_height=460, left_cols=("ชื่อบริษัท", "การเปลี่ยนแปลง"),
                   link_cols=("ticker",), link_target="_self",
                   sign_cols=("ส่วนลดขยับ",))


# ---------------------------------------------------------------------------
# หน้าแรก — บอกให้คนที่เพิ่งเข้ามารู้ว่าเว็บนี้ทำอะไรได้บ้าง
# ---------------------------------------------------------------------------
if MODE == HOME:

    @st.cache_data(show_spinner=False, ttl=600)
    def _home_stats():
        """ตัวเลขจริงของระบบ — ใช้แสดงบนการ์ดให้เห็นว่ามีข้อมูลอยู่จริงแค่ไหน"""
        out = {}
        try:
            import tools_deep_scan as _DS
            n = 0
            for mk in ("thai", "us"):
                df, _ = _DS.load_results(mk)
                if df is not None and not df.empty:
                    n += int(df["ปัญหา"].eq("").sum())
            out["deep"] = n
        except Exception:
            out["deep"] = 0
        try:
            import dividends as _DV
            n = 0
            for mk in ("thai", "us"):
                df, _ = _DV.load(mk)
                if df is not None and not df.empty:
                    n += len(_DV.upcoming(df, days=45))
            out["div"] = n
        except Exception:
            out["div"] = 0
        try:
            import archive as _AR
            s_ = _AR.stats()
            out["arc_val"] = int(s_["จำนวนค่า"].sum()) if len(s_) else 0
        except Exception:
            out["arc_val"] = 0
        return out

    HS = _home_stats()

    st.markdown("# Equity Research AI Pro")
    st.markdown("#### วิเคราะห์หุ้นจากงบการเงินจริง ไม่ใช่จากการคาดเดา")
    st.markdown(
        f"หุ้นไทย **866 ตัว** · หุ้นสหรัฐ **10,398 ตัว** · "
        f"งบการเงินในคลัง **{HS['arc_val']:,} ค่า**  \n"
        "ตัวเลขทุกตัวคำนวณด้วยโปรแกรม ตรวจย้อนกลับได้ว่ามาจากบรรทัดไหนในงบ")

    st.divider()

    # ---------- ช่องค้นหา — ทางลัดที่คนส่วนใหญ่อยากได้ ----------
    st.markdown("##### เริ่มจากเลือกหุ้นที่สนใจ")

    # ---- ใช้ selectbox เสมอ ไม่ใช่ text_input ----
    #
    # text_input ทำให้เบราว์เซอร์เสนอ "ข้อมูลที่เคยกรอก" ขึ้นมาเอง
    # ซึ่งบนมือถือจะดึงรายชื่อจากสมุดโทรศัพท์มาแสดง — ไม่เกี่ยวกับหุ้นเลย
    # และไม่มีรายชื่อหุ้นให้เลือก ต้องจำชื่อย่อเอาเอง
    #
    # selectbox ของ Streamlit กรองรายการให้ทันทีที่พิมพ์
    # ค้นได้ทั้งชื่อย่อและชื่อบริษัท และไม่มีการเสนอข้อมูลจากเครื่องผู้ใช้
    hc1, hc2 = st.columns([4, 1])
    with hc1:
        if OPTIONS:
            st.selectbox(
                "เลือกหุ้น", OPTIONS, index=None, key="home_pick",
                label_visibility="collapsed",
                placeholder="พิมพ์ชื่อย่อหรือชื่อบริษัท เช่น AAPL · ปตท · ธนาคาร")
        else:
            st.warning("โหลดรายชื่อหุ้นไม่สำเร็จ")

    def _go_search():
        pick = st.session_state.get("home_pick")
        if not pick:
            return
        st.session_state["jump"] = LOOKUP.get(
            pick, str(pick).split(" ")[0]).upper()
        st.session_state["mode"] = M_ONE
        st.session_state["ran"] = True

    hc2.button("วิเคราะห์", type="primary", use_container_width=True,
               on_click=_go_search, disabled=not OPTIONS)
    if OPTIONS:
        st.caption(f"ค้นหาได้ **{len(OPTIONS):,} ตัว** — "
                   "พิมพ์ตัวอักษรไม่กี่ตัวแล้วรายชื่อจะกรองให้เอง")

    st.divider()
    st.markdown("##### หรือเลือกจากสิ่งที่ระบบทำได้")

    # ---------- การ์ดความสามารถ ----------
    #
    # วาดการ์ดด้วย HTML แล้ววางปุ่มของ Streamlit ไว้ใต้การ์ด
    # เพราะปุ่มจริงใส่เข้าไปใน HTML ที่เราเขียนเองไม่ได้
    # และต้องใช้ปุ่มจริง เพราะลิงก์ธรรมดาจะทำให้โหลดหน้าใหม่ทั้งหน้า
    for i in range(0, len(CARDS), 2):
        cols = st.columns(2)
        for col, card in zip(cols, CARDS[i:i + 2]):
            with col:
                stat = ""
                if card["mode"].startswith("🏆") and HS["deep"]:
                    stat = f"วิเคราะห์ไว้แล้ว {HS['deep']:,} ตัว"
                elif card["mode"].startswith("💰") and HS["div"]:
                    stat = f"ใกล้ขึ้น XD ใน 45 วัน {HS['div']:,} ตัว"
                elif card["mode"] == M_SCREEN:
                    stat = "กรองจากทั้งตลาดได้ทันที"

                st.markdown(
                    f"<div class='card'><div class='ic'>{card['icon']}</div>"
                    f"<div class='ti'>{card['title']}</div>"
                    f"<div class='de'>{card['desc']}</div>"
                    + (f"<div class='st'>{stat}</div>" if stat else "")
                    + "</div>", unsafe_allow_html=True)
                st.button(card["ask"], key=f"card_{card['mode']}",
                          use_container_width=True,
                          on_click=_go_mode, args=(card["mode"],))
                st.write("")

    st.divider()

    with st.expander("ระบบนี้ทำงานอย่างไร"):
        st.markdown(
            "**หลักการเดียวที่ยึดตลอด — โปรแกรมคำนวณ ไม่ใช่ AI เดา**\n\n"
            "ตัวเลขการเงินทุกตัว (P/E · ROE · DCF · มูลค่าที่ประเมินได้) "
            "คำนวณด้วยโปรแกรมจากงบการเงินจริง จึงตรวจย้อนกลับได้ว่า"
            "เลขแต่ละตัวมาจากบรรทัดไหนในงบ\n\n"
            "| ขั้นตอน | ทำอะไร |\n|---|---|\n"
            "| 1. ดึงข้อมูล | หุ้นสหรัฐจาก **SEC EDGAR** ย้อนหลังถึง 15 ปี · "
            "หุ้นไทยจาก Yahoo Finance |\n"
            "| 2. คำนวณ | อัตราส่วนกว่า 150 ตัว · ประเมินมูลค่าหลายวิธี "
            "ตามกลุ่มธุรกิจ |\n"
            "| 3. ให้คะแนน | คุณภาพกิจการ · ความเสี่ยง · Buffett Score · "
            "ความน่าเชื่อถือของข้อมูลเอง |\n"
            "| 4. สรุป | รวมเป็นคะแนน 0–100 พร้อมบอกที่มาของทุกคะแนน |\n\n"
            "**ระบบบอกความไม่แน่ใจของตัวเองด้วย** — หุ้นที่มีงบย้อนหลังสั้น "
            "จะได้คะแนนความน่าเชื่อถือต่ำ และระบบจะดึงข้อสรุปเข้าหากลาง "
            "แทนที่จะฟันธงจากข้อมูลที่ไม่พอ")

    with st.expander("ข้อจำกัดที่ควรรู้ก่อนใช้"):
        st.markdown(
            "- **หุ้นไทยมีงบย้อนหลังแค่ 4 ปี** จากแหล่งข้อมูลฟรี ซึ่งไม่ครอบคลุม"
            "วัฏจักรธุรกิจหนึ่งรอบ ผลประเมินจึงเชื่อได้น้อยกว่าหุ้นสหรัฐ\n"
            "- **ส่วนลดที่สูงมากมักแปลว่าโมเดลเพี้ยน ไม่ใช่หุ้นถูก** "
            "ให้ดู `คะแนนรวม` และ `ความน่าเชื่อถือ` ประกอบเสมอ\n"
            "- **ผลเป็นภาพนิ่ง ณ วันที่วิเคราะห์** ราคาเปลี่ยนทุกวัน\n"
            "- **ระบบไม่รู้เรื่องที่ยังไม่อยู่ในงบ** เช่น ผู้บริหารลาออก "
            "คู่แข่งรายใหม่ หรือกฎหมายที่กำลังจะเปลี่ยน")

    st.error(
        "⚠️ **ไม่ใช่คำแนะนำการลงทุน**  \n"
        "เว็บนี้เป็นเครื่องมือคำนวณและสรุปตัวเลขจากงบการเงินสาธารณะเพื่อการศึกษา "
        "ไม่ใช่การให้คำแนะนำหรือชักชวนให้ซื้อขายหลักทรัพย์ "
        "และผู้จัดทำไม่ได้เป็นผู้แนะนำการลงทุนที่ได้รับความเห็นชอบจาก ก.ล.ต.  \n"
        "การลงทุนมีความเสี่ยง ผู้ลงทุนควรศึกษาข้อมูลและตัดสินใจด้วยตนเอง "
        "หรือปรึกษาผู้แนะนำการลงทุนที่ได้รับใบอนุญาตก่อนตัดสินใจทุกครั้ง")
    st.caption("ข้อมูลงบการเงินจาก SEC EDGAR และ Yahoo Finance "
               "อาจมีความคลาดเคลื่อน ควรตรวจสอบกับงบการเงินฉบับจริงก่อนใช้")
    st.stop()



# ---------------------------------------------------------------------------
# หน้าหุ้นปันผล — ตัวไหนใกล้ขึ้น XD จ่ายเท่าไร กี่ %
# ---------------------------------------------------------------------------
if MODE.startswith("💰"):
    import dividends as DV

    dmk = st.radio("ตลาด", ["🇹🇭 หุ้นไทย", "🇺🇸 หุ้นสหรัฐ"], horizontal=True,
                   key="div_market")
    dmarket = "thai" if dmk.startswith("🇹🇭") else "us"

    @st.cache_data(show_spinner=False, ttl=600)
    def _divdata(mkt):
        return DV.load(mkt)

    r1, r2 = st.columns([1, 4])
    if r1.button("🔄 โหลดข้อมูลใหม่", use_container_width=True, key="div_rf"):
        _divdata.clear()
        st.rerun()

    vdf, vmeta = _divdata(dmarket)

    if vdf is None or vdf.empty:
        st.warning(
            f"**ยังไม่มีข้อมูลปันผลของตลาด{'ไทย' if dmarket=='thai' else 'สหรัฐ'}**"
            "\n\nรันบน MacBook ก่อน (หุ้นที่เคยดึงข้อมูลแล้วจะเร็วมาก) :\n\n"
            f"```\neq\npython3 dividends.py --{dmarket} --days 60\n```\n"
            "อยากลองเร็ว ๆ ก่อนให้ใส่ `--limit 100`\n\n"
            "เสร็จแล้วส่งขึ้นเว็บ :\n\n"
            "```\ngit add data/snapshots\n"
            "git commit -m 'ข้อมูลปันผล'\ngit push\n```")
    else:
        r2.caption(f"ข้อมูล {len(vdf):,} ตัว · บันทึกเมื่อ "
                   f"{vmeta.get('บันทึกเมื่อ','-')[:16]} "
                   f"({vmeta.get('อายุ (ชม.)',0):.0f} ชม.ที่แล้ว)")

        g1, g2, g3 = st.columns([2, 2, 3])
        d_days = g1.slider("มองไปข้างหน้ากี่วัน", 7, 120, 45, 1)
        d_yld = g2.slider("ผลตอบแทนงวดนี้ขั้นต่ำ (%)", 0.0, 10.0, 0.0, 0.5)
        only_c = g3.checkbox(
            "เฉพาะที่ประกาศแล้วจริง (ไม่เอาค่าคาดการณ์)", value=False,
            help="หุ้นไทยที่ยังไม่ประกาศ ระบบจะคาดวันจากรอบการจ่ายเดิม "
                 "ซึ่งเป็นการประมาณ ไม่ใช่วันที่ยืนยัน")

        up = DV.upcoming(vdf, days=d_days, min_yield=d_yld or None,
                         only_confirmed=only_c)

        n_conf = int(up["ที่มาของวัน"].astype(str)
                     .str.contains("ประกาศ").sum()) if len(up) else 0
        m1, m2, m3, m4 = st.columns(4)
        metric_card(m1, f"ใกล้ XD ใน {d_days} วัน", f"{len(up):,} ตัว")
        metric_card(m2, "ประกาศแล้วจริง", f"{n_conf:,} ตัว", None,
                    "#1b6b3a" if n_conf else None)
        metric_card(m3, "เป็นค่าคาดการณ์", f"{len(up)-n_conf:,} ตัว", None,
                    "#c9a227" if len(up) - n_conf else None)
        _y = pd.to_numeric(up["ผลตอบแทนงวดนี้ (%)"],
                           errors="coerce") if len(up) else pd.Series(dtype=float)
        metric_card(m4, "ผลตอบแทนงวดนี้ สูงสุด",
                    f"{_y.max():.2f}%" if _y.notna().any() else "—")

        if up.empty:
            st.warning("ไม่มีหุ้นตัวใดเข้าเงื่อนไข — ลองขยายจำนวนวัน "
                       "หรือลดผลตอบแทนขั้นต่ำลง")
        else:
            cols = ["ticker", "วัน XD", "อีกกี่วัน", "ที่มาของวัน",
                    "เงินปันผล (ต่อหุ้น)", "ราคา", "ผลตอบแทนงวดนี้ (%)",
                    "ปันผลรวม 12 เดือน", "ผลตอบแทนต่อปี (%)",
                    "จ่ายกี่ครั้ง/ปี", "รอบการจ่าย",
                    "อัตราจ่ายจากกำไร (%)", "กลุ่ม", "ชื่อบริษัท"]
            show = up[[c for c in cols if c in up.columns]].copy()
            show = sort_controls(show, key=f"div_{dmarket}",
                                 default="อีกกี่วัน", asc=True)
            show.index = [str(i) for i in range(1, len(show) + 1)]
            st.caption("**กดที่ชื่อหุ้น** เพื่อเปิดวิเคราะห์รายตัวของตัวนั้น")
            html_table(show, first_col="ลำดับ", trim_year=False, fit=True,
                       max_height=620,
                       link_cols=("ticker",), link_target="_self",
                       left_cols=("วัน XD", "ที่มาของวัน", "รอบการจ่าย",
                                  "กลุ่ม", "ชื่อบริษัท"),
                       dec_cols={"อีกกี่วัน": 0, "จ่ายกี่ครั้ง/ปี": 0,
                                 "อัตราจ่ายจากกำไร (%)": 0,
                                 "ผลตอบแทนงวดนี้ (%)": 2,
                                 "ผลตอบแทนต่อปี (%)": 2})
            st.download_button("ดาวน์โหลดรายการนี้ (CSV)",
                               up.to_csv(index=False).encode("utf-8-sig"),
                               f"ปันผล_{dmarket}.csv", "text/csv")

        # ---- หุ้นที่ปันผลสม่ำเสมอและสูง (ไม่จำกัดว่าใกล้ XD) ----
        with st.expander("📈 หุ้นผลตอบแทนปันผลสูง (ทั้งตลาด ไม่จำกัดวัน XD)"):
            okd = vdf[vdf["ปัญหา"].eq("")] if "ปัญหา" in vdf.columns else vdf
            hi = okd.copy()
            hi["_y"] = pd.to_numeric(hi["ผลตอบแทนต่อปี (%)"], errors="coerce")
            # ตัดค่าเกิน 20% ทิ้ง — เกือบทั้งหมดเกิดจากปันผลพิเศษครั้งเดียว
            # ซึ่งปีหน้าจะไม่ได้อีก การโชว์ไว้หัวตารางจึงชวนให้เข้าใจผิด
            hi = hi[hi["_y"].between(0.5, 20)].nlargest(60, "_y").drop(columns=["_y"])
            if hi.empty:
                st.info("ยังไม่มีข้อมูลพอ")
            else:
                st.caption("ตัดตัวที่ผลตอบแทนเกิน 20% ออก เพราะเกือบทั้งหมด"
                           "มาจากปันผลพิเศษครั้งเดียว ไม่ใช่ระดับที่จะได้ทุกปี")
                hcols = ["ticker", "ผลตอบแทนต่อปี (%)", "ปันผลรวม 12 เดือน",
                         "ราคา", "จ่ายกี่ครั้ง/ปี", "รอบการจ่าย",
                         "อัตราจ่ายจากกำไร (%)", "กลุ่ม", "ชื่อบริษัท"]
                hs = hi[[c for c in hcols if c in hi.columns]].copy()
                hs.index = [str(i) for i in range(1, len(hs) + 1)]
                html_table(hs, first_col="อันดับ", trim_year=False, fit=True,
                           max_height=460,
                           link_cols=("ticker",), link_target="_self",
                           left_cols=("รอบการจ่าย", "กลุ่ม", "ชื่อบริษัท"),
                           dec_cols={"จ่ายกี่ครั้ง/ปี": 0,
                                     "อัตราจ่ายจากกำไร (%)": 0})

    st.info(
        "**XD คือวันแรกที่ซื้อแล้วไม่ได้ปันผลงวดนั้น** — ต้องถือหุ้นอยู่ก่อนวันนี้ถึงจะได้เงิน  \n"
        "วัน XD ราคามักลดลงประมาณเงินปันผลที่จ่าย ซึ่ง**ไม่ใช่หุ้นตก** "
        "แต่เป็นมูลค่าเงินสดที่ออกจากราคาไปอยู่ในกระเป๋าผู้ถือหุ้น "
        "การซื้อก่อน XD เพื่อกินปันผลจึงไม่ได้กำไรฟรี  \n"
        "**อัตราจ่ายจากกำไรเกิน 100%** แปลว่าจ่ายมากกว่าที่หากำไรได้ "
        "ซึ่งมักไม่ยั่งยืน เว้นแต่เป็นกองทุนหรือ REIT ที่ถูกบังคับให้จ่ายเกือบทั้งหมด")
    st.error("⚠️ **ไม่ใช่คำแนะนำการลงทุน** — วันที่ที่เป็น *คาดการณ์* "
             "ต้องตรวจกับประกาศของ SET หรือของบริษัทก่อนตัดสินใจเสมอ")
    # ต้องมี st.stop() ปิดท้ายทุกโหมด
    # เพราะหน้า "วิเคราะห์รายตัว" อยู่ท้ายไฟล์แบบไม่มี if ครอบ
    # ถ้าไม่หยุด หน้านี้จะไหลลงไปวาดหน้าวิเคราะห์รายตัวต่อท้ายด้วย
    st.stop()


if MODE.startswith("🏆"):
    import tools_deep_scan as DS

    st.markdown("### 🏆 รายการหุ้นตามคำแนะนำ")
    st.info(
        "**ทำไมต้องมีหน้านี้แยก** — คำแนะนำ Strong Buy รู้ได้จากการวิเคราะห์ลึก"
        "เท่านั้น ซึ่งใช้เวลาราว **30 วินาทีต่อหุ้น 1 ตัว**  \n"
        "หุ้นไทย 866 ตัว = 7 ชั่วโมง · หุ้นสหรัฐ 6,000 ตัว = 50 ชั่วโมง "
        "— กดปุ่มบนเว็บแล้วรอไม่ได้  \n"
        "จึงแยกเป็น **รันข้ามคืนบน MacBook → เปิดเว็บดูผลใน 2 วินาที**")

    mk = st.radio("ตลาด", ["🇹🇭 หุ้นไทย", "🇺🇸 หุ้นสหรัฐ"], horizontal=True)
    market = "thai" if mk.startswith("🇹🇭") else "us"

    @st.cache_data(show_spinner=False, ttl=300)
    def _deep(mkt):
        return DS.load_results(mkt)

    rf1, rf2 = st.columns([1, 4])
    if rf1.button("🔄 โหลดข้อมูลใหม่", use_container_width=True,
                  help="อ่านไฟล์ผลวิเคราะห์ใหม่ทันที ไม่รอแคช 5 นาที"):
        _deep.clear()
        st.rerun()

    deep_update_panel(market)
    deep_changes_panel(market)

    ddf, dmeta = _deep(market)

    if ddf is None or ddf.empty:
        st.warning(
            f"**ยังไม่มีผลวิเคราะห์ลึกของตลาด {market}**\n\n"
            "รันบน MacBook ก่อน (แนะนำให้เริ่มที่ 150 ตัว ใช้เวลาราว 1 ชั่วโมง)\n\n"
            "```\neq\n"
            f"python3 tools_deep_scan.py --{market} --top 150\n```\n\n"
            "อยากได้ครบทุกตัวจริง ๆ ให้ใช้ `--all` แล้วรันข้ามคืน  \n"
            "ถ้าปิดเครื่องกลางคัน รันใหม่ได้เลย ระบบจะทำต่อจากที่ค้างไว้\n\n"
            "หลังรันเสร็จ ถ้าอยากให้มือถือเห็นด้วย :\n\n"
            "```\ngit add data/snapshots\n"
            "git commit -m 'ผลวิเคราะห์ลึก'\ngit push\n```")
    else:
        ok = ddf[ddf["ปัญหา"].eq("")] if "ปัญหา" in ddf.columns else ddf
        age = dmeta.get("อายุ (ชม.)", 0)
        src_th = dmeta.get("ที่มา (ไทย)", "-")
        # ---- ครอบคลุมตลาดไปแล้วกี่เปอร์เซ็นต์ ----
        # หุ้นสหรัฐมี 10,398 ตัว รอบเดียววิเคราะห์ไม่หมดแน่นอน
        # การเห็นตัวเลขไม่ครบจึงเป็นเรื่องปกติ ไม่ใช่ความผิดพลาด
        # แต่ต้องบอกให้ชัดว่าครอบคลุมแค่ไหน จะได้ไม่เข้าใจว่า
        # "ทั้งตลาดมีแค่นี้" เหมือนครั้งก่อนที่เห็น 150 แล้วนึกว่าหายไป
        full = MARKET_SIZE.get(market, len(ddf))
        pct = len(ddf) / full * 100 if full else 100
        rf2.caption(
            f"ในไฟล์มี **{len(ddf):,} ตัว** จากทั้งตลาด {full:,} ตัว "
            f"(**{pct:.0f}%**) · วิเคราะห์สำเร็จ {len(ok):,} ตัว "
            f"· บันทึกเมื่อ {dmeta.get('บันทึกเมื่อ','-')[:16]} "
            f"({age:.0f} ชม.ที่แล้ว) · อ่านจาก **{src_th}**")

        if pct < 99:
            st.info(
                f"**วิเคราะห์ไปแล้ว {pct:.0f}% ของตลาด** — "
                f"เหลืออีก {full - len(ddf):,} ตัว  \n"
                "ระบบทยอยทำทีละรอบโดยตั้งใจ เพราะหุ้น 1 ตัวใช้เวลาราว 30 วินาที "
                f"ทั้งตลาดจึงต้องใช้ {_fmt_hours(full)}  \n"
                "กด **⚙️ อัปเดตผลวิเคราะห์** ด้านบนเพื่อทำต่อจากจุดที่ค้าง "
                "(ตัวที่ทำแล้วจะไม่ทำซ้ำ)")

        # ---- ด่านคุณภาพ : เอาของที่ไม่ควรอยู่ในรายการออก ----
        #
        # ในรายชื่อหุ้นสหรัฐมี warrant · unit · ETF · SPAC ปนอยู่มาก
        # ของพวกนี้ไม่มีงบกิจการจริง ส่วนลดจึงพุ่งถึงหลักล้านล้านเปอร์เซ็นต์
        # (SATLW ได้ 59,528,560,000,000% ซึ่งไร้ความหมายโดยสิ้นเชิง)
        #
        # กรองตอนแสดงผล ไม่ใช่ตอนวิเคราะห์ เพื่อให้ผลที่รันไปแล้วใช้ได้ทันที
        # โดยไม่ต้องรันใหม่ 5 ชั่วโมง
        strict = st.checkbox(
            "กรองเฉพาะหุ้นสามัญที่ตัวเลขน่าเชื่อถือ", value=True,
            key=f"strict_{market}",
            help="ตัด warrant · unit · ETF · หุ้นราคาต่ำกว่า 1 · "
                 "ส่วนลดเกิน 300% · ข้อมูลสั้นกว่า 4 ปี · บริษัทซ้ำที่จดหลายตลาด")
        if strict:
            before_n = len(ok)
            ok = DS.clean(ddf)
            cut = before_n - len(ok)
            if cut > 0:
                fl = DS.add_flags(ddf[ddf["ปัญหา"].eq("")])
                from collections import Counter
                cc = Counter()
                for s in fl["ธงเตือน"]:
                    for part in (s.split(" · ") if s else []):
                        cc[part] += 1
                detail = " · ".join(f"{k} {v:,}" for k, v in cc.most_common())
                st.caption(f"ตัดออก **{cut:,} ตัว** — {detail}  \n"
                           f"เหลือที่ใช้ตัดสินใจได้ **{len(ok):,} ตัว**")

        # ---- ตรวจสุขภาพผลลัพธ์ก่อนแสดง ----
        dg = DS.diagnose(ok)
        if dg and dg.get("ส่วนลดเกิน 100%", 0) > max(1, len(ok) * 0.15):
            st.error(
                f"⚠️ **ส่วนลดสูงผิดปกติ {dg['ส่วนลดเกิน 100%']:,} ตัว "
                f"(เกิน 200% อีก {dg['ส่วนลดเกิน 200%']:,} ตัว)**  \n"
                "ส่วนลด 100% = มูลค่าที่ประเมินได้เป็น **2 เท่า** ของราคา · "
                "300% = **4 เท่า** — ตลาดทั้งตลาดคงไม่พลาดขนาดนั้นพร้อมกัน  \n"
                f"สาเหตุที่เป็นไปได้มากกว่าคือ **โมเดลเพี้ยนจากข้อมูลสั้น** "
                f"(ปีข้อมูลค่ากลาง {dg.get('ปีข้อมูลค่ากลาง',0):.0f} ปี)  \n"
                "**ให้ใช้ `คะแนนรวม` และ `ความน่าเชื่อถือ` ตัดสินแทน `ส่วนลด`**")
        if dg:
            dc = st.columns(4)
            metric_card(dc[0], "ปีข้อมูลค่ากลาง",
                        f"{dg.get('ปีข้อมูลค่ากลาง',0):.0f} ปี",
                        "หุ้นสหรัฐได้ถึง 15 ปี")
            metric_card(dc[1], "ความน่าเชื่อถือค่ากลาง",
                        f"{dg.get('ความน่าเชื่อถือค่ากลาง',0):.0f} / 100")
            metric_card(dc[2], "น่าเชื่อถือ ≥ 70",
                        f"{dg.get('ความน่าเชื่อถือ >= 70',0):,} ตัว")
            top_sc = dg.get("คะแนนรวมสูงสุด") or 0
            metric_card(dc[3], "คะแนนสูงสุดที่ทำได้", f"{top_sc:.1f}",
                        "Strong Buy ต้อง 82",
                        "#2e7d32" if top_sc >= 82 else "#ef6c00")

        # ---- นับจำนวนแต่ละคำแนะนำ ----
        # นับจาก ok ไม่ใช่ ddf เพื่อให้ตัวเลขบนการ์ดตรงกับตารางข้างล่าง
        # ถ้าใช้คนละชุด จะเกิดกรณี "การ์ดบอกมี 58 ตัว แต่ตารางขึ้น 27"
        cnt = DS.summarize(ok)
        cc6 = st.columns(6)
        COLORS = {"Strong Buy": "#1b6b3a", "Buy": "#2e8b57",
                  "Accumulate": "#6aa84f", "Hold": "#c9a227",
                  "Reduce": "#d1793a", "Sell": "#c1442e"}
        for col, lv in zip(cc6, DS.ORDER):
            n_ = int(cnt.loc[lv, "จำนวน"]) if lv in cnt.index else 0
            metric_card(col, lv, f"{n_:,} ตัว", None,
                        COLORS[lv] if n_ else None)

        pick_lv = st.multiselect(
            "แสดงคำแนะนำระดับ", DS.ORDER,
            default=["Strong Buy", "Buy"] if
            (cnt.loc["Strong Buy", "จำนวน"] if "Strong Buy" in cnt.index else 0)
            else ["Buy", "Accumulate"])

        f1, f2 = st.columns(2)
        min_rel = f1.slider("คะแนนความน่าเชื่อถือขั้นต่ำ", 0, 100, 0, 5)
        min_yr = f2.slider("จำนวนปีข้อมูลขั้นต่ำ", 0, 15, 0, 1,
                           help="หุ้นไทยมักมี 4 ปี · หุ้นสหรัฐได้ถึง 15 ปีจาก SEC")

        sel = ok[ok["คำแนะนำ"].isin(pick_lv)] if pick_lv else ok.iloc[0:0]
        if min_rel:
            sel = sel[pd.to_numeric(sel["คะแนนความน่าเชื่อถือ"],
                                    errors="coerce").fillna(0) >= min_rel]
        if min_yr:
            sel = sel[pd.to_numeric(sel["ปีข้อมูล"],
                                    errors="coerce").fillna(0) >= min_yr]
        sel = sel.sort_values("คะแนนรวม", ascending=False)

        if sel.empty:
            # บอกให้ชัดว่าตัวกรองไหนตัดออกไป ไม่ใช่แค่ "ไม่เจอ"
            have_lv = {lv: int(cnt.loc[lv, "จำนวน"]) if lv in cnt.index else 0
                       for lv in pick_lv}
            zero = [lv for lv, n in have_lv.items() if n == 0]
            some = [f"{lv} {n:,} ตัว" for lv, n in have_lv.items() if n]
            msg = "**ไม่มีหุ้นตัวใดตรงเงื่อนไข**  \n"
            if zero:
                msg += (f"ระดับที่เลือกไว้ไม่มีหุ้นเลยในรอบนี้ : "
                        f"**{', '.join(zero)}** (0 ตัว)  \n")
            if some:
                msg += (f"ระดับที่มีหุ้นอยู่ : {' · '.join(some)} "
                        "— แต่ถูกตัดออกด้วยตัวกรองด้านล่าง  \n")
            if not some and not zero:
                msg += "ยังไม่ได้เลือกระดับคำแนะนำเลย  \n"
            msg += "ลองเลือกระดับเพิ่ม หรือลดคะแนนความน่าเชื่อถือ/ปีข้อมูลขั้นต่ำลง"
            st.warning(msg)
        else:
            # เปลี่ยนชื่อคอลัมน์ตอนแสดงผลเท่านั้น ไม่แตะข้อมูลที่บันทึกไว้
            # เพราะไฟล์ผลเก่าที่ทำไว้แล้วยังใช้ชื่อ "โซน" อยู่
            sel = sel.rename(columns={"โซน": "โซนราคา"})
            show = sel[[c for c in
                        ["ticker", "คำแนะนำ", "คะแนนรวม", "ราคา",
                         "มูลค่าที่ประเมินได้", "ส่วนลด (%)", "โซนราคา",
                         "ความน่าเชื่อถือ", "คะแนนความน่าเชื่อถือ", "ปีข้อมูล",
                         "Buffett", "คุณภาพ", "ความเสี่ยง", "กลุ่ม",
                         "ชื่อบริษัท"] if c in sel.columns]].copy()
            show = sort_controls(show, key=f"sb_{market}",
                                 default="คะแนนรวม", asc=False)
            show.index = [str(i) for i in range(1, len(show) + 1)]
            st.caption(
                f"**แสดง {len(show):,} ตัว** จาก {len(ok):,} ตัวที่วิเคราะห์สำเร็จ "
                f"· กรองด้วย : คำแนะนำ {', '.join(pick_lv)}"
                + (f" · ความน่าเชื่อถือ ≥ {min_rel}" if min_rel else "")
                + (f" · ข้อมูล ≥ {min_yr} ปี" if min_yr else "")
                + "  \nถ้าตัวเลขนี้น้อยกว่าที่คาด ให้ดูว่าไฟล์ผลมีกี่ตัว "
                  "(บรรทัดบนสุด) และเลือกคำแนะนำครบทุกระดับหรือยัง")
            st.caption("**กดที่ชื่อหุ้น** เพื่อเปิดวิเคราะห์รายตัวของตัวนั้น")
            html_table(show, first_col="อันดับ", trim_year=False, fit=True,
                       max_height=620, sign_cols=("ส่วนลด (%)",),
                       link_cols=("ticker",), link_target="_self",
                       left_cols=("คำแนะนำ", "โซนราคา", "ความน่าเชื่อถือ",
                                  "กลุ่ม", "ชื่อบริษัท"),
                       dec_cols={"คะแนนรวม": 1, "ปีข้อมูล": 0,
                                 "คะแนนความน่าเชื่อถือ": 0, "Buffett": 0,
                                 "คุณภาพ": 0, "ความเสี่ยง": 0})
            st.download_button(
                "ดาวน์โหลดรายการนี้ (CSV)",
                sel.to_csv(index=False).encode("utf-8-sig"),
                f"คำแนะนำ_{market}.csv", "text/csv")

        # ---- อธิบายจุดที่สับสนบ่อยที่สุดในตารางนี้ ----
        # "คำแนะนำ" กับ "โซนราคา" เป็นคนละเรื่อง แต่ใช้คำชุดเดียวกัน
        # จึงเห็นแถวที่ คำแนะนำ = Accumulate แต่ โซนราคา = Strong Buy
        # แล้วเข้าใจว่าระบบขัดแย้งกันเอง ทั้งที่ถูกต้องแล้ว
        with st.expander("ทำไมบางแถว คำแนะนำ = Accumulate แต่ โซนราคา = Strong Buy"):
            st.markdown(
                "สองคอลัมน์นี้ตอบคนละคำถาม เผอิญใช้คำชุดเดียวกัน\n\n"
                "| | ดูอะไร | คิดจากอะไร |\n"
                "|---|---|---|\n"
                "| **คำแนะนำ** | ข้อสรุปสุดท้าย | รวม 7 ด้าน — มูลค่า 30% · "
                "คุณภาพ 20% · Buffett 15% · ความเสี่ยง 15% · เติบโต 10% · "
                "วัฏจักร 5% · ข่าว 5% แล้วปรับตามความน่าเชื่อถือของข้อมูล |\n"
                "| **โซนราคา** | ราคาวันนี้ถูกหรือแพง | เทียบราคากับมูลค่าที่ประเมินได้ "
                "**อย่างเดียว** |\n\n"
                "ตัวอย่างจริงในตารางนี้ — **AU.BK** ราคา 4.64 มูลค่าประเมิน 9.18 "
                "ส่วนลด 98% จึงอยู่โซนราคา *Strong Buy*  \n"
                "แต่ความน่าเชื่อถือของข้อมูลอยู่ระดับ **ต่ำ (20/100)** เพราะมีงบแค่ 4 ปี "
                "ระบบจึงดึงข้อสรุปเข้าหากลาง เหลือ **Accumulate**\n\n"
                "**นี่คือพฤติกรรมที่ตั้งใจ** — ข้อมูล 4 ปีไม่ควรนำไปสู่คำแนะนำที่หนักแน่น "
                "ที่สุดของระบบ ส่วนลด 98% จากข้อมูลสั้นมักแปลว่าโมเดลเพี้ยน "
                "มากกว่าจะแปลว่าตลาดพลาด")

        if "Strong Buy" in pick_lv and not len(
                ok[ok["คำแนะนำ"].eq("Strong Buy")]):
            st.warning(
                "**ไม่พบ Strong Buy — นี่เป็นเรื่องปกติ**  \n"
                "Strong Buy ต้องได้คะแนนรวม **82 จาก 100** ซึ่งเกิดได้ก็ต่อเมื่อ "
                "ราคาถูก · คุณภาพดี · ความเสี่ยงต่ำ · ข้อมูลน่าเชื่อถือ "
                "**พร้อมกันทั้งสี่อย่าง**  \n"
                f"รอบนี้คะแนนสูงสุดทั้งตลาดคือ **{top_sc:.1f}** "
                f"ยังห่างอีก {82 - top_sc:.1f} คะแนน  \n"
                "สาเหตุหลักคือหุ้นไทยมีงบย้อนหลังแค่ 4 ปี ซึ่งกดคะแนนความน่าเชื่อถือ "
                "จนแตะ 82 ไม่ได้ — **หุ้นสหรัฐมีโอกาสมากกว่า** เพราะได้ 15 ปีจาก SEC")

        st.error("⚠️ **ไม่ใช่คำแนะนำการลงทุน** — เป็นการสรุปตัวเลขเพื่อการศึกษา  \n"
                 "ราคาเปลี่ยนทุกวัน ผลนี้เป็นภาพนิ่งของวันที่วิเคราะห์ "
                 "· เปิดวิเคราะห์รายตัวเพื่อดูเหตุผลเต็มก่อนตัดสินใจเสมอ")
    st.stop()


# ---------------------------------------------------------------------------
# โหมดคัดกรองทั้งตลาด (ชั้นที่ 1 — เร็ว)
# ---------------------------------------------------------------------------
if MODE.startswith("คัดกรอง"):
    from screener import (GROWTH_COLS, attach_growth, preset, quality_flags,
                          quarterly_growth, quick_filter, quick_screen)

    st.info("**ชั้นคัดกรองเร็ว** — ดึงเฉพาะตัวเลขสรุป (P/E, P/BV, ROE) "
            "ไม่ทำ DCF จึงเร็วกว่าราว 20 เท่า ใช้ได้กับทั้งตลาด\n\n"
            "หลังคัดได้แล้ว ให้เอารายชื่อไปวิเคราะห์ลึกในโหมดถัดไป")

    import snapshot as _SNAP

    # ตั้งค่าเริ่มต้นเป็น "ขอบเขตที่คัดกรองล่าสุด" ไม่ใช่ค่าคงที่
    # เพื่อให้แท็บใหม่ที่เปิดจากการกดชื่อหุ้น กลับมาเจอหน้าเดิมที่ค้างไว้
    _LASTS = _SNAP.get_last_scope()
    UNI_OPTS = ["🇺🇸 หุ้นสหรัฐทั้งตลาด (เร็ว)", "🇹🇭 หุ้นไทย",
                "หุ้นสหรัฐยอดนิยม 39 ตัว"]
    _uni_idx = UNI_OPTS.index(_LASTS["uni"]) if _LASTS.get("uni") in UNI_OPTS else 0
    uni = st.radio("ตลาด", UNI_OPTS, index=_uni_idx, horizontal=True)

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
        MKT_OPTS = ["ทั้งหมด", "SET", "mai"]
        IND_OPTS = ["ทุกกลุ่ม"] + thai_industries()
        with t1:
            mkt = st.radio("ตลาด", MKT_OPTS, horizontal=True,
                           index=(MKT_OPTS.index(_LASTS["mkt"])
                                  if _LASTS.get("mkt") in MKT_OPTS else 0))
        with t2:
            ind = st.selectbox("กลุ่มอุตสาหกรรม", IND_OPTS,
                               index=(IND_OPTS.index(_LASTS["ind"])
                                      if _LASTS.get("ind") in IND_OPTS else 0))
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

    # จำขอบเขตล่าสุดไว้ให้แท็บอื่นเปิดมาเจอหน้าเดิม
    _SNAP.set_last_scope({"uni": uni, "key": key, "snap_key": snap_key,
                          **({"mkt": mkt, "ind": ind} if key == "thai" else {})})

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

    # ---------- ค่าตั้งต้นของทุกเกณฑ์ + ปุ่มล้าง ----------
    # ทุกช่องต้องมี key เพื่อให้ปุ่มล้างเขียนค่ากลับได้
    # (widget ที่ไม่มี key จะแก้ค่าจากภายนอกไม่ได้เลย)
    FILTER_DEFAULTS = {
        "f_pe": 0.0, "f_pbv": 0.0, "f_ev": 0.0, "f_roe": 0.0, "f_fcf": 0.0,
        "f_div": 0.0, "f_de": 0.0, "f_gm": 0.0, "f_nm": 0.0, "f_cap": 0.0,
    }

    def _reset_filters():
        for k, v in FILTER_DEFAULTS.items():
            st.session_state[k] = v

    # ---------- การเติบโตรายไตรมาส (ต้องกดเอง) ----------
    # ไม่ดึงอัตโนมัติ เพราะต้องขอข้อมูลเพิ่ม 2 คำขอต่อหุ้น
    # ถ้าดึงพร้อมกันทั้ง 866 ตัวจะโดน Yahoo บล็อกและเสียอัตราสำเร็จ 99% ที่ได้มายาก
    # จึงให้ดึงเฉพาะรายชื่อที่ผ่านเกณฑ์แล้ว ซึ่งปกติเหลือหลักสิบ
    st.session_state.setdefault("qgrowth", None)

    n_on = sum(1 for k, v in FILTER_DEFAULTS.items()
               if st.session_state.get(k, v) != v)
    fh1, fh2 = st.columns([4, 1])
    with fh1:
        st.markdown("**เกณฑ์คัดกรอง** (ปล่อยเป็น 0 = ไม่ใช้เกณฑ์นั้น)")
        st.caption(f"ตั้งค่าไว้ **{n_on}** จุด" if n_on
                   else "ยังไม่ได้ตั้งเกณฑ์ใด — จะแสดงหุ้นทุกตัวที่ดึงข้อมูลได้")
    with fh2:
        st.button("🧹 ล้างเกณฑ์ทั้งหมด", use_container_width=True,
                  on_click=_reset_filters, disabled=n_on == 0,
                  help="คืนทุกช่องเป็น 0  \n"
                       "**ไม่ลบข้อมูลที่ดึงมาแล้ว** จึงไม่ต้องรอดึงใหม่")

    g = st.columns(10)
    f_pe = g[0].number_input("P/E ไม่เกิน", 0.0, 200.0, step=1.0, key="f_pe")
    f_pbv = g[1].number_input("P/BV ไม่เกิน", 0.0, 50.0, step=0.5, key="f_pbv")
    f_ev = g[9].number_input(
        "EV/EBITDA ไม่เกิน", 0.0, 100.0, step=0.5, key="f_ev",
        help="**มูลค่ากิจการ ÷ กำไรก่อนดอกเบี้ย ภาษี ค่าเสื่อม**\n\n"
             "ดีกว่า P/E ตรงที่นับหนี้เข้าไปด้วย และไม่ถูกบิดจากวิธีตัดค่าเสื่อม "
             "หรืออัตราภาษีที่ต่างกัน จึงเทียบข้ามบริษัทและข้ามประเทศได้ตรงกว่า\n\n"
             "ค่าทั่วไป 6–12 เท่า · ต่ำกว่า 6 อาจถูกจริงหรือธุรกิจกำลังถดถอย\n\n"
             "**ใช้กับธนาคารไม่ได้** เพราะดอกเบี้ยคือรายได้หลัก การตัดดอกเบี้ยออก "
             "จึงทำให้ตัวเลขไม่มีความหมาย")
    f_roe = g[2].number_input("ROE ขั้นต่ำ (%)", 0.0, 100.0, step=1.0, key="f_roe")
    f_fcf = g[3].number_input("FCF Yield ขั้นต่ำ (%)", 0.0, 50.0, step=0.5,
                              key="f_fcf")
    f_div = g[4].number_input("ปันผลขั้นต่ำ (%)", 0.0, 20.0, step=0.5, key="f_div")
    f_de = g[5].number_input("D/E ไม่เกิน (เท่า)", 0.0, 20.0, step=0.25, key="f_de",
                             help="**หนี้ที่มีดอกเบี้ย ÷ ส่วนของผู้ถือหุ้น**\n\n"
                                  "นับเฉพาะเงินกู้และหุ้นกู้ "
                                  "**ไม่รวม**เจ้าหนี้การค้าและค่าใช้จ่ายค้างจ่าย "
                                  "จึงต่ำกว่า 'หนี้สินรวม ÷ ส่วนทุน' ที่เห็นในตำรา\n\n"
                                  "ยิ่งต่ำยิ่งปลอดภัย · ธนาคารและลีสซิ่งจะสูงเป็นปกติ")
    f_gm = g[6].number_input("กำไรขั้นต้นขั้นต่ำ (%)", 0.0, 100.0, step=1.0,
                             key="f_gm",
                             help="อัตรากำไรขั้นต้นสูง = สินค้ามีอำนาจตั้งราคา "
                                  "หรือมีความได้เปรียบด้านต้นทุน")
    f_nm = g[7].number_input("กำไรสุทธิขั้นต่ำ (%)", 0.0, 100.0, step=1.0, key="f_nm")
    f_cap = g[8].number_input("มูลค่าตลาดขั้นต่ำ (ล้าน)", 0.0, 1e7, step=1000.0,
                              key="f_cap")

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

    # ---------- กู้ผลคัดกรองอัตโนมัติ ----------
    # ปัญหาที่แก้ : กดชื่อหุ้นในตาราง -> เปิดแท็บใหม่ -> แท็บนั้นเป็น session ใหม่
    # ที่ไม่มีผลคัดกรองเลย พอสลับกลับมาโหมดคัดกรองจึงเจอหน้าว่าง
    # และต้องรอดึงข้อมูลใหม่ 5-10 นาทีทั้งที่เพิ่งดึงไปเมื่อครู่
    #
    # แก้โดยดึงจากที่บันทึกไว้ให้เองเมื่อ session ยังไม่มีข้อมูล
    # ปลอดภัยเพราะทุกครั้งที่ดึงข้อมูลสำเร็จ ระบบบันทึกไว้อยู่แล้ว
    if (st.session_state.get("quick_df") is None and _saved is not None
            and not run_fresh):
        st.session_state["quick_df"] = _saved
        st.session_state["auto_restored"] = _smeta

    _ar = st.session_state.pop("auto_restored", None)
    if _ar:
        age = _ar.get("อายุ (ชม.)", 0)
        age_txt = f"{age:.0f} ชม.ที่แล้ว" if age >= 1 else "เมื่อสักครู่"
        st.success(
            f"↩️ **กู้ผลคัดกรองที่ทำไว้กลับมาให้แล้ว** "
            f"({_ar.get('จำนวนแถว',0):,} ตัว · ดึงเมื่อ {age_txt} · "
            f"จาก{_ar.get('ที่มา (ไทย)','-')})  \n"
            "ไม่ต้องคัดกรองใหม่ — กด **เริ่มคัดกรอง (ดึงข้อมูลใหม่)** "
            "เฉพาะเมื่อต้องการราคาล่าสุด")
    elif st.session_state.get("quick_df") is None and _saved is None:
        st.warning(
            "**ผลคัดกรองที่บันทึกไว้หายไป** — เกิดขึ้นเมื่อ Streamlit รีสตาร์ท "
            "(หลัง `git push` โค้ดใหม่ หรือแอปหลับเพราะไม่มีคนใช้ราว 30 นาที)  \n"
            "ที่เก็บในเครื่องของ Streamlit เป็นแบบชั่วคราว จึงหายไปพร้อมกัน\n\n"
            "**วิธีให้ไม่หายอีก** — เก็บผลไว้ที่ถาวร เลือกทางใดทางหนึ่ง  \n"
            "1. รันบน MacBook แล้ว push : "
            "`python3 tools_snapshot_build.py --thai` → `git push` "
            "(ไฟล์อยู่ใน `data/snapshots/` จึงรอดทุกการรีสตาร์ท)  \n"
            "2. ตั้งค่า Google Drive ตามคู่มือไฟล์ 19 — บันทึกอัตโนมัติทุกครั้ง")

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
            # ---------- รวมกับของเดิมทันที แล้วบันทึกทุกครั้ง ----------
            # ไม่มีรอบไหนดึงได้ครบ 100% และตัวที่พลาดไม่ใช่ตัวเดียวกันทุกรอบ
            # การรวมทำให้ยิ่งดึงยิ่งครบ และไม่มีทางที่ข้อมูลดีจะหายไป
            n_new = int(fresh["ปัญหา"].eq("").sum())
            prev, _pm = snapshot.info(snap_key)
            merged = snapshot.merge(prev, fresh)
            n_all = int(merged["ปัญหา"].eq("").sum())

            st.session_state["quick_df"] = merged
            r = snapshot.save(snap_key, merged,
                              extra={"ขอบเขต": snap_key, "ตลาด": key,
                                     "ดึงสำเร็จ": n_all})
            _peek.clear()                     # ให้ปุ่ม ⚡ เห็นของใหม่ทันที

            gain = n_all - n_new
            msg = f"รอบนี้ดึงได้ **{n_new:,}** ตัว"
            if prev is not None:
                msg += (f" · รวมกับของเดิมแล้วมี **{n_all:,} / {len(merged):,}** ตัว"
                        + (f" (ได้เพิ่มจากรอบก่อน {gain:,} ตัว)" if gain > 0 else ""))
            st.success(msg + f" — บันทึกแล้ว {r.get('ขนาด (KB)', 0)} KB")

            if r["local"] and not r["drive"]:
                st.warning(
                    "ข้อมูลนี้เก็บอยู่ในเครื่องของ Streamlit ซึ่ง **หายเมื่อแอปรีสตาร์ท** "
                    "(หลับเพราะไม่มีคนใช้ราว 30 นาที หรือตอน push โค้ดใหม่)  \n"
                    "กดปุ่ม **💾 บันทึกถาวร** ใต้ตารางเพื่อเก็บไว้ไม่ให้หาย")
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
                           min_net_margin=f_nm or None,
                           max_ev_ebitda=f_ev or None)

        # แนบการเติบโตรายไตรมาสถ้าเคยกดดึงไว้แล้ว
        res = attach_growth(res, st.session_state.get("qgrowth"))

        # ---- บัญชีว่าหุ้นหายไปที่ขั้นตอนไหนบ้าง ----
        # ผู้ใช้ต้องตรวจสอบได้ว่า 866 -> N เกิดจากอะไร ไม่ใช่หายไปเฉย ๆ
        FLOW = [("ทั้งหมดในทะเบียน", len(qdf)),
                ("ดึงข้อมูลสำเร็จ", len(got)),
                ("หลังจัดการหุ้นที่มีจุดต้องระวัง", len(base)),
                ("หลังเกณฑ์คัดกรอง", len(res))]

        # ---------- จัดเรียงตามหัวข้อที่เลือก ----------
        # ค่าเริ่มต้นของแต่ละหัวข้อตั้งให้ "ตัวที่น่าสนใจอยู่บน" โดยอัตโนมัติ
        #   P/E, P/BV, P/S, D/E  → น้อยไปมาก (ยิ่งต่ำยิ่งน่าสนใจ)
        #   ROE, FCF Yield, ปันผล, มูลค่าตลาด → มากไปน้อย
        SORTABLE = ["P/E", "P/BV", "P/S", "EV/EBITDA", "D/E", "ROE (%)",
                    "FCF Yield (%)", "อัตรากำไรขั้นต้น (%)", "อัตรากำไรสุทธิ (%)",
                    "ปันผล (%)", "รายได้ YoY (%)", "กำไร YoY (%)",
                    "มูลค่าตลาด (ล้าน)", "ราคา", "ticker"]
        # เพิ่มปุ่มเรียงตาม QoQ/YoY-Q เฉพาะเมื่อดึงงบไตรมาสมาแล้ว
        SORTABLE += [c for c in GROWTH_COLS
                     if c in res.columns and c != "งบไตรมาสล่าสุด"]
        ASC_BY_DEFAULT = {"P/E", "P/BV", "P/S", "EV/EBITDA", "D/E", "ticker"}
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
        metric_card(k[2], "ผ่านเกณฑ์", f"{len(res):,} ตัว",
                    f"จาก {len(base):,} ตัวที่นำมาคัด")
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

        with st.expander(f"🔎 หุ้นหายไปที่ขั้นตอนไหน — {len(qdf):,} เหลือ {len(res):,}"):
            prev = None
            for label, n in FLOW:
                drop = "" if prev is None else f"  (หายไป {prev - n:,} ตัว)"
                st.markdown(f"- **{label}** : {n:,} ตัว{drop}")
                prev = n

        if res.empty:
            st.warning("ไม่มีหุ้นตัวใดผ่านเกณฑ์ — ลองผ่อนเกณฑ์ลง")
        else:
            # ธงเตือนไว้ท้ายตาราง — ตัวเลขที่ใช้ตัดสินใจควรอยู่ใกล้ชื่อหุ้นมากกว่า
            # ชื่อบริษัทเต็มไว้ท้ายตาราง — เป็นคอลัมน์ที่กว้างที่สุดและอ่านทีหลังก็ได้
            # ถ้าอยู่ต้นตารางจะดันตัวเลขที่ใช้ตัดสินใจให้ห่างจาก ticker
            cols = ["ticker", "ราคา", "P/E", "P/BV", "P/S", "EV/EBITDA", "D/E",
                    "ROE (%)", "อัตรากำไรขั้นต้น (%)", "อัตรากำไรสุทธิ (%)",
                    "FCF Yield (%)", "ปันผล (%)",
                    "รายได้ YoY (%)", "กำไร YoY (%)"] + GROWTH_COLS + [
                    "มูลค่าตลาด (ล้าน)", "กลุ่ม", "⚠️", "ชื่อบริษัท"]

            # ถ้าตารางมีข้อมูลจากหลายวันปนกัน ต้องบอกให้เห็นว่าแถวไหนเป็นของวันไหน
            # ไม่อย่างนั้นผู้ใช้จะเข้าใจว่าราคาทุกแถวเป็นของวันนี้ ซึ่งไม่จริง
            days = (res[snapshot.STAMP_COL].dropna().unique()
                    if snapshot.STAMP_COL in res.columns else [])
            if len(days) > 1:
                cols.append(snapshot.STAMP_COL)
                newest = max(days)
                n_old = int((res[snapshot.STAMP_COL] != newest).sum())
                st.info(f"ตารางนี้รวมข้อมูลจาก {len(days)} วัน — "
                        f"**{n_old:,} ตัวเป็นข้อมูลจากรอบก่อน** เพราะรอบล่าสุดดึงไม่สำเร็จ "
                        f"(ดูคอลัมน์ *{snapshot.STAMP_COL}* ท้ายตาราง) "
                        "· ราคาของแถวเหล่านั้นไม่ใช่ราคาล่าสุด")
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
            # ระบายเขียวคอลัมน์การเติบโตที่เป็นบวก
            g_cols = tuple(c for c in show.columns
                           if "YoY" in c or "QoQ" in c)
            html_table(show, first_col="อันดับ", trim_year=False,
                       max_height=640, link_cols=("ticker",),
                       link_target="_self", sign_cols=g_cols,
                       left_cols=("ชื่อบริษัท", "กลุ่ม", "งบไตรมาสล่าสุด", "⚠️"))
            # ---------- ดึงการเติบโตรายไตรมาสเพิ่ม (กดเอง) ----------
            have_q = any(c in res.columns for c in GROWTH_COLS)
            gc1, gc2 = st.columns([1, 3])
            with gc1:
                go_q = st.button(
                    f"📈 ดึง QoQ / YoY รายไตรมาส ({len(res)} ตัว)",
                    use_container_width=True, type="secondary")
            with gc2:
                st.caption(
                    f"ต้องขอข้อมูลเพิ่ม **2 คำขอต่อหุ้น** (~{len(res)*2:,} คำขอ · "
                    f"ราว {len(res)*1.2/60:.0f}–{len(res)*2.5/60:.0f} นาที)  \n"
                    "จึงไม่ดึงอัตโนมัติ — ถ้าดึงพร้อมกันทั้งตลาดจะโดน Yahoo บล็อก "
                    "และเสียอัตราสำเร็จที่ได้มายาก **ให้กรองให้เหลือน้อยก่อนแล้วค่อยกด**"
                    + ("  \n✅ ดึงแล้ว — คอลัมน์ QoQ/YoY-Q อยู่ในตารางด้านบน"
                       if have_q else ""))
            if go_q:
                gbar, gnote = st.progress(0.0), st.empty()

                def on_g(i, total, t):
                    gbar.progress(min(i / total, 1.0))
                    gnote.caption(f"{t} — {i:,}/{total:,}")

                st.session_state["qgrowth"] = quarterly_growth(
                    list(res["ticker"]), progress=on_g)
                gbar.progress(1.0)
                gnote.empty()
                st.rerun()

            if quality:
                st.caption("**ความหมายของธง ⚠️** — `ขาดทุน` กำไรสุทธิติดลบ · "
                           "`กำไรพิเศษ` กำไรสุทธิเกิน 100% ของรายได้ · "
                           "`ทุนติดลบ` ส่วนของผู้ถือหุ้นติดลบ · "
                           "`เล็ก` มูลค่าตลาดต่ำกว่าเกณฑ์ · "
                           "`FCF?` FCF Yield สูงผิดปกติ · `P/E?` P/E ต่ำผิดปกติ  \n"
                           "ตัวเลขทุกช่องเป็นค่าจริงของหุ้นตัวนั้น ธงเป็นเพียงข้อสังเกตเพิ่มเติม")
            with st.expander("📖 ตัวเลขแต่ละคอลัมน์หมายถึงอะไรกันแน่ (อ่านก่อนใช้ตัดสินใจ)"):
                st.markdown("""
| คอลัมน์ | นิยามที่ใช้จริง | จุดที่ต่างจากที่คิด |
|---|---|---|
| **D/E** | หนี้**ที่มีดอกเบี้ย** ÷ ส่วนของผู้ถือหุ้น | **ไม่ใช่** หนี้สินรวม ÷ ส่วนทุน — ไม่นับเจ้าหนี้การค้า จึงต่ำกว่าที่คำนวณจากงบดุลเอง · `0.00` = ไม่มีเงินกู้เลย (พบได้จริงในหุ้นไทยหลายตัว) · `<0.01` = มีนิดเดียว · `—` = ไม่มีข้อมูล |
| **อัตรากำไรขั้นต้น** | (รายได้ − ต้นทุนขาย) ÷ รายได้ | **เว้นว่างสำหรับกลุ่มการเงิน** เพราะธนาคาร/ลีสซิ่งไม่มีต้นทุนขาย ค่าที่ได้จะเป็น 100% หรือ 0% ซึ่งเทียบกับธุรกิจอื่นไม่ได้ |
| **อัตรากำไรสุทธิ** | กำไรสุทธิ ÷ รายได้ (12 เดือนล่าสุด) | เกิน 100% ได้จริง ถ้ากำไรมาจากขายสินทรัพย์หรือส่วนแบ่งบริษัทร่วม — ติดธง `กำไรพิเศษ` ไว้ให้ |
| **P/E · P/BV · P/S** | ราคา ÷ กำไร/มูลค่าทางบัญชี/รายได้ ต่อหุ้น | คิดจาก **12 เดือนล่าสุด** ไม่ใช่ค่าเฉลี่ยหลายปี ปีที่มีรายการพิเศษจะทำให้เพี้ยนมาก |
| **ROE** | กำไรสุทธิ ÷ ส่วนของผู้ถือหุ้น | บริษัทที่ส่วนทุนเกือบหมดจะได้ ROE สูงลิ่วทั้งที่อ่อนแอ ดูคู่กับ `ทุนติดลบ` เสมอ |
| **FCF Yield** | (เงินสดจากดำเนินงาน − ลงทุน) ÷ มูลค่าตลาด | ปีที่ขายทรัพย์สินก้อนใหญ่จะพุ่งผิดปกติ และไม่เกิดซ้ำปีหน้า |
| **รายได้/กำไร YoY** | ไตรมาสล่าสุด เทียบ **ไตรมาสเดียวกันปีก่อน** | มาจาก yfinance โดยตรง · เป็นวิธีที่ถูกต้องสำหรับธุรกิจมีฤดูกาล |
| **QoQ** | ไตรมาสล่าสุด เทียบ **ไตรมาสก่อนหน้า** | ⚠️ ธุรกิจมีฤดูกาลจะบิดเบือนหนัก — ห้างฯ Q4 เทียบ Q3 สวยทุกปีโดยไม่ได้แปลว่าดีขึ้น |
| **YoY-Q** | เหมือน YoY แต่คำนวณเองจากงบไตรมาส | ใช้ตรวจว่าตัวเลข YoY ของ yfinance ตรงกับงบจริงไหม |

**ที่มาของตัวเลขทั้งหมด** — yfinance ซึ่งดึงจากหน้า Statistics ของ Yahoo Finance
เป็นตัวเลขสรุปสำเร็จรูป **ยังไม่ผ่านการตรวจสอบเหมือนชั้นวิเคราะห์ลึก**
ชั้นนี้มีไว้เพื่อ *คัดจาก 866 ตัวให้เหลือหลักสิบ* เท่านั้น ก่อนตัดสินใจจริงต้องส่งไปวิเคราะห์ลึก
ซึ่งอ่านงบการเงินย้อนหลังหลายปีและคำนวณเองทุกตัวเลข
""")
            _n = ("ครบทั้ง" if len(show) == len(res) else "แสดง")
            st.caption(f"เรียงตาม **{sort_col}** ({order}) · "
                       f"{_n} {len(show):,} ตัวจาก {len(res):,} ตัวที่ผ่านเกณฑ์ "
                       "· **กดที่ชื่อหุ้น** เพื่อดูการวิเคราะห์รายตัวทันที "
                       "· เลื่อนลงในตารางเพื่อดูตัวถัดไป")
            d1, d2 = st.columns(2)
            d1.download_button("ดาวน์โหลดผลทั้งหมด (CSV)",
                               res.to_csv(index=False).encode("utf-8-sig"),
                               "ผลคัดกรอง.csv", "text/csv",
                               use_container_width=True,
                               help="ไฟล์ตารางสำหรับเปิดใน Excel")

            # ---------- บันทึกถาวร ----------
            # ที่เก็บในเครื่องของ Streamlit Cloud หายทุกครั้งที่แอปรีสตาร์ท
            # (ซึ่งเกิดขึ้นทั้งตอนหลับเพราะไม่มีคนใช้ และตอน git push โค้ดใหม่)
            # ปุ่มนี้ทำให้เอาผลที่ดึงมาแล้วเก็บไว้ถาวรได้ โดยไม่ต้องดึงใหม่
            _blob = snapshot._pack(
                qdf.drop(columns=["⚠️"], errors="ignore"),
                {"ชื่อชุดข้อมูล": snap_key, "บันทึกเมื่อ": snapshot._now(),
                 "จำนวนแถว": int(len(qdf)), "คอลัมน์": list(qdf.columns),
                 "คอลัมน์ข้อความ": [c for c in qdf.columns
                                    if qdf[c].dropna().map(type).eq(str).any()],
                 "ขอบเขต": snap_key, "แหล่ง": "เว็บ"})
            d2.download_button(
                f"💾 บันทึกถาวร ({len(_blob)/1024:.0f} KB)",
                _blob, snapshot._fname(snap_key), "application/gzip",
                use_container_width=True, type="primary",
                help="ดาวน์โหลดแล้วนำไปวางใน data/snapshots/ ของโปรเจกต์ "
                     "แล้ว git push — ข้อมูลชุดนี้จะอยู่ถาวร ไม่หายตอนแอปรีสตาร์ท")
            st.caption(
                "**ปุ่ม 💾 บันทึกถาวร** — ข้อมูลที่ดึงบนเว็บจะหายทุกครั้งที่แอปรีสตาร์ท "
                "(หลับเพราะไม่มีคนใช้ หรือตอน push โค้ดใหม่)  \n"
                "ถ้าอยากเก็บผลชุดนี้ไว้ ให้กดปุ่ม 💾 แล้วทำตามนี้บน MacBook:\n"
                "```\neq\nmkdir -p data/snapshots\n"
                f"mv ~/Downloads/{snapshot._fname(snap_key)} data/snapshots/\n"
                "git add data/snapshots && git commit -m \"เก็บผลคัดกรอง\" && git push\n```")

            # ---------- ช่องติ๊กเลือกหุ้นทีละตัว ----------
            st.markdown("---")
            st.markdown("### ☑️ ติ๊กเลือกหุ้นไปวิเคราะห์ลึกหรือเปรียบเทียบ")
            st.caption("ชั้นคัดกรองบอกได้แค่ว่า 'ตัวเลขสรุปดูน่าสนใจ' "
                       "ยังไม่ได้ประเมินมูลค่า — เลือกตัวที่สนใจส่งไปวิเคราะห์เต็มรูปแบบ")

            all_tk = list(res["ticker"])

            # ---- ปุ่มเลือก/ล้าง ----
            # ต้องเขียนลง st.session_state["cb_<ticker>"] โดยตรง
            #
            # เหตุผล : เมื่อ checkbox มี key แล้ว Streamlit จะยึดค่าใน session_state
            # เป็นความจริง และ **ไม่สนใจ** พารามิเตอร์ value= อีกเลยหลังเรนเดอร์ครั้งแรก
            # โค้ดเดิมไปเติมชื่อหุ้นลงชุด picked เฉย ๆ ช่องติ๊กจึงไม่เปลี่ยนตาม
            # แล้วรอบถัดมาก็ถูกลบออกทันทีเพราะอ่านค่าช่องได้เป็น False
            def _check_all(tks, on=True):
                for x in tks:
                    st.session_state[f"cb_{x}"] = on

            b1, b2 = st.columns(2)
            b1.button(f"เลือกทั้งหมด ({len(all_tk)})", use_container_width=True,
                      on_click=_check_all, args=(all_tk, True))
            b2.button("ล้างที่เลือก", use_container_width=True,
                      on_click=_check_all, args=(all_tk, False))

            HEADS = ["เลือก", "หุ้น (กดเพื่อวิเคราะห์)", "รายได้ YoY", "กำไร YoY",
                     "ลึก", "P/E", "P/BV", "D/E", "ROE %", "GM %", "NM %",
                     "ชื่อบริษัท"]
            WIDTHS = [0.5, 1.3, 1.0, 1.0, 0.6, 0.8, 0.8, 0.8, 0.9, 0.9, 0.9, 2.0]
            hd = st.columns(WIDTHS)
            for col, txt in zip(hd, HEADS):
                col.markdown(f"<span class='muted'><b>{txt}</b></span>",
                             unsafe_allow_html=True)

            # ---------- ปุ่มเปิดวิเคราะห์รายตัวแบบไม่โหลดหน้าใหม่ ----------
            # นี่คือทางแก้รากของปัญหา "กลับมาแล้วผลคัดกรองหาย"
            #
            # ลิงก์ <a href='?t=XXX'> ทำให้เบราว์เซอร์โหลดหน้าใหม่เสมอ
            #   เปิดแท็บเดิม -> session เดิมถูกทิ้ง ผลคัดกรองหาย
            #   เปิดแท็บใหม่ -> แท็บนั้นเป็น session ใหม่ที่ไม่มีผลคัดกรอง
            # ทั้งสองทางจบลงที่ "ต้องคัดกรองใหม่"
            #
            # ปุ่มของ Streamlit ทำงานผ่าน websocket เดิม ไม่มีการโหลดหน้าใหม่
            # session_state จึงอยู่ครบ กลับมาโหมดคัดกรองแล้วเจอผลเดิมทันที
            def _open_stock(tk, deep=False):
                st.session_state["jump"] = tk
                st.session_state["mode"] = M_DEEP if deep else M_ONE
                # ตั้งธงให้หน้าวิเคราะห์เริ่มคำนวณเอง ไม่ต้องกดปุ่มซ้ำ
                st.session_state["ran"] = True
                if deep:
                    # โหมดวิเคราะห์ลึกรับรายชื่อผ่าน handoff
                    # (ตัวเดียวกับที่ปุ่ม "ส่งไปวิเคราะห์ลึก" ใช้อยู่แล้ว)
                    st.session_state["handoff"] = [tk]

            picked = set()
            for _, r in res.iterrows():
                t = r["ticker"]
                cc = st.columns(WIDTHS)
                on = cc[0].checkbox(" ", key=f"cb_{t}",
                                    label_visibility="collapsed")
                # ใช้ if ธรรมดา — เขียนเป็น expression ลอย ๆ ไม่ได้
                # เพราะ Streamlit จะเอาค่าที่ได้ (None) ไปแสดงบนหน้าจอ
                if on:
                    picked.add(t)
                # ชื่อหุ้นเป็นปุ่ม — กดแล้วไปวิเคราะห์รายตัวทันที
                #
                # ใช้ปุ่มแทนลิงก์ <a href> โดยตั้งใจ
                # ลิงก์ทำให้เบราว์เซอร์โหลดหน้าใหม่ = ผลคัดกรองที่ทำมาหายหมด
                # ปุ่มทำงานผ่านการเชื่อมต่อเดิม กดกลับมาแล้วผลยังอยู่ครบ
                cc[1].button(t, key=f"tk_{t}", use_container_width=True,
                             help=f"เปิดวิเคราะห์รายตัวของ {t}",
                             on_click=_open_stock, args=(t,))
                for slot, key in ((2, "รายได้ YoY (%)"), (3, "กำไร YoY (%)")):
                    gv = pd.to_numeric(r.get(key), errors="coerce")
                    cc[slot].markdown(
                        f"<span style='color:#2e9e5b;font-weight:600'>▲ {gv:,.1f}</span>"
                        if pd.notna(gv) and gv > 0 else
                        f"<span class='muted'>{_cell(gv, 1)}</span>",
                        unsafe_allow_html=True)
                cc[4].button("🔬", key=f"go_{t}",
                             help=f"วิเคราะห์ลึก {t} — มูลค่า คุณภาพ ความเสี่ยง "
                                  "และคำแนะนำแบบเต็ม",
                             on_click=_open_stock, args=(t, True))
                cc[5].caption(_cell(r.get("P/E"), 1))
                cc[6].caption(_cell(r.get("P/BV"), 2))
                cc[7].caption(_cell(r.get("D/E"), 2))
                cc[8].caption(_cell(r.get("ROE (%)"), 1))
                cc[9].caption(_cell(r.get("อัตรากำไรขั้นต้น (%)"), 1))
                cc[10].caption(_cell(r.get("อัตรากำไรสุทธิ (%)"), 1))
                cc[11].caption(str(r["ชื่อบริษัท"])[:34])

            st.info(
                "**กดชื่อหุ้น** → วิเคราะห์รายตัว (งบ · อัตราส่วน · กราฟ)  \n"
                "**กด 🔬** → วิเคราะห์ลึก (มูลค่า · คุณภาพ · ความเสี่ยง · คำแนะนำ)  \n"
                "ทั้งสองปุ่มไม่โหลดหน้าใหม่ ผลคัดกรองจึงอยู่ครบ "
                "กดกลับมาโหมดคัดกรองแล้วเจอเหมือนเดิมทันที")

            st.session_state["picked"] = picked
            sel = [t for t in all_tk if t in picked]
            st.markdown(f"**เลือกไว้ {len(sel)} ตัว** "
                        + (f"— {', '.join(sel[:15])}" + (" ..." if len(sel) > 15 else "")
                           if sel else "— ยังไม่ได้เลือก"))

            b3, b4 = st.columns(2)
            with b3:
                st.button(f"วิเคราะห์ลึก ({len(sel)})",
                          type="primary", use_container_width=True,
                          disabled=len(sel) == 0,
                          on_click=lambda: st.session_state.update(
                              {"handoff": sel, "mode": M_DEEP}))
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
                          autocomplete="off",
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
            disc = float(w["ส่วนลด (%)"])
            note_ = ("จัดอันดับโดยให้น้ำหนัก *ส่วนลด* กับ *ความน่าเชื่อถือ* "
                     "**เท่ากัน** — เป็นการจัดอันดับตัวเลข ไม่ใช่คำแนะนำให้ซื้อ")
            if disc > 0:
                st.success(f"**อันดับ 1 ตามตัวเลข : {w['ticker']}** — "
                           f"ราคาต่ำกว่ามูลค่าที่ประเมินได้ {disc:.0f}% · "
                           f"ความน่าเชื่อถือ {w['ความน่าเชื่อถือ']}  \n{note_}")
            else:
                # ทุกตัวแพงกว่ามูลค่าที่ประเมินได้ การชูตัวใดตัวหนึ่งว่า "น่าสนใจ"
                # จะทำให้เข้าใจผิดว่าตัวนั้นถูก ทั้งที่แค่ "แพงน้อยที่สุด"
                st.warning(
                    f"**ไม่มีตัวใดราคาต่ำกว่ามูลค่าที่ประเมินได้**  \n"
                    f"ตัวที่แพงน้อยที่สุดคือ **{w['ticker']}** ซึ่งยังแพงกว่ามูลค่า "
                    f"ที่ประเมินได้ **{abs(disc):.0f}%** (ความน่าเชื่อถือ "
                    f"{w['ความน่าเชื่อถือ']})  \n"
                    "การจัดอันดับนี้บอกได้แค่ว่า *ตัวไหนแพงน้อยกว่ากัน* "
                    "ไม่ได้แปลว่าตัวนั้นน่าซื้อ")
        full = res.get("full")
        secs = res.get("sections") or {}
        view = st.radio(
            "ระดับรายละเอียด", ["ครบทุกหัวข้อ", "เฉพาะหัวข้อหลัก"],
            horizontal=True,
            help="ครบทุกหัวข้อ = แสดงทุกตัวเลขที่ระบบคำนวณไว้แล้ว "
                 "เรียงต่อกันเป็นตารางเดียว แบ่งด้วยแถบหมวด")

        if view.startswith("ครบ") and full is not None and not full.empty:
            n_rows = sum(len(t) for t in secs.values())
            st.caption(f"**{n_rows} หัวข้อ** ใน {len(secs)} หมวด · "
                       "ทุกตัวเลขคำนวณจากงบการเงินย้อนหลัง ไม่ใช่ค่าสรุปสำเร็จรูป "
                       "· หัวตารางตรึงไว้ เลื่อนลงได้โดยยังเห็นชื่อหุ้น")
            st.caption("**กดที่ชื่อหุ้นบนหัวตาราง** เพื่อเปิดวิเคราะห์รายตัว "
                       "(เปิดแท็บใหม่ ผลเปรียบเทียบในแท็บนี้ไม่หาย)")
            html_table(full, first_col="หัวข้อ", trim_year=False, fit=True,
                       link_headers=True,
                       max_height=720)
        else:
            html_table(res["table"], first_col="หัวข้อ", trim_year=False,
                       fit=True, link_headers=True)

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
        rate = len(ok) / len(df) * 100 if len(df) else 0
        metric_card(k[0], "วิเคราะห์สำเร็จ", f"{len(ok)} / {len(df)}",
                    f"{rate:.0f}%", "#2e7d32" if rate >= 60 else "#c62828")
        metric_card(k[1], "ราคาต่ำกว่ามูลค่า", f"{len(under)} ตัว")
        best = (pd.to_numeric(under["ส่วนลด (%)"], errors="coerce").max()
                if ("ส่วนลด (%)" in under.columns and not under.empty) else None)
        metric_card(k[2], "ส่วนลดสูงสุด",
                    f"{best:,.0f}%" if best is not None and pd.notna(best) else "—")

        # ---- ไม่สำเร็จสักตัว ต้องบอกสาเหตุทันที ไม่ใช่ให้ไปหาเองในกล่องพับ ----
        if ok.empty:
            errs = df["ปัญหา"].value_counts()
            st.error(
                f"**วิเคราะห์ไม่สำเร็จทั้ง {len(df)} ตัว**\n\n"
                + "\n".join(f"- **{n} ตัว** — `{m}`" for m, n in errs.head(5).items())
                + "\n\n**ถ้าเจอ `429` หรือ `Too Many Requests`** = Yahoo ปฏิเสธคำขอ "
                  "ซึ่งเกิดกับเครื่องในศูนย์ข้อมูล (รวม Streamlit Cloud) "
                  "ชั้นวิเคราะห์ลึกต้องดึงงบการเงินเต็ม จึงโดนบล็อกง่ายกว่าชั้นคัดกรองมาก\n\n"
                  "วิธีที่ได้ผลแน่นอนคือรันบน MacBook:\n\n"
                  "```\neq\npython3 screener.py --scan CMR.BK KCC.BK SRICHA.BK\n```")
        elif under.empty:
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

            # ---- ธงเตือนผลบวกลวง ----
            # ส่วนลดมหาศาลที่มาจากข้อมูลน้อยหรือคะแนนต่ำ คือรูปแบบที่ผิดบ่อยที่สุด
            # ของการทำ DCF — ไม่ใช่เพราะหุ้นถูก แต่เพราะสมมติฐานเพี้ยน
            def _suspect(r):
                w = []
                d = pd.to_numeric(r.get("ส่วนลด (%)"), errors="coerce")
                sc = pd.to_numeric(r.get("คะแนน"), errors="coerce")
                yr = pd.to_numeric(r.get("ปีข้อมูล"), errors="coerce")
                gm = pd.to_numeric(r.get("ตลาดคาดโต (%)"), errors="coerce")
                cg = pd.to_numeric(r.get("CAGR รายได้ (%)"), errors="coerce")
                if pd.notna(d) and d > 50 and pd.notna(sc) and sc < 50:
                    w.append("ส่วนลดสูงแต่คะแนนต่ำ")
                if pd.notna(yr) and yr < 6:
                    w.append(f"ข้อมูลแค่ {yr:.0f} ปี")
                # ตลาดคาดให้หดตัวแรง ทั้งที่อดีตโตดี = ตลาดเห็นอะไรที่งบยังไม่บอก
                if pd.notna(gm) and pd.notna(cg) and gm < -10 and cg > 0:
                    w.append("ตลาดคาดว่าจะหดตัว")
                return " · ".join(w)

            show["⚠️"] = [_suspect(r) for _, r in show.iterrows()]
            show.index = [str(i) for i in range(1, len(show) + 1)]
            html_table(show, first_col="อันดับ", trim_year=False,
                       max_height=520, link_cols=("ticker",),
                       dec_cols={"คะแนน": 0, "ปีข้อมูล": 0})
            # ---------- ตารางเปรียบเทียบเต็มรูปแบบ ----------
            # ใช้ผลที่วิเคราะห์เสร็จแล้ว ไม่ต้องดึงข้อมูลใหม่
            from screener import build_compare
            cmp_full = build_compare(df, order=list(under["ticker"]))
            fullt = cmp_full.get("full")
            if fullt is not None and not fullt.empty:
                st.markdown("---")
                st.markdown("### 📊 ตารางเปรียบเทียบเต็มรูปแบบ")
                nsec = len(cmp_full.get("sections") or {})
                ndata = len(fullt) - nsec
                st.caption(
                    f"**{ndata} หัวข้อ** ใน {nsec} หมวด รวมสมมติฐานที่ใช้ประเมินมูลค่า "
                    "(WACC, g1, g2, สัดส่วนมูลค่าสุดท้าย) · "
                    "ใช้ผลที่วิเคราะห์ไปแล้ว ไม่ได้ดึงข้อมูลใหม่")
                html_table(fullt, first_col="หัวข้อ", trim_year=False, fit=True,
                           max_height=720)
                st.download_button(
                    "ดาวน์โหลดตารางเปรียบเทียบ (CSV)",
                    fullt.to_csv().encode("utf-8-sig"),
                    "เปรียบเทียบเชิงลึก.csv", "text/csv")

            st.caption(
                "**กดที่ชื่อหุ้น** เพื่อเปิดการวิเคราะห์รายตัวพร้อมรายงาน PDF  \n"
                "**ธง ⚠️** — `ส่วนลดสูงแต่คะแนนต่ำ` มูลค่าที่ประเมินได้อาจมาจาก"
                "สมมติฐานที่ไม่มั่นคง · `ข้อมูลแค่ N ปี` สั้นเกินกว่าจะครอบคลุม"
                "รอบธุรกิจหนึ่งรอบ (หุ้นวัฏจักรอย่างโรงกลั่นต้องการอย่างน้อย 10 ปี) · "
                "`ตลาดคาดว่าจะหดตัว` ราคาปัจจุบันสะท้อนว่าตลาดเห็นอนาคตแย่กว่าที่งบในอดีตบอก")

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

# ---------- ปุ่มกลับไปหน้าคัดกรอง ----------
# เห็นได้ตลอด ไม่ใช่เฉพาะตอนกดมาจากตาราง เพราะแท็บที่เปิดจากลิงก์
# เป็น session ใหม่ที่ไม่รู้ว่าตัวเองมาจากไหน
# ผลคัดกรองจะถูกกู้กลับมาให้เองจากที่บันทึกไว้ ไม่ต้องดึงใหม่
try:
    import snapshot as _SNAP2
    _last_scope = _SNAP2.get_last_scope()
except Exception:
    _last_scope = {}
if _last_scope.get("snap_key"):
    _bk = st.columns([1, 3])
    _bk[0].button("↩️ กลับไปหน้าคัดกรอง", use_container_width=True,
                  on_click=lambda: st.session_state.update({"mode": M_SCREEN}))
    _bk[1].caption(f"ผลคัดกรองล่าสุด **{_last_scope['snap_key']}** "
                   "ถูกบันทึกไว้แล้ว — กดกลับไปได้เลย ไม่ต้องคัดกรองใหม่")

# ---------------------------------------------------------------------------
# ช่องเลือกหุ้น
#
# ค่าเริ่มต้นคือ "เลือกจากรายชื่อ" เสมอ ไม่ว่ามาจากทางไหน
#
# เดิมตั้งไว้ว่า ถ้ามาจากการกดชื่อหุ้นในตาราง (JUMP) ให้สลับไปโหมดพิมพ์เอง
# ซึ่งทำให้เจอช่องพิมพ์ข้อความเปล่า ๆ แล้วเบราว์เซอร์บนมือถือเสนอ
# รายชื่อจากสมุดโทรศัพท์ขึ้นมาแทนรายชื่อหุ้น
#
# ตอนนี้ถ้ามี JUMP จะไปเลือกตัวนั้นในรายชื่อให้เลย
# จะสลับเป็นโหมดพิมพ์เองก็ต่อเมื่อหาหุ้นตัวนั้นในรายชื่อไม่เจอจริง ๆ
# ---------------------------------------------------------------------------

# แผนที่ย้อนกลับ ticker -> ข้อความในรายชื่อ เพื่อเลือกตัวที่ถูกล่วงหน้าได้
_REV = {}
for _o in OPTIONS:
    _REV.setdefault(LOOKUP.get(_o, str(_o).split(" ")[0]).upper(), _o)

_jump_in_list = bool(JUMP) and JUMP.upper() in _REV
_need_manual = (not OPTIONS) or (bool(JUMP) and not _jump_in_list)

manual = st.toggle("พิมพ์ ticker เอง (สำหรับหุ้นที่ไม่มีในรายชื่อ)",
                   value=_need_manual, key="manual_tk",
                   help="ปกติไม่ต้องเปิด — ให้เลือกจากรายชื่อจะได้ไม่พิมพ์ผิด "
                        "เปิดเฉพาะตอนหาหุ้นที่ต้องการในรายชื่อไม่เจอ")
if bool(JUMP) and not _jump_in_list:
    st.caption(f"ไม่พบ **{JUMP}** ในรายชื่อตั้งต้น จึงเปิดโหมดพิมพ์เองให้อัตโนมัติ")

c1, c2 = st.columns([3, 1])
with c1:
    if manual or not OPTIONS:
        ticker = st.text_input("ใส่ชื่อย่อหุ้น", value=JUMP or "AAPL",
                               key=f"tk_{JUMP or 'default'}",
                               autocomplete="off",
                               placeholder="เช่น AAPL, MSFT, PTT.BK",
                               label_visibility="collapsed").strip().upper()
    else:
        # selectbox ของ Streamlit กรองรายชื่อให้ทันทีที่พิมพ์
        # (ค้นได้ทั้งชื่อย่อและชื่อบริษัท เช่น พิมพ์ "ปตท" หรือ "Apple")
        if _jump_in_list:
            default = OPTIONS.index(_REV[JUMP.upper()])
        elif "AAPL — Apple Inc." in OPTIONS:
            default = OPTIONS.index("AAPL — Apple Inc.")
        else:
            default = 0
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

t0, t1, t2, t3, t4, t5, t6, t7, t9, t8 = st.tabs(
    ["⭐ คำแนะนำ", "ภาพรวม", "ผลประกอบการ", "อัตราส่วน", "ประเมินมูลค่า",
     "ช่วงราคา", "พยากรณ์ 10 ปี", "ความเสี่ยง", "คุณภาพ & กูรู", "ข่าว & XD"])

with t0:
    import recommend as RC
    import news_ai as NA
    import risk as _RK
    import quality as _QL
    import forecast as _FC

    @st.cache_data(show_spinner=False, ttl=1800)
    def _reco(tk, _rid):
        vv = dict(v)
        vv["ความน่าเชื่อถือ"] = b.get("ความน่าเชื่อถือ")
        _rf = v.get("wacc_detail", {}).get("พันธบัตร (rf)")
        nw = NA.analyze(tk, limit=25)
        return RC.build(data, R, v=vv,
                        risk=_RK.assess(data, R),
                        qual=_QL.assess_all(data, R, v=v, rf=_rf),
                        fc=_FC.forecast_all(R), news=nw), nw

    with st.spinner("กำลังรวมผลจากทุกโมดูล..."):
        RECO, NEWSAI = _reco(ticker, id(R))

    if not RECO.get("ใช้ได้"):
        st.error(RECO.get("เหตุผล", "สรุปคำแนะนำไม่ได้"))
    else:
        st.markdown(
            f"<div style='background:{RECO['สี']}18;border-left:8px solid "
            f"{RECO['สี']};padding:18px 22px;border-radius:8px;margin:6px 0 14px 0'>"
            f"<div style='font-size:2.1rem;font-weight:800;color:{RECO['สี']};"
            f"line-height:1.15'>{RECO['คำแนะนำ']}</div>"
            f"<div style='font-size:1rem;opacity:.85;margin-top:4px'>"
            f"คะแนนรวม <b>{RECO['คะแนนรวม']:.1f} / 100</b> · "
            f"ความมั่นใจ <b>{RECO['ความมั่นใจ (%)']:.0f}%</b></div>"
            f"<div style='margin-top:6px'>{RECO['คำอธิบายระดับ']}</div></div>",
            unsafe_allow_html=True)

        rr = st.columns(3)
        metric_card(rr[0], "ราคาปัจจุบัน",
                    f"{RECO['ราคาปัจจุบัน']:,.2f}" if RECO.get("ราคาปัจจุบัน") else "—",
                    cur)
        metric_card(rr[1], "มูลค่าที่ประเมินได้",
                    f"{RECO['มูลค่าที่ประเมินได้']:,.2f}"
                    if RECO.get("มูลค่าที่ประเมินได้") else "—",
                    "ค่ากลางทุกวิธี")
        d_ = v.get("ส่วนต่างจากราคา (%)")
        metric_card(rr[2], "ส่วนต่างจากราคา",
                    f"{d_:+.1f}%" if d_ is not None else "—", None,
                    "#2e7d32" if (d_ or 0) > 0 else "#c62828")

        st.markdown("#### ปัจจัยที่ใช้ตัดสิน")
        ft = RECO["ตารางปัจจัย"].copy()
        ft = ft[["คะแนน", "น้ำหนักจริง (%)", "ดันคะแนน", "หลักฐาน"]]
        html_table(ft, first_col="ด้าน", trim_year=False, fit=True,
                   sign_cols=("ดันคะแนน",), left_cols=("หลักฐาน",),
                   dec_cols={"คะแนน": 1, "น้ำหนักจริง (%)": 0, "ดันคะแนน": 1})
        st.caption("**ดันคะแนน** = ด้านนั้นดันคะแนนรวมขึ้น/ลงกี่คะแนน "
                   "เทียบกับถ้าได้คะแนนกลาง ๆ (50)")

        e1, e2 = st.columns(2)
        with e1:
            st.markdown("**🟢 หนุนมากที่สุด**")
            for f in RECO["หนุนมากที่สุด"]:
                st.markdown(f"- **{f['ด้าน']}** ({f['ดันคะแนน']:+.1f})  \n"
                            f"<span class='muted'>{f['หลักฐาน']}</span>",
                            unsafe_allow_html=True)
        with e2:
            st.markdown("**🔴 ฉุดมากที่สุด**")
            if RECO["ฉุดมากที่สุด"]:
                for f in RECO["ฉุดมากที่สุด"]:
                    st.markdown(f"- **{f['ด้าน']}** ({f['ดันคะแนน']:+.1f})  \n"
                                f"<span class='muted'>{f['หลักฐาน']}</span>",
                                unsafe_allow_html=True)
            else:
                st.caption("ไม่มีด้านใดฉุดคะแนนลง")

        if RECO["อะไรจะเปลี่ยนข้อสรุป"]:
            st.markdown("#### 🔀 อะไรจะทำให้ข้อสรุปเปลี่ยน")
            for t_ in RECO["อะไรจะเปลี่ยนข้อสรุป"]:
                st.markdown(f"- {t_['ถ้า']} "
                            f"({t_['ห่างจากราคาปัจจุบัน']}) → "
                            f"**{t_['จะกลายเป็น']}**")

        st.info(
            "**ข้อสรุปนี้มาจากกฎถ่วงน้ำหนักที่เขียนไว้ชัดเจน ไม่ใช่โมเดลภาษา**  \n"
            "ข้อมูลชุดเดิมจะให้คำตอบเดิมเสมอ และตรวจย้อนได้ว่าคะแนนแต่ละด้าน"
            "มาจากตัวเลขไหน — ต่างจากการให้ AI ตอบเป็นภาษา ซึ่งตอบไม่เหมือนกัน"
            "สองครั้งติดและตรวจสอบไม่ได้")
        st.error("⚠️ **ไม่ใช่คำแนะนำการลงทุน** — เป็นการสรุปตัวเลขเพื่อการศึกษา "
                 "โปรดตรวจสอบด้วยตนเองก่อนตัดสินใจ")

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
    st.markdown(f"**งบกำไรขาดทุน** — หน่วยล้าน {cur} "
                f"ยกเว้นกำไรต่อหุ้นซึ่งเป็น {cur} ต่อหุ้น")
    from statements import scale_for_display
    _inc, _dr = scale_for_display(S["income"])
    html_table(_inc, dec=0, dec_rows=_dr)

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
    # ---------- แนวทางตามกลุ่มธุรกิจ ----------
    grp = v.get("กลุ่มธุรกิจ", "ทั่วไป")
    play = v.get("แนวทางตามกลุ่ม") or {}
    if play:
        st.markdown(f"### จัดอยู่กลุ่ม **{grp}**")
        pc1, pc2 = st.columns(2)
        pc1.success("**ควรใช้** — " + " · ".join(play.get("ควรใช้", [])))
        if play.get("ห้ามใช้"):
            pc2.error("**ไม่ควรใช้** — " + " · ".join(play["ห้ามใช้"]))
        st.caption(play.get("เหตุผล", ""))

    # ---------- รายละเอียดวิธีเฉพาะกลุ่ม ----------
    ext = v.get("วิธีเฉพาะกลุ่ม") or {}

    ri = ext.get("Residual Income")
    if ri and ri.get("ใช้ได้"):
        with st.expander("🏦 Residual Income — มูลค่าจากงบดุล + กำไรส่วนเกิน"):
            kv_table([
                ("มูลค่าทางบัญชีต่อหุ้น", ri["มูลค่าทางบัญชีต่อหุ้น"]),
                ("+ กำไรส่วนเกินคิดลด", ri["PV กำไรส่วนเกิน ต่อหุ้น"]),
                ("= มูลค่าต่อหุ้น", ri["มูลค่าต่อหุ้น"]),
                ("ROE เริ่มต้น (%)", ri["ROE เริ่มต้น (%)"]),
                ("ต้นทุนส่วนทุน (%)", ri["ต้นทุนส่วนทุน (%)"]),
                ("อัตราจ่ายปันผล (%)", ri["อัตราจ่ายปันผล (%)"]),
                ("สัดส่วนที่มาจากงบดุล (%)", ri["สัดส่วนจากงบดุล (%)"]),
            ], fit=True)
            st.caption(
                f"**{ri['สัดส่วนจากงบดุล (%)']:.0f}% ของมูลค่ามาจากงบดุลที่ตรวจสอบได้** "
                "— ยิ่งสูงยิ่งพึ่งการเดาอนาคตน้อย ต่างจาก DCF ที่ 60–80% "
                "มาจากมูลค่าสุดท้ายซึ่งเป็นการเดาล้วน  \n"
                "โมเดลนี้ให้ ROE ค่อย ๆ ลดลงจนเท่าต้นทุนส่วนทุนใน 10 ปี "
                "เพราะคู่แข่งจะกัดกร่อนกำไรส่วนเกิน — เป็นสมมติฐานแบบอนุรักษ์นิยม")
            html_table(ri["ตารางรายปี"].set_index("ปีที่"), first_col="ปีที่",
                       trim_year=False, fit=True, max_height=280)

    mid = ext.get("กำไรกลางวัฏจักร")
    if mid and mid.get("ใช้ได้"):
        with st.expander("🔄 กำไรกลางวัฏจักร — แก้ปัญหา P/E หลอกในหุ้นวัฏจักร",
                         expanded=True):
            kv_table([
                (f"อัตรากำไรสุทธิเฉลี่ย {mid['จำนวนปีที่ใช้']} ปี (%)",
                 mid["อัตรากำไรสุทธิเฉลี่ย (%)"]),
                ("อัตรากำไรสุทธิปีล่าสุด (%)", mid["อัตรากำไรสุทธิปีล่าสุด (%)"]),
                ("EPS ปรับฐาน", mid["EPS ปรับฐาน"]),
                ("EPS ปีล่าสุด", mid["EPS ปีล่าสุด"]),
                ("P/E อ้างอิง", mid["P/E อ้างอิง"]),
                ("CAPE (ราคา ÷ EPS เฉลี่ย)", mid.get("CAPE")),
                ("มูลค่าต่อหุ้น", mid["มูลค่าต่อหุ้น"]),
            ], fit=True)
            st.caption(
                "**หุ้นวัฏจักรมี P/E ต่ำสุดตอนใกล้จุดพีค** และสูงสุดตอนใกล้จุดต่ำสุด "
                "— ตรงข้ามกับสัญชาตญาณ  \n"
                "วิธีนี้ใช้ *อัตรากำไรเฉลี่ยทั้งรอบ × รายได้ปีล่าสุด* "
                "จึงได้ความสามารถทำกำไรโดยเฉลี่ยบนขนาดกิจการวันนี้")
            for wmsg in mid.get("คำเตือน", []):
                st.warning(wmsg)

    ff = ext.get("P/FFO")
    if ff and ff.get("ใช้ได้"):
        with st.expander("🏢 P/FFO — วิธีมาตรฐานของ REIT", expanded=True):
            kv_table([
                ("กำไรสุทธิต่อหุ้น", ff["กำไรสุทธิต่อหุ้น"]),
                ("+ ค่าเสื่อมที่บวกกลับ (ล้าน)", ff["ค่าเสื่อมที่บวกกลับ (ล้าน)"]),
                ("FFO ต่อหุ้น", ff["FFO ต่อหุ้น"]),
                ("FFO สูงกว่ากำไรสุทธิ (เท่า)", ff["FFO สูงกว่ากำไรสุทธิ (เท่า)"]),
                ("P/FFO ปัจจุบัน", ff["P/FFO ปัจจุบัน"]),
                ("P/FFO อ้างอิง", ff["P/FFO อ้างอิง"]),
                ("มูลค่าต่อหุ้น", ff["มูลค่าต่อหุ้น"]),
            ], fit=True)
            st.caption(
                "บัญชีบังคับตัดค่าเสื่อมอาคารทุกปี ทั้งที่อสังหาฯ ที่ดูแลดี"
                "มักมีมูลค่าเพิ่มขึ้น ค่าเสื่อมจึงไม่ใช่เงินสดที่จ่ายออกจริง  \n"
                "**ข้อจำกัด** — FFO มาตรฐานต้องหักกำไรจากการขายทรัพย์สินออกด้วย "
                "แต่งบรวมไม่ได้แยกไว้ ปีที่ REIT ขายทรัพย์สินตัวเลขจะสูงเกินจริง")

    mc = ext.get("Monte Carlo")
    if mc and mc.get("ใช้ได้"):
        with st.expander(f"🎲 Monte Carlo — สุ่ม {mc['จำนวนรอบที่สำเร็จ']:,} รอบ"):
            pct = mc["เปอร์เซ็นไทล์"]
            mm = st.columns(5)
            for col, key, lbl in zip(mm, ["P10", "P25", "P50", "P75", "P90"],
                                     ["แย่ (P10)", "P25", "กลาง (P50)",
                                      "P75", "ดี (P90)"]):
                metric_card(col, lbl, f"{pct[key]:,.2f}")
            if "โอกาสมูลค่า > ราคา (%)" in mc:
                st.markdown(
                    f"- มูลค่า **สูงกว่า**ราคาปัจจุบัน : "
                    f"**{mc['โอกาสมูลค่า > ราคา (%)']:.0f}%** ของรอบที่สุ่ม  \n"
                    f"- สูงกว่าราคา 1.3 เท่า : "
                    f"{mc['โอกาสมูลค่า > ราคา 1.3 เท่า (%)']:.0f}%  \n"
                    f"- ต่ำกว่าราคา 0.7 เท่า : "
                    f"{mc['โอกาสมูลค่า < ราคา 0.7 เท่า (%)']:.0f}%")
            st.warning(
                "**อ่านเป็นความไวต่อสมมติฐาน ไม่ใช่ความน่าจะเป็นจริง** — "
                "ตัวเลข % ดูเป็นวิทยาศาสตร์ แต่เป็นจริงก็ต่อเมื่อสมมติฐาน"
                "เรื่องการกระจายของ WACC และ g ถูกต้อง ซึ่งเราไม่มีทางรู้")

    for name, why in (v.get("ต้องกรอกเอง") or []):
        st.info(f"**{name} ต้องกรอกข้อมูลเอง** — {why}  \n"
                "ดูเครื่องคิดเลขด้านล่างสุดของแท็บนี้")

    st.markdown("---")
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

    # ---------- เครื่องคิดเลข RNAV / SOTP (กรอกเอง) ----------
    # ไม่คำนวณอัตโนมัติ เพราะตัวเลขที่ต้องใช้ไม่มีในงบการเงินรวม
    # การเดาแล้วแสดงผลเหมือนของจริง อันตรายกว่าการไม่แสดงเลย
    st.markdown("---")
    with st.expander("🧮 เครื่องคิดเลข RNAV และ SOTP (กรอกข้อมูลเอง)"):
        import valuation_ext as VE
        try:
            from valuation import get_shares_outstanding
            _sh = get_shares_outstanding(data)
        except Exception:
            _sh = None

        rn_tab, so_tab = st.tabs(["RNAV (อสังหาริมทรัพย์)", "SOTP (โฮลดิ้ง)"])

        with rn_tab:
            st.caption(
                "**RNAV = มูลค่าทางบัญชี + ส่วนเพิ่มจากการตีราคาสินทรัพย์ใหม่**  \n"
                "งบการเงินบันทึกที่ดินด้วย *ราคาทุนตอนซื้อ* — ที่ดินที่ซื้อเมื่อ 30 ปีก่อน "
                "ยังอยู่ในงบด้วยราคาเดิม ส่วนต่างนี้หาได้จากรายงานประจำปี "
                "รายงานผู้ประเมินอิสระ หรือบทวิเคราะห์")
            try:
                _bv = float(pd.to_numeric(
                    R["raw"]["equity"], errors="coerce").dropna().iloc[-1])
            except Exception:
                _bv = 0.0
            r1, r2, r3 = st.columns(3)
            bv_in = r1.number_input("ส่วนของผู้ถือหุ้นตามบัญชี (ล้าน)",
                                    value=float(_bv / 1e6), step=100.0,
                                    key="rnav_bv")
            sur_in = r2.number_input("ส่วนเพิ่มจากการตีราคาใหม่ (ล้าน)",
                                     value=0.0, step=100.0, key="rnav_sur",
                                     help="ราคาตลาดของที่ดินและโครงการ "
                                          "ลบด้วยราคาทุนที่บันทึกในงบ")
            dis_in = r3.number_input("ส่วนลดที่ตลาดให้ (%)", 0.0, 60.0, 20.0, 5.0,
                                     key="rnav_dis",
                                     help="อสังหาฯ ไทยมักซื้อขายต่ำกว่า RNAV "
                                          "เพราะสภาพคล่องต่ำและความไม่แน่นอน"
                                          "ของการขายโครงการ")
            if _sh and (bv_in or sur_in):
                rr = VE.rnav(bv_in * 1e6, _sh,
                             revaluations=[("ตีราคาใหม่", sur_in * 1e6)],
                             discount=dis_in / 100)
                kv_table([("RNAV ต่อหุ้น (ก่อนส่วนลด)",
                           rr["RNAV ต่อหุ้น (ก่อนส่วนลด)"]),
                          (f"หลังส่วนลด {dis_in:.0f}%", rr["มูลค่าต่อหุ้น"]),
                          ("ราคาปัจจุบัน", price)], fit=True)
                if price:
                    d = (rr["มูลค่าต่อหุ้น"] / price - 1) * 100
                    st.markdown(f"ส่วนต่างจากราคา : **{d:+.1f}%**")

        with so_tab:
            st.caption(
                "**ประเมินแต่ละธุรกิจย่อยด้วยวิธีที่เหมาะกับธุรกิจนั้น แล้วรวมกัน**  \n"
                "ส่วนลดโฮลดิ้งมีเพราะผู้ถือหุ้นบริษัทแม่ไม่ได้ถือธุรกิจย่อยโดยตรง "
                "— มีค่าใช้จ่ายสำนักงานใหญ่ ภาษีซ้อนตอนจ่ายปันผลขึ้นมา "
                "และเลือกไม่ได้ว่าจะถือธุรกิจไหน")
            n_seg = st.number_input("จำนวนธุรกิจย่อย", 1, 8, 2, 1, key="sotp_n")
            segs = []
            for i in range(int(n_seg)):
                c = st.columns([2, 1.4, 1, 1.2])
                nm = c[0].text_input("ชื่อธุรกิจ", key=f"sg_n{i}",
                                     autocomplete="off",
                                     placeholder=f"ธุรกิจที่ {i+1}")
                base_v = c[1].number_input("ตัวเลขฐาน (ล้าน)", value=0.0,
                                           step=100.0, key=f"sg_v{i}",
                                           help="ปกติใช้ EBITDA หรือกำไรสุทธิ")
                mult = c[2].number_input("ตัวคูณ (เท่า)", 0.0, 60.0, 10.0, 0.5,
                                         key=f"sg_m{i}")
                stake = c[3].number_input("ถือหุ้น (%)", 0.0, 100.0, 100.0, 5.0,
                                          key=f"sg_s{i}")
                if base_v:
                    segs.append({"ชื่อ": nm or f"ธุรกิจที่ {i+1}",
                                 "ตัวเลข": base_v * 1e6, "ตัวคูณ": mult,
                                 "ฐาน": "EBITDA", "สัดส่วนถือหุ้น": stake / 100})
            s1, s2 = st.columns(2)
            try:
                _nd = float(pd.to_numeric(
                    R["raw"]["net_debt"], errors="coerce").dropna().iloc[-1])
            except Exception:
                _nd = 0.0
            nd_in = s1.number_input("หนี้สินสุทธิระดับบริษัทแม่ (ล้าน)",
                                    value=float(_nd / 1e6), step=100.0,
                                    key="sotp_nd")
            hd_in = s2.number_input("ส่วนลดโฮลดิ้ง (%)", 0.0, 50.0, 15.0, 5.0,
                                    key="sotp_hd")
            if segs and _sh:
                ss = VE.sotp(segs, net_debt=nd_in * 1e6, shares=_sh,
                             holding_discount=hd_in / 100)
                html_table(ss["ตารางธุรกิจย่อย"].set_index("ธุรกิจ"),
                           first_col="ธุรกิจ", trim_year=False, fit=True,
                           left_cols=("ฐานที่ใช้",))
                kv_table([("มูลค่าส่วนผู้ถือหุ้นต่อหุ้น (ก่อนส่วนลด)",
                           ss["ก่อนส่วนลด ต่อหุ้น"]),
                          (f"หลังส่วนลดโฮลดิ้ง {hd_in:.0f}%", ss["มูลค่าต่อหุ้น"]),
                          ("ราคาปัจจุบัน", price)], fit=True)
                if price:
                    d = (ss["มูลค่าต่อหุ้น"] / price - 1) * 100
                    st.markdown(f"ส่วนต่างจากราคา : **{d:+.1f}%**")

with t5:
    show_chart(RP.chart_price_bands(data, b))
    rows = []
    for n, (lo, hi) in b["bands"].items():
        rng = (f"มากกว่า {lo:,.2f}" if hi == float("inf")
               else f"ต่ำกว่า {hi:,.2f}" if lo == 0 else f"{lo:,.2f} – {hi:,.2f}")
        mark = "  ◀ ราคาปัจจุบัน" if n == zone else ""
        rows.append((n, f"{rng} {cur}{mark}"))
    kv_table(rows, fit=True)
    st.markdown(f"**ส่วนเผื่อความปลอดภัย {b['mos ที่ใช้']:.0%} — คำนวณจาก**")
    for r in b["mos_detail"]["เหตุผล"]:
        st.markdown(f"- {r}")

with t6:
    import forecast as FC

    st.markdown("### 📈 พยากรณ์ 10 ปี × 3 ฉาก")
    st.caption(
        "ทุกสมมติฐานสกัดจาก**งบย้อนหลังของหุ้นตัวนี้เอง** ไม่ได้ตั้งขึ้นมาลอย ๆ "
        "แล้วปรับด้วยหลัก 2 ข้อ : การเติบโตจางลงเสมอ และอัตรากำไรกลับสู่ค่าเฉลี่ย")

    fy1, fy2 = st.columns([1, 3])
    n_years = fy1.slider("จำนวนปี", 3, 10, 10, key="fc_years")

    @st.cache_data(show_spinner=False, ttl=1800)
    def _fc(tk, yrs, _rid):
        return FC.forecast_all(R, years=yrs)

    FCR = _fc(ticker, n_years, id(R))

    if not FCR.get("ใช้ได้"):
        st.error(f"พยากรณ์ไม่ได้ — {FCR.get('เหตุผล')}")
    else:
        asm = FCR["ฉาก"]["Base"]["สมมติฐาน"]
        for wmsg in FCR.get("คำเตือน", []):
            st.warning(wmsg)

        with st.expander("🔍 สมมติฐานที่สกัดจากงบย้อนหลัง (กดดูที่มาของทุกตัวเลข)"):
            kv_table([(k, asm[k]) for k in (
                "จำนวนปีข้อมูล", "อัตราโตรายได้ย้อนหลัง (%)",
                "อัตรากำไรขั้นต้น ค่ากลาง (%)", "อัตรากำไรขั้นต้น ปีล่าสุด (%)",
                "อัตรากำไรสุทธิ ค่ากลาง (%)", "อัตรากำไรสุทธิ ปีล่าสุด (%)",
                "CapEx / รายได้ (%)", "OCF / รายได้ (%)",
                "อัตราจ่ายปันผล (%)", "อัตราเปลี่ยนจำนวนหุ้น (%)")
                if asm.get(k) is not None], fit=True)
            st.caption(
                "**ค่ากลาง vs ปีล่าสุด** — ถ้าอัตรากำไรปีล่าสุดสูงกว่าค่ากลางมาก "
                "โมเดลจะค่อย ๆ ดึงกลับหาค่ากลางภายใน 5 ปี เพราะกำไรที่ดีผิดปกติ"
                "จะดึงคู่แข่งเข้ามา  \n"
                "นี่คือกลไกที่ป้องกันไม่ให้เกิดกรณีแบบ BCP ที่เอาปีพีคไปคาดว่า"
                "จะดีตลอดไป")

        # ---- เทียบ 3 ฉาก ----
        st.markdown("#### เทียบ 3 ฉาก ณ ปีสุดท้าย")
        cmp3 = FCR["เทียบ 3 ฉาก (ปีสุดท้าย)"].copy()
        for c in cmp3.columns:
            cmp3[c] = pd.to_numeric(cmp3[c], errors="coerce")
        big = cmp3.loc[[i for i in cmp3.index
                        if i not in ("EPS", "เงินปันผลต่อหุ้น")]] / 1e6
        small = cmp3.loc[[i for i in cmp3.index
                          if i in ("EPS", "เงินปันผลต่อหุ้น")]]
        st.markdown(f"**หน่วยล้าน {cur}**")
        html_table(big, first_col="รายการ", trim_year=False, fit=True, dec=0)
        st.markdown(f"**ต่อหุ้น ({cur})**")
        html_table(small, first_col="รายการ", trim_year=False, fit=True, dec=2)

        # ---- ตารางรายฉาก ----
        pick = st.radio("ดูตารางเต็มของฉาก", ["Base", "Bear", "Bull"],
                        horizontal=True, key="fc_pick")
        f = FCR["ฉาก"][pick]
        st.info(f"**{pick}** — {f['คำอธิบายฉาก']}  \n"
                f"อัตราโตปีแรก **{f['อัตราโตปีแรก (%)']:.1f}%** → "
                f"ปีสุดท้าย **{f['อัตราโตปีสุดท้าย (%)']:.1f}%**")

        d = f["ตาราง"].copy()
        for c in ("รายได้", "ต้นทุนขาย", "กำไรขั้นต้น", "กำไรดำเนินงาน",
                  "กำไรสุทธิ", "FCF"):
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors="coerce") / 1e6
        d = d.drop(columns=["จำนวนหุ้น"], errors="ignore")
        d.index = [f"ปีที่ {int(x)}" for x in d["ปีที่"]]
        d = d.drop(columns=["ปีที่"])
        st.caption(f"หน่วยล้าน {cur} ยกเว้น EPS · เงินปันผลต่อหุ้น · และคอลัมน์ %")
        html_table(d, first_col="ปี", trim_year=False, fit=True, max_height=480,
                   dec_cols={"EPS": 2, "เงินปันผลต่อหุ้น": 3})

        st.download_button(
            f"ดาวน์โหลดพยากรณ์ {pick} (CSV)",
            f["ตาราง"].to_csv(index=False).encode("utf-8-sig"),
            f"พยากรณ์_{ticker}_{pick}.csv", "text/csv")

        st.error(
            "⚠️ **นี่คือการต่อเส้นแนวโน้มจากอดีต ไม่ใช่การทำนายอนาคต**  \n"
            "โมเดลไม่รู้ว่าบริษัทกำลังจะออกสินค้าใหม่ เสียลูกค้ารายใหญ่ "
            "หรือโดนกฎหมายใหม่  \n"
            "**ปีที่ 1–3 พอใช้อ้างอิงได้ · ปีที่ 8–10 เป็นเพียงกรอบความเป็นไปได้**")


with t7:
    import risk as RK

    st.markdown("### ⚠️ ประเมินความเสี่ยง 12 ด้าน")

    @st.cache_data(show_spinner=False, ttl=1800)
    def _risk(tk, _rid):
        return RK.assess(data, R)

    RS = _risk(ticker, id(R))
    tot = RS.get("คะแนนรวม")

    rk = st.columns(3)
    metric_card(rk[0], "คะแนนความเสี่ยงรวม",
                f"{tot:.0f} / 100" if tot is not None else "—",
                RS.get("ระดับ"),
                "#2e7d32" if (tot or 0) < 40 else
                "#ef6c00" if (tot or 0) < 60 else "#c62828")
    metric_card(rk[1], "มาจากตัวเลขจริง",
                f"{RS['สัดส่วนจากตัวเลขจริง (%)']:.0f}%",
                "ของน้ำหนักทั้งหมด")
    top = RS.get("เสี่ยงสูงสุด") or []
    metric_card(rk[2], "ด้านที่เสี่ยงที่สุด",
                top[0][0] if top else "—",
                f"{top[0][1]:.0f} คะแนน" if top else None)

    st.caption(
        "**0 = ไม่มีความเสี่ยง · 100 = เสี่ยงสูงสุด** — คะแนนรวมถ่วงน้ำหนัก "
        "โดยด้านที่คำนวณจากงบได้น้ำหนักมากกว่า เพราะมีหลักฐานรองรับ")

    tsum = RS["ตารางสรุป"].copy()
    html_table(tsum, first_col="ด้าน", trim_year=False, fit=True, dec=0,
               left_cols=("ระดับ", "ที่มา"),
               dec_cols={"คะแนน": 0, "น้ำหนัก": 1})

    st.caption(
        "**ความหมายของ *ที่มา*** — นี่คือส่วนที่สำคัญที่สุดของหน้านี้  \n"
        "`คำนวณ` วัดจากงบการเงินโดยตรง ตรวจสอบย้อนได้ทุกตัว · "
        "`กลุ่ม` ประเมินจากลักษณะอุตสาหกรรม **ไม่ได้มาจากงบของบริษัทนี้** "
        "เป็นจุดตั้งต้นให้ปรับตามความรู้ที่อาจารย์มี · "
        "`ต้องดูเอง` ไม่มีข้อมูลให้ประเมินอัตโนมัติ")

    st.markdown("#### รายละเอียดด้านที่คำนวณจากงบ")
    for name in ("Financial Risk", "Business Risk", "Competition"):
        dd = RS["ด้าน"].get(name) or {}
        if not dd.get("รายละเอียด"):
            continue
        sc = dd.get("คะแนน")
        with st.expander(f"{name} — {sc:.0f} คะแนน ({RK.level(sc)})"
                         if sc is not None else name):
            for it in dd["รายละเอียด"]:
                rc = st.columns([2.2, 1, 1, 4])
                rc[0].markdown(f"**{it['ตัวชี้วัด']}**")
                # ห้ามตั้งชื่อตัวแปรว่า v — จะทับผลประเมินมูลค่าที่ใช้ทั้งหน้า
                iv = it["ค่า"]
                rc[1].markdown(f"{iv:,.2f}" if isinstance(iv, float) else str(iv))
                rc[2].markdown(f"เสี่ยง **{it['คะแนนเสี่ยง']:.0f}**")
                rc[3].caption(it["เกณฑ์"])

    st.markdown("#### ด้านที่ประเมินจากลักษณะอุตสาหกรรม")
    st.caption("ตัวเลขเหล่านี้ **ไม่ได้มาจากงบการเงินของบริษัทนี้** "
               "— เป็นค่าตั้งต้นตามอุตสาหกรรม ควรปรับตามที่อาจารย์รู้จริง")
    for name in ("Country Risk", "Currency Risk", "Legal/Regulatory",
                 "Technology Risk", "Disruption Risk", "AI Risk",
                 "Cyber Risk", "Climate Risk"):
        dd = RS["ด้าน"].get(name) or {}
        sc = dd.get("คะแนน")
        if sc is None:
            continue
        c = st.columns([1.6, 0.8, 1.2, 5])
        c[0].markdown(f"**{name}**")
        c[1].markdown(f"**{sc:.0f}**")
        c[2].markdown(RK.level(sc))
        c[3].caption(dd.get("คำอธิบาย", ""))

    kp = RS["ด้าน"].get("Key Person Risk") or {}
    st.markdown("#### Key Person Risk — ต้องประเมินเอง")
    st.info(kp.get("คำอธิบาย", "") + "\n\n**คำถามที่ควรหาคำตอบ**\n\n"
            + "\n".join(f"- {q}" for q in kp.get("คำถามที่ควรหาคำตอบ", [])))

    st.download_button(
        "ดาวน์โหลดผลประเมินความเสี่ยง (CSV)",
        RS["ตารางสรุป"].to_csv().encode("utf-8-sig"),
        f"ความเสี่ยง_{ticker}.csv", "text/csv")


with t9:
    import quality as QL

    st.markdown("### 🏅 คุณภาพกิจการและคะแนนแบบกูรู")

    @st.cache_data(show_spinner=False, ttl=1800)
    def _qual(tk, _rid):
        return QL.assess_all(data, R, v=v, rf=v.get("wacc_detail", {}).get("พันธบัตร (rf)"))

    with st.spinner("กำลังให้คะแนน 4 โมดูล..."):
        QA = _qual(ticker, id(R))

    # ---- สรุป 4 โมดูล ----
    mc4 = st.columns(4)
    for col, key, label in zip(mc4, ("Module 2", "Module 3", "Module 4", "Module 5"),
                               ("Quality Business", "Buffett Score",
                                "Peter Lynch", "Howard Marks")):
        m = QA[key]
        sc = m["คะแนนรวม"]
        metric_card(col, label, f"{sc:.0f} / 100" if sc is not None else "—",
                    f"จากงบ {m['สัดส่วนจากงบ (%)']:.0f}%",
                    "#2e7d32" if (sc or 0) >= 70 else
                    "#ef6c00" if (sc or 0) >= 50 else "#c62828")

    st.caption(
        "**ป้ายที่มาคือส่วนสำคัญที่สุดของหน้านี้**  \n"
        "`คำนวณ` วัดจากงบโดยตรง ตรวจสอบย้อนได้ · "
        "`ตัวแทน` ใช้ตัวเลขอื่นแทนสิ่งที่วัดตรง ๆ ไม่ได้ **เป็นการอนุมาน ผิดได้** · "
        "`ต้องดูเอง` ไม่มีข้อมูลให้ประเมิน ระบบให้เพียงคำถามที่ควรถาม")

    def _render_module(m, note=None):
        sc = m["คะแนนรวม"]
        st.markdown(f"#### {m['ชื่อโมดูล']}"
                    + (f" — **{sc:.1f} / 100**" if sc is not None else ""))
        if note:
            st.info(note)
        st.caption(f"ให้คะแนนได้ {m['ให้คะแนนได้']}/{m['จำนวนหัวข้อ']} หัวข้อ · "
                   f"มาจากงบโดยตรง {m['สัดส่วนจากงบ (%)']:.0f}% · "
                   f"ต้องดูเอง {m['ต้องดูเอง']} หัวข้อ")

        rows = []
        for it in m["รายการ"]:
            rows.append({
                "หัวข้อ": it["หัวข้อ"],
                "คะแนน": it["คะแนน"],
                "น้ำหนัก": it.get("น้ำหนัก"),
                "ที่มา": it["ที่มา"],
                "หลักฐาน": it["หลักฐาน"] or "—",
            })
        tb = pd.DataFrame(rows).set_index("หัวข้อ")
        if tb["น้ำหนัก"].isna().all():
            tb = tb.drop(columns=["น้ำหนัก"])
        html_table(tb, first_col="หัวข้อ", trim_year=False, fit=True,
                   dec_cols={"คะแนน": 0, "น้ำหนัก": 0},
                   left_cols=("ที่มา", "หลักฐาน"))

        manual = [it for it in m["รายการ"] if it["ที่มา"] == QL.MANUAL]
        if manual:
            with st.expander(f"❓ {len(manual)} หัวข้อที่ต้องหาคำตอบเอง"):
                for it in manual:
                    st.markdown(f"**{it['หัวข้อ']}** — {it['หมายเหตุ']}")

        with st.expander("📖 ที่มาและวิธีตีความแต่ละหัวข้อ"):
            for it in m["รายการ"]:
                if it["หมายเหตุ"]:
                    st.markdown(f"**{it['หัวข้อ']}** ({it['ที่มา']})  \n"
                                f"{it['หมายเหตุ']}")

    q2, q3, q4, q5 = st.tabs(
        ["Module 2 · คุณภาพกิจการ", "Module 3 · Buffett",
         "Module 4 · Peter Lynch", "Module 5 · Howard Marks"])

    with q2:
        _render_module(QA["Module 2"])

    with q3:
        m = QA["Module 3"]
        _render_module(m, f"**{m['ระดับ']}** — คะแนนถ่วงน้ำหนักตามหลัก 11 ข้อ "
                          f"ของ Warren Buffett รวม 100 คะแนนพอดี")

    with q4:
        m = QA["Module 4"]
        note = (f"จัดเป็นหุ้นประเภท **{m['ประเภทตาม Lynch']}** — "
                f"{m['คำอธิบายประเภท']}")
        if m.get("PEG") is not None:
            note += f"  \nPEG = **{m['PEG']:.2f}**"
        if m.get("อัตราโต EPS (%)") is not None:
            note += f" · EPS โตเฉลี่ย {m['อัตราโต EPS (%)']:+.1f}% ต่อปี"
        _render_module(m, note)

    with q5:
        m = QA["Module 5"]
        _render_module(m, f"**{m['สรุปตำแหน่งวัฏจักร']}**  \n"
                          "Howard Marks : *เราพยากรณ์อนาคตไม่ได้ "
                          "แต่รู้ได้ว่าตอนนี้ยืนอยู่ตรงไหนของวัฏจักร* — "
                          "หน้านี้จึงวัดตำแหน่ง ไม่ได้ทำนาย")


with t8:
    import news as NW

    @st.cache_data(show_spinner=False, ttl=1800)
    def _news(tk):
        return NW.dividend_calendar(tk), NW.headlines(tk, limit=15)

    with st.spinner("กำลังดึงข่าวและปฏิทินสิทธิประโยชน์..."):
        try:
            DV, NH = _news(ticker)
        except Exception as e:
            DV, NH = {"ปัญหา": f"{type(e).__name__}: {e}"}, {"รายการ": [], "ที่มา": []}

    # ---------- ปฏิทินสิทธิประโยชน์ ----------
    st.markdown("### 📅 ปฏิทินสิทธิประโยชน์")
    if DV.get("ปัญหา"):
        st.warning(f"ดึงข้อมูลปันผลไม่สำเร็จ — {DV['ปัญหา']}")
    else:
        c = st.columns(4)
        xd, days = DV.get("XD ล่าสุด/ถัดไป"), DV.get("อีกกี่วัน")
        when = ("—" if days is None else
                f"อีก {days} วัน" if days > 0 else
                "วันนี้" if days == 0 else f"ผ่านมาแล้ว {-days} วัน")
        metric_card(c[0], "วัน XD", xd or "—", when,
                    "#2e7d32" if (days is not None and days > 0) else None)
        metric_card(c[1], "ปันผลตอบแทน",
                    f"{DV['ปันผลตอบแทน (%)']:.2f}%" if DV.get("ปันผลตอบแทน (%)") is not None else "—")
        metric_card(c[2], "ปันผล 12 เดือน",
                    f"{DV['รวม 12 เดือน']:,.4f}" if DV.get("รวม 12 เดือน") else "—",
                    f"{cur} ต่อหุ้น")
        metric_card(c[3], "จ่ายปีละ",
                    f"{DV['จำนวนครั้ง/ปี']} ครั้ง" if DV.get("จำนวนครั้ง/ปี") else "—")

        st.caption("**XD (Ex-Dividend)** = วันที่ซื้อแล้ว **ไม่ได้** ปันผลงวดนั้น "
                   "· ในวัน XD ราคามักลดลงราวเงินปันผล ซึ่งไม่ใช่หุ้นตก "
                   "แต่เป็นมูลค่าปันผลออกจากราคาไป")

        # ตารางแคบทั้งคู่ วางคู่กันจะได้ไม่มีพื้นที่ว่างข้างขวาเป็นแถบยาว
        h = DV.get("ปันผลย้อนหลัง")
        sp = DV.get("แตกพาร์/รวมพาร์")
        g1, g2 = st.columns(2)

        with g1:
            if h is not None and len(h):
                hh = h.copy()
                hh.index = [str(i) for i in range(1, len(hh) + 1)]
                st.markdown("**ประวัติปันผล 5 ปีล่าสุด**")
                html_table(hh, first_col="#", dec=4, trim_year=False,
                           max_height=300, fit=True, left_cols=("วัน XD",))
                if len(hh) >= 2:
                    first = float(hh["เงินปันผล (ต่อหุ้น)"].iloc[-1])
                    last = float(hh["เงินปันผล (ต่อหุ้น)"].iloc[0])
                    if first > 0:
                        n = len(hh) - 1
                        g = (last / first) ** (1 / n) - 1 if n else 0
                        st.caption(f"ปันผลโตเฉลี่ย **{g*100:.1f}% ต่อครั้ง** "
                                   f"({first:.4f} → {last:.4f})")
            else:
                st.markdown("**ประวัติปันผล**")
                st.caption("ไม่พบประวัติการจ่ายปันผลใน 5 ปีล่าสุด")

        with g2:
            if sp is not None and len(sp):
                spp = sp.copy()
                spp.index = [str(i) for i in range(1, len(spp) + 1)]
                st.markdown("**แตกพาร์ / รวมพาร์**")
                html_table(spp, first_col="#", dec=2, trim_year=False,
                           fit=True, left_cols=("วันที่",))
                st.caption("แตกพาร์ทำให้ราคาต่อหุ้นลดลงตามสัดส่วน "
                           "แต่มูลค่ารวมที่ถืออยู่เท่าเดิม — ไม่ใช่การขาดทุน")
            else:
                st.markdown("**แตกพาร์ / รวมพาร์**")
                st.caption("ไม่เคยแตกพาร์หรือรวมพาร์")

    # ---------- ข่าว ----------
    st.markdown("---")
    st.markdown("### 📰 หัวข้อข่าว")
    if NH.get("รายการ"):
        st.caption(f"แหล่งข้อมูล: {', '.join(NH['ที่มา'])}")
        # วันที่เป็นคอลัมน์แคบคงที่ทางซ้าย หัวข้อไหลต่อทางขวา
        # ทำให้สายตากวาดลงตามแนวตั้งได้ ไม่ต้องหาว่าวันที่อยู่ตรงไหนของแต่ละบรรทัด
        for it in NH["รายการ"]:
            n1, n2 = st.columns([1, 9])
            n1.markdown(f"<span class='muted'>{it.get('วันที่') or '—'}</span>",
                        unsafe_allow_html=True)
            title = it["หัวข้อ"]
            link = it.get("ลิงก์")
            n2.markdown((f"[{title}]({link})" if link else f"{title}")
                        + f"  \n<span class='muted' style='font-size:.78rem'>"
                          f"{it.get('ที่มา','')}</span>", unsafe_allow_html=True)
    else:
        st.info("ดึงหัวข้อข่าวอัตโนมัติไม่ได้สำหรับหุ้นตัวนี้\n\n"
                "ข่าวหุ้นไทยส่วนใหญ่อยู่บนเว็บตลาดหลักทรัพย์ซึ่งไม่ได้เปิด API "
                "ไว้ให้ดึงอัตโนมัติอย่างเป็นทางการ — ใช้ลิงก์ด้านล่างเปิดดูโดยตรงได้")

    if NH.get("ลิงก์ SET"):
        l1, l2 = st.columns(2)
        l1.link_button("เปิดข่าวทั้งหมดที่ SET", NH["ลิงก์ SET"],
                       use_container_width=True)
        l2.link_button("เปิด Factsheet ที่ SET", NH["ลิงก์ Factsheet"],
                       use_container_width=True)
        st.caption("หน้า SET มีข่าวครบที่สุดสำหรับหุ้นไทย — ทั้งประกาศจ่ายปันผล "
                   "วัน XD/XM ผลประกอบการรายไตรมาส และรายการที่เกี่ยวโยงกัน")

    st.caption("ส่วนนี้แสดง **หัวข้อ** เท่านั้น ยังไม่ได้ให้ AI อ่านและตีความ "
               "(ตามพิมพ์เขียวคือ Part 12) — การสรุปข่าวด้วย AI จะทำในเฟสถัดไป")

st.markdown("---")
st.caption(f"ข้อมูลดึงเมื่อ {data.get('fetched_at','-')} · "
           f"งบการเงินจาก {v['แหล่งงบ']} · ราคาจาก yfinance · "
           f"สร้างหน้านี้เมื่อ {datetime.now().strftime('%d/%m/%Y %H:%M')}")
st.warning("เอกสารและตัวเลขทั้งหมดในหน้านี้จัดทำโดยระบบอัตโนมัติเพื่อการศึกษา "
           "**ไม่ใช่คำแนะนำการลงทุน** ผู้ใช้ควรตรวจสอบด้วยตนเองก่อนตัดสินใจใด ๆ")
