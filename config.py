# -*- coding: utf-8 -*-
"""
資料源設定。
sources 的順序＝優先順序：同一個建案若兩個來源都有，採用排在前面那個的資料。
好房網放前面，因為它多提供「地址」欄位。
"""

# 新北市要追蹤的行政區（好房網需要逐區抓）
NT_DISTRICTS = [
    "板橋區", "中和區", "永和區",
    "三重區", "蘆洲區", "五股區", "泰山區",
    "新莊區", "林口區", "八里區",
    "土城區", "樹林區", "鶯歌區", "三峽區",
    "新店區", "深坑區",
    "淡水區", "汐止區",
]

CITIES = {
    "新北市": {
        "enabled": True,
        "sources": ["housefun", "rakuya"],
        "housefun_districts": [("新北市", d) for d in NT_DISTRICTS],
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
        "sources": ["housefun", "rakuya", "591"],
        "housefun_districts": [("桃園市", "中壢區"), ("桃園市", "大園區")],
        "region_groups": {
            "青埔周邊（中壢/大園）": ["中壢區", "大園區"],
        },
    },
}

# 建照查詢層（領先指標，尚未自動化）
BUILDING_PERMIT_SOURCES = {
    "新北市": "https://building-management.publicwork.ntpc.gov.tw/",
    "桃園市": "https://building.tycg.gov.tw/",
}

# 抓取設定
REQUEST_TIMEOUT = 20
REQUEST_DELAY = 1.5          # 每次請求間隔秒數
RAKUYA_MAX_PAGES = 15        # 樂屋網每組參數最多翻頁數
HOUSEFUN_MAX_PAGES = 12      # 好房網每個行政區最多翻頁數
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
