import time
import random
from bs4 import BeautifulSoup

from x import Listing, fetch, human_scroll, to_float, to_price, to_int

class DothiParser:
    BASE = "https://dothi.net"

    def __init__(self, driver):
        self.driver = driver

    def get_listing_urls(self, page_url: str) -> list:
        html = fetch(self.driver, page_url, wait=False)
        if not html: return []
            
        human_scroll(self.driver)
        time.sleep(random.uniform(1.5, 2.5))
        html = self.driver.page_source
        
        soup = BeautifulSoup(html, "lxml")
        urls = []
        
        # Link dothi.net thường nằm trong div.list-box, the a
        for item in soup.select("ul.list-box li div.info h3 a"):
            href = item.get("href")
            if href:
                full_url = self.BASE + "/" + href.lstrip("/")
                urls.append(full_url)
                
        return urls

    def parse_detail(self, url: str) -> Listing:
        html = fetch(self.driver, url, wait=True)
        if not html: return None
            
        soup = BeautifulSoup(html, "lxml")
        
        l = Listing()
        l.url = url
        l.source = "dothi.net"
        
        # 1. Tiêu đề
        title_el = soup.select_one("h1")
        if title_el: l.property_type = title_el.get_text(strip=True)
        
        # 2. Giá và Diện tích (thường nằm cùng trong 1 khu vực)
        spans = soup.select("div.price-area span")
        for span in spans:
            txt = span.get_text(strip=True).lower()
            if "tỷ" in txt or "triệu" in txt:
                l.price = to_price(txt)
            if "m2" in txt:
                l.area = to_float(txt.replace("m2", ""))
        
        # 3. Địa chỉ
        addr_el = soup.select_one("div.location")
        if addr_el: 
            l.address_full = addr_el.get_text(strip=True).replace("Địa chỉ:", "").strip()
            parts = [p.strip() for p in l.address_full.split(",")]
            if len(parts) >= 1: l.city = parts[-1]
            if len(parts) >= 2: l.district = parts[-2]
            
        # 4. Các thông số khác nằm trong bảng ul li
        for li in soup.select("ul.pd-tien-ich li"):
            lbl = li.select_one("span.lbl")
            val = li.select_one("span.val")
            if lbl and val:
                lbl_txt = lbl.get_text(strip=True).lower()
                val_txt = val.get_text(strip=True)
                if "phòng ngủ" in lbl_txt: l.bedrooms = to_int(val_txt)
                if "số tầng" in lbl_txt: l.floors = to_int(val_txt)
                if "pháp lý" in lbl_txt: l.legal_status = val_txt
                if "hướng" in lbl_txt and "ban công" not in lbl_txt: l.house_direction = val_txt
                
        if l.price and l.area and l.area > 0:
            l.price_per_m2 = round(l.price / l.area, 4)
            
        return l
