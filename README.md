# Equity Research AI Pro

ระบบวิเคราะห์หุ้นจากงบการเงินจริง — เปิดใช้ได้ทั้ง iPhone / Android / Mac

> **ไม่ใช่คำแนะนำการลงทุน** เอกสารและตัวเลขทั้งหมดจัดทำโดยระบบอัตโนมัติเพื่อการศึกษา

---

## หลักการออกแบบ

**โค้ดคำนวณ · AI เล่าเรื่อง**
ตัวเลขทางการเงินทุกตัว (ratio, DCF, CAGR) คำนวณด้วย Python ทั้งหมด ตรวจสอบย้อนกลับได้ทุกขั้น
ไม่มี AI ตัวไหนตอบตัวเลขการเงินดิบ

**บอกความไม่แน่นอนเสมอ**
ระบบไม่ให้ตัวเลขเดียวแล้วจบ แต่ให้ช่วง ให้เหตุผล และให้**คะแนนความน่าเชื่อถือ**
ถ้าวิธีต่าง ๆ ให้ผลขัดกันมาก ระบบจะบอกตรง ๆ ว่าเชื่อไม่ได้

---

## แหล่งข้อมูล

| ประเภท | แหล่ง | ย้อนหลัง | ค่าใช้จ่าย |
|---|---|---|---|
| งบการเงินหุ้นสหรัฐ | **SEC EDGAR** (10-K ที่ยื่นจริง) | ~15 ปี | ฟรี |
| งบการเงินหุ้นต่างประเทศ | yfinance | ~4 ปี | ฟรี |
| ราคาหุ้น | yfinance | ตั้งแต่เริ่มซื้อขาย | ฟรี |

ระบบเลือกแหล่งให้อัตโนมัติจากรูปแบบชื่อย่อ (มีจุด = ต่างประเทศ)

---

## โครงสร้าง

| ไฟล์ | หน้าที่ |
|---|---|
| `data_layer.py` | ดึงข้อมูล + ระบบ cache + เลือกแหล่งอัตโนมัติ |
| `edgar_layer.py` | ดึงงบจาก SEC EDGAR + ปรับการแตกพาร์ |
| `statements.py` | YoY, CAGR, Common Size |
| `ratios.py` | อัตราส่วน 49 ตัว 7 หมวด |
| `valuation.py` | DCF 2-stage, EPV, Multiple ย้อนหลัง, Reverse DCF |
| `bands.py` | ช่วงราคา + Margin of Safety ปรับอัตโนมัติ |
| `report.py` | รายงาน PDF ภาษาไทย |
| `app.py` | หน้าเว็บ (Streamlit) |

---

## เริ่มใช้งาน

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# ไลบรารีระบบสำหรับสร้าง PDF (macOS)
brew install pango gdk-pixbuf libffi
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib

# ฟอนต์ไทย (ถ้ายังไม่มีในโฟลเดอร์ fonts/)
mkdir -p fonts
curl -L -o fonts/Sarabun-Regular.ttf \
  https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Regular.ttf
curl -L -o fonts/Sarabun-Bold.ttf \
  https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Bold.ttf
```

### ใช้ผ่านหน้าเว็บ
```bash
streamlit run app.py
```

### ใช้ผ่าน Terminal
```bash
python3 edgar_layer.py AAPL        # ดูงบดิบจาก SEC
python3 statements.py  AAPL        # วิเคราะห์งบ
python3 ratios.py      AAPL        # อัตราส่วนทั้งหมด
python3 valuation.py   AAPL        # ประเมินมูลค่า
python3 bands.py       AAPL        # ช่วงราคา
python3 report.py      AAPL --open # รายงาน PDF

python3 report.py PTT.BK --rf 0.025 --open   # หุ้นไทย ใส่พันธบัตรไทย
```

---

## สิ่งที่ระบบ **ไม่** ทำ

- ไม่ทำนายราคาหุ้น
- ไม่พิจารณาปัจจัยเชิงคุณภาพ (ผู้บริหาร การแข่งขัน กฎระเบียบ)
- ไม่รู้เหตุการณ์ที่เกิดหลังวันดึงข้อมูล
- ไม่ทดแทนการอ่านงบและเอกสารบริษัทด้วยตัวเอง

---

## สัญญาอนุญาต

โค้ด: ใช้ส่วนตัว
ฟอนต์ Sarabun: SIL Open Font License 1.1 (แจกจ่ายต่อได้)
