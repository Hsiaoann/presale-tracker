# -*- coding: utf-8 -*-
"""共用資料結構與工具函式。"""
import hashlib
from dataclasses import dataclass, asdict


@dataclass
class Listing:
    """一筆建案。所有 adapter 都必須回傳這個統一格式。"""
    city: str                    # 來源城市設定名稱，例如 "新北市"
    region: str                  # 行政區，例如 "板橋區"
    name: str                    # 案名
    source: str                  # 來源網站：rakuya / housefun
    url: str = ""                # 建案詳情頁連結
    price: str = ""              # 單價字串
    rooms: str = ""              # 坪數房型
    address: str = ""            # 地址（好房網有，樂屋網無）
    status: str = ""             # 預售屋 / 新成屋 / 未標示

    def uid(self) -> str:
        """
        唯一識別碼 = 城市 + 行政區 + 案名（正規化後雜湊）。
        刻意「不」使用各網站自己的ID，因為同一個建案在樂屋網和好房網
        會有不同的網站ID；用內容當識別碼，跨來源才能自動合併成同一筆，
        不會同一個案子通知你兩次。
        """
        norm = self.name.replace(" ", "").replace("　", "").strip()
        raw = f"{self.city}|{self.region}|{norm}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid()
        return d


def group_by_region(listings, region_groups) -> dict:
    """依 config 的 region_groups 把 listings 分組。未列到的行政區歸「其他」。"""
    region_to_group = {}
    for group_name, regions in region_groups.items():
        for r in regions:
            region_to_group[r] = group_name

    grouped = {}
    for lst in listings:
        group = region_to_group.get(lst.region, "其他")
        grouped.setdefault(group, []).append(lst)
    return grouped
