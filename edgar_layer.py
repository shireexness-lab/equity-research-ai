"""
edgar_layer.py — Part 1b : ดึงงบการเงินจาก SEC EDGAR (หุ้นสหรัฐ)
==================================================================
ทำไมต้องมีไฟล์นี้
------------------
yfinance ให้งบย้อนหลังแค่ 4 ปี ซึ่ง **ไม่พอ** สำหรับการวิเคราะห์แบบ Buffett
ที่ต้องดู "ROE สม่ำเสมอ 10 ปีไหม" หรือทำ Forecast 10 ปี

SEC EDGAR คือฐานข้อมูลที่บริษัทสหรัฐ **ยื่นงบจริงต่อ ก.ล.ต. สหรัฐ**
  • ฟรี ไม่ต้องสมัคร ไม่ต้องมี API key
  • ย้อนหลัง ~15 ปี
  • เป็นต้นทางแท้ ๆ ไม่ผ่านคนกลาง → ตรวจสอบย้อนกลับไปถึงเอกสาร 10-K ได้

ข้อจำกัด
--------
  • **หุ้นสหรัฐเท่านั้น** หุ้นไทย (.BK) ไม่มีใน EDGAR → ระบบจะใช้ yfinance ให้อัตโนมัติ
  • EDGAR ไม่มีราคาหุ้น → ราคายังดึงจาก yfinance เหมือนเดิม

หลักการออกแบบสำคัญ
-------------------
ไฟล์นี้จะแปลงข้อมูล EDGAR ให้มี **ชื่อบรรทัดเหมือน yfinance ทุกประการ**
("Total Revenue", "Net Income", ...) เพื่อให้ Part 2, 3, 4 ใช้ต่อได้ทันที
โดยไม่ต้องแก้โค้ดแม้แต่บรรทัดเดียว

วิธีใช้จาก Terminal
-------------------
    python3 edgar_layer.py AAPL
    python3 edgar_layer.py MSFT --years 20
"""

import argparse
import json
import os
import pickle
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache" / "edgar"

# SEC บังคับให้ระบุอีเมลติดต่อใน User-Agent มิฉะนั้นจะถูกปฏิเสธ (403)
# ⚠️ ถ้าจะ push โค้ดขึ้น GitHub แบบ public อีเมลนี้จะเห็นได้ทั้งโลก
#    ถ้าไม่ต้องการ ให้ตั้งค่าตัวแปรระบบแทน:  export SEC_CONTACT_EMAIL="you@example.com"
CONTACT_EMAIL = os.environ.get("SEC_CONTACT_EMAIL", "shireexness@gmail.com")
USER_AGENT = f"EquityResearchAI/1.0 ({CONTACT_EMAIL})"

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

MIN_REQUEST_INTERVAL = 0.15   # SEC จำกัด 10 ครั้ง/วินาที — เราเว้น 0.15 วิ เพื่อความปลอดภัย
_last_request_time = [0.0]


# ---------------------------------------------------------------------------
# ตัวช่วยเรียก API
# ---------------------------------------------------------------------------

def _ssl_context():
    """
    สร้างบริบท SSL สำหรับตรวจสอบใบรับรองเว็บ

    ปัญหาที่แก้ : Python ที่ติดตั้งจาก python.org บน macOS ไม่ได้ต่อสายเข้ากับ
    ที่เก็บใบรับรองของระบบ ทำให้เปิด https ไม่ได้ ขึ้น error
        CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate

    ทางแก้ : ใช้ชุดใบรับรองจากไลบรารี certifi ซึ่งติดมากับ yfinance อยู่แล้ว
    วิธีนี้ดีกว่าการรัน "Install Certificates.command" ที่เครื่อง เพราะ
    ตอนนำขึ้นเว็บ (Streamlit Cloud) จะทำงานได้เหมือนกันโดยไม่ต้องตั้งค่าอะไรอีก
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_SSL_CTX = _ssl_context()


def _get_json(url: str, timeout: int = 60):
    """เรียก API ของ SEC พร้อมหน่วงเวลาไม่ให้ยิงถี่เกินกติกา"""
    wait = MIN_REQUEST_INTERVAL - (time.time() - _last_request_time[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Host": url.split("/")[2],
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                import gzip
                raw = gzip.decompress(raw)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RuntimeError(
                "SEC ปฏิเสธคำขอ (403)\n"
                "  สาเหตุที่พบบ่อย: ไม่ได้ระบุอีเมลติดต่อ\n"
                f"  ปัจจุบันใช้: {CONTACT_EMAIL}\n"
                "  แก้โดย:  export SEC_CONTACT_EMAIL=\"อีเมลของคุณ\""
            )
        if e.code == 404:
            raise ValueError("ไม่พบข้อมูลบริษัทนี้ใน SEC EDGAR (อาจไม่ใช่บริษัทจดทะเบียนในสหรัฐ)")
        raise
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e.reason):
            raise RuntimeError(
                "ตรวจสอบใบรับรองความปลอดภัยไม่ผ่าน\n"
                "  สาเหตุ: Python ไม่พบชุดใบรับรอง\n"
                "  แก้โดยพิมพ์:  pip install --upgrade certifi"
            )
        raise RuntimeError(f"เชื่อมต่อ SEC ไม่ได้: {e.reason}")
    finally:
        _last_request_time[0] = time.time()
    return json.loads(raw)


def _cached(name: str, max_age_hours: float, fetch_fn):
    """อ่านจาก cache ถ้ายังไม่หมดอายุ ไม่งั้นดึงใหม่แล้วเก็บ"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{name}.pkl"
    if path.exists():
        age = (time.time() - path.stat().st_mtime) / 3600.0
        if age <= max_age_hours:
            try:
                with open(path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass
    data = fetch_fn()
    with open(path, "wb") as f:
        pickle.dump(data, f)
    return data


# ---------------------------------------------------------------------------
# ticker → CIK (รหัสบริษัทของ SEC)
# ---------------------------------------------------------------------------

def get_cik(ticker: str) -> int:
    """แปลง ticker เป็นรหัส CIK — เก็บตารางไว้ 30 วันเพราะเปลี่ยนแปลงน้อยมาก"""
    ticker = ticker.strip().upper()
    table = _cached("ticker_map", 24 * 30, lambda: _get_json(TICKER_MAP_URL))
    for row in table.values():
        if str(row.get("ticker", "")).upper() == ticker:
            return int(row["cik_str"])
    raise ValueError(
        f"ไม่พบ '{ticker}' ในทะเบียนบริษัทของ SEC\n"
        f"  • EDGAR มีเฉพาะบริษัทที่จดทะเบียนในสหรัฐ\n"
        f"  • หุ้นไทย (.BK) ให้ใช้ yfinance แทน (ระบบจะเลือกให้อัตโนมัติ)"
    )


def get_company_facts(ticker: str) -> dict:
    """ดึงข้อมูลงบทั้งหมดที่บริษัทเคยยื่น (ไฟล์ใหญ่ ~2-15 MB) — เก็บ cache 24 ชม."""
    cik = get_cik(ticker)
    return _cached(f"facts_{ticker.upper()}", 24,
                   lambda: _get_json(FACTS_URL.format(cik=cik)))


# ---------------------------------------------------------------------------
# แกะข้อมูลจากโครงสร้าง XBRL
# ---------------------------------------------------------------------------

def _annual_values(entries) -> dict:
    """
    ดึงเฉพาะตัวเลข "รายปี" จากรายการทั้งหมด

    ปัญหาที่ต้องแก้ 3 ข้อ
      1. ในรายการมีทั้งรายไตรมาส (Q1/Q2/Q3) และรายปี → กรองด้วยความยาวช่วง 340-400 วัน
      2. งบเดียวกันถูกยื่นซ้ำหลายครั้ง (10-K ปีนี้แสดงตัวเลขปีก่อนด้วย)
         → เลือกฉบับที่ยื่นล่าสุด เพราะเป็นตัวเลขหลังปรับปรุงแล้ว
      3. มีทั้ง 10-K, 10-Q, 8-K → เอาเฉพาะ 10-K (งบประจำปีที่ผ่านการตรวจสอบ)
    """
    best = {}
    for e in entries:
        form = str(e.get("form", ""))
        if not form.startswith("10-K"):
            continue
        if e.get("fp") not in ("FY", None):
            continue
        start, end = e.get("start"), e.get("end")
        if not start or not end:
            continue
        try:
            days = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days
        except Exception:
            continue
        if not (340 <= days <= 400):      # ต้องเป็นช่วง 1 ปีเท่านั้น
            continue
        prev = best.get(end)
        if prev is None or str(e.get("filed", "")) >= str(prev.get("filed", "")):
            best[end] = e
    return {k: (float(v["val"]), str(v.get("filed", ""))) for k, v in best.items()}


def _instant_values(entries) -> dict:
    """ดึงตัวเลข ณ วันสิ้นงวด (ใช้กับงบดุล ซึ่งเป็นภาพ ณ จุดเวลา ไม่ใช่ช่วงเวลา)"""
    best = {}
    for e in entries:
        form = str(e.get("form", ""))
        if not form.startswith("10-K"):
            continue
        if e.get("start") or not e.get("end"):
            continue                      # มี start = เป็นช่วงเวลา ไม่ใช่ instant
        end = e["end"]
        prev = best.get(end)
        if prev is None or str(e.get("filed", "")) >= str(prev.get("filed", "")):
            best[end] = e
    return {k: (float(v["val"]), str(v.get("filed", ""))) for k, v in best.items()}


def _pull(facts: dict, tags, kind: str, with_filed: bool = False) -> dict:
    """
    รวมข้อมูลจากทุก tag ที่ระบุ ให้ครอบคลุมทุกปีมากที่สุด

    ทำไมต้อง "รวม" ไม่ใช่ "เจอตัวแรกแล้วหยุด"
    ------------------------------------------------
    มาตรฐานบัญชีเปลี่ยนเป็นระยะ บริษัทเดียวกันจึงใช้คนละ tag ในคนละยุค
    ตัวอย่างจริงของ Apple (เปลี่ยนมาตรฐาน ASC 606 ปี 2019)
        ปี 2011-2016 : SalesRevenueNet
        ปี 2017-2025 : RevenueFromContractWithCustomerExcludingAssessedTax
    ถ้าเจอตัวแรกแล้วหยุด จะได้ข้อมูลแค่ 9 ปี แทนที่จะเป็น 15 ปี

    ลำดับความสำคัญ : tag ที่อยู่ **ต้นรายการชนะ** เมื่อปีนั้นมีข้อมูลซ้ำกัน
    (จึงต้องใส่ tag ที่ตรงความหมายที่สุดไว้ก่อนเสมอ)

    ⚠️ ข้อควรระวัง : ทุก tag ในรายการเดียวกันต้องมี **ความหมายเดียวกัน**
       ห้ามใส่ tag ที่นิยามต่างกัน (เช่น "ดอกเบี้ยจ่าย" กับ "ดอกเบี้ยรับ-จ่ายสุทธิ")
       เพราะจะทำให้ตัวเลขคนละนิยามมาต่อกันในตารางเดียว → กราฟกระโดดโดยไม่มีเหตุผล
    """
    gaap = facts.get("facts", {}).get("us-gaap", {})
    picker = _annual_values if kind == "duration" else _instant_values
    merged = {}
    # ไล่จากท้ายรายการมาต้น เพื่อให้ tag ต้นรายการเขียนทับ (= ชนะ)
    for tag in reversed(list(tags)):
        node = gaap.get(tag)
        if not node:
            continue
        for unit in ("USD", "USD/shares", "shares"):
            if unit in node.get("units", {}):
                vals = picker(node["units"][unit])
                if vals:
                    merged.update(vals)
                break
    # merged = {วันสิ้นงวด: (ค่า, วันที่ยื่นงบ)}
    if with_filed:
        return merged
    return {k: v[0] for k, v in merged.items()}


# ---------------------------------------------------------------------------
# ตารางแปลง : tag ของ SEC → ชื่อบรรทัดแบบ yfinance
# ---------------------------------------------------------------------------

# ⚠️ ทุก tag ในรายการเดียวกันต้องมีความหมายเดียวกัน (ดูคำอธิบายใน _pull)
#    tag ที่อยู่ต้นรายการ = ตรงความหมายที่สุด จะชนะเมื่อมีข้อมูลซ้ำปีเดียวกัน
INCOME_TAGS = {
    # เรียงตามยุค : tag ใหม่ (หลัง ASC 606) ก่อน แล้วตามด้วย tag เก่า
    "Total Revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax",
                      "RevenueFromContractWithCustomerIncludingAssessedTax",
                      "SalesRevenueNet", "SalesRevenueGoodsNet", "Revenues"],
    "Cost Of Revenue": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
    "Gross Profit": ["GrossProfit"],
    "Research And Development": ["ResearchAndDevelopmentExpense"],
    # ไม่ใส่ GeneralAndAdministrativeExpense เพราะเป็น G&A อย่างเดียว ไม่รวม Selling
    "Selling General And Administration": ["SellingGeneralAndAdministrativeExpense"],
    # ไม่ใส่ CostsAndExpenses เพราะรวมต้นทุนขายด้วย นิยามต่างกัน
    "Operating Expense": ["OperatingExpenses"],
    "Operating Income": ["OperatingIncomeLoss"],
    # ไม่ใส่ InterestIncomeExpenseNet เพราะเป็นดอกเบี้ย "รับ-จ่ายสุทธิ" คนละนิยาม
    "Interest Expense": ["InterestExpense", "InterestExpenseNonoperating"],
    "Pretax Income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "Tax Provision": ["IncomeTaxExpenseBenefit"],
    "Net Income": ["NetIncomeLoss", "ProfitLoss"],
    "Diluted EPS": ["EarningsPerShareDiluted"],
    "Basic EPS": ["EarningsPerShareBasic"],
    "Diluted Average Shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "Basic Average Shares": ["WeightedAverageNumberOfSharesOutstandingBasic",
                             "WeightedAverageNumberOfSharesOutstanding"],
}

BALANCE_TAGS = {
    "Total Assets": ["Assets"],
    "Current Assets": ["AssetsCurrent"],
    "Cash And Cash Equivalents": ["CashAndCashEquivalentsAtCarryingValue"],
    "Other Short Term Investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent",
                                     "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "Inventory": ["InventoryNet"],
    "Accounts Receivable": ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
    "Net PPE": ["PropertyPlantAndEquipmentNet"],
    "Accounts Payable": ["AccountsPayableCurrent"],
    "Current Liabilities": ["LiabilitiesCurrent"],
    "Total Liabilities Net Minority Interest": ["Liabilities"],
    "Stockholders Equity": ["StockholdersEquity",
                            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    # กำไรสะสม — จำเป็นสำหรับ Altman Z-Score (ตัวแปร X2)
    #
    # ถ้าไม่มีบรรทัดนี้ Altman คำนวณไม่ได้เลยแม้จะมีข้อมูลอื่นครบ
    # ชื่อแท็กมาตรฐานของ US-GAAP คือ RetainedEarningsAccumulatedDeficit
    # (ชื่อรวมคำว่า Deficit ไว้ด้วย เพราะบริษัทที่ขาดทุนสะสมใช้แท็กเดียวกัน
    #  แต่ค่าเป็นลบ ซึ่งถูกต้องตามที่ Altman ต้องการ)
    "Retained Earnings": ["RetainedEarningsAccumulatedDeficit"],
    # ไม่ใส่ LongTermDebt (ยอดรวมทั้งก้อน) เพราะจะนับซ้ำกับ Current Debt ด้านล่าง
    "Long Term Debt": ["LongTermDebtNoncurrent"],
    "Current Debt": ["LongTermDebtCurrent", "DebtCurrent"],
    "Commercial Paper": ["CommercialPaper", "OtherShortTermBorrowings"],
}

CASHFLOW_TAGS = {
    "Operating Cash Flow": ["NetCashProvidedByUsedInOperatingActivities",
                            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "Investing Cash Flow": ["NetCashProvidedByUsedInInvestingActivities"],
    "Financing Cash Flow": ["NetCashProvidedByUsedInFinancingActivities"],
    "Depreciation And Amortization": ["DepreciationDepletionAndAmortization",
                                      "DepreciationAmortizationAndAccretionNet",
                                      "DepreciationAndAmortization"],
    "Capital Expenditure": ["PaymentsToAcquirePropertyPlantAndEquipment",
                            "PaymentsToAcquireProductiveAssets"],
    "Cash Dividends Paid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "Repurchase Of Capital Stock": ["PaymentsForRepurchaseOfCommonStock"],
    "Stock Based Compensation": ["ShareBasedCompensation"],
}


# ---------------------------------------------------------------------------
# แก้ปัญหาการแตกพาร์ (stock split)
# ---------------------------------------------------------------------------

# บรรทัดที่ได้รับผลจากการแตกพาร์
#   "ต่อหุ้น" → หารด้วยตัวคูณ (เช่น แตก 7:1 กำไรต่อหุ้นเดิม 28 บาท กลายเป็น 4 บาท)
#   "จำนวนหุ้น" → คูณด้วยตัวคูณ (หุ้นเดิม 1 ล้าน กลายเป็น 7 ล้าน)
PER_SHARE_ROWS = {"Diluted EPS", "Basic EPS"}
SHARE_COUNT_ROWS = {"Diluted Average Shares", "Basic Average Shares"}


def get_splits(ticker: str):
    """
    ดึงประวัติการแตกพาร์จาก yfinance — คืน list ของ (วันที่, ตัวคูณ)
    เช่น Apple : [(2014-06-09, 7.0), (2020-08-31, 4.0)]
    ถ้าดึงไม่ได้จะคืนรายการว่าง (ระบบยังทำงานต่อได้ แค่ไม่ปรับพาร์)
    """
    def fetch():
        import yfinance as yf
        s = yf.Ticker(ticker).splits
        out = []
        for d, r in s.items():
            try:
                out.append((pd.Timestamp(d).tz_localize(None).to_pydatetime(), float(r)))
            except Exception:
                continue
        return out
    try:
        return _cached(f"splits_{ticker.upper()}", 24 * 7, fetch)
    except Exception as e:
        print(f"  [เตือน] ดึงประวัติการแตกพาร์ไม่ได้ ({e}) — ตัวเลขต่อหุ้นอาจไม่เทียบกันได้",
              file=sys.stderr)
        return []


def _split_factor(filed_date: str, splits) -> float:
    """
    หาตัวคูณการแตกพาร์ที่ต้องใช้ปรับตัวเลขจากงบฉบับหนึ่ง

    หลักคิด : งบที่ยื่นวันที่ X จะรายงานตัวเลขตามฐานหุ้น ณ วันนั้น
    ถ้าหลังจากวันที่ X มีการแตกพาร์อีก ตัวเลขในงบฉบับนั้นจึงเป็น "ฐานเก่า"
    ต้องคูณด้วยการแตกพาร์ทุกครั้งที่เกิดขึ้น**หลัง**วันยื่น จึงจะเทียบกับปัจจุบันได้

    ตัวอย่าง Apple : งบ FY2013 ยื่น 2013-10-30
        หลังจากนั้นแตกพาร์ 7:1 (2014) และ 4:1 (2020) → ตัวคูณ = 28
        กำไรต่อหุ้นที่รายงานไว้ 39.75 → ปรับเป็น 39.75 / 28 = 1.42
    """
    if not filed_date or not splits:
        return 1.0
    try:
        filed = datetime.fromisoformat(filed_date[:10])
    except Exception:
        return 1.0
    factor = 1.0
    for d, ratio in splits:
        if d > filed and ratio > 0:
            factor *= ratio
    return factor


def _build(tag_map: dict, facts: dict, kind: str, years) -> pd.DataFrame:
    """สร้างตารางงบ 1 ชุด (แถว = ชื่อบรรทัด, คอลัมน์ = ปี)"""
    rows = {}
    for name, tags in tag_map.items():
        with_filed = name in PER_SHARE_ROWS or name in SHARE_COUNT_ROWS
        vals = _pull(facts, tags, kind, with_filed=with_filed)
        if not vals:
            continue
        if with_filed:
            # เก็บทั้งค่าและวันที่ยื่น เพื่อนำไปปรับการแตกพาร์ทีหลัง
            rows[name] = [_nearest({k: v[0] for k, v in vals.items()}, y, kind)
                          for y in years]
            rows[f"__filed__{name}"] = [
                _nearest_filed(vals, y) for y in years]
        else:
            rows[name] = [_nearest(vals, y, kind) for y in years]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, index=years).T


def _apply_split_adjustment(income: pd.DataFrame, years, splits) -> dict:
    """
    ปรับตัวเลขต่อหุ้นและจำนวนหุ้นให้เทียบกันได้ทั้ง 15 ปี (แก้ไขตารางในที่)

    ทำไมต้องทำ : EDGAR เก็บตัวเลข "ตามที่ยื่นวันนั้น" ไม่ปรับย้อนหลัง
    แต่งบ 10-K แต่ละฉบับแสดงย้อนหลัง 3 ปี ปีที่ถูกรายงานซ้ำในฉบับใหม่จึงถูกปรับ
    ส่วนปีเก่ากว่านั้นไม่ถูกปรับ → ตารางเดียวมีตัวเลขคนละฐานปนกัน

    อาการที่เห็นถ้าไม่แก้ (ตัวอย่างจริงของ Apple)
        กำไรต่อหุ้น CAGR 15 ปี = −8.9%   ทั้งที่กำไรรวมโต 11%/ปี
        เงินปันผลต่อหุ้น 2017 = 2.39 → 2018 = 0.69  (ตกฮวบเพราะเปลี่ยนฐาน)

    วิธีแก้ : ใช้ "วันที่ยื่นงบ" ของแต่ละตัวเลข คูณด้วยการแตกพาร์ทุกครั้งที่เกิด
    ขึ้นหลังวันนั้น → ทุกปีมาอยู่บนฐานปัจจุบันเหมือนกันหมด
    """
    report = {"มีการแตกพาร์": len(splits), "ปีที่ปรับ": []}
    if not splits:
        return _drop_helper_rows(income), report

    for name in list(PER_SHARE_ROWS | SHARE_COUNT_ROWS):
        filed_row = f"__filed__{name}"
        if name not in income.index or filed_row not in income.index:
            continue
        for y in years:
            val = income.loc[name, y]
            if pd.isna(val):
                continue
            f = _split_factor(str(income.loc[filed_row, y] or ""), splits)
            if f == 1.0:
                continue
            income.loc[name, y] = val / f if name in PER_SHARE_ROWS else val * f
            report["ปีที่ปรับ"].append((name, y[:4], round(f, 2)))

    return _drop_helper_rows(income), report


def _drop_helper_rows(df: pd.DataFrame) -> pd.DataFrame:
    """ลบแถวช่วย __filed__ ทิ้ง แล้วบังคับให้ทั้งตารางเป็นตัวเลข"""
    keep = [i for i in df.index if not str(i).startswith("__filed__")]
    return df.loc[keep].apply(pd.to_numeric, errors="coerce")


def _nearest_filed(vals: dict, target: str):
    """หาวันที่ยื่นงบของค่าที่ตรงกับปีนี้ (ใช้คู่กับ _nearest)"""
    if target in vals:
        return vals[target][1]
    try:
        t = datetime.fromisoformat(target)
    except Exception:
        return ""
    best, best_gap = "", timedelta(days=11)
    for k, v in vals.items():
        try:
            gap = abs(datetime.fromisoformat(k) - t)
        except Exception:
            continue
        if gap < best_gap:
            best, best_gap = v[1], gap
    return best


def _nearest(vals: dict, target: str, kind: str):
    """
    หาค่าที่ตรงกับวันสิ้นงวด

    งบดุลบางบรรทัดอาจมีวันสิ้นงวดคลาดกัน 1-3 วันจากงบกำไรขาดทุน
    (เช่น บริษัทที่ปิดงบวันศุกร์สุดท้ายของเดือน) จึงยอมให้คลาดได้ 10 วัน
    """
    if target in vals:
        return vals[target]
    try:
        t = datetime.fromisoformat(target)
    except Exception:
        return float("nan")
    best, best_gap = float("nan"), timedelta(days=11)
    for k, v in vals.items():
        try:
            gap = abs(datetime.fromisoformat(k) - t)
        except Exception:
            continue
        if gap < best_gap:
            best, best_gap = v, gap
    return best


# ---------------------------------------------------------------------------
# ฟังก์ชันหลัก
# ---------------------------------------------------------------------------

def get_edgar_statements(ticker: str, max_years: int = 15) -> dict:
    """
    ดึงงบ 3 ตัวจาก SEC EDGAR

    คืน dict : {"income": DataFrame, "balance": DataFrame,
                "cashflow": DataFrame, "years": [...], "source": "SEC EDGAR"}
    ชื่อบรรทัดเหมือน yfinance ทุกประการ → Part 2/3/4 ใช้ต่อได้เลย
    """
    facts = get_company_facts(ticker)

    # ใช้ "รายได้รวม" เป็นตัวกำหนดว่ามีปีไหนบ้าง
    rev = _pull(facts, INCOME_TAGS["Total Revenue"], "duration")
    if not rev:
        rev = _pull(facts, ["NetIncomeLoss"], "duration")
    if not rev:
        raise ValueError(f"ดึงข้อมูลรายปีของ {ticker} จาก EDGAR ไม่ได้")

    years = sorted(rev.keys())[-max_years:]

    income = _build(INCOME_TAGS, facts, "duration", years)
    balance = _build(BALANCE_TAGS, facts, "instant", years)
    cashflow = _build(CASHFLOW_TAGS, facts, "duration", years)

    # --- ปรับตัวเลข "ต่อหุ้น" และ "จำนวนหุ้น" ให้เป็นฐานเดียวกันทั้งหมด ---
    splits = get_splits(ticker)
    income, split_report = _apply_split_adjustment(income, years, splits)

    # --- คำนวณบรรทัดที่ EDGAR ไม่มีให้ตรง ๆ ---
    def R(df, name):
        return df.loc[name] if name in df.index else pd.Series([float("nan")] * len(years), index=years)

    # หนี้สินมีดอกเบี้ยรวม = หนี้ระยะยาว + หนี้ระยะสั้น + ตั๋วเงินระยะสั้น
    total_debt = (R(balance, "Long Term Debt").fillna(0)
                  + R(balance, "Current Debt").fillna(0)
                  + R(balance, "Commercial Paper").fillna(0))
    if total_debt.abs().sum() > 0:
        balance.loc["Total Debt"] = total_debt
        balance.loc["Net Debt"] = (total_debt
                                   - R(balance, "Cash And Cash Equivalents").fillna(0)
                                   - R(balance, "Other Short Term Investments").fillna(0))
        # เงินลงทุนในกิจการ = หนี้มีดอกเบี้ย + ส่วนของผู้ถือหุ้น
        balance.loc["Invested Capital"] = total_debt + R(balance, "Stockholders Equity").fillna(0)

    # EBIT / EBITDA — EDGAR ไม่มี tag ตรง ๆ ต้องคำนวณเอง
    op = R(income, "Operating Income")
    pretax = R(income, "Pretax Income")
    int_exp = R(income, "Interest Expense")
    ebit = op.where(op.notna(), pretax + int_exp.fillna(0))
    income.loc["EBIT"] = ebit
    income.loc["EBITDA"] = ebit + R(cashflow, "Depreciation And Amortization").fillna(0)

    # กระแสเงินสดอิสระ
    if "Operating Cash Flow" in cashflow.index:
        cashflow.loc["Free Cash Flow"] = (R(cashflow, "Operating Cash Flow")
                                          - R(cashflow, "Capital Expenditure").abs().fillna(0))

    # กำไรขั้นต้น : ถ้าไม่มี tag ให้คำนวณจาก รายได้ − ต้นทุน
    if "Gross Profit" not in income.index and "Cost Of Revenue" in income.index:
        income.loc["Gross Profit"] = R(income, "Total Revenue") - R(income, "Cost Of Revenue")

    for df in (income, balance, cashflow):
        df.dropna(how="all", inplace=True)

    return {
        "income": income,
        "balance": balance,
        "cashflow": cashflow,
        "years": years,
        "source": "SEC EDGAR",
        "cik": get_cik(ticker),
        "entity": facts.get("entityName", ticker),
        "splits": splits,
        "split_report": split_report,
    }


def is_us_ticker(ticker: str) -> bool:
    """
    เดาว่าเป็นหุ้นสหรัฐไหม — หุ้นต่างประเทศใน yfinance จะมีจุดต่อท้าย
    เช่น PTT.BK (ไทย), 7203.T (ญี่ปุ่น), NESN.SW (สวิส)
    """
    return "." not in (ticker or "").strip()


# ---------------------------------------------------------------------------
# รันจาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Part 1b — ดึงงบจาก SEC EDGAR")
    p.add_argument("ticker")
    p.add_argument("--years", type=int, default=15, help="จำนวนปีย้อนหลัง (ค่าเริ่มต้น 15)")
    args = p.parse_args()

    try:
        res = get_edgar_statements(args.ticker, args.years)
    except Exception as e:
        print(f"\n[ไม่สำเร็จ] {type(e).__name__}: {e}\n", file=sys.stderr)
        return 1

    years = res["years"]
    print("=" * (30 + 10 * len(years)))
    print(f"  SEC EDGAR : {res['entity']}  (CIK {res['cik']})")
    print(f"  ได้ข้อมูล {len(years)} ปี : {years[0][:4]} – {years[-1][:4]}")
    print("=" * (30 + 10 * len(years)))

    if res["splits"]:
        s = ", ".join(f"{d.strftime('%Y')} = {r:.0f}:1" for d, r in res["splits"])
        print(f"  ประวัติแตกพาร์ : {s}")
        print(f"  ปรับตัวเลขต่อหุ้นให้เป็นฐานเดียวกันแล้ว "
              f"{len(res['split_report']['ปีที่ปรับ'])} จุด")

    show = [("รายได้รวม", "Total Revenue", res["income"]),
            ("กำไรขั้นต้น", "Gross Profit", res["income"]),
            ("กำไรสุทธิ", "Net Income", res["income"]),
            ("กำไรต่อหุ้น (ปรับพาร์)", "Diluted EPS", res["income"]),
            ("ดอกเบี้ยจ่าย", "Interest Expense", res["income"]),
            ("ส่วนของผู้ถือหุ้น", "Stockholders Equity", res["balance"]),
            ("กระแสเงินสดดำเนินงาน", "Operating Cash Flow", res["cashflow"]),
            ("กระแสเงินสดอิสระ", "Free Cash Flow", res["cashflow"])]

    print("\n  (หน่วย: ล้าน)")
    print("  {:<22}".format("") + "".join(f"{y[:4]:>10}" for y in years))
    for thai, key, df in show:
        line = f"  {thai:<22}"
        for y in years:
            v = df.loc[key, y] if key in df.index else float("nan")
            if pd.isna(v):
                line += f"{'-':>10}"
            elif "ต่อหุ้น" in thai:          # EPS เป็นหน่วยดอลลาร์/หุ้น ไม่ต้องหารล้าน
                line += f"{v:>10,.2f}"
            else:
                line += f"{v/1e6:>10,.0f}"
        print(line)

    print()
    print(f"  งบกำไรขาดทุน : {res['income'].shape[0]} บรรทัด")
    print(f"  งบดุล        : {res['balance'].shape[0]} บรรทัด")
    print(f"  งบกระแสเงินสด: {res['cashflow'].shape[0]} บรรทัด")
    print("=" * (30 + 10 * len(years)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
