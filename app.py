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
               max_height=None, link_cols=(), sort_cols=(),
               cur_sort=None, cur_asc=True, fit=False, left_cols=(),
               dec_cols=None, sign_cols=(), sign_mask=None):
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
            val = _cell(df.loc[name, c], (dec_cols or {}).get(c, dec))
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
                # target="_self" = เปิดในแท็บเดิม ไม่เด้งแท็บใหม่
                # เปิดแท็บใหม่ เพื่อไม่ให้ผลคัดกรองในแท็บเดิมหายไป
                val = (f"<a class='tk' target='_blank' rel='noopener' "
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
    from screener import (GROWTH_COLS, attach_growth, preset, quality_flags,
                          quarterly_growth, quick_filter, quick_screen)

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
                       sign_cols=g_cols,
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

            HEADS = ["เลือก", "หุ้น", "รายได้ YoY", "กำไร YoY",
                     "P/E", "P/BV", "D/E", "ROE %", "GM %", "NM %", "ชื่อบริษัท"]
            WIDTHS = [0.5, 1.2, 1.1, 1.0, 0.8, 0.8, 0.8, 0.9, 0.9, 0.9, 2.4]
            hd = st.columns(WIDTHS)
            for col, txt in zip(hd, HEADS):
                col.markdown(f"<span class='muted'><b>{txt}</b></span>",
                             unsafe_allow_html=True)

            # แสดงทุกตัวที่ผ่านเกณฑ์ ไม่แบ่งหน้า
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
                cc[1].markdown(f"<a class='tk' target='_blank' rel='noopener' "
                               f"href='?t={t}'>{t}</a>", unsafe_allow_html=True)
                for slot, key in ((2, "รายได้ YoY (%)"), (3, "กำไร YoY (%)")):
                    gv = pd.to_numeric(r.get(key), errors="coerce")
                    cc[slot].markdown(
                        f"<span style='color:#2e9e5b;font-weight:600'>▲ {gv:,.1f}</span>"
                        if pd.notna(gv) and gv > 0 else
                        f"<span class='muted'>{_cell(gv, 1)}</span>",
                        unsafe_allow_html=True)
                cc[4].caption(_cell(r.get("P/E"), 1))
                cc[5].caption(_cell(r.get("P/BV"), 2))
                cc[6].caption(_cell(r.get("D/E"), 2))
                cc[7].caption(_cell(r.get("ROE (%)"), 1))
                cc[8].caption(_cell(r.get("อัตรากำไรขั้นต้น (%)"), 1))
                cc[9].caption(_cell(r.get("อัตรากำไรสุทธิ (%)"), 1))
                cc[10].caption(str(r["ชื่อบริษัท"])[:36])

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
            html_table(full, first_col="หัวข้อ", trim_year=False, fit=True,
                       max_height=720)
        else:
            html_table(res["table"], first_col="หัวข้อ", trim_year=False, fit=True)

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

t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs(
    ["ภาพรวม", "ผลประกอบการ", "อัตราส่วน", "ประเมินมูลค่า", "ช่วงราคา",
     "พยากรณ์ 10 ปี", "ความเสี่ยง", "ข่าว & XD"])

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
