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
    # เพิ่มเติม — บริษัทขนาดกลางถึงใหญ่
    "TASCO": "ทิปโก้แอสฟัลท์", "STA": "ศรีตรังแอโกรอินดัสทรี",
    "STGT": "ศรีตรังโกลฟส์", "NER": "นอร์ทอีส รับเบอร์",
    "GFPT": "จีเอฟพีที", "TFG": "ไทยฟู้ดส์ กรุ๊ป",
    "ASIAN": "เอเชี่ยนซี คอร์ปอเรชั่น", "SNNP": "ศรีนานาพร มาร์เก็ตติ้ง",
    "TVO": "น้ำมันพืชไทย", "KSL": "น้ำตาลขอนแก่น",
    "BTG": "เบทาโกร", "PLANB": "แพลน บี มีเดีย",
    "VGI": "วีจีไอ", "MAJOR": "เมเจอร์ ซีนีเพล็กซ์",
    "COM7": "คอมเซเว่น", "SYNEX": "ซินเน็ค", "JMART": "เจ มาร์ท",
    "SIRI": "แสนสิริ", "ANAN": "อนันดา ดีเวลลอปเม้นท์",
    "LPN": "แอล.พี.เอ็น. ดีเวลลอปเมนท์", "SC": "เอสซี แอสเสท",
    "ROJNA": "สวนอุตสาหกรรมโรจนะ", "TICON": "ไทคอน",
    "STEC": "ซิโน-ไทย เอ็นจีเนียริ่ง", "CK": "ช.การช่าง",
    "ITD": "อิตาเลียนไทย ดีเวล๊อปเมนต์", "UNIQ": "ยูนิค เอ็นจิเนียริ่ง",
    "TPIPL": "ทีพีไอ โพลีน", "TPIPP": "ทีพีไอ โพลีน เพาเวอร์",
    "DCC": "ไดนาสตี้ เซรามิค", "TOA": "ทีโอเอ เพ้นท์",
    "EPG": "อีสเทิร์นโพลีเมอร์ กรุ๊ป", "PTG": "พีทีจี เอ็นเนอยี",
    "OR": "ปตท. น้ำมันและการค้าปลีก", "SUSCO": "ซัสโก้",
    "BAM": "บริหารสินทรัพย์ กรุงเทพพาณิชย์", "CHAYO": "ชโย กรุ๊ป",
    "SINGER": "ซิงเกอร์ ประเทศไทย", "THANI": "ราชธานีลิสซิ่ง",
    "ASP": "เอเซีย พลัส กรุ๊ป", "KTC": "บัตรกรุงไทย",
    "BLA": "กรุงเทพประกันชีวิต", "TIPH": "ทิพย กรุ๊ป",
    "BKI": "กรุงเทพประกันภัย", "TLI": "ไทยประกันชีวิต",
    "SIS": "เอสไอเอส ดิสทริบิวชั่น", "ILM": "อินเด็กซ์ ลิฟวิ่งมอลล์",
    "DOHOME": "ดูโฮม", "MEGA": "เมก้า ไลฟ์ไซแอ็นซ์",
    "RBF": "อาร์ แอนด์ บี ฟู้ด ซัพพลาย", "TFM": "ไทยยูเนี่ยน ฟีดมิลล์",
    "PRM": "พริมา มารีน", "RCL": "อาร์ ซี แอล",
    "WICE": "ไวส์ โลจิสติกส์", "III": "ทริพเพิล ไอ โลจิสติกส์",
    "SAT": "สมบูรณ์ แอ๊ดวานซ์", "STANLY": "ไทยสแตนเลย์การไฟฟ้า",
    "AH": "อาปิโก ไฮเทค", "PCSGH": "พี.ซี.เอส.แมชีน กรุ๊ป",
    "SPRC2": "", "TTA": "โทรีเซนไทย เอเยนต์ซีส์",
    "SPI": "สหพัฒนาอินเตอร์โฮลดิ้ง", "SAPPE2": "",
    "MOSHI": "โมชิ โมชิ รีเทล", "BE8": "เบอริลแปด",
    "BBIK": "บลูบิค กรุ๊ป", "SECURE": "เอ็นฟอร์ซ ซีเคียว",
}
# ลบรายการที่ชื่อว่าง (เผื่อพิมพ์ซ้ำ)
THAI_STOCKS = {k: v for k, v in THAI_STOCKS.items() if v}

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


# ---------------------------------------------------------------------------
# ทะเบียนบริษัทจดทะเบียนฉบับเต็มจากตลาดหลักทรัพย์ (930 รายการ)
#
# ที่มา : ดาวน์โหลดจากเว็บ SET → รายชื่อบริษัทจดทะเบียน → บันทึกเป็นไฟล์
#         แล้วแปลงเป็น data/set_listed.json
# วิธีอัปเดต : ดาวน์โหลดไฟล์ใหม่จาก SET แล้วรัน  python3 tools_update_set.py
# ---------------------------------------------------------------------------

SET_FILE = BASE_DIR / "data" / "set_listed.json"
_set_cache = {}


def load_set() -> dict:
    """
    อ่านทะเบียนบริษัทจดทะเบียนไทยฉบับเต็ม

    ถ้าไม่มีไฟล์ จะถอยไปใช้รายชื่อตั้งต้นที่ฝังไว้ในโค้ด (135 ตัว)
    เพื่อให้ระบบยังทำงานได้ ไม่พังเพราะไฟล์หาย
    """
    if _set_cache:
        return _set_cache
    try:
        import json
        with open(SET_FILE, encoding="utf-8") as f:
            js = json.load(f)
        _set_cache.update({"meta": js.get("meta", {}),
                           "companies": js.get("companies", [])})
    except Exception:
        _set_cache.update({
            "meta": {"ที่มา": "รายชื่อตั้งต้นในโค้ด (ไม่พบไฟล์ทะเบียนเต็ม)"},
            "companies": [{"sym": s, "name": n, "market": "SET",
                           "industry": "-", "sector": "-", "kind": "หุ้นสามัญ"}
                          for s, n in THAI_STOCKS.items()]})
    return _set_cache


def thai_industries():
    """รายชื่อกลุ่มอุตสาหกรรมทั้งหมด ใช้ทำตัวกรอง"""
    return sorted({c["industry"] for c in load_set()["companies"]
                   if c.get("industry") and c["industry"] != "-"})


def thai_universe(market=None, industry=None, common_only=True):
    """
    หุ้นไทยทั้งตลาด (เติม .BK ให้แล้ว)

        market      "SET" หรือ "mai" — ไม่ใส่ = ทั้งสองตลาด
        industry    กรองเฉพาะกลุ่มอุตสาหกรรมที่ระบุ
        common_only True = เอาเฉพาะหุ้นสามัญ ตัดกองทุนรวม/REIT ออก

    ทำไมต้องตัดกองทุน/REIT ออก : กองทุนไม่มีงบการเงินแบบบริษัท
    การคำนวณ P/E, ROE, DCF จึงไม่มีความหมาย
    """
    out = []
    for c in load_set()["companies"]:
        if common_only and c.get("kind") != "หุ้นสามัญ":
            continue
        if market and c.get("market") != market:
            continue
        if industry and c.get("industry") != industry:
            continue
        out.append(f"{c['sym']}.BK")
    return out


def us_universe(limit=None):
    """
    หุ้นสหรัฐทั้งตลาดจากทะเบียน SEC (~10,000 ตัว)

    ⚠️ รวมหุ้นขนาดเล็กมากและกองทรัสต์ด้วย ตัวที่ไม่มีข้อมูลจะถูกคัดออกเองระหว่างสแกน
    """
    out = sorted(us_tickers())
    return out[:limit] if limit else out


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
    seen = set()

    def add(sym, name, tag):
        if sym in seen:
            return
        seen.add(sym)
        label = f"{sym} — {name}" if name else sym
        if tag:
            label = f"{label}  ·{tag}"
        labels.append(label)
        lookup[label] = sym

    # หุ้นไทยจากทะเบียนฉบับเต็ม (เอาเฉพาะหุ้นสามัญ)
    for c in load_set()["companies"]:
        if c.get("kind") != "หุ้นสามัญ":
            continue
        add(f"{c['sym']}.BK", c["name"], c.get("market", "ไทย"))

    if include_us:
        us = us_tickers()
        for sym, name in POPULAR_US.items():
            add(sym, us.get(sym, name), "US")
        for sym in sorted(us):
            if sym in POPULAR_US:
                continue
            add(sym, us[sym], "US")

    return labels, lookup
