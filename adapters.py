# -*- coding: utf-8 -*-
"""
樂屋網抓取 adapter。

卡片邊界判定（重要）：
  以每個建案的 nc_item/info?ehid=xxx 連結為錨點，向上尋找「仍然只包含這一個
  建案連結」的最大容器，作為該案的卡片範圍。一旦某層祖先包含了第二個建案連結，
  就停在上一層。這個做法不依賴價格是否存在、也不依賴 CSS class，
  因此「開價未定」的案件不會誤抓到鄰居的資料（舊版的重複bug就是這樣來的）。

第二道保險：內容簽章去重（案名+行政區+單價+坪數房型 完全相同視為重複）。
"""
import re
import time
import requests
from bs4 import BeautifulSoup
from typing import List

from config import REQUEST_TIMEOUT, REQUEST_DELAY, USER_AGENT, RAKUYA_MAX_PAGES
from models import Listing

BASE = "https://www.rakuya.com.tw/nc/result"

RAKUYA_CITY_PARAMS = {
    "新北市": [
        {"city": "2"},
    ],
    "桃園市_青埔": [
        {"city": "4", "zipcode": "320"},   # 中壢區
        {"city": "4", "zipcode": "337"},   # 大園區
    ],
}

CITY_PREFIX = {
    "新北市": "新北市",
    "桃園市_青埔": "桃園市",
}

EHID_RE = re.compile(r"ehid=([0-9a-fA-F]+)")
PRICE_RE = re.compile(r"萬元?\s*/\s*坪")
REGION_RE = re.compile(r"(台北市|新北市|桃園市|基隆市)([\u4e00-\u9fa5]{1,3}區)")


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


def _ehids_in(node) -> set:
    """該節點底下所有建案的 ehid 集合。"""
    out = set()
    for link in node.select("a[href*='nc_item/info']"):
        m = EHID_RE.search(link.get("href", ""))
        if m:
            out.add(m.group(1))
    return out


def _find_card(anchor, ehid):
    """
    向上找「仍只含這一個 ehid」的最大容器，作為卡片邊界。
    一旦某層祖先出現第二個建案，就停在上一層。
    """
    node = anchor
    for _ in range(12):
        parent = node.parent
        if parent is None or parent.name in ("body", "html", "[document]"):
            break
        ehids = _ehids_in(parent)
        if len(ehids) > 1:      # 這層已經含到別的案子了，停在上一層
            break
        node = parent
    return node


def _parse_rakuya_page(html: str, city: str) -> List[Listing]:
    soup = BeautifulSoup(html, "lxml")
    listings: List[Listing] = []
    seen_ehid = set()
    city_prefix = CITY_PREFIX.get(city, "")

    for a in soup.select("a[href*='nc_item/info']"):
        href = a.get("href", "")
        m = EHID_RE.search(href)
        if not m:
            continue
        ehid = m.group(1)
        if ehid in seen_ehid:
            continue
        seen_ehid.add(ehid)

        card = _find_card(a, ehid)

        # 案名：卡片內第一個非純數字（非照片張數）的建案連結文字
        name = ""
        for link in card.select("a[href*='nc_item/info']"):
            t = link.get_text(strip=True)
            if t and not t.isdigit() and t not in ("看", "see"):
                name = t
                break
        if not name:
            continue

        # 行政區（並確認屬於本城市）
        pieces = [s.strip() for s in card.stripped_strings if s.strip()]
        text_all = " ".join(pieces)
        region = ""
        mm = REGION_RE.search(text_all)
        if mm:
            if mm.group(1) != city_prefix:
                continue          # 不是本城市的案子，跳過
            region = mm.group(2)
        else:
            continue              # 抓不到行政區，資料不完整，跳過

        # 單價 / 狀態 / 坪數房型：逐段文字比對特徵
        price = status = size_room = ""
        for t in pieces:
            if len(t) > 40:
                continue
            if not price and PRICE_RE.search(t):
                price = t
            elif not status and ("預售屋" in t or "新成屋" in t):
                status = "預售屋" if "預售屋" in t else "新成屋"
            elif not size_room and "坪" in t and ("房" in t or "格局" in t):
                size_room = t

        url = href if href.startswith("http") else ("https://www.rakuya.com.tw" + href)

        listings.append(Listing(
            city=city, region=region, name=name, source="rakuya",
            url=url, price=price, status=status, address=size_room,
        ))

    return listings


def fetch_rakuya(city: str, city_cfg: dict) -> List[Listing]:
    """抓樂屋網某城市預售屋（含翻頁）。"""
    param_sets = RAKUYA_CITY_PARAMS.get(city, [])
    if not param_sets:
        print(f"[rakuya][{city}] 無查詢參數設定，略過")
        return []

    session = _make_session()
    all_listings: List[Listing] = []
    seen_ehid = set()
    seen_sig = set()      # 內容簽章，第二道去重

    for params in param_sets:
        for page in range(1, RAKUYA_MAX_PAGES + 1):
            url = _build_url(params, page)
            try:
                r = session.get(url, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    print(f"[rakuya][{city}] {params} p{page} HTTP {r.status_code}，停止")
                    break
                r.encoding = r.apparent_encoding
            except Exception as e:
                print(f"[rakuya][{city}] {params} p{page} 失敗：{e}")
                break

            page_listings = _parse_rakuya_page(r.text, city)

            new_in_page = 0
            for lst in page_listings:
                m = EHID_RE.search(lst.url)
                ehid = m.group(1) if m else lst.name
                if ehid in seen_ehid:
                    continue
                sig = f"{lst.name}|{lst.region}|{lst.price}|{lst.address}"
                if sig in seen_sig:
                    continue      # 內容完全相同 = 重複刊登，略過
                seen_ehid.add(ehid)
                seen_sig.add(sig)
                all_listings.append(lst)
                new_in_page += 1

            print(f"[rakuya][{city}] {params} p{page}：本頁 {len(page_listings)} 筆、新增 {new_in_page} 筆")
            time.sleep(REQUEST_DELAY)

            if len(page_listings) == 0 or new_in_page == 0:
                break          # 翻到底或整頁都是重複，換下一組參數

    print(f"[rakuya][{city}] 合計 {len(all_listings)} 筆")
    return all_listings


ADAPTER_MAP = {
    "rakuya": fetch_rakuya,
}
