"""
run_hcm_hn.py — Quét toàn bộ căn hộ chung cư HCM + HN
URL pattern: base_url/pN?cIds=...

Chạy:
    python run_hcm_hn.py                          # cả HCM + HN
    python run_hcm_hn.py --only hcm               # chỉ HCM
    python run_hcm_hn.py --only hn                # chỉ HN
    python run_hcm_hn.py --only hn --start-page-hn 150   # resume từ trang 150
"""

import time, random, logging, argparse
from pathlib import Path
from datetime import datetime
import pandas as pd

# Import từ x.py (tất cả đã có trong file đó)
from x import (
    BDSParser, make_driver, save_to_csv,
    Listing, safe_get, FIELDS, is_cf_challenge,
)
from dataclasses import asdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("run_hcm_hn.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ─── Cấu hình 2 thành phố ──────────────────────────────────────────────────────
TARGETS = [
    {
        "name":        "can_ho_hcm",
        "base_url":    "https://batdongsan.com.vn/ban-can-ho-chung-cu-tp-ho-chi-minh",
        "query":       "?cIds=650,362,41,325,163,575,361,40,283,44,562,45,48",
        "total_pages": 8000,
        "output":      "output/can_ho_hcm.csv",
    },
    {
        "name":        "can_ho_hn",
        "base_url":    "https://batdongsan.com.vn/ban-can-ho-chung-cu-tp-ha-noi",
        "query":       "?cIds=650,362,41,325,163,575,361,40,283,44,562,45,48",
        "total_pages": 1024,
        "output":      "output/can_ho_hn.csv",
    },
]

DELAY_MIN  = 1.25
DELAY_MAX  = 2.5
SAVE_EVERY = 3   # lưu CSV sau mỗi N trang


def make_page_url(base_url: str, query: str, page: int) -> str:
    """
    Trang 1 : base_url + query
              vd: .../ban-can-ho-chung-cu-tp-ha-noi?cIds=...
    Trang N  : base_url + /pN + query
              vd: .../ban-can-ho-chung-cu-tp-ha-noi/p2?cIds=...
    """
    if page == 1:
        return base_url + query
    return f"{base_url}/p{page}{query}"


def load_existing(out_csv: str):
    """Đọc CSV đã crawl để resume, trả về (seen_urls, all_listings)."""
    seen_urls    = set()
    all_listings = []
    if not Path(out_csv).exists():
        return seen_urls, all_listings

    df = pd.read_csv(out_csv, encoding="utf-8-sig")
    seen_urls = set(df["url"].dropna().tolist())

    for _, row in df.iterrows():
        d = {}
        for k in FIELDS + ["source"]:
            if k in row:
                v = row[k]
                d[k] = None if (isinstance(v, float) and pd.isna(v)) else v
        try:
            all_listings.append(Listing(**{k: v for k, v in d.items()
                                           if k in Listing.__dataclass_fields__}))
        except Exception:
            pass

    log.info(f"  Resume: {len(seen_urls):,} URLs đã crawl trước")
    return seen_urls, all_listings


def crawl_target(target: dict, parser: BDSParser, start_page: int = 1) -> list:
    out_csv     = target["output"]
    base_url    = target["base_url"]
    query       = target["query"]
    total_pages = target["total_pages"]

    seen_urls, all_listings = load_existing(out_csv)
    log.info(f"Crawling [{target['name']}]: trang {start_page} → {total_pages}")

    for page_num in range(start_page, total_pages + 1):
        page_url = make_page_url(base_url, query, page_num)
        log.info(f"  [Page {page_num}/{total_pages}] {page_url}")

        urls = parser.get_listing_urls(page_url)
        if not urls:
            log.warning(f"  Không có URL trang {page_num} — bỏ qua")
            continue

        new_urls = [u for u in urls if u not in seen_urls]
        seen_urls.update(new_urls)
        log.info(f"  {len(new_urls)} new / {len(urls)} total")

        for i, url in enumerate(new_urls):
            log.info(f"    [{i+1}/{len(new_urls)}] {url}")
            listing = parser.parse_detail(url)
            if listing:
                listing.source = target["name"]
                all_listings.append(listing)
                log.info(
                    f"    ✓ id={listing.post_id} | "
                    f"{listing.price} | {listing.area}m² | "
                    f"{listing.district}, {listing.city}"
                )
            else:
                log.warning(f"    ✗ failed: {url}")
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        # Auto-save mỗi SAVE_EVERY trang
        if page_num % SAVE_EVERY == 0 and all_listings:
            save_to_csv(all_listings, out_csv)

    save_to_csv(all_listings, out_csv)
    log.info(f"✅ {target['name']}: {len(all_listings):,} listings → {out_csv}")
    return all_listings


def merge_outputs(targets_run: list) -> str:
    dfs = []
    for t in targets_run:
        p = t["output"]
        if Path(p).exists():
            df = pd.read_csv(p, encoding="utf-8-sig")
            dfs.append(df)

    if not dfs:
        return ""

    merged = pd.concat(dfs, ignore_index=True)
    before = len(merged)
    merged = merged.drop_duplicates(subset=["post_id"])
    log.info(f"Dedup: {before:,} → {len(merged):,}")

    # Tính price_per_m2 nếu còn thiếu
    mask = merged["price_per_m2"].isna() & merged["price"].notna() & merged["area"].notna()
    merged.loc[mask, "price_per_m2"] = (
        merged.loc[mask, "price"] / merged.loc[mask, "area"]
    ).round(4)

    ts  = datetime.now().strftime("%Y%m%d_%H%M")
    out = f"output/can_ho_all_{ts}.csv"
    merged.to_csv(out, index=False, encoding="utf-8-sig")
    return out


# ─── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only",           choices=["hcm", "hn"], default=None,
                    help="Chỉ chạy 1 thành phố")
    ap.add_argument("--start-page-hcm", type=int, default=1,
                    help="Trang bắt đầu cho HCM (dùng khi resume)")
    ap.add_argument("--start-page-hn",  type=int, default=1,
                    help="Trang bắt đầu cho HN (dùng khi resume)")
    args = ap.parse_args()

    Path("output").mkdir(exist_ok=True)

    # Xác định target cần chạy
    if args.only == "hcm":
        targets_to_run = [(TARGETS[0], args.start_page_hcm)]
    elif args.only == "hn":
        targets_to_run = [(TARGETS[1], args.start_page_hn)]
    else:
        targets_to_run = [
            (TARGETS[0], args.start_page_hcm),
            (TARGETS[1], args.start_page_hn),
        ]

    # Khởi động driver (1 driver dùng chung cho toàn bộ session)
    driver = make_driver()
    parser = BDSParser(driver)

    try:
        # Warm-up — để Cloudflare set cookie
        log.info("Warm-up: visiting homepage...")
        safe_get(driver, "https://batdongsan.com.vn")
        time.sleep(random.uniform(4, 7))

        for idx, (target, start_page) in enumerate(targets_to_run):
            crawl_target(target, parser, start_page=start_page)

            if idx < len(targets_to_run) - 1:
                wait = random.uniform(20, 40)
                log.info(f"Nghỉ {wait:.0f}s trước thành phố tiếp theo...")
                time.sleep(wait)

    except KeyboardInterrupt:
        log.info("Người dùng dừng — dữ liệu đã auto-save.")

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    # Merge nếu chạy cả 2
    out_targets = [t for t, _ in targets_to_run]
    if len(out_targets) > 1:
        out = merge_outputs(out_targets)
        if out:
            total = len(pd.read_csv(out))
            print(f"\n✅ Merged {total:,} dòng → {out}")
    else:
        t = out_targets[0]
        n = len(pd.read_csv(t["output"])) if Path(t["output"]).exists() else 0
        print(f"\n✅ {n:,} dòng → {t['output']}")