# -*- coding: utf-8 -*-
"""
樂屋網抓取 adapter（已依實際網址參數與 HTML 結構修正）。

網址格式（經實際驗證）：
  https://www.rakuya.com.tw/nc/result?search=city&city={城市代碼}[&zipcode={行政區代碼}]&tab=presale_house&sort=11&page={頁數}
  城市代碼：2=新北市、4=桃園市
  行政區代碼（zipcode）：320=中壢區、337=大園區（青埔涵蓋這兩區）

解析策略：以每個建案的 nc_item/info?ehid=xxx 連結為錨點，
用「內容特徵」抓各欄位，不死綁 CSS class，樂屋網微幅改版時仍可運作。
"""
import re
import time
import requests
from bs4 import BeautifulSoup
from typing import List

from config import REQUEST_TIMEOUT, REQUEST_DELAY, USER_AGENT, RAKUYA_MAX_PAGES
from models import Listing

BASE = "https://www.rakuya.com.tw/nc/result"

# 每個「城市設定」對應一組或多組查詢參數（青埔 = 中壢 + 大園 兩個 zipcode）
RAKUYA_CITY_PARAMS = {
    "新北市": [
        {"city": "2"},
    ],
    "桃園市_青埔": [
        {"city": "4", "zipcode": "320"},   # 中壢區（青埔主體）
        {"city": "4", "zipcode": "337"},   # 大園區（青埔北側）
    ],
}

# 行政區前綴檢查（保險用，確保不混入其他縣市）
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
    })
    return s


def _build_url(params: dict, page: int) -> str:
    q = [("search", "city")]
    q += [(k, v) for k, v in params.items()]
    q += [("tab", "presale_house"), ("sort", "11"), ("page", str(page))]
    return BASE + "?" + "&".join(f"{k}={v}" for k, v in q)


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

        # 卡片容器：往上找包含價格資訊的祖先
        card = a
        for _ in range(6):
            card = card.parent
            if card is None:
                break
            if card.find(string=re.compile(r"萬元?/坪")):
                break
        if card is None:
            continue

        # 案名：第一個非圖示的 nc_item 連結文字（排除純數字的照片數連結）
        name = ""
        for link in card.select("a[href*='nc_item/info']"):
            t = link.get_text(strip=True)
            if t and t not in ("看", "see") and not t.isdigit():
                name = t
                break
        if not name:
            continue

        # 行政區
        region = ""
        city_ok = False
        text_all = card.get_text(" ", strip=True)
        mm = re.search(r"(台北市|新北市|桃園市|基隆市)([\u4e00-\u9fa5]{1,3}區)", text_all)
        if mm:
            region = mm.group(2)
            city_ok = (mm.group(1) == city_prefix)
        if city_prefix and not city_ok:
            continue

        # 價格 / 狀態 / 坪數房型
        price = status = size_room = ""
        for chunk in card.find_all(["li", "p", "span", "div"]):
            t = chunk.get_text(strip=True)
            if not t:
                continue
            if not price and re.search(r"萬元?/坪", t) and len(t) < 30:
                price = t
            elif not status and ("預售屋" in t or "新成屋" in t) and len(t) < 30:
                status = "預售屋" if "預售屋" in t else "新成屋"
            elif not size_room and ("坪" in t and "房" in t) and len(t) < 30:
                size_room = t

        url = href if href.startswith("http") else ("https://www.rakuya.com.tw" + href)

        listings.append(Listing(
            city=city, region=region, name=name, source="rakuya",
            url=url, price=price, status=status, address=size_room,
        ))

    return listings


def fetch_rakuya(city: str, city_cfg: dict) -> List[Listing]:
    """抓樂屋網某城市新建案（含翻頁，鎖定預售屋 tab）。"""
    param_sets = RAKUYA_CITY_PARAMS.get(city, [])
    if not param_sets:
        print(f"[rakuya][{city}] 無查詢參數設定，略過")
        return []

    session = _make_session()
    all_listings: List[Listing] = []
    seen_ehid = set()

    for params in param_sets:
        for page in range(1, RAKUYA_MAX_PAGES + 1):
            url = _build_url(params, page)
            try:
                r = session.get(url, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    print(f"[rakuya][{city}] {params} page {page} HTTP {r.status_code}，停止翻頁")
                    break
                r.encoding = r.apparent_encoding
            except Exception as e:
                print(f"[rakuya][{city}] {params} page {page} 抓取失敗：{e}")
                break

            page_listings = _parse_rakuya_page(r.text, city, city_cfg)

            new_in_page = 0
            for lst in page_listings:
                m = re.search(r"ehid=([0-9a-fA-F]+)", lst.url)
                ehid = m.group(1) if m else lst.name
                if ehid not in seen_ehid:
                    seen_ehid.add(ehid)
                    all_listings.append(lst)
                    new_in_page += 1

            print(f"[rakuya][{city}] {params} page {page}：本頁 {len(page_listings)} 筆、新增 {new_in_page} 筆")
            time.sleep(REQUEST_DELAY)

            # 本頁解析不到任何案件 = 已翻過最後一頁，換下一組參數
            if len(page_listings) == 0:
                break

    return all_listings


ADAPTER_MAP = {
    "rakuya": fetch_rakuya,
}
