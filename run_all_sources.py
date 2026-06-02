import time
import random
import logging
import csv
import os
from pathlib import Path

# Import các parser
from x import BDSParser, make_driver, Listing, FIELDS
from alonhadat_parser import AloNhaDatParser
from cafeland_parser import CafelandParser
from mogi_parser import MogiParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Cấu hình danh sách các web muốn cào (HCM, 170 trang/web)
TARGETS = [
    {
        "source_name": "mogi.vn",
        "url": "https://mogi.vn/ho-chi-minh/mua-can-ho-chung-cu",
        "parser_class": MogiParser,
        "max_pages": 2026
    },
    {
        "source_name": "cafeland.vn",
        "url": "https://nhadat.cafeland.vn/nha-dat-ban/ban-can-ho-chung-cu-tai-tp-ho-chi-minh/",
        "parser_class": CafelandParser,
        "max_pages": 2026
    },
    {
        "source_name": "batdongsan.com.vn",
        "url": "https://batdongsan.com.vn/ban-can-ho-chung-cu-tp-hcm",
        "parser_class": BDSParser,
        "max_pages": 2026
    }
]

def make_page_url(base_url, source_name, page_num):
    """Mỗi web có quy luật chia trang khác nhau"""
    if page_num == 1:
        return base_url
        
    if source_name == "batdongsan.com.vn":
        return f"{base_url}/p{page_num}"
    elif source_name == "alonhadat.com.vn":
        return base_url.replace(".html", f"/trang--{page_num}.html")
    elif source_name == "cafeland.vn":
        return f"{base_url}page-{page_num}/"
    elif source_name == "mogi.vn":
        return f"{base_url}?cp={page_num}"
    return base_url

from dataclasses import asdict

def append_to_csv(listing, file_path):
    """Ghi trực tiếp 1 dòng dữ liệu vào file CSV"""
    file_exists = os.path.isfile(file_path)
    
    # Lấy toàn bộ danh sách các cột từ cấu trúc Listing
    all_fields = FIELDS + ["source"]
    
    with open(file_path, mode='a', encoding='utf-8', newline='') as f:
        # Nếu file chưa tồn tại thì ghi BOM và Header
        if not file_exists:
            f.write('\ufeff') # Thêm ký tự BOM để Excel đọc được tiếng Việt
            writer = csv.DictWriter(f, fieldnames=all_fields)
            writer.writeheader()
        else:
            writer = csv.DictWriter(f, fieldnames=all_fields)
            
        # Tự động chuyển Object thành Dictionary, không bị thiếu trường
        try:
            row = asdict(listing)
        except TypeError:
            row = vars(listing)
            
        # Lọc ra các cột hợp lệ
        valid_row = {k: v for k, v in row.items() if k in all_fields}
        writer.writerow(valid_row)

def load_processed_urls(file_path):
    """Đọc file CSV để lấy danh sách các URL đã cào thành công"""
    processed = set()
    if os.path.isfile(file_path):
        try:
            with open(file_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'url' in row and row['url']:
                        processed.add(row['url'])
        except Exception as e:
            log.error(f"Lỗi khi đọc file CSV cũ: {e}")
    return processed

def main():
    Path("output").mkdir(exist_ok=True)
    out_csv = "output/data_BDS_TPHCM1.csv"
    
    # Lấy danh sách các URL đã cào từ trước để tránh trùng lặp
    processed_urls = load_processed_urls(out_csv)
    if processed_urls:
        log.info(f"==== TÌM THẤY {len(processed_urls)} BÀI ĐÃ CÀO TRONG LẦN CHẠY TRƯỚC ====")

    # Khởi động 1 trình duyệt duy nhất dùng chung
    driver = make_driver()
    total_scraped = len(processed_urls)
    
    try:
        for target in TARGETS:
            log.info(f"==== ĐANG BẮT ĐẦU CÀO TRANG: {target['source_name']} ====")
            ParserClass = target["parser_class"]
            parser = ParserClass(driver)
            
            for page in range(1, target["max_pages"] + 1):
                page_url = make_page_url(target["url"], target["source_name"], page)
                log.info(f"  -> Truy cập: {page_url}")
                
                urls = parser.get_listing_urls(page_url)
                log.info(f"  Tìm thấy {len(urls)} bài đăng trên trang {page}.")
                
                for i, url in enumerate(urls):
                    if url in processed_urls:
                        log.info(f"    [BỎ QUA] Đã tồn tại trong CSV: {url}")
                        continue
                        
                    log.info(f"    Đang bóc tách [{i+1}/{len(urls)}] (Tổng đã lưu: {total_scraped}): {url}")
                    try:
                        listing = parser.parse_detail(url)
                        if listing:
                            # [QUAN TRỌNG] Lưu thẳng vào ổ cứng ngay lập tức!
                            append_to_csv(listing, out_csv)
                            processed_urls.add(url)
                            total_scraped += 1
                            log.info(f"    [OK] Giá: {listing.price} | DT: {listing.area} | Nguồn: {listing.source}")
                    except Exception as e:
                        log.error(f"    [LỖI] {e}")
                        
                    # Nghỉ ngẫu nhiên từ 1.5s - 3s để tránh bị block IP
                    time.sleep(random.uniform(1.5, 3.0)) 
                    
    finally:
        driver.quit()
        
    log.info(f"==== HOÀN THÀNH! LƯU TỔNG CỘNG {total_scraped} BÀI RA FILE {out_csv} ====")

if __name__ == "__main__":
    main()
