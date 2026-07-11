# -*- coding: utf-8 -*-
"""
主程式：每日執行。
流程：讀設定 -> 逐城市逐來源抓取 -> 合併去重 -> 跟昨天 diff -> 依區域分組推播 -> 存檔
"""
from config import CITIES
from adapters import ADAPTER_MAP
from state import load_seen, save_seen, diff_new
from notify import format_message, send


def collect_city(city: str, city_cfg: dict):
    """抓某城市所有來源，合併並去重。"""
    all_listings = []
    seen_uids = set()

    for source in city_cfg.get("sources", []):
        adapter = ADAPTER_MAP.get(source)
        if not adapter:
            print(f"[{city}] 未知來源 {source}，略過")
            continue
        try:
            results = adapter(city, city_cfg)
            print(f"[{city}][{source}] 抓到 {len(results)} 筆")
        except Exception as e:
            print(f"[{city}][{source}] 例外：{e}")
            results = []

        # 同城市內跨來源去重（同一個案子可能同時出現在樂屋網和住展）
        for lst in results:
            uid = lst.uid()
            if uid not in seen_uids:
                seen_uids.add(uid)
                all_listings.append(lst)

    return all_listings


def main():
    seen = load_seen()
    updated_seen = dict(seen)
    all_messages = []

    for city, city_cfg in CITIES.items():
        if not city_cfg.get("enabled", True):
            continue

        current = collect_city(city, city_cfg)
        new_listings, status_changed, city_seen = diff_new(current, updated_seen)
        updated_seen = city_seen  # 累積更新

        msg = format_message(
            city, city_cfg.get("region_groups", {}),
            new_listings, status_changed,
        )
        if msg:
            all_messages.append(msg)

        print(f"[{city}] 新案 {len(new_listings)} 筆、"
              f"狀態變化 {len(status_changed)} 筆")

    # 首次執行（seen 為空）時，只建立基準線、不推播海量歷史案件
    if not seen:
        print("首次執行：建立基準線，本次不推播（避免一次通知全部既有案件）")
        save_seen(updated_seen)
        return

    if all_messages:
        final = "\n\n".join(all_messages)
        send(final)
    else:
        send("")  # 內部會判斷無新案不推播

    save_seen(updated_seen)


if __name__ == "__main__":
    main()
