# -*- coding: utf-8 -*-
"""
資料源設定檔（可插拔）。
每個「城市」是一份設定；要新增城市（例如未來想加台中），
只需在 CITIES 裡多加一個 entry，並在 adapters/ 裡對應實作解析邏輯。

region_map：把資料源回傳的行政區字串，歸類到你想要的「通知分組」。
            key 是分組顯示名稱，value 是屬於這組的行政區清單。
            沒被列到的行政區，會自動落到 "其他" 分組，不會漏掉。
"""

CITIES = {
    "新北市": {
        "enabled": True,
        # 樂屋網 / 住展的新北市新案列表頁。實際網址在 adapter 裡使用。
        "sources": ["rakuya", "housefun"],
        # 通知時的區域分組。你可以自由調整分組方式。
        "region_groups": {
            "板橋雙和線": ["板橋區", "中和區", "永和區"],
            "三重蘆洲線": ["三重區", "蘆洲區", "五股區", "泰山區"],
            "新莊林口線": ["新莊區", "林口區", "八里區"],
            "土城樹林線": ["土城區", "樹林區", "鶯歌區", "三峽區"],
            "新店深坑線": ["新店區", "深坑區", "石碇區"],
            "淡水汐止線": ["淡水區", "汐止區", "瑞芳區", "金山區", "萬里區"],
        },
    },
    "桃園市_青埔": {
        "enabled": True,
        "sources": ["rakuya", "housefun"],
        # 只鎖青埔，青埔行政上屬中壢區與大園區交界，用關鍵字過濾。
        # adapter 會在抓桃園資料後，只留下地址/案名含這些關鍵字的案件。
        "keyword_filter": ["青埔", "高鐵桃園", "領航", "青塘園", "橫科"],
        "region_groups": {
            "青埔特區": ["中壢區", "大園區"],
        },
    },
}

# 建照查詢層（領先指標）：每週跑一次的獨立排程使用。
# 第一版先放官方查詢入口網址供人工/後續自動化，解析邏輯獨立於每日流程。
BUILDING_PERMIT_SOURCES = {
    "新北市": "https://building-management.publicwork.ntpc.gov.tw/",
    "桃園市": "https://building.tycg.gov.tw/",  # 桃園市政府建管單位入口（青埔用）
}

# 抓取禮貌設定
REQUEST_TIMEOUT = 20          # 單一請求逾時秒數
REQUEST_DELAY = 2.0           # 每次請求之間的間隔秒數（避免對網站造成負擔）
RAKUYA_MAX_PAGES = 13         # 樂屋網新建案列表最多翻幾頁（依實際總頁數調整）
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
