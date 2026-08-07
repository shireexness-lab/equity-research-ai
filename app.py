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
  .block-container {{ padding-top:1.2rem; max-width:1200px; }}
  .zone {{ display:inline-block; padding:.4rem 1.4rem; border-radius:.5rem;
          color:#fff !important; font-size:1.4rem; font-weight:700; }}
  .zone * {{ color:#fff !important; }}
  .t {{ color:{c['txt']}; }}
  .t th {{ background:{c['bg2']} !important; color:{c['txt']} !important; }}
  .t td {{ border-bottom:1px solid {c['line']}; }}
  .t tbody tr:nth-child(even) {{ background:rgba(128,128,128,.10); }}
  .mc {{ border:1px solid {c['line']}; border-radius:.5rem; padding:.6rem .8rem; }}
  .mc .k {{ color:{c['dim']}; font-size:.78rem; }}
  .mc .v {{ color:{c['txt']}; font-size:1.3rem; font-weight:700; line-height:1.3; }}
  .mc .d {{ font-size:.78rem; }}
  .tw {{ overflow-x:auto; }}
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


def html_table(df: pd.DataFrame, first_col="รายการ", dec=2, trim_year=True):
    """แสดง DataFrame เป็นตาราง HTML (เลื่อนซ้าย-ขวาได้บนมือถือ)"""
    cols = [str(c)[:4] if trim_year else str(c) for c in df.columns]
    h = [f"<div class='tw'><table class='t'><thead><tr><th class='l'>{first_col}</th>"]
    h += [f"<th>{c}</th>" for c in cols]
    h.append("</tr></thead><tbody>")
    for name in df.index:
        h.append(f"<tr><td class='l'>{name}</td>")
        h += [f"<td>{_cell(df.loc[name, c], dec)}</td>" for c in df.columns]
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

MODE = st.radio("โหมด", ["วิเคราะห์รายตัว", "สแกนหาหุ้นราคาต่ำกว่ามูลค่า"],
                horizontal=True, label_visibility="collapsed")


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
# โหมดสแกน
# ---------------------------------------------------------------------------
if MODE.startswith("สแกน"):
    from screener import preset, scan, undervalued

    st.info("**วิธีทำงาน** — ระบบจะวิเคราะห์หุ้นทีละตัวแบบเต็มรูปแบบ "
            "แล้วเรียงลำดับตามส่วนลดจากมูลค่าที่ประเมินได้\n\n"
            "⏱️ ใช้เวลาราว **30 วินาทีต่อหุ้น 1 ตัว** ในครั้งแรก "
            "(ตัวที่เคยวิเคราะห์แล้วจะเร็วมาก) — แนะนำให้เริ่มที่ 10–15 ตัวก่อน")

    s1, s2 = st.columns([3, 2])
    with s1:
        group = st.radio("ชุดหุ้น", ["หุ้นไทย", "หุ้นสหรัฐยอดนิยม", "เลือกเอง"],
                         horizontal=True)
    with s2:
        n_max = st.slider("จำนวนสูงสุด", 3, 40, 10)

    if group == "เลือกเอง":
        picks = st.multiselect("เลือกหุ้นที่ต้องการสแกน", OPTIONS, max_selections=40)
        scan_list = [LOOKUP.get(p, str(p).split(" ")[0]) for p in picks]
    else:
        scan_list = preset("thai" if group == "หุ้นไทย" else "us")[:n_max]
        st.caption(f"จะสแกน : {', '.join(scan_list[:10])}"
                   + (f" ... รวม {len(scan_list)} ตัว" if len(scan_list) > 10 else ""))

    f1, f2, f3 = st.columns(3)
    with f1:
        s_rf = st.number_input("อัตราพันธบัตร", 0.0, 0.15,
                               0.025 if group == "หุ้นไทย" else 0.042, 0.005,
                               format="%.3f")
    with f2:
        min_disc = st.slider("ส่วนลดขั้นต่ำ (%)", -50, 80, 0, 5)
    with f3:
        min_score = st.slider("คะแนนความน่าเชื่อถือขั้นต่ำ", 0, 100, 0, 5)

    if st.button("เริ่มสแกน", type="primary", use_container_width=True):
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
            cols = ["ticker", "ชื่อบริษัท", "ราคา", "มูลค่าที่ประเมินได้",
                    "ส่วนลด (%)", "โซน", "ความน่าเชื่อถือ", "คะแนน",
                    "ปีข้อมูล", "ROE เฉลี่ย (%)", "ตลาดคาดโต (%)", "ใช้ DCF"]
            show = under[[c for c in cols if c in under.columns]].copy()
            show.index = range(1, len(show) + 1)
            html_table(show.T, first_col="อันดับ", trim_year=False)

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


manual = st.toggle("พิมพ์ ticker เอง (สำหรับหุ้นที่ไม่มีในรายชื่อ)",
                   value=not OPTIONS,
                   help="รายชื่อหุ้นไทยเป็นรายชื่อตั้งต้น ไม่ครบทุกตัว "
                        "ถ้าหาไม่เจอให้เปิดสวิตช์นี้แล้วพิมพ์เอง")

c1, c2 = st.columns([3, 1])
with c1:
    if manual or not OPTIONS:
        ticker = st.text_input("ใส่ชื่อย่อหุ้น", value="AAPL",
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
