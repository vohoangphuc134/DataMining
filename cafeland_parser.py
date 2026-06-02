import time
import random
from bs4 import BeautifulSoup
import re

from x import Listing, fetch, human_scroll, to_float, to_price, to_int

class CafelandParser:
    BASE = "https://nhadat.cafeland.vn"

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
        
        # Ở Cafeland, link bài đăng thường nằm trong các thẻ a có href chứa đuôi .html
        for a in soup.find_all("a", href=True):
            href = a['href']
            # Lọc các link bài đăng bất động sản (thường có dãy số ID và đuôi .html)
            if re.search(r'-\d+\.html$', href) and "dang-tin" not in href and "moi-gioi" not in href and "ho-tro" not in href:
                if href.startswith("http"):
                    full_url = href
                else:
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
        l.source = "cafeland.vn"
        
        # 1. Tiêu đề
        title_el = soup.select_one("h1")
        if title_el: l.property_type = title_el.get_text(strip=True)
        
        # Trích xuất từ class infor-data đặc trưng của Cafeland
        for item in soup.find_all('div', class_=lambda c: c and 'infor-data' in c):
            txt = item.get_text(strip=True).lower()
            if "tỷ" in txt or "triệu" in txt or "tỉ" in txt:
                l.price = to_price(txt)
            elif "m2" in txt or "m²" in txt:
                l.area = to_float(txt.replace("m2", "").replace("m²", "").replace(",", "."))
            elif "pn" in txt or "phòng" in txt:
                l.bedrooms = to_int(txt)
                
        # Fallback: Trích xuất các trường khác (Địa chỉ, Hướng, v.v) từ nội dung trang
        text_content = soup.get_text(" ", strip=True).lower()
        
        # Nếu vẫn chưa thấy Giá
        if not l.price:
            price_match = re.search(r'giá\s*:\s*([\d\,\.]+\s*(tỷ|triệu))', text_content)
            if price_match: l.price = to_price(price_match.group(1))
            
        # Nếu vẫn chưa thấy Diện tích
        if not l.area:
            area_match = re.search(r'diện tích\s*:\s*([\d\,\.]+)\s*m2', text_content)
            if area_match: l.area = to_float(area_match.group(1).replace(",", "."))
        
        # 3. Địa chỉ
        addr_match = re.search(r'địa chỉ\s*:\s*([^,]+,[^,]+,[^,]+)', text_content)
        if addr_match: 
            l.address_full = addr_match.group(1).strip()
            parts = [p.strip() for p in l.address_full.split(",")]
            if len(parts) >= 1: l.city = parts[-1]
            if len(parts) >= 2: l.district = parts[-2]
            if len(parts) >= 3: l.ward = parts[-3]
            
        if l.price and l.area and l.area > 0:
            l.price_per_m2 = round(l.price / l.area, 4)
            
        return l
