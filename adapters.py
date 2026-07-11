# -*- coding: utf-8 -*-
"""
各資料源的抓取 adapter。

目前實作：樂屋網（rakuya）—— 已依實際 HTML 結構撰寫並驗證解析邏輯。
第二階段：住展找房（myhousingex）—— 為純 SPA，需 Playwright，見檔案下方說明。

解析策略：以每個建案的 nc_item/info?ehid=xxx 連結為錨點，
用「內容特徵」抓各欄位（看到「萬元/坪」判定為價格、看到「預售屋」判定為狀態），
不死綁 CSS class，因此樂屋網微幅改版時仍有機會正常運作。
"""
import re
import time
import requests
from bs4 import BeautifulSoup
from typing import List

from config import REQUEST_TIMEOUT, REQUEST_DELAY, USER_AGENT, RAKUYA_MAX_PAGES
from models import Listing

# 各縣市在樂屋網新建案搜尋的城市代碼（用於組 search 參數）
# 樂屋網新建案列表可直接用 ?city= 篩選；若參數失效，改用不帶城市、
# 抓全部再用行政區過濾（本 adapter 兩種都支援，預設用行政區過濾較穩）。
RAKUYA_CITY_NAMES = {
    "新北市": "新北市",
    "桃園市_青埔": "桃園市",
}

# 判斷行政區屬於哪個「來源城市 key」用的城市前綴
CITY_PREFIX = {
    "新北市": "新北市",
    "桃園市_青埔": "桃園市",
}


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    })
    return s


def _parse_rakuya_page(html: str, city: str, city_cfg: dict) -> List[Listing]:
    """解析單頁樂屋網新建案列表。"""
    soup = BeautifulSoup(html, "lxml")
    listings: List[Listing] = []
    seen_ehid = set()
    city_prefix = CITY_PREFIX.get(city, "")

    for a in soup.select("a[href*='nc_item/info']"):
        href = a.get("href", "")
        m = re.search(r"ehid=([0-9a-fA-F]+)", href)
        if not m:
            continue
        ehid = m.group(1)
        if ehid in seen_ehid:
            continue
        seen_ehid.add(ehid)

        # 卡片容器：往上找最近、且包含價格資訊的祖先
        card = a
        for _ in range(6):
            card = card.parent
            if card is None:
                break
            if card.find(string=re.compile(r"萬元?/坪")):
                break
        if card is None:
            continue

        # 案名：第一個非圖示的 nc_item 連結文字
        name = ""
        for link in card.select("a[href*='nc_item/info']"):
            t = link.get_text(strip=True)
            if t and t not in ("看", "see", ""):
                name = t
                break
        if not name:
            continue

        # 行政區（限定本城市前綴，避免把台北市案件誤算進新北）
        region = ""
        city_ok = False
        text_all = card.get_text(" ", strip=True)
        mm = re.search(r"(台北市|新北市|桃園市|基隆市)([\u4e00-\u9fa5]{1,3}區)", text_all)
        if mm:
            region = mm.group(2)
            city_ok = (mm.group(1) == city_prefix)

        # 只保留屬於目標城市的案件
        if city_prefix and not city_ok:
            continue

        # 價格 / 狀態 / 坪數房型
        price = status = size_room = ""
        for chunk in card.find_all(["li", "p", "span", "div"]):
            t = chunk.get_text(strip=True)
            if not t:
                continue
            if not price and re.search(r"萬元?/坪", t):
                price = t
            elif not status and ("預售屋" in t or "新成屋" in t):
                status = "預售屋" if "預售屋" in t else "新成屋"
            elif not size_room and ("坪" in t and "房" in t):
                size_room = t

        url = href if href.startswith("http") else ("https://www.rakuya.com.tw" + href)

        listings.append(Listing(
            city=city, region=region, name=name, source="rakuya",
            url=url, price=price, status=status, address=size_room,
        ))

    return listings


def fetch_rakuya(city: str, city_cfg: dict) -> List[Listing]:
    """
    抓樂屋網某城市新建案（含翻頁）。
    網址：https://www.rakuya.com.tw/nc/result
    只抓「預售屋」tab（tab=presale_house），符合搶早鳥的目標。
    """
    base = "https://www.rakuya.com.tw/nc/result"
    session = _make_session()
    all_listings: List[Listing] = []
    seen_ehid = set()

    for page in range(1, RAKUYA_MAX_PAGES + 1):
        # tab=presale_house 只看預售屋；sort=11 通常為最新更新排序
        url = f"{base}?tab=presale_house&sort=11&page={page}"
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                print(f"[rakuya][{city}] page {page} HTTP {r.status_code}，停止翻頁")
                break
            r.encoding = r.apparent_encoding
        except Exception as e:
            print(f"[rakuya][{city}] page {page} 抓取失敗：{e}")
            break

        page_listings = _parse_rakuya_page(r.text, city, city_cfg)

        # 去重 + 判斷是否還有新內容（沒有就代表翻到底了）
        new_in_page = 0
        for lst in page_listings:
            m = re.search(r"ehid=([0-9a-fA-F]+)", lst.url)
            ehid = m.group(1) if m else lst.name
            if ehid not in seen_ehid:
                seen_ehid.add(ehid)
                all_listings.append(lst)
                new_in_page += 1

        print(f"[rakuya][{city}] page {page}：本頁 {len(page_listings)} 筆、新增 {new_in_page} 筆")

        # 這一頁完全沒有屬於本城市的新案，可能已翻到與本城市無關的頁；
        # 但因為列表是全台混排，保險起見仍續抓到 MAX_PAGES。
        time.sleep(REQUEST_DELAY)

    return _apply_keyword_filter(all_listings, city_cfg)


# ──────────────────────────────────────────────────────────────
def _apply_keyword_filter(listings: List[Listing], city_cfg: dict) -> List[Listing]:
    """若城市設定有 keyword_filter（例如青埔），只留含關鍵字的案件。"""
    keywords = city_cfg.get("keyword_filter")
    if not keywords:
        return listings
    filtered = []
    for lst in listings:
        haystack = f"{lst.name} {lst.address} {lst.region}"
        if any(kw in haystack for kw in keywords):
            filtered.append(lst)
    return filtered


# adapter 名稱 -> 函式
ADAPTER_MAP = {
    "rakuya": fetch_rakuya,
}


# ══════════════════════════════════════════════════════════════
# 第二階段：住展找房（myhousingex.com.tw）
#
# 住展找房是純 JavaScript SPA，requests 抓不到內容，需要用 Playwright。
# 建案詳情頁格式：https://www.myhousingex.com.tw/developments/{代碼}
# （例如 甲山林市政帝景 -> /developments/22UHXGXL）
#
# 待加入時的骨架：
#
#   from playwright.sync_api import sync_playwright
#
#   def fetch_myhousingex(city, city_cfg):
#       url = "https://www.myhousingex.com.tw/developments?city=新北市"
#       with sync_playwright() as p:
#           browser = p.chromium.launch(headless=True)
#           page = browser.new_page(user_agent=USER_AGENT)
#           page.goto(url)
#           page.wait_for_selector("a[href*='/developments/']")
#           html = page.content()
#           browser.close()
#       # 用 developments/{代碼} 的代碼當唯一 ID，解析同 rakuya
#       ...
#
# 需求：requirements.txt 加 playwright，workflow 加 playwright install chromium。
# ══════════════════════════════════════════════════════════════
