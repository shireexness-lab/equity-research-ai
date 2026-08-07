"""
tickers.py — รายชื่อหุ้นสำหรับช่องค้นหา
========================================
หน้าที่ : รวบรวมรายชื่อหุ้นให้ผู้ใช้พิมพ์แล้วเห็นตัวเลือกขึ้นมาทันที

แหล่งรายชื่อ
------------
หุ้นสหรัฐ : ดึงจาก SEC โดยตรง (~10,000 ตัว) — เป็นทะเบียนทางการ อัปเดตเอง ฟรี
หุ้นไทย   : รายชื่อตั้งต้นที่เตรียมไว้ (ไม่ครบทุกตัว) เพราะ SET ไม่มี API ฟรี

⚠️ รายชื่อหุ้นไทยเป็นเพียง "จุดเริ่มต้น" ไม่ใช่ทะเบียนทางการ
   บางบริษัทอาจเปลี่ยนชื่อ ควบรวม หรือเพิกถอนไปแล้ว
   ผู้ใช้พิมพ์ ticker เองได้เสมอ แม้ไม่มีในรายชื่อ
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# หุ้นไทย — รายชื่อตั้งต้น จัดกลุ่มตามอุตสาหกรรมเพื่อให้ค้นหาง่าย
# ---------------------------------------------------------------------------

THAI_STOCKS = {
    # พลังงานและปิโตรเคมี
    "PTT": "ปตท.", "PTTEP": "ปตท.สำรวจและผลิตปิโตรเลียม",
    "PTTGC": "พีทีที โกลบอล เคมิคอล", "TOP": "ไทยออยล์",
    "BCP": "บางจาก", "IRPC": "ไออาร์พีซี", "SPRC": "สตาร์ ปิโตรเลียม",
    "IVL": "อินโดรามา เวนเจอร์ส", "SCC": "ปูนซิเมนต์ไทย", "SCGP": "เอสซีจี แพคเกจจิ้ง",
    # ไฟฟ้าและสาธารณูปโภค
    "GULF": "กัลฟ์", "GPSC": "โกลบอล เพาเวอร์ ซินเนอร์ยี่",
    "EGCO": "ผลิตไฟฟ้า", "RATCH": "ราช กรุ๊ป", "BGRIM": "บี.กริม เพาเวอร์",
    "EA": "พลังงานบริสุทธิ์", "TTW": "ทีทีดับบลิว",
    # ธนาคารและการเงิน
    "SCB": "เอสซีบี เอกซ์", "KBANK": "กสิกรไทย", "BBL": "กรุงเทพ",
    "KTB": "กรุงไทย", "TTB": "ทีเอ็มบีธนชาต", "TISCO": "ทิสโก้",
    "KKP": "เกียรตินาคินภัทร", "MTC": "เมืองไทย แคปปิตอล",
    "SAWAD": "ศรีสวัสดิ์", "TIDLOR": "เงินติดล้อ", "JMT": "เจ เอ็ม ที",
    "AEONTS": "อิออน ธนสินทรัพย์",
    # ค้าปลีกและอาหาร
    "CPALL": "ซีพี ออลล์", "CPAXT": "ซีพี แอ็กซ์ตร้า", "CPF": "เจริญโภคภัณฑ์อาหาร",
    "CRC": "เซ็นทรัล รีเทล", "HMPRO": "โฮม โปรดักส์", "GLOBAL": "สยามโกลบอลเฮ้าส์",
    "BJC": "เบอร์ลี่ ยุคเกอร์", "TU": "ไทยยูเนี่ยน กรุ๊ป", "OSP": "โอสถสภา",
    "CBG": "คาราบาวกรุ๊ป", "ICHI": "อิชิตัน", "SAPPE": "เซ็ปเป้", "M": "เอ็มเค เรสโตรองต์",
    # สื่อสารและเทคโนโลยี
    "ADVANC": "แอดวานซ์ อินโฟร์ เซอร์วิส", "TRUE": "ทรู คอร์ปอเรชั่น",
    "DELTA": "เดลต้า อีเลคโทรนิคส์", "KCE": "เคซีอี อีเลคโทรนิคส์",
    "HANA": "ฮานา ไมโครอิเล็คโทรนิคส", "SVI": "เอสวีไอ",
    # โรงพยาบาลและสุขภาพ
    "BDMS": "กรุงเทพดุสิตเวชการ", "BH": "โรงพยาบาลบำรุงราษฎร์",
    "BCH": "บางกอก เชน ฮอสปิทอล", "CHG": "โรงพยาบาลจุฬารัตน์",
    "THG": "ธนบุรี เฮลท์แคร์", "PR9": "โรงพยาบาลพระรามเก้า",
    "TQM": "ทีคิวเอ็ม อัลฟา",
    # อสังหาริมทรัพย์และนิคม
    "CPN": "เซ็นทรัลพัฒนา", "LH": "แลนด์แอนด์เฮ้าส์", "AP": "เอพี (ไทยแลนด์)",
    "SPALI": "ศุภาลัย", "QH": "ควอลิตี้เฮ้าส์", "ORI": "ออริจิ้น พร็อพเพอร์ตี้",
    "AMATA": "อมตะ คอร์ปอเรชัน", "WHA": "ดับบลิวเอชเอ คอร์ปอเรชั่น",
    # ขนส่งและท่องเที่ยว
    "AOT": "ท่าอากาศยานไทย", "BEM": "ทางด่วนและรถไฟฟ้ากรุงเทพ",
    "BTS": "บีทีเอส กรุ๊ป", "AAV": "เอเชีย เอวิเอชั่น",
    "MINT": "ไมเนอร์ อินเตอร์เนชั่นแนล", "CENTEL": "โรงแรมเซ็นทรัลพลาซา",
    "ERW": "ดิ เอราวัณ กรุ๊ป",
}

# หุ้นสหรัฐยอดนิยม — ใส่ไว้ให้ขึ้นก่อนเสมอแม้ยังโหลดรายชื่อจาก SEC ไม่เสร็จ
POPULAR_US = {
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
    "AMZN": "Amazon", "NVDA": "NVIDIA", "META": "Meta Platforms",
    "TSLA": "Tesla", "BRK-B": "Berkshire Hathaway", "JPM": "JPMorgan Chase",
    "V": "Visa", "MA": "Mastercard", "UNH": "UnitedHealth",
    "JNJ": "Johnson & Johnson", "PG": "Procter & Gamble", "KO": "Coca-Cola",
    "PEP": "PepsiCo", "COST": "Costco", "WMT": "Walmart",
    "HD": "Home Depot", "MCD": "McDonald's", "NKE": "Nike",
    "DIS": "Walt Disney", "NFLX": "Netflix", "ADBE": "Adobe",
    "CRM": "Salesforce", "ORCL": "Oracle", "AMD": "AMD",
    "INTC": "Intel", "QCOM": "Qualcomm", "TXN": "Texas Instruments",
    "AVGO": "Broadcom", "CSCO": "Cisco", "IBM": "IBM",
    "XOM": "Exxon Mobil", "CVX": "Chevron", "LLY": "Eli Lilly",
    "ABBV": "AbbVie", "MRK": "Merck", "PFE": "Pfizer",
}


def us_tickers() -> dict:
    """
    ดึงทะเบียนหุ้นสหรัฐจาก SEC (~10,000 ตัว)
    ใช้ระบบ cache เดียวกับ edgar_layer จึงไม่ยิงซ้ำ (เก็บ 30 วัน)
    ถ้าดึงไม่ได้ จะคืนเฉพาะรายชื่อยอดนิยมแทน เพื่อให้แอปยังใช้ได้
    """
    try:
        from edgar_layer import TICKER_MAP_URL, _cached, _get_json
        table = _cached("ticker_map", 24 * 30, lambda: _get_json(TICKER_MAP_URL))
        out = {}
        for row in table.values():
            t = str(row.get("ticker", "")).upper().strip()
            name = str(row.get("title", "")).strip()
            if t:
                out[t] = name
        return out or dict(POPULAR_US)
    except Exception:
        return dict(POPULAR_US)


def build_options(include_us=True):
    """
    สร้างรายการตัวเลือกสำหรับช่องค้นหา

    เรียงลำดับให้ค้นง่าย :
      1. หุ้นไทย (ผู้ใช้เป็นคนไทย น่าจะค้นบ่อย)
      2. หุ้นสหรัฐยอดนิยม
      3. หุ้นสหรัฐที่เหลือทั้งหมด (เรียงตามตัวอักษร)

    คืน (รายการข้อความ, dict แปลงข้อความกลับเป็น ticker)
    """
    labels, lookup = [], {}

    def add(sym, name, tag):
        label = f"{sym} — {name}" if name else sym
        if tag:
            label = f"{label}  ·{tag}"
        if sym not in lookup.values():
            labels.append(label)
            lookup[label] = sym

    for sym, name in THAI_STOCKS.items():
        add(f"{sym}.BK", name, "ไทย")

    if include_us:
        us = us_tickers()
        for sym, name in POPULAR_US.items():
            add(sym, us.get(sym, name), "US")
        for sym in sorted(us):
            if sym in POPULAR_US:
                continue
            add(sym, us[sym], "US")

    return labels, lookup
