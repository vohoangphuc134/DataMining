import re
import time
import random
from bs4 import BeautifulSoup

from x import Listing, fetch, human_scroll, to_float, to_price, to_int

class MogiParser:
    BASE = "https://mogi.vn"

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
        
        for item in soup.select("a.link-overlay"):
            href = item.get("href")
            if href and "/news/" not in href and "id" in href:
                full_url = href if href.startswith("http") else self.BASE + "/" + href.lstrip("/")
                if full_url not in urls:
                    urls.append(full_url)
                
        return urls

    def parse_detail(self, url: str) -> Listing:
        html = fetch(self.driver, url, wait=True)
        if not html: return None
            
        soup = BeautifulSoup(html, "lxml")
        
        l = Listing()
        l.url = url
        l.source = "mogi.vn"
        
        title_el = soup.select_one("title")
        if title_el: l.property_type = title_el.get_text(strip=True)
        
        # Giá
        price_el = soup.select_one(".price")
        if price_el: 
            l.price = to_price(price_el.get_text(strip=True))
            
        # Địa chỉ
        addr_el = soup.select_one(".address")
        if addr_el:
            l.address_full = addr_el.get_text(strip=True)
            parts = [p.strip() for p in l.address_full.split(",")]
            if len(parts) >= 1: l.city = parts[-1]
            if len(parts) >= 2: l.district = parts[-2]
            if len(parts) >= 3: l.ward = parts[-3]
            
        # Dùng vòng lặp quét qua các thông số chuẩn của Mogi (Thẻ div.info-attr)
        for attr in soup.select("div.info-attr"):
            txt = attr.get_text(" ", strip=True).lower()
            if "diện tích" in txt:
                area_match = re.search(r'([\d\,\.]+)\s*m\s*2', txt)
                if area_match: l.area = to_float(area_match.group(1).replace(",", "."))
            elif "phòng ngủ" in txt:
                pn_match = re.search(r'phòng ngủ\s*(\d+)', txt)
                if pn_match: l.bedrooms = to_int(pn_match.group(1))
            elif "nhà tắm" in txt or "phòng tắm" in txt or "toilet" in txt:
                wc_match = re.search(r'(?:nhà tắm|phòng tắm|toilet)\s*(\d+)', txt)
                if wc_match: l.bathrooms = to_int(wc_match.group(1))
            elif "pháp lý" in txt:
                l.legal_status = attr.get_text(" ", strip=True).split("Pháp lý")[-1].strip()

        if l.price and l.area and l.area > 0:
            l.price_per_m2 = round(l.price / l.area, 4)
            
        return l
