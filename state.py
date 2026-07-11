# -*- coding: utf-8 -*-
"""
狀態儲存與 diff 比對。
把每天抓到的案件清單存成 JSON，跟前一天比對出「新增案件」。
GitHub Actions 會把這個 JSON commit 回 repo，達到跨日持久化。
"""
import json
import os
from typing import List
from models import Listing

STATE_FILE = "seen_listings.json"


def load_seen() -> dict:
    """讀取已看過的案件。回傳 {uid: listing_dict}。首次執行回傳空 dict。"""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 相容性：確保是 dict
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_seen(seen: dict) -> None:
    """把最新的已看過清單寫回檔案。"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2, sort_keys=True)


def diff_new(current: List[Listing], seen: dict):
    """
    比對出這次抓到、但過去沒看過的新案件。
    同時偵測「狀態變化」（例如從 最新推案 -> 公開銷售），這類也值得通知。

    回傳 (new_listings, status_changed, updated_seen)
      new_listings    : 全新案件
      status_changed  : 既有案件但銷售狀態改變（可能代表開始銷售，早鳥時機）
      updated_seen    : 更新後要存回檔案的完整清單
    """
    new_listings = []
    status_changed = []
    updated_seen = dict(seen)  # 複製一份來更新

    for lst in current:
        uid = lst.uid()
        if uid not in seen:
            new_listings.append(lst)
            updated_seen[uid] = lst.to_dict()
        else:
            old_status = seen[uid].get("status", "")
            if lst.status and lst.status != old_status:
                status_changed.append((lst, old_status))
            # 更新為最新資訊（價格、狀態可能變動）
            updated_seen[uid] = lst.to_dict()

    return new_listings, status_changed, updated_seen
