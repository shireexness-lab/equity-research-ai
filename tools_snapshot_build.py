"""
tools_snapshot_build.py — คัดกรองทั้งตลาดบน MacBook แล้วส่งผลขึ้น Google Drive
===============================================================================
ปัญหาที่แก้
-----------
Yahoo Finance บล็อกคำขอที่มาจากศูนย์ข้อมูล ซึ่งรวมถึง Streamlit Cloud
พอกดคัดกรองบนเว็บจึงได้ 0 ตัว ทั้งที่รันบน MacBook แล้วได้ครบ

ทำไมบล็อก : Yahoo ไม่อยากให้ใครดูดข้อมูลไปทำระบบเชิงพาณิชย์
เครื่องบ้าน/มือถือดูเหมือนคนใช้งานจริง เครื่องในศูนย์ข้อมูลดูเหมือนหุ่นยนต์
IP ของ Streamlit Cloud ยังใช้ร่วมกับผู้ใช้คนอื่นทั้งโลกด้วย จึงโดนบล็อกง่ายกว่า

วิธีแก้ที่ได้ผลแน่นอน
---------------------
    [ MacBook ]  ดึงข้อมูล -> บันทึกลง Google Drive
                                      |
    [ เว็บ / iPhone ]  กดปุ่ม ⚡ -> อ่านจาก Drive -> ได้ผลใน 2 วินาที

เว็บไม่ต้องคุยกับ Yahoo เลย จึงไม่มีทางโดนบล็อก

วิธีใช้
-------
    python3 tools_snapshot_build.py --thai            # หุ้นไทยทั้งตลาด
    python3 tools_snapshot_build.py --us              # หุ้นสหรัฐยอดนิยม
    python3 tools_snapshot_build.py --us-all          # หุ้นสหรัฐทั้งตลาด (SEC)
    python3 tools_snapshot_build.py --thai --limit 50 # ทดลองด้วย 50 ตัวก่อน

ทำให้อัตโนมัติทุกเช้า (ไม่บังคับ)
----------------------------------
    crontab -e
    แล้วใส่บรรทัดนี้ (รันทุกวัน 8 โมงเช้า)
    0 8 * * * cd ~/equity-research-ai && .venv/bin/python tools_snapshot_build.py --thai
"""

import argparse
import sys
import time

import snapshot


def _bar(i, total, msg=""):
    """แถบความคืบหน้าแบบง่าย ๆ ใน Terminal"""
    w = 34
    frac = min(i / total, 1.0) if total else 0
    fill = int(w * frac)
    sys.stdout.write(f"\r  [{'█'*fill}{'·'*(w-fill)}] {frac*100:5.1f}%  "
                     f"{str(msg)[:34]:<34}")
    sys.stdout.flush()


def build(kind: str, limit: int = 0, market=None, industry=None) -> int:
    from screener import preset, quick_screen

    t0 = time.time()

    if kind == "us-all":
        from market import us_market_snapshot
        key = "us-all"
        print(f"\nคัดกรองหุ้นสหรัฐทั้งตลาดผ่าน SEC EDGAR")
        print("-" * 58)
        df = us_market_snapshot(progress=_bar)
    else:
        if kind == "thai":
            from tickers import thai_universe
            uni = thai_universe(market=market, industry=industry)
            mk = market or "ทั้งหมด"
            ind = industry or "ทุกกลุ่ม"
            uni = uni[:limit] if limit else uni
            key = f"thai-{mk}-{ind}-{len(uni)}"
        else:
            uni = preset("us")
            uni = uni[:limit] if limit else uni
            key = f"us-{len(uni)}"

        print(f"\nคัดกรอง {len(uni):,} ตัว  (ชื่อชุดข้อมูล: {key})")
        print("-" * 58)
        df = quick_screen(uni, progress=_bar)

    print()
    n_new = int(df["ปัญหา"].eq("").sum())
    mins = (time.time() - t0) / 60
    print(f"\n  ดึงสำเร็จ : {n_new:,} / {len(df):,} ตัว  "
          f"({n_new/len(df)*100 if len(df) else 0:.0f}%)")
    print(f"  ใช้เวลา   : {mins:.1f} นาที")

    # ---- รวมกับของเดิม ----
    # ตัวที่พลาดไม่ใช่ตัวเดียวกันทุกรอบ การรวมจึงทำให้ยิ่งดึงยิ่งครบ
    # และไม่มีทางที่ข้อมูลดีที่เคยได้มาแล้วจะหายไป
    prev, _ = snapshot.info(key)
    df = snapshot.merge(prev, df)
    n_ok = int(df["ปัญหา"].eq("").sum())
    if prev is not None:
        gain = n_ok - n_new
        print(f"  รวมของเดิม: {n_ok:,} / {len(df):,} ตัว"
              + (f"  (ได้เพิ่มจากรอบก่อน {gain:,} ตัว)" if gain > 0 else ""))

    if n_ok == 0:
        print("\n  [ไม่บันทึก] ไม่มีข้อมูลที่ใช้ได้เลย")
        errs = df.loc[~df["ปัญหา"].eq(""), "ปัญหา"].value_counts()
        print("\n  สาเหตุที่พบบ่อย:")
        for msg, n in errs.head(5).items():
            print(f"    {n:>6,} ตัว  {msg}")
        print()
        return 1

    r = snapshot.save(key, df, to_repo=True,
                      extra={"ขอบเขต": key, "ดึงสำเร็จ": n_ok, "แหล่ง": "MacBook"})
    print(f"\n  บันทึก    : {r.get('ขนาด (KB)', 0)} KB")
    print(f"    ในโปรเจกต์   : {'สำเร็จ' if r['repo'] else 'ไม่สำเร็จ'}"
          "   (data/snapshots/)")
    print(f"    เครื่องนี้    : {'สำเร็จ' if r['local'] else 'ไม่สำเร็จ'}")
    if r["drive"]:
        print("    Google Drive : สำเร็จ")

    if r["repo"]:
        print("\n  " + "=" * 54)
        print("  ขั้นต่อไป — ส่งขึ้นเว็บ (คัดลอกไปวางใน Terminal ได้เลย)")
        print("  " + "=" * 54)
        print("\n    git add data/snapshots")
        print(f'    git commit -m "อัปเดตข้อมูลคัดกรอง {key}"')
        print("    git push")
        print("\n  รอ 1-2 นาทีให้เว็บโหลดใหม่ แล้วกดปุ่ม ⚡ ได้ทั้งบนเว็บและมือถือ")
    print()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="คัดกรองทั้งตลาดบนเครื่องนี้ แล้วเก็บผลไว้ให้เว็บ/มือถือเรียกใช้")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--thai", action="store_true", help="หุ้นไทยทั้งตลาด")
    g.add_argument("--us", action="store_true", help="หุ้นสหรัฐยอดนิยม")
    g.add_argument("--us-all", action="store_true",
                   help="หุ้นสหรัฐทั้งตลาดผ่าน SEC EDGAR")
    p.add_argument("--limit", type=int, default=0, help="จำกัดจำนวน (0 = ไม่จำกัด)")
    p.add_argument("--market", default=None, help="เฉพาะหุ้นไทย: SET หรือ mai")
    p.add_argument("--industry", default=None, help="เฉพาะหุ้นไทย: กลุ่มอุตสาหกรรม")
    a = p.parse_args()

    kind = "thai" if a.thai else ("us-all" if a.us_all else "us")
    try:
        return build(kind, a.limit, a.market, a.industry)
    except KeyboardInterrupt:
        print("\n\n  ยกเลิกแล้ว (ไม่ได้บันทึกอะไร)\n")
        return 1
    except Exception as e:
        print(f"\n\n  [ไม่สำเร็จ] {type(e).__name__}: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
