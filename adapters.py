# -*- coding: utf-8 -*-
"""
資料源抓取。

樂屋網 (rakuya)：https://www.rakuya.com.tw/nc/result?search=city&city=..&tab=presale_house
好房網 (housefun)：https://newhouse.housefun.com.tw/region/{縣市}-{行政區}_c/
  兩者皆為伺服器渲染，requests 即可抓取。
  （591 為 JavaScript 動態載入，需 Playwright，暫未納入。）

卡片邊界判定：以建案詳情連結為錨點，往上找「仍只含這一個建案」的最大容器。
不依賴 CSS class 或價格是否存在，避免「開價未定」的案子誤抓鄰居資料。
"""
import re
import time
import requests
from bs4 import BeautifulSoup
from typing import List
from urllib.parse import quote

from config import (REQUEST_TIMEOUT, REQUEST_DELAY, USER_AGENT,
                    RAKUYA_MAX_PAGES, HOUSEFUN_MAX_PAGES)
from models import Listing

# ── 通用工具 ────────────────────────────────────────────────
REGION_RE = re.compile(r"(台北市|新北市|桃園市|基隆市)([\u4e00-\u9fa5]{1,3}區)")
PRICE_RE = re.compile(r"萬\s*元?\s*/\s*(坪|戶)")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def _ids_in(node, pattern) -> set:
    out = set()
    for link in node.select("a[href]"):
        m = pattern.search(link.get("href", ""))
        if m:
            out.add(m.group(1))
    return out


def _find_card(anchor, pattern):
    """往上找仍只含一個建案ID的最大容器。"""
    node = anchor
    for _ in range(12):
        parent = node.parent
        if parent is None or parent.name in ("body", "html", "[document]"):
            break
        if len(_ids_in(parent, pattern)) > 1:
            break
        node = parent
    return node


# ══════════════════════════════════════════════════════════
# 樂屋網
# ══════════════════════════════════════════════════════════
RAKUYA_ID_RE = re.compile(r"ehid=([0-9a-fA-F]+)")
RAKUYA_BASE = "https://www.rakuya.com.tw/nc/result"

RAKUYA_CITY_PARAMS = {
    "新北市": [{"city": "2"}],
    "桃園市_青埔": [{"city": "4", "zipcode": "320"}, {"city": "4", "zipcode": "337"}],
}
CITY_PREFIX = {"新北市": "新北市", "桃園市_青埔": "桃園市"}


def _parse_rakuya(html: str, city: str) -> List[Listing]:
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    prefix = CITY_PREFIX.get(city, "")

    for a in soup.select("a[href*='nc_item/info']"):
        m = RAKUYA_ID_RE.search(a.get("href", ""))
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        card = _find_card(a, RAKUYA_ID_RE)

        name = ""
        for link in card.select("a[href*='nc_item/info']"):
            t = link.get_text(strip=True)
            if t and not t.isdigit() and t not in ("看", "see"):
                name = t
                break
        if not name:
            continue

        pieces = [s.strip() for s in card.stripped_strings if s.strip()]
        mm = REGION_RE.search(" ".join(pieces))
        if not mm or mm.group(1) != prefix:
            continue
        region = mm.group(2)

        price = status = rooms = ""
        for t in pieces:
            if len(t) > 40:
                continue
            if not price and PRICE_RE.search(t):
                price = t
            elif not status and ("預售屋" in t or "新成屋" in t):
                status = "預售屋" if "預售屋" in t else "新成屋"
            elif not rooms and "坪" in t and ("房" in t or "格局" in t):
                rooms = t

        href = a.get("href", "")
        url = href if href.startswith("http") else "https://www.rakuya.com.tw" + href
        out.append(Listing(city=city, region=region, name=name, source="rakuya",
                           url=url, price=price, rooms=rooms, status=status))
    return out


def fetch_rakuya(city: str, cfg: dict) -> List[Listing]:
    params_list = RAKUYA_CITY_PARAMS.get(city, [])
    if not params_list:
        return []
    s = _session()
    out, seen_uid = [], set()

    for params in params_list:
        for page in range(1, RAKUYA_MAX_PAGES + 1):
            q = [("search", "city")] + list(params.items()) + \
                [("tab", "presale_house"), ("sort", "11"), ("page", str(page))]
            url = RAKUYA_BASE + "?" + "&".join(f"{k}={v}" for k, v in q)
            try:
                r = s.get(url, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    break
                r.encoding = r.apparent_encoding
            except Exception as e:
                print(f"[rakuya][{city}] p{page} 失敗：{e}")
                break

            page_items = _parse_rakuya(r.text, city)
            new = 0
            for lst in page_items:
                if lst.uid() not in seen_uid:
                    seen_uid.add(lst.uid())
                    out.append(lst)
                    new += 1
            time.sleep(REQUEST_DELAY)
            if not page_items or new == 0:
                break

    print(f"[rakuya][{city}] 抓到 {len(out)} 筆")
    return out


# ══════════════════════════════════════════════════════════
# 好房網
# ══════════════════════════════════════════════════════════
HF_ID_RE = re.compile(r"/building/(\d+)")
HF_BASE = "https://newhouse.housefun.com.tw/region"

# 翻頁網址候選格式（第一次抓時自動偵測哪個有效）
HF_PAGE_FORMATS = ["{base}?p={n}", "{base}?page={n}", "{base}/{n}_p/"]


def _hf_district_url(county: str, district: str) -> str:
    return f"{HF_BASE}/{quote(county)}-{quote(district)}_c"


def _parse_housefun(html: str, city: str, county: str) -> List[Listing]:
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()

    for a in soup.select("a[href*='/building/']"):
        m = HF_ID_RE.search(a.get("href", ""))
        if not m or m.group(1) in seen:
            continue
        bid = m.group(1)
        seen.add(bid)
        card = _find_card(a, HF_ID_RE)

        # 案名：連到 /building/{id} 且文字非價格、非地址的連結
        name = ""
        for link in card.select("a[href*='/building/']"):
            t = link.get_text(strip=True)
            if not t or PRICE_RE.search(t) or "訂閱" in t or REGION_RE.search(t):
                continue
            if t in ("售價未定", "看更多"):
                continue
            name = t
            break
        if not name:
            continue

        pieces = [s.strip() for s in card.stripped_strings if s.strip()]
        text_all = " ".join(pieces)

        mm = REGION_RE.search(text_all)
        if not mm or mm.group(1) != county:
            continue
        region = mm.group(2)

        # 地址：含「縣市+區」的完整字串
        address = ""
        for t in pieces:
            if REGION_RE.search(t) and len(t) > 6:
                address = t
                break

        price = rooms = ""
        for t in pieces:
            if len(t) > 40:
                continue
            if not price and (PRICE_RE.search(t) or "售價未定" in t):
                price = t
            if not rooms and "坪" in t and ("房" in t or "格局" in t):
                rooms = t
        if not price:
            price = "售價未定"

        # 狀態：卡片內若標示新成屋則排除（我們只要預售）
        if "新成屋" in text_all:
            continue
        status = "預售屋" if "預售屋" in text_all else "未標示"

        out.append(Listing(city=city, region=region, name=name, source="housefun",
                           url=f"https://newhouse.housefun.com.tw/building/{bid}",
                           price=price, rooms=rooms, address=address, status=status))
    return out


def fetch_housefun(city: str, cfg: dict) -> List[Listing]:
    districts = cfg.get("housefun_districts", [])
    if not districts:
        return []
    s = _session()
    out, seen_uid = [], set()
    page_fmt = None      # 自動偵測到的翻頁格式

    for county, district in districts:
        base = _hf_district_url(county, district)

        # 第 1 頁
        try:
            r = s.get(base + "/", timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                print(f"[housefun] {district} HTTP {r.status_code}，略過")
                continue
            r.encoding = r.apparent_encoding
        except Exception as e:
            print(f"[housefun] {district} 失敗：{e}")
            continue

        p1 = _parse_housefun(r.text, city, county)
        p1_uids = {l.uid() for l in p1}
        for lst in p1:
            if lst.uid() not in seen_uid:
                seen_uid.add(lst.uid())
                out.append(lst)
        time.sleep(REQUEST_DELAY)

        if not p1:
            continue

        # 翻頁格式自動偵測（只做一次）
        if page_fmt is None:
            for fmt in HF_PAGE_FORMATS:
                try:
                    tr = s.get(fmt.format(base=base, n=2), timeout=REQUEST_TIMEOUT)
                    tr.encoding = tr.apparent_encoding
                    if tr.status_code != 200:
                        continue
                    p2 = _parse_housefun(tr.text, city, county)
                    if p2 and any(l.uid() not in p1_uids for l in p2):
                        page_fmt = fmt
                        print(f"[housefun] 翻頁格式偵測成功：{fmt}")
                        break
                except Exception:
                    continue
                finally:
                    time.sleep(REQUEST_DELAY)
            if page_fmt is None:
                print("[housefun] 未偵測到翻頁格式，僅抓每區第1頁")

        # 續抓後續頁
        if page_fmt:
            for page in range(2, HOUSEFUN_MAX_PAGES + 1):
                try:
                    rr = s.get(page_fmt.format(base=base, n=page), timeout=REQUEST_TIMEOUT)
                    if rr.status_code != 200:
                        break
                    rr.encoding = rr.apparent_encoding
                except Exception:
                    break
                items = _parse_housefun(rr.text, city, county)
                new = 0
                for lst in items:
                    if lst.uid() not in seen_uid:
                        seen_uid.add(lst.uid())
                        out.append(lst)
                        new += 1
                time.sleep(REQUEST_DELAY)
                if not items or new == 0:
                    break

    print(f"[housefun][{city}] 抓到 {len(out)} 筆")
    return out


ADAPTER_MAP = {
    "rakuya": fetch_rakuya,
    "housefun": fetch_housefun,
}


# ══════════════════════════════════════════════════════════
# 591 新推建案（早期訊號源）
#
# 591 的列表本體是 JS 動態載入，requests 抓不到；
# 但列表頁底部的「新推建案」區塊是靜態 HTML，列出最新上架案
# （含「尚未取得建照」的超早期案）。建案詳情頁的 <title> 與
# meta description 是伺服器渲染的，格式：
#   title: {案名}-新建案-{縣市}{行政區} | 591新建案
# 策略：抓新推清單 -> 只對「沒見過的ID」抓詳情頁解析區域/價格。
# 已見過的 ID 從 seen_listings.json 裡既有 591 連結取得，
# 避免每天重抓所有詳情頁。
# ══════════════════════════════════════════════════════════
H591_ID_RE = re.compile(r"newhouse\.591\.com\.tw/(\d+)")
H591_TITLE_RE = re.compile(
    r"(.+?)-新建案-(台北市|新北市|桃園市|基隆市)([\u4e00-\u9fa5]{1,3}區)")
H591_PRICE_RE = re.compile(r"單價([\d.]+)萬元?/坪起?")

H591_REGIONS = {
    "新北市": "3",
    "桃園市_青埔": "6",
}
H591_QINGPU_DISTRICTS = {"中壢區", "大園區"}
H591_MAX_NEW_DETAILS = 12    # 每縣市每天最多抓幾個新案詳情頁


def _known_591_ids() -> set:
    """從既有基準線取得已見過的 591 案件 ID，避免重抓詳情頁。"""
    try:
        import json as _json
        with open("seen_listings.json", encoding="utf-8") as f:
            seen = _json.load(f)
        ids = set()
        for item in seen.values():
            m = H591_ID_RE.search(item.get("url", ""))
            if m:
                ids.add(m.group(1))
        return ids
    except Exception:
        return set()


def _parse_591_new_block(html: str) -> list:
    """解析列表頁「新推建案」區塊，回傳 [(id, 案名), ...]（保持頁面順序）。"""
    soup = BeautifulSoup(html, "lxml")
    marker = soup.find(string=re.compile("新推建案"))
    if not marker:
        return []
    # 往上找包含多個建案連結的容器
    node = marker.parent
    for _ in range(6):
        if node is None:
            return []
        links = node.select("a[href*='newhouse.591.com.tw/']")
        ids = [(m.group(1), a.get_text(strip=True))
               for a in links
               if (m := H591_ID_RE.search(a.get("href", "")))]
        if len(ids) >= 3:
            # 排除混入「熱銷建案」等其他區塊：容器不能太大
            text = node.get_text()
            if "熱銷建案" in text or "大型建案" in text:
                node = None  # 找過頭了，改用保守策略
                break
            return [(i, n) for i, n in ids if n]
        node = node.parent

    # 保守策略：marker 後面的兄弟連結，直到遇到下一個區塊標題
    out = []
    for el in marker.parent.next_elements:
        if isinstance(el, str) and ("熱銷建案" in el or "大型建案" in el):
            break
        if getattr(el, "name", None) == "a":
            m = H591_ID_RE.search(el.get("href", ""))
            t = el.get_text(strip=True)
            if m and t:
                out.append((m.group(1), t))
    return out


def _fetch_591_detail(session, bid: str):
    """抓詳情頁，從 title/meta 解析 (案名, 縣市, 行政區, 價格)。失敗回 None。"""
    url = f"https://newhouse.591.com.tw/{bid}"
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        r.encoding = r.apparent_encoding
    except Exception:
        return None

    soup = BeautifulSoup(r.text, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    m = H591_TITLE_RE.search(title)
    if not m:
        return None
    name, county, region = m.group(1).strip(), m.group(2), m.group(3)

    desc = ""
    md = soup.find("meta", attrs={"name": "description"}) or \
         soup.find("meta", attrs={"property": "og:description"})
    if md:
        desc = md.get("content", "")
    pm = H591_PRICE_RE.search(desc)
    price = f"{pm.group(1)}萬/坪起" if pm else ("售價未定" if "售價未定" in desc else "")

    return name, county, region, price, url


def fetch_591(city: str, cfg: dict) -> List[Listing]:
    regionid = H591_REGIONS.get(city)
    if not regionid:
        return []
    s = _session()
    prefix = CITY_PREFIX.get(city, "")

    try:
        r = s.get(f"https://newhouse.591.com.tw/list?regionid={regionid}",
                  timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            print(f"[591][{city}] 列表 HTTP {r.status_code}，略過")
            return []
        r.encoding = r.apparent_encoding
    except Exception as e:
        print(f"[591][{city}] 列表抓取失敗：{e}")
        return []
    time.sleep(REQUEST_DELAY)

    new_block = _parse_591_new_block(r.text)
    if not new_block:
        print(f"[591][{city}] 未解析到新推建案區塊（頁面可能改版），略過")
        return []

    known = _known_591_ids()
    todo = [(bid, nm) for bid, nm in new_block if bid not in known]
    print(f"[591][{city}] 新推建案 {len(new_block)} 筆，其中未見過 {len(todo)} 筆")

    out = []
    for bid, list_name in todo[:H591_MAX_NEW_DETAILS]:
        detail = _fetch_591_detail(s, bid)
        time.sleep(REQUEST_DELAY)
        if not detail:
            continue
        name, county, region, price, url = detail
        if county != prefix:
            continue
        if city == "桃園市_青埔" and region not in H591_QINGPU_DISTRICTS:
            continue
        # 591 新推清單常標註「(尚未取得建照)」，保留在案名裡當訊號
        status = "新推" if "尚未取得建照" not in name else "新推(未取得建照)"
        out.append(Listing(city=city, region=region,
                           name=name.replace("(尚未取得建照)", "").strip(),
                           source="591", url=url, price=price, status=status))

    print(f"[591][{city}] 納入 {len(out)} 筆")
    return out


ADAPTER_MAP["591"] = fetch_591
