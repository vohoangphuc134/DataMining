import re
import time
import random
from bs4 import BeautifulSoup

from x import Listing, fetch, human_scroll, to_float, to_price, to_int

class AloNhaDatParser:
    BASE = "https://alonhadat.com.vn"

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
        
        # Sửa: Lấy thẻ a class 'link' nằm trong article class 'property-item'
        for item in soup.select("article.property-item a.link"):
            href = item.get("href")
            if href:
                full_url = self.BASE + "/" + href.lstrip("/")
                if full_url not in urls:
                    urls.append(full_url)
                
        return urls

    def parse_detail(self, url: str) -> Listing:
        html = fetch(self.driver, url, wait=True)
        if not html: return None
            
        soup = BeautifulSoup(html, "lxml")
        
        l = Listing()
        l.url = url
        l.source = "alonhadat"
        
        title_el = soup.select_one("h1")
        if title_el: l.property_type = title_el.get_text(strip=True)
        
        price_el = soup.select_one("span.price")
        if price_el: l.price = to_price(price_el.get_text(strip=True))
        
        area_el = soup.select_one("span.area")
        if area_el: 
            area_str = area_el.get_text(strip=True).lower().replace("diện tích:", "").replace("m2", "").replace("m²", "").replace(",", ".").strip()
            l.area = to_float(area_str)
        
        addr_el = soup.select_one(".current-address")
        if addr_el: 
            l.address_full = addr_el.get_text(strip=True)
            parts = [p.strip() for p in l.address_full.split(",")]
            if len(parts) >= 1: l.city = parts[-1]
            if len(parts) >= 2: l.district = parts[-2]
            if len(parts) >= 3: l.ward = parts[-3]
            
        for tr in soup.select("table tr"):
            tds = tr.select("td")
            if len(tds) >= 2:
                lbl1 = tds[0].get_text(strip=True).lower()
                val1 = tds[1].get_text(strip=True)
                if "phòng ngủ" in lbl1: l.bedrooms = to_int(val1)
                if "tầng" in lbl1: l.floors = to_int(val1)
                if "hướng" in lbl1 and "ban công" not in lbl1: l.house_direction = val1
                if "pháp lý" in lbl1: l.legal_status = val1
                
                if len(tds) >= 4:
                    lbl2 = tds[2].get_text(strip=True).lower()
                    val2 = tds[3].get_text(strip=True)
                    if "phòng ngủ" in lbl2: l.bedrooms = to_int(val2)
                    if "tầng" in lbl2: l.floors = to_int(val2)
                    if "hướng" in lbl2 and "ban công" not in lbl2: l.house_direction = val2
                    if "pháp lý" in lbl2: l.legal_status = val2
        
        if l.price and l.area and l.area > 0:
            l.price_per_m2 = round(l.price / l.area, 4)
            
        return l
