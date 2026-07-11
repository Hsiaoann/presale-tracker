# -*- coding: utf-8 -*-
"""
資料源設定檔。
城市查詢參數（樂屋網 city/zipcode 代碼）定義在 adapters.py 的 RAKUYA_CITY_PARAMS。
這裡管：啟用哪些城市、來源、通知的區域分組。
"""

CITIES = {
    "新北市": {
        "enabled": True,
        "sources": ["rakuya"],
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
        "sources": ["rakuya"],
        # 青埔橫跨中壢、大園兩區，樂屋網卡片無完整地址、多數青埔案名不含「青埔」，
        # 故直接鎖 zipcode 320（中壢）+337（大園）整區，範圍稍寬但保證不漏。
        "region_groups": {
            "青埔周邊（中壢/大園）": ["中壢區", "大園區"],
        },
    },
}

# 建照查詢層（領先指標）：每週手動查或後續另寫週排程。
BUILDING_PERMIT_SOURCES = {
    "新北市": "https://building-management.publicwork.ntpc.gov.tw/",
    "桃園市": "https://building.tycg.gov.tw/",
}

# 抓取禮貌設定
REQUEST_TIMEOUT = 20
REQUEST_DELAY = 2.0
RAKUYA_MAX_PAGES = 15   # 每組查詢參數最多翻幾頁（翻到空頁會自動停）
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
