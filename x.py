"""
=================================================================
  BatDongSan.com.vn - Automated Property Data Crawler
  Thu thap tu dong toan bo thong tin BDS cho phan tich du lieu
=================================================================
Cai dat: pip install undetected-chromedriver beautifulsoup4 lxml pandas
Chay   : python bds_crawler.py
"""

import sys, time, json, csv, random, re, os
from datetime import datetime
from urllib.parse import urljoin, urlparse
import pandas as pd
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

sys.stdout.reconfigure(encoding='utf-8')

# =================================================================
#  CAU HINH - chinh sua o day
# =================================================================
CONFIG = {
    # Cac loai BDS can crawl: them/bot tuy y
    "categories": [
        {"url": "https://batdongsan.com.vn/ban-nha-rieng-tp-ha-noi",            "type": "Nha rieng - Ha Noi"},
        {"url": "https://batdongsan.com.vn/ban-nha-rieng-tp-ho-chi-minh",       "type": "Nha rieng - HCM"},
        {"url": "https://batdongsan.com.vn/ban-can-ho-chung-cu-tp-ha-noi",      "type": "Chung cu - Ha Noi"},
        {"url": "https://batdongsan.com.vn/ban-can-ho-chung-cu-tp-ho-chi-minh", "type": "Chung cu - HCM"},
        {"url": "https://batdongsan.com.vn/ban-dat-nen-du-an-tp-ha-noi",        "type": "Dat nen - Ha Noi"},
        {"url": "https://batdongsan.com.vn/ban-dat-nen-du-an-tp-ho-chi-minh",   "type": "Dat nen - HCM"},
        {"url": "https://batdongsan.com.vn/ban-nha-biet-thu-lien-ke-tp-ha-noi", "type": "Biet thu - Ha Noi"},
        {"url": "https://batdongsan.com.vn/ban-nha-biet-thu-lien-ke-tp-ho-chi-minh", "type": "Biet thu - HCM"},
    ],
    "max_pages_per_category": 5,    # So trang phan trang moi category
    "max_total_posts":        100,   # Tong so bai toi da
    "delay_min":              2.5,   # Thoi gian cho giua request (giay)
    "delay_max":              4.5,
    "autosave_every":         25,    # Tu dong luu moi N bai
    "output_csv":             "bds_dataset.csv",
    "output_json":            "bds_dataset.json",
    "progress_file":          "bds_progress.json",  # Resume neu bi ngat
}

FIELDS = [
    "post_id","url","post_date","post_type","is_urgent","seller_type",
    "property_type","project_name",
    "price","price_per_m2","area","area_used",
    "floors","bedrooms","bathrooms","frontage","acces_road",
    "house_direction","balcony_direction","floors_apartment","year_built",
    "address_full","street","ward","district","city",
    "legal_status","furniture_state",
    "has_garage","has_pool","has_elevator","has_security","has_parking",
    "management_fee","has_swimming_pool","has_gym","has_supermarket","building_density",
    "crawled_at",
]


# =================================================================
#  CHROME DRIVER
# =================================================================
def get_chrome_version():
    import subprocess
    for cmd in [
        r'reg query "HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon" /v version',
        r'reg query "HKLM\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome" /v DisplayVersion',
    ]:
        try:
            out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
            m = re.search(r"(\d+)\.", out)
            if m:
                return int(m.group(1))
        except:
            pass
    return None

def build_driver():
    ver = get_chrome_version()
    print(f"[DRIVER] Chrome version: {ver or 'auto'}")
    opts = uc.ChromeOptions()
    opts.add_argument("--window-size=1440,900")
    opts.add_argument("--lang=vi-VN,vi")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    return uc.Chrome(options=opts, headless=False,
                     use_subprocess=True, version_main=ver)


# =================================================================
#  TIEN ICH FETCH
# =================================================================
def wait_cf(driver, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = driver.title.lower()
        s = driver.page_source[:3000].lower()
        if "just a moment" not in t and "checking your browser" not in s:
            return True
        time.sleep(1.5)
    return False

def human_scroll(driver):
    try:
        h = driver.execute_script("return document.body.scrollHeight")
        for _ in range(random.randint(2, 4)):
            y = random.randint(300, max(400, h // 2))
            driver.execute_script(f"window.scrollTo({{top:{y},behavior:'smooth'}});")
            time.sleep(random.uniform(0.3, 0.7))
        driver.execute_script("window.scrollTo(0,0);")
    except:
        pass

def fetch(driver, url, wait=True):
    try:
        driver.get(url)
        if not wait_cf(driver, 30):
            return None
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body")))
        if wait:
            human_scroll(driver)
            time.sleep(random.uniform(CONFIG["delay_min"], CONFIG["delay_max"]))
        return driver.page_source
    except Exception as e:
        print(f"  [ERR] {e}")
        return None


# =================================================================
#  PARSE TRANG DANH SACH
# =================================================================
def get_post_urls(html, base):
    soup = BeautifulSoup(html, "lxml")
    urls = set()

    # Dung selector chinh xac: card bai dang
    for card in soup.select("div.re__card-full, div[class*='card-full']"):
        a = card.find("a", href=True)
        if a:
            full = urljoin(base, a["href"]).split("?")[0].split("#")[0]
            if re.search(r"pr\d{5,}$", full):
                urls.add(full)

    # Fallback: quet tat ca link ket thuc bang prXXXXXX
    if not urls:
        for a in soup.find_all("a", href=True):
            full = urljoin(base, a["href"]).split("?")[0].split("#")[0]
            if re.search(r"pr\d{5,}$", full):
                urls.add(full)

    return urls

def get_next_page(current_url, page_num):
    """Tao URL trang ke tiep."""
    base = re.sub(r"/p\d+$", "", current_url.rstrip("/"))
    return f"{base}/p{page_num}"


# =================================================================
#  PARSE TRANG CHI TIET - TRICH XUAT TRUONG
# =================================================================
def to_float(text):
    if not text: return None
    t = re.sub(r"[^\d.,]", "", text.replace(",", "."))
    try: return float(t)
    except: return None

def to_int(text):
    v = to_float(text)
    return int(v) if v is not None else None

def to_price(text):
    """chuyen moi dinh dang gia -> trieu VND."""
    if not text:
        return None

    t = text.lower().replace("\u00a0", " ").replace(",", ".")

    try:
        m = re.search(r"([\d.]+)\s*t[ỷy]", t)   # ví dụ: 6.9 tỷ
        if m:
            val = m.group(1)
            if val != ".":
                return round(float(val) * 1000, 1)

        m = re.search(r"([\d.]+)\s*triệu", t)   # ví dụ: 500 triệu
        if m:
            val = m.group(1)
            if val != ".":
                return round(float(val), 1)

        m = re.search(r"([\d.]+)", t)
        if m:
            val = m.group(1)
            if val != ".":
                return float(val)

    except:
        return None

    return None

def to_bool(text):
    if not text: return None
    t = text.lower()
    if any(x in t for x in ["có", "co ", "yes", "✓", "x"]): return True
    if any(x in t for x in ["không", "khong", "no"]): return False
    return None

# Map label (lowercase) -> (field_name, converter)
LABEL_MAP = {
    "diện tích":                ("area",              to_float),
    "dt sử dụng":               ("area_used",         to_float),
    "diện tích sàn":            ("area_used",         to_float),
    "mức giá":                  ("price",             to_price),
    "giá/m²":                   ("price_per_m2",      to_price),
    "giá trên m²":              ("price_per_m2",      to_price),
    "số tầng":                  ("floors",            to_int),
    "tầng số":                  ("floors_apartment",  to_int),
    "tầng":                     ("floors_apartment",  to_int),
    "số phòng ngủ":             ("bedrooms",          to_int),
    "phòng ngủ":                ("bedrooms",          to_int),
    "số toilet":                ("bathrooms",         to_int),
    "toilet":                   ("bathrooms",         to_int),
    "phòng tắm":                ("bathrooms",         to_int),
    "mặt tiền":                 ("frontage",          to_float),
    "đường vào":                ("acces_road",        to_float),
    "hướng nhà":                ("house_direction",   str.strip),
    "hướng cửa chính":          ("house_direction",   str.strip),
    "hướng ban công":           ("balcony_direction", str.strip),
    "năm xây dựng":             ("year_built",        to_int),
    "pháp lý":                  ("legal_status",      str.strip),
    "nội thất":                 ("furniture_state",   str.strip),
    "tình trạng nội thất":      ("furniture_state",   str.strip),
    "gara":                     ("has_garage",        to_bool),
    "chỗ để xe hơi":            ("has_garage",        to_bool),
    "hồ bơi":                   ("has_pool",          to_bool),
    "hồ bơi riêng":             ("has_pool",          to_bool),
    "thang máy":                ("has_elevator",      to_bool),
    "bảo vệ":                   ("has_security",      to_bool),
    "an ninh":                  ("has_security",      to_bool),
    "chỗ để xe":                ("has_parking",       to_bool),
    "bãi đậu xe":               ("has_parking",       to_bool),
    "phí quản lý":              ("management_fee",    to_float),
    "hồ bơi chung cư":          ("has_swimming_pool", to_bool),
    "hồ bơi (chung cư)":        ("has_swimming_pool", to_bool),
    "gym / fitness":            ("has_gym",           to_bool),
    "gym":                      ("has_gym",           to_bool),
    "siêu thị":                 ("has_supermarket",   to_bool),
    "trung tâm thương mại":     ("has_supermarket",   to_bool),
    "mật độ xây dựng":          ("building_density",  to_float),
    "tên dự án":                ("project_name",      str.strip),
}

def parse_detail(html, url):
    rec = {f: None for f in FIELDS}
    rec["url"]        = url
    rec["crawled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rec["is_urgent"]  = False

    soup = BeautifulSoup(html, "lxml")

    # === POST ID tu URL ===
    m = re.search(r"pr(\d+)$", url)
    if m:
        rec["post_id"] = m.group(1)

    # === TIEU DE / LOAI BDS ===
    h1 = soup.select_one("h1")
    if h1:
        rec["property_type"] = h1.get_text(strip=True)

    # === SELLER NAME ===
    agent = soup.select_one("div.re__agent-infor.re__agent-name")
    if agent:
        rec["seller_type"] = agent.get_text(strip=True).split("Xem thêm")[0].strip()

    # === THONG TIN NGAN (gia, dien tich) - div.re__pr-short-info-item ===
    for item in soup.select("div.re__pr-short-info-item.js__pr-short-info-item"):
        txt = item.get_text(" ", strip=True)
        # "Khoảng giá Thỏa thuận" hoac "Khoảng giá 5,2 tỷ"
        if "giá" in txt.lower() or "tỷ" in txt.lower() or "triệu" in txt.lower():
            # lay phan sau label
            parts = txt.split(None, 2)
            if len(parts) >= 3:
                val = " ".join(parts[2:])
                rec["price"] = to_price(val)
        elif "diện tích" in txt.lower() or "m²" in txt:
            m2 = re.search(r"([\d,.]+)\s*m²", txt)
            if m2:
                rec["area"] = to_float(m2.group(1))

    # === CONFIG ITEMS (ngay dang, loai tin, ma tin) ===
    for item in soup.select("div.re__pr-short-info-item.js__pr-config-item"):
        txt = item.get_text(" ", strip=True)
        if "ngày đăng" in txt.lower():
            m = re.search(r"(\d{2}/\d{2}/\d{4})", txt)
            if m: rec["post_date"] = m.group(1)
        elif "loại tin" in txt.lower():
            rec["post_type"] = txt.replace("Loại tin", "").strip()
            rec["is_urgent"] = bool(re.search(r"gấp|hot|urgent", txt.lower()))
        elif "mã tin" in txt.lower():
            m = re.search(r"(\d{5,})", txt)
            if m and not rec["post_id"]:
                rec["post_id"] = m.group(1)

    # === SPECS CHI TIET - div.re__pr-specs-content-item ===
    for item in soup.select("div.re__pr-specs-content-item"):
        title_el = item.select_one(".re__pr-specs-content-item-title")
        value_el = item.select_one(".re__pr-specs-content-item-value")

        if not title_el or not value_el:
            # Fallback: 2 div con dau tien
            children = [c for c in item.children
                        if hasattr(c, "get_text") and c.get_text(strip=True)]
            if len(children) >= 2:
                title_el, value_el = children[0], children[1]
            else:
                continue

        label = title_el.get_text(strip=True).lower().rstrip(":")
        value = value_el.get_text(strip=True)

        for key, (field, fn) in LABEL_MAP.items():
            if key in label:
                try:
                    v = fn(value)
                    if v is not None:
                        rec[field] = v
                except:
                    rec[field] = value
                break

    # === DIA CHI tu breadcrumb ===
    crumbs = [a.get_text(strip=True)
              for a in soup.select("ul.re__breadcrumb a, .re__breadcrumb a")
              if a.get_text(strip=True)]
    if crumbs:
        # Bo "Trang chu" / "Mua ban"
        crumbs = [c for c in crumbs if c.lower() not in
                  ("trang chủ", "mua bán", "cho thuê", "batdongsan.com.vn")]
        if len(crumbs) >= 1: rec["city"]     = crumbs[-1] if len(crumbs) >= 1 else None
        if len(crumbs) >= 2: rec["district"] = crumbs[-2] if len(crumbs) >= 2 else None
        if len(crumbs) >= 3: rec["ward"]     = crumbs[-3] if len(crumbs) >= 3 else None

    # Address full tu tieu de hoac mo ta
    addr_el = soup.select_one(".re__pr-short-info-item .re__pr-address-value,"
                               "[class*='address-value']")
    if addr_el:
        rec["address_full"] = addr_el.get_text(strip=True)
    elif rec["ward"] and rec["district"] and rec["city"]:
        rec["address_full"] = f"{rec['ward']}, {rec['district']}, {rec['city']}"

    # === FALLBACK: quet full text neu con null ===
    if rec["price"] is None or rec["area"] is None or rec["bedrooms"] is None:
        full = soup.get_text(" ", strip=True)

        if rec["price"] is None:
            m = re.search(r"([\d.,]+)\s*t[ỷỉy]", full)
            if m: rec["price"] = to_price(m.group(0))

        if rec["area"] is None:
            m = re.search(r"([\d.,]+)\s*m[²2]", full)
            if m: rec["area"] = to_float(m.group(1))

        if rec["bedrooms"] is None:
            m = re.search(r"(\d+)\s*phòng ngủ", full, re.I)
            if m: rec["bedrooms"] = int(m.group(1))

    # === TIEN ICH - trich tu description text ===
    desc_el = soup.select_one(
        ".re__section-body.re__detail-content, "
        "[class*='detail-content'], "
        ".re__pr-description"
    )
    desc = desc_el.get_text(" ", strip=True).lower() if desc_el else ""
    full_lower = soup.get_text(" ", strip=True).lower()

    def has_keyword(text, *kws):
        return any(k in text for k in kws)

    rec["has_garage"]    = has_keyword(desc, "hầm để xe", "garage", "gara", "ô tô vào nhà", "ô tô đỗ cửa")
    rec["has_pool"]      = has_keyword(desc, "hồ bơi", "bể bơi", "swimming pool")
    rec["has_elevator"]  = has_keyword(desc, "thang máy", "elevator", "thang may")
    rec["has_security"]  = has_keyword(desc, "bảo vệ 24", "an ninh 24", "security", "bảo vệ tòa nhà")
    rec["has_parking"]   = has_keyword(desc, "chỗ để xe", "bãi đỗ xe", "parking", "bãi xe", "để xe máy")

    # Cac tien ich chi co o chung cu - lay tu full page
    rec["has_swimming_pool"] = has_keyword(full_lower, "hồ bơi", "bể bơi") or rec["has_pool"]
    rec["has_gym"]           = has_keyword(full_lower, "gym", "phòng gym", "fitness", "phòng tập")
    rec["has_supermarket"]   = has_keyword(full_lower, "siêu thị", "trung tâm thương mại", "shophouse")

    # === PROJECT NAME - tu breadcrumb, URL, hoac title ===
    if rec["project_name"] is None:
        # Thu lay tu breadcrumb (thuong la ten du an)
        crumb_els = soup.select("ul.re__breadcrumb li, .re__breadcrumb li")
        for li in crumb_els:
            txt = li.get_text(strip=True)
            # Du an thuong co chu "dự án" hoac viet hoa
            if txt and 5 < len(txt) < 80 and txt not in [
                "Trang chủ", "Mua bán", "Cho thuê", "Hà Nội",
                "Hồ Chí Minh", "Đà Nẵng"
            ]:
                # Lay breadcrumb dau tien sau loai BDS
                a = li.find("a", href=True)
                if a and re.search(r"/du-an-|/project", a.get("href", "")):
                    rec["project_name"] = txt
                    break

        # Fallback: trich tu title/URL
        if rec["project_name"] is None:
            m = re.search(r"(?:dự án|chung cư|khu đô thị)\s+([A-Z][\w\s]+?)(?:\s*[,-]|$)",
                          rec.get("property_type","") or "", re.I)
            if m:
                rec["project_name"] = m.group(1).strip()

    # === MANAGEMENT FEE - trich tu description ===
    if rec["management_fee"] is None:
        m = re.search(r"(?:phí quản lý|phi quan ly)[:\s]*([\d.,]+)\s*(?:đồng|nghìn|triệu|k|tr)?",
                      desc, re.I)
        if m:
            rec["management_fee"] = to_float(m.group(1))

    # === BUILDING DENSITY - trich tu text ===
    if rec["building_density"] is None:
        m = re.search(r"mật độ[\s\w]*?([\d.,]+)\s*%", full_lower)
        if m:
            rec["building_density"] = to_float(m.group(1))

    return rec



# =================================================================
#  CRAWLER CHINH
# =================================================================
class BDSCrawler:
    def __init__(self):
        self.records    = []
        self.seen_urls  = set()
        self.post_queue = []

        # Load progress neu co (resume)
        if os.path.exists(CONFIG["progress_file"]):
            with open(CONFIG["progress_file"], encoding="utf-8") as f:
                prog = json.load(f)
                self.seen_urls  = set(prog.get("seen_urls", []))
                self.post_queue = prog.get("remaining_queue", [])
                print(f"[RESUME] Tim thay progress: {len(self.seen_urls)} bai da crawl, "
                      f"{len(self.post_queue)} bai con lai trong queue")

        print("[INIT] Khoi dong Chrome...")
        self.driver = build_driver()
        self._warm_up()

    def _warm_up(self):
        print("[WARM] Xin phep Cloudflare...")
        self.driver.get("https://batdongsan.com.vn/")
        ok = wait_cf(self.driver, 35)
        if ok:
            time.sleep(random.uniform(5, 8))
            human_scroll(self.driver)
            print("[WARM] OK - San sang!\n")
        else:
            print("[WARN] CF chua pass, thu tiep...\n")

    # -------------------------------------------------------
    def _discover_posts(self):
        """Quet tat ca category de lay URL bai dang."""
        if self.post_queue:
            print(f"[SKIP] Dung queue cu ({len(self.post_queue)} bai)\n")
            return

        print("=" * 60)
        print("  BUOC 1: KHAM PHA URL BAI DANG")
        print("=" * 60)

        all_urls = []
        for cat in CONFIG["categories"]:
            print(f"\n[CAT] {cat['type']}")
            cat_urls = set()

            for page in range(1, CONFIG["max_pages_per_category"] + 1):
                if len(all_urls) + len(cat_urls) >= CONFIG["max_total_posts"]:
                    break

                url = cat["url"] if page == 1 else get_next_page(cat["url"], page)
                print(f"  [PAGE {page}] {url}")

                html = fetch(self.driver, url, wait=False)
                time.sleep(random.uniform(2, 3.5))
                if not html:
                    break

                found = get_post_urls(html, url) - self.seen_urls
                new_on_page = found - cat_urls
                if not new_on_page:
                    print(f"  [STOP] Khong co bai moi, dung phan trang")
                    break

                cat_urls |= new_on_page
                print(f"         +{len(new_on_page)} bai (tong cat: {len(cat_urls)})")

            all_urls.extend(list(cat_urls))
            print(f"  [CAT DONE] {len(cat_urls)} bai")

        # Xao tron de lay da dang loai BDS
        random.shuffle(all_urls)
        self.post_queue = all_urls[:CONFIG["max_total_posts"]]
        print(f"\n[DISCOVER] Tong {len(self.post_queue)} bai dang can crawl\n")

    # -------------------------------------------------------
    def _crawl_posts(self):
        print("=" * 60)
        print("  BUOC 2: CRAWL TUNG BAI DANG")
        print("=" * 60)
        print()

        total = len(self.post_queue)
        done  = 0

        while self.post_queue:
            url = self.post_queue.pop(0)
            if url in self.seen_urls:
                continue

            done += 1
            pct  = done / total * 100
            eta  = (total - done) * ((CONFIG["delay_min"] + CONFIG["delay_max"]) / 2)
            print(f"[{done:4d}/{total}] ({pct:.0f}%)  ETA ~{eta/60:.0f} phut  {url}")

            html = fetch(self.driver, url)
            if not html:
                print("  [SKIP] Khong lay duoc HTML")
                continue

            rec = parse_detail(html, url)
            self.records.append(rec)
            self.seen_urls.add(url)

            # In nhanh truong quan trong
            info = []
            if rec["price"]:        info.append(f"Gia: {rec['price']}tr")
            if rec["area"]:         info.append(f"DT: {rec['area']}m2")
            if rec["bedrooms"]:     info.append(f"PN: {rec['bedrooms']}")
            if rec["district"]:     info.append(f"Q: {rec['district']}")
            print(f"         [{' | '.join(info) if info else 'OK - kiem tra CSV'}]")

            # Auto-save va luu progress
            if done % CONFIG["autosave_every"] == 0:
                self._save()
                self._save_progress()
                print(f"  [AUTO-SAVE] {len(self.records)} bai da luu")

        self._save()
        self._cleanup_progress()

    # -------------------------------------------------------
    def _save(self):
        if not self.records:
            return
        with open(CONFIG["output_json"], "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

        df = pd.DataFrame(self.records, columns=FIELDS)
        df.to_csv(CONFIG["output_csv"], index=False, encoding="utf-8-sig")

    def _save_progress(self):
        prog = {
            "seen_urls":       list(self.seen_urls),
            "remaining_queue": self.post_queue,
            "saved_at":        datetime.now().isoformat(),
        }
        with open(CONFIG["progress_file"], "w", encoding="utf-8") as f:
            json.dump(prog, f, ensure_ascii=False)

    def _cleanup_progress(self):
        if os.path.exists(CONFIG["progress_file"]):
            os.remove(CONFIG["progress_file"])

    # -------------------------------------------------------
    def run(self):
        try:
            self._discover_posts()
            self._crawl_posts()
        except KeyboardInterrupt:
            print("\n[STOP] Nguoi dung dung. Dang luu...")
            self._save()
            self._save_progress()
            print("[SAVE] Da luu progress. Chay lai de tiep tuc.")
        finally:
            try:
                self.driver.quit()
            except:
                pass

        print(f"\n{'='*60}")
        print(f"  HOAN THANH: {len(self.records)} bai dang")
        print(f"  CSV  -> {CONFIG['output_csv']}")
        print(f"  JSON -> {CONFIG['output_json']}")
        print(f"{'='*60}")

        if self.records:
            df = pd.DataFrame(self.records)
            print(f"\n  Truong co du lieu:")
            for col in FIELDS:
                if col in df:
                    nn = df[col].notna().sum()
                    if nn > 0:
                        print(f"    {col:<25} {nn:4d}/{len(df)} ({nn/len(df)*100:.0f}%)")


# =================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  BatDongSan Crawler - BDS Data Collection Tool")
    print(f"  Muc tieu: {CONFIG['max_total_posts']} bai dang")
    print(f"  Output : {CONFIG['output_csv']}")
    print("=" * 60 + "\n")

    crawler = BDSCrawler()
    crawler.run()


def run(start_url, max_pages=5, max_listings=100, output_csv="output.csv", headless=False, delay_min=2.5, delay_max=4.5):
    global CONFIG
    original_config = CONFIG.copy()
    CONFIG["categories"] = [{"url": start_url, "type": "Custom"}]
    CONFIG["max_pages_per_category"] = max_pages
    CONFIG["max_total_posts"] = max_listings
    CONFIG["output_csv"] = output_csv
    CONFIG["delay_min"] = delay_min
    CONFIG["delay_max"] = delay_max
    # Note: headless not implemented in class yet
    crawler = BDSCrawler()
    crawler.run()
    records = crawler.records
    CONFIG.update(original_config)
    return records


def save_to_csv(records, output_csv):
    if not records:
        return
    df = pd.DataFrame(records, columns=FIELDS)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

# =================================================================
#  ADAPTER LAYER — cho run_hcm_hn.py import
#  Giu nguyen code goc, chi them alias/wrapper
# =================================================================
from dataclasses import dataclass, asdict, field as dc_field
from typing import Optional

@dataclass
class Listing:
    """Wrapper dataclass tuong thich voi run_hcm_hn.py"""
    post_id:           Optional[str]   = None
    url:               Optional[str]   = None
    post_date:         Optional[str]   = None
    post_type:         Optional[str]   = None
    is_urgent:         Optional[bool]  = None
    seller_type:       Optional[str]   = None
    property_type:     Optional[str]   = None
    project_name:      Optional[str]   = None
    price:             Optional[float] = None
    price_per_m2:      Optional[float] = None
    area:              Optional[float] = None
    area_used:         Optional[float] = None
    floors:            Optional[int]   = None
    bedrooms:          Optional[int]   = None
    bathrooms:         Optional[int]   = None
    frontage:          Optional[float] = None
    acces_road:        Optional[float] = None
    house_direction:   Optional[str]   = None
    balcony_direction: Optional[str]   = None
    floors_apartment:  Optional[int]   = None
    year_built:        Optional[int]   = None
    address_full:      Optional[str]   = None
    street:            Optional[str]   = None
    ward:              Optional[str]   = None
    district:          Optional[str]   = None
    city:              Optional[str]   = None
    legal_status:      Optional[str]   = None
    furniture_state:   Optional[str]   = None
    has_garage:        Optional[bool]  = None
    has_pool:          Optional[bool]  = None
    has_elevator:      Optional[bool]  = None
    has_security:      Optional[bool]  = None
    has_parking:       Optional[bool]  = None
    management_fee:    Optional[float] = None
    has_swimming_pool: Optional[bool]  = None
    has_gym:           Optional[bool]  = None
    has_supermarket:   Optional[bool]  = None
    building_density:  Optional[float] = None
    crawled_at:        Optional[str]   = None
    source:            Optional[str]   = None


def is_cf_challenge(src: str) -> bool:
    return any(x in src for x in [
        "cf-turnstile", "Just a moment", "challenge-platform",
        "Performing security", "Checking your browser",
    ])


def make_driver(headless: bool = False):
    """Alias cho build_driver() — tuong thich voi run_hcm_hn.py"""
    return build_driver()


def safe_get(driver, url: str, retries: int = 3) -> bool:
    """Alias dung fetch() ben duoi — tra ve True neu thanh cong."""
    for attempt in range(retries):
        html = fetch(driver, url, wait=True)
        if html and not is_cf_challenge(html):
            return True
        print(f"  [RETRY] safe_get attempt {attempt+1}/{retries}")
        time.sleep(5)
    return False


class BDSParser:
    """
    Wrapper class xung quanh cac ham parse hien co (get_post_urls, parse_detail).
    run_hcm_hn.py goi parser.get_listing_urls() va parser.parse_detail().
    """
    BASE = "https://batdongsan.com.vn"

    def __init__(self, driver):
        self.driver = driver

    def get_listing_urls(self, page_url: str) -> list:
        """Lay danh sach URL bai dang tren 1 trang."""
        html = fetch(self.driver, page_url, wait=False)
        if not html or is_cf_challenge(html):
            return []
        # scroll nhe de trigger lazy-load
        human_scroll(self.driver)
        time.sleep(random.uniform(1.5, 2.5))
        # lay lai sau scroll
        html = self.driver.page_source
        urls = get_post_urls(html, self.BASE)
        return list(urls)

    def parse_detail(self, url: str) -> Optional[Listing]:
        """Crawl va parse 1 bai dang chi tiet, tra ve Listing object."""
        html = fetch(self.driver, url, wait=True)
        if not html or is_cf_challenge(html):
            return None

        rec = parse_detail(html, url)   # ham hien co trong x.py

        # Chuyen tu dict -> Listing dataclass
        l = Listing()
        for field_name in FIELDS:
            if hasattr(l, field_name):
                setattr(l, field_name, rec.get(field_name))

        # Tinh price_per_m2 neu chua co
        if l.price_per_m2 is None and l.price and l.area:
            try:
                l.price_per_m2 = round(float(l.price) / float(l.area), 4)
            except:
                pass

        return l


def save_to_csv(listings, output_csv: str):
    """
    Nhan vao list[Listing] hoac list[dict], luu ra CSV.
    Tuong thich voi ca 2 kieu du lieu.
    """
    if not listings:
        return
    import pandas as pd
    from dataclasses import asdict as _asdict

    rows = []
    for item in listings:
        if isinstance(item, dict):
            rows.append(item)
        else:
            try:
                rows.append(_asdict(item))
            except Exception:
                rows.append(vars(item))

    df = pd.DataFrame(rows)
    # Dam bao thu tu cot
    all_cols = FIELDS + ["source"]
    final_cols = [c for c in all_cols if c in df.columns]
    df = df[final_cols]
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {len(df):,} rows -> {output_csv}")