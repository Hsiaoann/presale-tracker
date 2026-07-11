# -*- coding: utf-8 -*-
"""
共用資料結構與工具函式。
"""
import hashlib
from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class Listing:
    """一筆建案。所有 adapter 都必須回傳這個統一格式。"""
    city: str                    # 來源城市設定名稱，例如 "新北市"
    region: str                  # 行政區，例如 "板橋區"
    name: str                    # 案名
    source: str                  # 來源網站，例如 "rakuya"
    url: str = ""                # 建案詳情頁連結
    price: str = ""              # 價格帶字串，例如 "88~96萬/坪"，抓不到就留空
    status: str = ""             # 銷售狀態，例如 "公開銷售"/"最新推案"，抓不到就留空
    address: str = ""            # 地址或路段（青埔關鍵字過濾會用到）

    def uid(self) -> str:
        """
        產生穩定的唯一識別碼，用來做每日 diff 比對。
        優先用網址裡的天然 ID（樂屋網 ehid / 住展 developments 代碼），
        因為它最穩定、不受案名或行政區文字微調影響；
        抓不到時才退回 來源+案名+行政區 的雜湊。
        刻意不把 price/status 納入，這樣「同一個案子降價或狀態改變」
        不會被誤判成新案（狀態變化另外處理）。
        """
        import re
        m = re.search(r"ehid=([0-9a-fA-F]+)", self.url or "")
        if m:
            return f"rakuya:{m.group(1)}"
        m = re.search(r"/developments/([0-9A-Za-z]+)", self.url or "")
        if m:
            return f"myhousingex:{m.group(1)}"
        raw = f"{self.source}|{self.city}|{self.region}|{self.name}".strip()
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid()
        return d


def group_by_region(listings, region_groups) -> dict:
    """
    把一批 listings 依 config 裡定義的 region_groups 分組。
    回傳 dict：{分組名稱: [listing, ...]}。
    不在任何分組定義內的行政區，落到 "其他"。
    """
    # 建立 行政區 -> 分組名 的反查表
    region_to_group = {}
    for group_name, regions in region_groups.items():
        for r in regions:
            region_to_group[r] = group_name

    grouped = {}
    for lst in listings:
        group = region_to_group.get(lst.region, "其他")
        grouped.setdefault(group, []).append(lst)
    return grouped
