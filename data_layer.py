"""
data_layer.py — Part 1 : Data Layer
====================================
หน้าที่ : ดึงข้อมูลหุ้นจาก yfinance เข้ามาเก็บในรูปแบบมาตรฐาน + ระบบ cache

ทำไมต้องมี cache ?
  yfinance เป็นบริการฟรี ถ้ายิงถี่เกินไปจะโดนบล็อก (Too Many Requests)
  โปรแกรมนี้จึงเก็บข้อมูลที่ดึงมาแล้วลงไฟล์ ครั้งต่อไปอ่านจากไฟล์แทน
  ค่าเริ่มต้น = ข้อมูลอายุไม่เกิน 24 ชั่วโมง ถือว่ายังใช้ได้

วิธีใช้จาก Terminal
-------------------
    python3 data_layer.py AAPL           # ดึง (หรืออ่านจาก cache)
    python3 data_layer.py AAPL --refresh # บังคับดึงใหม่ ไม่สนใจ cache
    python3 data_layer.py PTT.BK         # หุ้นไทย ต้องมี .BK ต่อท้ายเสมอ

วิธีใช้จากไฟล์ Python อื่น (Part 2, 3, 4 จะเรียกแบบนี้)
------------------------------------------------------
    from data_layer import get_stock_data, find_row
    d = get_stock_data("AAPL")
    revenue = find_row(d["income"], ["Total Revenue", "Revenue"])
"""

import argparse
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# ค่าคงที่ของโมดูล
# ---------------------------------------------------------------------------

# โฟลเดอร์ cache จะอยู่ข้าง ๆ ไฟล์นี้เสมอ (ไม่ว่าจะรันจากที่ไหน)
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
DEFAULT_MAX_AGE_HOURS = 24  # cache เก่ากว่านี้ถือว่าหมดอายุ

# ก้อนข้อมูลที่ระบบนี้รับประกันว่าจะมีเสมอ
REQUIRED_KEYS = ("ticker", "info", "income", "balance", "cashflow", "prices")

# เวอร์ชันของโครงสร้างข้อมูล — เพิ่มเลขนี้ทุกครั้งที่แก้วิธีจัดรูปแบบข้อมูล
# cache เก่าที่เวอร์ชันไม่ตรงจะถูกทิ้งและดึงใหม่อัตโนมัติ
# (ป้องกันปัญหา "แก้โค้ดแล้วแต่ยังเห็นข้อมูลเก่าผิด ๆ")
SCHEMA_VERSION = 3


# ---------------------------------------------------------------------------
# ตัวช่วย : หาชื่อบรรทัดในงบการเงิน
# ---------------------------------------------------------------------------

def find_row(df: pd.DataFrame, candidates, default=None):
    """
    หาบรรทัดในงบการเงิน โดยลองหลายชื่อ

    ทำไมต้องมีฟังก์ชันนี้ ?
      yfinance ตั้งชื่อบรรทัดไม่เหมือนกันทุกหุ้น เช่นบางตัวใช้ "Total Revenue"
      บางตัวใช้ "Operating Revenue" ถ้าเขียน df.loc["Total Revenue"] ตรง ๆ
      โปรแกรมจะพังทันทีเมื่อเจอหุ้นที่ตั้งชื่อต่าง

    ขั้นตอนการหา (ไล่จากแม่นยำที่สุดไปหลวมที่สุด)
      1. ชื่อตรงเป๊ะ
      2. ชื่อตรงเป๊ะแบบไม่สนตัวพิมพ์เล็ก/ใหญ่และช่องว่าง
      3. ชื่อที่มีคำนั้นอยู่ข้างใน

    คืนค่า : pandas Series (ค่ารายปี) หรือ `default` ถ้าไม่เจอ
    """
    if df is None or df.empty:
        return default

    if isinstance(candidates, str):
        candidates = [candidates]

    index_list = list(df.index)

    # รอบที่ 1 : ตรงเป๊ะ
    for name in candidates:
        if name in index_list:
            return df.loc[name]

    # รอบที่ 2 : ไม่สนตัวพิมพ์เล็ก/ใหญ่ และช่องว่าง
    normalized = {str(i).lower().replace(" ", ""): i for i in index_list}
    for name in candidates:
        key = name.lower().replace(" ", "")
        if key in normalized:
            return df.loc[normalized[key]]

    # รอบที่ 3 : มีคำนั้นอยู่ข้างใน
    for name in candidates:
        key = name.lower().replace(" ", "")
        for norm_key, original in normalized.items():
            if key in norm_key:
                return df.loc[original]

    return default


# ---------------------------------------------------------------------------
# ตัวช่วยเรื่อง cache
# ---------------------------------------------------------------------------

def _cache_file(ticker: str) -> Path:
    """ที่อยู่ไฟล์ cache ของหุ้นตัวนี้ เช่น cache/AAPL.pkl"""
    safe = ticker.upper().replace("/", "_")
    return CACHE_DIR / f"{safe}.pkl"


def _cache_age_hours(path: Path):
    """cache เก่ากี่ชั่วโมงแล้ว — คืน None ถ้ายังไม่มีไฟล์"""
    if not path.exists():
        return None
    return (time.time() - path.stat().st_mtime) / 3600.0


def _load_cache(ticker: str, max_age_hours: float):
    """อ่าน cache ถ้ายังไม่หมดอายุ — คืน None ถ้าไม่มีหรือหมดอายุแล้ว"""
    if max_age_hours <= 0:
        return None  # ตั้ง max-age เป็น 0 = สั่งให้ดึงใหม่เสมอ
    path = _cache_file(ticker)
    age = _cache_age_hours(path)
    if age is None or age > max_age_hours:
        return None
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
    except Exception:
        # ไฟล์เสีย → ถือว่าไม่มี cache แล้วดึงใหม่
        return None
    if not all(k in data for k in REQUIRED_KEYS):
        return None
    if data.get("_schema") != SCHEMA_VERSION:
        print("  [ข้าม] cache เป็นรูปแบบเก่า → ดึงข้อมูลใหม่", file=sys.stderr)
        return None
    data["_from_cache"] = True
    data["_cache_age_hours"] = max(0.0, round(age, 2))
    return data


def _save_cache(ticker: str, data: dict) -> None:
    """เขียน cache ลงไฟล์ + เขียน CSV ไว้เปิดดูด้วยตาเอง"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_cache_file(ticker), "wb") as f:
        pickle.dump(data, f)

    # CSV สำหรับเปิดดูใน Excel/Numbers เวลาอยากตรวจตัวเลขด้วยมือ
    csv_dir = CACHE_DIR / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    safe = ticker.upper().replace("/", "_")
    for name in ("income", "balance", "cashflow"):
        df = data.get(name)
        if isinstance(df, pd.DataFrame) and not df.empty:
            df.to_csv(csv_dir / f"{safe}_{name}.csv", encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# ตัวช่วย : จัดรูปแบบตารางงบให้เป็นมาตรฐาน
# ---------------------------------------------------------------------------

def _standardize(df, drop_sparse: bool = True) -> pd.DataFrame:
    """
    ทำให้ตารางงบการเงินอยู่ในรูปแบบเดียวกันเสมอ
      - คอลัมน์เป็นข้อความวันที่ 'YYYY-MM-DD'
      - เรียงจากปีเก่า → ปีใหม่ (ซ้ายไปขวา)  ← สำคัญมากสำหรับการคำนวณ CAGR
      - ค่าทั้งหมดเป็นตัวเลข (float) ถ้าแปลงไม่ได้จะเป็นค่าว่าง

    drop_sparse : ตัดคอลัมน์ที่ข้อมูลไม่ครบทิ้งไหม
        True  = ใช้กับ yfinance (มักแถมคอลัมน์ขยะมา)
        False = ใช้กับ EDGAR (ปีเก่ามีบรรทัดน้อยกว่าเป็นเรื่องปกติ ไม่ใช่ขยะ)
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # คอลัมน์ของ yfinance เป็น Timestamp → แปลงเป็นข้อความ
    new_cols = []
    for c in df.columns:
        try:
            new_cols.append(pd.Timestamp(c).strftime("%Y-%m-%d"))
        except Exception:
            new_cols.append(str(c))
    df.columns = new_cols

    # เรียงปีเก่าไปใหม่
    df = df[sorted(df.columns)]

    # บังคับให้เป็นตัวเลข
    df = df.apply(pd.to_numeric, errors="coerce")

    # ตัดบรรทัดที่ว่างเปล่าทั้งแถวทิ้ง
    df = df.dropna(how="all")

    # --- ตัด "คอลัมน์ขยะ" ทิ้ง ---
    # yfinance มักแถมคอลัมน์ปีเก่าสุดที่มีข้อมูลแค่ 3-8 บรรทัด (จากทั้งหมด 40-70 บรรทัด)
    # ถ้าปล่อยไว้ CAGR จะคำนวณจากปีฐานที่เป็นค่าว่าง → ผลลัพธ์ผิดทั้งระบบ
    # เกณฑ์ : คอลัมน์ต้องมีข้อมูลอย่างน้อย 50% ของคอลัมน์ที่สมบูรณ์ที่สุด
    if drop_sparse and not df.empty:
        counts = df.notna().sum()
        threshold = max(1, counts.max() * 0.5)
        keep = counts[counts >= threshold].index
        dropped = [c for c in df.columns if c not in keep]
        if dropped:
            print(f"  [ข้าม] ตัดคอลัมน์ข้อมูลไม่ครบ: {', '.join(dropped)}", file=sys.stderr)
        df = df[list(keep)]
        df = df.dropna(how="all")

    return df


# ---------------------------------------------------------------------------
# ฟังก์ชันหลัก
# ---------------------------------------------------------------------------

def get_stock_data(
    ticker: str,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    force_refresh: bool = False,
    price_period: str = "max",
    deep: bool = True,
    edgar_years: int = 15,
) -> dict:
    """
    ดึงข้อมูลหุ้น 1 ตัว คืนเป็น dict ที่มี key เหล่านี้เสมอ

        ticker    : ชื่อย่อหุ้น (ตัวพิมพ์ใหญ่)
        info      : dict ข้อมูลบริษัท (ชื่อ, sector, จำนวนหุ้น, ราคาปัจจุบัน)
        income    : DataFrame งบกำไรขาดทุน (คอลัมน์ = ปี เรียงเก่า→ใหม่)
        balance   : DataFrame งบดุล
        cashflow  : DataFrame งบกระแสเงินสด
        prices    : DataFrame ราคาย้อนหลัง (Open/High/Low/Close/Volume)
        fetched_at: เวลาที่ดึงข้อมูล
        statements_source : "SEC EDGAR" หรือ "yfinance"

    การเลือกแหล่งงบการเงิน (deep=True)
        หุ้นสหรัฐ (ไม่มีจุดใน ticker)  → SEC EDGAR ~15 ปี  ← งบที่ยื่นจริง
        หุ้นต่างประเทศ เช่น PTT.BK    → yfinance 4 ปี
        ถ้า EDGAR ล้มเหลว จะถอยกลับมาใช้ yfinance อัตโนมัติ
    ราคาและข้อมูลบริษัทดึงจาก yfinance เสมอ (EDGAR ไม่มีราคาหุ้น)

    ถ้า ticker ไม่มีอยู่จริง จะโยน ValueError พร้อมข้อความภาษาไทย
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        raise ValueError("กรุณาระบุ ticker เช่น AAPL หรือ PTT.BK")

    # ---- 1) ลองอ่านจาก cache ก่อน ----
    if not force_refresh:
        cached = _load_cache(ticker, max_age_hours)
        if cached is not None:
            return cached

    # ---- 2) ดึงจากอินเทอร์เน็ต ----
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError(
            "ยังไม่ได้ติดตั้ง yfinance\n"
            "แก้โดยพิมพ์ใน Terminal:  pip install yfinance"
        )

    t = yf.Ticker(ticker)

    # info บางครั้งช้าหรือพัง จึงต้องหุ้มด้วย try
    try:
        info = dict(t.info or {})
    except Exception:
        info = {}

    def _safe(getter, label):
        """เรียกดึงข้อมูลแบบไม่ให้พังทั้งโปรแกรมถ้าก้อนใดก้อนหนึ่งมีปัญหา"""
        try:
            return getter()
        except Exception as e:
            print(f"  [เตือน] ดึง {label} ไม่สำเร็จ: {e}", file=sys.stderr)
            return pd.DataFrame()

    income = _standardize(_safe(lambda: t.income_stmt, "งบกำไรขาดทุน"))
    balance = _standardize(_safe(lambda: t.balance_sheet, "งบดุล"))
    cashflow = _standardize(_safe(lambda: t.cashflow, "งบกระแสเงินสด"))
    prices = _safe(lambda: t.history(period=price_period, auto_adjust=False), "ราคา")

    # ---- 3) ตรวจว่า ticker มีอยู่จริงไหม ----
    has_name = bool(info.get("longName") or info.get("shortName"))
    has_statements = not income.empty or not balance.empty
    has_prices = isinstance(prices, pd.DataFrame) and not prices.empty

    if not (has_name or has_statements or has_prices):
        raise ValueError(
            f"ไม่พบข้อมูลหุ้น '{ticker}'\n"
            f"  • ตรวจการสะกดอีกครั้ง\n"
            f"  • หุ้นไทยต้องมี .BK ต่อท้าย เช่น PTT.BK, TQM.BK\n"
            f"  • ถ้าสะกดถูกแล้วยังไม่ได้ อาจโดนจำกัดการเรียกชั่วคราว รอ 1–2 นาทีแล้วลองใหม่"
        )

    # ---- 4) หุ้นสหรัฐ : ใช้งบจาก SEC EDGAR แทน (ลึกกว่ามาก ~15 ปี) ----
    statements_source = "yfinance"
    if deep:
        try:
            from edgar_layer import get_edgar_statements, is_us_ticker
        except ImportError:
            is_us_ticker = None
        if is_us_ticker is not None and is_us_ticker(ticker):
            try:
                print("  กำลังดึงงบย้อนหลังจาก SEC EDGAR ...", file=sys.stderr)
                ed = get_edgar_statements(ticker, max_years=edgar_years)
                # EDGAR ไม่ต้องตัดคอลัมน์ เพราะปีเก่ามีบรรทัดน้อยกว่าเป็นเรื่องปกติ
                income = _standardize(ed["income"], drop_sparse=False)
                balance = _standardize(ed["balance"], drop_sparse=False)
                cashflow = _standardize(ed["cashflow"], drop_sparse=False)
                statements_source = "SEC EDGAR"
                print(f"  ได้งบ {len(ed['years'])} ปี จาก SEC EDGAR", file=sys.stderr)
            except Exception as e:
                # EDGAR ล้มเหลว → ใช้ yfinance ต่อไป ไม่ให้ทั้งระบบพัง
                print(f"  [เตือน] ดึงจาก EDGAR ไม่สำเร็จ ({e}) → ใช้ yfinance แทน",
                      file=sys.stderr)

    data = {
        "ticker": ticker,
        "info": info,
        "income": income,
        "balance": balance,
        "cashflow": cashflow,
        "statements_source": statements_source,
        "prices": prices if isinstance(prices, pd.DataFrame) else pd.DataFrame(),
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "_schema": SCHEMA_VERSION,
        "_from_cache": False,
        "_cache_age_hours": 0.0,
    }

    _save_cache(ticker, data)
    return data


# ---------------------------------------------------------------------------
# ตัวช่วยอ่านค่าที่ใช้บ่อย (Part อื่นจะเรียกใช้)
# ---------------------------------------------------------------------------

def get_years(data: dict):
    """คืนรายการปีที่มีข้อมูลงบ เช่น ['2021-09-25', ..., '2024-09-28']"""
    income = data.get("income")
    if isinstance(income, pd.DataFrame) and not income.empty:
        return list(income.columns)
    return []


def get_shares_outstanding(data: dict):
    """จำนวนหุ้น — ลองหลายที่เพราะ yfinance ไม่ได้ใส่ให้ครบทุกตัว"""
    info = data.get("info", {})
    for key in ("sharesOutstanding", "impliedSharesOutstanding", "floatShares"):
        v = info.get(key)
        if v:
            return float(v)
    # แผนสำรอง : หาจากงบดุล
    row = find_row(data.get("balance"), ["Ordinary Shares Number", "Share Issued"])
    if row is not None and not row.dropna().empty:
        return float(row.dropna().iloc[-1])
    return None


def get_current_price(data: dict):
    """ราคาปัจจุบัน — ถ้า info ไม่มี ใช้ราคาปิดล่าสุดแทน"""
    info = data.get("info", {})
    for key in ("currentPrice", "regularMarketPrice", "previousClose"):
        v = info.get(key)
        if v:
            return float(v)
    prices = data.get("prices")
    if isinstance(prices, pd.DataFrame) and not prices.empty and "Close" in prices:
        return float(prices["Close"].dropna().iloc[-1])
    return None


# ---------------------------------------------------------------------------
# แสดงผลสรุปบนหน้าจอ (ใช้ตอนทดสอบ)
# ---------------------------------------------------------------------------

def print_summary(data: dict) -> None:
    info = data.get("info", {})
    name = info.get("longName") or info.get("shortName") or "(ไม่ทราบชื่อ)"
    currency = info.get("currency", "")
    price = get_current_price(data)
    shares = get_shares_outstanding(data)
    years = get_years(data)

    src = "อ่านจาก cache" if data.get("_from_cache") else "ดึงใหม่จากอินเทอร์เน็ต"
    age = data.get("_cache_age_hours", 0)

    print("=" * 68)
    print(f"  {data['ticker']} — {name}")
    print("=" * 68)
    print(f"  แหล่งข้อมูล      : {src}" + (f" (อายุ {age} ชม.)" if data.get("_from_cache") else ""))
    print(f"  งบการเงินจาก     : {data.get('statements_source', 'yfinance')}")
    print(f"  ตลาด / สกุลเงิน  : {info.get('exchange', '-')} / {currency or '-'}")
    print(f"  กลุ่มอุตสาหกรรม  : {info.get('sector', '-')} / {info.get('industry', '-')}")
    print(f"  ราคาปัจจุบัน     : {price:,.2f} {currency}" if price else "  ราคาปัจจุบัน     : ไม่พบ")
    print(f"  จำนวนหุ้น        : {shares:,.0f}" if shares else "  จำนวนหุ้น        : ไม่พบ")
    print()
    print(f"  งบกำไรขาดทุน    : {data['income'].shape[0]} บรรทัด × {data['income'].shape[1]} ปี")
    print(f"  งบดุล            : {data['balance'].shape[0]} บรรทัด × {data['balance'].shape[1]} ปี")
    print(f"  งบกระแสเงินสด   : {data['cashflow'].shape[0]} บรรทัด × {data['cashflow'].shape[1]} ปี")
    print(f"  ราคาย้อนหลัง     : {len(data['prices']):,} วัน")
    print(f"  ปีที่มีข้อมูล     : {', '.join(y[:4] for y in years) or '-'}")
    print()

    # แสดงตัวเลขสำคัญ 4 บรรทัด เพื่อให้ตรวจด้วยตาได้ทันที
    checks = [
        ("รายได้รวม",        ["Total Revenue", "Operating Revenue"]),
        ("กำไรขั้นต้น",       ["Gross Profit"]),
        ("กำไรสุทธิ",        ["Net Income", "Net Income Common Stockholders"]),
        ("ส่วนของผู้ถือหุ้น", None),
    ]
    print("  ตัวเลขสำคัญ (หน่วย: ล้าน)")
    print("  " + "-" * 64)
    header = "  {:<18}".format("") + "".join(f"{y[:4]:>11}" for y in years)
    print(header)
    for label, names in checks:
        if names is None:
            row = find_row(data["balance"], ["Stockholders Equity", "Total Equity Gross Minority Interest"])
        else:
            row = find_row(data["income"], names)
        if row is None:
            print(f"  {label:<18}" + "     ไม่พบ")
            continue
        line = f"  {label:<18}"
        for y in years:
            v = row.get(y)
            line += f"{v/1e6:>11,.0f}" if pd.notna(v) else f"{'-':>11}"
        print(line)
    print("=" * 68)


# ---------------------------------------------------------------------------
# รันจาก Terminal
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Part 1 — ดึงข้อมูลหุ้นเข้ามาเก็บพร้อมระบบ cache"
    )
    parser.add_argument("ticker", help="ชื่อย่อหุ้น เช่น AAPL หรือ PTT.BK")
    parser.add_argument("--refresh", action="store_true",
                        help="บังคับดึงใหม่ ไม่สนใจ cache")
    parser.add_argument("--max-age", type=float, default=DEFAULT_MAX_AGE_HOURS,
                        help=f"อายุ cache สูงสุด (ชั่วโมง) ค่าเริ่มต้น {DEFAULT_MAX_AGE_HOURS}")
    parser.add_argument("--no-deep", action="store_true",
                        help="ไม่ใช้ SEC EDGAR ใช้ yfinance อย่างเดียว (ไว้เทียบผลลัพธ์)")
    parser.add_argument("--years", type=int, default=15,
                        help="จำนวนปีย้อนหลังที่ดึงจาก EDGAR (ค่าเริ่มต้น 15)")
    args = parser.parse_args()

    try:
        data = get_stock_data(
            args.ticker,
            max_age_hours=args.max_age,
            force_refresh=args.refresh,
            deep=not args.no_deep,
            edgar_years=args.years,
        )
    except ValueError as e:
        print(f"\n[ไม่สำเร็จ] {e}\n", file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"\n[ไม่สำเร็จ] {e}\n", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n[ไม่สำเร็จ] เกิดข้อผิดพลาดที่ไม่คาดคิด: {type(e).__name__}: {e}\n",
              file=sys.stderr)
        return 1

    print_summary(data)
    print(f"บันทึก cache ไว้ที่ : {_cache_file(data['ticker'])}")
    print(f"ไฟล์ CSV สำหรับตรวจ : {CACHE_DIR / 'csv'}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
